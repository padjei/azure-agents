"""
Claude-Powered Azure Data Architect Agent
==========================================

A terminal-runnable AI agent that acts as a Principal Azure Data Architect. It
combines deep Azure platform expertise (Synapse, ADLS Gen2, Data Factory, SQL,
Cosmos DB, Event Hubs, Databricks, Purview), data modeling (Kimball dimensional,
medallion lakehouse), ETL/ELT pipeline design, and security-by-design to help
you design scalable, secure, and efficient data solutions.

It has two kinds of tools:
  * Discovery (read-only): inventory and inspect your existing Azure data estate
    so recommendations are grounded in reality.
  * Design (generative): produce concrete artifacts — lakehouse layouts, star
    schemas + DDL, and ingestion pipeline blueprints.

Reasoning is driven by Anthropic Claude via LangChain/LangGraph. Both Claude and
Azure are reached without secrets in code: Claude via your Claude subscription
(OAuth, `ant auth login`) and Azure via DefaultAzureCredential (your `az login`
session).

Run (keyless):
    az login          # Azure access (DefaultAzureCredential reuses this session)
    ant auth login    # Claude access via your Claude subscription (OAuth)
    python data_architect_agent.py

No ANTHROPIC_API_KEY is required. To use an Anthropic API key instead of the
subscription, set ANTHROPIC_API_KEY (env var or a local .env file) and it wins.
"""

import os
import sys
import json
import re
import shutil
import subprocess
from typing import Dict, Any, List

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.sql import SqlManagementClient
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent


# ==========================================================
# 1. AZURE AUTHENTICATION & CLIENT BOOTSTRAP
# ==========================================================
try:
    credential = DefaultAzureCredential(exclude_shared_token_cache_credential=True)
    sub_client = SubscriptionClient(credential)

    subscriptions = list(sub_client.subscriptions.list())
    if not subscriptions:
        print("[-] Error: No active Azure subscriptions found for this identity.")
        sys.exit(1)

    ACTIVE_SUBSCRIPTION_ID = subscriptions[0].subscription_id
    print("[+] Authenticated Successfully to Azure Active Directory/Entra ID")
    print(f"[+] Operational Scope: {subscriptions[0].display_name} ({ACTIVE_SUBSCRIPTION_ID})\n")

    resource_client = ResourceManagementClient(credential, ACTIVE_SUBSCRIPTION_ID)
    storage_client = StorageManagementClient(credential, ACTIVE_SUBSCRIPTION_ID)
    sql_client = SqlManagementClient(credential, ACTIVE_SUBSCRIPTION_ID)

except Exception as e:  # noqa: BLE001
    print(f"[-] Authentication Initialization Failed: {str(e)}")
    sys.exit(1)


# Data-platform resource types the architect cares about, grouped by role.
DATA_PLATFORM_TYPES = {
    "Microsoft.Synapse/workspaces": "Analytics — Synapse Workspace",
    "Microsoft.Databricks/workspaces": "Analytics — Databricks",
    "Microsoft.Kusto/clusters": "Analytics — Data Explorer (Kusto)",
    "Microsoft.DataFactory/factories": "Integration — Data Factory",
    "Microsoft.StreamAnalytics/streamingjobs": "Streaming — Stream Analytics",
    "Microsoft.EventHub/namespaces": "Streaming — Event Hubs",
    "Microsoft.Storage/storageAccounts": "Storage — Storage / Data Lake",
    "Microsoft.Sql/servers": "OLTP/OLAP — Azure SQL",
    "Microsoft.DBforPostgreSQL/flexibleServers": "OLTP — PostgreSQL",
    "Microsoft.DBforMySQL/flexibleServers": "OLTP — MySQL",
    "Microsoft.DocumentDB/databaseAccounts": "NoSQL — Cosmos DB",
    "Microsoft.Purview/accounts": "Governance — Microsoft Purview",
}


def _pascal(text: str) -> str:
    parts = re.split(r"[^0-9a-zA-Z]+", (text or "").strip())
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Entity"


def _split_list(text: str) -> List[str]:
    return [t.strip() for t in re.split(r"[,;\n]+", text or "") if t.strip()]


# ==========================================================
# 2. DISCOVERY TOOLS (READ-ONLY)
# ==========================================================

@tool
def discover_data_estate() -> str:
    """
    Read-only inventory of the Azure data platform in the active subscription.
    Groups data-relevant resources (Synapse, SQL, Data Factory, Storage/Data Lake,
    Cosmos DB, Event Hubs, Databricks, Purview, etc.) so architecture recommendations
    are grounded in what already exists. Use this first when asked to assess or design.
    """
    try:
        resources = resource_client.resources.list()
        estate: Dict[str, List[Dict[str, str]]] = {}
        total = 0
        for r in resources:
            role = DATA_PLATFORM_TYPES.get(r.type)
            if not role:
                continue
            total += 1
            estate.setdefault(role, []).append({
                "Name": r.name,
                "ResourceGroup": r.id.split("/")[4] if "/" in r.id else "Unknown",
                "Location": r.location,
            })

        summary = {
            "Subscription": ACTIVE_SUBSCRIPTION_ID,
            "DataResourceCount": total,
            "MissingCapabilities": [
                role for t, role in DATA_PLATFORM_TYPES.items()
                if role not in estate
            ],
            "Estate": estate or "No recognized data-platform resources found.",
        }
        return json.dumps(summary, indent=2)
    except Exception as e:  # noqa: BLE001
        return f"Error discovering data estate: {str(e)}"


@tool
def inspect_data_lake_storage() -> str:
    """
    Read-only assessment of Storage accounts for data-lake suitability. Reports whether
    hierarchical namespace (ADLS Gen2) is enabled, redundancy (SKU), encryption, TLS,
    and public access — the properties that matter for a secure, scalable lakehouse.
    """
    try:
        accounts = storage_client.storage_accounts.list()
        report = []
        for a in accounts:
            is_hns = bool(getattr(a, "is_hns_enabled", False))
            sku = getattr(getattr(a, "sku", None), "name", "Unknown")
            public = getattr(a, "allow_blob_public_access", None)
            https_only = getattr(a, "enable_https_traffic_only", None)
            net = getattr(a, "network_rule_set", None)
            default_action = getattr(net, "default_action", "Allow (no firewall)") if net else "Allow (no firewall)"
            report.append({
                "StorageAccount": a.name,
                "ResourceGroup": a.id.split("/")[4] if "/" in a.id else "Unknown",
                "Location": a.location,
                "Redundancy": sku,
                "IsDataLakeGen2": is_hns,
                "HttpsOnly": https_only,
                "PublicBlobAccess": public,
                "NetworkDefaultAction": default_action,
                "DataLakeAssessment": (
                    "Ready for lakehouse" if is_hns and default_action == "Deny"
                    else "Usable, but harden: " + ", ".join(
                        ([] if is_hns else ["enable hierarchical namespace"])
                        + ([] if default_action == "Deny" else ["restrict network access / add private endpoint"])
                        + ([] if public is False else ["disable public blob access"])
                    )
                ),
            })
        return json.dumps(report, indent=2) if report else "No Storage accounts found in this subscription."
    except Exception as e:  # noqa: BLE001
        return f"Error inspecting data lake storage: {str(e)}"


@tool
def inspect_sql_estate() -> str:
    """
    Read-only inventory of Azure SQL logical servers and their databases, including
    service tier / SKU and status. Useful for understanding the current OLTP/OLAP
    footprint before designing a serving layer or migration.
    """
    try:
        servers = sql_client.servers.list()
        report = []
        for s in servers:
            rg = s.id.split("/")[4] if "/" in s.id else "Unknown"
            databases = []
            try:
                for db in sql_client.databases.list_by_server(rg, s.name):
                    if db.name == "master":
                        continue
                    sku = getattr(db, "sku", None)
                    databases.append({
                        "Database": db.name,
                        "Tier": getattr(sku, "tier", None) or getattr(sku, "name", "Unknown"),
                        "Status": getattr(db, "status", "Unknown"),
                    })
            except Exception as inner:  # noqa: BLE001
                databases = [{"Error": f"Could not list databases: {str(inner)}"}]
            report.append({
                "SqlServer": s.name,
                "ResourceGroup": rg,
                "Location": s.location,
                "PublicNetworkAccess": getattr(s, "public_network_access", "Unknown"),
                "Databases": databases,
            })
        return json.dumps(report, indent=2) if report else "No Azure SQL servers found in this subscription."
    except Exception as e:  # noqa: BLE001
        return f"Error inspecting SQL estate: {str(e)}"


# ==========================================================
# 3. DESIGN TOOLS (GENERATIVE ARTIFACTS)
# ==========================================================

@tool
def design_medallion_lakehouse(domain: str, source_systems: str = "") -> str:
    """
    Produces a Bronze/Silver/Gold (medallion) lakehouse design on ADLS Gen2 + Delta Lake
    for a data domain. Returns zone layout, path conventions, formats, governance, and
    security recommendations.

    Args:
        domain: Business/data domain (e.g. "claims", "sales", "telemetry").
        source_systems: Optional comma-separated list of source systems feeding the lake.
    """
    d = (domain or "domain").strip().lower().replace(" ", "_")
    sources = _split_list(source_systems) or ["<define source systems>"]
    design = {
        "Domain": domain or "unspecified",
        "Pattern": "Medallion (Bronze/Silver/Gold) Lakehouse on ADLS Gen2 + Delta Lake",
        "StorageFoundation": {
            "Service": "Azure Data Lake Storage Gen2 (hierarchical namespace enabled)",
            "Redundancy": "ZRS minimum; GRS/RA-GRS for production DR",
            "TableFormat": "Delta Lake (ACID, time travel) for Silver & Gold",
            "RawFormat": "Source-native (JSON/CSV/Parquet) retained immutably in Bronze",
        },
        "Zones": [
            {
                "Zone": "Bronze (Raw)",
                "Container": "bronze",
                "PathConvention": f"bronze/{d}/{{source}}/{{yyyy}}/{{MM}}/{{dd}}/",
                "Purpose": "Immutable landing of source data exactly as received",
                "Format": "Source-native",
            },
            {
                "Zone": "Silver (Cleansed & Conformed)",
                "Container": "silver",
                "PathConvention": f"silver/{d}/{{entity}}/",
                "Purpose": "Deduplicated, typed, validated, conformed to canonical model",
                "Format": "Delta",
            },
            {
                "Zone": "Gold (Curated & Serving)",
                "Container": "gold",
                "PathConvention": f"gold/{d}/{{mart}}/",
                "Purpose": "Business-level aggregates / dimensional models for BI & ML",
                "Format": "Delta (optionally served to Synapse dedicated SQL pool)",
            },
        ],
        "SourceSystems": sources,
        "Governance": [
            "Register the lake in Microsoft Purview for catalog, classification, and lineage",
            "Data-quality gates between Bronze->Silver (schema + expectation checks)",
            "PII tagging and column-level classification at Silver",
        ],
        "Security": [
            "Private endpoints on the storage account; disable public blob access",
            "Customer-managed keys (CMK) via Key Vault for encryption at rest",
            "POSIX ACLs on paths + Azure RBAC for coarse-grained access",
            "Synapse Data Exfiltration Protection when reading/writing from Synapse",
        ],
        "Observability": "Stream pipeline runs to Log Analytics + immutable archive (see infra/ in this repo).",
    }
    return json.dumps(design, indent=2)


@tool
def design_dimensional_model(business_process: str, grain: str = "",
                             measures: str = "", dimensions: str = "") -> str:
    """
    Produces a Kimball star-schema design for a business process, plus a Synapse-optimized
    T-SQL DDL sketch (distribution + columnstore guidance).

    Args:
        business_process: e.g. "retail sales", "insurance claims".
        grain: The fact grain, e.g. "one row per order line".
        measures: Comma-separated measures, e.g. "quantity, unit_price, discount".
        dimensions: Comma-separated dimensions, e.g. "date, customer, product, store".
    """
    fact_name = f"Fact{_pascal(business_process)}"
    measure_list = _split_list(measures) or ["amount", "quantity"]
    dim_list = _split_list(dimensions) or ["date", "customer", "product"]

    dims = []
    for dname in dim_list:
        is_date = dname.lower() in ("date", "time", "calendar")
        dims.append({
            "Name": f"Dim{_pascal(dname)}",
            "SurrogateKey": f"{_pascal(dname)}Key",
            "SCD": "Type 0 (static)" if is_date else "Type 2 (track history)",
        })

    # Build a Synapse dedicated SQL pool DDL sketch.
    fk_cols = "\n".join(f"    {d['SurrogateKey']} INT NOT NULL," for d in dims)
    measure_cols = "\n".join(f"    {m.replace(' ', '_')} DECIMAL(18,2) NULL," for m in measure_list)
    ddl = (
        f"-- Synapse dedicated SQL pool: fact uses HASH distribution + clustered columnstore\n"
        f"CREATE TABLE dbo.{fact_name}\n"
        f"(\n"
        f"{fk_cols}\n"
        f"{measure_cols}\n"
        f"    LoadDate DATETIME2 NOT NULL\n"
        f")\n"
        f"WITH (DISTRIBUTION = HASH({dims[0]['SurrogateKey']}), CLUSTERED COLUMNSTORE INDEX);\n\n"
        + "".join(
            f"-- {d['Name']} ({d['SCD']})\n"
            f"CREATE TABLE dbo.{d['Name']}\n"
            f"(\n    {d['SurrogateKey']} INT NOT NULL,\n    BusinessKey NVARCHAR(100) NOT NULL,\n"
            f"    -- descriptive attributes ...\n    RowIsCurrent BIT NOT NULL,\n    RowStartDate DATETIME2 NOT NULL,\n    RowEndDate DATETIME2 NULL\n)\n"
            f"WITH (DISTRIBUTION = REPLICATE, CLUSTERED COLUMNSTORE INDEX);\n\n"
            for d in dims
        )
    )

    design = {
        "BusinessProcess": business_process or "unspecified",
        "Grain": grain or "DEFINE THE GRAIN (one row per ...)",
        "FactTable": {
            "Name": fact_name,
            "Type": "Transaction fact (consider periodic snapshot / accumulating snapshot if needed)",
            "Measures": measure_list,
            "ForeignKeys": [d["SurrogateKey"] for d in dims],
        },
        "Dimensions": dims,
        "SynapseOptimizations": [
            f"Fact: HASH distribution on {dims[0]['SurrogateKey']} (high-cardinality FK) + clustered columnstore",
            "Small dimensions: REPLICATE; very large dimensions: consider ROUND_ROBIN or HASH",
            "Partition the fact by the date key for load/prune efficiency",
            "Load via CTAS/partition switching for performant batch loads",
        ],
        "DDL_Sketch": ddl,
    }
    return json.dumps(design, indent=2)


@tool
def design_ingestion_pipeline(source_type: str, target: str = "Synapse dedicated SQL pool",
                              pattern: str = "batch") -> str:
    """
    Produces an ETL/ELT ingestion pipeline blueprint: recommended service, stages,
    incremental-load strategy, reliability, security, and observability.

    Args:
        source_type: e.g. "on-prem SQL Server", "REST API", "Event Hub", "SaaS (Salesforce)".
        target: Serving target, e.g. "Synapse dedicated SQL pool", "Delta Gold".
        pattern: "batch", "micro-batch", or "streaming".
    """
    p = (pattern or "batch").strip().lower()
    service = {
        "streaming": "Event Hubs + Azure Stream Analytics (or Spark Structured Streaming on Databricks/Synapse)",
        "micro-batch": "Synapse Spark / Databricks Auto Loader (incremental file ingestion)",
    }.get(p, "Azure Data Factory or Synapse Pipelines (Copy activity + Mapping Data Flows)")

    incremental = (
        "Event-time watermarking with checkpointing; exactly-once sink where supported"
        if p == "streaming"
        else "High-watermark column (LastModified) or native CDC; store the watermark in a control table"
    )

    design = {
        "Source": source_type or "unspecified",
        "Target": target,
        "Pattern": p,
        "RecommendedService": service,
        "Stages": [
            {"Stage": "Extract", "Detail": f"Connect to {source_type or 'source'} via a managed-identity linked service (no secrets)"},
            {"Stage": "Land (Bronze)", "Detail": "Write raw, immutable copy to ADLS Gen2 partitioned by ingest date"},
            {"Stage": "Transform (Silver)", "Detail": "Cleanse, dedupe, type, conform to canonical model (Delta)"},
            {"Stage": "Serve (Gold/SQL)", "Detail": f"Curate and publish to {target} for BI/ML consumption"},
        ],
        "IncrementalStrategy": incremental,
        "Orchestration": "Metadata-driven, parameterized pipelines with schedule/tumbling-window triggers",
        "Reliability": [
            "Retry policies with exponential backoff on activities",
            "Idempotent loads (MERGE / partition overwrite) so re-runs are safe",
            "Dead-letter path for records that fail validation",
        ],
        "Security": [
            "Self-hosted or managed Integration Runtime with Managed Private Endpoints for sources",
            "Enable Synapse Data Exfiltration Protection (approved egress targets only)",
            "Managed Identity for all linked services; secrets (if any) in Key Vault",
        ],
        "Observability": (
            "Stream IntegrationPipelineRuns / IntegrationActivityRuns to Log Analytics and an "
            "immutable archive — see infra/ in this repo for the HITRUST r2 diagnostic-logging setup."
        ),
    }
    return json.dumps(design, indent=2)


# ==========================================================
# 4. AGENT ORCHESTRATION VIA CLAUDE
# ==========================================================

architect_tools = [
    discover_data_estate,
    inspect_data_lake_storage,
    inspect_sql_estate,
    design_medallion_lakehouse,
    design_dimensional_model,
    design_ingestion_pipeline,
]

def _oauth_access_token():
    """Mint a short-lived Claude OAuth access token from the `ant auth login`
    profile. Returns None if the `ant` CLI is missing or you're not signed in."""
    if not shutil.which("ant"):
        return None
    try:
        result = subprocess.run(
            ["ant", "auth", "print-credentials", "--access-token"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = result.stdout.strip()
    return token if result.returncode == 0 and token else None


def build_llm():
    """Instantiate Claude, defaulting to your Claude subscription (OAuth) rather
    than an API key. Model is overridable via the CLAUDE_MODEL env var.

    Credential resolution, first match wins:
      1. ANTHROPIC_API_KEY     — explicit Anthropic API-key override.
      2. ANTHROPIC_AUTH_TOKEN  — a Bearer token already in the environment.
      3. Claude subscription   — a short-lived OAuth token minted here from the
                                 `ant auth login` profile via the `ant` CLI.
    """
    model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

    # Explicit API key wins if provided.
    if os.getenv("ANTHROPIC_API_KEY"):
        return ChatAnthropic(model=model, temperature=0)

    # Otherwise default to subscription OAuth. Mint a token from the signed-in
    # profile unless one is already present in the environment.
    if not os.getenv("ANTHROPIC_AUTH_TOKEN"):
        token = _oauth_access_token()
        if token:
            os.environ["ANTHROPIC_AUTH_TOKEN"] = token

    if not os.getenv("ANTHROPIC_AUTH_TOKEN"):
        sys.exit(
            "[!] No Claude credentials found.\n"
            "    - Recommended: sign in with your Claude subscription -> run `ant auth login`.\n"
            "    - Or set ANTHROPIC_API_KEY (Anthropic API key) in your environment or .env.\n"
            "    Install the ant CLI: https://platform.claude.com/docs/en/api/sdks/cli"
        )

    # Hand the OAuth token to the SDK the way it expects: Authorization: Bearer
    # (api_key=None disables x-api-key) plus the OAuth beta header for /v1/messages.
    return ChatAnthropic(
        model=model,
        temperature=0,
        anthropic_api_key=None,
        default_headers={"anthropic-beta": "oauth-2025-04-20"},
    )


llm = build_llm()

system_prompt = (
    "You are a Principal Azure Data Architect. You combine deep Azure platform expertise "
    "(Synapse, ADLS Gen2, Data Factory, Azure SQL, Cosmos DB, Event Hubs, Databricks, Purview), "
    "data modeling (Kimball dimensional, Data Vault, medallion lakehouse), ETL/ELT and pipeline "
    "design, security-by-design, and cost/scalability judgement. You communicate clearly for both "
    "technical engineers and business stakeholders.\n\n"
    "Operating method:\n"
    "1. Understand the requirement and the CURRENT estate first — call discover_data_estate and the "
    "inspect_* tools before proposing designs, so recommendations are grounded in reality.\n"
    "2. Offer options with explicit trade-offs (scalability, cost, operational complexity), then a "
    "clear recommendation.\n"
    "3. Produce concrete artifacts using the design_* tools (lakehouse layout, star schema + DDL, "
    "ingestion blueprint), then narrate the rationale.\n"
    "4. ALWAYS fold in security (private endpoints, Data Exfiltration Protection, CMK, RBAC, "
    "classification) and observability (diagnostic logging to Log Analytics) — never bolt them on later.\n"
    "5. State assumptions explicitly and ask for the grain, SLAs, data volumes, and latency needs when "
    "they materially change the design."
)


def _build_react_agent(model, agent_tools, prompt):
    """Construct a ReAct agent, tolerating the langgraph `state_modifier` -> `prompt`
    parameter rename across versions."""
    try:
        return create_react_agent(model, agent_tools, prompt=prompt)
    except TypeError:
        return create_react_agent(model, agent_tools, state_modifier=prompt)


data_architect_agent = _build_react_agent(llm, architect_tools, system_prompt)


# ==========================================================
# 5. INTERACTIVE TERMINAL RUNTIME
# ==========================================================
if __name__ == "__main__":
    print("==================================================================")
    print("🏛️  CLAUDE-POWERED AZURE DATA ARCHITECT AGENT ACTIVATED  🏛️")
    print("==================================================================")
    print("[*] Expertise: Synapse, ADLS Gen2, Data Factory, SQL, Cosmos, Event Hubs, Databricks, Purview.")
    print("Ask a data architecture question, e.g.:")
    print("  - Assess my current data estate and recommend a lakehouse design.")
    print("  - Design a star schema for retail sales at order-line grain.")
    print("  - Blueprint a streaming ingestion pipeline from Event Hub to a Gold Delta table.")
    print("(Type 'quit' to exit)\n")

    while True:
        try:
            user_input = input("Azure-Data-Architect > ")
            if user_input.lower() in ["exit", "quit"]:
                print("[*] Session terminated.")
                break
            if not user_input.strip():
                continue

            events = data_architect_agent.stream(
                {"messages": [("user", user_input)]},
                stream_mode="values",
            )
            for event in events:
                if "messages" in event:
                    last_message = event["messages"][-1]
                    if last_message.type == "ai" and last_message.content:
                        print(f"\n[Data Architect Recommendations]:\n{last_message.content}\n")
        except KeyboardInterrupt:
            print("\n[*] Manual session override requested.")
            break
        except Exception as e:  # noqa: BLE001
            print(f"[-] Runtime execution failure occurred: {str(e)}")

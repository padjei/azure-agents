# Claude-Powered Azure Agents

Terminal-runnable AI agents for Azure, driven by **Anthropic Claude** via **LangChain / LangGraph**.
Azure access uses `DefaultAzureCredential`, so they authenticate from your existing `az login`
session — **no secrets are stored in code**. Two agents share one runtime/image:

1. **Security & Compliance agent** (`azure_security_agent.py`) — audits an Azure subscription's
   security posture and produces remediation / Azure Policy templates for frameworks such as
   **HITRUST CSF r2**.
2. **Data Architect agent** (`data_architect_agent.py`) — assesses your data estate and designs
   scalable, secure data solutions (lakehouse layouts, dimensional models + DDL, ingestion pipelines).

## What's inside

| File | Purpose |
| ---- | ------- |
| `azure_security_agent.py` | **Security agent.** Audits NSGs, Key Vault, Defender for Cloud, Resource Groups, Azure Policy, and Synapse diagnostic logging; generates remediation policy JSON. |
| `data_architect_agent.py` | **Data Architect agent.** Discovers the data estate and designs medallion lakehouses, Kimball star schemas + Synapse DDL, and ETL/ELT pipeline blueprints. |
| `requirements.txt` | Pinned Python dependencies. |
| `Dockerfile` / `docker-compose.yml` | Containerized runtime — run on any laptop with only Docker. |
| `docs/hitrust_r2_retention_framework.md` | HITRUST r2 Synapse hardening, retention, and PRISMA maturity guidance. |
| `kql/*.kql` | Log Analytics audit queries for Synapse ETL egress and pipeline tampering. |
| `infra/` | Bicep + CLI bootstrap and a DeployIfNotExists policy that establish and enforce Synapse diagnostic logging (see `infra/README.md`). |
| `.env.example` | Template for your local `.env` (never commit the real `.env`). |

## Security agent tools (skills)

- `audit_network_security_groups` — flags overly permissive inbound NSG rules (Any-source Allow).
- `audit_key_vault_access_and_networking` — flags Key Vaults exposed to the public internet.
- `extract_defender_for_cloud_alerts` — pulls active Microsoft Defender for Cloud alerts.
- `audit_resource_groups` — flags missing compliance tags (`Environment`, `HITRUST`).
- `check_policy_compliance` — lists non-compliant resources from Azure Policy Insights.
- `audit_synapse_diagnostic_settings` — **read-only** check that every Synapse workspace streams the required HITRUST r2 audit categories to Log Analytics + an immutable archive.
- `generate_remediation_policy` — emits an Azure Policy JSON definition for a named framework.

## Data Architect agent tools (skills)

Discovery (read-only):
- `discover_data_estate` — inventories data-platform resources (Synapse, SQL, Data Factory, Storage/Data Lake, Cosmos, Event Hubs, Databricks, Purview…).
- `inspect_data_lake_storage` — assesses Storage accounts for lakehouse suitability (ADLS Gen2 / redundancy / encryption / public access).
- `inspect_sql_estate` — inventories Azure SQL servers/databases and tiers.

Design (generative):
- `design_medallion_lakehouse` — Bronze/Silver/Gold layout on ADLS Gen2 + Delta, with governance & security.
- `design_dimensional_model` — Kimball star schema + Synapse-optimized T-SQL DDL (distribution + columnstore).
- `design_ingestion_pipeline` — ETL/ELT blueprint (service choice, incremental strategy, reliability, security, observability).

## Diagnostic logging (HITRUST r2)

Audit logging is a *control*, not a one-off fix — it only captures events once it's on, so it must
be established up front and kept on continuously. This repo follows a **read-only agent + Azure
Policy enforcement** model:

- **Establish + enforce** (not the agent): `infra/bicep` or `infra/cli` stands up the baseline
  (Log Analytics 365d + immutable WORM archive + diagnostic setting); `infra/policy` assigns a
  `DeployIfNotExists` policy so any workspace that lacks it is auto-remediated.
- **Verify** (the agent): `audit_synapse_diagnostic_settings` reports per-workspace whether logging
  is correctly configured — it never enables anything itself.

See [`infra/README.md`](infra/README.md) for the full runbook.

---

## Quick start (Docker — recommended)

You only need **Docker Desktop** and the **Azure CLI** installed. No local Python required.

```bash
# 1. Authenticate to Azure on your host machine
az login

# 2. Put your Anthropic key in a local .env file
cp .env.example .env
#   then edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 3. Build + launch an interactive agent (compose reads ANTHROPIC_API_KEY from .env)
docker compose run --rm agent            # security & compliance agent
docker compose run --rm data-architect   # data architect agent
```

`--rm` auto-removes the container on exit. The compose file mounts `~/.azure` into the container
so `DefaultAzureCredential` reuses your host `az login` — no second login inside Docker.

## Quick start (local Python)

> Requires **Python 3.11 or 3.12** (the pinned dependencies predate Python 3.14).

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."   # or use the .env file
az login

python azure_security_agent.py     # security & compliance agent
python data_architect_agent.py     # data architect agent
```

## Example prompts

**Security agent:**
```
Run a full scan on my network layers and secrets storage. Are there any vectors
exposed that breach HITRUST compliance?

Check Microsoft Defender for Cloud alerts and generate an Azure Policy that
permanently denies any wide internet-to-internal data tier routing.
```

**Data Architect agent:**
```
Assess my current data estate and recommend a medallion lakehouse design for the
claims domain.

Design a star schema for retail sales at order-line grain, then blueprint a
batch ingestion pipeline from on-prem SQL Server into a Synapse dedicated SQL pool.
```

Type `quit` or `exit` to end the session.

## Choosing the Claude model

Defaults to `claude-sonnet-4-6`. Override without editing code via the `CLAUDE_MODEL` env var
(e.g. `CLAUDE_MODEL=claude-opus-4-8` for deeper reasoning).

## Security notes

- `.env` is git-ignored — your API key never reaches GitHub. Commit only `.env.example`.
- The agent performs **read-only audits**; it drafts policy JSON but does not apply changes.
- Azure permissions come from your signed-in identity; the agent can only see what you can.

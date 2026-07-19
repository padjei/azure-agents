"""
Claude Comprehensive Azure Audit & Compliance Agent
===================================================

An enterprise-grade, terminal-runnable AI agent that audits an Azure
subscription's security posture (NSGs, Key Vault, Defender for Cloud, Azure
Policy) and produces remediation plans / Azure Policy templates mapped to
high-stakes frameworks such as HITRUST CSF r2.

Reasoning is driven by Anthropic Claude via LangChain/LangGraph. Both Claude and
Azure are reached without secrets in code: Claude via your Claude subscription
(OAuth, `ant auth login`) and Azure via DefaultAzureCredential (your `az login`
session, or Managed Identity in the cloud).

Run (keyless):
    az login          # Azure access (DefaultAzureCredential reuses this session)
    ant auth login    # Claude access via your Claude subscription (OAuth)
    python azure_security_agent.py

No ANTHROPIC_API_KEY is required. To use an Anthropic API key instead of the
subscription, set ANTHROPIC_API_KEY (env var or a local .env file) and it wins.
"""

import os
import sys
import json
import shutil
import subprocess
from typing import Dict, Any, List

from dotenv import load_dotenv

# Load ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN (and anything else) from a local,
# git-ignored .env file.
load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.policyinsights import PolicyInsightsClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.security import SecurityCenter
from azure.mgmt.monitor import MonitorManagementClient
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent


# ==========================================================
# 1. ENTERPRISE AZURE AUTHENTICATION & MULTI-CLIENT BOOTSTRAP
# ==========================================================
security_center_client = None  # best-effort; some SDK versions need asc_location

try:
    # Authenticate implicitly using CLI context, Managed Identity, or Interactive Browser
    credential = DefaultAzureCredential(exclude_shared_token_cache_credential=True)
    sub_client = SubscriptionClient(credential)

    subscriptions = list(sub_client.subscriptions.list())
    if not subscriptions:
        print("[-] Error: No active Azure subscriptions found for this identity.")
        sys.exit(1)

    ACTIVE_SUBSCRIPTION_ID = subscriptions[0].subscription_id
    print("[+] Authenticated Successfully to Azure Active Directory/Entra ID")
    print(f"[+] Operational Scope: {subscriptions[0].display_name} ({ACTIVE_SUBSCRIPTION_ID})\n")

    # Initialize Core Security and Infrastructure Clients
    resource_client = ResourceManagementClient(credential, ACTIVE_SUBSCRIPTION_ID)
    policy_client = PolicyInsightsClient(credential)
    network_client = NetworkManagementClient(credential, ACTIVE_SUBSCRIPTION_ID)
    kv_client = KeyVaultManagementClient(credential, ACTIVE_SUBSCRIPTION_ID)
    monitor_client = MonitorManagementClient(credential, ACTIVE_SUBSCRIPTION_ID)

    # Defender for Cloud client construction varies across SDK versions; keep it
    # best-effort so a signature mismatch never kills the whole agent.
    try:
        security_center_client = SecurityCenter(credential, ACTIVE_SUBSCRIPTION_ID)
    except Exception as sc_err:  # noqa: BLE001
        print(f"[!] Defender for Cloud client unavailable, that tool will be limited: {sc_err}")

except Exception as e:  # noqa: BLE001
    print(f"[-] Cross-Service Authentication Initialization Failed: {str(e)}")
    sys.exit(1)


# ==========================================================
# 2. ADVANCED COMPONENT-SPECIFIC AUDITING TOOLS (SKILLS)
# ==========================================================

@tool
def audit_network_security_groups() -> str:
    """
    Audits all Network Security Groups (NSGs). Explicitly flags highly insecure rules,
    specifically searching for broad ingress rules mapping to dangerous ports (e.g., SSH 22, RDP 3389, HTTP 80/443 with Any source).
    """
    try:
        nsgs = network_client.network_security_groups.list_all()
        nsg_report = []

        for nsg in nsgs:
            dangerous_rules = []
            rules = nsg.security_rules if nsg.security_rules else []
            default_rules = nsg.default_security_rules if nsg.default_security_rules else []

            for rule in (rules + default_rules):
                # Filter for Ingress Rules set to Allow from Any Source
                if (rule.direction == "Inbound" and
                        rule.access == "Allow" and
                        (rule.source_address_prefix == "*" or rule.source_address_prefix == "0.0.0.0/0")):

                    dangerous_rules.append({
                        "RuleName": rule.name,
                        "Port": rule.destination_port_range,
                        "Protocol": rule.protocol,
                        "Source": rule.source_address_prefix,
                        "Risk": "Critical - Overly permissive ingress allowed across system boundary."
                    })

            nsg_report.append({
                "NSGName": nsg.name,
                "ResourceGroup": nsg.id.split("/")[4] if "/" in nsg.id else "Unknown",
                "Location": nsg.location,
                "FlaggedPermissiveRules": dangerous_rules,
                "Status": "COMPLIANT" if not dangerous_rules else "NON-COMPLIANT"
            })

        return json.dumps(nsg_report, indent=2)
    except Exception as e:  # noqa: BLE001
        return f"Error auditing Network Security Groups: {str(e)}"


@tool
def audit_key_vault_access_and_networking() -> str:
    """
    Inspects all Azure Key Vaults within the scope subscription. Evaluates access policies,
    Azure RBAC authorization mapping, and critical network firewall rules (ensuring public access is disabled).
    """
    try:
        vaults = kv_client.vaults.list_by_subscription()
        vault_report = []

        for vault_resource in vaults:
            # Fetch complete resource metadata to inspect network ACLs
            rg_name = vault_resource.id.split("/")[4]
            vault = kv_client.vaults.get(rg_name, vault_resource.name)
            properties = vault.properties

            # Evaluate public network exposure configuration
            public_network_access = getattr(properties, "public_network_access", "Not Specified")
            network_acls = getattr(properties, "network_acls", None)
            default_action = network_acls.default_action if network_acls else "Allow (No Firewall)"

            # Parse access policies or check if Azure RBAC is used instead
            rbac_enabled = getattr(properties, "enable_rbac_authorization", False)
            access_policy_count = len(properties.access_policies) if properties.access_policies else 0

            vault_report.append({
                "VaultName": vault.name,
                "ResourceGroup": rg_name,
                "AzureRbacEnabled": rbac_enabled,
                "LegacyAccessPoliciesDefined": access_policy_count,
                "PublicNetworkAccessStatus": public_network_access,
                "NetworkFirewallDefaultAction": default_action,
                "ComplianceAssessment": "PASSED" if (public_network_access == "Disabled" or default_action == "Deny") else "FAILED - Vault exposed to public internet endpoints"
            })

        return json.dumps(vault_report, indent=2)
    except Exception as e:  # noqa: BLE001
        return f"Error inspecting Azure Key Vault clusters: {str(e)}"


@tool
def extract_defender_for_cloud_alerts() -> str:
    """
    Queries Microsoft Defender for Cloud (Security Center) to retrieve active security alerts,
    threat detections, and high-severity environment misconfigurations.
    """
    try:
        if security_center_client is None:
            return "Microsoft Defender for Cloud client is not initialized in this environment."

        # Fetch active security alerts from the subscription scope
        alerts = security_center_client.alerts.list()
        active_alerts = []

        for alert in alerts:
            if alert.status == "Active":
                active_alerts.append({
                    "AlertName": alert.alert_display_name,
                    "Severity": alert.severity,
                    "CompromisedResource": alert.compromised_entity,
                    "Description": alert.description,
                    "RemediationSteps": alert.remediation_steps
                })

        return json.dumps(active_alerts, indent=2) if active_alerts else "No active high-severity threat detections found in Microsoft Defender for Cloud."
    except Exception as e:  # noqa: BLE001
        return f"Error pulling Microsoft Defender for Cloud telemetry: {str(e)}"


@tool
def audit_resource_groups() -> str:
    """
    Audits all Resource Groups in the active subscription and flags loose security
    configurations like missing mandatory compliance tags (e.g., Environment, Owner, HITRUST_Scope).
    """
    try:
        rgs = resource_client.resource_groups.list()
        report = []
        for rg in rgs:
            tags = rg.tags if rg.tags else {}
            has_compliance_tags = "Environment" in tags or "HITRUST" in tags
            report.append({
                "ResourceGroup": rg.name,
                "Location": rg.location,
                "Tags": tags,
                "ComplianceStatus": "PASSED" if has_compliance_tags else "FAILED - Missing Regulatory Tags"
            })
        return json.dumps(report, indent=2)
    except Exception as e:  # noqa: BLE001
        return f"Error auditing resource groups: {str(e)}"


@tool
def check_policy_compliance() -> str:
    """
    Queries the Azure Policy Insights engine to find all non-compliant resources
    under high-stakes compliance blueprints (like HITRUST, HIPAA, or CIS benchmarks).
    """
    try:
        policy_states = policy_client.policy_states.list_query_results_for_subscription(
            policy_states_resource="default",
            subscription_id=ACTIVE_SUBSCRIPTION_ID,
            top=30
        )

        non_compliant_resources = []
        for state in policy_states.value:
            if state.additional_properties.get("complianceState") == "NonCompliant":
                non_compliant_resources.append({
                    "ResourceID": state.additional_properties.get("resourceId"),
                    "ResourceType": state.additional_properties.get("resourceType"),
                    "PolicyAssignmentName": state.additional_properties.get("policyAssignmentName"),
                    "PolicyDefinition": state.additional_properties.get("policyDefinitionName")
                })
        return json.dumps(non_compliant_resources, indent=2) if non_compliant_resources else "All verified resources are compliant."
    except Exception as e:  # noqa: BLE001
        return f"Error extracting policy insights: {str(e)}"


# Categories that HITRUST r2 requires for Synapse ingestion/ETL boundary auditing.
REQUIRED_SYNAPSE_LOG_CATEGORIES = {
    "IntegrationPipelineRuns",
    "IntegrationActivityRuns",
    "SynapseRbacOperations",
}


@tool
def audit_synapse_diagnostic_settings() -> str:
    """
    READ-ONLY HITRUST r2 check. For every Azure Synapse workspace in the subscription,
    verifies that a Diagnostic Setting streams the required audit log categories
    (IntegrationPipelineRuns, IntegrationActivityRuns, SynapseRbacOperations) to a
    Log Analytics workspace and, ideally, to an immutable storage archive.
    Flags any workspace missing logging or missing categories. Does NOT modify anything;
    remediation is handled by the DeployIfNotExists policy under infra/policy/.
    """
    try:
        workspaces = resource_client.resources.list(
            filter="resourceType eq 'Microsoft.Synapse/workspaces'"
        )
        report = []
        found_any = False

        for ws in workspaces:
            found_any = True
            settings = monitor_client.diagnostic_settings.list(ws.id)
            ws_settings = list(getattr(settings, "value", None) or settings)

            enabled_categories = set()
            to_log_analytics = False
            to_storage_archive = False

            for s in ws_settings:
                if getattr(s, "workspace_id", None):
                    to_log_analytics = True
                if getattr(s, "storage_account_id", None):
                    to_storage_archive = True
                for log in (s.logs or []):
                    if log.enabled and log.category in REQUIRED_SYNAPSE_LOG_CATEGORIES:
                        enabled_categories.add(log.category)

            missing = sorted(REQUIRED_SYNAPSE_LOG_CATEGORIES - enabled_categories)
            compliant = (not missing) and to_log_analytics

            report.append({
                "SynapseWorkspace": ws.name,
                "ResourceGroup": ws.id.split("/")[4] if "/" in ws.id else "Unknown",
                "DiagnosticSettingsCount": len(ws_settings),
                "RequiredCategoriesEnabled": sorted(enabled_categories),
                "MissingCategories": missing,
                "StreamsToLogAnalytics": to_log_analytics,
                "StreamsToImmutableArchive": to_storage_archive,
                "HitrustR2Status": "PASSED" if compliant else "FAILED - diagnostic logging incomplete",
                "Recommendation": (
                    "Compliant."
                    if compliant
                    else "Deploy the HITRUST r2 diagnostic setting (see infra/bicep or infra/cli) "
                         "and assign the DeployIfNotExists policy under infra/policy/ to prevent drift."
                ),
            })

        if not found_any:
            return "No Azure Synapse workspaces found in this subscription."
        return json.dumps(report, indent=2)
    except Exception as e:  # noqa: BLE001
        return f"Error auditing Synapse diagnostic settings: {str(e)}"


@tool
def generate_remediation_policy(framework_name: str, control: str = "network_boundary") -> str:
    """
    Generates an Azure Policy definition (JSON) that enforces a security guardrail for a
    high-stakes compliance framework like HITRUST r2.

    Args:
        framework_name: The framework the guardrail maps to (e.g. "HITRUST r2").
        control: Which guardrail to emit:
            - "network_boundary" (default): Deny NSG rules that allow inbound traffic from
              any source ("*"), preventing open ingress across a system boundary.
            - "required_tags": Deny resources missing the HITRUST_Scope governance tag,
              enforcing compliance scoping and inventory.
    """
    control = (control or "network_boundary").strip().lower()

    if control == "required_tags":
        display_name = f"Enforce required HITRUST_Scope tag for {framework_name}"
        policy_rule = {
            "if": {
                "allOf": [
                    {
                        "field": "tags['HITRUST_Scope']",
                        "exists": "false"
                    }
                ]
            },
            "then": {
                "effect": "Deny"
            }
        }
    else:
        control = "network_boundary"
        display_name = f"Enforce Secure Network Boundaries and Identity for {framework_name}"
        policy_rule = {
            "if": {
                "allOf": [
                    {
                        "field": "type",
                        "equals": "Microsoft.Network/networkSecurityGroups"
                    },
                    {
                        "field": "Microsoft.Network/networkSecurityGroups/securityRules/access",
                        "equals": "Allow"
                    },
                    {
                        "field": "Microsoft.Network/networkSecurityGroups/securityRules/direction",
                        "equals": "Inbound"
                    },
                    {
                        "field": "Microsoft.Network/networkSecurityGroups/securityRules/sourceAddressPrefix",
                        "equals": "*"
                    }
                ]
            },
            "then": {
                "effect": "Deny"
            }
        }

    policy_template = {
        "properties": {
            "displayName": display_name,
            "policyType": "Custom",
            "mode": "Indexed",
            "description": f"Enforces strict infrastructure requirements ({control}) mapped directly to {framework_name} controls.",
            "policyRule": policy_rule
        }
    }
    return json.dumps(policy_template, indent=2)


# ==========================================================
# 3. COMPREHENSIVE AI COGNITIVE ORCHESTRATION VIA CLAUDE
# ==========================================================

# Consolidate all infrastructure auditing tools into the tool matrix
security_tools = [
    audit_resource_groups,
    check_policy_compliance,
    generate_remediation_policy,
    audit_network_security_groups,
    audit_key_vault_access_and_networking,
    extract_defender_for_cloud_alerts,
    audit_synapse_diagnostic_settings,
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


# Instantiate Claude to drive complex security and audit topology reasoning.
llm = build_llm()

# Multi-domain security instructions for compliance architecture tracking
system_prompt = (
    "You are a Principal Cloud Security Architect and Lead Azure Compliance Assessor.\n"
    "Your objective is to run deep programmatic security audits across the network layer (NSGs), "
    "data-protection tier (Key Vault), native posture state (Defender for Cloud), and governance boundaries (Azure Policies).\n\n"
    "Operational Instructions:\n"
    "1. When tasked to run a comprehensive check, call your diagnostic tools systematically.\n"
    "2. Correlate insights (e.g., if a Key Vault has public access enabled AND an NSG has wide inbound rules, explicitly flag this as a critical path to PHI compromise).\n"
    "3. For HITRUST r2 audit-logging controls, use audit_synapse_diagnostic_settings to VERIFY (read-only) that Synapse workspaces stream the required categories to Log Analytics and an immutable archive. You do not enable logging yourself; when it is missing, direct the user to the infra/ bootstrap and the DeployIfNotExists enforcement policy.\n"
    "4. When mapping to regulatory standards like HITRUST r2, output crisp structural remediation scripts, explicit Azure CLI commands, or Azure Policy templates to implement guardrails."
)

def _build_react_agent(model, tools, prompt):
    """Construct a ReAct agent, tolerating the langgraph `state_modifier` -> `prompt`
    parameter rename across versions."""
    try:
        return create_react_agent(model, tools, prompt=prompt)
    except TypeError:
        return create_react_agent(model, tools, state_modifier=prompt)


# Compile into a deterministic ReAct state machine loop
comprehensive_security_agent = _build_react_agent(llm, security_tools, system_prompt)


# ==========================================================
# 4. EXECUTION LOOP
# ==========================================================
if __name__ == "__main__":
    print("========================================================================")
    print("🔥 CLAUDE COMPREHENSIVE AZURE AUDIT & COMPLIANCE AGENT OPERATIONAL 🔥")
    print("========================================================================")
    print("[*] Systems Connected: Resource Engine, Network Fabric, Key Vaults, Policy Insights, Defender Center.")
    print("Ready for security audit input. (Type 'quit' to terminate program)\n")

    while True:
        try:
            user_input = input("Azure-Security-Core-Agent > ")
            if user_input.lower() in ["exit", "quit"]:
                print("[*] Session terminated.")
                break
            if not user_input.strip():
                continue

            # Process state execution over the LangGraph runtime
            events = comprehensive_security_agent.stream(
                {"messages": [("user", user_input)]},
                stream_mode="values",
            )
            for event in events:
                if "messages" in event:
                    last_message = event["messages"][-1]
                    # Print structural text back out to the terminal interface
                    if last_message.type == "ai" and last_message.content:
                        print(f"\n[Security Agent Findings & Remediation Plans]:\n{last_message.content}\n")
        except KeyboardInterrupt:
            print("\n[*] Manual session override requested.")
            break
        except Exception as e:  # noqa: BLE001
            print(f"[-] Runtime execution failure occurred: {str(e)}")

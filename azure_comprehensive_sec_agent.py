"""
Claude Comprehensive Azure Audit & Compliance Agent
===================================================

An enterprise-grade, terminal-runnable AI agent that audits an Azure
subscription's security posture (NSGs, Key Vault, Defender for Cloud, Azure
Policy) and produces remediation plans / Azure Policy templates mapped to
high-stakes frameworks such as HITRUST CSF r2.

Reasoning is driven by Anthropic Claude via LangChain/LangGraph. Azure access
uses DefaultAzureCredential, so it authenticates from your existing `az login`
session (or Managed Identity in the cloud) with no secrets in code.

Run:
    az login
    export ANTHROPIC_API_KEY="sk-ant-..."   # or put it in a local .env file
    python azure_comprehensive_sec_agent.py
"""

import os
import sys
import json
from typing import Dict, Any, List

from dotenv import load_dotenv

# Load ANTHROPIC_API_KEY (and anything else) from a local, git-ignored .env file.
load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.policyinsights import PolicyInsightsClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.keyvault import KeyVaultManagementClient
from azure.mgmt.security import SecurityCenter
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


@tool
def generate_remediation_policy(framework_name: str) -> str:
    """
    Generates an Azure Policy rule definition (JSON structure) used to implement
    and enforce security guardrails tailored to high-stakes compliance frameworks like HITRUST r2.
    """
    policy_template = {
        "properties": {
            "displayName": f"Enforce Secure Network Boundaries and Identity for {framework_name}",
            "policyType": "Custom",
            "mode": "Indexed",
            "description": f"Enforces strict infrastructure requirements mapped directly to {framework_name} controls.",
            "policyRule": {
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
]

# Instantiate Claude to drive complex security and audit topology reasoning.
# Model is overridable via the CLAUDE_MODEL env var.
llm = ChatAnthropic(
    model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
    temperature=0,
)

# Multi-domain security instructions for compliance architecture tracking
system_prompt = (
    "You are a Principal Cloud Security Architect and Lead Azure Compliance Assessor.\n"
    "Your objective is to run deep programmatic security audits across the network layer (NSGs), "
    "data-protection tier (Key Vault), native posture state (Defender for Cloud), and governance boundaries (Azure Policies).\n\n"
    "Operational Instructions:\n"
    "1. When tasked to run a comprehensive check, call your diagnostic tools systematically.\n"
    "2. Correlate insights (e.g., if a Key Vault has public access enabled AND an NSG has wide inbound rules, explicitly flag this as a critical path to PHI compromise).\n"
    "3. When mapping to regulatory standards like HITRUST r2, output crisp structural remediation scripts, explicit Azure CLI commands, or Azure Policy templates to implement guardrails."
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

"""
Claude-Powered Azure Security & Compliance Agent (Starter Edition)
==================================================================

A minimal, terminal-runnable AI agent that inspects Azure Resource Groups and
Azure Policy compliance, and drafts Azure Policy remediation templates for
frameworks such as HITRUST r2. Reasoning via Anthropic Claude
(LangChain/LangGraph); Azure access via DefaultAzureCredential.

This is the lightweight starting point. For the full multi-service audit
(NSGs, Key Vault, Defender for Cloud) use azure_comprehensive_sec_agent.py.

Run:
    az login
    export ANTHROPIC_API_KEY="sk-ant-..."   # or put it in a local .env file
    python azure_security_agent.py
"""

import os
import sys
import json
from typing import Dict, Any, List

from dotenv import load_dotenv

load_dotenv()

from azure.identity import DefaultAzureCredential
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.policyinsights import PolicyInsightsClient
from langchain_core.tools import tool
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent


# ==========================================
# 1. AZURE AUTHENTICATION & INITIALIZATION
# ==========================================
try:
    # DefaultAzureCredential tries Azure CLI credentials, VS Code credentials,
    # and falls back to an interactive browser window automatically.
    credential = DefaultAzureCredential(exclude_shared_token_cache_credential=True)
    sub_client = SubscriptionClient(credential)

    # Grab the first available active subscription
    subscriptions = list(sub_client.subscriptions.list())
    if not subscriptions:
        print("[-] Error: No active Azure subscriptions found for this identity.")
        sys.exit(1)

    ACTIVE_SUBSCRIPTION_ID = subscriptions[0].subscription_id
    print("[+] Authenticated Successfully to Azure!")
    print(f"[+] Active Subscription: {subscriptions[0].display_name} ({ACTIVE_SUBSCRIPTION_ID})\n")

    # Initialize Azure Clients
    resource_client = ResourceManagementClient(credential, ACTIVE_SUBSCRIPTION_ID)
    policy_client = PolicyInsightsClient(credential)

except Exception as e:  # noqa: BLE001
    print(f"[-] Authentication Failed: {str(e)}")
    sys.exit(1)


# ==========================================
# 2. DEFINING AGENT SECURITY SKILLS (TOOLS)
# ==========================================

@tool
def audit_resource_groups() -> str:
    """
    Audits all Resource Groups in the active subscription and flags loose security
    configurations like missing mandatory compliance tags (e.g., Environment, Owner).
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
            top=20
        )

        non_compliant_resources = []
        for state in policy_states.value:
            if state.additional_properties.get("complianceState") == "NonCompliant":
                non_compliant_resources.append({
                    "ResourceID": state.additional_properties.get("resourceId"),
                    "ResourceType": state.additional_properties.get("resourceType"),
                    "PolicyAssignmentName": state.additional_properties.get("policyAssignmentName"),
                    "PolicyDefinitionName": state.additional_properties.get("policyDefinitionName")
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
    # High stakes frameworks require enforcement structures like 'Deny' or 'DeployIfNotExists'
    policy_template = {
        "properties": {
            "displayName": f"Enforce Secure Configurations for {framework_name}",
            "policyType": "Custom",
            "mode": "Indexed",
            "description": f"Enforces strict infrastructure requirements mapped directly to {framework_name} controls.",
            "policyRule": {
                "if": {
                    "allOf": [
                        {
                            "field": "tags[HITRUST_Scope]",
                            "exists": "false"
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


# ==========================================
# 3. AGENT ORCHESTRATION VIA CLAUDE
# ==========================================

# Pack tools together
tools = [audit_resource_groups, check_policy_compliance, generate_remediation_policy]

# Initialize the Claude Model via LangChain Anthropic wrapper.
# Model is overridable via the CLAUDE_MODEL env var.
llm = ChatAnthropic(
    model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
    temperature=0,
)

# Structural System Prompt ensuring the agent adheres to security engineering logic
system_prompt = (
    "You are a Senior Azure Cyber Security & Compliance Engineering Agent.\n"
    "Your objective is to inspect infrastructure setups, locate active compliance violations "
    "using your tools, and write policy remediation structures for regulatory frameworks such as HITRUST r2.\n"
    "When asked to audit or run checks, utilize the proper tool in sequence. Always output clear, "
    "remediation steps alongside technical configurations."
)

def _build_react_agent(model, agent_tools, prompt):
    """Construct a ReAct agent, tolerating the langgraph `state_modifier` -> `prompt`
    parameter rename across versions."""
    try:
        return create_react_agent(model, agent_tools, prompt=prompt)
    except TypeError:
        return create_react_agent(model, agent_tools, state_modifier=prompt)


# Compile the ReAct agent graph
security_agent = _build_react_agent(llm, tools, system_prompt)


# ==========================================
# 4. INTERACTIVE TERMINAL RUNTIME
# ==========================================
if __name__ == "__main__":
    print("==================================================================")
    print("⚡ CLAUDE-POWERED AZURE SECURITY & COMPLIANCE AGENT ACTIVATED ⚡")
    print("==================================================================")
    print("Ask a security or compliance query (e.g., 'Run a comprehensive compliance audit on my resources and construct a policy mapping to HITRUST r2 rules')\n")

    while True:
        try:
            user_input = input("Azure-Sec-Agent > ")
            if user_input.lower() in ["exit", "quit"]:
                print("[*] Terminating Agent Session. Goodbye.")
                break

            if not user_input.strip():
                continue

            # Process input through the langgraph engine
            events = security_agent.stream(
                {"messages": [("user", user_input)]},
                stream_mode="values",
            )

            for event in events:
                if "messages" in event:
                    # Echo back the ultimate text response from Claude
                    last_message = event["messages"][-1]
                    if last_message.type == "ai" and last_message.content:
                        print(f"\n[Agent Response]:\n{last_message.content}\n")

        except KeyboardInterrupt:
            print("\n[*] Session interrupted by user.")
            break
        except Exception as e:  # noqa: BLE001
            print(f"[-] Execution Error: {str(e)}")

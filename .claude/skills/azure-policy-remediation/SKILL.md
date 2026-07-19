---
name: azure-policy-remediation
description: Generate a ready-to-apply Azure Policy definition (JSON) for a compliance guardrail — deny open-ingress NSG rules (network_boundary) or deny resources missing the HITRUST_Scope tag (required_tags). Use when asked to generate/create an Azure Policy for a framework like HITRUST r2.
---

# Azure Policy Remediation Generator

Ask which `control` and which `framework` (default: "HITRUST r2") if unspecified, then emit the full
policy JSON and the apply commands.

## control = network_boundary (default)
Deny NSG rules allowing inbound from any source.
```json
{
  "properties": {
    "displayName": "Enforce Secure Network Boundaries and Identity for <FRAMEWORK>",
    "policyType": "Custom",
    "mode": "Indexed",
    "description": "Enforces strict infrastructure requirements (network_boundary) mapped to <FRAMEWORK> controls.",
    "policyRule": {
      "if": {
        "allOf": [
          { "field": "type", "equals": "Microsoft.Network/networkSecurityGroups" },
          { "field": "Microsoft.Network/networkSecurityGroups/securityRules/access", "equals": "Allow" },
          { "field": "Microsoft.Network/networkSecurityGroups/securityRules/direction", "equals": "Inbound" },
          { "field": "Microsoft.Network/networkSecurityGroups/securityRules/sourceAddressPrefix", "equals": "*" }
        ]
      },
      "then": { "effect": "Deny" }
    }
  }
}
```

## control = required_tags
Deny resources missing the `HITRUST_Scope` governance tag.
```json
{
  "properties": {
    "displayName": "Enforce required HITRUST_Scope tag for <FRAMEWORK>",
    "policyType": "Custom",
    "mode": "Indexed",
    "description": "Enforces strict infrastructure requirements (required_tags) mapped to <FRAMEWORK> controls.",
    "policyRule": {
      "if": { "allOf": [ { "field": "tags['HITRUST_Scope']", "exists": "false" } ] },
      "then": { "effect": "Deny" }
    }
  }
}
```

## Apply (the user runs these)
```bash
az policy definition create --name <name> --rules "@policy.json" --mode Indexed
az policy assignment create --name <assign> --policy <name> --scope /subscriptions/<sub-id>
```
Do not assign or delete policy automatically — output the commands for the user. For the Synapse
diagnostic-logging DeployIfNotExists policy, use `infra/policy/` instead of generating a new one.

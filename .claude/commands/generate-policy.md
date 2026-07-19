---
description: Generate an Azure Policy remediation definition (network boundary or required tags) for a framework
---

Use the `azure-policy-remediation` skill to generate a ready-to-apply Azure Policy JSON definition
for the requested guardrail:

- `network_boundary` (default) — deny NSG rules allowing inbound from any source (`*`).
- `required_tags` — deny resources missing the `HITRUST_Scope` governance tag.

Ask which control and which framework (default: HITRUST r2) if not specified. Output the full policy
JSON and the `az policy definition create` / `az policy assignment create` commands to apply it.
Do not assign or delete any policy automatically — leave that to the user.

$ARGUMENTS

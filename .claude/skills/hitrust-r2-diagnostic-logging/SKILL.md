---
name: hitrust-r2-diagnostic-logging
description: Verify (read-only) and guide setup of HITRUST CSF r2 Synapse diagnostic logging — required log categories, dual-destination retention (Log Analytics 365d + immutable WORM archive), and the DeployIfNotExists enforcement policy. Use for HITRUST/r2/audit-logging/retention questions about Azure Synapse.
---

# HITRUST r2 — Synapse Diagnostic Logging

Full framework: `docs/hitrust_r2_retention_framework.md`. Setup assets: `infra/`.

## Required log categories
Every Synapse workspace must stream these to Log Analytics (and ideally an immutable archive):
- `IntegrationPipelineRuns` — ETL execution states
- `IntegrationActivityRuns` — individual copy/transform steps (rows/bytes moved)
- `SynapseRbacOperations` — role-based access changes

## Verify (read-only)
```bash
az synapse workspace list -o json
# per workspace:
az monitor diagnostic-settings list --resource <synapse-workspace-id> -o json
```
For each workspace confirm: the 3 categories are `enabled`; a `workspaceId` (Log Analytics) is set;
and a `storageAccountId` (immutable archive) is set. Report PASS/FAIL with exact gaps.

Retention & immutability:
```bash
az monitor log-analytics workspace show -g <rg> -n <la> --query retentionInDays -o tsv   # >= 365
az storage account show -n <sa> -g <rg> --query immutableStorageWithVersioning -o json    # enabled
```

## Establish (baseline — the user runs it)
- Bicep: `az deployment group create -g <rg> -f infra/bicep/main.bicep -p synapseWorkspaceName=<n> logAnalyticsWorkspaceName=<la> storageAccountName=<sa>`
- CLI: `infra/cli/setup_diagnostics.sh -g <rg> -s <synapse> -l <la> -a <storage>`

## Enforce (continuous — the user runs it)
`infra/policy/assign_policy.sh -w "<log-analytics-resource-id>"` assigns a DeployIfNotExists policy
so any Synapse workspace missing the setting is auto-remediated (closes the timing gap).

## PRISMA maturity (all three scored)
Policy (documented logging + retention policy) · Procedure (SOP + which KQL queries, see `kql/`) ·
Implementation (90+ days of history + signed-off weekly reviews).

Never delete or overwrite an existing diagnostic setting — provide the command for the user.

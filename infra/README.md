# infra/ — Synapse Diagnostic Logging (HITRUST r2)

This directory implements the **"always-on baseline + continuous enforcement"** model for the
Synapse audit-logging control. The agent stays **read-only** and only *verifies* this is in place
(`audit_synapse_diagnostic_settings`); it never enables logging itself.

Why this split? Diagnostic logging only captures events from the moment it's on. If you waited for
an agent to notice it's missing and switch it on, every event before that is gone — and an r2
auditor wants 90+ days of history. So logging must be established **before** and kept on
**continuously**, independent of the agent.

```
  ┌──────────────────────┐   verifies (read-only)   ┌──────────────────────────┐
  │  Compliance Agent    │ ───────────────────────► │  Synapse Diagnostic       │
  │  audit_synapse_...    │                          │  Setting (the control)    │
  └──────────────────────┘                          └────────────┬─────────────┘
                                                                  ▲ deploys / self-heals
  establishes once                                                │
  ┌──────────────────────┐        ┌──────────────────────────────┴─────────────┐
  │  bicep/ or cli/       │        │  policy/  DeployIfNotExists (continuous)     │
  │  (baseline bootstrap) │        │  auto-applies to any workspace that drifts   │
  └──────────────────────┘        └──────────────────────────────────────────────┘
```

## 1. Baseline bootstrap — run once per Synapse workspace

Creates the Log Analytics workspace (365-day retention), the immutable WORM storage archive, and
the diagnostic setting streaming the three HITRUST categories to both.

**Bicep:**
```bash
az login
az deployment group create \
  --resource-group <rg-with-synapse> \
  --template-file bicep/main.bicep \
  --parameters synapseWorkspaceName=<name> \
               logAnalyticsWorkspaceName=<la-name> \
               storageAccountName=<globally-unique-lowercase>
```

**Azure CLI (equivalent):**
```bash
az login
chmod +x cli/setup_diagnostics.sh
./cli/setup_diagnostics.sh -g <rg> -s <synapse-ws> -l <la-name> -a <storage-name>
```

## 2. Continuous enforcement — assign the policy once per subscription

`policy/synapse-diagnostics-deployIfNotExists.json` is a custom **DeployIfNotExists** policy. Once
assigned, Azure guarantees every existing and future Synapse workspace has the diagnostic setting —
auto-deploying it (and self-healing drift) with no agent in the loop and no write credentials given
to an LLM.

```bash
az login
chmod +x policy/assign_policy.sh
./policy/assign_policy.sh -w "<log-analytics-workspace-resource-id>"
```

The script creates the definition, assigns it with a managed identity, grants that identity
**Monitoring Contributor** + **Log Analytics Contributor** (required by DeployIfNotExists), and
triggers a remediation task to fix workspaces that are already non-compliant.

## 3. Verify from the agent

```
Azure-Security-Core-Agent > Verify that all my Synapse workspaces have HITRUST r2 diagnostic logging configured.
```
The agent calls `audit_synapse_diagnostic_settings` and reports PASS/FAIL per workspace — including
whether logs reach both Log Analytics and the immutable archive.

## Notes & production hardening
- **Lock the archive before an audit:** the storage immutability starts `Unlocked` (extendable).
  Switch to `Locked` to make the retention window irrevocable:
  `az storage account update -n <sa> -g <rg> --immutability-state Locked`.
- **Durability:** the templates use `Standard_LRS`. Consider `Standard_GRS`/`RA-GRS` for production.
- **Storage archiving** via diagnostic settings is the method the source doc specifies. For very
  high volume, Log Analytics data export or Event Hub are alternatives.
- The DINE policy targets **Log Analytics**; the immutable-archive destination is established by the
  bootstrap. Extend the policy's embedded ARM template with `storageAccountId` if you want the
  policy to enforce the archive sink too.

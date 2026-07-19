---
description: Run a full read-only Azure security & compliance audit (NSGs, Key Vault, Defender, tags, Policy, Synapse logging)
---

Use the `security-auditor` sub-agent to run a comprehensive, **read-only** security and compliance
audit of the currently signed-in Azure subscription. Cover:

- **Network** — NSG inbound rules open to any source (`*` / `0.0.0.0/0`); highlight dangerous ports (22, 3389, 1433, 3306, 5432).
- **Secrets** — Key Vaults exposed to the public internet (`publicNetworkAccess` / `networkAcls.defaultAction`).
- **Threats** — active Microsoft Defender for Cloud alerts.
- **Governance** — Resource Groups missing `Environment` / `Owner` / `HITRUST_Scope` tags.
- **Policy** — non-compliant resources from Azure Policy.
- **Audit logging** — Synapse workspaces missing HITRUST r2 diagnostic categories.

Correlate cross-service risk, map findings to HITRUST r2 domains, and output ready-to-run `az`
remediation commands or an Azure Policy JSON (via the `azure-policy-remediation` skill). Save the
report to `reports/output/security-audit-<date>.md`.

Confirm the target subscription with `az account show` first. Do not modify or delete anything.

$ARGUMENTS

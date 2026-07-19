---
description: Verify HITRUST r2 Synapse diagnostic logging, retention, and PRISMA maturity posture
---

Use the `hitrust-compliance` sub-agent to verify (read-only) HITRUST CSF r2 audit-logging controls
for every Azure Synapse workspace:

- Required diagnostic categories enabled: `IntegrationPipelineRuns`, `IntegrationActivityRuns`, `SynapseRbacOperations`
- Dual destination: Log Analytics (>= 365-day retention) **and** an immutable WORM storage archive
- PRISMA maturity reminder (Policy + Procedure + Implementation)

Report PASS/FAIL per workspace with the exact missing categories/destinations. If anything is
missing, point to `infra/` (bootstrap) and `infra/policy/assign_policy.sh` (DeployIfNotExists) with
the exact commands to run — do not change anything yourself.

$ARGUMENTS

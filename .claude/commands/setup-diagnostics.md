---
description: Guide establishing + enforcing Synapse HITRUST r2 diagnostic logging via infra/ (Bicep/CLI + DeployIfNotExists)
---

Use the `hitrust-compliance` sub-agent to guide the user through establishing and enforcing Synapse
diagnostic logging using this repo's `infra/`:

1. **Baseline** (once per workspace) — walk through `infra/bicep/main.bicep` (or
   `infra/cli/setup_diagnostics.sh`): Log Analytics (365d) + immutable WORM archive + diagnostic
   setting streaming the three required categories.
2. **Enforcement** (once per subscription) — `infra/policy/assign_policy.sh` assigns the
   DeployIfNotExists policy so any Synapse workspace lacking the setting is auto-remediated.
3. **Verify** — re-run the `check-hitrust` verification.

Produce the exact parameterized commands for the user's environment (ask for resource group,
Synapse workspace name, and desired Log Analytics / storage names). Explain the `Unlocked` →
`Locked` immutability step before an audit. Do not run destructive commands; the user applies infra.

$ARGUMENTS

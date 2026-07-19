# Azure Agents — Claude Code Multi-Agent System

This repo is a **Claude Code** workspace for Azure security/compliance auditing and data-platform
architecture. It runs **keyless**: Claude is provided by the Claude Code runtime (authenticated by
your Claude subscription), and Azure access comes from your `az login` session. **No
`ANTHROPIC_API_KEY` is required for the Claude Code mode.**

> There is also a legacy **standalone Python mode** (`azure_security_agent.py`,
> `data_architect_agent.py`) that calls the Anthropic API directly and *does* need
> `ANTHROPIC_API_KEY`. Prefer the Claude Code mode below.

## How Azure access works (keyless)

- **Claude** → Claude Code runtime (your Pro/Max subscription login). No key in the repo.
- **Azure** → the `az` CLI. Run `az login` once; agents call `az ... -o json` via Bash.
- **Safety** → `.claude/hooks/pre-tool-safety.mjs` blocks destructive commands (resource deletes,
  removing diagnostic settings/policies, `rm -rf`, `DROP`/`TRUNCATE`). Agents audit and design only.

Always confirm the target subscription first: `az account show -o json`.

## Agent streams (`.claude/agents/`)

- **security-auditor** (`/audit-security`) — read-only posture audit: NSGs, Key Vault exposure,
  Defender for Cloud alerts, RG tags, Azure Policy compliance, Synapse diagnostic logging; maps to
  HITRUST r2 and emits remediation `az`/Policy JSON.
- **data-architect** (`/design-data`) — discovers the data estate, then designs medallion
  lakehouses, Kimball star schemas + Synapse DDL, and ingestion pipelines; security + observability
  folded in.
- **hitrust-compliance** (`/check-hitrust`, `/setup-diagnostics`) — verifies Synapse diagnostic
  logging + retention + PRISMA maturity; guides `infra/` bootstrap and the DeployIfNotExists policy.

## Slash commands (`.claude/commands/`)

`/audit-security` · `/design-data` · `/check-hitrust` · `/setup-diagnostics` · `/generate-policy`

## Skills (`.claude/skills/`) — auto-discovered

`azure-security-audit` · `hitrust-r2-diagnostic-logging` · `azure-policy-remediation` ·
`medallion-lakehouse-design` · `dimensional-model-synapse` · `ingestion-pipeline-design`

## Repo assets the agents rely on

- `docs/hitrust_r2_retention_framework.md` — HITRUST r2 framework + retention model.
- `kql/*.kql` — Log Analytics queries (egress anomalies, unauthorized pipeline changes).
- `infra/` — Bicep + CLI bootstrap and the DeployIfNotExists policy for Synapse diagnostic logging.

## Rules for agents

- **Read-only by default.** Never delete or reconfigure Azure resources. Output exact `az`/Bicep
  commands for the human to run deliberately (the safety hook will block destructive calls anyway).
- Confirm subscription scope before auditing; the agents only see what the signed-in identity can.
- Save substantial outputs to `reports/output/` (git-ignored).

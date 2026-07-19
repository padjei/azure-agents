# Claude-Powered Azure Agents

AI agents for Azure **security/compliance auditing** and **data-platform architecture**, covering
NSGs, Key Vault, Defender for Cloud, Azure Policy, and HITRUST CSF r2 Synapse logging on the security
side, and medallion lakehouses, Kimball dimensional models + Synapse DDL, and ingestion pipelines on
the data side.

There are **two ways to run**, sharing the same knowledge, docs, `kql/`, and `infra/`:

| Mode | Claude auth | How Azure is reached | When |
| ---- | ----------- | -------------------- | ---- |
| **① Claude Code (recommended, keyless)** | Your **Claude subscription** (no `ANTHROPIC_API_KEY`) | `az` CLI via Bash | Open the repo in Claude Code; use slash commands / agents |
| **② Standalone Python (keyless)** | Your **Claude subscription** via OAuth (`ant auth login`); `ANTHROPIC_API_KEY` optional | Azure SDK + `DefaultAzureCredential` | Run the `*.py` agents directly / in Docker |

> **New here?** See **[docs/USAGE.md](docs/USAGE.md)** for both modes step by step.

## What's inside

| Path | Purpose |
| ---- | ------- |
| `.claude/` | **Claude Code setup (keyless mode).** `agents/` (security-auditor, data-architect, hitrust-compliance), `commands/` (slash commands), `skills/` (Azure knowledge), `hooks/` (safety + session log), `settings.json`. |
| `CLAUDE.md` | Project context Claude Code loads automatically. |
| `azure_security_agent.py` | **Python security agent.** Audits NSGs, Key Vault, Defender, RGs, Azure Policy, Synapse logging; generates remediation policy JSON. |
| `data_architect_agent.py` | **Python data architect agent.** Discovers the estate; designs lakehouses, star schemas + DDL, pipelines. |
| `requirements.txt` | Pinned Python dependencies (mode ② only). |
| `Dockerfile` / `docker-compose.yml` | Containerized runtime for mode ② — run with only Docker. |
| `docs/USAGE.md` | Step-by-step usage for both modes + a pre-deployment checklist. |
| `docs/hitrust_r2_retention_framework.md` | HITRUST r2 Synapse hardening, retention, and PRISMA maturity guidance. |
| `kql/*.kql` | Log Analytics audit queries for Synapse ETL egress and pipeline tampering. |
| `infra/` | Bicep + CLI bootstrap and a DeployIfNotExists policy that establish and enforce Synapse diagnostic logging (see `infra/README.md`). |
| `.env.example` | Template for your local `.env` (never commit the real `.env`). |

## Security agent tools (skills)

- `audit_network_security_groups` — flags overly permissive inbound NSG rules (Any-source Allow).
- `audit_key_vault_access_and_networking` — flags Key Vaults exposed to the public internet.
- `extract_defender_for_cloud_alerts` — pulls active Microsoft Defender for Cloud alerts.
- `audit_resource_groups` — flags missing compliance tags (`Environment`, `HITRUST`).
- `check_policy_compliance` — lists non-compliant resources from Azure Policy Insights.
- `audit_synapse_diagnostic_settings` — **read-only** check that every Synapse workspace streams the required HITRUST r2 audit categories to Log Analytics + an immutable archive.
- `generate_remediation_policy` — emits an Azure Policy JSON definition for a named framework.

## Data Architect agent tools (skills)

Discovery (read-only):
- `discover_data_estate` — inventories data-platform resources (Synapse, SQL, Data Factory, Storage/Data Lake, Cosmos, Event Hubs, Databricks, Purview…).
- `inspect_data_lake_storage` — assesses Storage accounts for lakehouse suitability (ADLS Gen2 / redundancy / encryption / public access).
- `inspect_sql_estate` — inventories Azure SQL servers/databases and tiers.

Design (generative):
- `design_medallion_lakehouse` — Bronze/Silver/Gold layout on ADLS Gen2 + Delta, with governance & security.
- `design_dimensional_model` — Kimball star schema + Synapse-optimized T-SQL DDL (distribution + columnstore).
- `design_ingestion_pipeline` — ETL/ELT blueprint (service choice, incremental strategy, reliability, security, observability).

## Diagnostic logging (HITRUST r2)

Audit logging is a *control*, not a one-off fix — it only captures events once it's on, so it must
be established up front and kept on continuously. This repo follows a **read-only agent + Azure
Policy enforcement** model:

- **Establish + enforce** (not the agent): `infra/bicep` or `infra/cli` stands up the baseline
  (Log Analytics 365d + immutable WORM archive + diagnostic setting); `infra/policy` assigns a
  `DeployIfNotExists` policy so any workspace that lacks it is auto-remediated.
- **Verify** (the agent): `audit_synapse_diagnostic_settings` reports per-workspace whether logging
  is correctly configured — it never enables anything itself.

See [`infra/README.md`](infra/README.md) for the full runbook.

---

## ① Run keyless with Claude Code (recommended)

No API key, no Python, no Docker. Claude comes from your Claude subscription; Azure comes from `az`.

```bash
# 1. Sign in to Azure (the agents reuse this session)
az login

# 2. Open this repo in Claude Code (CLI shown; the IDE extensions work too)
cd azure-agents
claude
```

Then drive it with slash commands (or just ask in natural language):

```
/audit-security                 # full read-only security & compliance audit
/check-hitrust                  # verify Synapse HITRUST r2 diagnostic logging
/design-data design a medallion lakehouse for the claims domain
/generate-policy network_boundary for HITRUST r2
/setup-diagnostics              # guided infra/ bootstrap + enforcement policy
```

Claude Code auto-loads `CLAUDE.md`, the three sub-agents in `.claude/agents/`, the six skills in
`.claude/skills/`, and a **safety hook** that blocks destructive Azure commands (resource deletes,
removing diagnostic settings/policies, `rm -rf`). The agents are **read-only** — they audit and
design, and hand you exact `az`/Bicep commands to run yourself.

> Requires the Claude Code CLI (`npm i -g @anthropic-ai/claude-code`) or an IDE extension, signed in
> with your Claude account. This mode needs **no `ANTHROPIC_API_KEY`**.

---

## ② Run as standalone Python (keyless — your Claude subscription)

Claude is reached through your **Claude subscription** via OAuth — no API key. Sign in once with
the `ant` CLI ([install](https://platform.claude.com/docs/en/api/sdks/cli)); the agents mint a
short-lived token from that profile automatically. An `ANTHROPIC_API_KEY` still works if set — it
overrides the subscription.

**Local Python** (requires **Python 3.11 or 3.12** — the pinned dependencies predate Python 3.14):

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

az login          # Azure access (DefaultAzureCredential reuses this session)
ant auth login    # Claude access via your Claude subscription (OAuth)

python azure_security_agent.py     # security & compliance agent
python data_architect_agent.py     # data architect agent
```

**Docker** (only **Docker Desktop** + **Azure CLI** + `ant` on the host — no local Python). The
container has no `ant` CLI, so pass a host-minted OAuth token in via the environment:

```bash
az login
eval "$(ant auth print-credentials --env)"   # exports ANTHROPIC_AUTH_TOKEN for compose
#   (or instead put ANTHROPIC_API_KEY=sk-ant-... in a local .env — cp .env.example .env)

docker compose run --rm agent            # security & compliance agent
docker compose run --rm data-architect   # data architect agent
```

`--rm` auto-removes the container on exit. The compose file mounts `~/.azure` into the container
so `DefaultAzureCredential` reuses your host `az login` — no second login inside Docker.

## Example prompts

**Security agent:**
```
Run a full scan on my network layers and secrets storage. Are there any vectors
exposed that breach HITRUST compliance?

Check Microsoft Defender for Cloud alerts and generate an Azure Policy that
permanently denies any wide internet-to-internal data tier routing.
```

**Data Architect agent:**
```
Assess my current data estate and recommend a medallion lakehouse design for the
claims domain.

Design a star schema for retail sales at order-line grain, then blueprint a
batch ingestion pipeline from on-prem SQL Server into a Synapse dedicated SQL pool.
```

Type `quit` or `exit` to end the session.

## Choosing the Claude model

- **Claude Code mode ①:** set in `.claude/settings.json` (`"model": "claude-opus-4-8"`).
- **Python mode ②:** defaults to `claude-sonnet-4-6`; override via the `CLAUDE_MODEL` env var
  (e.g. `CLAUDE_MODEL=claude-opus-4-8`).

## Security notes

- **Both modes are keyless by default** — Claude comes from your subscription (mode ① via Claude
  Code, mode ② via `ant auth login` OAuth) and Azure from `az login`, so no secrets are stored. A
  safety hook (`.claude/hooks/pre-tool-safety.mjs`) blocks destructive Azure/filesystem commands.
- If you opt into an `ANTHROPIC_API_KEY` (mode ②), keep it in `.env`, which is git-ignored — it
  never reaches GitHub (commit only `.env.example`). OAuth tokens are short-lived and never stored.
- The agents perform **read-only** discovery/audits; they draft policy JSON and design artifacts but do not change your Azure resources.
- Azure permissions come from your signed-in identity; the agents can only see what you can.

## Deploy to GitHub

Once you've verified both agents locally (see [docs/USAGE.md](docs/USAGE.md)), publish so you can
clone and run from any laptop. A **private** repo is recommended since the agents inspect your cloud.

```bash
# from the azure-agents/ directory
git status                      # confirm .env is NOT listed
git remote add origin https://github.com/<you>/azure-agents.git
git branch -M main
git push -u origin main
```

On a fresh laptop later:
```bash
git clone https://github.com/<you>/azure-agents.git
cd azure-agents
cp .env.example .env            # add your ANTHROPIC_API_KEY
az login
docker compose run --rm agent           # or: data-architect
```

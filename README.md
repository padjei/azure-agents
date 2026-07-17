# Azure Security & Compliance Agent (Claude-powered)

A terminal-runnable AI agent that audits an Azure subscription's security posture and produces
remediation plans / Azure Policy templates mapped to high-stakes frameworks such as **HITRUST CSF r2**.

Reasoning is driven by **Anthropic Claude** via **LangChain / LangGraph**. Azure access uses
`DefaultAzureCredential`, so the agent authenticates from your existing `az login` session — **no
secrets are stored in code**.

## What's inside

| File | Purpose |
| ---- | ------- |
| `azure_security_agent.py` | **The agent.** Audits NSGs, Key Vault, Defender for Cloud, Resource Groups, Azure Policy, and Synapse diagnostic logging; generates remediation policy JSON. |
| `requirements.txt` | Pinned Python dependencies. |
| `Dockerfile` / `docker-compose.yml` | Containerized runtime — run on any laptop with only Docker. |
| `docs/hitrust_r2_retention_framework.md` | HITRUST r2 Synapse hardening, retention, and PRISMA maturity guidance. |
| `kql/*.kql` | Log Analytics audit queries for Synapse ETL egress and pipeline tampering. |
| `infra/` | Bicep + CLI bootstrap and a DeployIfNotExists policy that establish and enforce Synapse diagnostic logging (see `infra/README.md`). |
| `.env.example` | Template for your local `.env` (never commit the real `.env`). |

## The agent's tools (skills)

- `audit_network_security_groups` — flags overly permissive inbound NSG rules (Any-source Allow).
- `audit_key_vault_access_and_networking` — flags Key Vaults exposed to the public internet.
- `extract_defender_for_cloud_alerts` — pulls active Microsoft Defender for Cloud alerts.
- `audit_resource_groups` — flags missing compliance tags (`Environment`, `HITRUST`).
- `check_policy_compliance` — lists non-compliant resources from Azure Policy Insights.
- `audit_synapse_diagnostic_settings` — **read-only** check that every Synapse workspace streams the required HITRUST r2 audit categories to Log Analytics + an immutable archive.
- `generate_remediation_policy` — emits an Azure Policy JSON definition for a named framework.

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

## Quick start (Docker — recommended)

You only need **Docker Desktop** and the **Azure CLI** installed. No local Python required.

```bash
# 1. Authenticate to Azure on your host machine
az login

# 2. Put your Anthropic key in a local .env file
cp .env.example .env
#   then edit .env and set ANTHROPIC_API_KEY=sk-ant-...

# 3. Build + launch the interactive agent (compose reads ANTHROPIC_API_KEY from .env)
docker compose run --rm agent
```

`--rm` auto-removes the container on exit. The compose file mounts `~/.azure` into the container
so `DefaultAzureCredential` reuses your host `az login` — no second login inside Docker.

## Quick start (local Python)

> Requires **Python 3.11 or 3.12** (the pinned dependencies predate Python 3.14).

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

export ANTHROPIC_API_KEY="sk-ant-..."   # or use the .env file
az login

python azure_security_agent.py
```

## Example prompts

```
Run a full scan on my network layers and secrets storage. Are there any vectors
exposed that breach HITRUST compliance?

Check Microsoft Defender for Cloud alerts and generate an Azure Policy that
permanently denies any wide internet-to-internal data tier routing.
```

Type `quit` or `exit` to end the session.

## Choosing the Claude model

Defaults to `claude-sonnet-4-6`. Override without editing code via the `CLAUDE_MODEL` env var
(e.g. `CLAUDE_MODEL=claude-opus-4-8` for deeper reasoning).

## Security notes

- `.env` is git-ignored — your API key never reaches GitHub. Commit only `.env.example`.
- The agent performs **read-only audits**; it drafts policy JSON but does not apply changes.
- Azure permissions come from your signed-in identity; the agent can only see what you can.

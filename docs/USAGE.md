# Using the agents (and how to try them before deploying)

This walks you through running both agents **locally on your laptop first**, confirming they work
against your Azure subscription, and only then pushing to GitHub. Do this on the machine you built
them on before you rely on cloning to a fresh laptop.

---

## 0. Prerequisites

| Need | Why | Check |
| ---- | --- | ----- |
| **Docker Desktop** | Runs the agents without installing Python locally | `docker version` |
| **Azure CLI** | Provides the login the agents reuse | `az version` |
| **Anthropic API key** | Powers Claude reasoning | starts with `sk-ant-` |
| **Azure permissions** | The agents only see what your identity can | at least **Reader** on the subscription; **Contributor** to deploy `infra/` |

> The agents authenticate to Azure via `DefaultAzureCredential`, which reuses your `az login`
> session. They never store Azure secrets. The only secret is your Anthropic key, kept in a local,
> git-ignored `.env`.

---

## 1. One-time setup

```bash
cd azure-agents

# Anthropic key -> local .env (git-ignored; never committed)
cp .env.example .env
#   edit .env and set: ANTHROPIC_API_KEY=sk-ant-...

# Sign in to Azure (opens a browser)
az login

# Confirm which subscription you're pointed at — the agents use the FIRST one returned
az account show --output table
```

If you have multiple subscriptions and want a specific one:
```bash
az account set --subscription "<subscription-name-or-id>"
```

---

## 2. Build once, confirm it starts

```bash
docker compose build          # builds the shared azure-agents image
```

A successful build means every dependency resolved. If you don't have Docker, use the
[local Python path](../README.md#quick-start-local-python) instead (Python 3.11/3.12).

---

## 3. Run the Security & Compliance agent

```bash
docker compose run --rm agent
```

You'll get an interactive prompt. Try, one line at a time:

```
Azure-Security-Core-Agent > Audit my resource groups for compliance tags.
Azure-Security-Core-Agent > Run a full scan on my network layers and secrets storage. What breaches HITRUST?
Azure-Security-Core-Agent > Verify that all my Synapse workspaces have HITRUST r2 diagnostic logging.
Azure-Security-Core-Agent > Generate an Azure Policy that denies NSG rules open to the internet.
Azure-Security-Core-Agent > quit
```

What to expect: Claude calls the relevant read-only tools, correlates findings, and prints a
findings/remediation block. It **audits and drafts** — it does not change your Azure resources.

---

## 4. Run the Data Architect agent

```bash
docker compose run --rm data-architect
```

```
Azure-Data-Architect > Assess my current data estate and highlight gaps.
Azure-Data-Architect > Recommend a medallion lakehouse design for the claims domain, sources Guidewire and Salesforce.
Azure-Data-Architect > Design a star schema for retail sales at order-line grain with measures quantity, unit_price, discount.
Azure-Data-Architect > Blueprint a streaming ingestion pipeline from Event Hub into a Gold Delta table.
Azure-Data-Architect > quit
```

What to expect: it inventories your data services first (discovery tools), then emits concrete
artifacts — lakehouse zone layouts, a Kimball star schema with Synapse-optimized DDL, and pipeline
blueprints — always folding in security and observability.

---

## 5. Switching the Claude model (optional)

Both agents default to `claude-sonnet-4-6`. For deeper reasoning on complex designs/audits:

```bash
# in .env
CLAUDE_MODEL=claude-opus-4-8
```

---

## 6. Pre-deployment checklist

Before you push to GitHub, confirm:

- [ ] `docker compose build` succeeds
- [ ] `docker compose run --rm agent` starts, answers a prompt, and exits on `quit`
- [ ] `docker compose run --rm data-architect` does the same
- [ ] `git status` shows **no `.env`** staged (run `git check-ignore .env` → should print `.env`)
- [ ] `.env.example` is committed but contains only placeholders
- [ ] You're comfortable the read-only tools returned data (i.e. your `az login` scope is correct)

Then follow **Deploy to GitHub** in the [README](../README.md#deploy-to-github).

---

## Troubleshooting

| Symptom | Likely cause / fix |
| ------- | ------------------ |
| `No active Azure subscriptions found` | Not logged in — run `az login`; check `az account show`. |
| `Authentication ... Failed` on Azure | Token expired or wrong tenant — `az login --tenant <tenant-id>`. |
| Empty audit results | Your identity lacks read access to those resources — grant Reader on the subscription. |
| Anthropic 401 / auth error | `ANTHROPIC_API_KEY` missing or wrong in `.env`. |
| Docker can't read `~/.azure` | Ensure you ran `az login` on the **host**; the compose file mounts `~/.azure` read-through. |
| Local `pip install` fails on Python 3.14 | Use Python 3.11/3.12, or just use Docker. |

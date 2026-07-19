# Using the agents

There are two ways to run this repo. **Mode ① (Claude Code) is keyless and recommended.** Mode ②
(standalone Python) is the original API-key path, kept as an alternative.

---

## Mode ① — Claude Code (keyless, recommended)

Claude comes from your **Claude subscription** (via the Claude Code runtime) — **no
`ANTHROPIC_API_KEY`**. Azure comes from your **`az login`** session. Nothing to build.

### Prerequisites
| Need | Why | Check |
| ---- | --- | ----- |
| **Claude Code** | The runtime that *is* Claude here | `claude --version` (install: `npm i -g @anthropic-ai/claude-code`) — or a Claude Code IDE extension |
| **Signed-in Claude account** | Provides Claude, keyless | Claude Code prompts you to log in on first run |
| **Azure CLI** | Azure access the agents reuse | `az version` |
| **Node.js** | Runs the safety/session hooks | `node --version` |
| **Azure permissions** | Agents see only what you can | Reader on the subscription; Contributor to apply `infra/` |

### Run it
```bash
az login                     # sign in to Azure
cd azure-agents
claude                       # opens Claude Code in this repo
```

Then use slash commands (or plain English):

```
/audit-security                                   # full read-only security & compliance audit
/check-hitrust                                    # verify Synapse HITRUST r2 diagnostic logging
/design-data design a star schema for retail sales at order-line grain
/generate-policy required_tags for HITRUST r2     # emit an Azure Policy JSON
/setup-diagnostics                                # guided infra/ bootstrap + enforcement policy
```

Or spawn a sub-agent directly, e.g. *"Use the data-architect agent to assess my data estate and
recommend a lakehouse."*

### What loads automatically
- `CLAUDE.md` — project context
- `.claude/agents/` — `security-auditor`, `data-architect`, `hitrust-compliance`
- `.claude/skills/` — 6 Azure knowledge skills (auto-discovered)
- `.claude/hooks/pre-tool-safety.mjs` — **blocks destructive commands** (resource deletes, removing
  diagnostic settings/policies, `rm -rf`, `DROP`/`TRUNCATE`)
- `.claude/settings.json` — model (`claude-opus-4-8`), permissions (allow/deny), adaptive thinking

The agents are **read-only**: they audit and design, then hand you exact `az`/Bicep commands to run
yourself. Session summaries are written to `reports/output/session-logs/` (git-ignored).

### Verify it's wired up
```bash
az account show -o json                              # correct subscription?
node .claude/hooks/pre-tool-safety.mjs <<< '{"tool_input":{"command":"az group delete -n x"}}'
#   ^ should print a JSON "deny" decision — proof the safety hook works
```

---

## Mode ② — Standalone Python (needs an Anthropic API key)

Use this if you're not running Claude Code. It calls the Anthropic API directly, so it needs a key.

### Setup
```bash
cd azure-agents
cp .env.example .env          # set ANTHROPIC_API_KEY=sk-ant-...  (git-ignored)
az login
```

### Run with Docker (no local Python)
```bash
docker compose build
docker compose run --rm agent            # security & compliance agent
docker compose run --rm data-architect   # data architect agent
```

### Run with local Python (3.11 / 3.12)
```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
az login
python azure_security_agent.py     # or: python data_architect_agent.py
```

---

## Example prompts (either mode)

**Security / compliance**
```
Run a full scan of my network layers and secrets storage. What breaches HITRUST?
Verify that all my Synapse workspaces have HITRUST r2 diagnostic logging.
Generate an Azure Policy that denies NSG rules open to the internet.
```

**Data architecture**
```
Assess my current data estate and recommend a medallion lakehouse for the claims domain.
Design a star schema for retail sales at order-line grain, then a batch ingestion pipeline
from on-prem SQL Server into a Synapse dedicated SQL pool.
```

---

## Pre-deployment checklist

- [ ] Mode ①: `claude` opens the repo, `/audit-security` runs, safety hook denies a test delete
- [ ] Mode ②: `docker compose run --rm agent` (and `data-architect`) start and answer a prompt
- [ ] `git status` shows **no `.env`** staged (`git check-ignore .env` → prints `.env`)
- [ ] `reports/output/` is git-ignored (not committing session logs)
- [ ] Your `az login` scope is correct (read-only tools returned data)

Then push (see the README's **Deploy to GitHub**).

---

## Troubleshooting

| Symptom | Fix |
| ------- | --- |
| `No active Azure subscriptions found` | `az login`; check `az account show`. |
| Claude Code not authenticated | Launch `claude` and complete the login prompt (subscription account). |
| Safety hook didn't block a delete | Ensure `node` is installed and `.claude/settings.json` hooks point at `${CLAUDE_PROJECT_DIR}/.claude/hooks/`. |
| Empty audit results | Your identity lacks read access — grant Reader on the subscription. |
| (Mode ②) Anthropic 401 | `ANTHROPIC_API_KEY` missing/wrong in `.env`. |
| (Mode ②) `pip install` fails on Python 3.14 | Use Python 3.11/3.12, or use Docker. |

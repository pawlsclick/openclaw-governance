---
name: openclaw-governance
description: Operate OpenClaw multi-agent governance with openclaw-gov — discover cron/workflow inventory, validate registry and runbooks, staged brownfield promotion, inject AGENTS.md stanzas, and ship governance PRs. Use when changing crons, workflows, runbooks, registry.yaml, RACI, governance.config.yaml, or when asked to refresh governance inventory, run governance check, adopt/migrate a governance root, or complete material system config changes.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins:
        - openclaw-gov
        - openclaw
      anyBins:
        - gh
    envVars:
      - name: OPENCLAW_GOVERNANCE_ROOT
        required: false
        description: Override path to governance root when not using default ~/.openclaw/governance or nearest governance.config.yaml.
    install:
      - kind: uv
        package: "openclaw-governance @ git+https://github.com/pawlsclick/openclaw-governance@v0.5.5"
        bins: [openclaw-gov]
    emoji: "📋"
    homepage: https://github.com/pawlsclick/openclaw-governance
---

# OpenClaw Governance (openclaw-gov)

Teaches agents to maintain the **governance root**: `registry.yaml`, runbooks, CHANGELOG, and CI drift checks. The CLI inventories live OpenClaw state; agents document and ship changes.

## Step 0 — Resolve governance root

Precedence: `--root PATH` > `OPENCLAW_GOVERNANCE_ROOT` > nearest `governance.config.yaml` walking up from cwd > `~/.openclaw/governance`.

Always confirm before mutating files:

```bash
openclaw-gov doctor --validate-config --root "$GOV_ROOT"
```

Set `GOV_ROOT` to the resolved path for commands below.

## Quick start (read-only, ~3 commands)

```bash
export GOV_ROOT="${OPENCLAW_GOVERNANCE_ROOT:-$HOME/.openclaw/governance}"

openclaw-gov doctor --validate-config --root "$GOV_ROOT"
openclaw-gov discover --root "$GOV_ROOT"
openclaw-gov check --root "$GOV_ROOT"
```

Human report goes to stderr; pipe **only stdout** when using `--json`.

## When this skill applies

Invoke for:

- Cron create/remove/schedule/payload changes
- New or updated workflow runbooks
- `workflows/registry.yaml` or RACI changes
- OpenClaw gateway/runtime/plugin changes that affect automation
- Cross-repo script path changes referenced by crons (governance PR in same window)
- Brownfield adoption from an existing governance repo

Governing runbook (read when doing material changes): `workflows/runbooks/main.system_config_change_governance.md` under the governance root.

## NEVER (critical)

1. **Do not** run `discover --write`, `discover --promote`, or `regen --write` on branch `main`.
2. **Do not** call a governance change "done" without runbook + registry (when needed) + `workflows/CHANGELOG.md` + passing `check`.
3. **Do not** pipe full `discover --json` into context — use targeted `jq` slices.
4. **Do not** use `discover --write` on brownfield systems when `discover --staged` + `--promote` is available.

## Ship workflow (always branch first)

```bash
openclaw-gov ship start --root "$GOV_ROOT"
# ... edit runbooks, registry, README via discover/regen as needed ...
openclaw-gov regen --write --root "$GOV_ROOT"
openclaw-gov check --root "$GOV_ROOT"
openclaw-gov ship commit --root "$GOV_ROOT"
# Non-interactive agents:
openclaw-gov ship commit --root "$GOV_ROOT" --push
```

Requires git remote configured at governance root. Push/PR needs `gh auth login`.

### Conventional Commits (required)

**Every governance git commit must use [Conventional Commits](https://www.conventionalcommits.org/).** Never commit on `main`. Never use vague messages (`update`, `fix stuff`, `WIP`).

Format:

```
type(scope): imperative summary

Optional body: what changed and why. Keep subject ≤72 chars.
```

Common types for governance work:

| Type | Use when |
|------|----------|
| `docs` | Runbooks, README, CHANGELOG-only updates |
| `chore` | Registry sync, inventory refresh, regen output |
| `feat` | New workflow promoted to `active` / `required` |
| `fix` | Correcting registry/runbook drift or wrong RACI |

Scope: use `governance` (matches `ship commit` defaults).

Examples:

```bash
openclaw-gov ship commit -m "docs(governance): add runbook for billing-bot daily sync" --root "$GOV_ROOT"
openclaw-gov ship commit -m "chore(governance): refresh discovered inventory snapshot" --root "$GOV_ROOT"
openclaw-gov ship commit -m "feat(governance): promote main.cron.heartbeat to active" --root "$GOV_ROOT"
```

`ship commit` without `-m` infers a generic conventional message from changed paths (e.g. `docs(governance): update runbooks`). **Prefer `-m` with a specific subject** that names the workflow or artifact you changed.

If you commit manually (not via `ship commit`), stage only governance paths and use the same conventional format before opening a PR.

## Discover — pick the right flag

| Intent | Command |
|--------|---------|
| Console summary only (no files) | `discover` |
| Refresh committed inventory JSON | `discover --inventory` |
| Inventory + promotion candidates (no registry write) | `discover --staged` |
| Apply staged merge to registry | `discover --promote` |
| Controlled promotion | `discover --promote --allowlist path.json` |
| Legacy immediate registry write | `discover --write` (greenfield only; branch first) |

Brownfield flow: see [references/brownfield-flow.md](references/brownfield-flow.md).

Full command matrix: [references/commands.md](references/commands.md).

### Useful JSON slices

```bash
openclaw-gov discover --json --root "$GOV_ROOT" | jq '.cron_instance_groups[] | select(.kind == "fan_out")'
openclaw-gov discover --json --root "$GOV_ROOT" | jq '.agent_statuses'
```

## Material change completion checklist

Before marking the task done:

- [ ] Change applied and verified on the live system
- [ ] Runbook updated under `workflows/runbooks/`
- [ ] `workflows/registry.yaml` updated if workflow is new or materially changed
- [ ] Append entry to `workflows/CHANGELOG.md` (who, what, when, where, why)
- [ ] `openclaw-gov check` passes
- [ ] `openclaw-gov regen --check` passes (CI gate)
- [ ] Governance commit uses Conventional Commits (`type(governance): summary`) on a feature branch
- [ ] Governance PR open (same change window as domain-repo script/cron changes)

Cross-repo rule: material script-path or cron-payload changes in other repos require a paired governance PR — do not merge domain automation without updated registry/runbook.

## Bootstrap and migration

```bash
# New governance root
openclaw-gov init --root "$GOV_ROOT"

# Brownfield: adopt existing repo (source authoritative)
openclaw-gov adopt --from /path/to/existing-governance --root "$GOV_ROOT"

# Inject governance stanza into agent AGENTS.md (per governance.config.yaml)
openclaw-gov inject-agents --write
openclaw-gov inject-agents --write --prune
```

See upstream [migrating guide](https://github.com/pawlsclick/openclaw-governance/blob/main/docs/migrating-existing-governance.md).

## Error rescue (common)

| Symptom | Fix |
|---------|-----|
| No governance root | `openclaw-gov init --root "$GOV_ROOT"` |
| `config ignored` | Export `OPENCLAW_GOVERNANCE_ROOT` or pass `--root` |
| discover hangs | Raise `discovery.cron_timeout_seconds` in `governance.config.yaml` |
| `regen --check` fails | On feature branch: `regen --write`, then commit |
| jq parse error | Upgrade CLI to v0.5.5+; ensure only JSON on stdout |
| promote touched curated rows | Restore from git; use `--staged` + `--allowlist` |
| CI runs old CLI | Bump pin in `.github/workflows/governance-drift.yml` |

## CI gate (governance repos)

```bash
openclaw-gov regen --check && openclaw-gov check
openclaw-gov discover --staged --root "$GOV_ROOT"
git diff --exit-code workflows/registry.yaml
```

## Install CLI (operators)

Ubuntu (pipx recommended):

```bash
pipx install "openclaw-governance @ git+https://github.com/pawlsclick/openclaw-governance@v0.5.5"
```

Mac / venv:

```bash
pip install "openclaw-governance @ git+https://github.com/pawlsclick/openclaw-governance@v0.5.5"
```

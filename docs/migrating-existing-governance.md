# Migrating an existing governance root

Use this guide when you already have a governance repository (for example `openclaw-workspace-governance`) with hand-authored `registry.yaml` entries, runbooks, and RACI domains, and want to adopt **openclaw-gov** without losing promoted workflows.

## Prerequisites

- OpenClaw installed with `openclaw.json` listing your agents
- `openclaw-gov` v0.4.0+ installed ([README](../README.md))
- A backup or git commit of your governance repo before merging

## Set the governance root

Root resolution order:

1. `openclaw-gov --root PATH`
2. `OPENCLAW_GOVERNANCE_ROOT` environment variable
3. Nearest `governance.config.yaml` walking up from cwd
4. `~/.openclaw/governance`

Example:

```bash
export OPENCLAW_GOVERNANCE_ROOT=~/Projects/my-openclaw-governance
```

## Path A: Adopt into a new target root

Use when you want a fresh `~/.openclaw/governance` (or another directory) merged from an existing repo.

```bash
# Preview
openclaw-gov adopt --from ~/Projects/openclaw-workspace-governance --dry-run

# Execute (backs up target registry, writes adoption report)
openclaw-gov adopt --from ~/Projects/openclaw-workspace-governance --root ~/.openclaw/governance
```

`adopt`:

- Copies `workflows/runbooks/*.md` only when the target file does not exist
- Merges `registry.yaml` with **staged** rules: `active`, `required`, and other promoted statuses are not overwritten
- Adds missing `raci_domains` from the source without removing target domains
- Writes `workflows/adoption-report-*.json`

Alias:

```bash
openclaw-gov init --adopt ~/Projects/openclaw-workspace-governance --root ~/.openclaw/governance
```

## Path B: Use your existing repo as the governance root

```bash
cd ~/Projects/openclaw-workspace-governance
export OPENCLAW_GOVERNANCE_ROOT=$PWD

openclaw-gov doctor --validate-config
openclaw-gov discover --staged --json
openclaw-gov check
```

## First discover after adoption

Prefer **`discover --staged`** on brownfield systems:

- Adds new crons as `status: discovered`
- Refreshes discovery-owned fields on existing `discovered` rows
- Skips hand-edited fields on `active` / `required` workflows (only updates `runtime_status` when cron enablement changes)

```bash
openclaw-gov discover --staged
openclaw-gov regen --write
openclaw-gov check
```

Use plain `discover --write` only when you intentionally want the legacy merge behavior.

## Validate configuration early

```bash
openclaw-gov config validate
openclaw-gov doctor --validate-config
```

Catches:

- Empty `accountable_humans`
- RACI accountable names not listed in config
- Unknown `agents.inject_included` agent ids
- Typos in `governance.config.yaml` keys
- `governance_root` in config pointing elsewhere than the resolved root

## Duplicate crons

Discover dedupes crons by **fingerprint** (agent + name + schedule + payload preview). If you see:

```text
WARN DUPLICATE CRON for agent `main`: fingerprint `abc123...` matches jobs ...
```

Only one registry workflow is created per fingerprint. Remove duplicate cron jobs in OpenClaw or rename/reschedule so fingerprints differ.

## Slow or failing agents

Each agent's `openclaw cron list` call uses `discovery.cron_timeout_seconds` (default **45**, max **120**). Discovery continues on failure and reports per-agent errors in `--json` output under `agent_statuses` and `errors`.

Example config:

```yaml
discovery:
  cron_timeout_seconds: 60
```

## Promote workflows

After verifying triggers and runbooks, promote entries in `workflows/registry.yaml` from `discovered` to `active` or `required`. See `workflows/README.md` in your governance root.

## Troubleshooting

| Symptom | Action |
|---------|--------|
| 21 duplicate workflow rows | Re-run `discover --staged`; check DUPLICATE CRON warnings |
| discover hangs | Lower agent count test with one agent; increase timeout; check `openclaw cron list --agent ID --json` |
| config ignored | Set `OPENCLAW_GOVERNANCE_ROOT` or pass `--root` |
| inject dry-run says `created` | Upgrade to v0.4.0+ (`would_create` on dry-run) |

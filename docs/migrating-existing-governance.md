# Migrating an existing governance root

Use this guide when you already have a governance repository with hand-authored `registry.yaml` entries, runbooks, and RACI domains, and want to adopt **openclaw-gov** without losing promoted workflows.

## Prerequisites

- OpenClaw installed with `openclaw.json` listing your agents
- `openclaw-gov` v0.5.5+ installed ([README](../README.md))
- A backup or git commit of your governance repo before merging

## Recommended migration flow

```bash
# 1. Initialize target governance root (default: ~/.openclaw/governance)
openclaw-gov init --root ~/.openclaw/governance

# 2. Adopt from your existing governance repo (source is authoritative)
openclaw-gov adopt --from ~/Projects/my-openclaw-governance --root ~/.openclaw/governance

# 3. Validate configuration
openclaw-gov doctor --validate-config --root ~/.openclaw/governance

# 4. Registry and runbook checks
openclaw-gov check --root ~/.openclaw/governance

# 5. Discover inventory (read-only console; machine-readable JSON on stdout)
openclaw-gov discover --root ~/.openclaw/governance

# 5b. Or pipe JSON only (human report is on stderr)
openclaw-gov discover --json --root ~/.openclaw/governance | jq .

# 6. Review inventory (cron_instance_groups shows fan-out; group_id in schema v2)

# 7. Review discovery candidates (writes inventory + candidates; does not mutate registry.yaml)
openclaw-gov discover --staged --root ~/.openclaw/governance
# Review workflows/discovery-candidates.json, then apply when ready:
openclaw-gov discover --promote --root ~/.openclaw/governance

# 8. Regenerate README sections (packaged generator — use in CI)
openclaw-gov regen --write --root ~/.openclaw/governance

# 9. Ship governance changes
openclaw-gov ship start --root ~/.openclaw/governance
# ... edit registry/runbooks ...
openclaw-gov ship commit --root ~/.openclaw/governance
```

**CI gate for downstream governance repos:**

```bash
openclaw-gov regen --check && openclaw-gov check
```

Do not rely on vendored generator scripts; the packaged `openclaw-gov regen` output is canonical.

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
openclaw-gov adopt --from ~/Projects/my-openclaw-governance --dry-run

# Execute (backs up target registry, writes adoption report)
openclaw-gov adopt --from ~/Projects/my-openclaw-governance --root ~/.openclaw/governance
```

By default, **adopt treats the source as authoritative**:

- `governance.config.yaml` values come from the source (only `governance_root` and `openclaw_home` are rewritten for the target)
- Top-level `registry.yaml` metadata sections are preserved
- `workflows/CHANGELOG.md`, `workflows/README.md`, and `docs/**` are copied when missing
- Runbooks under `workflows/runbooks/` are copied when missing
- Promoted workflows (`active`, `required`, etc.) in the target are not overwritten

Use `--keep-target-config` if you prefer the older behavior (target config wins on conflict; source fills gaps only).

The adoption report (`workflows/adoption-report-*.json`) includes a semantic diff: config keys overwritten/kept, registry sections copied/merged, docs copied/skipped.

Alias:

```bash
openclaw-gov init --adopt ~/Projects/my-openclaw-governance --root ~/.openclaw/governance
```

## Path B: Use your existing repo as the governance root

```bash
cd ~/Projects/my-openclaw-governance
export OPENCLAW_GOVERNANCE_ROOT=$PWD

openclaw-gov doctor --validate-config
openclaw-gov discover --staged --json
openclaw-gov check
```

## First discover after adoption

Plain `discover` is read-only (console summary only). Prefer **`discover --staged`** on brownfield systems (v0.5.1+):

- Writes stable `workflows/discovered-inventory.json` and `workflows/discovery-candidates.json`
- Does **not** mutate `registry.yaml` (safe for CI: `git diff workflows/registry.yaml` should be empty)
- Classifies findings (`missing_active_cron`, `workspace_runbook_candidate`, `protected_existing_changed`, etc.)

Use **`discover --inventory`** when you only need to refresh the committed inventory snapshot (no candidates, no registry).

Optional **`--include-runtime-metrics`** writes per-run agent timings to `workflows/discovered-inventory-runtime.json` (gitignored in template repos; not for committed governance inventory).

Apply changes explicitly with **`discover --promote`** (or `discover --promote --allowlist PATH`):

- Adds new crons as `status: discovered`
- Refreshes discovery-owned fields on existing `discovered` rows only
- Skips hand-edited fields on `active` / `required` workflows (does not change `runtime_status` on protected rows)
- Does **not** overwrite curated `agents` or `raci_domains` rows (fills missing agent fields only; generated RACI defaults are init-only when `raci_domains` is empty)
- Does **not** create runbook stubs for workflow IDs already present in `registry.yaml` (existing `runbook:` parent paths are preserved)
- Skips registry write when there is no semantic diff

**Inventory schema v2 (v0.5.5+):** After upgrading, run `discover --staged` or `discover --inventory` once and commit the regenerated `workflows/discovered-inventory.json`. See [docs/releases/v0.5.5.md](releases/v0.5.5.md).

**Allowlist (v0.5.2+):** `--allowlist` limits promotion to the listed workflow IDs only. Registry rows, runbook stubs, and workspace runbook imports all respect the allowlist. Curated agents and RACI domains are never rewritten by allowlist-scoped promote. `discovery-candidates.json` and `discovered-inventory.json` still reflect the full scan; stderr reports how many candidates were skipped by allowlist (including workspace runbook candidates).

**Brownfield on v0.5.3+:** `discover --promote` preserves curated agents/RACI and skips runbook stubs for workflows already in the registry (v0.5.4+). Prefer `discover --staged`, review candidates, then `discover --promote --allowlist` for controlled promotion.

```bash
openclaw-gov discover --staged
# review workflows/discovery-candidates.json
# optional: promote only missing_active_cron rows
openclaw-gov discover --promote --allowlist allowlist.json
openclaw-gov regen --write
openclaw-gov check
```

If you used `--promote` without an allowlist on v0.5.1 and got unreferenced runbooks, delete the orphan files under `workflows/runbooks/` (or restore from git) before re-running `check`.

Use plain `discover --write` only when you intentionally want the legacy merge behavior (writes registry immediately).

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

## Cron instance groups (fan-out)

Discover fingerprints each cron job from the **full normalized payload** (not a message preview). Jobs that share agent, name, and schedule but differ in payload are **related instances** (fan-out), not duplicates.

- **Exact duplicate** (same fingerprint): warning `EXACT DUPLICATE CRON`; only the first job is kept in discovery output.
- **Fan-out** (same name/schedule, different payload): all jobs are kept; materialization creates **one workflow** with multiple `cron_job_ids`.

JSON output includes `cron_instance_groups` with `group_id` (schema v2). Example:

```bash
openclaw-gov discover --json | jq '.cron_instance_groups[] | select(.kind == "fan_out") | {group_id, agent_id, name, job_count}'
```

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
| `jq` parse error on discover | Upgrade to v0.5.1+; ensure only JSON is piped from stdout (human report is on stderr) |
| Missing fan-out cron jobs | Check `cron_instance_groups` in JSON; distinct payloads should appear under one group |
| Adopt kept generic config | Re-run without `--keep-target-config`; inspect `adoption-report-*.json` |
| regen --check fails after regen --write | Run from governance root; ensure README has governance markers from `init` |
| discover hangs | Increase `discovery.cron_timeout_seconds`; test `openclaw cron list --agent ID --json` |
| config ignored | Set `OPENCLAW_GOVERNANCE_ROOT` or pass `--root` |
| inject dry-run modified files | Upgrade to v0.5.1+ (dry-run must not write) |

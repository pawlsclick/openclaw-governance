# Changelog

All notable changes to the **openclaw-governance** package (`openclaw-gov` CLI).

Install pins use git tags: `pipx install "openclaw-governance @ git+https://github.com/pawlsclick/openclaw-governance@vX.Y.Z"`

## v0.7.4 — 2026-05-30

**Plugin-scoped agents excluded from platform RACI broadcast (Issue #33)**

- Auto-detect plugin-owned agents via `openclaw plugins list --json` (id match or workspace under plugin rootDir).
- Default new plugin agents to `governance_scope: plugin` and `raci_broadcast_excluded: true`.
- Re-promote refreshes plugin scope unless operator explicitly promotes with `governance_scope: core` or `raci_broadcast_excluded: false`.

## v0.7.3 — 2026-05-30

**CLI version display (follow-up to v0.7.2)**

- `openclaw-gov --version` now reads from package metadata (`pyproject.toml`) instead of a stale hardcoded `__init__.py` string.
- Add CI test ensuring installed version matches `pyproject.toml`.

## v0.7.2 — 2026-05-30

**Cron fingerprint sync on promote (Issue #30)**

- `discover --promote` now keeps `discovered_from.cron_fingerprint` in sync with top-level `cron_fingerprint` and `cron_instances[].fingerprint`.
- `openclaw-gov check` errors when a single-string cron workflow has mismatched nested vs top-level fingerprints.

## v0.7.1 — 2026-05-30

**Idempotent capability promote (Issue #28)**

- Stop refreshing `discovered_at` on existing capability registry rows during promote merge.
- Set `discovered_at` only when a capability object is first created (first-seen semantics).
- Only mark capabilities as `updated` when a material refresh field actually changes.

## v0.7.0 — 2026-05-30

**Capability registry writing (Issue #26)**

- `discover --promote --include-skills --include-plugins` writes compact `capabilities` objects to `registry.yaml` for eligible skills and enabled plugins only.
- `discover --staged` adds active/inventory/drift capability buckets to `discovery-candidates.json`.
- `check --skills --plugins` validates registry coverage against the active surface; inventory-only capabilities summarized without requiring registry rows.
- Protected capability fields (`runbook`, curated `governance_status`) preserved on merge.
- `inventory skills|plugins` handles early pipe close without `BrokenPipeError`.

## v0.6.3 — 2026-05-30

**Workspace skill twin merge (Issue #21 validation)**

- `merge_skill_records` enriches `openclaw-workspace` runtime records from matching `workspace-scan` entries by name instead of appending duplicate rows.
- Filesystem-only skills (name not in runtime inventory) remain separate orphan records.

## v0.6.2 — 2026-05-30

**Skill duplicate classification fix**

- `mark_duplicate_skills` skips records with empty `install_path`. Runtime CLI skills without `filePath` were resolving `Path("")` to the process CWD and incorrectly marking ~100+ distinct skills as duplicates of the first pathless entry.

## v0.6.1 — 2026-05-30

**Skill JSON capture hotfix (Issue #21 validation)**

- `run_openclaw_json` captures CLI stdout via temp file instead of a pipe, fixing truncated `openclaw skills list --json` on large skill sets.
- `discover --staged --include-skills` writes `discovered-skills.json` even when CLI capture fails, using filesystem fallback with `degraded: true` and `cli_capture` metadata.
- `check --skills` no longer fails on a missing artifact when staged discovery already summarized skills.

## v0.6.0 — 2026-05-30

**Plugin and skill capability inventory**

- `discover --include-skills` / `--include-plugins` scan OpenClaw CLI JSON plus workspace filesystem drift.
- With `--inventory` or `--staged`, writes `workflows/discovered-skills.json` and `workflows/discovered-plugins.json` (`capabilities_schema_version: 1`).
- `check --skills` / `--plugins` validate drift against `governance.config.yaml` `capabilities:` expected/exempt lists.
- `inventory skills|plugins --json` reads committed artifacts (or `--live`).
- Optional `regen --include-capabilities` adds compact counts from committed artifacts when README markers exist.
- Plain `discover` unchanged unless `--include-*` flags are passed.

## v0.5.5 — 2026-05-28

**Safer, stable discovery artifacts**

- Plain `discover` is read-only (console summary only; no files written).
- `discover --inventory` writes stable `workflows/discovered-inventory.json` (schema v2).
- `discover --include-runtime-metrics` writes volatile timings to `workflows/discovered-inventory-runtime.json`.
- Redact sensitive CLI flag values in `message_preview` (wallet address, token, password-style flags; configurable denylist).
- Inventory uses `group_id` (deterministic hash) instead of NUL-delimited `group_key` / `instance_group_key`.
- Cron schedules stored as JSON objects when structured (legacy string schedules unchanged).

**Upgrade:** Re-run `discover --staged` or `discover --inventory` and commit the regenerated inventory. Expect a one-time diff when migrating from schema v1.

## v0.5.4 — 2026-05-28

- `discover --promote` no longer creates runbook stubs for workflows already in `registry.yaml`.
- Protected registry rows are not mutated during staged merge (no cron_job_ids union on protected workflows).

## v0.5.3 — 2026-05-28

- `discover --promote` preserves curated `agents` and `raci_domains` (fills gaps only; no refresh overwrite).

## v0.5.2 — 2026-05-27

- `discover --promote --allowlist PATH` limits registry/runbook/import mutations to listed workflow ids.

## v0.5.1 — 2026-05-27

- `discover --staged` writes inventory + `discovery-candidates.json` without mutating `registry.yaml`.
- `discover --promote` applies staged merge rules explicitly.
- CI template runs staged discover and fails if `registry.yaml` changes.

## v0.5.0

- Migration cutover: adopt, discover, regen, inject-agents, ship workflow.

# Workflow governance changelog

Append-only audit log for material workflow and system configuration changes.

## 2026-05-27 — openclaw-governance v0.5.1 staged discovery

- **Who:** openclaw-governance release
- **Workflow:** (tooling)
- **Where:** `openclaw-gov discover`, `workflows/registry.yaml`, CI drift workflow
- **What:** `discover --staged` writes inventory + `discovery-candidates.json` only; registry changes require `discover --promote` (or legacy `--write`). CI runs staged discover and fails if `registry.yaml` changes.
- **Why:** Prevent accidental registry mutation during discovery review; keep protected workflow metadata stable.
- **Runbook:** `docs/migrating-existing-governance.md` (upstream package)

## Entry format

- **Who:** agent or person
- **Workflow:** workflow id
- **Where:** files, services, cron jobs, repos
- **What:** short description of the working change
- **Why:** operational reason
- **Runbook:** path under `workflows/runbooks/`

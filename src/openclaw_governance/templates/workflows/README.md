# Workflow registry

`registry.yaml` is the canonical workflow inventory for this OpenClaw install.

## Change completion rule

When you materially change a workflow, cron, or platform integration:

1. Update the runbook under `workflows/runbooks/`
2. Update `workflows/registry.yaml` if the workflow is new or materially changed
3. Append one entry to `workflows/CHANGELOG.md`
4. Run `openclaw-gov check`

See `runbooks/main.system_config_change_governance.md`.

## Lifecycle: discovered → active

Promote `status: discovered` only after:

1. Trigger matches production (cron payload, phrase, or manual path)
2. Runbook lists verification commands and healthy state
3. `runtime_status` matches production
4. `openclaw-gov check` passes

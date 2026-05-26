# System config change governance

Workflow ID: `main.system_config_change_governance`  
Agent: `main`  
Status: required

## Purpose

Prevent silent infrastructure drift. Any core system configuration change must leave behind:

1. A runbook that defines the resulting configuration state
2. A workflow registry entry when the change introduces or materially alters standing automation
3. An append-only changelog entry (who, what, when, where, why)

## Applies to

- OpenClaw runtime, gateway, and package updates
- Cron job creation, removal, schedule changes, or payload changes
- Plugin installs, removals, or updates
- Shared-agent configuration that affects routing, tools, or recall
- Workflow registry or runbook changes that affect how other agents operate

## Enforcement rule

The task is not complete until:

- The change is applied and verified
- The runbook is updated
- The registry is updated when needed
- `workflows/CHANGELOG.md` has a new entry
- `openclaw-gov check` passes (when a governance root exists)

# openclaw-governance

Discovery, validation, and runbook generation for [OpenClaw](https://github.com/openclaw/openclaw) multi-agent installs.

`openclaw-gov` inventories agents, cron jobs, workspaces, and git repos on **your** machine, then materializes a local governance root (`registry.yaml`, runbook stubs, README sections, AGENTS.md stanzas). No dependency on any operator-specific workspace repo.

## Install (v0.1 — git URL)

```bash
pip install "openclaw-governance @ git+https://github.com/pawlsclick/openclaw-governance@v0.1.0"
```

Editable dev install:

```bash
git clone https://github.com/pawlsclick/openclaw-governance.git
cd openclaw-governance
pip install -e ".[dev]"
```

## Quick start

```bash
# 1. Initialize governance root (default: ~/.openclaw/governance)
openclaw-gov init

# 2. Discover live state (dry-run; writes inventory snapshot only)
openclaw-gov discover

# 3. Materialize registry + runbook stubs
openclaw-gov discover --write

# 4. Regenerate README tables and validate
openclaw-gov regen --write
openclaw-gov check

# 5. Inject governance stanza into each agent AGENTS.md
openclaw-gov inject-agents --write
```

Custom governance root (e.g. dedicated git repo):

```bash
openclaw-gov init --root ~/Projects/my-openclaw-governance
cd ~/Projects/my-openclaw-governance
openclaw-gov discover --write --root .
```

## Commands

| Command | Description |
|---------|-------------|
| `openclaw-gov doctor` | Check OpenClaw home, config, CLI, PyYAML |
| `openclaw-gov init` | Scaffold governance root from templates |
| `openclaw-gov discover` | Inventory agents/crons/repos (dry-run) |
| `openclaw-gov discover --write` | Write `registry.yaml` + runbook stubs |
| `openclaw-gov check` | Validate registry ↔ runbooks ↔ README |
| `openclaw-gov regen --write` | Refresh README summary + RACI markers |
| `openclaw-gov inject-agents --write` | Add governance block to `AGENTS.md` files |

## Configuration

`governance.config.yaml` in the governance root:

- `openclaw_home` — usually `~/.openclaw`
- `governance_root` — this directory
- `accountable_humans` — names allowed in RACI accountable fields
- `agents.broadcast_excluded` — cron-only agents omitted from broadcast RACI
- `discovery.*` — script globs and git repo scan toggles

## What discover creates

For each OpenClaw cron job:

- Registry entry: `status: discovered`, `runtime_status` from enabled flag
- Runbook stub: `workflows/runbooks/<agent>.cron.<name>.md` (skipped if file already exists)
- Inventory snapshot: `workflows/discovered-inventory.json`

Promote workflows to `active` / `required` after you verify triggers and fill in runbook details (see `workflows/README.md` in the governance root).

## CI

After `init`, commit the governance root and enable `.github/workflows/governance-drift.yml`. It installs this package from git and runs `openclaw-gov regen --check` and `openclaw-gov check`.

## License

MIT

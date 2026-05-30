# openclaw-governance

Discovery, validation, and runbook generation for [OpenClaw](https://github.com/openclaw/openclaw) multi-agent installs.

`openclaw-gov` inventories agents, cron jobs, workspaces, and git repos on **your** machine, then materializes a local governance root (`registry.yaml`, runbook stubs, README sections, AGENTS.md stanzas). No dependency on any operator-specific workspace repo.

## System overview

```mermaid
flowchart TB
  subgraph host["Operator machine"]
    OC["~/.openclaw\nopenclaw.json"]
    GOV["~/.openclaw/governance\ngovernance.config.yaml"]
    WS["Agent workspaces\nAGENTS.md"]
  end
  CLI["openclaw-gov CLI\ndiscover · regen · check · ship · inject-agents"]
  GH["GitHub remote\n(user-configured)"]

  OC --> CLI
  CLI --> GOV
  CLI --> WS
  GOV -->|git push| GH
  GH -->|CI| DRIFT["governance-drift.yml\nregen --check · check"]
```

## Install (v0.5.5)

Pinned release: `@v0.5.5`. Use a git tag for reproducible installs; use `@main` only if you accept moving-head changes.

See [CHANGELOG.md](CHANGELOG.md) and [docs/releases/v0.5.5.md](docs/releases/v0.5.5.md) for upgrade notes (inventory schema v2, read-only discover).

### Ubuntu / Debian (pipx — recommended)

Ubuntu 24.04+ (and many Debian installs) block system-wide `pip install` with `externally-managed-environment` (PEP 668). Use **pipx** so `openclaw-gov` gets its own environment and lands on your `PATH`:

```bash
sudo apt update
sudo apt install -y pipx python3-venv
pipx ensurepath
# Log out/in, or: source ~/.profile

pipx install "openclaw-governance @ git+https://github.com/pawlsclick/openclaw-governance@v0.5.5"
openclaw-gov --version
```

**Upgrade** to a newer tag (pipx matches installs by full URL — use `--force` when the tag changes):

```bash
pipx install "openclaw-governance @ git+https://github.com/pawlsclick/openclaw-governance@v0.5.5" --force
```

`pipx upgrade openclaw-governance` alone does not change an existing git tag pin.

**venv fallback** (no pipx): `python3 -m venv ~/.openclaw/venv/governance`, install with that venv’s `pip`, and add `~/.openclaw/venv/governance/bin` to `PATH`.

Avoid `pip install --break-system-packages` on the host Python unless you accept apt/Python conflicts.

### pip / virtualenv (macOS, containers, existing venv)

When you already work inside a virtualenv (or a image without PEP 668 restrictions):

```bash
pip install "openclaw-governance @ git+https://github.com/pawlsclick/openclaw-governance@v0.5.5"
```

### Editable dev install

```bash
git clone https://github.com/pawlsclick/openclaw-governance.git
cd openclaw-governance
pip install -e ".[dev]"
```

## Quick start

Default governance root: `~/.openclaw/governance`. Override with `--root`, `OPENCLAW_GOVERNANCE_ROOT`, or by running inside a directory tree that contains `governance.config.yaml`.

**Migrating an existing governance repo?** See [docs/migrating-existing-governance.md](docs/migrating-existing-governance.md).

```bash
# 1. Initialize governance root (default: ~/.openclaw/governance)
openclaw-gov init

# Or adopt from an existing governance root (brownfield)
openclaw-gov adopt --from ~/Projects/openclaw-workspace-governance --dry-run
openclaw-gov adopt --from ~/Projects/openclaw-workspace-governance

# 2. Set your GitHub remote and which agents get governance stanzas
#    Edit ~/.openclaw/governance/governance.config.yaml

# 3. Discover live state (read-only console summary; no files written)
openclaw-gov discover --root ~/.openclaw/governance

# 3b. Refresh committed inventory snapshot (stable JSON; no registry changes)
openclaw-gov discover --inventory --root ~/.openclaw/governance

# 4. Materialize registry + runbook stubs (also scaffolds README.md if missing)
openclaw-gov discover --write --root ~/.openclaw/governance

# Brownfield: review candidates without mutating registry (CI-safe)
openclaw-gov discover --staged --root ~/.openclaw/governance
openclaw-gov discover --promote --root ~/.openclaw/governance

# 5. Regenerate README tables and validate
openclaw-gov regen --write --root ~/.openclaw/governance
openclaw-gov check --root ~/.openclaw/governance
openclaw-gov doctor --root ~/.openclaw/governance

# 6. Inject governance stanza into selected agent AGENTS.md files
openclaw-gov inject-agents --write

# 7. Remove stanzas from agents no longer in the inject set
openclaw-gov inject-agents --write --prune
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
| `openclaw-gov doctor` | Check OpenClaw home, config, remote URL, git origin, inject list |
| `openclaw-gov doctor --validate-config` | Doctor + semantic config validation |
| `openclaw-gov config validate` | Validate `governance.config.yaml` semantics |
| `openclaw-gov init` | Scaffold governance root from templates |
| `openclaw-gov init --adopt PATH` | Adopt from an existing governance root |
| `openclaw-gov adopt --from PATH` | Adopt source governance root (source authoritative by default) |
| `openclaw-gov adopt --keep-target-config` | Adopt while keeping existing target `governance.config.yaml` on conflict |
| `openclaw-gov discover` | Read-only discovery summary (console only; no governance files written) |
| `openclaw-gov discover --inventory` | Write stable `workflows/discovered-inventory.json` (no registry changes) |
| `openclaw-gov discover --include-runtime-metrics` | Also write `workflows/discovered-inventory-runtime.json` (timings; gitignored locally) |
| `openclaw-gov discover --json` | Machine-readable inventory JSON on stdout (human report on stderr) |
| `openclaw-gov discover --write` | Write registry + runbook stubs (implies `--inventory`) |
| `openclaw-gov discover --staged` | Write inventory + `discovery-candidates.json` (no registry mutation) |
| `openclaw-gov discover --promote` | Apply staged merge and write registry when changed |
| `openclaw-gov discover --promote --allowlist PATH` | Promote only listed workflow ids; agents and curated RACI unchanged |
| `openclaw-gov check` | Validate registry ↔ runbooks ↔ README |
| `openclaw-gov regen --write` | Refresh README summary + RACI markers |
| `openclaw-gov regen --check` | CI drift check (use with `openclaw-gov check`) |
| `openclaw-gov inject-agents --write` | Add governance block to selected `AGENTS.md` files |
| `openclaw-gov inject-agents --write --prune` | Inject selected agents and remove stanza elsewhere |
| `openclaw-gov inject-agents --agent main --write` | Inject one agent (overrides config for this run) |
| `openclaw-gov ship start` | Create/checkout feature branch from `main` **before** governance `--write` |
| `openclaw-gov ship commit` | Validate, conventional commit, prompt to push/PR (`--push` / `--no-push`) |

## Ship governance changes (git workflow)

When updating governance documentation (registry, runbooks, README), **never commit on `main`**. Branch first, make changes, then commit:

```bash
# 1. Branch BEFORE any --write to the governance root
openclaw-gov ship start --root ~/.openclaw/governance

# 2. Make changes on the feature branch
openclaw-gov discover --write --root ~/.openclaw/governance
openclaw-gov regen --write --root ~/.openclaw/governance
openclaw-gov check --root ~/.openclaw/governance

# 3. Commit; prompts to push and open PR when run interactively
openclaw-gov ship commit --root ~/.openclaw/governance

# Non-interactive (agents): push and open PR explicitly
openclaw-gov ship commit --root ~/.openclaw/governance --push
```

Requires a git repository at the governance root with `remote.url` configured. Push/PR needs `gh` authenticated (`gh auth login`).

## Configuration

`governance.config.yaml` in the governance root:

- `openclaw_home` — usually `~/.openclaw`
- `governance_root` — this directory
- `remote.url` — GitHub (or other) remote where you push governance changes
- `remote.default_branch` — default branch name (default: `main`)
- `accountable_humans` — names allowed in RACI accountable fields
- `agents.broadcast_excluded` — cron-only agents omitted from broadcast RACI
- `agents.inject_included` — allowlist of agent ids that receive the governance stanza in `AGENTS.md`. **Omit the key** to inject all agents; **`[]`** injects none until you pass `--agent`
- **Discovery** (`discovery.*`) — script globs, git repo scan toggles, `cron_timeout_seconds` (default 45, max 120), optional `sensitive_preview_flags` (extra CLI flags redacted in `message_preview`)

Root precedence: `--root` > `OPENCLAW_GOVERNANCE_ROOT` > nearest `governance.config.yaml` > `~/.openclaw/governance`.

### Automatic RACI domains (no manual registry edits)

On `discover --write`, the tool creates RACI domains from **whatever agents exist on your machine** — no product-specific names:

| Discovered agent | Auto domain key | Workflow prefix |
|------------------|-----------------|-----------------|
| `billing-bot` | `billing_bot_ops` | `billing-bot.*` |
| `research` | `research_ops` | `research.*` |
| `main` (if present) | `main_ops` + shared `personal_ops` / `governance_registry` | `main.*` |

Each workflow gets `raci_domain` inferred from its id prefix (or `agent` field). Existing domain blocks and explicit `raci_workflow_domains` entries are never overwritten. Customize naming with `domain_prefix_rules` in config (replaces built-in defaults when set).

Example:

```yaml
remote:
  url: "https://github.com/you/your-governance-repo.git"
  default_branch: main

agents:
  inject_included:
    - main
    - research
```

## What discover creates

`openclaw-gov discover` scans live OpenClaw state and prints a console summary. It does **not** write governance files unless you pass `--inventory`, `--staged`, `--promote`, or `--write`.

`openclaw-gov discover --inventory` writes a **stable** inventory snapshot at `workflows/discovered-inventory.json` (no `generated_at` or per-run agent timings; cron schedules as JSON objects; `group_id` instead of NUL-delimited keys; sensitive CLI flag values redacted in previews). Optional `--include-runtime-metrics` writes volatile timings to `workflows/discovered-inventory-runtime.json`.

`openclaw-gov discover --write` also:

- **Imports** workspace runbooks into `workflows/runbooks/{workflow_id}.md` (converted to openclaw-gov format; skips if destination already exists)
- **Links** all governance runbooks (existing + imported) into `registry.yaml`
- **Creates** cron runbook stubs and registry entries as before

Workflow id for workspace imports: `{agent}.{slug}` from the filename (or the filename stem when it already starts with `{agent}.`).

For each OpenClaw cron job:

- Registry entry: `status: discovered`, `runtime_status` from enabled flag
- Runbook stub: `workflows/runbooks/<agent>.cron.<name>.md` (skipped if file already exists)
- Inventory snapshot: `workflows/discovered-inventory.json` (when using `--inventory`, `--staged`, `--promote`, or `--write`)

Discovery scans **agents** from `openclaw.json`, **cron jobs** via `openclaw cron list --json`, **governance runbooks** under `workflows/runbooks/*.md`, and **workspace runbooks** matching `*runbook*.md` (identify only unless promoted/imported).

For each runbook already on disk (without a matching cron-derived workflow):

- Registry entry: `status: discovered`, `runbook` pointer set, title taken from the runbook heading when possible
- Runbook file is never overwritten

Promote workflows to `active` / `required` after you verify triggers and fill in runbook details (see `workflows/README.md` in the governance root).

## CI

After `init`, commit the governance root and enable `.github/workflows/governance-drift.yml`. It installs `@v0.5.5` from git, runs `openclaw-gov regen --check` and `openclaw-gov check`, and runs `openclaw-gov discover --staged` with `git diff --exit-code workflows/registry.yaml` so staged discovery cannot mutate the registry in CI.

**Existing governance repos:** `init` does not overwrite a workflow file already on disk. After upgrading to v0.5.5, manually bump the install pin in your repo's `.github/workflows/governance-drift.yml` (see [migrating guide](docs/migrating-existing-governance.md#ci-workflow-pin-existing-governance-repos)).

## License

MIT

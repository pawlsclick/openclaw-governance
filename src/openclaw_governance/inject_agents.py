"""Inject governance stanza into agent AGENTS.md files."""

from __future__ import annotations

from pathlib import Path

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import load_openclaw_config, parse_agents_from_config

BEGIN = "<!-- openclaw-governance:begin -->"
END = "<!-- openclaw-governance:end -->"


def render_stanza(config: GovernanceConfig) -> str:
    root = config.governance_root
    registry_rel = "workflows/registry.yaml"
    return f"""{BEGIN}
## Governance (OpenClaw)

This agent follows the workspace governance contract maintained by **openclaw-gov**.

- **Governance root:** `{root}`
- **Registry:** `{registry_rel}` (canonical workflow inventory)
- **On material workflow, cron, or platform change:** update runbook → registry → `workflows/CHANGELOG.md` → governance PR
- **Governing runbook:** `workflows/runbooks/main.system_config_change_governance.md`
- **Validate:** `openclaw-gov check` and `openclaw-gov regen --check`

Do not wait to be asked for documentation updates after a working change is verified.

{END}
"""


def inject_file(path: Path, stanza: str, *, write: bool) -> str:
    if not path.is_file():
        body = f"# AGENTS.md\n\n{stanza}\n"
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return "created"

    text = path.read_text(encoding="utf-8")
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        updated = text[:start] + stanza.rstrip() + text[end:]
        action = "updated" if updated != text else "unchanged"
    else:
        separator = "\n\n" if text.endswith("\n") else "\n\n"
        updated = text.rstrip() + separator + stanza + "\n"
        action = "appended"

    if write and updated != text:
        path.write_text(updated, encoding="utf-8")
    elif write:
        pass
    return action if write or updated == text else f"would_{action}"


def collect_agent_files(config: GovernanceConfig) -> list[Path]:
    paths: list[Path] = []
    try:
        openclaw_config = load_openclaw_config(config)
        for agent in parse_agents_from_config(openclaw_config, config):
            paths.append(Path(agent.workspace) / "AGENTS.md")
    except (FileNotFoundError, ValueError):
        pass

    main_workspace = config.openclaw_home / "workspace"
    paths.append(main_workspace / "AGENTS.md")
    return sorted({path.resolve() for path in paths})


def run_inject(config: GovernanceConfig, *, write: bool = False) -> int:
    stanza = render_stanza(config)
    any_error = False
    for agents_path in collect_agent_files(config):
        action = inject_file(agents_path, stanza, write=write)
        print(f"{action}: {agents_path}")
        if action == "would_created" and not write:
            continue
    if not collect_agent_files(config):
        print("WARN no agent AGENTS.md paths found (check openclaw.json)")
        any_error = True
    return 1 if any_error else 0

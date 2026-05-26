"""Inject governance stanza into agent AGENTS.md files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import load_openclaw_config, parse_agents_from_config

BEGIN = "<!-- openclaw-governance:begin -->"
END = "<!-- openclaw-governance:end -->"


@dataclass(frozen=True)
class AgentAgentsTarget:
    agent_id: str
    path: Path


def render_stanza(config: GovernanceConfig) -> str:
    root = config.governance_root
    registry_rel = "workflows/registry.yaml"
    lines = [
        BEGIN,
        "## Governance (OpenClaw)",
        "",
        "This agent follows the workspace governance contract maintained by **openclaw-gov**.",
        "",
        f"- **Governance root:** `{root}`",
        f"- **Registry:** `{registry_rel}` (canonical workflow inventory)",
    ]
    if config.remote_url:
        lines.append(f"- **Governance remote:** `{config.remote_url}` (open PRs here after material changes)")
    lines.extend(
        [
            "- **On material workflow, cron, or platform change:** update runbook → registry → `workflows/CHANGELOG.md` → governance PR",
            "- **Governing runbook:** `workflows/runbooks/main.system_config_change_governance.md`",
            "- **Validate:** `openclaw-gov check` and `openclaw-gov regen --check`",
            "",
            "Do not wait to be asked for documentation updates after a working change is verified.",
            "",
            END,
        ]
    )
    return "\n".join(lines) + "\n"


def has_stanza(text: str) -> bool:
    return BEGIN in text and END in text


def remove_stanza_from_text(text: str) -> tuple[str, bool]:
    if not has_stanza(text):
        return text, False
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    prefix = text[:start].rstrip()
    suffix = text[end:].lstrip("\n")
    if prefix and suffix:
        updated = prefix + "\n\n" + suffix
    elif prefix:
        updated = prefix + "\n"
    elif suffix:
        updated = suffix + "\n" if not suffix.endswith("\n") else suffix
    else:
        updated = ""
    return updated, True


def inject_file(path: Path, stanza: str, *, write: bool) -> str:
    if not path.is_file():
        body = f"# AGENTS.md\n\n{stanza}\n"
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return "created"

    text = path.read_text(encoding="utf-8")
    if has_stanza(text):
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


def prune_file(path: Path, *, write: bool) -> str:
    if not path.is_file():
        return "unchanged"
    text = path.read_text(encoding="utf-8")
    updated, removed = remove_stanza_from_text(text)
    if not removed:
        return "unchanged"
    if write:
        path.write_text(updated, encoding="utf-8")
    return "pruned" if write else "would_prune"


def collect_agent_targets(config: GovernanceConfig) -> list[AgentAgentsTarget]:
    """All known agents mapped to AGENTS.md paths (deduped by path)."""
    by_path: dict[Path, str] = {}
    try:
        openclaw_config = load_openclaw_config(config)
        for agent in parse_agents_from_config(openclaw_config, config):
            path = (Path(agent.workspace) / "AGENTS.md").resolve()
            by_path[path] = agent.agent_id
    except (FileNotFoundError, ValueError):
        pass

    main_path = (config.openclaw_home / "workspace" / "AGENTS.md").resolve()
    if main_path not in by_path:
        by_path[main_path] = "main"

    return [
        AgentAgentsTarget(agent_id=agent_id, path=path)
        for path, agent_id in sorted(by_path.items(), key=lambda item: item[1])
    ]


def known_agent_ids(config: GovernanceConfig) -> set[str]:
    try:
        openclaw_config = load_openclaw_config(config)
        return {agent.agent_id for agent in parse_agents_from_config(openclaw_config, config)}
    except (FileNotFoundError, ValueError):
        return set()


def resolve_inject_agent_ids(
    config: GovernanceConfig,
    *,
    cli_agents: list[str] | None = None,
) -> set[str]:
    """Agent IDs that should receive (or keep) the governance stanza."""
    if cli_agents:
        return {agent_id.strip() for agent_id in cli_agents if agent_id.strip()}

    if config.inject_included is not None:
        return set(config.inject_included)

    return known_agent_ids(config)


def run_inject(
    config: GovernanceConfig,
    *,
    write: bool = False,
    cli_agents: list[str] | None = None,
    prune: bool = False,
) -> int:
    targets = collect_agent_targets(config)
    if not targets:
        print("WARN no agent AGENTS.md paths found (check openclaw.json)")
        return 1

    inject_ids = resolve_inject_agent_ids(config, cli_agents=cli_agents)
    stanza = render_stanza(config)
    any_error = False

    for target in targets:
        should_inject = target.agent_id in inject_ids
        if should_inject:
            action = inject_file(target.path, stanza, write=write)
            print(f"{action}: {target.path} ({target.agent_id})")
        else:
            print(f"skip (not in inject set): {target.path} ({target.agent_id})")

    if prune:
        for target in targets:
            if target.agent_id in inject_ids:
                continue
            action = prune_file(target.path, write=write)
            if action != "unchanged":
                print(f"{action}: {target.path} ({target.agent_id})")

    unknown = inject_ids - known_agent_ids(config)
    if unknown:
        print(f"WARN inject set includes unknown agent ids: {', '.join(sorted(unknown))}")
        any_error = True

    return 1 if any_error else 0

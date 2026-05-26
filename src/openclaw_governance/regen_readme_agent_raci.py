"""Regenerate README agent RACI section from registry.yaml."""

from __future__ import annotations

import re
from typing import Any

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.registry_common import (
    UniqueKeyLoader,
    agent_ids,
    agents_excluded_from_raci_broadcast,
    construct_mapping_without_duplicate_keys,
    load_registry,
    normalize_party_list,
    raci_domains,
)

UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping_without_duplicate_keys
)

BEGIN_MARKER = "<!-- governance:agent-raci:begin -->"
END_MARKER = "<!-- governance:agent-raci:end -->"


def render_agent_catalog(agents: list[dict[str, Any]]) -> list[str]:
    lines = [
        "### Agent catalog",
        "",
        "| Agent ID | Name | Role | Workspace |",
        "|---|---|---|---|",
    ]
    for entry in sorted(agents, key=lambda item: str(item.get("id", ""))):
        if not isinstance(entry, dict):
            continue
        agent_id = entry.get("id", "")
        name = entry.get("name", "")
        role = entry.get("role", "")
        workspace = str(entry.get("workspace", "")).replace("|", "\\|")
        if entry.get("raci_broadcast_excluded") is True:
            role = f"{role} (cron-only; excluded from cross-agent RACI broadcasts)"
        lines.append(f"| `{agent_id}` | {name} | {role} | `{workspace}` |")
    lines.append("")
    return lines


def render_domain_matrix(
    domains: dict[str, dict[str, Any]],
    agent_id_list: list[str],
    broadcast_excluded: set[str],
) -> list[str]:
    broadcast_note = (
        "Core platform domains should inform every broadcast agent on material changes "
        "(every registered agent except those marked `raci_broadcast_excluded`)."
    )
    if broadcast_excluded:
        excluded_list = ", ".join(f"`{agent_id}`" for agent_id in sorted(broadcast_excluded))
        broadcast_note += f" Excluded from broadcasts: {excluded_list}."
    lines = [
        "### Domain RACI",
        "",
        "Letters: **R** = responsible (executing agent), **A** = accountable (human), **C** = consulted, **I** = informed.",
        broadcast_note,
        "",
        "| Domain | R | A | C | I |",
        "|---|---|---|---|---|",
    ]
    for domain_key in sorted(domains):
        domain = domains[domain_key]
        title = domain.get("title", domain_key)
        responsible = domain.get("responsible", "")
        accountable = domain.get("accountable", "")
        consulted = ", ".join(normalize_party_list(domain.get("consulted")))
        informed = ", ".join(normalize_party_list(domain.get("informed")))
        lines.append(
            f"| {title}<br>`{domain_key}` | `{responsible}` | {accountable} | {consulted or '—'} | {informed or '—'} |"
        )

    lines.extend(
        [
            "",
            f"Registered agents: {', '.join(f'`{agent_id}`' for agent_id in sorted(agent_id_list))}.",
            "",
        ]
    )
    return lines


def replace_marked_section(readme: str, body: str) -> str:
    pattern = re.compile(
        re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
        flags=re.DOTALL,
    )
    replacement = f"{BEGIN_MARKER}\n{body}{END_MARKER}"
    if not pattern.search(readme):
        raise ValueError(f"README.md missing {BEGIN_MARKER} / {END_MARKER} markers")
    return pattern.sub(replacement, readme, count=1)


def render_section(registry: dict[str, Any]) -> str:
    agents = registry.get("agents")
    if not isinstance(agents, list):
        agents = []
    agent_id_list = agent_ids(registry)
    domains = raci_domains(registry)

    lines: list[str] = []
    lines.extend(render_agent_catalog([entry for entry in agents if isinstance(entry, dict)]))
    excluded = agents_excluded_from_raci_broadcast(registry)
    lines.extend(render_domain_matrix(domains, agent_id_list, excluded))
    return "\n".join(lines) + "\n"


def run_regen_raci(config: GovernanceConfig, *, write: bool = False, check: bool = False) -> int:
    root = config.governance_root
    registry_path = config.registry_path
    readme_path = config.readme_path

    try:
        registry = load_registry(registry_path)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"ERROR {exc}")
        return 1

    generated = render_section(registry)
    readme = readme_path.read_text(encoding="utf-8")
    try:
        updated = replace_marked_section(readme, generated)
    except ValueError as exc:
        print(f"ERROR {exc}")
        return 1

    if write:
        readme_path.write_text(updated, encoding="utf-8")
        print(f"updated {readme_path.relative_to(root)}")
        return 0

    if check:
        if updated != readme:
            print("ERROR README agent RACI is stale; run: openclaw-gov regen --write")
            return 1
        print("readme_agent_raci_ok")
        return 0

    print(generated)
    return 0

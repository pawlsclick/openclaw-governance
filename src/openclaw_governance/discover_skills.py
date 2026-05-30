"""Discover installed OpenClaw skills via CLI and workspace filesystem scan."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openclaw_governance.capability_enrich import (
    SCOPE_NOTE,
    infer_skill_type,
    merge_skill_records,
    scan_skill_tree,
    scan_workspace_skills,
    shorten_home,
)
from openclaw_governance.capability_governance import apply_skill_governance_statuses, summarize_statuses
from openclaw_governance.config import CapabilitiesConfig, GovernanceConfig
from openclaw_governance.discover import DiscoveredAgent
from openclaw_governance.openclaw_cli import openclaw_cli_version, run_openclaw_json

CAPABILITIES_SCHEMA_VERSION = 1


@dataclass
class SkillsDiscoveryResult:
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _source_is_install_path(source: str) -> bool:
    if not source:
        return False
    if source.startswith(("/", "~")):
        return True
    return "/" in source or "\\" in source


def _project_cli_skill(skill: dict[str, Any], *, agent_id: str | None) -> dict[str, Any]:
    source = str(skill.get("source") or "")
    name = str(skill.get("name") or "unnamed")
    install_raw = skill.get("filePath") or skill.get("baseDir")
    if not install_raw and _source_is_install_path(source):
        install_raw = source
    install_path = shorten_home(str(install_raw)) if install_raw else ""
    path_obj = Path(str(skill.get("filePath") or skill.get("path") or name))
    return {
        "name": name,
        "type": infer_skill_type(path_obj, source),
        "agent_id": agent_id,
        "install_path": install_path,
        "source": source,
        "eligible": skill.get("eligible"),
        "bundled": bool(skill.get("bundled")),
        "governance_status": "undocumented",
        "flags": {"symlink": False, "duplicate_of": None, "orphan": False},
    }


def _cli_skills_to_records(data: dict[str, Any]) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    skills_raw = data.get("skills")
    if not isinstance(skills_raw, list):
        return [], set(), set()
    records: list[dict[str, Any]] = []
    paths: set[str] = set()
    names: set[str] = set()
    for item in skills_raw:
        if not isinstance(item, dict):
            continue
        record = _project_cli_skill(item, agent_id=None)
        records.append(record)
        if record["install_path"]:
            paths.add(str(record["install_path"]))
        names.add(str(record["name"]))
    return records, paths, names


def discover_skills(
    config: GovernanceConfig,
    agents: list[DiscoveredAgent],
    capabilities: CapabilitiesConfig,
) -> SkillsDiscoveryResult:
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []
    cli_records: list[dict[str, Any]] = []
    cli_paths: set[str] = set()
    cli_names: set[str] = set()

    data, err = run_openclaw_json(
        ["skills", "list", "--json"],
        timeout_seconds=config.discovery_cron_timeout_seconds,
    )
    if err:
        warnings.append(err)
        errors.append({"phase": "skills_list", "message": err})
    elif data:
        cli_records, cli_paths, cli_names = _cli_skills_to_records(data)

    workspace_records: list[dict[str, Any]] = []
    for agent in agents:
        workspace = Path(agent.workspace)
        if not workspace.is_dir():
            continue
        workspace_records.extend(
            scan_workspace_skills(
                agent.agent_id,
                workspace,
                cli_paths=cli_paths,
                cli_names=cli_names,
            )
        )

    for optional_root in capabilities.optional_scan_roots:
        if not str(optional_root).strip():
            continue
        root = Path(optional_root).expanduser()
        if root.is_dir():
            workspace_records.extend(
                scan_skill_tree(
                    root,
                    "host",
                    cli_paths=cli_paths,
                    cli_names=cli_names,
                )
            )

    plugin_skills = config.openclaw_home / "plugin-skills"
    if plugin_skills.is_dir():
        workspace_records.extend(
            scan_skill_tree(
                plugin_skills,
                "host",
                cli_paths=cli_paths,
                cli_names=cli_names,
            )
        )

    skills = merge_skill_records(cli_records, workspace_records)
    apply_skill_governance_statuses(
        skills,
        expected=set(capabilities.expected_skills),
        exempt=set(capabilities.exempt_skills),
    )

    payload: dict[str, Any] = {
        "capabilities_schema_version": CAPABILITIES_SCHEMA_VERSION,
        "openclaw_home": str(config.openclaw_home),
        "openclaw_cli_version": openclaw_cli_version(),
        "scope_note": SCOPE_NOTE,
        "skills": skills,
        "summary": summarize_statuses(skills),
        "warnings": warnings,
        "errors": errors,
    }
    return SkillsDiscoveryResult(payload=payload, warnings=warnings, errors=errors)

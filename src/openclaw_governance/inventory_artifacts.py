"""Write capability inventory artifacts under workflows/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover_plugins import PluginsDiscoveryResult
from openclaw_governance.discover_skills import SkillsDiscoveryResult


def write_capability_artifacts(
    config: GovernanceConfig,
    *,
    skills: SkillsDiscoveryResult | None = None,
    plugins: PluginsDiscoveryResult | None = None,
) -> dict[str, str]:
    paths: dict[str, str] = {}
    if skills is None and plugins is None:
        return paths

    workflows_dir = config.governance_root / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    if skills is not None:
        skills_path = workflows_dir / "discovered-skills.json"
        skills_path.write_text(json.dumps(skills.payload, indent=2) + "\n", encoding="utf-8")
        paths["skills_inventory_path"] = str(skills_path)

    if plugins is not None:
        plugins_path = workflows_dir / "discovered-plugins.json"
        plugins_path.write_text(json.dumps(plugins.payload, indent=2) + "\n", encoding="utf-8")
        paths["plugins_inventory_path"] = str(plugins_path)

    return paths


def _load_json_object_artifact(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def load_skills_artifact(config: GovernanceConfig) -> dict[str, Any] | None:
    path = config.governance_root / "workflows" / "discovered-skills.json"
    return _load_json_object_artifact(path)


def load_plugins_artifact(config: GovernanceConfig) -> dict[str, Any] | None:
    path = config.governance_root / "workflows" / "discovered-plugins.json"
    return _load_json_object_artifact(path)

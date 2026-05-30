"""Validate capability inventory drift against governance policy."""

from __future__ import annotations

from typing import Any

from openclaw_governance.capability_governance import (
    DEFAULT_CHECK_FAIL_ON,
    plugin_is_material,
    skill_is_material,
)
from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import discover
from openclaw_governance.discover_plugins import discover_plugins
from openclaw_governance.discover_skills import discover_skills
from openclaw_governance.inventory_artifacts import load_plugins_artifact, load_skills_artifact


class CapabilityCheck:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(f"ERROR {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(f"WARN {message}")


def _check_skills_payload(payload: dict[str, Any], check: CapabilityCheck, fail_on: set[str]) -> None:
    skills = payload.get("skills")
    if not isinstance(skills, list):
        check.error("discovered-skills.json missing skills array")
        return

    undocumented_material = 0
    for record in skills:
        if not isinstance(record, dict):
            continue
        status = str(record.get("governance_status") or "undocumented")
        if status == "undocumented" and skill_is_material(record):
            undocumented_material += 1
            name = record.get("name", "?")
            if "undocumented_skill" in fail_on:
                check.error(f"undocumented skill: {name}")
            else:
                check.warn(f"undocumented skill: {name}")

    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    bundled_undocumented = summary.get("undocumented", 0) - undocumented_material
    if bundled_undocumented > 0 and "undocumented_skill" not in fail_on:
        check.warn(
            f"{bundled_undocumented} bundled or low-material skills undocumented (summary only)"
        )


def _check_plugins_payload(payload: dict[str, Any], check: CapabilityCheck, fail_on: set[str]) -> None:
    plugins = payload.get("plugins")
    if not isinstance(plugins, list):
        check.error("discovered-plugins.json missing plugins array")
        return

    for record in plugins:
        if not isinstance(record, dict):
            continue
        status = str(record.get("governance_status") or "undocumented")
        if status != "undocumented":
            continue
        if not plugin_is_material(record):
            continue
        plugin_id = record.get("id") or record.get("name") or "?"
        if "undocumented_plugin_enabled" in fail_on:
            check.error(f"enabled undocumented plugin: {plugin_id}")
        else:
            check.warn(f"enabled undocumented plugin: {plugin_id}")


def run_check_capabilities(
    config: GovernanceConfig,
    *,
    skills: bool = False,
    plugins: bool = False,
    live: bool = False,
) -> int:
    check = CapabilityCheck()
    fail_on = {_normalize_fail_key(item) for item in config.capabilities.check_fail_on}
    if not fail_on:
        fail_on = set(DEFAULT_CHECK_FAIL_ON)

    if skills:
        payload = None
        if live:
            discovery = discover(config)
            result = discover_skills(config, discovery.agents, config.capabilities)
            payload = result.payload
        else:
            payload = load_skills_artifact(config)
            if payload is None:
                check.error(
                    "discovered-skills.json missing; run discover --inventory --include-skills "
                    "or pass --live"
                )
        if payload is not None:
            _check_skills_payload(payload, check, fail_on)

    if plugins:
        payload = None
        if live:
            result = discover_plugins(config, config.capabilities)
            payload = result.payload
        else:
            payload = load_plugins_artifact(config)
            if payload is None:
                check.error(
                    "discovered-plugins.json missing; run discover --inventory --include-plugins "
                    "or pass --live"
                )
        if payload is not None:
            _check_plugins_payload(payload, check, fail_on)

    for warning in check.warnings:
        print(warning)
    for error in check.errors:
        print(error)

    if check.errors:
        return 1
    if skills or plugins:
        print("governance_capabilities_ok")
    return 0


def _normalize_fail_key(value: str) -> str:
    return value.strip()

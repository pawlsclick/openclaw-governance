"""Validate capability inventory drift against governance policy."""

from __future__ import annotations

from typing import Any

from openclaw_governance.capability_governance import (
    DEFAULT_CHECK_FAIL_ON,
    apply_plugin_governance_statuses,
    apply_skill_governance_statuses,
    plugin_is_material,
    skill_is_material,
    summarize_statuses,
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


def _reapply_skill_governance(payload: dict[str, Any], config: GovernanceConfig) -> None:
    skills = payload.get("skills")
    if not isinstance(skills, list):
        return
    apply_skill_governance_statuses(
        skills,
        expected=set(config.capabilities.expected_skills),
        exempt=set(config.capabilities.exempt_skills),
    )
    payload["summary"] = summarize_statuses(skills)


def _reapply_plugin_governance(payload: dict[str, Any], config: GovernanceConfig) -> None:
    plugins = payload.get("plugins")
    if not isinstance(plugins, list):
        return
    apply_plugin_governance_statuses(
        plugins,
        expected=set(config.capabilities.expected_plugins),
        exempt=set(config.capabilities.exempt_plugins),
    )
    payload["summary"] = summarize_statuses(plugins)


def _check_discovery_payload_errors(payload: dict[str, Any], check: CapabilityCheck, label: str) -> None:
    errors = payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return
    for item in errors:
        if isinstance(item, dict):
            phase = item.get("phase") or label
            message = item.get("message") or item
            check.error(f"discovery failed ({phase}): {message}")
        else:
            check.error(f"discovery failed ({label}): {item}")


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
    configured_fail_on = config.capabilities.check_fail_on
    if configured_fail_on is None:
        fail_on = set(DEFAULT_CHECK_FAIL_ON)
    else:
        fail_on = {_normalize_fail_key(item) for item in configured_fail_on}

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
            elif not payload:
                check.error("discovered-skills.json is invalid or empty")
            else:
                _reapply_skill_governance(payload, config)
        if payload:
            _check_discovery_payload_errors(payload, check, "skills")
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
            elif not payload:
                check.error("discovered-plugins.json is invalid or empty")
            else:
                _reapply_plugin_governance(payload, config)
        if payload:
            _check_discovery_payload_errors(payload, check, "plugins")
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

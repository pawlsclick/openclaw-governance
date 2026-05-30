"""Validate capability inventory drift against governance policy."""

from __future__ import annotations

from typing import Any

import yaml

from openclaw_governance.capability_governance import (
    DEFAULT_CHECK_FAIL_ON,
    apply_plugin_governance_statuses,
    apply_skill_governance_statuses,
    plugin_is_material,
    summarize_statuses,
)
from openclaw_governance.capability_registry import (
    _capabilities_section,
    capability_is_governed,
    is_active_plugin,
    is_active_skill,
    is_inventory_only_plugin,
    is_inventory_only_skill,
    plugin_registry_id,
    skill_registry_id,
)
from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import discover
from openclaw_governance.discover_plugins import discover_plugins
from openclaw_governance.discover_skills import discover_skills
from openclaw_governance.inventory_artifacts import load_plugins_artifact, load_skills_artifact
from openclaw_governance.registry_common import load_registry


class CapabilityCheck:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(f"ERROR {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(f"WARN {message}")


def _load_registry_capabilities(config: GovernanceConfig, check: CapabilityCheck) -> dict[str, Any]:
    path = config.registry_path
    empty: dict[str, Any] = {"schema_version": 1, "skills": [], "plugins": []}
    if not path.is_file():
        return empty
    try:
        registry = load_registry(path)
    except OSError as exc:
        check.error(f"{path} cannot be read: {exc}")
        return empty
    except yaml.YAMLError as exc:
        check.error(f"{path} does not parse as YAML: {exc}")
        return empty
    except ValueError as exc:
        check.error(str(exc))
        return empty
    return _capabilities_section(registry)


def _registry_skill_index(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in section.get("skills", [])
        if isinstance(item, dict) and item.get("id")
    }


def _registry_plugin_index(section: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in section.get("plugins", [])
        if isinstance(item, dict) and item.get("id")
    }


def _check_skills_payload(
    payload: dict[str, Any],
    check: CapabilityCheck,
    fail_on: set[str],
    registry_section: dict[str, Any],
) -> None:
    skills = payload.get("skills")
    if not isinstance(skills, list):
        check.error("discovered-skills.json missing skills array")
        return

    reg_skills = _registry_skill_index(registry_section)
    inventory_only = 0

    for record in skills:
        if not isinstance(record, dict):
            check.error("discovered-skills.json contains non-object skill entries")
            continue

        if is_inventory_only_skill(record):
            inventory_only += 1
            continue

        if not is_active_skill(record):
            inventory_only += 1
            continue

        name = str(record.get("name") or "?")
        entry_id = skill_registry_id(name)
        reg_entry = reg_skills.get(entry_id)
        status = str(record.get("governance_status") or "undocumented")
        if status in {"exempt", "expected"}:
            continue
        governed = capability_is_governed(reg_entry) if reg_entry else False
        if governed:
            continue

        if reg_entry is None:
            message = f"eligible skill not in registry capabilities: {name}"
        else:
            message = f"active undocumented skill: {name}"
        if "undocumented_skill" in fail_on:
            check.error(message)
        else:
            check.warn(message)

    if inventory_only > 0:
        check.warn(
            f"{inventory_only} skills are inventory-only (ineligible or inactive; no registry required)"
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
    degraded = payload.get("degraded") is True
    for item in errors:
        if isinstance(item, dict):
            phase = item.get("phase") or label
            message = item.get("message") or item
            msg = f"discovery failed ({phase}): {message}"
        else:
            msg = f"discovery failed ({label}): {item}"
        if degraded:
            check.warn(msg.replace("discovery failed", "discovery degraded", 1))
        else:
            check.error(msg)


def _check_plugins_payload(
    payload: dict[str, Any],
    check: CapabilityCheck,
    fail_on: set[str],
    registry_section: dict[str, Any],
) -> None:
    plugins = payload.get("plugins")
    if not isinstance(plugins, list):
        check.error("discovered-plugins.json missing plugins array")
        return

    reg_plugins = _registry_plugin_index(registry_section)
    inventory_only = 0

    for record in plugins:
        if not isinstance(record, dict):
            check.error("discovered-plugins.json contains non-object plugin entries")
            continue

        if is_inventory_only_plugin(record):
            inventory_only += 1
            continue

        if not is_active_plugin(record):
            inventory_only += 1
            continue

        plugin_id = str(record.get("id") or record.get("name") or "?")
        entry_id = plugin_registry_id(plugin_id)
        reg_entry = reg_plugins.get(entry_id)
        status = str(record.get("governance_status") or "undocumented")
        if status in {"exempt", "expected"}:
            continue
        governed = capability_is_governed(reg_entry) if reg_entry else False
        if governed:
            continue

        if reg_entry is None:
            message = f"enabled plugin not in registry capabilities: {plugin_id}"
        else:
            message = f"enabled undocumented plugin: {plugin_id}"
        if "undocumented_plugin_enabled" in fail_on:
            check.error(message)
        else:
            check.warn(message)

    if inventory_only > 0:
        check.warn(
            f"{inventory_only} plugins are inventory-only (disabled; no registry required)"
        )


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

    registry_section = _load_registry_capabilities(config, check)

    if skills:
        payload = None
        if live:
            if not config.capabilities.discover_skills:
                check.error(
                    "--skills --live requested but capabilities.discover_skills is false"
                )
            else:
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
            _check_skills_payload(payload, check, fail_on, registry_section)

    if plugins:
        payload = None
        if live:
            if not config.capabilities.discover_plugins:
                check.error(
                    "--plugins --live requested but capabilities.discover_plugins is false"
                )
            else:
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
            _check_plugins_payload(payload, check, fail_on, registry_section)

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

"""Discover installed OpenClaw plugins via CLI JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from openclaw_governance.capability_enrich import shorten_home
from openclaw_governance.capability_governance import apply_plugin_governance_statuses, summarize_statuses
from openclaw_governance.config import CapabilitiesConfig, GovernanceConfig
from openclaw_governance.openclaw_cli import openclaw_cli_version, run_openclaw_json

CAPABILITIES_SCHEMA_VERSION = 1

PROJECTED_PLUGIN_FIELDS = (
    "id",
    "name",
    "version",
    "description",
    "format",
    "source",
    "rootDir",
    "origin",
    "status",
    "providerIds",
    "channelIds",
    "commands",
    "routes",
)


@dataclass
class PluginsDiscoveryResult:
    payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _project_plugin(plugin: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key in PROJECTED_PLUGIN_FIELDS:
        if key in plugin:
            value = plugin[key]
            if key in {"source", "rootDir"} and isinstance(value, str):
                value = shorten_home(value)
            record[key] = value
    record["enabled"] = plugin.get("status") == "loaded" or bool(plugin.get("enabled"))
    record["governance_status"] = "undocumented"
    record["type"] = "connector" if plugin.get("format") == "connector" else "plugin"
    return record


def discover_plugins(
    config: GovernanceConfig,
    capabilities: CapabilitiesConfig,
) -> PluginsDiscoveryResult:
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []

    data, err = run_openclaw_json(
        ["plugins", "list", "--json"],
        timeout_seconds=config.discovery_cron_timeout_seconds,
    )
    plugins: list[dict[str, Any]] = []
    if err:
        warnings.append(err)
        errors.append({"phase": "plugins_list", "message": err})
    elif data:
        raw_plugins = data.get("plugins")
        if isinstance(raw_plugins, list):
            plugins = [_project_plugin(item) for item in raw_plugins if isinstance(item, dict)]

    apply_plugin_governance_statuses(
        plugins,
        expected=set(capabilities.expected_plugins),
        exempt=set(capabilities.exempt_plugins),
    )

    payload: dict[str, Any] = {
        "capabilities_schema_version": CAPABILITIES_SCHEMA_VERSION,
        "openclaw_home": str(config.openclaw_home),
        "openclaw_cli_version": openclaw_cli_version(),
        "plugins": plugins,
        "summary": summarize_statuses(plugins),
        "warnings": warnings,
        "errors": errors,
    }
    return PluginsDiscoveryResult(payload=payload, warnings=warnings, errors=errors)

"""Detect plugin-scoped agents for RACI broadcast defaults."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.openclaw_cli import run_openclaw_json

AGENT_GOVERNANCE_SCOPE_REFRESH_FIELDS = frozenset({"governance_scope", "raci_broadcast_excluded"})


def load_plugin_scope_index(
    config: GovernanceConfig,
) -> tuple[set[str], list[Path]]:
    """Return plugin ids and resolved root directories from OpenClaw CLI."""
    plugin_ids: set[str] = set()
    plugin_roots: list[Path] = []
    data, err = run_openclaw_json(
        ["plugins", "list", "--json"],
        timeout_seconds=config.discovery_cron_timeout_seconds,
    )
    if err:
        return plugin_ids, plugin_roots
    raw_plugins = data.get("plugins") if isinstance(data, dict) else None
    if not isinstance(raw_plugins, list):
        return plugin_ids, plugin_roots

    for plugin in raw_plugins:
        if not isinstance(plugin, dict):
            continue
        plugin_id = plugin.get("id")
        if isinstance(plugin_id, str) and plugin_id:
            plugin_ids.add(plugin_id)
        for key in ("rootDir", "source"):
            raw_root = plugin.get(key)
            if not isinstance(raw_root, str) or not raw_root.strip():
                continue
            try:
                plugin_roots.append(Path(raw_root).expanduser().resolve())
            except OSError:
                continue
            break
    return plugin_ids, plugin_roots


def is_plugin_scoped_agent(
    agent_id: str,
    workspace: str,
    plugin_ids: set[str],
    plugin_roots: list[Path],
) -> bool:
    if agent_id in plugin_ids:
        return True
    if not workspace:
        return False
    try:
        agent_workspace = Path(workspace).expanduser().resolve()
    except OSError:
        return False
    for root in plugin_roots:
        try:
            resolved_root = root.expanduser().resolve()
            agent_workspace.relative_to(resolved_root)
            return True
        except (ValueError, OSError):
            continue
    return False


def agent_explicitly_promoted_to_broadcast(entry: dict[str, Any]) -> bool:
    if entry.get("governance_scope") == "core":
        return True
    return entry.get("raci_broadcast_excluded") is False


def apply_plugin_scope_to_agent_entry(entry: dict[str, Any], *, plugin_scoped: bool) -> None:
    if not plugin_scoped:
        return
    entry["governance_scope"] = "plugin"
    entry["raci_broadcast_excluded"] = True

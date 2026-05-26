"""Shared helpers for OpenClaw workflow governance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

VALID_WORKFLOW_STATUSES = frozenset({"active", "required", "discovered", "implemented", "archived"})
VALID_RUNTIME_STATUSES = frozenset({"active", "manual", "disabled"})

# Minimal generic prefix rules; extend via governance.config.yaml domain_prefix_rules.
DEFAULT_DOMAIN_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("main.system_config_change_governance", "governance_registry"),
    ("main.workflow_registry_drift_check", "governance_registry"),
    ("main.cron.", "personal_ops"),
    ("main.", "personal_ops"),
)

CORE_PLATFORM_DOMAINS = frozenset({"platform_notion", "platform_google"})


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys instead of silently overwriting."""


def construct_mapping_without_duplicate_keys(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            line = key_node.start_mark.line + 1
            column = key_node.start_mark.column + 1
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r} at line {line}, column {column}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping_without_duplicate_keys
)


def load_registry(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle, Loader=UniqueKeyLoader)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return data


def agent_ids(registry: dict[str, Any]) -> list[str]:
    agents = registry.get("agents")
    if not isinstance(agents, list):
        return []
    ids: list[str] = []
    for entry in agents:
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            ids.append(entry["id"])
    return ids


def raci_domains(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    domains = registry.get("raci_domains")
    if not isinstance(domains, dict):
        return {}
    return {key: value for key, value in domains.items() if isinstance(value, dict)}


def agents_excluded_from_raci_broadcast(registry: dict[str, Any]) -> set[str]:
    excluded: set[str] = set()
    agents = registry.get("agents")
    if isinstance(agents, list):
        for entry in agents:
            if isinstance(entry, dict) and entry.get("raci_broadcast_excluded") is True:
                agent_id = entry.get("id")
                if isinstance(agent_id, str):
                    excluded.add(agent_id)
    extra = registry.get("raci_broadcast_excluded_agents")
    if isinstance(extra, list):
        excluded.update(str(item) for item in extra)
    return excluded


def agents_requiring_raci_broadcast(registry: dict[str, Any]) -> set[str]:
    return set(agent_ids(registry)) - agents_excluded_from_raci_broadcast(registry)


def explicit_workflow_domains(registry: dict[str, Any]) -> dict[str, str]:
    mapping = registry.get("raci_workflow_domains")
    if not isinstance(mapping, dict):
        return {}
    explicit = mapping.get("explicit")
    if not isinstance(explicit, dict):
        return {}
    return {str(key): str(value) for key, value in explicit.items()}


def resolve_workflow_raci_domain(
    workflow_id: str,
    registry: dict[str, Any],
    prefix_rules: tuple[tuple[str, str], ...] | None = None,
) -> str | None:
    explicit = explicit_workflow_domains(registry)
    if workflow_id in explicit:
        return explicit[workflow_id]

    rules = prefix_rules if prefix_rules is not None else DEFAULT_DOMAIN_PREFIX_RULES
    for prefix, domain in rules:
        if workflow_id.startswith(prefix) or workflow_id == prefix.rstrip("."):
            return domain
    return None


def resolve_workflow_raci(
    workflow: dict[str, Any],
    registry: dict[str, Any],
    prefix_rules: tuple[tuple[str, str], ...] | None = None,
) -> dict[str, Any] | None:
    if isinstance(workflow.get("raci"), dict):
        return workflow["raci"]

    domain_key = workflow.get("raci_domain")
    if not isinstance(domain_key, str):
        domain_key = resolve_workflow_raci_domain(str(workflow.get("id", "")), registry, prefix_rules)
    if not domain_key:
        return None

    domains = raci_domains(registry)
    domain = domains.get(domain_key)
    if not isinstance(domain, dict):
        return None

    return {
        "domain": domain_key,
        "responsible": domain.get("responsible"),
        "accountable": domain.get("accountable"),
        "consulted": list(domain.get("consulted") or []),
        "informed": list(domain.get("informed") or []),
    }


def normalize_party_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []

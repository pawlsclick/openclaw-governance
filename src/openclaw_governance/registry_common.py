"""Shared helpers for OpenClaw workflow governance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

VALID_WORKFLOW_STATUSES = frozenset(
    {"active", "required", "discovered", "deprecated", "implemented", "archived"}
)
VALID_RUNTIME_STATUSES = frozenset({"active", "manual", "disabled"})

# Minimal generic prefix rules; extend via governance.config.yaml domain_prefix_rules.
DEFAULT_DOMAIN_PREFIX_RULES: tuple[tuple[str, str], ...] = (
    ("main.system_config_change_governance", "governance_registry"),
    ("main.workflow_registry_drift_check", "governance_registry"),
    ("main.cron.", "personal_ops"),
    ("main.", "personal_ops"),
)


def agent_raci_domain_key(agent_id: str) -> str:
    """Default RACI domain for any discovered agent: normalize id + ``_ops`` suffix."""
    slug = agent_id.strip().replace("-", "_")
    return f"{slug}_ops"


def agent_domain_prefix_rules(agent_ids: list[str]) -> tuple[tuple[str, str], ...]:
    """Map ``{agent_id}.`` workflow prefixes to each agent's auto ops domain."""
    rules: list[tuple[str, str]] = []
    for agent_id in sorted(set(agent_ids)):
        if not agent_id:
            continue
        rules.append((f"{agent_id}.", agent_raci_domain_key(agent_id)))
    return tuple(rules)


def effective_domain_prefix_rules(
    config_rules: tuple[tuple[str, str], ...],
    registry: dict[str, Any],
) -> tuple[tuple[str, str], ...]:
    """Config/default rules first, then per-agent rules from registry agents."""
    return tuple(config_rules) + agent_domain_prefix_rules(agent_ids(registry))

CORE_PLATFORM_DOMAINS = frozenset({"platform_notion", "platform_google"})

DEFAULT_RECOGNIZED_WORKFLOW_PREFIXES: tuple[str, ...] = (
    "platform.",
    "workflow_registry.",
)


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
            if not isinstance(entry, dict):
                continue
            agent_id = entry.get("id")
            if not isinstance(agent_id, str) or not agent_id:
                continue
            if entry.get("governance_scope") == "core" or entry.get(
                "raci_broadcast_excluded"
            ) is False:
                continue
            if entry.get("raci_broadcast_excluded") is True:
                excluded.add(agent_id)
            elif (
                entry.get("governance_scope") == "plugin"
                and entry.get("raci_broadcast_excluded") is not False
            ):
                excluded.add(agent_id)
    extra = registry.get("raci_broadcast_excluded_agents")
    if isinstance(extra, list):
        excluded.update(str(item) for item in extra)
    return excluded


def agents_requiring_raci_broadcast(registry: dict[str, Any]) -> set[str]:
    return set(agent_ids(registry)) - agents_excluded_from_raci_broadcast(registry)


def agents_for_raci_broadcast(
    registry: dict[str, Any],
    config_excluded: list[str] | None = None,
) -> list[str]:
    """Agent ids that may appear in generated RACI informed lists."""
    excluded = agents_excluded_from_raci_broadcast(registry)
    if config_excluded:
        excluded.update(str(item) for item in config_excluded)
    return sorted(set(agent_ids(registry)) - excluded)


def platform_workflow_ids(registry: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    platform = registry.get("platform")
    if not isinstance(platform, dict):
        return ids
    for platform_config in platform.values():
        if not isinstance(platform_config, dict):
            continue
        raw = platform_config.get("workflows")
        if isinstance(raw, list):
            ids.update(str(item) for item in raw if item)
    return ids


def is_governed_workflow_id(
    workflow_id: str,
    registry: dict[str, Any],
    config: Any | None = None,
) -> bool:
    """True when discovery should not add a new generic row from runbook scan."""
    if workflow_id in platform_workflow_ids(registry):
        return True
    explicit = explicit_workflow_domains(registry)
    if workflow_id in explicit:
        return True
    prefixes = list(DEFAULT_RECOGNIZED_WORKFLOW_PREFIXES)
    if config is not None:
        extra = getattr(config, "discovery_recognized_workflow_prefixes", None)
        if isinstance(extra, list):
            prefixes.extend(str(item) for item in extra)
    for prefix in prefixes:
        if workflow_id.startswith(prefix) or workflow_id == prefix.rstrip("."):
            return True
    return False


def should_skip_runbook_proposal(
    workflow_id: str,
    registry: dict[str, Any],
    config: Any | None = None,
) -> bool:
    """True when an on-disk runbook should not create a new registry row."""
    if workflow_id in _workflow_index(registry):
        return True
    return is_governed_workflow_id(workflow_id, registry, config)


def _workflow_index(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    workflows = registry.get("workflows")
    if not isinstance(workflows, list):
        return {}
    return {
        str(item["id"]): item
        for item in workflows
        if isinstance(item, dict) and item.get("id")
    }


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


def ensure_raci_domains(
    registry: dict[str, Any],
    agent_ids_list: list[str],
    *,
    accountable: str = "Operator",
    config_excluded: list[str] | None = None,
    init_only: bool = False,
) -> None:
    """Merge default RACI domains into registry without overwriting operator edits."""
    current = registry.get("raci_domains")
    if not isinstance(current, dict):
        current = {}
    if init_only and current:
        return
    broadcast = agents_for_raci_broadcast(registry, config_excluded)
    if not broadcast and agent_ids_list:
        broadcast = [
            agent_id
            for agent_id in agent_ids_list
            if agent_id not in agents_excluded_from_raci_broadcast(registry)
            and agent_id not in set(config_excluded or [])
        ]
    defaults = default_raci_domains(broadcast, accountable=accountable)
    for key, value in defaults.items():
        if key not in current:
            current[key] = value
    registry["raci_domains"] = current


def default_raci_domains(
    broadcast_agent_ids: list[str],
    *,
    accountable: str = "Operator",
) -> dict[str, Any]:
    informed = sorted(set(broadcast_agent_ids))
    main_responsible = "main" if "main" in informed else (informed[0] if informed else "main")
    domains: dict[str, Any] = {
        "governance_registry": {
            "title": "Workflow registry, runbooks, and governance PRs",
            "responsible": main_responsible,
            "accountable": accountable,
            "consulted": [],
            "informed": [agent_id for agent_id in informed if agent_id != "main"],
        },
        "personal_ops": {
            "title": "Personal and workspace automations",
            "responsible": main_responsible,
            "accountable": accountable,
            "consulted": [],
            "informed": informed,
        },
    }
    orchestrator = "main" if "main" in informed else main_responsible
    for agent_id in informed:
        domain_key = agent_raci_domain_key(agent_id)
        if domain_key in domains:
            continue
        consulted = [orchestrator] if orchestrator != agent_id else []
        domains[domain_key] = {
            "title": f"{agent_id} agent workflows",
            "responsible": agent_id,
            "accountable": accountable,
            "consulted": consulted,
            "informed": [other for other in informed if other != agent_id],
        }
    return domains


def infer_workflow_raci_domain(
    workflow_id: str,
    agent_id: str,
    registry: dict[str, Any],
    prefix_rules: tuple[tuple[str, str], ...],
) -> str | None:
    """Resolve RACI domain for a workflow; returns None if no domain exists in registry."""
    domain_key = resolve_workflow_raci_domain(workflow_id, registry, prefix_rules)
    if not domain_key and agent_id:
        domain_key = agent_raci_domain_key(agent_id)
    if not domain_key:
        return None
    if domain_key in raci_domains(registry):
        return domain_key
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

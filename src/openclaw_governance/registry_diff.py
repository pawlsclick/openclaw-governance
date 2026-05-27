"""Semantic diff for registry.yaml to avoid no-op rewrites."""

from __future__ import annotations

import json
from typing import Any


def _normalize(value: Any) -> Any:
    return json.loads(json.dumps(value, sort_keys=True, default=str))


def registry_semantic_diff(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Return whether registry content changed and a compact summary."""
    changes: dict[str, Any] = {
        "changed": False,
        "workflows": [],
        "agents": [],
        "raci_domains": [],
        "top_level": [],
    }

    skip_keys = frozenset({"generated_at"})
    for key in sorted(set(before) | set(after)):
        if key in skip_keys:
            continue
        if key in {"workflows", "agents", "raci_domains"}:
            continue
        if _normalize(before.get(key)) != _normalize(after.get(key)):
            changes["top_level"].append(key)
            changes["changed"] = True

    before_agents = {
        str(item["id"]): item
        for item in (before.get("agents") or [])
        if isinstance(item, dict) and item.get("id")
    }
    after_agents = {
        str(item["id"]): item
        for item in (after.get("agents") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for agent_id in sorted(set(before_agents) | set(after_agents)):
        if _normalize(before_agents.get(agent_id)) != _normalize(after_agents.get(agent_id)):
            changes["agents"].append(agent_id)
            changes["changed"] = True

    before_domains = before.get("raci_domains") if isinstance(before.get("raci_domains"), dict) else {}
    after_domains = after.get("raci_domains") if isinstance(after.get("raci_domains"), dict) else {}
    for domain_key in sorted(set(before_domains) | set(after_domains)):
        if _normalize(before_domains.get(domain_key)) != _normalize(after_domains.get(domain_key)):
            changes["raci_domains"].append(domain_key)
            changes["changed"] = True

    before_workflows = {
        str(item["id"]): item
        for item in (before.get("workflows") or [])
        if isinstance(item, dict) and item.get("id")
    }
    after_workflows = {
        str(item["id"]): item
        for item in (after.get("workflows") or [])
        if isinstance(item, dict) and item.get("id")
    }
    for workflow_id in sorted(set(before_workflows) | set(after_workflows)):
        if _normalize(before_workflows.get(workflow_id)) != _normalize(after_workflows.get(workflow_id)):
            changes["workflows"].append(workflow_id)
            changes["changed"] = True

    return changes

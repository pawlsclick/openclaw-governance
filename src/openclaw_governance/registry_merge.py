"""Registry and governance root merge helpers for discover and adopt."""

from __future__ import annotations

from typing import Any

from openclaw_governance.registry_common import VALID_WORKFLOW_STATUSES

# Operator-promoted workflows: discover must not overwrite hand-authored fields.
PROTECTED_WORKFLOW_STATUSES = frozenset({"active", "required", "deprecated", "implemented", "archived"})

CRON_DISCOVERY_REFRESH_FIELDS = (
    "agent",
    "purpose",
    "trigger",
    "orchestration",
    "success_criteria",
    "failure_modes",
    "tests",
    "discovered_from",
    "cron_fingerprint",
)


def merge_agents(
    existing: list[dict[str, Any]],
    proposed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge agent entries; preserve hand-authored fields from existing rows."""
    by_id: dict[str, dict[str, Any]] = {}
    for item in existing:
        if isinstance(item, dict) and item.get("id"):
            by_id[str(item["id"])] = dict(item)

    for item in proposed:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        agent_id = str(item["id"])
        if agent_id in by_id:
            current = by_id[agent_id]
            for key, value in item.items():
                if key in {"workspace", "name", "role"}:
                    current[key] = value
                elif key not in current:
                    current[key] = value
        else:
            by_id[agent_id] = dict(item)

    return sorted(by_id.values(), key=lambda entry: str(entry.get("id", "")))


def merge_raci_domains(
    target: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, int]:
    """Merge raci_domains from source into target without dropping target domains."""
    counts = {"added": 0, "preserved": 0}
    current = target.get("raci_domains")
    if not isinstance(current, dict):
        current = {}
        target["raci_domains"] = current

    incoming = source.get("raci_domains")
    if not isinstance(incoming, dict):
        return counts

    for key, domain in incoming.items():
        if key in current:
            counts["preserved"] += 1
            continue
        current[key] = domain
        counts["added"] += 1
    return counts


def merge_workflows(
    existing: list[dict[str, Any]],
    proposed: list[dict[str, Any]],
    *,
    staged: bool = False,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    """Merge proposed workflows into existing registry rows."""
    by_id = {str(item.get("id")): item for item in existing if isinstance(item, dict) and item.get("id")}
    by_fingerprint: dict[str, str] = {}
    for workflow_id, workflow in by_id.items():
        if not isinstance(workflow, dict):
            continue
        fp = workflow.get("cron_fingerprint") or (workflow.get("discovered_from") or {}).get(
            "cron_fingerprint"
        )
        if isinstance(fp, str) and fp:
            by_fingerprint[fp] = workflow_id

    created: list[str] = []
    updated: list[str] = []
    skipped_protected: list[str] = []

    for workflow in proposed:
        workflow_id = str(workflow.get("id"))
        fingerprint = workflow.get("cron_fingerprint")
        if isinstance(fingerprint, str) and fingerprint in by_fingerprint:
            workflow_id = by_fingerprint[fingerprint]
            workflow = {**workflow, "id": workflow_id}

        if workflow_id in by_id:
            current = by_id[workflow_id]
            status = str(current.get("status", "discovered"))
            if staged and status in PROTECTED_WORKFLOW_STATUSES:
                if workflow.get("runtime_status"):
                    current["runtime_status"] = workflow["runtime_status"]
                skipped_protected.append(workflow_id)
                continue

            if workflow.get("cron_job_ids"):
                current["cron_job_ids"] = workflow["cron_job_ids"]
            if workflow.get("cron_fingerprint"):
                current["cron_fingerprint"] = workflow["cron_fingerprint"]
            if (
                workflow.get("orchestration") == "openclaw_cron"
                and workflow.get("runtime_status")
            ):
                if current.get("orchestration") != "openclaw_cron":
                    for field in CRON_DISCOVERY_REFRESH_FIELDS:
                        if field in workflow:
                            current[field] = workflow[field]
                current["runtime_status"] = workflow["runtime_status"]
            updated.append(workflow_id)
        else:
            if staged:
                workflow = dict(workflow)
                workflow["status"] = "discovered"
            if not str(workflow.get("status")):
                workflow["status"] = "discovered"
            status = str(workflow.get("status"))
            if status not in VALID_WORKFLOW_STATUSES:
                workflow["status"] = "discovered"
            by_id[workflow_id] = workflow
            fp = workflow.get("cron_fingerprint")
            if isinstance(fp, str) and fp:
                by_fingerprint[fp] = workflow_id
            created.append(workflow_id)

    merged = sorted(by_id.values(), key=lambda item: str(item.get("id", "")))
    return merged, created, updated, skipped_protected


def merge_registry_for_adopt(
    target: dict[str, Any],
    source: dict[str, Any],
) -> dict[str, Any]:
    """Merge source registry into target for adopt; preserve promoted workflows."""
    target_workflows = target.get("workflows")
    if not isinstance(target_workflows, list):
        target_workflows = []
    source_workflows = source.get("workflows")
    if not isinstance(source_workflows, list):
        source_workflows = []

    merged_workflows, created, updated, skipped = merge_workflows(
        target_workflows,
        source_workflows,
        staged=True,
    )
    target["workflows"] = merged_workflows

    target_agents = target.get("agents")
    if not isinstance(target_agents, list):
        target_agents = []
    source_agents = source.get("agents")
    if not isinstance(source_agents, list):
        source_agents = []
    target["agents"] = merge_agents(target_agents, source_agents)

    domain_counts = merge_raci_domains(target, source)

    return {
        "workflows_created": created,
        "workflows_updated": updated,
        "workflows_skipped_protected": skipped,
        "raci_domains_added": domain_counts["added"],
        "raci_domains_preserved": domain_counts["preserved"],
    }

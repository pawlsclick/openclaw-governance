"""Registry and governance root merge helpers for discover and adopt."""

from __future__ import annotations

from typing import Any

from openclaw_governance.registry_common import VALID_WORKFLOW_STATUSES

# Operator-promoted workflows: discover must not overwrite hand-authored fields.
PROTECTED_WORKFLOW_STATUSES = frozenset({"active", "required", "deprecated", "implemented", "archived"})


def _workflow_fingerprints(workflow: dict[str, Any]) -> list[str]:
    """Collect all cron fingerprints referenced by a workflow row."""
    found: list[str] = []
    raw = workflow.get("cron_fingerprint")
    if isinstance(raw, str) and raw:
        found.append(raw)
    elif isinstance(raw, list):
        found.extend(str(item) for item in raw if item)

    discovered = workflow.get("discovered_from")
    if isinstance(discovered, dict):
        nested = discovered.get("cron_fingerprint")
        if isinstance(nested, str) and nested:
            found.append(nested)
        elif isinstance(nested, list):
            found.extend(str(item) for item in nested if item)
        instances = discovered.get("cron_instances")
        if isinstance(instances, list):
            for instance in instances:
                if isinstance(instance, dict):
                    fp = instance.get("fingerprint")
                    if isinstance(fp, str) and fp:
                        found.append(fp)
    return sorted(set(found))


def _union_cron_job_ids(current: dict[str, Any], incoming: dict[str, Any]) -> None:
    existing_ids = list(current.get("cron_job_ids") or [])
    for job_id in incoming.get("cron_job_ids") or []:
        if job_id and job_id not in existing_ids:
            existing_ids.append(job_id)
    if existing_ids:
        current["cron_job_ids"] = existing_ids

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
    *,
    source_overwrites: bool = False,
) -> dict[str, int]:
    """Merge raci_domains from source into target without dropping target domains."""
    counts = {"added": 0, "preserved": 0, "overwritten": 0}
    current = target.get("raci_domains")
    if not isinstance(current, dict):
        current = {}
        target["raci_domains"] = current

    incoming = source.get("raci_domains")
    if not isinstance(incoming, dict):
        return counts

    for key, domain in incoming.items():
        if key in current:
            if source_overwrites and current[key] != domain:
                current[key] = domain
                counts["overwritten"] += 1
            else:
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
        for fp in _workflow_fingerprints(workflow):
            by_fingerprint[fp] = workflow_id

    created: list[str] = []
    updated: list[str] = []
    skipped_protected: list[str] = []

    for workflow in proposed:
        workflow_id = str(workflow.get("id"))
        for fp in _workflow_fingerprints(workflow):
            if fp in by_fingerprint:
                workflow_id = by_fingerprint[fp]
                workflow = {**workflow, "id": workflow_id}
                break

        if workflow_id in by_id:
            current = by_id[workflow_id]
            status = str(current.get("status", "discovered"))
            if staged and status in PROTECTED_WORKFLOW_STATUSES:
                if workflow.get("runtime_status"):
                    current["runtime_status"] = workflow["runtime_status"]
                skipped_protected.append(workflow_id)
                continue

            _union_cron_job_ids(current, workflow)
            if workflow.get("cron_fingerprint"):
                current["cron_fingerprint"] = workflow["cron_fingerprint"]
            discovered = workflow.get("discovered_from")
            if isinstance(discovered, dict) and discovered.get("cron_instances"):
                current_discovered = current.get("discovered_from")
                if not isinstance(current_discovered, dict):
                    current_discovered = {}
                    current["discovered_from"] = current_discovered
                current_discovered["cron_instances"] = discovered["cron_instances"]
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
            for fp in _workflow_fingerprints(workflow):
                by_fingerprint[fp] = workflow_id
            created.append(workflow_id)

    merged = sorted(by_id.values(), key=lambda item: str(item.get("id", "")))
    return merged, created, updated, skipped_protected


def merge_registry_for_adopt(
    target: dict[str, Any],
    source: dict[str, Any],
    *,
    source_authoritative: bool = True,
) -> dict[str, Any]:
    """Merge source registry into target for adopt; preserve promoted workflows."""
    sections_copied: list[str] = []
    sections_merged: list[str] = []
    sections_skipped: list[str] = []

    reserved = frozenset({"workflows", "agents", "raci_domains"})
    for key, value in source.items():
        if key in reserved:
            continue
        if source_authoritative:
            target[key] = value
            sections_copied.append(key)
        elif key not in target:
            target[key] = value
            sections_copied.append(key)
        else:
            sections_skipped.append(key)

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
    sections_merged.append("workflows")

    target_agents = target.get("agents")
    if not isinstance(target_agents, list):
        target_agents = []
    source_agents = source.get("agents")
    if not isinstance(source_agents, list):
        source_agents = []
    target["agents"] = merge_agents(target_agents, source_agents)
    sections_merged.append("agents")

    domain_counts = merge_raci_domains(
        target,
        source,
        source_overwrites=source_authoritative,
    )
    sections_merged.append("raci_domains")

    return {
        "workflows_created": created,
        "workflows_updated": updated,
        "workflows_skipped_protected": skipped,
        "raci_domains_added": domain_counts["added"],
        "raci_domains_preserved": domain_counts["preserved"],
        "raci_domains_overwritten": domain_counts.get("overwritten", 0),
        "sections_copied": sections_copied,
        "sections_merged": sections_merged,
        "sections_skipped": sections_skipped,
    }

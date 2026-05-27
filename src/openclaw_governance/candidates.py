"""Discovery candidate classification and promotion reports (non-destructive staged review)."""

from __future__ import annotations

from typing import Any

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import DiscoveryResult
from openclaw_governance.registry_common import (
    agents_excluded_from_raci_broadcast,
    agents_for_raci_broadcast,
    default_raci_domains,
    raci_domains,
    _workflow_index,
)
from openclaw_governance.registry_merge import PROTECTED_WORKFLOW_STATUSES, _workflow_fingerprints

CANDIDATE_CLASSES = frozenset(
    {
        "missing_active_cron",
        "workspace_runbook_candidate",
        "possible_duplicate",
        "protected_existing_changed",
        "unsafe_raci_generated",
    }
)

PROTECTED_WORKFLOW_KEYS = frozenset(
    {
        "title",
        "purpose",
        "status",
        "runtime_status",
        "raci",
        "raci_domain",
        "runbook",
    }
)


def _append_candidate(candidates: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    candidate_class = entry.get("class")
    if candidate_class not in CANDIDATE_CLASSES:
        raise ValueError(f"invalid candidate class: {candidate_class!r}")
    candidates.append(entry)


def _fingerprint_to_workflow_id(registry: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for workflow_id, workflow in _workflow_index(registry).items():
        for fp in _workflow_fingerprints(workflow):
            mapping[fp] = workflow_id
    return mapping


def _protected_field_changes(
    current: dict[str, Any],
    proposed: dict[str, Any],
) -> list[str]:
    changes: list[str] = []
    for key in PROTECTED_WORKFLOW_KEYS:
        if key not in proposed:
            continue
        if current.get(key) != proposed.get(key):
            changes.append(key)
    return changes


def _unsafe_raci_informed_additions(
    registry: dict[str, Any],
    proposed_domains: dict[str, Any],
    config: GovernanceConfig,
) -> list[dict[str, Any]]:
    """Detect new RACI domains that would inform broadcast-excluded agents."""
    excluded = agents_excluded_from_raci_broadcast(registry)
    excluded.update(config.raci_broadcast_excluded)
    current = raci_domains(registry)
    issues: list[dict[str, Any]] = []
    for domain_key, domain in proposed_domains.items():
        if domain_key in current:
            continue
        if not isinstance(domain, dict):
            continue
        informed = domain.get("informed")
        if not isinstance(informed, list):
            continue
        bad = sorted({str(item) for item in informed if str(item) in excluded})
        if bad:
            issues.append({"domain": domain_key, "excluded_agents_in_informed": bad})
    return issues


def build_discovery_candidates(
    result: DiscoveryResult,
    registry: dict[str, Any],
    proposed_workflows: list[dict[str, Any]],
    config: GovernanceConfig,
    *,
    warnings: list[str] | None = None,
    skipped_runbook_proposals: list[str] | None = None,
) -> dict[str, Any]:
    """Classify discovery findings without mutating registry."""
    warn = warnings if warnings is not None else list(result.warnings)
    candidates: list[dict[str, Any]] = []
    by_id = _workflow_index(registry)
    fp_map = _fingerprint_to_workflow_id(registry)

    for warning in warn:
        if "EXACT DUPLICATE CRON" in warning:
            _append_candidate(
                candidates,
                {
                    "class": "possible_duplicate",
                    "workflow_id": None,
                    "detail": warning,
                },
            )

    for workflow in proposed_workflows:
        workflow_id = str(workflow.get("id", ""))
        if not workflow_id:
            continue

        existing = by_id.get(workflow_id)
        if existing is None:
            for fp in _workflow_fingerprints(workflow):
                if fp in fp_map and fp_map[fp] != workflow_id:
                    _append_candidate(
                        candidates,
                        {
                            "class": "possible_duplicate",
                            "workflow_id": workflow_id,
                            "detail": f"Fingerprint {fp} already maps to {fp_map[fp]}",
                        },
                    )
                    break
            orchestration = workflow.get("orchestration")
            if orchestration == "openclaw_cron":
                _append_candidate(
                    candidates,
                    {
                        "class": "missing_active_cron",
                        "workflow_id": workflow_id,
                        "detail": "Live cron with no registry workflow row",
                        "agent": workflow.get("agent"),
                        "runtime_status": workflow.get("runtime_status"),
                    },
                )
            elif workflow.get("discovered_from", {}).get("source") == "workspace_runbook":
                _append_candidate(
                    candidates,
                    {
                        "class": "workspace_runbook_candidate",
                        "workflow_id": workflow_id,
                        "detail": "Workspace runbook not yet in registry",
                        "target_runbook": workflow.get("runbook"),
                    },
                )
            elif workflow.get("discovered_from", {}).get("source") == "runbook_on_disk":
                _append_candidate(
                    candidates,
                    {
                        "class": "workspace_runbook_candidate",
                        "workflow_id": workflow_id,
                        "detail": "Governance runbook on disk without registry row",
                        "runbook": workflow.get("runbook"),
                    },
                )
            continue

        status = str(existing.get("status", "discovered"))
        if status in PROTECTED_WORKFLOW_STATUSES:
            blocked = _protected_field_changes(existing, workflow)
            if blocked:
                _append_candidate(
                    candidates,
                    {
                        "class": "protected_existing_changed",
                        "workflow_id": workflow_id,
                        "detail": f"Discovery would change protected fields: {', '.join(blocked)}",
                        "blocked_fields": blocked,
                        "status": status,
                    },
                )

    broadcast = agents_for_raci_broadcast(registry, config.raci_broadcast_excluded)
    proposed_domains = default_raci_domains(
        broadcast,
        accountable=config.accountable_humans[0] if config.accountable_humans else "Operator",
    )
    for issue in _unsafe_raci_informed_additions(registry, proposed_domains, config):
        _append_candidate(
            candidates,
            {
                "class": "unsafe_raci_generated",
                "workflow_id": None,
                "detail": "Proposed RACI domain would inform broadcast-excluded agents",
                **issue,
            },
        )

    skipped = sorted(set(skipped_runbook_proposals or []))

    return {
        "generated_at": result.generated_at,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "broadcast_agents": broadcast,
        "skipped_runbook_proposals": skipped,
    }


def filter_proposed_by_allowlist(
    proposed_workflows: list[dict[str, Any]],
    allowlist: set[str],
) -> list[dict[str, Any]]:
    return [workflow for workflow in proposed_workflows if str(workflow.get("id")) in allowlist]

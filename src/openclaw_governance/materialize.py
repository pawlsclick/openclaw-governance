"""Write registry entries and runbook stubs from discovery results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import DiscoveryResult, workflow_id_for_cron
from openclaw_governance.registry_common import UniqueKeyLoader, construct_mapping_without_duplicate_keys, load_registry

UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping_without_duplicate_keys
)


def runbook_path_for(workflow_id: str) -> str:
    return f"workflows/runbooks/{workflow_id}.md"


def render_runbook_stub(
    *,
    workflow_id: str,
    agent_id: str,
    title: str,
    cron_job_ids: list[str],
    schedule: str,
    message_preview: str,
    enabled: bool,
) -> str:
    runtime = "active" if enabled else "disabled"
    lines = [
        f"# {title}",
        "",
        f"Workflow ID: `{workflow_id}`  ",
        f"Agent: `{agent_id}`  ",
        "Status: discovered",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} (openclaw-gov discover)",
        "",
        "## Purpose",
        "",
        "Auto-generated runbook stub. Replace this section with the real operational purpose after verification.",
        "",
        f"Cron job ids: {', '.join(f'`{job_id}`' for job_id in cron_job_ids) if cron_job_ids else '—'}",
        "",
        "## Trigger",
        "",
        f"- Schedule: `{schedule or 'unknown'}`",
        f"- Runtime status when discovered: `{runtime}`",
        "",
        "## Payload preview",
        "",
        "```text",
        message_preview or "(empty)",
        "```",
        "",
        "## Verification",
        "",
        "Add commands that prove this workflow is healthy. Example:",
        "",
        "```bash",
        f"openclaw cron list --agent {agent_id} --json",
        "```",
        "",
        "## Expected healthy state",
        "",
        "- Cron job exists and is enabled (if applicable).",
        "- Last run completed without error (document where to check).",
        "",
        "## Failure modes",
        "",
        "- TBD after operator review.",
        "",
        "## Recovery",
        "",
        "- TBD after operator review.",
        "",
    ]
    return "\n".join(lines)


def default_code_management() -> dict[str, Any]:
    return {
        "repo_decision": "tbd",
        "repo_url": "",
        "notes": "Set after deciding where durable workflow code belongs.",
    }


def workflow_entry_from_cron(
    agent_id: str,
    job: Any,
    config: GovernanceConfig,
) -> dict[str, Any]:
    workflow_id = workflow_id_for_cron(agent_id, job.name)
    runbook = runbook_path_for(workflow_id)
    runtime_status = "active" if job.enabled else "disabled"
    return {
        "id": workflow_id,
        "agent": agent_id,
        "title": job.name.replace("_", " ").replace("-", " ").title(),
        "status": "discovered",
        "purpose": f"Discovered OpenClaw cron job `{job.name}` for agent `{agent_id}`.",
        "trigger": f"cron/openclaw_cron ({job.schedule or 'schedule unknown'})",
        "orchestration": "openclaw_cron",
        "inputs": [],
        "outputs": [],
        "tools_or_scripts": [],
        "source_docs": [],
        "cron_job_ids": [job.job_id] if job.job_id else [],
        "risk_level": "low",
        "approval_required": False,
        "success_criteria": ["Cron job runs on schedule without error (verify and refine)."],
        "failure_modes": ["Cron disabled or payload references stale paths (verify after promotion)."],
        "tests": [f"openclaw cron list --agent {agent_id} --json"],
        "runbook": runbook,
        "runtime_status": runtime_status,
        "code_management": default_code_management(),
        "discovered_from": {
            "source": "openclaw-gov discover",
            "cron_name": job.name,
            "message_preview": job.message_preview,
        },
    }


def agents_registry_entries(result: DiscoveryResult, config: GovernanceConfig) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for agent in result.agents:
        entry: dict[str, Any] = {
            "id": agent.agent_id,
            "name": agent.name,
            "role": agent.role,
            "workspace": agent.workspace,
        }
        if agent.agent_id in config.raci_broadcast_excluded:
            entry["raci_broadcast_excluded"] = True
        if agent.git_repos:
            entry["repositories"] = agent.git_repos
        entries.append(entry)
    return entries


def default_raci_domains(agent_ids_list: list[str]) -> dict[str, Any]:
    informed = sorted(set(agent_ids_list))
    return {
        "governance_registry": {
            "title": "Workflow registry, runbooks, and governance PRs",
            "responsible": "main" if "main" in informed else (informed[0] if informed else "main"),
            "accountable": "Operator",
            "consulted": [],
            "informed": [agent_id for agent_id in informed if agent_id != "main"],
        },
        "personal_ops": {
            "title": "Personal and workspace automations",
            "responsible": "main" if "main" in informed else (informed[0] if informed else "main"),
            "accountable": "Operator",
            "consulted": [],
            "informed": informed,
        },
    }


def merge_workflows(
    existing: list[dict[str, Any]],
    proposed: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    by_id = {str(item.get("id")): item for item in existing if isinstance(item, dict) and item.get("id")}
    created: list[str] = []
    updated: list[str] = []

    for workflow in proposed:
        workflow_id = str(workflow.get("id"))
        if workflow_id in by_id:
            current = by_id[workflow_id]
            # Preserve operator edits; refresh cron ids and runtime from discovery.
            if workflow.get("cron_job_ids"):
                current["cron_job_ids"] = workflow["cron_job_ids"]
            if workflow.get("runtime_status"):
                current["runtime_status"] = workflow["runtime_status"]
            updated.append(workflow_id)
        else:
            by_id[workflow_id] = workflow
            created.append(workflow_id)

    merged = sorted(by_id.values(), key=lambda item: str(item.get("id", "")))
    return merged, created, updated


def materialize_from_discovery(
    result: DiscoveryResult,
    config: GovernanceConfig,
    *,
    write: bool = False,
) -> dict[str, Any]:
    """Build or update registry + runbooks. Returns summary dict."""
    summary: dict[str, Any] = {
        "write": write,
        "created_workflows": [],
        "updated_workflows": [],
        "created_runbooks": [],
        "skipped_runbooks": [],
    }

    proposed_workflows: list[dict[str, Any]] = []
    for agent in result.agents:
        for job in agent.cron_jobs:
            proposed_workflows.append(workflow_entry_from_cron(agent.agent_id, job, config))

    registry_path = config.registry_path
    if registry_path.is_file():
        registry = load_registry(registry_path)
    else:
        registry = {
            "generated_at": result.generated_at,
            "version": 0.1,
            "source_note": "Initialized by openclaw-gov discover",
            "agents": [],
            "raci_domains": {},
            "workflows": [],
        }

    registry["generated_at"] = result.generated_at
    registry["agents"] = agents_registry_entries(result, config)
    agent_id_list = [entry["id"] for entry in registry["agents"]]
    if not registry.get("raci_domains"):
        registry["raci_domains"] = default_raci_domains(agent_id_list)

    existing_workflows = registry.get("workflows")
    if not isinstance(existing_workflows, list):
        existing_workflows = []

    merged, created, updated = merge_workflows(existing_workflows, proposed_workflows)
    registry["workflows"] = merged
    summary["created_workflows"] = created
    summary["updated_workflows"] = updated

    if not write:
        summary["would_write_registry"] = str(registry_path)
        summary["proposed_workflow_count"] = len(proposed_workflows)
        return summary

    config.runbooks_dir.mkdir(parents=True, exist_ok=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    for workflow in proposed_workflows:
        workflow_id = str(workflow["id"])
        runbook_rel = runbook_path_for(workflow_id)
        runbook_file = config.governance_root / runbook_rel
        if runbook_file.is_file():
            summary["skipped_runbooks"].append(runbook_rel)
            continue

        agent_id = str(workflow.get("agent", ""))
        job = next(
            (
                cron
                for agent in result.agents
                if agent.agent_id == agent_id
                for cron in agent.cron_jobs
                if workflow_id_for_cron(agent_id, cron.name) == workflow_id
            ),
            None,
        )
        runbook_file.write_text(
            render_runbook_stub(
                workflow_id=workflow_id,
                agent_id=agent_id,
                title=str(workflow.get("title", workflow_id)),
                cron_job_ids=list(workflow.get("cron_job_ids") or []),
                schedule=job.schedule if job else "",
                message_preview=job.message_preview if job else "",
                enabled=job.enabled if job else True,
            ),
            encoding="utf-8",
        )
        summary["created_runbooks"].append(runbook_rel)

    with registry_path.open("w", encoding="utf-8") as handle:
        yaml.dump(registry, handle, sort_keys=False, allow_unicode=True)

    inventory_path = config.governance_root / "workflows" / "discovered-inventory.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
    summary["inventory_path"] = str(inventory_path)
    summary["registry_path"] = str(registry_path)
    return summary

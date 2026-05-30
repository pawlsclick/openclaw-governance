"""Write registry entries and runbook stubs from discovery results."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import (
    DiscoveredAgent,
    DiscoveredRunbook,
    DiscoveredWorkspaceRunbook,
    DiscoveryResult,
    cron_instance_group_id,
    format_schedule_label,
    scan_runbooks_on_disk,
    workflow_id_for_cron,
)
from openclaw_governance.governance_scaffold import ensure_governance_scaffold
from openclaw_governance.runbook_import import render_imported_runbook
from openclaw_governance.candidates import (
    build_discovery_candidates,
    filter_proposed_by_allowlist,
)
from openclaw_governance.discover_plugins import discover_plugins
from openclaw_governance.discover_skills import discover_skills
from openclaw_governance.inventory_artifacts import write_capability_artifacts
from openclaw_governance.registry_diff import registry_semantic_diff
from openclaw_governance.registry_merge import (
    PROTECTED_WORKFLOW_STATUSES,
    merge_agents,
    merge_workflows,
)
from openclaw_governance.registry_common import (
    UniqueKeyLoader,
    construct_mapping_without_duplicate_keys,
    effective_domain_prefix_rules,
    ensure_raci_domains,
    infer_workflow_raci_domain,
    load_registry,
    should_skip_runbook_proposal,
)

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
    schedule: Any,
    message_preview: str,
    enabled: bool,
) -> str:
    runtime = "active" if enabled else "disabled"
    schedule_label = format_schedule_label(schedule)
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
        f"- Schedule: `{schedule_label}`",
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


def workflow_entry_from_runbook(
    runbook: DiscoveredRunbook,
    *,
    workspace_source: DiscoveredWorkspaceRunbook | None = None,
) -> dict[str, Any]:
    discovered_from: dict[str, Any] = {
        "source": "runbook_on_disk",
        "path": runbook.path,
    }
    purpose = f"Discovered existing runbook `{runbook.runbook}`. Review and promote to active when verified."
    if workspace_source is not None:
        discovered_from = {
            "source": "workspace_runbook",
            "path": workspace_source.source_path,
            "workspace_relative": workspace_source.workspace_relative,
        }
        purpose = (
            f"Imported workspace runbook `{workspace_source.workspace_relative}` into `{runbook.runbook}`."
        )
    return {
        "id": runbook.workflow_id,
        "agent": runbook.agent_id,
        "title": runbook.title,
        "status": "discovered",
        "purpose": purpose,
        "trigger": "see runbook (discovered on disk)",
        "orchestration": "unknown",
        "inputs": [],
        "outputs": [],
        "tools_or_scripts": [],
        "source_docs": [runbook.runbook, workspace_source.source_path] if workspace_source else [runbook.runbook],
        "cron_job_ids": [],
        "risk_level": "low",
        "approval_required": False,
        "success_criteria": ["Runbook documents verification steps (review and refine)."],
        "failure_modes": ["Registry entry out of sync with runbook (re-run discover --write)."],
        "tests": [],
        "runbook": runbook.runbook,
        "runtime_status": "manual",
        "code_management": default_code_management(),
        "discovered_from": discovered_from,
    }


def import_workspace_runbooks(
    workspace_runbooks: list[DiscoveredWorkspaceRunbook],
    config: GovernanceConfig,
) -> dict[str, list[str]]:
    """Convert workspace runbooks into the governance runbooks directory."""
    summary: dict[str, list[str]] = {
        "imported_runbooks": [],
        "skipped_imported_runbooks": [],
    }
    if not workspace_runbooks:
        return summary

    config.runbooks_dir.mkdir(parents=True, exist_ok=True)
    for item in workspace_runbooks:
        dest = config.governance_root / item.target_runbook
        if dest.is_file():
            summary["skipped_imported_runbooks"].append(item.target_runbook)
            continue
        source_path = Path(item.source_path)
        body = source_path.read_text(encoding="utf-8")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            render_imported_runbook(
                workflow_id=item.workflow_id,
                agent_id=item.agent_id,
                title=item.title,
                source_path=source_path,
                source_body=body,
            ),
            encoding="utf-8",
        )
        summary["imported_runbooks"].append(item.target_runbook)
    return summary


def workflow_entry_from_cron_group(
    agent_id: str,
    jobs: list[Any],
    config: GovernanceConfig,
) -> dict[str, Any]:
    """One registry workflow per (agent, name, schedule) with all matching cron_job_ids."""
    if not jobs:
        raise ValueError("workflow_entry_from_cron_group requires at least one cron job")
    primary = jobs[0]
    workflow_id = workflow_id_for_cron(agent_id, primary.name)
    runbook = runbook_path_for(workflow_id)
    any_enabled = any(job.enabled for job in jobs)
    runtime_status = "active" if any_enabled else "disabled"
    job_ids = sorted({job.job_id for job in jobs if job.job_id})
    fingerprints = sorted({job.fingerprint for job in jobs if job.fingerprint})
    cron_instances = [
        {"job_id": job.job_id, "fingerprint": job.fingerprint}
        for job in jobs
        if job.fingerprint or job.job_id
    ]
    purpose = f"Discovered OpenClaw cron job `{primary.name}` for agent `{agent_id}`."
    if len(jobs) > 1:
        purpose = (
            f"Discovered {len(jobs)} related cron instances for `{primary.name}` "
            f"(agent `{agent_id}`); same name and schedule, distinct payloads."
        )
    return {
        "id": workflow_id,
        "agent": agent_id,
        "title": primary.name.replace("_", " ").replace("-", " ").title(),
        "status": "discovered",
        "purpose": purpose,
        "trigger": f"cron/openclaw_cron ({format_schedule_label(primary.schedule)})",
        "orchestration": "openclaw_cron",
        "inputs": [],
        "outputs": [],
        "tools_or_scripts": [],
        "source_docs": [],
        "cron_job_ids": job_ids,
        "risk_level": "low",
        "approval_required": False,
        "success_criteria": ["Cron job runs on schedule without error (verify and refine)."],
        "failure_modes": ["Cron disabled or payload references stale paths (verify after promotion)."],
        "tests": [f"openclaw cron list --agent {agent_id} --json"],
        "runbook": runbook,
        "runtime_status": runtime_status,
        "code_management": default_code_management(),
        "cron_fingerprint": fingerprints[0] if len(fingerprints) == 1 else fingerprints,
        "discovered_from": {
            "source": "openclaw-gov discover",
            "cron_name": primary.name,
            "message_preview": primary.message_preview,
            "cron_fingerprint": fingerprints[0] if len(fingerprints) == 1 else fingerprints,
            "cron_instances": cron_instances,
            "instance_group_id": primary.group_id
            or cron_instance_group_id(agent_id, primary.name, primary.schedule),
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


def discovery_result_for_allowlist(
    result: DiscoveryResult,
    allowlist: set[str],
) -> DiscoveryResult:
    """Return a copy of discovery data limited to allowlisted workflow ids (materialization only)."""
    filtered_agents: list[DiscoveredAgent] = []
    for agent in result.agents:
        filtered_jobs = [
            job
            for job in agent.cron_jobs
            if workflow_id_for_cron(agent.agent_id, job.name) in allowlist
        ]
        filtered_agents.append(
            DiscoveredAgent(
                agent_id=agent.agent_id,
                name=agent.name,
                role=agent.role,
                workspace=agent.workspace,
                cron_jobs=filtered_jobs,
                git_repos=list(agent.git_repos),
                script_paths=list(agent.script_paths),
            )
        )
    return DiscoveryResult(
        generated_at=result.generated_at,
        openclaw_home=result.openclaw_home,
        openclaw_config_path=result.openclaw_config_path,
        agents=filtered_agents,
        runbooks=[rb for rb in result.runbooks if rb.workflow_id in allowlist],
        workspace_runbooks=[
            item for item in result.workspace_runbooks if item.workflow_id in allowlist
        ],
        warnings=list(result.warnings),
        errors=list(result.errors),
        agent_statuses=list(result.agent_statuses),
    )


def collect_allowlist_skips(
    result: DiscoveryResult,
    allowlist: set[str],
) -> tuple[list[str], list[str]]:
    """Workflow ids that would be proposed but are excluded by the allowlist."""
    skipped: set[str] = set()
    skipped_workspace: set[str] = set()
    for item in result.workspace_runbooks:
        if item.workflow_id not in allowlist:
            skipped.add(item.workflow_id)
            skipped_workspace.add(item.workflow_id)
    for agent in result.agents:
        for job in agent.cron_jobs:
            workflow_id = workflow_id_for_cron(agent.agent_id, job.name)
            if workflow_id not in allowlist:
                skipped.add(workflow_id)
    for runbook in result.runbooks:
        if runbook.workflow_id not in allowlist:
            skipped.add(runbook.workflow_id)
    return sorted(skipped), sorted(skipped_workspace)


def apply_inferred_raci_domain(
    workflow: dict[str, Any],
    registry: dict[str, Any],
    prefix_rules: tuple[tuple[str, str], ...],
) -> None:
    if workflow.get("raci_domain"):
        return
    domain = infer_workflow_raci_domain(
        str(workflow.get("id", "")),
        str(workflow.get("agent", "")),
        registry,
        prefix_rules,
    )
    if domain:
        workflow["raci_domain"] = domain


def build_proposed_workflows(
    result: DiscoveryResult,
    config: GovernanceConfig,
    registry: dict[str, Any],
    *,
    write_runbooks_import: bool,
    allowlist: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[DiscoveredRunbook]]:
    """Build proposed workflow entries and runbook side-effect summary."""
    workspace_by_workflow = {item.workflow_id: item for item in result.workspace_runbooks}
    side_summary: dict[str, Any] = {
        "imported_runbooks": [],
        "skipped_imported_runbooks": [],
        "skipped_runbook_proposals": [],
    }
    known_agent_ids = {agent.agent_id for agent in result.agents}
    governance_runbooks = list(result.runbooks)

    if write_runbooks_import and result.workspace_runbooks:
        import_summary = import_workspace_runbooks(result.workspace_runbooks, config)
        side_summary.update(import_summary)
        imported_runbooks = set(import_summary["imported_runbooks"])
        workspace_by_workflow = {
            item.workflow_id: item
            for item in result.workspace_runbooks
            if item.target_runbook in imported_runbooks
        }
        governance_runbooks = scan_runbooks_on_disk(config, known_agent_ids)
    elif result.workspace_runbooks:
        existing_runbook_workflow_ids = {runbook.workflow_id for runbook in governance_runbooks}
        for item in result.workspace_runbooks:
            if allowlist is not None and item.workflow_id not in allowlist:
                continue
            if item.workflow_id in existing_runbook_workflow_ids:
                continue
            target = config.governance_root / item.target_runbook
            if target.is_file():
                continue
            governance_runbooks.append(
                DiscoveredRunbook(
                    workflow_id=item.workflow_id,
                    runbook=item.target_runbook,
                    agent_id=item.agent_id,
                    title=item.title,
                    path=str(target.resolve()),
                )
            )
            existing_runbook_workflow_ids.add(item.workflow_id)

    proposed_by_id: dict[str, dict[str, Any]] = {}
    cron_groups: dict[str, list[Any]] = defaultdict(list)
    for agent in result.agents:
        for job in agent.cron_jobs:
            group_id = job.group_id or cron_instance_group_id(
                agent.agent_id, job.name, job.schedule
            )
            cron_groups[group_id].append(job)

    for jobs in cron_groups.values():
        if not jobs:
            continue
        agent_id = jobs[0].agent_id
        entry = workflow_entry_from_cron_group(agent_id, jobs, config)
        workflow_id = str(entry["id"])
        proposed_by_id[workflow_id] = entry

    for runbook in governance_runbooks:
        if allowlist is not None and runbook.workflow_id not in allowlist:
            continue
        if runbook.workflow_id in proposed_by_id:
            continue
        if should_skip_runbook_proposal(runbook.workflow_id, registry, config):
            side_summary["skipped_runbook_proposals"].append(runbook.workflow_id)
            continue
        workspace_source = workspace_by_workflow.get(runbook.workflow_id)
        proposed_by_id[runbook.workflow_id] = workflow_entry_from_runbook(
            runbook,
            workspace_source=workspace_source,
        )

    return list(proposed_by_id.values()), side_summary, governance_runbooks


def write_discovery_artifacts(
    result: DiscoveryResult,
    config: GovernanceConfig,
    *,
    candidates: dict[str, Any] | None = None,
    write_inventory: bool = False,
    include_runtime_metrics: bool = False,
) -> dict[str, str]:
    """Write discovered-inventory.json and optional discovery artifacts."""
    paths: dict[str, str] = {}
    if not write_inventory and not include_runtime_metrics and candidates is None:
        return paths

    workflows_dir = config.governance_root / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    if write_inventory:
        known_agent_ids = {agent.agent_id for agent in result.agents}
        inventory_result = DiscoveryResult(
            generated_at=result.generated_at,
            openclaw_home=result.openclaw_home,
            openclaw_config_path=result.openclaw_config_path,
            agents=result.agents,
            runbooks=scan_runbooks_on_disk(config, known_agent_ids)
            if config.runbooks_dir.is_dir()
            else result.runbooks,
            workspace_runbooks=result.workspace_runbooks,
            warnings=result.warnings,
            errors=result.errors,
            agent_statuses=result.agent_statuses,
        )
        inventory_path = workflows_dir / "discovered-inventory.json"
        inventory_path.write_text(
            json.dumps(inventory_result.to_inventory_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        paths["inventory_path"] = str(inventory_path)

    if include_runtime_metrics:
        runtime_path = workflows_dir / "discovered-inventory-runtime.json"
        runtime_path.write_text(
            json.dumps(result.to_runtime_dict(), indent=2) + "\n",
            encoding="utf-8",
        )
        paths["runtime_path"] = str(runtime_path)

    if candidates is not None:
        candidates_path = workflows_dir / "discovery-candidates.json"
        candidates_path.write_text(json.dumps(candidates, indent=2) + "\n", encoding="utf-8")
        paths["candidates_path"] = str(candidates_path)
    return paths


def materialize_from_discovery(
    result: DiscoveryResult,
    config: GovernanceConfig,
    *,
    write: bool = False,
    staged: bool = False,
    promote: bool = False,
    allowlist: set[str] | None = None,
    write_inventory: bool = False,
    include_runtime_metrics: bool = False,
    include_skills: bool = False,
    include_plugins: bool = False,
) -> dict[str, Any]:
    """Build or update registry + runbooks. Returns summary dict."""
    write_registry = write or promote
    staged_merge = promote or staged
    report_candidates = staged

    summary: dict[str, Any] = {
        "write": write_registry,
        "staged": staged,
        "promote": promote,
        "created_workflows": [],
        "updated_workflows": [],
        "skipped_protected_workflows": [],
        "created_workflows_from_runbooks": [],
        "created_runbooks": [],
        "skipped_runbooks": [],
        "imported_runbooks": [],
        "skipped_imported_runbooks": [],
        "runbooks_in_governance": len(result.runbooks),
        "runbooks_in_workspaces": len(result.workspace_runbooks),
    }

    registry_path = config.registry_path
    if registry_path.is_file():
        registry_before = load_registry(registry_path)
    else:
        registry_before = {
            "generated_at": result.generated_at,
            "version": 0.1,
            "source_note": "Initialized by openclaw-gov discover",
            "agents": [],
            "raci_domains": {},
            "workflows": [],
        }

    registry = json.loads(json.dumps(registry_before, default=str))

    full_proposed: list[dict[str, Any]] | None = None
    full_import_side: dict[str, Any] | None = None
    if allowlist is not None and report_candidates:
        full_proposed, full_import_side, _ = build_proposed_workflows(
            result,
            config,
            registry,
            write_runbooks_import=False,
            allowlist=None,
        )

    materialize_result = result
    if allowlist is not None:
        skipped_by_allowlist, skipped_workspace = collect_allowlist_skips(result, allowlist)
        summary["skipped_by_allowlist"] = skipped_by_allowlist
        summary["skipped_workspace_runbook_candidates"] = skipped_workspace
        if not allowlist:
            summary["allowlist_empty_warning"] = (
                "Allowlist is empty; no workflows will be promoted."
            )
        materialize_result = discovery_result_for_allowlist(result, allowlist)

    proposed_workflows, import_side, governance_runbooks = build_proposed_workflows(
        materialize_result,
        config,
        registry,
        write_runbooks_import=write_registry,
        allowlist=allowlist,
    )
    summary["imported_runbooks"] = import_side.get("imported_runbooks", [])
    summary["skipped_imported_runbooks"] = import_side.get("skipped_imported_runbooks", [])

    if allowlist is not None:
        proposed_workflows = filter_proposed_by_allowlist(proposed_workflows, allowlist)

    candidates_report = None
    if report_candidates:
        candidates_for_report = (
            full_proposed if full_proposed is not None else proposed_workflows
        )
        candidates_report = build_discovery_candidates(
            result,
            registry,
            candidates_for_report,
            config,
            skipped_runbook_proposals=(
                full_import_side.get("skipped_runbook_proposals", [])
                if full_import_side is not None
                else import_side.get("skipped_runbook_proposals", [])
            ),
        )
        summary["candidates"] = candidates_report

    registry["generated_at"] = result.generated_at
    proposed_agents = agents_registry_entries(result, config)
    existing_agents = registry.get("agents")
    if not isinstance(existing_agents, list):
        existing_agents = []
    # Promote/staged: preserve curated agent fields; only fill gaps on new agents.
    registry["agents"] = merge_agents(
        existing_agents, proposed_agents, refresh_discovery_fields=not staged_merge
    )
    agent_id_list = [entry["id"] for entry in registry["agents"]]
    accountable = config.accountable_humans[0] if config.accountable_humans else "Operator"
    existing_raci = registry_before.get("raci_domains")
    raci_is_curated = isinstance(existing_raci, dict) and bool(existing_raci)
    if not (staged_merge and raci_is_curated):
        ensure_raci_domains(
            registry,
            agent_id_list,
            accountable=accountable,
            config_excluded=config.raci_broadcast_excluded,
        )

    existing_workflows = registry.get("workflows")
    if not isinstance(existing_workflows, list):
        existing_workflows = []

    merged, created, updated, skipped_protected = merge_workflows(
        existing_workflows,
        proposed_workflows,
        staged=staged_merge,
    )
    prefix_rules = effective_domain_prefix_rules(tuple(config.domain_prefix_rules), registry)
    for workflow in merged:
        if not isinstance(workflow, dict):
            continue
        if staged_merge and str(workflow.get("status", "")) in PROTECTED_WORKFLOW_STATUSES:
            continue
        apply_inferred_raci_domain(workflow, registry, prefix_rules)
    registry["workflows"] = merged
    summary["created_workflows"] = created
    summary["updated_workflows"] = updated
    summary["skipped_protected_workflows"] = skipped_protected
    runbook_workflow_ids = {runbook.workflow_id for runbook in governance_runbooks}
    summary["created_workflows_from_runbooks"] = [
        workflow_id for workflow_id in created if workflow_id in runbook_workflow_ids
    ]

    effective_write_inventory = write_inventory or staged or promote or write

    artifact_paths = write_discovery_artifacts(
        result,
        config,
        candidates=candidates_report,
        write_inventory=effective_write_inventory,
        include_runtime_metrics=include_runtime_metrics,
    )
    summary.update(artifact_paths)
    effective_write_capabilities = effective_write_inventory and (include_skills or include_plugins)
    if include_skills or include_plugins:
        skills_errors: list[str] = []
        plugins_errors: list[str] = []
        if include_skills and not config.capabilities.discover_skills:
            skills_errors.append(
                "--include-skills requested but capabilities.discover_skills is false"
            )
        if include_plugins and not config.capabilities.discover_plugins:
            plugins_errors.append(
                "--include-plugins requested but capabilities.discover_plugins is false"
            )
        skills_result = None
        plugins_result = None
        if include_skills and config.capabilities.discover_skills:
            skills_result = discover_skills(config, result.agents, config.capabilities)
            summary["skills_summary"] = skills_result.payload.get("summary")
            summary["skills_warnings"] = skills_result.warnings
            for err in skills_result.errors:
                phase = err.get("phase", "skills") if isinstance(err, dict) else "skills"
                message = err.get("message", err) if isinstance(err, dict) else err
                skills_errors.append(f"{phase}: {message}")
        if include_plugins and config.capabilities.discover_plugins:
            plugins_result = discover_plugins(config, config.capabilities)
            summary["plugins_summary"] = plugins_result.payload.get("summary")
            summary["plugins_warnings"] = plugins_result.warnings
            for err in plugins_result.errors:
                phase = err.get("phase", "plugins") if isinstance(err, dict) else "plugins"
                message = err.get("message", err) if isinstance(err, dict) else err
                plugins_errors.append(f"{phase}: {message}")
        capabilities_errors = skills_errors + plugins_errors
        if capabilities_errors:
            summary["capabilities_errors"] = capabilities_errors
        write_skills = (
            effective_write_capabilities
            and include_skills
            and not skills_errors
            and skills_result is not None
        )
        write_plugins = (
            effective_write_capabilities
            and include_plugins
            and not plugins_errors
            and plugins_result is not None
        )
        if write_skills or write_plugins:
            summary.update(
                write_capability_artifacts(
                    config,
                    skills=skills_result if write_skills else None,
                    plugins=plugins_result if write_plugins else None,
                )
            )
        elif (skills_result or plugins_result) and not effective_write_capabilities:
            summary["capabilities_read_only"] = (
                "Capability scan complete; use --inventory or --staged to write "
                "discovered-skills.json / discovered-plugins.json."
            )
    summary["read_only"] = (
        not effective_write_inventory
        and not include_runtime_metrics
        and candidates_report is None
        and not write_registry
    )

    diff = registry_semantic_diff(registry_before, registry)
    summary["registry_diff"] = diff

    if not write_registry:
        summary["would_write_registry"] = str(registry_path)
        summary["proposed_workflow_count"] = len(proposed_workflows)
        existing_ids = {str(item.get("id")) for item in existing_workflows if isinstance(item, dict)}
        summary["would_link_runbooks"] = [
            runbook.workflow_id
            for runbook in governance_runbooks
            if runbook.workflow_id not in existing_ids
        ]
        summary["would_import_runbooks"] = [
            item.target_runbook
            for item in materialize_result.workspace_runbooks
            if not (config.governance_root / item.target_runbook).is_file()
        ]
        if staged and not promote:
            summary["promote_hint"] = (
                "discover --staged wrote inventory + discovery-candidates.json only. "
                "Use discover --promote to apply registry changes."
            )
        return summary

    registry_unchanged = not diff["changed"]
    if registry_unchanged:
        summary["registry_unchanged"] = True

    scaffolded = ensure_governance_scaffold(config)
    if scaffolded:
        summary["scaffolded_files"] = scaffolded

    config.runbooks_dir.mkdir(parents=True, exist_ok=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    existing_by_id = {
        str(item.get("id")): item
        for item in (registry_before.get("workflows") or [])
        if isinstance(item, dict) and item.get("id")
    }
    created_set = set(created)
    merged_by_id = {
        str(item.get("id")): item
        for item in registry.get("workflows", [])
        if isinstance(item, dict) and item.get("id")
    }

    for workflow in proposed_workflows:
        workflow_id = str(workflow["id"])
        if staged_merge:
            if workflow_id in existing_by_id:
                existing_runbook = str(existing_by_id[workflow_id].get("runbook") or "")
                if existing_runbook:
                    summary["skipped_runbooks"].append(existing_runbook)
                continue
            if workflow_id not in created_set:
                continue

        merged_wf = merged_by_id.get(workflow_id, workflow)
        runbook_rel = str(merged_wf.get("runbook") or runbook_path_for(workflow_id))
        runbook_file = config.governance_root / runbook_rel
        if runbook_file.is_file():
            summary["skipped_runbooks"].append(runbook_rel)
            continue

        agent_id = str(workflow.get("agent", ""))
        group_jobs = [
            cron
            for agent in materialize_result.agents
            if agent.agent_id == agent_id
            for cron in agent.cron_jobs
            if workflow_id_for_cron(agent_id, cron.name) == workflow_id
        ]
        job = group_jobs[0] if group_jobs else None
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

    if not registry_unchanged:
        with registry_path.open("w", encoding="utf-8") as handle:
            yaml.dump(registry, handle, sort_keys=False, allow_unicode=True)

    summary["registry_path"] = str(registry_path)
    return summary

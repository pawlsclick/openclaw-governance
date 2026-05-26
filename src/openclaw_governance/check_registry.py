"""Validate workflow governance registry consistency."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.registry_common import (
    CORE_PLATFORM_DOMAINS,
    VALID_RUNTIME_STATUSES,
    VALID_WORKFLOW_STATUSES,
    agent_ids,
    agents_excluded_from_raci_broadcast,
    agents_requiring_raci_broadcast,
    load_registry,
    normalize_party_list,
    raci_domains,
    effective_domain_prefix_rules,
    resolve_workflow_raci,
    resolve_workflow_raci_domain,
)

REQUIRED_WORKFLOW_FIELDS = {
    "id",
    "agent",
    "title",
    "status",
    "purpose",
    "trigger",
    "orchestration",
    "inputs",
    "outputs",
    "tools_or_scripts",
    "source_docs",
    "cron_job_ids",
    "risk_level",
    "approval_required",
    "success_criteria",
    "failure_modes",
    "tests",
    "runbook",
    "runtime_status",
    "code_management",
}


class Check:
    def __init__(self) -> None:
        self.errors: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(f"ERROR {message}")

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.error(message)


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def load_registry_checked(path: Path, root: Path, check: Check) -> dict[str, Any]:
    try:
        return load_registry(path)
    except OSError as exc:
        check.error(f"{rel(path, root)} cannot be read: {exc}")
        return {}
    except yaml.YAMLError as exc:
        check.error(f"{rel(path, root)} does not parse as YAML: {exc}")
        return {}
    except ValueError as exc:
        check.error(str(exc))
        return {}


def iter_runbook_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "runbook" and isinstance(child, str) and child.startswith("workflows/runbooks/"):
                refs.add(child)
            else:
                refs.update(iter_runbook_refs(child))
    elif isinstance(value, list):
        for child in value:
            refs.update(iter_runbook_refs(child))
    return refs


def check_workflows(root: Path, registry: dict[str, Any], check: Check, config: GovernanceConfig) -> None:
    workflows = registry.get("workflows")
    check.require(isinstance(workflows, list), "workflows must be a list")
    if not isinstance(workflows, list):
        return

    seen: set[str] = set()
    for index, workflow in enumerate(workflows):
        if not isinstance(workflow, dict):
            check.error(f"workflows[{index}] must be a mapping")
            continue

        workflow_id = workflow.get("id", f"<index:{index}>")
        if workflow_id in seen:
            check.error(f"duplicate workflow id: {workflow_id}")
        seen.add(workflow_id)

        missing = sorted(REQUIRED_WORKFLOW_FIELDS - set(workflow))
        for field in missing:
            check.error(f"workflows[{workflow_id}].{field} missing")

        status = workflow.get("status")
        if status not in VALID_WORKFLOW_STATUSES:
            check.error(f"workflows[{workflow_id}].status invalid: {status!r}")

        runtime_status = workflow.get("runtime_status")
        if runtime_status not in VALID_RUNTIME_STATUSES:
            check.error(f"workflows[{workflow_id}].runtime_status invalid: {runtime_status!r}")

        runbook = workflow.get("runbook")
        if isinstance(runbook, str):
            check.require((root / runbook).is_file(), f"workflows[{workflow_id}].runbook missing: {runbook}")

        if config.finance_agent_owner_check and workflow.get("agent") == "finance":
            check.require(
                workflow.get("owner") == "Felix",
                f"workflows[{workflow_id}].owner expected Felix, got {workflow.get('owner')!r}",
            )

        if status == "archived":
            check.require(
                runtime_status == "disabled",
                f"workflows[{workflow_id}] is archived but runtime_status is {runtime_status!r}",
            )

    platform = registry.get("platform", {})
    if isinstance(platform, dict):
        for platform_id, platform_config in platform.items():
            if not isinstance(platform_config, dict):
                continue
            for workflow_id in platform_config.get("workflows", []) or []:
                check.require(workflow_id in seen, f"platform.{platform_id}.workflows references missing workflow: {workflow_id}")


def validate_raci_party(
    check: Check,
    *,
    context: str,
    party: str,
    known_agents: set[str],
    accountable_humans: set[str],
    allow_humans: bool,
) -> None:
    if party in known_agents:
        return
    if allow_humans and party in accountable_humans:
        return
    check.error(f"{context} unknown party {party!r}")


def check_agents_and_raci_domains(registry: dict[str, Any], check: Check, config: GovernanceConfig) -> set[str]:
    agents = registry.get("agents")
    check.require(isinstance(agents, list), "agents must be a list")
    if not isinstance(agents, list):
        return set()

    known_agents: set[str] = set()
    for index, entry in enumerate(agents):
        if not isinstance(entry, dict):
            check.error(f"agents[{index}] must be a mapping")
            continue
        agent_id = entry.get("id")
        check.require(isinstance(agent_id, str) and agent_id, f"agents[{index}].id missing")
        if not isinstance(agent_id, str):
            continue
        if agent_id in known_agents:
            check.error(f"duplicate agent id: {agent_id}")
        known_agents.add(agent_id)
        for field in ("name", "role", "workspace"):
            check.require(isinstance(entry.get(field), str) and entry.get(field), f"agents[{agent_id}].{field} missing")

    domains = raci_domains(registry)
    workflows = registry.get("workflows")
    workflow_count = len(workflows) if isinstance(workflows, list) else 0
    if known_agents or workflow_count:
        check.require(domains, "raci_domains must define at least one domain")
    if not domains:
        return known_agents
    broadcast_excluded = agents_excluded_from_raci_broadcast(registry)
    broadcast_agents = agents_requiring_raci_broadcast(registry)
    humans = set(config.accountable_humans)

    for domain_key, domain in domains.items():
        context = f"raci_domains.{domain_key}"
        check.require(isinstance(domain.get("title"), str) and domain.get("title"), f"{context}.title missing")

        responsible = domain.get("responsible")
        check.require(isinstance(responsible, str), f"{context}.responsible must be an agent id")
        validate_raci_party(
            check,
            context=f"{context}.responsible",
            party=responsible,
            known_agents=known_agents,
            accountable_humans=humans,
            allow_humans=False,
        )

        accountable = domain.get("accountable")
        check.require(isinstance(accountable, str), f"{context}.accountable must be a human name")
        validate_raci_party(
            check,
            context=f"{context}.accountable",
            party=accountable,
            known_agents=known_agents,
            accountable_humans=humans,
            allow_humans=True,
        )

        for label in ("consulted", "informed"):
            for party in normalize_party_list(domain.get(label)):
                if party in broadcast_excluded:
                    check.error(
                        f"{context}.{label} must not include broadcast-excluded agent {party!r} "
                        f"(isolated cron-only agents are not notified of cross-workspace changes)"
                    )
                validate_raci_party(
                    check,
                    context=f"{context}.{label}",
                    party=party,
                    known_agents=known_agents,
                    accountable_humans=humans,
                    allow_humans=True,
                )

        if domain_key in CORE_PLATFORM_DOMAINS:
            informed = set(normalize_party_list(domain.get("informed")))
            missing = sorted(broadcast_agents - informed)
            extra = sorted(informed & broadcast_excluded)
            check.require(
                not missing,
                f"{context}.informed must include all broadcast agents; missing: {', '.join(missing)}",
            )
            check.require(
                not extra,
                f"{context}.informed must not include broadcast-excluded agents: {', '.join(extra)}",
            )

    return known_agents


def check_workflow_raci(
    registry: dict[str, Any],
    check: Check,
    known_agents: set[str],
    config: GovernanceConfig,
) -> None:
    workflows = registry.get("workflows")
    if not isinstance(workflows, list):
        return

    domains = raci_domains(registry)
    prefix_rules = effective_domain_prefix_rules(tuple(config.domain_prefix_rules), registry)
    humans = set(config.accountable_humans)
    high_risk_ids: list[str] = []

    for workflow in workflows:
        if not isinstance(workflow, dict):
            continue
        workflow_id = str(workflow.get("id", ""))
        if workflow.get("risk_level") == "high":
            high_risk_ids.append(workflow_id)

        domain_key = workflow.get("raci_domain")
        if isinstance(domain_key, str):
            check.require(domain_key in domains, f"workflows[{workflow_id}].raci_domain unknown: {domain_key}")
        else:
            resolved = resolve_workflow_raci_domain(workflow_id, registry, prefix_rules)
            check.require(
                resolved is not None,
                f"workflows[{workflow_id}] has no raci_domain and no prefix mapping; add raci_domain or raci_workflow_domains.explicit entry",
            )
            if resolved:
                check.require(resolved in domains, f"workflows[{workflow_id}] maps to unknown domain {resolved!r}")

        effective = resolve_workflow_raci(workflow, registry, prefix_rules)
        check.require(effective is not None, f"workflows[{workflow_id}] could not resolve effective RACI")

        if isinstance(workflow.get("raci"), dict):
            raci = workflow["raci"]
            for field in ("responsible", "accountable"):
                check.require(field in raci, f"workflows[{workflow_id}].raci.{field} missing")
            validate_raci_party(
                check,
                context=f"workflows[{workflow_id}].raci.responsible",
                party=str(raci.get("responsible")),
                known_agents=known_agents,
                accountable_humans=humans,
                allow_humans=False,
            )
            validate_raci_party(
                check,
                context=f"workflows[{workflow_id}].raci.accountable",
                party=str(raci.get("accountable")),
                known_agents=known_agents,
                accountable_humans=humans,
                allow_humans=True,
            )
            excluded = agents_excluded_from_raci_broadcast(registry)
            for label in ("consulted", "informed"):
                for party in normalize_party_list(raci.get(label)):
                    if party in excluded:
                        check.error(
                            f"workflows[{workflow_id}].raci.{label} must not include "
                            f"broadcast-excluded agent {party!r}"
                        )
                    validate_raci_party(
                        check,
                        context=f"workflows[{workflow_id}].raci.{label}",
                        party=party,
                        known_agents=known_agents,
                        accountable_humans=humans,
                        allow_humans=True,
                    )

    for workflow_id in high_risk_ids:
        workflow = next(item for item in workflows if isinstance(item, dict) and item.get("id") == workflow_id)
        check.require(
            isinstance(workflow.get("raci"), dict),
            f"workflows[{workflow_id}] is high risk and must define an explicit raci block",
        )


def check_raci_prefix_coverage(registry: dict[str, Any], check: Check, config: GovernanceConfig) -> None:
    workflows = registry.get("workflows")
    if not isinstance(workflows, list):
        return
    if not config.domain_prefix_rules:
        return
    domains = raci_domains(registry)
    if not domains:
        return
    for prefix, domain_key in config.domain_prefix_rules:
        check.require(domain_key in domains, f"domain_prefix_rules {prefix!r} -> unknown domain {domain_key!r}")


def check_runbook_references(root: Path, registry: dict[str, Any], check: Check) -> None:
    referenced = iter_runbook_refs(registry)
    for runbook in sorted(referenced):
        check.require((root / runbook).is_file(), f"runbook reference missing: {runbook}")

    runbook_dir = root / "workflows" / "runbooks"
    if not runbook_dir.is_dir():
        return
    workflows = registry.get("workflows")
    allow_orphan_runbooks = isinstance(workflows, list) and len(workflows) == 0
    for path in sorted(runbook_dir.glob("*.md")):
        runbook = rel(path, root)
        if allow_orphan_runbooks and runbook not in referenced:
            continue
        check.require(runbook in referenced, f"unreferenced runbook: {runbook}")


def parse_readme_counts(readme: str, check: Check) -> tuple[int | None, dict[str, int], dict[str, int]]:
    total_match = re.search(r"The current registry tracks (\d+) workflows:", readme)
    total = int(total_match.group(1)) if total_match else None
    if total is None:
        check.error("README workflow total line missing")

    status_counts: dict[str, int] = {}
    runtime_counts: dict[str, int] = {}
    for label in VALID_WORKFLOW_STATUSES:
        match = re.search(rf"- (\d+) {re.escape(label)} workflow entries", readme)
        if match:
            status_counts[label] = int(match.group(1))

    for label in VALID_RUNTIME_STATUSES:
        match = re.search(rf"- (\d+) {re.escape(label)} runtimes", readme)
        if match:
            runtime_counts[label] = int(match.group(1))

    return total, status_counts, runtime_counts


def check_readme_counts(root: Path, registry: dict[str, Any], check: Check) -> None:
    readme_path = root / "README.md"
    if not readme_path.exists():
        check.error("README.md missing")
        return

    workflows = registry.get("workflows")
    if not isinstance(workflows, list):
        return

    readme = readme_path.read_text(encoding="utf-8")
    readme_total, readme_statuses, readme_runtimes = parse_readme_counts(readme, check)
    actual_statuses = Counter(workflow.get("status") for workflow in workflows if isinstance(workflow, dict))
    actual_runtimes = Counter(workflow.get("runtime_status") for workflow in workflows if isinstance(workflow, dict))

    if readme_total is not None:
        check.require(readme_total == len(workflows), f"README total mismatch: says {readme_total}, registry has {len(workflows)}")

    for status in sorted(VALID_WORKFLOW_STATUSES):
        if actual_statuses[status] > 0:
            check.require(
                status in readme_statuses,
                f"README count missing for status {status}: registry has {actual_statuses[status]}",
            )
        if status in readme_statuses:
            check.require(
                readme_statuses[status] == actual_statuses[status],
                f"README count mismatch for status {status}: says {readme_statuses[status]}, registry has {actual_statuses[status]}",
            )

    for runtime in sorted(VALID_RUNTIME_STATUSES):
        if actual_runtimes[runtime] > 0:
            check.require(
                runtime in readme_runtimes,
                f"README count missing for runtime {runtime}: registry has {actual_runtimes[runtime]}",
            )
        if runtime in readme_runtimes:
            check.require(
                readme_runtimes[runtime] == actual_runtimes[runtime],
                f"README count mismatch for runtime {runtime}: says {readme_runtimes[runtime]}, registry has {actual_runtimes[runtime]}",
            )


def run_check(config: GovernanceConfig) -> int:
    root = config.governance_root
    check = Check()
    registry_path = config.registry_path
    if not registry_path.is_file():
        check.error(f"registry missing: {registry_path}")
    else:
        registry = load_registry_checked(registry_path, root, check)
        if not check.errors:
            known_agents = check_agents_and_raci_domains(registry, check, config)
            check_raci_prefix_coverage(registry, check, config)
            check_workflows(root, registry, check, config)
            if known_agents:
                check_workflow_raci(registry, check, known_agents, config)
            check_runbook_references(root, registry, check)
            if config.require_readme_markers:
                check_readme_counts(root, registry, check)

    if check.errors:
        for error in check.errors:
            print(error)
        return 1

    print("governance_registry_ok")
    return 0

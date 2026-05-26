"""Discover OpenClaw agents, cron jobs, workspaces, and git repos."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.paths import openclaw_config_path
from openclaw_governance.runbook_import import (
    scan_workspace_runbooks,
    workflow_id_from_workspace_runbook,
)
from openclaw_governance.runbook_utils import (
    agent_id_from_workflow_id,
    parse_runbook_title,
    slugify,
    workflow_id_from_path,
)


@dataclass
class CronJob:
    agent_id: str
    job_id: str
    name: str
    enabled: bool
    schedule: str
    message_preview: str


@dataclass
class DiscoveredAgent:
    agent_id: str
    name: str
    role: str
    workspace: str
    cron_jobs: list[CronJob] = field(default_factory=list)
    git_repos: list[dict[str, str]] = field(default_factory=list)
    script_paths: list[str] = field(default_factory=list)


@dataclass
class DiscoveredRunbook:
    workflow_id: str
    runbook: str
    agent_id: str
    title: str
    path: str
    source: str = "governance"


@dataclass
class DiscoveredWorkspaceRunbook:
    agent_id: str
    workflow_id: str
    title: str
    source_path: str
    workspace_relative: str
    target_runbook: str


@dataclass
class DiscoveryResult:
    generated_at: str
    openclaw_home: str
    openclaw_config_path: str
    agents: list[DiscoveredAgent]
    runbooks: list[DiscoveredRunbook] = field(default_factory=list)
    workspace_runbooks: list[DiscoveredWorkspaceRunbook] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "openclaw_home": self.openclaw_home,
            "openclaw_config_path": self.openclaw_config_path,
            "warnings": self.warnings,
            "runbooks": [
                {
                    "workflow_id": runbook.workflow_id,
                    "runbook": runbook.runbook,
                    "agent_id": runbook.agent_id,
                    "title": runbook.title,
                    "path": runbook.path,
                    "source": runbook.source,
                }
                for runbook in self.runbooks
            ],
            "workspace_runbooks": [
                {
                    "agent_id": item.agent_id,
                    "workflow_id": item.workflow_id,
                    "title": item.title,
                    "source_path": item.source_path,
                    "workspace_relative": item.workspace_relative,
                    "target_runbook": item.target_runbook,
                }
                for item in self.workspace_runbooks
            ],
            "agents": [
                {
                    "agent_id": agent.agent_id,
                    "name": agent.name,
                    "role": agent.role,
                    "workspace": agent.workspace,
                    "cron_jobs": [
                        {
                            "job_id": job.job_id,
                            "name": job.name,
                            "enabled": job.enabled,
                            "schedule": job.schedule,
                            "message_preview": job.message_preview,
                        }
                        for job in agent.cron_jobs
                    ],
                    "git_repos": agent.git_repos,
                    "script_paths": agent.script_paths,
                }
                for agent in self.agents
            ],
        }


def scan_runbooks_on_disk(
    config: GovernanceConfig,
    known_agent_ids: set[str],
) -> list[DiscoveredRunbook]:
    """Find runbook markdown files under workflows/runbooks/."""
    runbooks_dir = config.runbooks_dir
    if not runbooks_dir.is_dir():
        return []

    discovered: list[DiscoveredRunbook] = []
    for path in sorted(runbooks_dir.glob("*.md")):
        if not path.is_file():
            continue
        workflow_id = path.stem
        if not workflow_id:
            continue
        discovered.append(
            DiscoveredRunbook(
                workflow_id=workflow_id,
                runbook=f"workflows/runbooks/{path.name}",
                agent_id=agent_id_from_workflow_id(workflow_id, known_agent_ids),
                title=parse_runbook_title(path),
                path=str(path.resolve()),
            )
        )
    return discovered


def scan_workspace_runbooks_for_agents(
    agents: list[DiscoveredAgent],
    config: GovernanceConfig,
) -> tuple[list[DiscoveredWorkspaceRunbook], list[str]]:
    """Locate *runbook*.md files in agent workspaces (identify only)."""
    if not config.discovery_scan_workspace_runbooks:
        return [], []

    warnings: list[str] = []
    discovered: list[DiscoveredWorkspaceRunbook] = []
    seen_workflow_ids: dict[str, str] = {}
    governance_runbooks = config.runbooks_dir.resolve() if config.runbooks_dir.is_dir() else None

    for agent in agents:
        workspace = Path(agent.workspace)
        for path in scan_workspace_runbooks(
            agent.agent_id,
            workspace,
            glob_pattern=config.discovery_workspace_runbook_glob,
            governance_runbooks_dir=governance_runbooks,
        ):
            workflow_id = workflow_id_from_workspace_runbook(agent.agent_id, path)
            if workflow_id in seen_workflow_ids:
                prior = seen_workflow_ids[workflow_id]
                warnings.append(
                    f"duplicate workflow id `{workflow_id}` from {prior} and {path}; keeping first"
                )
                continue
            seen_workflow_ids[workflow_id] = str(path)
            try:
                relative = path.relative_to(workspace).as_posix()
            except ValueError:
                relative = path.name
            target = f"workflows/runbooks/{workflow_id}.md"
            discovered.append(
                DiscoveredWorkspaceRunbook(
                    agent_id=agent.agent_id,
                    workflow_id=workflow_id,
                    title=parse_runbook_title(path),
                    source_path=str(path),
                    workspace_relative=relative,
                    target_runbook=target,
                )
            )
    return discovered, warnings


def load_openclaw_config(config: GovernanceConfig) -> dict[str, Any]:
    path = openclaw_config_path(config.openclaw_home)
    if not path.is_file():
        raise FileNotFoundError(f"OpenClaw config not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def parse_agents_from_config(openclaw_config: dict[str, Any], config: GovernanceConfig) -> list[DiscoveredAgent]:
    agents_block = openclaw_config.get("agents")
    if not isinstance(agents_block, dict):
        return []

    entries = agents_block.get("list")
    if not isinstance(entries, list):
        return []

    discovered: list[DiscoveredAgent] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        agent_id = entry.get("id")
        if not isinstance(agent_id, str) or not agent_id:
            continue

        identity = entry.get("identity") if isinstance(entry.get("identity"), dict) else {}
        name = entry.get("name") or identity.get("name") or agent_id.replace("_", " ").title()
        role = entry.get("role") or identity.get("role") or f"{agent_id} agent"

        workspace_raw = entry.get("workspace")
        if isinstance(workspace_raw, str) and workspace_raw:
            workspace = str(Path(workspace_raw).expanduser().resolve())
        else:
            workspace = str((config.openclaw_home / "agents" / agent_id).resolve())
            if agent_id == "main":
                workspace = str((config.openclaw_home / "workspace").resolve())

        discovered.append(
            DiscoveredAgent(
                agent_id=agent_id,
                name=str(name),
                role=str(role),
                workspace=workspace,
            )
        )
    return discovered


def run_openclaw_cron_list(agent_id: str) -> tuple[list[dict[str, Any]], str | None]:
    try:
        proc = subprocess.run(
            ["openclaw", "cron", "list", "--agent", agent_id, "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        return [], "openclaw CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return [], f"openclaw cron list timed out for agent {agent_id}"

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        return [], f"openclaw cron list failed for {agent_id}: {stderr[:200]}"

    raw = proc.stdout or ""
    start = raw.find("{")
    if start < 0:
        return [], f"openclaw cron list returned non-JSON for {agent_id}"
    try:
        data = json.loads(raw[start:])
    except json.JSONDecodeError as exc:
        return [], f"openclaw cron list JSON parse error for {agent_id}: {exc}"

    jobs = data.get("jobs")
    if isinstance(jobs, list):
        return [item for item in jobs if isinstance(item, dict)], None
    return [], None


def parse_cron_jobs(agent_id: str, jobs: list[dict[str, Any]]) -> list[CronJob]:
    parsed: list[CronJob] = []
    seen: set[tuple[str, str]] = set()
    for job in jobs:
        job_id = str(job.get("id", ""))
        name = str(job.get("name") or job_id or "unnamed")
        dedupe_key = (job_id, name)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        enabled = bool(job.get("enabled", True))
        schedule = ""
        sched = job.get("schedule")
        if isinstance(sched, dict):
            schedule = json.dumps(sched, sort_keys=True)
        elif sched is not None:
            schedule = str(sched)

        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        message = payload.get("message", "")
        preview = str(message).replace("\n", " ")[:160]

        parsed.append(
            CronJob(
                agent_id=agent_id,
                job_id=job_id,
                name=name,
                enabled=enabled,
                schedule=schedule,
                message_preview=preview,
            )
        )
    return parsed


def git_remote_for(path: Path) -> dict[str, str] | None:
    try:
        inside = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            check=False,
        )
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return None
        root = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        top = Path(root.stdout.strip()).resolve()
        remote = subprocess.run(
            ["git", "-C", str(top), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
        )
        url = remote.stdout.strip() if remote.returncode == 0 else ""
        return {"path": str(top), "remote": url}
    except (OSError, subprocess.SubprocessError):
        return None


def scan_scripts(workspace: Path, globs: list[str]) -> list[str]:
    found: list[str] = []
    for pattern in globs:
        for path in workspace.glob(pattern):
            if path.is_file():
                found.append(str(path.resolve()))
    return sorted(set(found))[:50]


def discover(config: GovernanceConfig) -> DiscoveryResult:
    warnings: list[str] = []
    openclaw_config = load_openclaw_config(config)
    agents = parse_agents_from_config(openclaw_config, config)

    for agent in agents:
        jobs_raw, cron_warning = run_openclaw_cron_list(agent.agent_id)
        if cron_warning:
            warnings.append(cron_warning)
        agent.cron_jobs = parse_cron_jobs(agent.agent_id, jobs_raw)

        workspace = Path(agent.workspace)
        if config.discovery_scan_git_repos and workspace.is_dir():
            repo = git_remote_for(workspace)
            if repo:
                agent.git_repos.append(repo)
            for child in workspace.iterdir():
                if child.is_dir() and (child / ".git").is_dir():
                    nested = git_remote_for(child)
                    if nested and nested not in agent.git_repos:
                        agent.git_repos.append(nested)

        if workspace.is_dir():
            agent.script_paths = scan_scripts(workspace, config.discovery_script_globs)

    known_agent_ids = {agent.agent_id for agent in agents}
    runbooks = scan_runbooks_on_disk(config, known_agent_ids)
    workspace_runbooks, workspace_warnings = scan_workspace_runbooks_for_agents(agents, config)
    warnings.extend(workspace_warnings)

    return DiscoveryResult(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path=str(openclaw_config_path(config.openclaw_home)),
        agents=agents,
        runbooks=runbooks,
        workspace_runbooks=workspace_runbooks,
        warnings=warnings,
    )


def workflow_id_for_cron(agent_id: str, job_name: str) -> str:
    return f"{agent_id}.cron.{slugify(job_name)}"


def print_discovery_report(result: DiscoveryResult) -> None:
    print(f"Discovery at {result.generated_at}")
    print(f"OpenClaw home: {result.openclaw_home}")
    print(f"Agents: {len(result.agents)}")
    cron_total = sum(len(agent.cron_jobs) for agent in result.agents)
    print(f"Cron jobs: {cron_total}")
    print(f"Runbooks in governance root: {len(result.runbooks)}")
    print(f"Runbooks in agent workspaces: {len(result.workspace_runbooks)}")
    for warning in result.warnings:
        print(f"WARN {warning}")
    print("")
    for runbook in result.runbooks:
        print(f"  [governance] {runbook.runbook} -> `{runbook.workflow_id}` ({runbook.title})")
    for item in result.workspace_runbooks:
        print(
            f"  [workspace/{item.agent_id}] {item.workspace_relative} -> "
            f"`{item.workflow_id}` => {item.target_runbook}"
        )
    if result.runbooks or result.workspace_runbooks:
        print("")
    for agent in result.agents:
        print(f"- {agent.agent_id}: workspace={agent.workspace} crons={len(agent.cron_jobs)} scripts={len(agent.script_paths)}")
        for job in agent.cron_jobs:
            state = "enabled" if job.enabled else "disabled"
            print(f"    cron [{state}] {job.name} -> {workflow_id_for_cron(agent.agent_id, job.name)}")

"""Regenerate README workflow summary from registry.yaml."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from openclaw_governance.check_capabilities import (
    _reapply_plugin_governance,
    _reapply_skill_governance,
)
from openclaw_governance.config import GovernanceConfig
from openclaw_governance.inventory_artifacts import load_plugins_artifact, load_skills_artifact
from openclaw_governance.registry_common import UniqueKeyLoader, construct_mapping_without_duplicate_keys, load_registry

UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping_without_duplicate_keys
)

VALID_WORKFLOW_STATUSES = ("active", "required", "discovered", "implemented", "archived")
VALID_RUNTIME_STATUSES = ("active", "manual", "disabled")

BEGIN_MARKER = "<!-- governance:workflow-summary:begin -->"
END_MARKER = "<!-- governance:workflow-summary:end -->"
CAPABILITIES_BEGIN = "<!-- governance:capabilities-summary:begin -->"
CAPABILITIES_END = "<!-- governance:capabilities-summary:end -->"


def runbook_link(runbook: str) -> str:
    name = Path(runbook).name
    return f"[{name}]({runbook})"


def render_summary(workflows: list[dict[str, Any]]) -> str:
    status_counts = Counter(w.get("status") for w in workflows if isinstance(w, dict))
    runtime_counts = Counter(w.get("runtime_status") for w in workflows if isinstance(w, dict))

    lines: list[str] = []
    lines.append(f"The current registry tracks {len(workflows)} workflows:")
    lines.append("")

    for status in VALID_WORKFLOW_STATUSES:
        count = status_counts.get(status, 0)
        if count:
            lines.append(f"- {count} {status} workflow entries")

    for runtime in VALID_RUNTIME_STATUSES:
        count = runtime_counts.get(runtime, 0)
        if count:
            lines.append(f"- {count} {runtime} runtimes")

    lines.append("")
    lines.append("| Workflow | Agent | Status | Runtime | Trigger | Risk | Runbook |")
    lines.append("|---|---:|---:|---:|---|---:|---|")

    for workflow in sorted(workflows, key=lambda item: str(item.get("id", ""))):
        if not isinstance(workflow, dict):
            continue
        workflow_id = workflow.get("id", "")
        title = workflow.get("title", "")
        agent = workflow.get("agent", "")
        status = workflow.get("status", "")
        runtime_status = workflow.get("runtime_status", "")
        trigger = str(workflow.get("trigger", "")).replace("|", "\\|")
        risk = workflow.get("risk_level", "")
        runbook = workflow.get("runbook", "")
        runbook_cell = runbook_link(runbook) if isinstance(runbook, str) and runbook else ""
        lines.append(
            f"| `{workflow_id}`<br>{title} | {agent} | {status} | {runtime_status} | {trigger} | {risk} | {runbook_cell} |"
        )

    return "\n".join(lines) + "\n"


def replace_marked_section(readme: str, new_body: str) -> str:
    pattern = re.compile(
        re.escape(BEGIN_MARKER) + r".*?" + re.escape(END_MARKER),
        flags=re.DOTALL,
    )
    replacement = f"{BEGIN_MARKER}\n{new_body}{END_MARKER}"
    if not pattern.search(readme):
        raise ValueError(f"README.md missing {BEGIN_MARKER} / {END_MARKER} markers")
    return pattern.sub(replacement, readme, count=1)


def render_capabilities_summary(config: GovernanceConfig) -> str | None:
    skills = load_skills_artifact(config)
    plugins = load_plugins_artifact(config)
    if skills is None and plugins is None:
        return None
    if not skills and not plugins:
        return None

    lines: list[str] = []
    lines.append("Capability inventory snapshots (from committed discovered-*.json):")
    lines.append("")
    if skills:
        _reapply_skill_governance(skills, config)
        summary = skills.get("summary") if isinstance(skills.get("summary"), dict) else {}
        lines.append(
            f"- Skills: {summary.get('total', 0)} total, "
            f"{summary.get('undocumented', 0)} undocumented, "
            f"{summary.get('expected', 0)} expected"
        )
    if plugins:
        _reapply_plugin_governance(plugins, config)
        summary = plugins.get("summary") if isinstance(plugins.get("summary"), dict) else {}
        lines.append(
            f"- Plugins: {summary.get('total', 0)} total, "
            f"{summary.get('undocumented', 0)} undocumented, "
            f"{summary.get('expected', 0)} expected"
        )
    lines.append("")
    lines.append(
        "Refresh with `openclaw-gov discover --staged --include-skills --include-plugins`."
    )
    return "\n".join(lines) + "\n"


def replace_optional_marked_section(readme: str, begin: str, end: str, new_body: str) -> str | None:
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), flags=re.DOTALL)
    if not pattern.search(readme):
        return None
    replacement = f"{begin}\n{new_body}{end}"
    return pattern.sub(replacement, readme, count=1)


def run_regen_summary(
    config: GovernanceConfig,
    *,
    write: bool = False,
    check: bool = False,
    include_capabilities: bool = False,
) -> int:
    root = config.governance_root
    registry_path = config.registry_path
    readme_path = config.readme_path

    try:
        registry = load_registry(registry_path)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        print(f"ERROR {exc}")
        return 1

    workflows = [item for item in registry["workflows"] if isinstance(item, dict)]
    generated = render_summary(workflows)

    if not readme_path.exists():
        print("ERROR README.md missing")
        return 1

    readme = readme_path.read_text(encoding="utf-8")
    try:
        updated = replace_marked_section(readme, generated)
    except ValueError as exc:
        print(f"ERROR {exc}")
        return 1

    capabilities_generated: str | None = None
    if include_capabilities:
        capabilities_generated = render_capabilities_summary(config)
        if capabilities_generated is None:
            if check:
                print(
                    "ERROR discovered-skills.json and/or discovered-plugins.json missing or invalid; "
                    "run: openclaw-gov discover --staged --include-skills --include-plugins"
                )
                return 1
            print(
                "WARN no discovered-skills.json or discovered-plugins.json; "
                "skipping capabilities summary"
            )
        else:
            cap_updated = replace_optional_marked_section(
                updated,
                CAPABILITIES_BEGIN,
                CAPABILITIES_END,
                capabilities_generated,
            )
            if cap_updated is None:
                print(
                    f"WARN README missing {CAPABILITIES_BEGIN} markers; "
                    "capabilities summary not written"
                )
            else:
                updated = cap_updated

    if write:
        readme_path.write_text(updated, encoding="utf-8")
        print(f"updated {readme_path.relative_to(root)}")
        return 0

    if check:
        if updated != readme:
            workflow_only = replace_marked_section(readme, generated)
            if workflow_only != readme:
                print("ERROR README workflow summary is stale; run: openclaw-gov regen --write")
                return 1
            if include_capabilities and capabilities_generated is not None:
                cap_only = replace_optional_marked_section(
                    readme,
                    CAPABILITIES_BEGIN,
                    CAPABILITIES_END,
                    capabilities_generated,
                )
                if cap_only is not None and cap_only != readme:
                    print(
                        "ERROR README capabilities summary is stale; "
                        "run: openclaw-gov regen --write --include-capabilities"
                    )
                    return 1
            print("ERROR README summary is stale; run: openclaw-gov regen --write")
            return 1
        print("readme_workflow_summary_ok")
        return 0

    print(generated)
    return 0

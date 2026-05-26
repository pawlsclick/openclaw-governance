"""Regenerate README workflow summary from registry.yaml."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.registry_common import UniqueKeyLoader, construct_mapping_without_duplicate_keys, load_registry

UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping_without_duplicate_keys
)

VALID_WORKFLOW_STATUSES = ("active", "required", "discovered", "implemented", "archived")
VALID_RUNTIME_STATUSES = ("active", "manual", "disabled")

BEGIN_MARKER = "<!-- governance:workflow-summary:begin -->"
END_MARKER = "<!-- governance:workflow-summary:end -->"


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


def run_regen_summary(config: GovernanceConfig, *, write: bool = False, check: bool = False) -> int:
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

    if write:
        readme_path.write_text(updated, encoding="utf-8")
        print(f"updated {readme_path.relative_to(root)}")
        return 0

    if check:
        if updated != readme:
            print("ERROR README workflow summary is stale; run: openclaw-gov regen --write")
            return 1
        print("readme_workflow_summary_ok")
        return 0

    print(generated)
    return 0

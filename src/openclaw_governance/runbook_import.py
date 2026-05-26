"""Convert workspace runbooks into openclaw-gov governance runbook format."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from openclaw_governance.runbook_utils import slugify

_SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
    }
)


def workflow_id_from_workspace_runbook(agent_id: str, path: Path) -> str:
    """Derive a registry workflow id from a workspace runbook path."""
    stem = path.stem
    if stem.startswith(f"{agent_id}."):
        return stem
    normalized = re.sub(r"-?runbook", "", stem, flags=re.IGNORECASE).strip("-_")
    slug_source = normalized or stem
    slug = slugify(slug_source)
    return f"{agent_id}.{slug}"


def _should_skip_workspace_path(path: Path) -> bool:
    return any(part in _SKIP_DIR_NAMES for part in path.parts)


def scan_workspace_runbooks(
    agent_id: str,
    workspace: Path,
    *,
    glob_pattern: str = "**/*runbook*.md",
    governance_runbooks_dir: Path | None = None,
    max_files: int = 100,
) -> list[Path]:
    """Find runbook markdown files under an agent workspace."""
    if not workspace.is_dir():
        return []

    found: list[Path] = []
    for path in sorted(workspace.glob(glob_pattern)):
        if not path.is_file():
            continue
        if _should_skip_workspace_path(path.relative_to(workspace)):
            continue
        if governance_runbooks_dir is not None:
            try:
                path.resolve().relative_to(governance_runbooks_dir.resolve())
                continue
            except ValueError:
                pass
        found.append(path.resolve())
        if len(found) >= max_files:
            break
    return found


def strip_leading_runbook_metadata(body: str) -> str:
    """Remove duplicate title / workflow metadata from imported body."""
    lines = body.splitlines()
    index = 0
    if index < len(lines) and lines[index].strip().startswith("# "):
        index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    metadata_prefixes = (
        "workflow id:",
        "agent:",
        "status:",
        "generated:",
        "migrated from:",
    )
    while index < len(lines):
        stripped = lines[index].strip().lower()
        if not stripped:
            index += 1
            continue
        if any(stripped.startswith(prefix) for prefix in metadata_prefixes):
            index += 1
            continue
        break
    return "\n".join(lines[index:]).strip()


def render_imported_runbook(
    *,
    workflow_id: str,
    agent_id: str,
    title: str,
    source_path: Path,
    source_body: str,
) -> str:
    """Wrap workspace runbook content in the governance runbook template."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cleaned = strip_leading_runbook_metadata(source_body)
    lines = [
        f"# {title}",
        "",
        f"Workflow ID: `{workflow_id}`  ",
        f"Agent: `{agent_id}`  ",
        "Status: discovered",
        f"Generated: {timestamp} (openclaw-gov discover — imported from workspace)",
        f"Migrated from: `{source_path}`",
        "",
    ]
    if cleaned:
        lines.extend(["## Imported content", "", cleaned, ""])
    else:
        lines.extend(
            [
                "## Purpose",
                "",
                "Imported from a workspace runbook. Replace this section with the operational purpose after review.",
                "",
            ]
        )
    return "\n".join(lines) + "\n"

"""Shared helpers for runbook discovery and import."""

from __future__ import annotations

import re
from pathlib import Path


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "unnamed"


def agent_id_from_workflow_id(workflow_id: str, known_agent_ids: set[str]) -> str:
    prefix = workflow_id.split(".", 1)[0]
    if prefix in known_agent_ids:
        return prefix
    return "main"


def parse_runbook_title(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return workflow_id_from_path(path)
    for line in text.splitlines()[:40]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return workflow_id_from_path(path)


def workflow_id_from_path(path: Path) -> str:
    return path.stem.replace("_", " ").replace("-", " ").title()

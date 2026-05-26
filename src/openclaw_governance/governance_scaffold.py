"""Ensure governance root has template files (README, config, etc.)."""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from openclaw_governance.config import GovernanceConfig


def _templates_root() -> Path:
    return Path(resources.files("openclaw_governance")) / "templates"


def ensure_governance_scaffold(config: GovernanceConfig) -> list[str]:
    """Copy missing template files into the governance root. Returns relative paths created."""
    root = config.governance_root
    templates = _templates_root()
    created: list[str] = []

    root.mkdir(parents=True, exist_ok=True)
    for item in templates.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(templates)
        dest = root / rel
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)
        created.append(rel.as_posix())

    config_path = root / "governance.config.yaml"
    if config_path.is_file():
        text = config_path.read_text(encoding="utf-8")
        updated = text.replace("OPENCLAW_HOME_PLACEHOLDER", str(config.openclaw_home))
        updated = updated.replace("GOVERNANCE_ROOT_PLACEHOLDER", str(root))
        if updated != text:
            config_path.write_text(updated, encoding="utf-8")

    return created

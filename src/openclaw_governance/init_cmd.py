"""Initialize a governance root from templates."""

from __future__ import annotations

import shutil
from importlib import resources
from pathlib import Path

from openclaw_governance.config import GovernanceConfig


def _templates_root() -> Path:
    return Path(resources.files("openclaw_governance")) / "templates"


def run_init(config: GovernanceConfig, *, force: bool = False) -> int:
    root = config.governance_root
    templates = _templates_root()

    if root.exists() and any(root.iterdir()) and not force:
        print(f"ERROR governance root not empty: {root} (use --force to overwrite templates)")
        return 1

    root.mkdir(parents=True, exist_ok=True)

    for item in templates.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(templates)
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not force:
            continue
        shutil.copy2(item, dest)

    # Ensure config references resolved paths.
    config_path = root / "governance.config.yaml"
    if config_path.is_file():
        text = config_path.read_text(encoding="utf-8")
        text = text.replace("OPENCLAW_HOME_PLACEHOLDER", str(config.openclaw_home))
        text = text.replace("GOVERNANCE_ROOT_PLACEHOLDER", str(root))
        config_path.write_text(text, encoding="utf-8")

    print(f"initialized governance root at {root}")
    print("next: openclaw-gov discover   # dry-run inventory")
    print("      openclaw-gov discover --write   # write registry + runbook stubs")
    return 0

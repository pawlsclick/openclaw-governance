"""Resolve OpenClaw and governance directory paths."""

from __future__ import annotations

import os
from pathlib import Path


def expand(path: str) -> Path:
    return Path(os.path.expanduser(path)).resolve()


def default_openclaw_home() -> Path:
    if env := os.environ.get("OPENCLAW_HOME"):
        return expand(env)
    return expand("~/.openclaw")


def openclaw_config_path(openclaw_home: Path) -> Path:
    env_path = os.environ.get("OPENCLAW_CONFIG_PATH")
    if env_path:
        return expand(env_path)
    return openclaw_home / "openclaw.json"


def default_governance_root(openclaw_home: Path) -> Path:
    return openclaw_home / "governance"


def governance_root_from_env() -> Path | None:
    """Governance root from OPENCLAW_GOVERNANCE_ROOT, if set."""
    env = os.environ.get("OPENCLAW_GOVERNANCE_ROOT")
    if env:
        return expand(env)
    return None


def resolve_governance_root(
    *,
    cli_root: Path | str | None = None,
    start: Path | None = None,
) -> Path:
    """Resolve governance root: CLI --root > env > walk-up > ~/.openclaw/governance."""
    if cli_root:
        return Path(cli_root).resolve()
    env_root = governance_root_from_env()
    if env_root is not None:
        return env_root
    found = find_governance_root(start)
    if found is not None:
        return found
    return default_governance_root(default_openclaw_home())


def is_governance_root(directory: Path) -> bool:
    """True when directory looks like an openclaw-gov governance root."""
    if (directory / "governance.config.yaml").is_file():
        return True
    if (directory / "README.md").is_file() and (directory / "workflows" / "registry.yaml").is_file():
        return True
    return False


def find_governance_root(start: Path | None = None) -> Path | None:
    """Walk up from start (or cwd) looking for a governance root."""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if is_governance_root(directory):
            return directory
    return None

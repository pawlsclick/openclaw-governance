"""Environment checks for openclaw-gov."""

from __future__ import annotations

import shutil
import subprocess

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.inject_agents import known_agent_ids
from openclaw_governance.paths import openclaw_config_path
from openclaw_governance.remote import get_git_origin, normalize_git_remote, validate_remote_url

try:
    import yaml  # noqa: F401
except ImportError:
    yaml = None


def run_doctor(config: GovernanceConfig) -> int:
    ok = True

    print(f"OpenClaw home: {config.openclaw_home}")
    print(f"Governance root: {config.governance_root}")

    if not config.openclaw_home.is_dir():
        print(f"WARN openclaw home missing: {config.openclaw_home}")
        ok = False

    cfg_path = openclaw_config_path(config.openclaw_home)
    if cfg_path.is_file():
        print(f"OK openclaw config: {cfg_path}")
    else:
        print(f"WARN openclaw config missing: {cfg_path}")
        ok = False

    if yaml is None:
        print("ERROR PyYAML not installed")
        ok = False
    else:
        print("OK PyYAML available")

    if config.remote_url:
        remote_error = validate_remote_url(config.remote_url)
        if remote_error:
            print(f"ERROR remote.url invalid: {remote_error}")
            ok = False
        else:
            print(f"OK remote.url: {config.remote_url}")
            origin = get_git_origin(config.governance_root)
            if origin is None:
                print("NOTE governance root is not a git repo (or has no origin)")
            elif normalize_git_remote(origin) != normalize_git_remote(config.remote_url):
                print(f"WARN git origin differs from remote.url")
                print(f"     config:  {config.remote_url}")
                print(f"     origin:  {origin}")
            else:
                print("OK git origin matches remote.url")
    else:
        print("NOTE remote.url not set (add under remote: in governance.config.yaml)")

    if config.inject_included is None:
        print("OK agents.inject_included: (omit) — all agents eligible for stanza injection")
    elif not config.inject_included:
        print("OK agents.inject_included: [] — stanza injection disabled unless --agent is passed")
    else:
        print(f"OK agents.inject_included: {', '.join(config.inject_included)}")
        known = known_agent_ids(config)
        unknown = sorted(set(config.inject_included) - known)
        if unknown:
            print(f"WARN unknown agent ids in inject_included: {', '.join(unknown)}")
            ok = False

    if shutil.which("openclaw"):
        try:
            proc = subprocess.run(
                ["openclaw", "--version"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            version = (proc.stdout or proc.stderr or "").strip().splitlines()[0:1]
            print(f"OK openclaw CLI: {version[0] if version else 'found'}")
        except subprocess.TimeoutExpired:
            print("WARN openclaw --version timed out")
    else:
        print("WARN openclaw CLI not on PATH (cron discovery will be skipped)")

    if shutil.which("git"):
        print("OK git available")
    else:
        print("WARN git not on PATH (repo discovery limited)")

    registry = config.registry_path
    if registry.is_file():
        print(f"OK registry: {registry}")
    else:
        print(f"NOTE registry not initialized yet: {registry}")

    readme = config.readme_path
    if readme.is_file():
        print(f"OK README: {readme}")
    else:
        print(f"NOTE README missing (run openclaw-gov init)")

    return 0 if ok else 1

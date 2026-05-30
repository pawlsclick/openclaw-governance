"""Load governance.config.yaml and merge defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from openclaw_governance.paths import default_governance_root, default_openclaw_home, expand
from openclaw_governance.registry_common import DEFAULT_DOMAIN_PREFIX_RULES

DEFAULT_CRON_TIMEOUT_SECONDS = 45
MAX_CRON_TIMEOUT_SECONDS = 120

DEFAULT_CAPABILITY_CHECK_FAIL_ON = ("undocumented_plugin_enabled",)


@dataclass
class CapabilitiesConfig:
    discover_skills: bool = True
    discover_plugins: bool = True
    optional_scan_roots: list[str] = field(default_factory=list)
    expected_skills: list[str] = field(default_factory=list)
    expected_plugins: list[str] = field(default_factory=list)
    exempt_skills: list[str] = field(default_factory=list)
    exempt_plugins: list[str] = field(default_factory=list)
    check_fail_on: list[str] | None = None


@dataclass
class GovernanceConfig:
    openclaw_home: Path
    governance_root: Path
    accountable_humans: list[str] = field(default_factory=list)
    agent_default_accountable: dict[str, str] = field(default_factory=dict)
    raci_broadcast_excluded: list[str] = field(default_factory=list)
    inject_included: list[str] | None = None
    remote_url: str | None = None
    remote_default_branch: str = "main"
    domain_prefix_rules: list[tuple[str, str]] = field(default_factory=lambda: list(DEFAULT_DOMAIN_PREFIX_RULES))
    discovery_scan_git_repos: bool = True
    discovery_scan_workspace_runbooks: bool = True
    discovery_workspace_runbook_glob: str = "**/*runbook*.md"
    discovery_script_globs: list[str] = field(default_factory=lambda: ["scripts/**/*.py", "automation/**/*.py"])
    discovery_cron_timeout_seconds: int = 45
    discovery_sensitive_preview_flags: list[str] = field(default_factory=list)
    require_readme_markers: bool = True
    finance_agent_owner_check: bool = False
    capabilities: CapabilitiesConfig = field(default_factory=CapabilitiesConfig)

    @property
    def registry_path(self) -> Path:
        return self.governance_root / "workflows" / "registry.yaml"

    @property
    def runbooks_dir(self) -> Path:
        return self.governance_root / "workflows" / "runbooks"

    @property
    def readme_path(self) -> Path:
        return self.governance_root / "README.md"


def _parse_prefix_rules(raw: Any) -> list[tuple[str, str]]:
    if not isinstance(raw, list):
        return list(DEFAULT_DOMAIN_PREFIX_RULES)
    rules: list[tuple[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and "prefix" in item and "domain" in item:
            rules.append((str(item["prefix"]), str(item["domain"])))
    return rules or list(DEFAULT_DOMAIN_PREFIX_RULES)


def load_config(
    governance_root: Path | None = None,
    *,
    openclaw_home: Path | None = None,
) -> GovernanceConfig:
    root = governance_root or expand(".")
    config_path = root / "governance.config.yaml"
    data: dict[str, Any] = {}
    if config_path.is_file():
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
            if isinstance(loaded, dict):
                data = loaded

    home = expand(str(data.get("openclaw_home", openclaw_home or default_openclaw_home())))
    gov_root_raw = data.get("governance_root")
    if gov_root_raw:
        gov_root = expand(str(gov_root_raw))
    elif governance_root is not None:
        gov_root = governance_root.resolve()
    else:
        gov_root = default_governance_root(home)

    agents_cfg = data.get("agents") if isinstance(data.get("agents"), dict) else {}
    remote_cfg = data.get("remote") if isinstance(data.get("remote"), dict) else {}
    discovery_cfg = data.get("discovery") if isinstance(data.get("discovery"), dict) else {}

    accountable = data.get("accountable_humans")
    if not isinstance(accountable, list):
        accountable = ["Operator"]

    agent_accountable = data.get("agent_default_accountable")
    if not isinstance(agent_accountable, dict):
        agent_accountable = {}

    excluded = agents_cfg.get("broadcast_excluded") if isinstance(agents_cfg, dict) else None
    if not isinstance(excluded, list):
        excluded = []

    inject_included: list[str] | None = None
    if isinstance(agents_cfg, dict) and "inject_included" in agents_cfg:
        raw_inject = agents_cfg.get("inject_included")
        if isinstance(raw_inject, list):
            inject_included = [str(item) for item in raw_inject]
        else:
            inject_included = []

    remote_url: str | None = None
    if isinstance(remote_cfg, dict):
        raw_url = remote_cfg.get("url")
        if isinstance(raw_url, str) and raw_url.strip():
            remote_url = raw_url.strip()

    remote_branch = "main"
    if isinstance(remote_cfg, dict):
        raw_branch = remote_cfg.get("default_branch")
        if isinstance(raw_branch, str) and raw_branch.strip():
            remote_branch = raw_branch.strip()

    script_globs = discovery_cfg.get("scan_script_globs")
    if not isinstance(script_globs, list):
        script_globs = ["scripts/**/*.py", "automation/**/*.py"]

    raw_timeout = discovery_cfg.get("cron_timeout_seconds", DEFAULT_CRON_TIMEOUT_SECONDS)
    try:
        cron_timeout = int(raw_timeout)
    except (TypeError, ValueError):
        cron_timeout = DEFAULT_CRON_TIMEOUT_SECONDS
    cron_timeout = max(1, min(cron_timeout, MAX_CRON_TIMEOUT_SECONDS))

    extra_sensitive_flags = discovery_cfg.get("sensitive_preview_flags")
    if not isinstance(extra_sensitive_flags, list):
        extra_sensitive_flags = []

    capabilities_cfg = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {}
    optional_roots = capabilities_cfg.get("optional_scan_roots")
    if not isinstance(optional_roots, list):
        optional_roots = []
    expected_skills = capabilities_cfg.get("expected_skills")
    if not isinstance(expected_skills, list):
        expected_skills = []
    expected_plugins = capabilities_cfg.get("expected_plugins")
    if not isinstance(expected_plugins, list):
        expected_plugins = []
    exempt_skills = capabilities_cfg.get("exempt_skills")
    if not isinstance(exempt_skills, list):
        exempt_skills = []
    exempt_plugins = capabilities_cfg.get("exempt_plugins")
    if not isinstance(exempt_plugins, list):
        exempt_plugins = []
    if "check_fail_on" in capabilities_cfg:
        raw_check_fail_on = capabilities_cfg.get("check_fail_on")
        check_fail_on = (
            [str(item) for item in raw_check_fail_on]
            if isinstance(raw_check_fail_on, list)
            else []
        )
    else:
        check_fail_on = None

    capabilities = CapabilitiesConfig(
        discover_skills=bool(capabilities_cfg.get("discover_skills", True)),
        discover_plugins=bool(capabilities_cfg.get("discover_plugins", True)),
        optional_scan_roots=[str(item) for item in optional_roots],
        expected_skills=[str(item) for item in expected_skills],
        expected_plugins=[str(item) for item in expected_plugins],
        exempt_skills=[str(item) for item in exempt_skills],
        exempt_plugins=[str(item) for item in exempt_plugins],
        check_fail_on=[str(item) for item in check_fail_on],
    )

    return GovernanceConfig(
        openclaw_home=home,
        governance_root=gov_root,
        accountable_humans=[str(item) for item in accountable],
        agent_default_accountable={str(k): str(v) for k, v in agent_accountable.items()},
        raci_broadcast_excluded=[str(item) for item in excluded],
        inject_included=inject_included,
        remote_url=remote_url,
        remote_default_branch=remote_branch,
        domain_prefix_rules=_parse_prefix_rules(data.get("domain_prefix_rules")),
        discovery_scan_git_repos=bool(discovery_cfg.get("scan_git_repos", True)),
        discovery_scan_workspace_runbooks=bool(discovery_cfg.get("scan_workspace_runbooks", True)),
        discovery_workspace_runbook_glob=str(
            discovery_cfg.get("scan_workspace_runbook_glob", "**/*runbook*.md")
        ),
        discovery_script_globs=[str(item) for item in script_globs],
        discovery_cron_timeout_seconds=cron_timeout,
        discovery_sensitive_preview_flags=[str(item) for item in extra_sensitive_flags],
        require_readme_markers=bool(data.get("require_readme_markers", True)),
        finance_agent_owner_check=bool(data.get("finance_agent_owner_check", False)),
        capabilities=capabilities,
    )

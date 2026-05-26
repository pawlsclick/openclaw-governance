"""Load governance.config.yaml and merge defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from openclaw_governance.paths import default_governance_root, default_openclaw_home, expand
from openclaw_governance.registry_common import DEFAULT_DOMAIN_PREFIX_RULES


@dataclass
class GovernanceConfig:
    openclaw_home: Path
    governance_root: Path
    accountable_humans: list[str] = field(default_factory=list)
    agent_default_accountable: dict[str, str] = field(default_factory=dict)
    raci_broadcast_excluded: list[str] = field(default_factory=list)
    domain_prefix_rules: list[tuple[str, str]] = field(default_factory=lambda: list(DEFAULT_DOMAIN_PREFIX_RULES))
    discovery_scan_git_repos: bool = True
    discovery_script_globs: list[str] = field(default_factory=lambda: ["scripts/**/*.py", "automation/**/*.py"])
    require_readme_markers: bool = True
    finance_agent_owner_check: bool = False

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

    script_globs = discovery_cfg.get("scan_script_globs")
    if not isinstance(script_globs, list):
        script_globs = ["scripts/**/*.py", "automation/**/*.py"]

    return GovernanceConfig(
        openclaw_home=home,
        governance_root=gov_root,
        accountable_humans=[str(item) for item in accountable],
        agent_default_accountable={str(k): str(v) for k, v in agent_accountable.items()},
        raci_broadcast_excluded=[str(item) for item in excluded],
        domain_prefix_rules=_parse_prefix_rules(data.get("domain_prefix_rules")),
        discovery_scan_git_repos=bool(discovery_cfg.get("scan_git_repos", True)),
        discovery_script_globs=[str(item) for item in script_globs],
        require_readme_markers=bool(data.get("require_readme_markers", True)),
        finance_agent_owner_check=bool(data.get("finance_agent_owner_check", False)),
    )

"""Validate governance.config.yaml semantics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.inject_agents import known_agent_ids
from openclaw_governance.registry_common import load_registry, raci_domains

IssueLevel = Literal["error", "warn"]

KNOWN_TOP_LEVEL_KEYS = frozenset(
    {
        "openclaw_home",
        "governance_root",
        "remote",
        "accountable_humans",
        "agent_default_accountable",
        "agents",
        "discovery",
        "domain_prefix_rules",
        "require_readme_markers",
        "finance_agent_owner_check",
        "raci_workflow_domains",
    }
)


@dataclass(frozen=True)
class ValidationIssue:
    level: IssueLevel
    message: str

    def format(self) -> str:
        prefix = "ERROR" if self.level == "error" else "WARN"
        return f"{prefix} {self.message}"


def validate_config(config: GovernanceConfig, *, config_file: Path | None = None) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    config_path = config_file or (config.governance_root / "governance.config.yaml")

    if not config.accountable_humans:
        issues.append(
            ValidationIssue(
                level="error",
                message="accountable_humans is empty; add at least one human name",
            )
        )

    humans = set(config.accountable_humans)
    for domain_key, domain in raci_domains(_load_registry_if_exists(config)).items():
        accountable = domain.get("accountable")
        if isinstance(accountable, str) and accountable and accountable not in humans:
            issues.append(
                ValidationIssue(
                    level="error",
                    message=(
                        f"raci_domains.{domain_key}.accountable `{accountable}` "
                        f"not listed in accountable_humans"
                    ),
                )
            )

    if config.inject_included:
        known = known_agent_ids(config)
        unknown = sorted(set(config.inject_included) - known)
        if unknown:
            issues.append(
                ValidationIssue(
                    level="error",
                    message=f"agents.inject_included references unknown agent ids: {', '.join(unknown)}",
                )
            )

    if config_path.is_file():
        loaded_root = _config_governance_root_from_file(config_path)
        if loaded_root and loaded_root.resolve() != config.governance_root.resolve():
            issues.append(
                ValidationIssue(
                    level="warn",
                    message=(
                        f"governance.config.yaml at {config_path} sets governance_root={loaded_root} "
                        f"but resolved root is {config.governance_root}"
                    ),
                )
            )
        issues.extend(_unknown_config_keys(config_path))

    return issues


def _load_registry_if_exists(config: GovernanceConfig) -> dict:
    path = config.registry_path
    if not path.is_file():
        return {"raci_domains": {}}
    try:
        return load_registry(path)
    except (OSError, ValueError, yaml.YAMLError):
        return {"raci_domains": {}}


def _config_governance_root_from_file(config_path: Path) -> Path | None:
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        return None
    raw = data.get("governance_root")
    if not isinstance(raw, str) or not raw.strip():
        return None
    return Path(raw).expanduser().resolve()


def _unknown_config_keys(config_path: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        return issues

    for key in data:
        if key not in KNOWN_TOP_LEVEL_KEYS:
            issues.append(
                ValidationIssue(
                    level="warn",
                    message=f"unknown key in governance.config.yaml: {key!r} (typo?)",
                )
            )
    return issues


def run_validate_config(config: GovernanceConfig) -> int:
    issues = validate_config(config)
    if not issues:
        print("OK governance config valid")
        return 0

    errors = [issue for issue in issues if issue.level == "error"]
    for issue in issues:
        print(issue.format())
    return 1 if errors else 0

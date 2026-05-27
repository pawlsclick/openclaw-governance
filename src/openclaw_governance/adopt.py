"""Adopt an existing governance root into a target openclaw-gov instance."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.init_cmd import run_init
from openclaw_governance.paths import is_governance_root
from openclaw_governance.registry_common import load_registry
from openclaw_governance.registry_merge import merge_registry_for_adopt


def _copy_runbooks_if_missing(source_root: Path, target_root: Path) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {"copied": [], "skipped": []}
    source_runbooks = source_root / "workflows" / "runbooks"
    if not source_runbooks.is_dir():
        return summary

    target_runbooks = target_root / "workflows" / "runbooks"
    target_runbooks.mkdir(parents=True, exist_ok=True)

    for path in sorted(source_runbooks.glob("*.md")):
        if not path.is_file():
            continue
        dest = target_runbooks / path.name
        rel = f"workflows/runbooks/{path.name}"
        if dest.is_file():
            summary["skipped"].append(rel)
            continue
        shutil.copy2(path, dest)
        summary["copied"].append(rel)
    return summary


def _merge_config_file(source_root: Path, target_root: Path) -> list[str]:
    warnings: list[str] = []
    source_path = source_root / "governance.config.yaml"
    target_path = target_root / "governance.config.yaml"
    if not source_path.is_file():
        return warnings

    with source_path.open("r", encoding="utf-8") as handle:
        source_data = yaml.safe_load(handle)
    if not isinstance(source_data, dict):
        return warnings

    target_data: dict[str, Any] = {}
    if target_path.is_file():
        with target_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
            if isinstance(loaded, dict):
                target_data = loaded

    source_home = source_data.get("openclaw_home")
    target_home = target_data.get("openclaw_home")
    if source_home and target_home and str(source_home) != str(target_home):
        warnings.append(
            f"openclaw_home differs: source={source_home!r} target={target_home!r} (target kept)"
        )

    for key, value in source_data.items():
        if key not in target_data:
            target_data[key] = value

    target_data.setdefault("governance_root", str(target_root))
    with target_path.open("w", encoding="utf-8") as handle:
        yaml.dump(target_data, handle, sort_keys=False, allow_unicode=True)
    return warnings


def run_adopt(
    config: GovernanceConfig,
    *,
    source_root: Path,
    write: bool = False,
) -> tuple[int, dict[str, Any]]:
    source = source_root.resolve()
    target = config.governance_root.resolve()

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_root": str(source),
        "target_root": str(target),
        "write": write,
    }

    if not is_governance_root(source):
        print(f"ERROR source is not a governance root: {source}")
        print("Expected governance.config.yaml or workflows/registry.yaml")
        return 2, report

    if source == target:
        print(f"ERROR source and target are the same: {source}")
        return 2, report

    source_registry_path = source / "workflows" / "registry.yaml"
    if not source_registry_path.is_file():
        print(f"ERROR source registry missing: {source_registry_path}")
        return 2, report

    source_registry = load_registry(source_registry_path)
    runbook_summary = {"copied": [], "skipped": []}
    registry_summary: dict[str, Any] = {}
    config_warnings: list[str] = []

    if write:
        if not target.exists() or not any(target.iterdir()):
            run_init(config, force=False)
        elif not is_governance_root(target):
            print(f"ERROR target exists but is not a governance root: {target}")
            return 2, report

        runbook_summary = _copy_runbooks_if_missing(source, target)
        config_warnings = _merge_config_file(source, target)

        target_registry_path = target / "workflows" / "registry.yaml"
        if target_registry_path.is_file():
            target_registry = load_registry(target_registry_path)
        else:
            target_registry = {
                "generated_at": report["generated_at"],
                "version": 0.1,
                "source_note": "Initialized by openclaw-gov adopt",
                "agents": [],
                "raci_domains": {},
                "workflows": [],
            }

        backup_path = target / "workflows" / f"registry.pre-adopt-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.yaml"
        if target_registry_path.is_file():
            shutil.copy2(target_registry_path, backup_path)
            report["registry_backup"] = str(backup_path)

        registry_summary = merge_registry_for_adopt(target_registry, source_registry)
        target_registry["generated_at"] = report["generated_at"]
        target_registry_path.parent.mkdir(parents=True, exist_ok=True)
        with target_registry_path.open("w", encoding="utf-8") as handle:
            yaml.dump(target_registry, handle, sort_keys=False, allow_unicode=True)

        report_path = target / "workflows" / f"adoption-report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        report.update(
            {
                "runbooks": runbook_summary,
                "registry": registry_summary,
                "config_warnings": config_warnings,
            }
        )
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["report_path"] = str(report_path)
    else:
        source_workflows = source_registry.get("workflows")
        if not isinstance(source_workflows, list):
            source_workflows = []
        report["would_copy_runbooks"] = len(list((source / "workflows" / "runbooks").glob("*.md")))
        report["source_workflow_count"] = len(source_workflows)
        report["dry_run"] = True

    _print_adoption_report(report)
    return 0, report


def _print_adoption_report(report: dict[str, Any]) -> None:
    print(f"Adoption report at {report['generated_at']}")
    print(f"Source: {report['source_root']}")
    print(f"Target: {report['target_root']}")
    if report.get("dry_run"):
        print("dry-run only (no files written). Use without --dry-run to adopt.")
        print(f"source workflows: {report.get('source_workflow_count', 0)}")
        print(f"runbooks in source: {report.get('would_copy_runbooks', 0)}")
        return

    runbooks = report.get("runbooks") or {}
    print(f"runbooks copied: {len(runbooks.get('copied', []))}")
    print(f"runbooks skipped (already exist): {len(runbooks.get('skipped', []))}")
    reg = report.get("registry") or {}
    print(f"workflows created: {len(reg.get('workflows_created', []))}")
    print(f"workflows updated: {len(reg.get('workflows_updated', []))}")
    print(
        f"workflows skipped (protected status): {len(reg.get('workflows_skipped_protected', []))}"
    )
    print(f"raci_domains added: {reg.get('raci_domains_added', 0)}")
    for warning in report.get("config_warnings") or []:
        print(f"WARN {warning}")
    if report.get("report_path"):
        print(f"report: {report['report_path']}")
    if report.get("registry_backup"):
        print(f"registry backup: {report['registry_backup']}")

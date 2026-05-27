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


PATH_REWRITE_KEYS = frozenset({"governance_root", "openclaw_home"})
SUPPORT_DOC_PATHS = (
    "workflows/CHANGELOG.md",
    "workflows/README.md",
)


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


def _copy_support_docs(source_root: Path, target_root: Path) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {"copied": [], "skipped": []}
    for rel in SUPPORT_DOC_PATHS:
        source_path = source_root / rel
        if not source_path.is_file():
            continue
        dest = target_root / rel
        if dest.is_file():
            summary["skipped"].append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dest)
        summary["copied"].append(rel)

    source_docs = source_root / "docs"
    if source_docs.is_dir():
        target_docs = target_root / "docs"
        target_docs.mkdir(parents=True, exist_ok=True)
        for path in sorted(source_docs.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(source_root).as_posix()
            dest = target_root / rel
            if dest.is_file():
                summary["skipped"].append(rel)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            summary["copied"].append(rel)
    return summary


def _adopt_config_file(
    source_root: Path,
    target_root: Path,
    config: GovernanceConfig,
    *,
    keep_target_config: bool,
) -> dict[str, Any]:
    """Merge governance.config.yaml; source is authoritative unless keep_target_config."""
    diff: dict[str, Any] = {
        "overwritten": [],
        "kept_from_target": [],
        "path_rewrites": {},
        "added_from_source": [],
        "dropped_from_target": [],
    }
    source_path = source_root / "governance.config.yaml"
    target_path = target_root / "governance.config.yaml"
    if not source_path.is_file():
        return diff

    with source_path.open("r", encoding="utf-8") as handle:
        source_data = yaml.safe_load(handle)
    if not isinstance(source_data, dict):
        return diff

    target_data: dict[str, Any] = {}
    if target_path.is_file():
        with target_path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle)
            if isinstance(loaded, dict):
                target_data = loaded

    if keep_target_config:
        merged = dict(target_data)
        for key, value in source_data.items():
            if key not in merged:
                merged[key] = value
                diff["added_from_source"].append(key)
        for key in source_data:
            if key in target_data and target_data[key] != source_data[key]:
                if key not in PATH_REWRITE_KEYS:
                    diff["kept_from_target"].append(key)
    else:
        merged = dict(source_data)
        for key in source_data:
            if key in target_data and target_data[key] != source_data[key]:
                if key in PATH_REWRITE_KEYS:
                    diff["path_rewrites"][key] = {
                        "source": source_data[key],
                        "target_before": target_data[key],
                    }
                else:
                    diff["overwritten"].append(key)
            elif key not in target_data:
                diff["added_from_source"].append(key)
        for key in target_data:
            if key not in source_data:
                diff["dropped_from_target"].append(key)

    merged["governance_root"] = str(target_root)
    merged["openclaw_home"] = str(config.openclaw_home)
    for key, value in (
        ("governance_root", str(target_root)),
        ("openclaw_home", str(config.openclaw_home)),
    ):
        existing = diff["path_rewrites"].get(key)
        if isinstance(existing, dict):
            existing["target_after"] = value
        else:
            diff["path_rewrites"][key] = {"target_after": value}

    with target_path.open("w", encoding="utf-8") as handle:
        yaml.dump(merged, handle, sort_keys=False, allow_unicode=True)
    return diff


def run_adopt(
    config: GovernanceConfig,
    *,
    source_root: Path,
    write: bool = False,
    keep_target_config: bool = False,
) -> tuple[int, dict[str, Any]]:
    source = source_root.resolve()
    target = config.governance_root.resolve()

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_root": str(source),
        "target_root": str(target),
        "write": write,
        "keep_target_config": keep_target_config,
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

    if write:
        if not target.exists() or not any(target.iterdir()):
            run_init(config, force=False)
        elif not is_governance_root(target):
            print(f"ERROR target exists but is not a governance root: {target}")
            return 2, report

        runbook_summary = _copy_runbooks_if_missing(source, target)
        docs_summary = _copy_support_docs(source, target)
        config_diff = _adopt_config_file(
            source,
            target,
            config,
            keep_target_config=keep_target_config,
        )

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

        backup_path = target / "workflows" / (
            f"registry.pre-adopt-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.yaml"
        )
        if target_registry_path.is_file():
            shutil.copy2(target_registry_path, backup_path)
            report["registry_backup"] = str(backup_path)

        registry_summary = merge_registry_for_adopt(
            target_registry,
            source_registry,
            source_authoritative=not keep_target_config,
        )
        target_registry["generated_at"] = report["generated_at"]
        target_registry_path.parent.mkdir(parents=True, exist_ok=True)
        with target_registry_path.open("w", encoding="utf-8") as handle:
            yaml.dump(target_registry, handle, sort_keys=False, allow_unicode=True)

        report_path = target / "workflows" / (
            f"adoption-report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        report.update(
            {
                "runbooks": runbook_summary,
                "docs": docs_summary,
                "registry": registry_summary,
                "config": config_diff,
            }
        )
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        report["report_path"] = str(report_path)
    else:
        source_workflows = source_registry.get("workflows")
        if not isinstance(source_workflows, list):
            source_workflows = []
        source_runbooks = source / "workflows" / "runbooks"
        report["would_copy_runbooks"] = (
            len(list(source_runbooks.glob("*.md"))) if source_runbooks.is_dir() else 0
        )
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
    docs = report.get("docs") or {}
    print(f"docs copied: {len(docs.get('copied', []))}")
    print(f"docs skipped (already exist): {len(docs.get('skipped', []))}")
    reg = report.get("registry") or {}
    print(f"workflows created: {len(reg.get('workflows_created', []))}")
    print(f"workflows updated: {len(reg.get('workflows_updated', []))}")
    print(
        f"workflows skipped (protected status): {len(reg.get('workflows_skipped_protected', []))}"
    )
    print(f"raci_domains added: {reg.get('raci_domains_added', 0)}")
    config_diff = report.get("config") or {}
    if config_diff.get("overwritten"):
        print(f"config keys overwritten from source: {', '.join(config_diff['overwritten'])}")
    if config_diff.get("kept_from_target"):
        print(f"config keys kept from target: {', '.join(config_diff['kept_from_target'])}")
    if report.get("report_path"):
        print(f"report: {report['report_path']}")
    if report.get("registry_backup"):
        print(f"registry backup: {report['registry_backup']}")

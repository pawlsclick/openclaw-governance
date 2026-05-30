"""Governance status classification for skills and plugins."""

from __future__ import annotations

from typing import Any

from openclaw_governance.capability_enrich import shorten_home

GOVERNANCE_STATUSES = frozenset(
    {"expected", "undocumented", "stale", "duplicate", "missing", "exempt"}
)

DEFAULT_CHECK_FAIL_ON = ("undocumented_plugin_enabled",)

FILESYSTEM_SKILL_SOURCES = frozenset({"filesystem-scan", "workspace-scan"})


def _normalize_key(value: str) -> str:
    return value.strip().lower()


def _normalize_path_key(value: str) -> str:
    return shorten_home(value.strip()).lower()


def _config_lookup_keys(value: str) -> set[str]:
    stripped = value.strip()
    if not stripped:
        return set()
    return {_normalize_key(stripped), _normalize_path_key(stripped)}


def classify_skill_record(
    record: dict[str, Any],
    *,
    expected: set[str],
    exempt: set[str],
) -> str:
    flags = record.get("flags") or {}
    if flags.get("duplicate_of"):
        return "duplicate"
    name = _normalize_key(str(record.get("name") or ""))
    path_key = _normalize_path_key(str(record.get("install_path") or ""))
    if name in exempt or path_key in exempt:
        return "exempt"
    if path_key in expected:
        return "expected"
    if name in expected and str(record.get("source") or "") not in FILESYSTEM_SKILL_SOURCES:
        return "expected"
    if flags.get("orphan"):
        return "undocumented"
    if record.get("bundled"):
        return "undocumented"
    return "undocumented"


def classify_plugin_record(
    record: dict[str, Any],
    *,
    expected: set[str],
    exempt: set[str],
) -> str:
    plugin_id = _normalize_key(str(record.get("id") or record.get("name") or ""))
    if plugin_id in exempt:
        return "exempt"
    if plugin_id in expected:
        return "expected"
    return "undocumented"


def apply_skill_governance_statuses(
    skills: list[dict[str, Any]],
    *,
    expected: set[str],
    exempt: set[str],
) -> None:
    expected_norm: set[str] = set()
    exempt_norm: set[str] = set()
    for item in expected:
        expected_norm |= _config_lookup_keys(item)
    for item in exempt:
        exempt_norm |= _config_lookup_keys(item)
    for record in skills:
        if not isinstance(record, dict):
            continue
        record["governance_status"] = classify_skill_record(
            record,
            expected=expected_norm,
            exempt=exempt_norm,
        )


def apply_plugin_governance_statuses(
    plugins: list[dict[str, Any]],
    *,
    expected: set[str],
    exempt: set[str],
) -> None:
    expected_norm = {_normalize_key(item) for item in expected}
    exempt_norm = {_normalize_key(item) for item in exempt}
    for record in plugins:
        if not isinstance(record, dict):
            continue
        record["governance_status"] = classify_plugin_record(
            record,
            expected=expected_norm,
            exempt=exempt_norm,
        )


def summarize_statuses(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        status = str(record.get("governance_status") or "undocumented")
        counts[status] = counts.get(status, 0) + 1
    counts["total"] = len(records)
    return counts


def plugin_is_material(record: dict[str, Any]) -> bool:
    status = str(record.get("status") or "")
    return status == "loaded" or bool(record.get("enabled"))


def skill_is_material(record: dict[str, Any]) -> bool:
    if record.get("bundled"):
        return False
    if record.get("governance_status") == "exempt":
        return False
    return True

"""Registry projection and merge for active OpenClaw skills and plugins."""

from __future__ import annotations

from typing import Any

from openclaw_governance.capability_governance import FILESYSTEM_SKILL_SOURCES

CAPABILITY_SCHEMA_VERSION = 1

PROTECTED_CAPABILITY_GOVERNANCE = frozenset({"expected", "exempt"})
PROTECTED_CAPABILITY_FIELDS = frozenset({"runbook", "notes", "governance_status", "status"})

CAPABILITY_DISCOVERY_REFRESH_FIELDS = (
    "name",
    "type",
    "source",
    "install_path",
    "root_dir",
    "origin",
    "eligible",
    "enabled",
    "agent_id",
    "plugin_id",
    "discovered_at",
    "governance_status",
)


def skill_registry_id(name: str) -> str:
    return f"skill:{name.strip().lower()}"


def plugin_registry_id(plugin_id: str) -> str:
    return f"plugin:{plugin_id.strip().lower()}"


def _capabilities_section(registry: dict[str, Any]) -> dict[str, Any]:
    if isinstance(registry.get("skills"), list) or isinstance(registry.get("plugins"), list):
        section = registry
    else:
        section = registry.get("capabilities")
    if not isinstance(section, dict):
        return {"schema_version": CAPABILITY_SCHEMA_VERSION, "skills": [], "plugins": []}
    skills = section.get("skills")
    plugins = section.get("plugins")
    return {
        "schema_version": section.get("schema_version", CAPABILITY_SCHEMA_VERSION),
        "skills": list(skills) if isinstance(skills, list) else [],
        "plugins": list(plugins) if isinstance(plugins, list) else [],
    }


def is_active_skill(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    if record.get("eligible") is not True:
        return False
    source = str(record.get("source") or "")
    flags = record.get("flags") if isinstance(record.get("flags"), dict) else {}
    if source in FILESYSTEM_SKILL_SOURCES and flags.get("orphan"):
        return False
    return True


def is_active_plugin(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict):
        return False
    status = str(record.get("status") or "")
    return status == "loaded" or bool(record.get("enabled"))


def is_inventory_only_skill(record: dict[str, Any]) -> bool:
    return isinstance(record, dict) and not is_active_skill(record)


def is_inventory_only_plugin(record: dict[str, Any]) -> bool:
    return isinstance(record, dict) and not is_active_plugin(record)


def project_skill_registry_entry(record: dict[str, Any], discovered_at: str) -> dict[str, Any]:
    name = str(record.get("name") or "unnamed")
    governance_status = str(record.get("governance_status") or "undocumented")
    return {
        "id": skill_registry_id(name),
        "name": name,
        "type": str(record.get("type") or "skill"),
        "source": record.get("source"),
        "install_path": record.get("install_path") or None,
        "eligible": True,
        "agent_id": record.get("agent_id"),
        "governance_status": governance_status,
        "runbook": None,
        "discovered_at": discovered_at,
    }


def project_plugin_registry_entry(record: dict[str, Any], discovered_at: str) -> dict[str, Any]:
    plugin_id = str(record.get("id") or record.get("name") or "unnamed")
    governance_status = str(record.get("governance_status") or "undocumented")
    root_dir = record.get("rootDir") or record.get("root_dir")
    return {
        "id": plugin_registry_id(plugin_id),
        "name": str(record.get("name") or plugin_id),
        "type": str(record.get("type") or "plugin"),
        "plugin_id": plugin_id,
        "source": record.get("source"),
        "root_dir": root_dir,
        "origin": record.get("origin"),
        "enabled": True,
        "governance_status": governance_status,
        "runbook": None,
        "discovered_at": discovered_at,
    }


def propose_capability_entries(
    skills: list[dict[str, Any]],
    plugins: list[dict[str, Any]],
    discovered_at: str,
) -> dict[str, Any]:
    proposed_skills = [
        project_skill_registry_entry(record, discovered_at)
        for record in skills
        if isinstance(record, dict) and is_active_skill(record)
    ]
    proposed_plugins = [
        project_plugin_registry_entry(record, discovered_at)
        for record in plugins
        if isinstance(record, dict) and is_active_plugin(record)
    ]
    proposed_skills.sort(key=lambda item: str(item.get("id", "")))
    proposed_plugins.sort(key=lambda item: str(item.get("id", "")))
    return {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "skills": proposed_skills,
        "plugins": proposed_plugins,
    }


def _capability_is_protected(current: dict[str, Any]) -> bool:
    if str(current.get("governance_status") or "") in PROTECTED_CAPABILITY_GOVERNANCE:
        return True
    runbook = str(current.get("runbook") or "").strip()
    return bool(runbook)


def _merge_capability_list(
    existing: list[dict[str, Any]],
    proposed: list[dict[str, Any]],
    *,
    staged: bool,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[str]]:
    by_id = {
        str(item.get("id")): dict(item)
        for item in existing
        if isinstance(item, dict) and item.get("id")
    }
    created: list[str] = []
    updated: list[str] = []
    skipped_protected: list[str] = []

    for entry in proposed:
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            continue
        if entry_id in by_id:
            current = by_id[entry_id]
            if staged and _capability_is_protected(current):
                skipped_protected.append(entry_id)
                for field in CAPABILITY_DISCOVERY_REFRESH_FIELDS:
                    if field in PROTECTED_CAPABILITY_FIELDS:
                        continue
                    if field in entry:
                        current[field] = entry[field]
                continue
            for field in CAPABILITY_DISCOVERY_REFRESH_FIELDS:
                if field in PROTECTED_CAPABILITY_FIELDS and _capability_is_protected(current):
                    continue
                if field in entry:
                    current[field] = entry[field]
            updated.append(entry_id)
        else:
            new_entry = dict(entry)
            if staged:
                new_entry.setdefault("governance_status", "undocumented")
            by_id[entry_id] = new_entry
            created.append(entry_id)

    proposed_ids = {
        str(entry.get("id"))
        for entry in proposed
        if isinstance(entry, dict) and entry.get("id")
    }
    for entry_id in list(by_id):
        if entry_id in proposed_ids:
            continue
        if _capability_is_protected(by_id[entry_id]):
            continue
        del by_id[entry_id]

    merged = sorted(by_id.values(), key=lambda item: str(item.get("id", "")))
    return merged, created, updated, skipped_protected


def merge_capabilities(
    existing: dict[str, Any],
    proposed: dict[str, Any],
    *,
    staged: bool = False,
    merge_skills: bool = True,
    merge_plugins: bool = True,
) -> tuple[dict[str, Any], list[str], list[str], list[str]]:
    """Merge proposed capability entries; preserve curated registry fields when staged."""
    current = _capabilities_section(existing if existing else {})
    prop_skills = proposed.get("skills") if isinstance(proposed.get("skills"), list) else []
    prop_plugins = proposed.get("plugins") if isinstance(proposed.get("plugins"), list) else []

    if merge_skills:
        merged_skills, created_s, updated_s, skipped_s = _merge_capability_list(
            current["skills"],
            prop_skills,
            staged=staged,
        )
    else:
        merged_skills = list(current["skills"])
        created_s, updated_s, skipped_s = [], [], []

    if merge_plugins:
        merged_plugins, created_p, updated_p, skipped_p = _merge_capability_list(
            current["plugins"],
            prop_plugins,
            staged=staged,
        )
    else:
        merged_plugins = list(current["plugins"])
        created_p, updated_p, skipped_p = [], [], []

    merged = {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "skills": merged_skills,
        "plugins": merged_plugins,
    }
    created = created_s + created_p
    updated = updated_s + updated_p
    skipped = skipped_s + skipped_p
    return merged, created, updated, skipped


def _registry_capability_ids(registry: dict[str, Any]) -> tuple[set[str], set[str]]:
    section = _capabilities_section(registry)
    skill_ids = {
        str(item.get("id"))
        for item in section["skills"]
        if isinstance(item, dict) and item.get("id")
    }
    plugin_ids = {
        str(item.get("id"))
        for item in section["plugins"]
        if isinstance(item, dict) and item.get("id")
    }
    return skill_ids, plugin_ids


def build_capability_candidates(
    registry: dict[str, Any],
    *,
    skills: list[dict[str, Any]],
    plugins: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    """Classify capability inventory for staged review without mutating registry."""
    reg_skill_ids, reg_plugin_ids = _registry_capability_ids(registry)
    proposed = propose_capability_entries(skills, plugins, generated_at)

    active_skill_candidates: list[dict[str, Any]] = []
    active_plugin_candidates: list[dict[str, Any]] = []
    drift: list[dict[str, Any]] = []

    inventory_only_skills = 0
    inventory_only_plugins = 0

    for record in skills:
        if not isinstance(record, dict):
            continue
        if is_inventory_only_skill(record):
            inventory_only_skills += 1
            continue
        entry = project_skill_registry_entry(record, generated_at)
        entry_id = str(entry["id"])
        if entry_id not in reg_skill_ids:
            active_skill_candidates.append(
                {
                    "id": entry_id,
                    "name": entry.get("name"),
                    "kind": "active_skill",
                    "governance_status": entry.get("governance_status"),
                }
            )
        if not str(record.get("install_path") or "").strip():
            drift.append(
                {
                    "class": "active_missing_path",
                    "id": entry_id,
                    "name": record.get("name"),
                    "detail": "Eligible skill missing install_path metadata",
                }
            )

    for record in skills:
        if not isinstance(record, dict):
            continue
        flags = record.get("flags") if isinstance(record.get("flags"), dict) else {}
        source = str(record.get("source") or "")
        if source in FILESYSTEM_SKILL_SOURCES and flags.get("orphan"):
            drift.append(
                {
                    "class": "filesystem_only_skill",
                    "id": skill_registry_id(str(record.get("name") or "")),
                    "name": record.get("name"),
                    "detail": "Filesystem skill not visible in runtime inventory",
                }
            )

    for record in plugins:
        if not isinstance(record, dict):
            continue
        if is_inventory_only_plugin(record):
            inventory_only_plugins += 1
            continue
        entry = project_plugin_registry_entry(record, generated_at)
        entry_id = str(entry["id"])
        if entry_id not in reg_plugin_ids:
            active_plugin_candidates.append(
                {
                    "id": entry_id,
                    "plugin_id": entry.get("plugin_id"),
                    "kind": "active_plugin",
                    "governance_status": entry.get("governance_status"),
                }
            )

    seen: set[tuple[str, str]] = set()
    unique_drift: list[dict[str, Any]] = []
    for item in drift:
        key = (str(item.get("class")), str(item.get("id")))
        if key in seen:
            continue
        seen.add(key)
        unique_drift.append(item)

    return {
        "generated_at": generated_at,
        "active_skill_candidates": active_skill_candidates,
        "active_plugin_candidates": active_plugin_candidates,
        "inventory_only": {
            "skills": inventory_only_skills,
            "plugins": inventory_only_plugins,
        },
        "proposed_counts": {
            "skills": len(proposed["skills"]),
            "plugins": len(proposed["plugins"]),
        },
        "drift": unique_drift,
    }


def capability_is_governed(entry: dict[str, Any]) -> bool:
    """True when registry documents governance via runbook (not status alone)."""
    return bool(str(entry.get("runbook") or "").strip())

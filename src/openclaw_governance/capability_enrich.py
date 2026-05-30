"""Filesystem enrichment and drift detection for capability inventory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

SKILL_MARKER = "SKILL.md"
SCOPE_NOTE = (
    "CLI skills list reflects the default agent workspace; per-agent workspace scans "
    "add agent-scoped entries and orphan detection."
)

WORKSPACE_RUNTIME_SOURCE = "openclaw-workspace"
WORKSPACE_SCAN_SOURCE = "workspace-scan"


def shorten_home(path: str) -> str:
    home = Path.home()
    try:
        resolved = Path(path).resolve()
    except OSError:
        return path
    try:
        rel = resolved.relative_to(home)
        return f"~/{rel.as_posix()}"
    except ValueError:
        return str(resolved)


def path_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def infer_skill_type(install_path: Path, source: str) -> str:
    lowered = str(install_path).lower()
    if "plugin-skills" in lowered or "plugin_skills" in lowered:
        return "plugin_skill"
    if ".cursor/skills" in lowered or "codex" in lowered and "/skills" in lowered:
        return "generated_host_skill"
    if source == "openclaw-managed":
        return "skill"
    return "skill"


def scan_skill_tree(
    root: Path,
    agent_id: str,
    *,
    cli_paths: set[str],
    cli_names: set[str],
) -> list[dict[str, Any]]:
    """Find skill directories containing SKILL.md directly under root."""
    records: list[dict[str, Any]] = []
    if not root.is_dir():
        return records
    root_resolved = root.resolve()
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() and not entry.is_symlink():
            continue
        if not (entry / SKILL_MARKER).is_file():
            continue
        try:
            install = entry.resolve()
        except OSError:
            continue
        if not path_within_root(install, root_resolved):
            continue
        install_str = shorten_home(str(install))
        name = entry.name
        in_cli = install_str in cli_paths or name in cli_names
        records.append(
            {
                "name": name,
                "type": infer_skill_type(install, "filesystem"),
                "agent_id": agent_id,
                "install_path": install_str,
                "source": "filesystem-scan",
                "eligible": None,
                "bundled": False,
                "governance_status": "undocumented",
                "flags": {
                    "symlink": entry.is_symlink(),
                    "duplicate_of": None,
                    "orphan": not in_cli,
                },
            }
        )
    return records


def scan_workspace_skills(
    agent_id: str,
    workspace: Path,
    *,
    cli_paths: set[str],
    cli_names: set[str],
) -> list[dict[str, Any]]:
    """Find skill directories under workspace/skills without following symlinks out of root."""
    records: list[dict[str, Any]] = []
    skills_root = workspace / "skills"
    if not skills_root.is_dir():
        return records

    workspace_resolved = workspace.resolve()
    for entry in sorted(skills_root.iterdir()):
        if not entry.is_dir() and not entry.is_symlink():
            continue
        skill_md = entry / SKILL_MARKER
        if not skill_md.is_file() and not (entry / SKILL_MARKER).exists():
            continue
        try:
            install = entry.resolve()
        except OSError:
            continue
        if not path_within_root(install, workspace_resolved):
            continue

        install_str = shorten_home(str(install))
        name = entry.name
        in_cli = install_str in cli_paths or name in cli_names
        records.append(
            {
                "name": name,
                "type": infer_skill_type(install, "workspace"),
                "agent_id": agent_id,
                "install_path": install_str,
                "source": "workspace-scan",
                "eligible": None,
                "bundled": False,
                "governance_status": "undocumented",
                "flags": {
                    "symlink": entry.is_symlink(),
                    "duplicate_of": None,
                    "orphan": not in_cli,
                },
            }
        )
    return records


def mark_duplicate_skills(skills: list[dict[str, Any]]) -> None:
    by_realpath: dict[str, str] = {}
    for record in skills:
        raw_path = str(record.get("install_path") or "").strip()
        if not raw_path:
            # Runtime CLI skills often omit filePath; Path("").resolve() is CWD and
            # falsely marks every pathless skill as a duplicate of the first one seen.
            continue
        try:
            resolved = str(Path(raw_path.replace("~", str(Path.home()))).resolve())
        except OSError:
            continue
        if resolved in by_realpath:
            if not isinstance(record.get("flags"), dict):
                record["flags"] = {}
            record["flags"]["duplicate_of"] = by_realpath[resolved]
        else:
            by_realpath[resolved] = str(record.get("name") or resolved)


def _enrich_workspace_cli_from_scan(cli: dict[str, Any], fs: dict[str, Any]) -> None:
    fs_path = str(fs.get("install_path") or "").strip()
    if fs_path and not str(cli.get("install_path") or "").strip():
        cli["install_path"] = fs_path
    flags = cli.setdefault("flags", {})
    if not isinstance(flags, dict):
        flags = {}
        cli["flags"] = flags
    fs_flags = fs.get("flags") if isinstance(fs.get("flags"), dict) else {}
    if fs_flags.get("symlink"):
        flags["symlink"] = True
    flags["orphan"] = False


def merge_skill_records(
    cli_records: list[dict[str, Any]],
    workspace_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    workspace_cli_by_name: dict[str, dict[str, Any]] = {}
    for record in cli_records:
        if str(record.get("source") or "") != WORKSPACE_RUNTIME_SOURCE:
            continue
        name_key = str(record.get("name") or "").lower()
        if name_key:
            workspace_cli_by_name[name_key] = record

    seen_paths: set[str] = {
        str(item.get("install_path") or "")
        for item in cli_records
        if str(item.get("install_path") or "").strip()
    }
    merged = list(cli_records)
    for record in workspace_records:
        if str(record.get("source") or "") == WORKSPACE_SCAN_SOURCE:
            name_key = str(record.get("name") or "").lower()
            cli_match = workspace_cli_by_name.get(name_key)
            if cli_match is not None:
                _enrich_workspace_cli_from_scan(cli_match, record)
                path_key = str(record.get("install_path") or "")
                if path_key:
                    seen_paths.add(path_key)
                continue

        path_key = str(record.get("install_path") or "")
        if path_key and path_key in seen_paths:
            continue
        merged.append(record)
        if path_key:
            seen_paths.add(path_key)
    mark_duplicate_skills(merged)
    return merged

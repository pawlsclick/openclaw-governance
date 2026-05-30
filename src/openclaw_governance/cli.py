"""openclaw-gov command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openclaw_governance import __version__
from openclaw_governance.adopt import run_adopt
from openclaw_governance.check_capabilities import run_check_capabilities
from openclaw_governance.check_registry import run_check
from openclaw_governance.config import load_config
from openclaw_governance.discover import discover, print_discovery_report
from openclaw_governance.doctor import run_doctor
from openclaw_governance.init_cmd import run_init
from openclaw_governance.inject_agents import run_inject
from openclaw_governance.inventory_artifacts import load_plugins_artifact, load_skills_artifact
from openclaw_governance.discover_plugins import discover_plugins
from openclaw_governance.discover_skills import discover_skills
from openclaw_governance.materialize import materialize_from_discovery
from openclaw_governance.paths import default_governance_root, default_openclaw_home, resolve_governance_root
from openclaw_governance.regen_readme_agent_raci import run_regen_raci
from openclaw_governance.regen_readme_summary import run_regen_summary
from openclaw_governance.ship import run_ship_commit, run_ship_start
from openclaw_governance.validate_config import run_validate_config


def resolve_config(args: argparse.Namespace):
    root = resolve_governance_root(cli_root=getattr(args, "root", None))
    return load_config(root)


def cmd_doctor(args: argparse.Namespace) -> int:
    code = run_doctor(resolve_config(args))
    if getattr(args, "validate_config", False):
        validate_code = run_validate_config(resolve_config(args))
        if validate_code != 0:
            return validate_code
    return code


def cmd_init(args: argparse.Namespace) -> int:
    adopt_from = getattr(args, "adopt", None)
    if adopt_from:
        config = resolve_config(args)
        code, _ = run_adopt(config, source_root=Path(adopt_from), write=not args.dry_run)
        return code

    root = resolve_governance_root(cli_root=getattr(args, "root", None))
    config = load_config(root)
    return run_init(config, force=args.force)


def cmd_adopt(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    code, _ = run_adopt(
        config,
        source_root=Path(args.from_source),
        write=not args.dry_run,
        keep_target_config=getattr(args, "keep_target_config", False),
    )
    return code


def cmd_config_validate(args: argparse.Namespace) -> int:
    return run_validate_config(resolve_config(args))


def _load_allowlist(path: Path) -> set[str]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, dict) and isinstance(data.get("workflow_ids"), list):
        return {str(item) for item in data["workflow_ids"]}
    if isinstance(data, list):
        return {str(item) for item in data}
    raise ValueError(f"allowlist must be a JSON array or object with workflow_ids: {path}")


def _print_discover_materialization(
    summary: dict[str, Any], *, write: bool, staged: bool, promote: bool, file: Any = None
) -> None:
    out = sys.stdout if file is None else file
    if summary.get("promote_hint"):
        print(summary["promote_hint"], file=out)
    if summary.get("plugins_inventory_path"):
        print(f"plugins inventory: {summary.get('plugins_inventory_path')}", file=out)
    if summary.get("skills_inventory_path"):
        print(f"skills inventory: {summary.get('skills_inventory_path')}", file=out)
    if summary.get("skills_summary"):
        print(f"skills summary: {summary.get('skills_summary')}", file=out)
    if summary.get("plugins_summary"):
        print(f"plugins summary: {summary.get('plugins_summary')}", file=out)
    if summary.get("capabilities_read_only"):
        print(summary["capabilities_read_only"], file=out)
    if summary.get("inventory_path"):
        print(f"inventory: {summary.get('inventory_path')}", file=out)
    if summary.get("runtime_path"):
        print(f"runtime metrics: {summary.get('runtime_path')}", file=out)
    if summary.get("candidates_path"):
        print(f"candidates: {summary.get('candidates_path')}", file=out)
        report = summary.get("candidates") or {}
        print(f"candidate count: {report.get('candidate_count', 0)}", file=out)
    if write:
        print("", file=out)
        if summary.get("registry_unchanged"):
            print(f"registry unchanged (no write): {summary.get('registry_path')}", file=out)
        else:
            print(f"wrote registry: {summary.get('registry_path')}", file=out)
        print(f"created workflows: {len(summary.get('created_workflows', []))}", file=out)
        print(f"updated workflows: {len(summary.get('updated_workflows', []))}", file=out)
        if staged or promote:
            skipped = summary.get("skipped_protected_workflows") or []
            print(f"skipped protected workflows: {len(skipped)}", file=out)
        print(f"created runbooks: {len(summary.get('created_runbooks', []))}", file=out)
        scaffolded = summary.get("scaffolded_files") or []
        if scaffolded:
            print(f"scaffolded missing files: {len(scaffolded)} (e.g. README.md)", file=out)
        linked = summary.get("created_workflows_from_runbooks") or []
        if linked:
            print(f"linked registry from existing runbooks: {len(linked)}", file=out)
        imported = summary.get("imported_runbooks") or []
        if imported:
            print(f"imported workspace runbooks: {len(imported)}", file=out)
        skipped_import = summary.get("skipped_imported_runbooks") or []
        if skipped_import:
            print(f"skipped workspace imports (already exist): {len(skipped_import)}", file=out)
        skipped_allowlist = summary.get("skipped_by_allowlist") or []
        if skipped_allowlist:
            skipped_ws = summary.get("skipped_workspace_runbook_candidates") or []
            print(f"skipped by allowlist: {len(skipped_allowlist)}", file=out)
            if skipped_ws:
                print(
                    f"skipped workspace runbook candidates (allowlist): {len(skipped_ws)}",
                    file=out,
                )
        if summary.get("allowlist_empty_warning"):
            print(summary["allowlist_empty_warning"], file=out)
    else:
        print("", file=out)
        if summary.get("read_only"):
            print(
                "Read-only discovery: no governance files written. "
                "Use --inventory to write workflows/discovered-inventory.json, "
                "--staged for inventory + discovery-candidates.json, "
                "or --promote / --write to update registry/runbooks.",
                file=out,
            )
        else:
            print(
                "Registry not written. Use --promote to apply staged merge rules, "
                "or --write for legacy immediate registry + runbook writes.",
                file=out,
            )
        in_gov = summary.get("runbooks_in_governance")
        in_ws = summary.get("runbooks_in_workspaces")
        if in_gov is not None:
            print(f"runbooks in governance root: {in_gov}", file=out)
        if in_ws:
            print(f"runbooks in agent workspaces: {in_ws}", file=out)
        would_link = summary.get("would_link_runbooks") or []
        if would_link:
            print(f"would add registry entries for runbooks: {len(would_link)}", file=out)
        would_import = summary.get("would_import_runbooks") or []
        if would_import:
            print(f"would import workspace runbooks: {len(would_import)}", file=out)
        skipped_allowlist = summary.get("skipped_by_allowlist") or []
        if skipped_allowlist:
            skipped_ws = summary.get("skipped_workspace_runbook_candidates") or []
            print(f"would skip by allowlist: {len(skipped_allowlist)}", file=out)
            if skipped_ws:
                print(
                    f"would skip workspace runbook candidates (allowlist): {len(skipped_ws)}",
                    file=out,
                )
        if summary.get("allowlist_empty_warning"):
            print(summary["allowlist_empty_warning"], file=out)


def cmd_discover(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    result = discover(config)

    allowlist: set[str] | None = None
    allowlist_path = getattr(args, "allowlist", None)
    if allowlist_path:
        allowlist = _load_allowlist(Path(allowlist_path))

    include_runtime_metrics = args.include_runtime_metrics
    write_registry = args.write or args.promote

    summary = materialize_from_discovery(
        result,
        config,
        write=args.write,
        staged=args.staged,
        promote=args.promote,
        allowlist=allowlist,
        write_inventory=args.inventory,
        include_runtime_metrics=include_runtime_metrics,
        include_skills=args.include_skills,
        include_plugins=args.include_plugins,
    )

    if args.json:
        payload = result.to_dict()
        payload["materialization"] = summary
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        print_discovery_report(result, file=sys.stderr)
        _print_discover_materialization(
            summary,
            write=write_registry,
            staged=args.staged,
            promote=args.promote,
            file=sys.stderr,
        )
    else:
        print_discovery_report(result)
        _print_discover_materialization(
            summary,
            write=write_registry,
            staged=args.staged,
            promote=args.promote,
        )
    capabilities_errors = summary.get("capabilities_errors")
    if isinstance(capabilities_errors, list) and capabilities_errors:
        for message in capabilities_errors:
            print(f"ERROR {message}", file=sys.stderr)
        return 1
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    code = run_check(config)
    if code != 0:
        return code
    if args.skills or args.plugins:
        return run_check_capabilities(
            config,
            skills=args.skills,
            plugins=args.plugins,
            live=getattr(args, "live", False),
        )
    return code


def cmd_inventory(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    kind = args.inventory_kind
    live = getattr(args, "live", False)

    if kind == "skills":
        if live:
            if not config.capabilities.discover_skills:
                print(
                    "ERROR inventory skills --live requested but capabilities.discover_skills is false",
                    file=sys.stderr,
                )
                return 1
            result = discover(config)
            payload = discover_skills(config, result.agents, config.capabilities).payload
        else:
            payload = load_skills_artifact(config)
            if payload is None:
                print(
                    "ERROR discovered-skills.json missing; run discover --inventory --include-skills "
                    "or pass --live",
                    file=sys.stderr,
                )
                return 1
            if not payload:
                print("ERROR discovered-skills.json is invalid or empty", file=sys.stderr)
                return 1
    else:
        if live:
            if not config.capabilities.discover_plugins:
                print(
                    "ERROR inventory plugins --live requested but capabilities.discover_plugins is false",
                    file=sys.stderr,
                )
                return 1
            payload = discover_plugins(config, config.capabilities).payload
        else:
            payload = load_plugins_artifact(config)
            if payload is None:
                print(
                    "ERROR discovered-plugins.json missing; run discover --inventory --include-plugins "
                    "or pass --live",
                    file=sys.stderr,
                )
                return 1
            if not payload:
                print("ERROR discovered-plugins.json is invalid or empty", file=sys.stderr)
                return 1

    sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    return 0


def cmd_regen(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    code = run_regen_summary(
        config,
        write=args.write,
        check=args.check,
        include_capabilities=getattr(args, "include_capabilities", False),
    )
    if code != 0:
        return code
    return run_regen_raci(config, write=args.write, check=args.check)


def cmd_inject(args: argparse.Namespace) -> int:
    cli_agents = getattr(args, "agents", None) or None
    return run_inject(
        resolve_config(args),
        write=args.write,
        cli_agents=cli_agents,
        prune=getattr(args, "prune", False),
    )


def _ship_common_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--dry-run", action="store_true", help="Print actions without changing git state")
    parser.add_argument(
        "--base",
        help="Base branch name (default: remote.default_branch from governance.config.yaml)",
    )


def cmd_ship_start(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    return run_ship_start(
        config,
        branch=getattr(args, "branch", None),
        base=getattr(args, "base", None),
        dry_run=args.dry_run,
    )


def cmd_ship_commit(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    return run_ship_commit(
        config,
        message=getattr(args, "message", None),
        base=getattr(args, "base", None),
        push=args.push,
        no_push=args.no_push,
        dry_run=args.dry_run,
    )


def cmd_ship(args: argparse.Namespace) -> int:
    return int(args.ship_func(args))


def cmd_config(args: argparse.Namespace) -> int:
    return int(args.config_func(args))


def _root_argument_help() -> str:
    return (
        "Governance root (directory with governance.config.yaml). "
        "Precedence: --root > OPENCLAW_GOVERNANCE_ROOT > nearest config > ~/.openclaw/governance."
    )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help=_root_argument_help())

    parser = argparse.ArgumentParser(prog="openclaw-gov", description="OpenClaw governance toolkit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", help=_root_argument_help())

    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser(
        "doctor",
        parents=[common],
        help="Check OpenClaw home, CLI, and governance paths",
    )
    doctor_parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Also run governance.config.yaml semantic validation",
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    init_parser = sub.add_parser(
        "init",
        parents=[common],
        help="Initialize governance root from templates",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite template files")
    init_parser.add_argument(
        "--adopt",
        metavar="PATH",
        help="Adopt workflows/registry from an existing governance root (alias for adopt --from)",
    )
    init_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --adopt: preview only, do not write",
    )
    init_parser.set_defaults(func=cmd_init)

    adopt_parser = sub.add_parser(
        "adopt",
        parents=[common],
        help="Copy/merge an existing governance root into the target root",
    )
    adopt_parser.add_argument(
        "--from",
        dest="from_source",
        required=True,
        metavar="PATH",
        help="Existing governance root to adopt from",
    )
    adopt_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview adoption without writing files",
    )
    adopt_parser.add_argument(
        "--keep-target-config",
        action="store_true",
        help="Keep existing target governance.config.yaml values on conflict (default: source wins)",
    )
    adopt_parser.set_defaults(func=cmd_adopt)

    config_parser = sub.add_parser(
        "config",
        parents=[common],
        help="Governance configuration commands",
    )
    config_sub = config_parser.add_subparsers(dest="config_command", required=True)
    config_validate = config_sub.add_parser(
        "validate",
        parents=[common],
        help="Validate governance.config.yaml semantics",
    )
    config_validate.set_defaults(func=cmd_config, config_func=cmd_config_validate)

    discover_parser = sub.add_parser(
        "discover",
        parents=[common],
        help="Discover agents, crons, repos (read-only console summary by default)",
    )
    discover_parser.add_argument(
        "--inventory",
        action="store_true",
        help="Write workflows/discovered-inventory.json (stable snapshot, no registry changes)",
    )
    discover_parser.add_argument(
        "--include-runtime-metrics",
        action="store_true",
        help=(
            "Also write workflows/discovered-inventory-runtime.json with per-run timings "
            "(use with --inventory, --staged, --promote, or --write)"
        ),
    )
    discover_parser.add_argument(
        "--write",
        action="store_true",
        help="Legacy: write registry + runbook stubs (implies --inventory)",
    )
    discover_parser.add_argument(
        "--staged",
        action="store_true",
        help="Write inventory + discovery-candidates.json; do not mutate registry (CI-safe review)",
    )
    discover_parser.add_argument(
        "--promote",
        action="store_true",
        help="Apply staged merge rules and write registry when changed",
    )
    discover_parser.add_argument(
        "--allowlist",
        metavar="PATH",
        help=(
            "JSON workflow id allowlist (array or {workflow_ids: [...]}). "
            "With --promote or --write, only allowlisted workflows are promoted: registry rows, "
            "runbook stubs, and workspace runbook imports. Agents and raci_domains still merge. "
            "Full discovery stays in inventory/candidates; skipped ids are reported."
        ),
    )
    discover_parser.add_argument("--json", action="store_true", help="Print inventory JSON to stdout")
    discover_parser.add_argument(
        "--include-skills",
        action="store_true",
        help="Discover installed skills (writes artifacts with --inventory or --staged)",
    )
    discover_parser.add_argument(
        "--include-plugins",
        action="store_true",
        help="Discover installed plugins (writes artifacts with --inventory or --staged)",
    )
    discover_parser.set_defaults(func=cmd_discover)

    check_parser = sub.add_parser(
        "check",
        parents=[common],
        help="Validate registry, runbooks, and README markers",
    )
    check_parser.add_argument(
        "--skills",
        action="store_true",
        help="Also check discovered-skills.json drift (warn by default for skills)",
    )
    check_parser.add_argument(
        "--plugins",
        action="store_true",
        help="Also check discovered-plugins.json drift (fail on enabled undocumented plugins)",
    )
    check_parser.add_argument(
        "--live",
        action="store_true",
        help="With --skills/--plugins: classify live discovery instead of committed artifacts",
    )
    check_parser.set_defaults(func=cmd_check)

    regen_parser = sub.add_parser(
        "regen",
        parents=[common],
        help="Regenerate README summary and RACI sections",
    )
    regen_parser.add_argument("--write", action="store_true")
    regen_parser.add_argument("--check", action="store_true")
    regen_parser.add_argument(
        "--include-capabilities",
        action="store_true",
        help="Include compact capability counts from committed discovered-*.json in README",
    )
    regen_parser.set_defaults(func=cmd_regen)

    inventory_parser = sub.add_parser(
        "inventory",
        parents=[common],
        help="Print capability inventory JSON from artifacts or live discovery",
    )
    inventory_sub = inventory_parser.add_subparsers(dest="inventory_kind", required=True)
    for kind in ("skills", "plugins"):
        kind_parser = inventory_sub.add_parser(
            kind,
            parents=[common],
            help=f"Print discovered-{kind}.json payload",
        )
        kind_parser.add_argument(
            "--live",
            action="store_true",
            help=f"Run live discovery instead of reading workflows/discovered-{kind}.json",
        )
        kind_parser.add_argument("--json", action="store_true", help="Print JSON (default)")
        kind_parser.set_defaults(func=cmd_inventory, inventory_kind=kind)

    inject_parser = sub.add_parser(
        "inject-agents",
        parents=[common],
        help="Inject governance stanza into agent AGENTS.md files",
    )
    inject_parser.add_argument("--write", action="store_true")
    inject_parser.add_argument(
        "--agent",
        action="append",
        dest="agents",
        metavar="ID",
        help="Inject only this agent (repeatable). Overrides agents.inject_included for this run.",
    )
    inject_parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove governance stanza from agents not in the inject set",
    )
    inject_parser.set_defaults(func=cmd_inject)

    ship_parser = sub.add_parser(
        "ship",
        parents=[common],
        help="Git workflow: branch before governance writes, commit, optional push/PR",
    )
    ship_sub = ship_parser.add_subparsers(dest="ship_command", required=True)

    ship_start = ship_sub.add_parser(
        "start",
        parents=[common],
        help="Create/checkout feature branch from main before governance --write commands",
    )
    _ship_common_flags(ship_start)
    ship_start.add_argument(
        "--branch",
        help="Feature branch name (default: governance/YYYY-MM-DD-sync)",
    )
    ship_start.set_defaults(ship_func=cmd_ship_start)

    ship_commit = ship_sub.add_parser(
        "commit",
        parents=[common],
        help="Validate, stage governance artifacts, conventional commit, optional push/PR",
    )
    _ship_common_flags(ship_commit)
    ship_commit.add_argument("--message", "-m", help="Commit message (default: inferred from changes)")
    ship_commit.add_argument("--push", action="store_true", help="Push branch and open PR without prompting")
    ship_commit.add_argument("--no-push", action="store_true", help="Stop after commit; print push/PR commands")
    ship_commit.set_defaults(ship_func=cmd_ship_commit)

    ship_parser.set_defaults(func=cmd_ship)

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI args; --root may appear before or after the subcommand."""
    parser = build_parser()
    argv_list = list(argv) if argv is not None else sys.argv[1:]

    leading = argparse.ArgumentParser(add_help=False)
    leading.add_argument("--root")
    leading_args, remaining = leading.parse_known_args(argv_list)

    args = parser.parse_args(remaining)
    if leading_args.root and not getattr(args, "root", None):
        args.root = leading_args.root
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

"""openclaw-gov command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openclaw_governance import __version__
from openclaw_governance.check_registry import run_check
from openclaw_governance.config import load_config
from openclaw_governance.discover import discover, print_discovery_report
from openclaw_governance.doctor import run_doctor
from openclaw_governance.init_cmd import run_init
from openclaw_governance.inject_agents import run_inject
from openclaw_governance.materialize import materialize_from_discovery
from openclaw_governance.paths import default_governance_root, default_openclaw_home, find_governance_root
from openclaw_governance.regen_readme_agent_raci import run_regen_raci
from openclaw_governance.regen_readme_summary import run_regen_summary


def resolve_config(args: argparse.Namespace):
    if args.root:
        root = Path(args.root).resolve()
    else:
        root = find_governance_root()
        if root is None:
            root = default_governance_root(default_openclaw_home())
    return load_config(root)


def cmd_doctor(args: argparse.Namespace) -> int:
    return run_doctor(resolve_config(args))


def cmd_init(args: argparse.Namespace) -> int:
    from openclaw_governance.paths import default_governance_root, default_openclaw_home

    root_arg = getattr(args, "root", None)
    if root_arg:
        root = Path(root_arg).resolve()
    else:
        root = default_governance_root(default_openclaw_home())
    config = load_config(root)
    return run_init(config, force=args.force)


def cmd_discover(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    result = discover(config)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print_discovery_report(result)

    summary = materialize_from_discovery(result, config, write=args.write)
    if args.write:
        print("")
        print(f"wrote registry: {summary.get('registry_path')}")
        print(f"inventory: {summary.get('inventory_path')}")
        print(f"created workflows: {len(summary.get('created_workflows', []))}")
        print(f"updated workflows: {len(summary.get('updated_workflows', []))}")
        print(f"created runbooks: {len(summary.get('created_runbooks', []))}")
        scaffolded = summary.get("scaffolded_files") or []
        if scaffolded:
            print(f"scaffolded missing files: {len(scaffolded)} (e.g. README.md)")
        linked = summary.get("created_workflows_from_runbooks") or []
        if linked:
            print(f"linked registry from existing runbooks: {len(linked)}")
        imported = summary.get("imported_runbooks") or []
        if imported:
            print(f"imported workspace runbooks: {len(imported)}")
        skipped_import = summary.get("skipped_imported_runbooks") or []
        if skipped_import:
            print(f"skipped workspace imports (already exist): {len(skipped_import)}")
    else:
        print("")
        print("dry-run only (no files written). Use --write to materialize registry + runbooks.")
        in_gov = summary.get("runbooks_in_governance")
        in_ws = summary.get("runbooks_in_workspaces")
        if in_gov is not None:
            print(f"runbooks in governance root: {in_gov}")
        if in_ws:
            print(f"runbooks in agent workspaces: {in_ws}")
        would_link = summary.get("would_link_runbooks") or []
        if would_link:
            print(f"would add registry entries for runbooks: {len(would_link)}")
        would_import = summary.get("would_import_runbooks") or []
        if would_import:
            print(f"would import workspace runbooks: {len(would_import)}")

    if not args.write and not args.json:
        out = config.governance_root / "workflows" / "discovered-inventory.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result.to_dict(), indent=2) + "\n", encoding="utf-8")
        print(f"inventory snapshot: {out}")

    return 0


def cmd_check(args: argparse.Namespace) -> int:
    return run_check(resolve_config(args))


def cmd_regen(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    code = run_regen_summary(config, write=args.write, check=args.check)
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


def _root_argument_help() -> str:
    return (
        "Governance root (directory with governance.config.yaml). "
        "Default: walk up from cwd or ~/.openclaw/governance."
    )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help=_root_argument_help())

    parser = argparse.ArgumentParser(prog="openclaw-gov", description="OpenClaw governance toolkit")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--root", help=_root_argument_help())

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "doctor",
        parents=[common],
        help="Check OpenClaw home, CLI, and governance paths",
    ).set_defaults(func=cmd_doctor)

    init_parser = sub.add_parser(
        "init",
        parents=[common],
        help="Initialize governance root from templates",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite template files")
    init_parser.set_defaults(func=cmd_init)

    discover_parser = sub.add_parser(
        "discover",
        parents=[common],
        help="Discover agents, crons, repos (dry-run by default)",
    )
    discover_parser.add_argument("--write", action="store_true", help="Write registry + runbook stubs")
    discover_parser.add_argument("--json", action="store_true", help="Print inventory JSON to stdout")
    discover_parser.set_defaults(func=cmd_discover)

    sub.add_parser(
        "check",
        parents=[common],
        help="Validate registry, runbooks, and README markers",
    ).set_defaults(func=cmd_check)

    regen_parser = sub.add_parser(
        "regen",
        parents=[common],
        help="Regenerate README summary and RACI sections",
    )
    regen_parser.add_argument("--write", action="store_true")
    regen_parser.add_argument("--check", action="store_true")
    regen_parser.set_defaults(func=cmd_regen)

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

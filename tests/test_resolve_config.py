"""Tests for governance root resolution in the CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from openclaw_governance.cli import parse_args, resolve_config


def test_resolve_config_defaults_when_only_stray_registry_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Stray ~/workflows/registry.yaml must not become the governance root."""
    openclaw_home = tmp_path / "openclaw"
    openclaw_home.mkdir()
    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))

    cwd = tmp_path / "user-home"
    cwd.mkdir()
    (cwd / "workflows").mkdir()
    (cwd / "workflows" / "registry.yaml").write_text("workflows: []\n", encoding="utf-8")

    expected = openclaw_home / "governance"
    monkeypatch.chdir(cwd)

    config = resolve_config(argparse.Namespace(root=None))
    assert config.governance_root == expected


def test_discover_accepts_root_after_subcommand(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    (gov / "governance.config.yaml").write_text("openclaw_home: /\n", encoding="utf-8")

    args = parse_args(["discover", "--write", "--root", str(gov)])
    assert args.command == "discover"
    assert args.write is True
    assert Path(args.root).resolve() == gov.resolve()


def test_discover_accepts_root_before_subcommand(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()

    args = parse_args(["--root", str(gov), "discover", "--write"])
    assert args.command == "discover"
    assert Path(args.root).resolve() == gov.resolve()


def test_resolve_config_finds_explicit_governance_root(tmp_path: Path, monkeypatch) -> None:
    openclaw_home = tmp_path / "openclaw"
    gov = openclaw_home / "governance"
    gov.mkdir(parents=True)
    (gov / "governance.config.yaml").write_text(
        f"openclaw_home: {openclaw_home}\ngovernance_root: {gov}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))
    monkeypatch.chdir(tmp_path)

    config = resolve_config(argparse.Namespace(root=None))
    assert config.governance_root == gov.resolve()

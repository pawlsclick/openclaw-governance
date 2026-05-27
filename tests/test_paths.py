from pathlib import Path

from openclaw_governance.paths import (
    find_governance_root,
    governance_root_from_env,
    is_governance_root,
    resolve_governance_root,
)


def test_stray_registry_under_home_is_not_governance_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / "workflows").mkdir()
    (home / "workflows" / "registry.yaml").write_text("workflows: []\n", encoding="utf-8")

    assert not is_governance_root(home)
    assert find_governance_root(home) is None


def test_resolve_governance_root_env_override(tmp_path: Path, monkeypatch) -> None:
    env_root = tmp_path / "from-env"
    env_root.mkdir()
    (env_root / "governance.config.yaml").write_text("openclaw_home: /\n", encoding="utf-8")
    monkeypatch.setenv("OPENCLAW_GOVERNANCE_ROOT", str(env_root))
    assert governance_root_from_env() == env_root.resolve()
    assert resolve_governance_root() == env_root.resolve()


def test_resolve_governance_root_cli_beats_env(tmp_path: Path, monkeypatch) -> None:
    env_root = tmp_path / "from-env"
    cli_root = tmp_path / "from-cli"
    env_root.mkdir()
    cli_root.mkdir()
    monkeypatch.setenv("OPENCLAW_GOVERNANCE_ROOT", str(env_root))
    assert resolve_governance_root(cli_root=str(cli_root)) == cli_root.resolve()


def test_governance_root_with_config(tmp_path: Path) -> None:
    root = tmp_path / "gov"
    root.mkdir()
    (root / "governance.config.yaml").write_text("openclaw_home: /\n", encoding="utf-8")
    (root / "workflows").mkdir()
    (root / "workflows" / "registry.yaml").write_text("workflows: []\n", encoding="utf-8")

    assert is_governance_root(root)
    assert find_governance_root(root) == root

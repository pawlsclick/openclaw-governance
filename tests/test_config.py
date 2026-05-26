from pathlib import Path

import yaml

from openclaw_governance.config import load_config


def test_load_config_remote_and_inject(tmp_path: Path) -> None:
    root = tmp_path / "gov"
    root.mkdir()
    config_data = {
        "openclaw_home": str(tmp_path / "oc"),
        "governance_root": str(root),
        "remote": {"url": "https://github.com/you/gov.git", "default_branch": "main"},
        "agents": {"inject_included": ["main", "research"]},
    }
    (root / "governance.config.yaml").write_text(yaml.dump(config_data), encoding="utf-8")

    config = load_config(root)
    assert config.remote_url == "https://github.com/you/gov.git"
    assert config.inject_included == ["main", "research"]


def test_load_config_inject_empty_list(tmp_path: Path) -> None:
    root = tmp_path / "gov"
    root.mkdir()
    (root / "governance.config.yaml").write_text(
        yaml.dump({"agents": {"inject_included": []}}),
        encoding="utf-8",
    )
    config = load_config(root)
    assert config.inject_included == []


def test_load_config_inject_omitted_is_none(tmp_path: Path) -> None:
    root = tmp_path / "gov"
    root.mkdir()
    (root / "governance.config.yaml").write_text("agents: {}\n", encoding="utf-8")
    config = load_config(root)
    assert config.inject_included is None

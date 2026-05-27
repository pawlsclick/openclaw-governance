from pathlib import Path

import yaml

from openclaw_governance.config import GovernanceConfig, load_config
from openclaw_governance.validate_config import validate_config


def test_validate_config_empty_accountable_humans(tmp_path: Path) -> None:
    root = tmp_path / "gov"
    root.mkdir()
    (root / "governance.config.yaml").write_text(
        yaml.dump({"accountable_humans": [], "governance_root": str(root)}),
        encoding="utf-8",
    )
    config = load_config(root)
    issues = validate_config(config)
    assert any(issue.level == "error" and "accountable_humans" in issue.message for issue in issues)


def test_validate_config_unknown_inject_agent(tmp_path: Path, monkeypatch) -> None:
    openclaw_home = tmp_path / "oc"
    openclaw_home.mkdir()
    config_path = openclaw_home / "openclaw.json"
    config_path.write_text('{"agents": {"list": [{"id": "main"}]}}', encoding="utf-8")

    root = tmp_path / "gov"
    root.mkdir()
    (root / "governance.config.yaml").write_text(
        yaml.dump(
            {
                "openclaw_home": str(openclaw_home),
                "governance_root": str(root),
                "agents": {"inject_included": ["missing-agent"]},
            }
        ),
        encoding="utf-8",
    )
    config = load_config(root)
    issues = validate_config(config)
    assert any("unknown agent ids" in issue.message for issue in issues)

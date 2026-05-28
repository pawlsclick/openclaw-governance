from unittest.mock import patch

from openclaw_governance.cli import main
from openclaw_governance.discover import DiscoveredAgent, DiscoveryResult


def test_discover_default_is_read_only(tmp_path, capsys) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    (gov / "governance.config.yaml").write_text(
        f"openclaw_home: {tmp_path / 'oc'}\ngovernance_root: {gov}\n",
        encoding="utf-8",
    )
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[DiscoveredAgent("main", "Main", "role", str(tmp_path / "w"))],
    )

    with patch("openclaw_governance.cli.discover", return_value=result):
        code = main(["discover", "--root", str(gov)])

    assert code == 0
    assert not (gov / "workflows/discovered-inventory.json").exists()
    captured = capsys.readouterr()
    assert "Read-only discovery" in captured.out

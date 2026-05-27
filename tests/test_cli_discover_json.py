import json
from unittest.mock import patch

from openclaw_governance.cli import main
from openclaw_governance.discover import CronJob, DiscoveredAgent, DiscoveryResult


def _minimal_result() -> DiscoveryResult:
    return DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home="/tmp/oc",
        openclaw_config_path="/tmp/oc/openclaw.json",
        agents=[
            DiscoveredAgent(
                agent_id="main",
                name="Main",
                role="agent",
                workspace="/tmp/w",
                cron_jobs=[
                    CronJob(
                        "main",
                        "j1",
                        "test",
                        True,
                        "0 9 * * *",
                        "hello",
                        "abc123",
                        "main\0test\00 9 * * *",
                    )
                ],
            )
        ],
        warnings=["sample warning"],
    )


def test_discover_json_stdout_is_pure_json(tmp_path, capsys) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    (gov / "governance.config.yaml").write_text(
        f"openclaw_home: {tmp_path / 'oc'}\ngovernance_root: {gov}\n",
        encoding="utf-8",
    )

    with patch("openclaw_governance.cli.discover", return_value=_minimal_result()):
        code = main(["discover", "--json", "--root", str(gov)])

    assert code == 0
    captured = capsys.readouterr()
    doc = json.loads(captured.out)
    assert "agents" in doc
    assert "materialization" in doc
    assert "cron_instance_groups" in doc
    assert captured.err.strip()  # human report on stderr

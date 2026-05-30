import json
from pathlib import Path

import pytest

from openclaw_governance.openclaw_cli import run_openclaw_json


def test_run_openclaw_json_uses_file_stdout_not_pipe(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_run(cmd, **kwargs):
        captured["capture_output"] = kwargs.get("capture_output")
        captured["stdout_is_file"] = hasattr(kwargs.get("stdout"), "write")
        stdout = kwargs["stdout"]
        stdout.write('{"skills": [{"name": "big-skill"}]}\n')
        stdout.flush()
        return type("Proc", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("openclaw_governance.openclaw_cli.subprocess.run", fake_run)
    data, err = run_openclaw_json(["skills", "list", "--json"])
    assert err is None
    assert data is not None
    assert data["skills"][0]["name"] == "big-skill"
    assert captured.get("capture_output") is not True
    assert captured.get("stdout_is_file") is True


def test_run_openclaw_json_parses_large_payload(monkeypatch) -> None:
    large_blob = {"skills": [{"name": f"skill-{index}", "description": "x" * 200} for index in range(400)]}

    def fake_run(cmd, **kwargs):
        stdout = kwargs["stdout"]
        stdout.write(json.dumps(large_blob))
        stdout.flush()
        return type("Proc", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr("openclaw_governance.openclaw_cli.subprocess.run", fake_run)
    data, err = run_openclaw_json(["skills", "list", "--json"])
    assert err is None
    assert data is not None
    assert len(data["skills"]) == 400

import json
from pathlib import Path

import pytest

from openclaw_governance.capability_enrich import (
    WORKSPACE_RUNTIME_SOURCE,
    WORKSPACE_SCAN_SOURCE,
    mark_duplicate_skills,
    merge_skill_records,
    scan_workspace_skills,
)
from openclaw_governance.capability_governance import apply_plugin_governance_statuses, apply_skill_governance_statuses
from openclaw_governance.check_capabilities import run_check_capabilities
from openclaw_governance.config import CapabilitiesConfig, GovernanceConfig
from openclaw_governance.discover import DiscoveredAgent, DiscoveryResult
from openclaw_governance.discover_plugins import discover_plugins
from openclaw_governance.discover_skills import discover_skills
from openclaw_governance.materialize import materialize_from_discovery


SKILLS_FIXTURE = {
    "workspaceDir": "/home/user/.openclaw/workspace",
    "managedSkillsDir": "/home/user/.openclaw/skills",
    "skills": [
        {
            "name": "demo-skill",
            "description": "Demo",
            "source": "/home/user/.openclaw/workspace/skills/demo-skill",
            "eligible": True,
            "disabled": False,
            "bundled": False,
            "missing": {"bins": [], "anyBins": [], "env": [], "config": [], "os": []},
        }
    ],
}

PLUGINS_FIXTURE = {
    "workspaceDir": "/home/user/.openclaw/workspace",
    "plugins": [
        {
            "id": "discord",
            "name": "Discord",
            "version": "1.0.0",
            "description": "Discord channel",
            "format": "plugin",
            "source": "/home/user/.openclaw/extensions/discord",
            "rootDir": "/home/user/.openclaw/extensions/discord",
            "origin": "global",
            "status": "loaded",
            "providerIds": [],
            "channelIds": ["discord"],
        }
    ],
    "diagnostics": [{"level": "warn", "message": "secret-path-info"}],
}


@pytest.fixture
def mock_openclaw_json(monkeypatch):
    def _mock(argv, **kwargs):
        joined = " ".join(argv)
        if joined.startswith("skills list"):
            return SKILLS_FIXTURE, None
        if joined.startswith("plugins list"):
            return PLUGINS_FIXTURE, None
        return None, f"unexpected argv: {argv}"

    monkeypatch.setattr("openclaw_governance.discover_skills.run_openclaw_json", _mock)
    monkeypatch.setattr("openclaw_governance.discover_plugins.run_openclaw_json", _mock)
    monkeypatch.setattr("openclaw_governance.discover_skills.openclaw_cli_version", lambda **kwargs: "openclaw 2026.5.0")
    monkeypatch.setattr("openclaw_governance.discover_plugins.openclaw_cli_version", lambda **kwargs: "openclaw 2026.5.0")


def test_discover_skills_projects_cli_and_classifies(tmp_path, mock_openclaw_json) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    workspace = tmp_path / "workspace"
    (workspace / "skills" / "local-skill").mkdir(parents=True)
    (workspace / "skills" / "local-skill" / "SKILL.md").write_text("# Local\n", encoding="utf-8")

    config = GovernanceConfig(
        openclaw_home=tmp_path / "oc",
        governance_root=gov,
        capabilities=CapabilitiesConfig(expected_skills=["demo-skill"]),
    )
    agents = [DiscoveredAgent("main", "Main", "role", str(workspace))]
    result = discover_skills(config, agents, config.capabilities)
    payload = result.payload

    assert payload["capabilities_schema_version"] == 1
    assert "generated_at" not in payload
    names = {item["name"] for item in payload["skills"]}
    assert "demo-skill" in names
    assert "local-skill" in names
    demo = next(item for item in payload["skills"] if item["name"] == "demo-skill")
    assert demo["governance_status"] == "expected"
    local = next(item for item in payload["skills"] if item["name"] == "local-skill")
    assert local["flags"]["orphan"] is True


def test_discover_plugins_strips_diagnostics(mock_openclaw_json) -> None:
    config = GovernanceConfig(
        openclaw_home=Path("/tmp/oc"),
        governance_root=Path("/tmp/gov"),
    )
    result = discover_plugins(config, config.capabilities)
    encoded = json.dumps(result.payload)
    assert "diagnostics" not in encoded
    assert "secret-path-info" not in encoded
    plugin = result.payload["plugins"][0]
    assert plugin["id"] == "discord"
    assert plugin["enabled"] is True


def test_materialize_writes_capability_artifacts_when_staged(tmp_path, mock_openclaw_json) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[DiscoveredAgent("main", "Main", "role", str(tmp_path / "w"))],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(
        result,
        config,
        staged=True,
        include_skills=True,
        include_plugins=True,
    )
    assert summary.get("skills_inventory_path")
    assert summary.get("plugins_inventory_path")
    skills = json.loads((gov / "workflows/discovered-skills.json").read_text(encoding="utf-8"))
    assert skills["summary"]["total"] >= 1


def test_materialize_without_inventory_flags_does_not_write_capabilities(tmp_path, mock_openclaw_json) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[DiscoveredAgent("main", "Main", "role", str(tmp_path / "w"))],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(
        result,
        config,
        include_skills=True,
        include_plugins=True,
    )
    assert "skills_inventory_path" not in summary
    assert not (gov / "workflows/discovered-skills.json").exists()
    assert summary.get("capabilities_read_only")


def test_duplicate_skills_marked() -> None:
    skills = [
        {"name": "a", "install_path": "/tmp/skill-a", "flags": {}},
        {"name": "b", "install_path": "/tmp/skill-a", "flags": {}},
    ]
    mark_duplicate_skills(skills)
    assert skills[1]["flags"]["duplicate_of"] == "a"


def test_mark_duplicate_skills_skips_empty_install_path() -> None:
    skills = [
        {"name": "1password", "install_path": "", "flags": {}},
        {"name": "academic-verify", "install_path": "", "flags": {}},
        {"name": "adler-reading-coach", "install_path": "", "flags": {}},
    ]
    mark_duplicate_skills(skills)
    for record in skills:
        assert record["flags"].get("duplicate_of") is None


def test_merge_enriches_workspace_cli_from_scan() -> None:
    cli_records = [
        {
            "name": "academic-verify",
            "source": WORKSPACE_RUNTIME_SOURCE,
            "install_path": "",
            "flags": {"symlink": False, "duplicate_of": None, "orphan": False},
        }
    ]
    workspace_records = [
        {
            "name": "academic-verify",
            "source": WORKSPACE_SCAN_SOURCE,
            "install_path": "~/.openclaw/workspace/skills/academic-verify",
            "flags": {"symlink": True, "duplicate_of": None, "orphan": False},
        }
    ]
    merged = merge_skill_records(cli_records, workspace_records)
    assert len(merged) == 1
    record = merged[0]
    assert record["source"] == WORKSPACE_RUNTIME_SOURCE
    assert record["install_path"] == "~/.openclaw/workspace/skills/academic-verify"
    assert record["flags"]["symlink"] is True
    assert record["flags"]["orphan"] is False


def test_merge_keeps_orphan_when_no_runtime_match() -> None:
    cli_records = [
        {
            "name": "demo-skill",
            "source": WORKSPACE_RUNTIME_SOURCE,
            "install_path": "",
            "flags": {},
        }
    ]
    workspace_records = [
        {
            "name": "local-only",
            "source": WORKSPACE_SCAN_SOURCE,
            "install_path": "/tmp/workspace/skills/local-only",
            "flags": {"orphan": True},
        }
    ]
    merged = merge_skill_records(cli_records, workspace_records)
    assert len(merged) == 2
    orphan = next(item for item in merged if item["name"] == "local-only")
    assert orphan["flags"]["orphan"] is True


def test_merge_does_not_drop_unrelated_cli() -> None:
    cli_records = [
        {"name": "bundled-skill", "source": "openclaw-bundled", "install_path": "", "flags": {}},
    ]
    workspace_records = [
        {
            "name": "bundled-skill",
            "source": WORKSPACE_SCAN_SOURCE,
            "install_path": "/tmp/workspace/skills/bundled-skill",
            "flags": {},
        }
    ]
    merged = merge_skill_records(cli_records, workspace_records)
    assert len(merged) == 2


def test_discover_skills_merges_workspace_twins(tmp_path, monkeypatch) -> None:
    fixture = {
        "workspaceDir": str(tmp_path / "workspace"),
        "managedSkillsDir": str(tmp_path / "skills"),
        "skills": [
            {
                "name": "academic-verify",
                "description": "Academic verify",
                "source": "openclaw-workspace",
                "eligible": True,
                "disabled": False,
                "bundled": False,
                "missing": {"bins": [], "anyBins": [], "env": [], "config": [], "os": []},
            }
        ],
    }

    def _mock(argv, **kwargs):
        if " ".join(argv).startswith("skills list"):
            return fixture, None
        return None, f"unexpected argv: {argv}"

    monkeypatch.setattr("openclaw_governance.discover_skills.run_openclaw_json", _mock)
    monkeypatch.setattr(
        "openclaw_governance.discover_skills.openclaw_cli_version",
        lambda **kwargs: "openclaw 2026.5.0",
    )

    gov = tmp_path / "gov"
    workspace = tmp_path / "workspace"
    skill_dir = workspace / "skills" / "academic-verify"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Academic verify\n", encoding="utf-8")

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    agents = [DiscoveredAgent("main", "Main", "role", str(workspace))]
    payload = discover_skills(config, agents, config.capabilities).payload

    academic = [item for item in payload["skills"] if item["name"] == "academic-verify"]
    assert len(academic) == 1
    assert academic[0]["source"] == WORKSPACE_RUNTIME_SOURCE
    assert academic[0]["install_path"]
    assert academic[0]["flags"]["orphan"] is False


def test_check_plugins_fails_on_undocumented_enabled(tmp_path, mock_openclaw_json) -> None:
    gov = tmp_path / "gov"
    (gov / "workflows").mkdir(parents=True)
    payload = discover_plugins(
        GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov),
        CapabilitiesConfig(),
    ).payload
    (gov / "workflows/discovered-plugins.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    config = GovernanceConfig(
        openclaw_home=tmp_path / "oc",
        governance_root=gov,
        capabilities=CapabilitiesConfig(check_fail_on=["undocumented_plugin_enabled"]),
    )
    assert run_check_capabilities(config, plugins=True) == 1


def test_check_plugins_passes_when_expected(tmp_path, mock_openclaw_json) -> None:
    gov = tmp_path / "gov"
    (gov / "workflows").mkdir(parents=True)
    config = GovernanceConfig(
        openclaw_home=tmp_path / "oc",
        governance_root=gov,
        capabilities=CapabilitiesConfig(expected_plugins=["discord"]),
    )
    payload = discover_plugins(config, config.capabilities).payload
    (gov / "workflows/discovered-plugins.json").write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    assert run_check_capabilities(config, plugins=True) == 0


def test_discover_skills_marks_degraded_on_cli_failure(tmp_path, monkeypatch) -> None:
    def _fail(argv, **kwargs):
        return None, "openclaw skills list --json JSON parse error: truncated"

    monkeypatch.setattr("openclaw_governance.discover_skills.run_openclaw_json", _fail)
    monkeypatch.setattr(
        "openclaw_governance.discover_skills.openclaw_cli_version",
        lambda **kwargs: "openclaw 2026.5.0",
    )

    gov = tmp_path / "gov"
    workspace = tmp_path / "workspace"
    (workspace / "skills" / "local-skill").mkdir(parents=True)
    (workspace / "skills" / "local-skill" / "SKILL.md").write_text("# Local\n", encoding="utf-8")
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    agents = [DiscoveredAgent("main", "Main", "role", str(workspace))]
    result = discover_skills(config, agents, config.capabilities)

    assert result.payload["cli_capture"] == "failed"
    assert result.payload["degraded"] is True
    assert result.errors
    assert any(item["name"] == "local-skill" for item in result.payload["skills"])


def test_materialize_writes_skills_artifact_on_cli_failure(tmp_path, monkeypatch) -> None:
    def _fail(argv, **kwargs):
        joined = " ".join(argv)
        if joined.startswith("skills list"):
            return None, "openclaw skills list --json JSON parse error: truncated"
        if joined.startswith("plugins list"):
            return {
                "plugins": [{"id": "discord", "name": "Discord", "enabled": True, "status": "loaded"}]
            }, None
        return None, f"unexpected argv: {argv}"

    monkeypatch.setattr("openclaw_governance.discover_skills.run_openclaw_json", _fail)
    monkeypatch.setattr("openclaw_governance.discover_plugins.run_openclaw_json", _fail)
    monkeypatch.setattr(
        "openclaw_governance.discover_skills.openclaw_cli_version",
        lambda **kwargs: "openclaw 2026.5.0",
    )
    monkeypatch.setattr(
        "openclaw_governance.discover_plugins.openclaw_cli_version",
        lambda **kwargs: "openclaw 2026.5.0",
    )

    gov = tmp_path / "gov"
    gov.mkdir()
    workspace = tmp_path / "workspace"
    (workspace / "skills" / "local-skill").mkdir(parents=True)
    (workspace / "skills" / "local-skill" / "SKILL.md").write_text("# Local\n", encoding="utf-8")
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[DiscoveredAgent("main", "Main", "role", str(workspace))],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(
        result,
        config,
        staged=True,
        include_skills=True,
        include_plugins=True,
    )

    assert summary.get("skills_inventory_path")
    assert summary.get("skills_artifact_degraded") is True
    skills = json.loads((gov / "workflows/discovered-skills.json").read_text(encoding="utf-8"))
    assert skills["cli_capture"] == "failed"
    assert skills["degraded"] is True
    assert skills["summary"]["total"] >= 1

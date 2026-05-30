import json

import pytest
import yaml

from openclaw_governance.capability_registry import (
    build_capability_candidates,
    is_active_plugin,
    is_active_skill,
    merge_capabilities,
    propose_capability_entries,
    skill_registry_id,
)
from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import DiscoveredAgent, DiscoveryResult
from openclaw_governance.materialize import materialize_from_discovery
from openclaw_governance.registry_diff import registry_semantic_diff


def _skill(name: str, *, eligible: bool = True, orphan: bool = False, path: str = "") -> dict:
    return {
        "name": name,
        "eligible": eligible,
        "install_path": path,
        "source": "openclaw-workspace" if not orphan else "workspace-scan",
        "governance_status": "undocumented",
        "flags": {"orphan": orphan},
    }


def _plugin(plugin_id: str, *, enabled: bool = True) -> dict:
    return {
        "id": plugin_id,
        "name": plugin_id.title(),
        "enabled": enabled,
        "status": "loaded" if enabled else "disabled",
        "governance_status": "undocumented",
    }


def test_propose_capabilities_filters_active_only() -> None:
    skills = [
        _skill("active-one"),
        _skill("inactive", eligible=False),
        _skill("orphan", orphan=True, path="/tmp/orphan"),
    ]
    plugins = [_plugin("discord"), _plugin("slack", enabled=False)]
    proposed = propose_capability_entries(skills, plugins, "2026-05-30T00:00:00Z")
    assert len(proposed["skills"]) == 1
    assert proposed["skills"][0]["name"] == "active-one"
    assert len(proposed["plugins"]) == 1
    assert proposed["plugins"][0]["plugin_id"] == "discord"


def test_is_active_skill_requires_eligible_true() -> None:
    assert is_active_skill(_skill("x", eligible=True)) is True
    assert is_active_skill(_skill("x", eligible=False)) is False
    assert is_active_plugin(_plugin("x", enabled=True)) is True
    assert is_active_plugin(_plugin("x", enabled=False)) is False


def test_merge_capabilities_preserves_runbook() -> None:
    existing = {
        "schema_version": 1,
        "skills": [
            {
                "id": skill_registry_id("demo"),
                "name": "demo",
                "governance_status": "expected",
                "runbook": "workflows/runbooks/demo.md",
            }
        ],
        "plugins": [],
    }
    proposed = propose_capability_entries([_skill("demo")], [], "2026-05-30T00:00:00Z")
    merged, created, updated, skipped = merge_capabilities(existing, proposed, staged=True)
    skill = merged["skills"][0]
    assert skill["runbook"] == "workflows/runbooks/demo.md"
    assert skill["governance_status"] == "expected"
    assert skill["id"] in skipped or skill["id"] in updated


def test_build_capability_candidates_buckets() -> None:
    registry = {"capabilities": {"skills": [], "plugins": []}}
    skills = [_skill("active"), _skill("bundled", eligible=False), _skill("orphan", orphan=True)]
    plugins = [_plugin("discord"), _plugin("slack", enabled=False)]
    report = build_capability_candidates(
        registry,
        skills=skills,
        plugins=plugins,
        generated_at="2026-05-30T00:00:00Z",
    )
    assert len(report["active_skill_candidates"]) == 1
    assert len(report["active_plugin_candidates"]) == 1
    assert report["inventory_only"]["skills"] == 2
    assert report["inventory_only"]["plugins"] == 1
    assert any(item["class"] == "filesystem_only_skill" for item in report["drift"])


def test_registry_semantic_diff_capabilities() -> None:
    before = {"capabilities": {"schema_version": 1, "skills": [], "plugins": []}}
    after = {
        "capabilities": {
            "schema_version": 1,
            "skills": [{"id": "skill:demo", "name": "demo"}],
            "plugins": [],
        }
    }
    diff = registry_semantic_diff(before, after)
    assert diff["changed"] is True
    assert diff["capabilities"] is True


def test_promote_writes_capabilities_section(tmp_path, monkeypatch) -> None:
    fixture_skills = {
        "skills": [
            {
                "name": "demo-skill",
                "description": "Demo",
                "source": "openclaw-workspace",
                "eligible": True,
                "disabled": False,
                "bundled": False,
                "missing": {"bins": [], "anyBins": [], "env": [], "config": [], "os": []},
            }
        ],
    }
    fixture_plugins = {
        "plugins": [
            {
                "id": "discord",
                "name": "Discord",
                "enabled": True,
                "status": "loaded",
                "source": "/tmp/discord",
                "rootDir": "/tmp/discord",
            }
        ],
    }

    def _mock(argv, **kwargs):
        joined = " ".join(argv)
        if joined.startswith("skills list"):
            return fixture_skills, None
        if joined.startswith("plugins list"):
            return fixture_plugins, None
        return None, f"unexpected argv: {argv}"

    monkeypatch.setattr("openclaw_governance.discover_skills.run_openclaw_json", _mock)
    monkeypatch.setattr("openclaw_governance.discover_plugins.run_openclaw_json", _mock)
    monkeypatch.setattr(
        "openclaw_governance.discover_skills.openclaw_cli_version",
        lambda **kwargs: "openclaw 2026.5.0",
    )
    monkeypatch.setattr(
        "openclaw_governance.discover_plugins.openclaw_cli_version",
        lambda **kwargs: "openclaw 2026.5.0",
    )

    gov = tmp_path / "gov"
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        yaml.dump(
            {
                "generated_at": "2025-01-01T00:00:00Z",
                "version": 0.1,
                "agents": [],
                "raci_domains": {},
                "workflows": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

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
        promote=True,
        include_skills=True,
        include_plugins=True,
    )

    assert summary.get("capability_created")
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert len(registry["capabilities"]["skills"]) == 1
    assert len(registry["capabilities"]["plugins"]) == 1

    # discovery-candidates.json is staged-only; promote writes registry capabilities directly.
    candidates_path = gov / "workflows" / "discovery-candidates.json"
    assert not candidates_path.is_file()


def test_staged_does_not_write_capabilities_to_registry(tmp_path, monkeypatch) -> None:
    def _mock(argv, **kwargs):
        joined = " ".join(argv)
        if joined.startswith("skills list"):
            return {"skills": [{"name": "demo", "eligible": True, "source": "openclaw-workspace"}]}, None
        if joined.startswith("plugins list"):
            return {"plugins": []}, None
        return None, f"unexpected: {argv}"

    monkeypatch.setattr("openclaw_governance.discover_skills.run_openclaw_json", _mock)
    monkeypatch.setattr("openclaw_governance.discover_plugins.run_openclaw_json", _mock)
    monkeypatch.setattr(
        "openclaw_governance.discover_skills.openclaw_cli_version",
        lambda **kwargs: "openclaw 2026.5.0",
    )
    monkeypatch.setattr(
        "openclaw_governance.discover_plugins.openclaw_cli_version",
        lambda **kwargs: "openclaw 2026.5.0",
    )

    gov = tmp_path / "gov"
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    before = {
        "generated_at": "2025-01-01T00:00:00Z",
        "version": 0.1,
        "agents": [],
        "raci_domains": {},
        "workflows": [],
    }
    registry_path.write_text(yaml.dump(before, sort_keys=False), encoding="utf-8")

    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[DiscoveredAgent("main", "Main", "role", str(tmp_path / "w"))],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    materialize_from_discovery(
        result,
        config,
        staged=True,
        include_skills=True,
        include_plugins=True,
    )

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert "capabilities" not in registry

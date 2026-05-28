"""Regression: discover --promote must not rewrite curated agents, RACI, or protected workflows."""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import CronJob, DiscoveredAgent, DiscoveryResult
from openclaw_governance.materialize import materialize_from_discovery


def _curated_registry() -> dict:
    return {
        "generated_at": "2025-01-01T00:00:00Z",
        "version": 0.1,
        "agents": [
            {
                "id": "main",
                "name": "Main Orchestrator",
                "role": "Primary operator agent",
                "workspace": "/curated/main",
                "notes": "Hand-authored agent notes",
            },
            {
                "id": "research",
                "name": "Research Specialist",
                "role": "Deep research",
                "workspace": "/curated/research",
                "repositories": ["https://github.com/example/research"],
            },
        ],
        "raci_domains": {
            "main_ops": {
                "title": "Main operations (curated)",
                "responsible": "main",
                "accountable": "Woodrow",
                "consulted": [],
                "informed": ["research"],
            },
            "finance_ops": {
                "title": "Finance workflows (curated)",
                "responsible": "main",
                "accountable": "Woodrow",
                "consulted": [],
                "informed": [],
            },
        },
        "workflows": [
            {
                "id": "main.cron.daily_brief",
                "status": "active",
                "title": "Daily briefing (curated)",
                "purpose": "Send the morning brief",
                "runtime_status": "active",
                "raci_domain": "main_ops",
                "runbook": "workflows/runbooks/main.cron.daily_brief.md",
                "agent": "main",
            },
            {
                "id": "main.cron.weekly_review",
                "status": "required",
                "title": "Weekly review (curated)",
                "purpose": "Run the weekly review cadence",
                "runtime_status": "active",
                "raci_domain": "main_ops",
                "runbook": "workflows/runbooks/main.cron.weekly_review.md",
                "agent": "main",
            },
        ],
    }


def _discovery_result(tmp_path: Path) -> DiscoveryResult:
    return DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[
            DiscoveredAgent(
                agent_id="main",
                name="main",
                role="generic role from discovery",
                workspace=str(tmp_path / "discovered-main"),
                cron_jobs=[
                    CronJob(
                        "main",
                        "job-daily",
                        "daily_brief",
                        True,
                        "0 7 * * *",
                        "generic daily message",
                        "fp-daily",
                        "gk-daily",
                    ),
                    CronJob(
                        "main",
                        "job-weekly",
                        "weekly_review",
                        True,
                        "0 9 * * 1",
                        "generic weekly message",
                        "fp-weekly",
                        "gk-weekly",
                    ),
                    CronJob(
                        "main",
                        "job-new",
                        "new_cron_job",
                        True,
                        "0 12 * * *",
                        "brand new cron",
                        "fp-new",
                        "gk-new",
                    ),
                ],
            ),
            DiscoveredAgent(
                agent_id="research",
                name="research",
                role="generic research role",
                workspace=str(tmp_path / "discovered-research"),
                cron_jobs=[],
            ),
        ],
    )



def test_staged_reports_protected_drift_without_mutating_registry(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    seed = _curated_registry()
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(yaml.dump(seed, sort_keys=False), encoding="utf-8")
    before_text = registry_path.read_text(encoding="utf-8")

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(_discovery_result(tmp_path), config, staged=True)

    assert registry_path.read_text(encoding="utf-8") == before_text
    classes = {item["class"] for item in summary["candidates"]["candidates"]}
    assert "protected_existing_changed" in classes
    protected = [
        item
        for item in summary["candidates"]["candidates"]
        if item.get("class") == "protected_existing_changed"
    ]
    assert protected
    for item in protected:
        assert item.get("blocked_fields")


def test_promote_preserves_curated_agents_raci_and_protected_workflows(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    seed = _curated_registry()
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(yaml.dump(seed, sort_keys=False), encoding="utf-8")

    before_agents = copy.deepcopy(seed["agents"])
    before_raci = copy.deepcopy(seed["raci_domains"])
    before_protected = {
        item["id"]: copy.deepcopy(item)
        for item in seed["workflows"]
        if item["status"] in {"active", "required"}
    }

    config = GovernanceConfig(
        openclaw_home=tmp_path / "oc",
        governance_root=gov,
        accountable_humans=["Woodrow"],
    )
    allowlist = {"main.cron.new_cron_job"}
    summary = materialize_from_discovery(
        _discovery_result(tmp_path),
        config,
        promote=True,
        allowlist=allowlist,
    )

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))

    assert registry["agents"] == before_agents
    assert registry["raci_domains"] == before_raci

    for workflow_id, expected in before_protected.items():
        actual = next(item for item in registry["workflows"] if item["id"] == workflow_id)
        for key in (
            "title",
            "purpose",
            "status",
            "runtime_status",
            "raci_domain",
            "runbook",
        ):
            assert actual.get(key) == expected.get(key), f"{workflow_id}.{key}"

    assert "main.cron.new_cron_job" in summary["created_workflows"]
    assert "main.cron.daily_brief" not in summary["created_workflows"]
    assert "main.cron.weekly_review" not in summary["updated_workflows"]


def test_promote_skips_runbook_stubs_for_existing_parent_runbooks(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    runbooks_dir = gov / "workflows" / "runbooks"
    runbooks_dir.mkdir(parents=True)
    parent_runbook = runbooks_dir / "main.parent_ops.md"
    parent_runbook.write_text("# Parent runbook\n", encoding="utf-8")

    seed = {
        "generated_at": "2025-01-01T00:00:00Z",
        "version": 0.1,
        "agents": [
            {
                "id": "main",
                "name": "Main Orchestrator",
                "role": "Primary operator agent",
                "workspace": "/curated/main",
            }
        ],
        "raci_domains": {
            "main_ops": {
                "title": "Main operations (curated)",
                "responsible": "main",
                "accountable": "Woodrow",
                "consulted": [],
                "informed": [],
            }
        },
        "workflows": [
            {
                "id": "main.cron.notion_activity_tracker",
                "status": "active",
                "title": "Notion activity tracker (curated)",
                "purpose": "Track Notion activity",
                "runtime_status": "active",
                "raci_domain": "main_ops",
                "runbook": "workflows/runbooks/main.parent_ops.md",
                "agent": "main",
            },
            {
                "id": "main.cron.watch_mattermost_calls_openclaw_voice_call_feature_requests",
                "status": "required",
                "title": "Mattermost voice watch (curated)",
                "purpose": "Watch Mattermost calls",
                "runtime_status": "active",
                "raci_domain": "main_ops",
                "runbook": "workflows/runbooks/main.parent_ops.md",
                "agent": "main",
            },
        ],
    }
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.write_text(yaml.dump(seed, sort_keys=False), encoding="utf-8")
    before_registry_text = registry_path.read_text(encoding="utf-8")

    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[
            DiscoveredAgent(
                agent_id="main",
                name="main",
                role="generic role from discovery",
                workspace=str(tmp_path / "discovered-main"),
                cron_jobs=[
                    CronJob(
                        "main",
                        "job-notion",
                        "notion_activity_tracker",
                        True,
                        "0 7 * * *",
                        "generic notion message",
                        "fp-notion",
                        "gk-notion",
                    ),
                    CronJob(
                        "main",
                        "job-mm",
                        "watch_mattermost_calls_openclaw_voice_call_feature_requests",
                        True,
                        "0 8 * * *",
                        "generic mattermost message",
                        "fp-mm",
                        "gk-mm",
                    ),
                ],
            )
        ],
    )
    config = GovernanceConfig(
        openclaw_home=tmp_path / "oc",
        governance_root=gov,
        accountable_humans=["Woodrow"],
    )

    summary = materialize_from_discovery(result, config, promote=True)

    assert summary.get("registry_unchanged") is True
    assert registry_path.read_text(encoding="utf-8") == before_registry_text
    assert summary["created_runbooks"] == []
    assert not (runbooks_dir / "main.cron.notion_activity_tracker.md").exists()
    assert not (
        runbooks_dir / "main.cron.watch_mattermost_calls_openclaw_voice_call_feature_requests.md"
    ).exists()
    assert parent_runbook.is_file()

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert registry["agents"] == seed["agents"]
    assert registry["raci_domains"] == seed["raci_domains"]
    for expected in seed["workflows"]:
        actual = next(item for item in registry["workflows"] if item["id"] == expected["id"])
        for key in (
            "status",
            "title",
            "purpose",
            "runtime_status",
            "raci_domain",
            "runbook",
        ):
            assert actual.get(key) == expected.get(key)

"""Tests for discover --promote --allowlist filtering all mutation paths."""

from pathlib import Path

import yaml

from openclaw_governance.check_registry import run_check
from openclaw_governance.config import GovernanceConfig
from openclaw_governance.regen_readme_summary import run_regen_summary
from openclaw_governance.discover import (
    CronJob,
    DiscoveredAgent,
    DiscoveredWorkspaceRunbook,
    DiscoveryResult,
)
from openclaw_governance.materialize import materialize_from_discovery


def _empty_registry() -> dict:
    return {
        "generated_at": "2025-01-01T00:00:00Z",
        "version": 0.1,
        "agents": [{"id": "main", "name": "Main", "role": "Agent", "workspace": "/w"}],
        "raci_domains": {},
        "workflows": [],
    }


def _write_governance_config(gov: Path, config: GovernanceConfig) -> None:
    (gov / "governance.config.yaml").write_text(
        f"openclaw_home: {config.openclaw_home}\n"
        f"governance_root: {gov}\n"
        "accountable_humans:\n  - Operator\n",
        encoding="utf-8",
    )


def _discovery_with_cron_and_workspace(tmp_path: Path) -> DiscoveryResult:
    agents = [
        DiscoveredAgent(
            agent_id="main",
            name="Main",
            role="main",
            workspace=str(tmp_path / "workspace"),
            cron_jobs=[
                CronJob(
                    "main",
                    f"j{index}",
                    f"job_{index}",
                    True,
                    "0 9 * * *",
                    "msg",
                    f"fp{index}",
                    f"gk{index}",
                )
                for index in range(15)
            ],
        )
    ]
    workspace_runbooks = [
        DiscoveredWorkspaceRunbook(
            agent_id="main",
            workflow_id=workflow_id,
            title=workflow_id.replace("_", " ").title(),
            source_path=str(tmp_path / "workspace" / f"{workflow_id}.md"),
            workspace_relative=f"{workflow_id}.md",
            target_runbook=f"workflows/runbooks/{workflow_id}.md",
        )
        for workflow_id in (
            "main.current_system_2026_04_25",
            "main.chrome_debug_mcp_2026_04_20",
            "main.cursor_openclaw_2026_04_25",
            "main.google_access_2026_04_20",
            "main.mattermost_christopher_2026_04_19",
            "main.runbook",
        )
    ]
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for item in workspace_runbooks:
        Path(item.source_path).write_text(f"# {item.title}\n", encoding="utf-8")

    return DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=agents,
        workspace_runbooks=workspace_runbooks,
    )


def test_promote_allowlist_only_cron_workflows(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(yaml.dump(_empty_registry(), sort_keys=False), encoding="utf-8")

    result = _discovery_with_cron_and_workspace(tmp_path)
    allowlist = {f"main.cron.job_{index}" for index in range(15)}

    config = GovernanceConfig(
        openclaw_home=tmp_path / "oc",
        governance_root=gov,
        accountable_humans=["Operator"],
    )
    _write_governance_config(gov, config)
    summary = materialize_from_discovery(result, config, promote=True, allowlist=allowlist)

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    workflow_ids = {item["id"] for item in registry["workflows"]}
    assert workflow_ids == allowlist
    assert len(summary["created_workflows"]) == 15
    assert summary["imported_runbooks"] == []
    assert len(summary["skipped_workspace_runbook_candidates"]) == 6
    assert "main.runbook" in summary["skipped_by_allowlist"]

    runbooks_dir = gov / "workflows" / "runbooks"
    created_names = {path.name for path in runbooks_dir.glob("*.md")}
    expected_cron_runbooks = {f"{workflow_id}.md" for workflow_id in allowlist}
    assert expected_cron_runbooks.issubset(created_names)
    for workflow_id in summary["skipped_workspace_runbook_candidates"]:
        assert f"{workflow_id}.md" not in created_names

    orphan = runbooks_dir / "main.system_config_change_governance.md"
    if orphan.is_file() and "main.system_config_change_governance" not in workflow_ids:
        orphan.unlink()

    assert run_regen_summary(config, write=True) == 0
    assert run_check(config) == 0


def test_staged_candidates_remain_full_with_allowlist(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(yaml.dump(_empty_registry(), sort_keys=False), encoding="utf-8")

    result = _discovery_with_cron_and_workspace(tmp_path)
    allowlist = {"main.cron.job_0"}

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(result, config, staged=True, allowlist=allowlist)

    candidates = summary["candidates"]["candidates"]
    classes = {item["class"] for item in candidates}
    assert "missing_active_cron" in classes
    assert "workspace_runbook_candidate" in classes
    assert summary["skipped_by_allowlist"]


def test_dry_run_would_import_respects_allowlist(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(yaml.dump(_empty_registry(), sort_keys=False), encoding="utf-8")

    result = _discovery_with_cron_and_workspace(tmp_path)
    allowlist = {"main.cron.job_0"}

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(result, config, write=False, allowlist=allowlist)

    assert summary["would_import_runbooks"] == []
    assert summary["proposed_workflow_count"] == 1


def test_empty_allowlist_warns_and_promotes_nothing(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(yaml.dump(_empty_registry(), sort_keys=False), encoding="utf-8")

    result = _discovery_with_cron_and_workspace(tmp_path)
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(result, config, promote=True, allowlist=set())

    assert summary.get("allowlist_empty_warning")
    assert summary["created_workflows"] == []
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert registry["workflows"] == []

from pathlib import Path

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import (
    CronJob,
    DiscoveredAgent,
    DiscoveryResult,
    agent_id_from_workflow_id,
    scan_runbooks_on_disk,
)
from openclaw_governance.materialize import materialize_from_discovery


def test_agent_id_from_workflow_id() -> None:
    known = {"main", "finance"}
    assert agent_id_from_workflow_id("main.system_config_change_governance", known) == "main"
    assert agent_id_from_workflow_id("finance.weekly_program_review", known) == "finance"
    assert agent_id_from_workflow_id("platform.notion", known) == "main"


def test_scan_runbooks_on_disk(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    runbooks = gov / "workflows" / "runbooks"
    runbooks.mkdir(parents=True)
    runbook = runbooks / "main.system_config_change_governance.md"
    runbook.write_text(
        "# System Config Change Governance\n\nWorkflow body.\n",
        encoding="utf-8",
    )

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    found = scan_runbooks_on_disk(config, {"main"})
    assert len(found) == 1
    assert found[0].workflow_id == "main.system_config_change_governance"
    assert found[0].title == "System Config Change Governance"
    assert found[0].runbook == "workflows/runbooks/main.system_config_change_governance.md"


def test_materialize_links_existing_runbook(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    runbooks = gov / "workflows" / "runbooks"
    runbooks.mkdir(parents=True)
    (runbooks / "main.workflow_registry_drift_check.md").write_text(
        "# Workflow Registry Drift Check\n",
        encoding="utf-8",
    )

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[],
        runbooks=scan_runbooks_on_disk(config, set()),
    )

    summary = materialize_from_discovery(result, config, write=True)
    assert summary["created_workflows_from_runbooks"] == ["main.workflow_registry_drift_check"]

    registry = yaml.safe_load((gov / "workflows" / "registry.yaml").read_text(encoding="utf-8"))
    workflows = registry["workflows"]
    assert any(item["id"] == "main.workflow_registry_drift_check" for item in workflows)
    assert (gov / "workflows/runbooks/main.workflow_registry_drift_check.md").is_file()


def test_materialize_preserves_existing_runbook_runtime_status(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    runbooks = gov / "workflows" / "runbooks"
    runbooks.mkdir(parents=True)
    (runbooks / "main.workflow_registry_drift_check.md").write_text(
        "# Workflow Registry Drift Check\n",
        encoding="utf-8",
    )
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.write_text(
        yaml.dump(
            {
                "generated_at": "2025-01-01T00:00:00Z",
                "version": 0.1,
                "agents": [],
                "raci_domains": {},
                "workflows": [
                    {
                        "id": "main.workflow_registry_drift_check",
                        "runtime_status": "active",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[],
        runbooks=scan_runbooks_on_disk(config, set()),
    )

    materialize_from_discovery(result, config, write=True)

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    workflow = next(
        item
        for item in registry["workflows"]
        if item["id"] == "main.workflow_registry_drift_check"
    )
    assert workflow["runtime_status"] == "active"


def test_materialize_promotes_matching_runbook_to_cron_workflow(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    runbooks = gov / "workflows" / "runbooks"
    runbooks.mkdir(parents=True)
    (runbooks / "main.cron.workflow_registry_drift_check.md").write_text(
        "# Workflow Registry Drift Check\n",
        encoding="utf-8",
    )

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    initial_result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[],
        runbooks=scan_runbooks_on_disk(config, set()),
    )
    materialize_from_discovery(initial_result, config, write=True)

    agents = [
        DiscoveredAgent(
            agent_id="main",
            name="Main",
            role="main",
            workspace=str(tmp_path),
            cron_jobs=[
                CronJob(
                    agent_id="main",
                    job_id="cron-123",
                    name="workflow_registry_drift_check",
                    enabled=True,
                    schedule="0 6 * * *",
                    message_preview="check registry",
                )
            ],
        )
    ]
    cron_result = DiscoveryResult(
        generated_at="2026-01-02T00:00:00Z",
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path="/tmp/openclaw.json",
        agents=agents,
        runbooks=scan_runbooks_on_disk(config, {"main"}),
    )

    materialize_from_discovery(cron_result, config, write=True)

    registry = yaml.safe_load((gov / "workflows" / "registry.yaml").read_text(encoding="utf-8"))
    workflow = next(
        item
        for item in registry["workflows"]
        if item["id"] == "main.cron.workflow_registry_drift_check"
    )
    assert workflow["orchestration"] == "openclaw_cron"
    assert workflow["trigger"] == "cron/openclaw_cron (0 6 * * *)"
    assert workflow["purpose"] == (
        "Discovered OpenClaw cron job `workflow_registry_drift_check` for agent `main`."
    )
    assert workflow["cron_job_ids"] == ["cron-123"]
    assert workflow["runtime_status"] == "active"
    assert workflow["discovered_from"]["source"] == "openclaw-gov discover"

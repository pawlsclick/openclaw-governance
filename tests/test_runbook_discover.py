from pathlib import Path

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import (
    agent_id_from_workflow_id,
    scan_runbooks_on_disk,
)
from openclaw_governance.materialize import materialize_from_discovery
from openclaw_governance.discover import DiscoveryResult


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

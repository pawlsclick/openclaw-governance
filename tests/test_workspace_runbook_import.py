from pathlib import Path

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import (
    DiscoveredAgent,
    DiscoveryResult,
    scan_workspace_runbooks_for_agents,
)
from openclaw_governance.materialize import import_workspace_runbooks, materialize_from_discovery
from openclaw_governance.runbook_import import (
    render_imported_runbook,
    workflow_id_from_workspace_runbook,
)


def test_workflow_id_from_workspace_runbook() -> None:
    assert workflow_id_from_workspace_runbook("main", Path("google-access-runbook.md")) == "main.google_access"
    assert (
        workflow_id_from_workspace_runbook("main", Path("main.system_config_change_governance.md"))
        == "main.system_config_change_governance"
    )


def test_scan_workspace_runbooks_for_agents(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "plans").mkdir()
    runbook = workspace / "plans" / "daily-wiki-runbook.md"
    runbook.write_text("# Daily Wiki Runbook\n\nSteps here.\n", encoding="utf-8")

    agents = [
        DiscoveredAgent(
            agent_id="main",
            name="Main",
            role="main",
            workspace=str(workspace),
        )
    ]
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=tmp_path / "gov")
    found, warnings = scan_workspace_runbooks_for_agents(agents, config)
    assert not warnings
    assert len(found) == 1
    assert found[0].workflow_id == "main.daily_wiki"
    assert found[0].target_runbook == "workflows/runbooks/main.daily_wiki.md"


def test_import_workspace_runbook_on_write(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "finance-risk-runbook.md"
    source.write_text("# Finance Risk\n\nDo the thing.\n", encoding="utf-8")

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    agents = [
        DiscoveredAgent(agent_id="finance", name="Finance", role="finance", workspace=str(workspace)),
    ]
    found, _ = scan_workspace_runbooks_for_agents(agents, config)
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path="/tmp/openclaw.json",
        agents=agents,
        workspace_runbooks=found,
    )

    summary = materialize_from_discovery(result, config, write=True)
    assert summary["imported_runbooks"] == ["workflows/runbooks/finance.finance_risk.md"]

    dest = gov / "workflows/runbooks/finance.finance_risk.md"
    assert dest.is_file()
    text = dest.read_text(encoding="utf-8")
    assert "Workflow ID: `finance.finance_risk`" in text
    assert "## Imported content" in text
    assert "Do the thing." in text

    registry = yaml.safe_load((gov / "workflows/registry.yaml").read_text(encoding="utf-8"))
    assert any(item["id"] == "finance.finance_risk" for item in registry["workflows"])


def test_skipped_workspace_import_keeps_existing_runbook_metadata(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "daily-report-runbook.md"
    source.write_text("# Daily Report\n\nWorkspace copy.\n", encoding="utf-8")

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    agents = [DiscoveredAgent(agent_id="main", name="Main", role="main", workspace=str(workspace))]
    found, _ = scan_workspace_runbooks_for_agents(agents, config)

    dest = gov / found[0].target_runbook
    dest.parent.mkdir(parents=True)
    dest.write_text("# Daily Report\n\nExisting governance copy.\n", encoding="utf-8")

    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path="/tmp/openclaw.json",
        agents=agents,
        workspace_runbooks=found,
    )

    summary = materialize_from_discovery(result, config, write=True)
    assert summary["skipped_imported_runbooks"] == [found[0].target_runbook]

    registry = yaml.safe_load((gov / "workflows/registry.yaml").read_text(encoding="utf-8"))
    workflow = next(item for item in registry["workflows"] if item["id"] == found[0].workflow_id)
    assert workflow["discovered_from"]["source"] == "runbook_on_disk"
    assert workflow["source_docs"] == [found[0].target_runbook]


def test_discover_dry_run_does_not_import(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "main-test-runbook.md").write_text("# Test\n", encoding="utf-8")

    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    agents = [DiscoveredAgent(agent_id="main", name="Main", role="main", workspace=str(workspace))]
    found, _ = scan_workspace_runbooks_for_agents(agents, config)
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(config.openclaw_home),
        openclaw_config_path="/tmp/openclaw.json",
        agents=agents,
        workspace_runbooks=found,
    )

    summary = materialize_from_discovery(result, config, write=False)
    assert summary["would_import_runbooks"]
    assert summary["would_link_runbooks"] == [found[0].workflow_id]
    assert not list(gov.glob("workflows/runbooks/*.md"))

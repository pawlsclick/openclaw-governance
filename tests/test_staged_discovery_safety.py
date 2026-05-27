from pathlib import Path

import yaml

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import (
    CronJob,
    DiscoveredAgent,
    DiscoveryResult,
)
from openclaw_governance.materialize import materialize_from_discovery
from openclaw_governance.registry_common import (
    agents_for_raci_broadcast,
    default_raci_domains,
    is_governed_workflow_id,
)


def test_staged_does_not_write_registry(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    registry_path = gov / "workflows" / "registry.yaml"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        yaml.dump(
            {
                "generated_at": "2025-01-01T00:00:00Z",
                "version": 0.1,
                "agents": [{"id": "main", "name": "Main"}],
                "raci_domains": {},
                "workflows": [
                    {
                        "id": "main.cron.daily",
                        "status": "active",
                        "title": "Keep",
                        "runtime_status": "active",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    mtime_before = registry_path.stat().st_mtime

    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[
            DiscoveredAgent(
                "main",
                "Main",
                "role",
                str(tmp_path / "w"),
                cron_jobs=[
                    CronJob("main", "j1", "daily", False, "0 9 * * *", "msg", "fp1", "gk")
                ],
            )
        ],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(result, config, staged=True)

    assert registry_path.stat().st_mtime == mtime_before
    assert summary.get("candidates_path")
    assert summary.get("inventory_path")
    assert summary.get("promote_hint")
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert registry["workflows"][0]["runtime_status"] == "active"


def test_promote_writes_registry_when_changed(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
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
        agents=[
            DiscoveredAgent(
                "main",
                "Main",
                "role",
                str(tmp_path / "w"),
                cron_jobs=[
                    CronJob("main", "j1", "daily", True, "0 9 * * *", "msg", "fp1", "gk")
                ],
            )
        ],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(result, config, promote=True)
    assert summary.get("created_workflows")
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    assert any(item["id"] == "main.cron.daily" for item in registry["workflows"])


def test_raci_broadcast_excludes_agents_from_informed() -> None:
    registry = {
        "agents": [
            {"id": "main"},
            {"id": "renewal", "raci_broadcast_excluded": True},
        ],
        "raci_domains": {},
    }
    broadcast = agents_for_raci_broadcast(registry, ["renewal"])
    assert broadcast == ["main"]
    domains = default_raci_domains(broadcast, accountable="Operator")
    informed = domains["personal_ops"]["informed"]
    assert "renewal" not in informed


def test_is_governed_platform_prefix() -> None:
    registry = {
        "workflows": [],
        "platform": {"notion": {"workflows": ["platform.notion"]}},
        "raci_workflow_domains": {"explicit": {}},
    }
    assert is_governed_workflow_id("platform.notion", registry)
    assert is_governed_workflow_id("workflow_registry.agent_raci", registry)
    assert not is_governed_workflow_id("main.workflow_registry_drift_check", registry)

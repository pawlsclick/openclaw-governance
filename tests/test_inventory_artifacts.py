import json

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.discover import (
    CronJob,
    DiscoveredAgent,
    DiscoveryResult,
    cron_instance_group_id,
    parse_cron_jobs,
)
from openclaw_governance.materialize import materialize_from_discovery


def test_inventory_is_stable_without_runtime_fields() -> None:
    schedule = {"expr": "0 0 1 * *", "kind": "cron", "tz": "UTC"}
    result = DiscoveryResult(
        generated_at="2026-05-28T12:00:00Z",
        openclaw_home="/oc",
        openclaw_config_path="/oc/openclaw.json",
        agents=[
            DiscoveredAgent(
                "main",
                "Main",
                "role",
                "/w",
                cron_jobs=[
                    CronJob(
                        "main",
                        "j1",
                        "monthly",
                        True,
                        schedule,
                        "preview",
                        "fp1",
                        cron_instance_group_id("main", "monthly", schedule),
                    )
                ],
            )
        ],
        agent_statuses=[],
    )
    inventory = result.to_inventory_dict()
    assert "generated_at" not in inventory
    assert "agent_statuses" not in inventory
    assert inventory["inventory_schema_version"] == 2
    job = inventory["agents"][0]["cron_jobs"][0]
    assert job["schedule"] == schedule
    assert "group_id" in job
    assert "instance_group_key" not in job
    group = inventory["cron_instance_groups"][0]
    assert group["schedule"] == schedule
    assert "group_id" in group
    assert "group_key" not in group
    encoded = json.dumps(inventory)
    assert "\u0000" not in encoded
    assert "\\u0000" not in encoded


def test_parse_cron_jobs_structured_schedule_and_legacy_string() -> None:
    structured = parse_cron_jobs(
        "main",
        [
            {
                "id": "a",
                "name": "cron-a",
                "enabled": True,
                "schedule": {"expr": "0 9 * * *", "kind": "cron", "tz": "UTC"},
                "payload": {"message": "hello"},
            }
        ],
    )
    assert structured[0].schedule == {"expr": "0 9 * * *", "kind": "cron", "tz": "UTC"}

    legacy = parse_cron_jobs(
        "main",
        [
            {
                "id": "b",
                "name": "cron-b",
                "enabled": True,
                "schedule": "0 10 * * *",
                "payload": {"message": "hello"},
            }
        ],
    )
    assert legacy[0].schedule == "0 10 * * *"


def test_plain_materialize_does_not_write_inventory(tmp_path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[DiscoveredAgent("main", "Main", "role", str(tmp_path / "w"))],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(result, config)
    assert "inventory_path" not in summary
    assert not (gov / "workflows/discovered-inventory.json").exists()


def test_runtime_metrics_file_optional(tmp_path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path="/tmp/openclaw.json",
        agents=[DiscoveredAgent("main", "Main", "role", str(tmp_path / "w"))],
        agent_statuses=[],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)
    summary = materialize_from_discovery(
        result,
        config,
        staged=True,
        include_runtime_metrics=True,
    )
    runtime_path = gov / "workflows/discovered-inventory-runtime.json"
    assert summary.get("runtime_path") == str(runtime_path)
    runtime = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert runtime["generated_at"] == result.generated_at
    assert "agent_statuses" in runtime
    inventory = json.loads((gov / "workflows/discovered-inventory.json").read_text(encoding="utf-8"))
    assert "generated_at" not in inventory

from openclaw_governance.discover import (
    DiscoveryResult,
    DiscoveredAgent,
    CronJob,
    cron_fingerprint,
    cron_instance_group_id,
    parse_cron_jobs,
    slugify,
    workflow_id_for_cron,
)
from openclaw_governance.materialize import materialize_from_discovery
from openclaw_governance.config import GovernanceConfig


def test_slugify() -> None:
    assert slugify("Daily Wiki Refresh") == "daily_wiki_refresh"
    assert slugify("") == "unnamed"


def test_workflow_id_for_cron() -> None:
    assert workflow_id_for_cron("main", "daily-wiki-refresh") == "main.cron.daily_wiki_refresh"


def test_parse_cron_jobs_dedupes_exact_repeats_only() -> None:
    jobs = [
        {"id": "job-1", "name": "Alpha", "enabled": True, "schedule": "0 9 * * *", "payload": {"message": "a"}},
        {"id": "job-1", "name": "Alpha", "enabled": True, "schedule": "0 9 * * *", "payload": {"message": "a"}},
        {"id": "job-2", "name": "Beta", "enabled": True, "schedule": "0 10 * * *", "payload": {"message": "b"}},
        {"id": "", "name": "job-2", "enabled": True, "schedule": "0 11 * * *", "payload": {"message": "c"}},
    ]
    parsed = parse_cron_jobs("main", jobs)
    assert len(parsed) == 3
    assert [job.job_id for job in parsed] == ["job-1", "job-2", ""]
    assert [job.name for job in parsed] == ["Alpha", "Beta", "job-2"]


def test_cron_instance_groups_in_discovery_dict() -> None:
    schedule = {"expr": "0 9 * * *", "kind": "cron"}
    group_id = cron_instance_group_id("main", "sync", schedule)
    job_a = CronJob(
        agent_id="main",
        job_id="j1",
        name="sync",
        enabled=True,
        schedule=schedule,
        message_preview="a",
        fingerprint="fp1",
        group_id=group_id,
    )
    job_b = CronJob(
        agent_id="main",
        job_id="j2",
        name="sync",
        enabled=True,
        schedule=schedule,
        message_preview="b",
        fingerprint="fp2",
        group_id=group_id,
    )
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home="/oc",
        openclaw_config_path="/oc/openclaw.json",
        agents=[DiscoveredAgent(agent_id="main", name="Main", role="r", workspace="/w", cron_jobs=[job_a, job_b])],
    )
    groups = result.cron_instance_groups()
    assert len(groups) == 1
    assert groups[0]["kind"] == "fan_out"
    assert groups[0]["job_count"] == 2


def test_materialize_groups_cron_jobs_into_one_workflow(tmp_path) -> None:
    schedule = {"expr": "0 9 * * *", "kind": "cron"}
    group_id = cron_instance_group_id("main", "fan", schedule)
    jobs = [
        CronJob("main", "j1", "fan", True, schedule, "one", "fp1", group_id),
        CronJob("main", "j2", "fan", True, schedule, "two", "fp2", group_id),
    ]
    result = DiscoveryResult(
        generated_at="2026-01-01T00:00:00Z",
        openclaw_home=str(tmp_path / "oc"),
        openclaw_config_path=str(tmp_path / "oc" / "openclaw.json"),
        agents=[DiscoveredAgent("main", "Main", "role", str(tmp_path / "w"), cron_jobs=jobs)],
    )
    config = GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=tmp_path / "gov")
    summary = materialize_from_discovery(result, config, write=False, staged=True)
    assert summary["proposed_workflow_count"] == 1

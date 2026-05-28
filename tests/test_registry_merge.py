from pathlib import Path

from openclaw_governance.discover import cron_fingerprint, parse_cron_jobs
from openclaw_governance.registry_merge import merge_agents, merge_workflows


def _job(
    *,
    job_id: str,
    name: str,
    message: str,
    schedule: dict | str = "0 9 * * *",
) -> dict:
    sched = schedule if isinstance(schedule, dict) else {"kind": "cron", "expr": schedule}
    return {
        "id": job_id,
        "name": name,
        "enabled": True,
        "schedule": sched,
        "payload": {"message": message},
    }


def test_cron_fingerprint_stable() -> None:
    job = _job(job_id="a", name="daily", message="hello")
    a = cron_fingerprint("main", job)
    b = cron_fingerprint("main", dict(job))
    assert a == b


def test_cron_fingerprint_differs_when_payload_suffix_differs() -> None:
    job_a = _job(job_id="job-1", name="daily", message="prefix shared tail A")
    job_b = _job(job_id="job-2", name="daily", message="prefix shared tail B")
    assert cron_fingerprint("main", job_a) != cron_fingerprint("main", job_b)


def test_parse_cron_jobs_dedupes_exact_duplicates_only() -> None:
    jobs = [
        _job(job_id="job-1", name="Alpha", message="same"),
        _job(job_id="job-1", name="Alpha", message="same"),
        _job(job_id="job-2", name="Alpha", message="different payload"),
    ]
    warnings: list[str] = []
    parsed = parse_cron_jobs("main", jobs, warnings=warnings)
    assert len(parsed) == 2
    assert any("EXACT DUPLICATE CRON" in warning for warning in warnings)


def test_parse_cron_jobs_keeps_fan_out_instances() -> None:
    jobs = [
        _job(job_id="job-1", name="fan", message="params=one"),
        _job(job_id="job-2", name="fan", message="params=two"),
    ]
    parsed = parse_cron_jobs("main", jobs)
    assert len(parsed) == 2
    assert parsed[0].instance_group_key == parsed[1].instance_group_key
    assert parsed[0].fingerprint != parsed[1].fingerprint


def test_merge_workflows_unions_cron_job_ids() -> None:
    existing = [
        {
            "id": "main.cron.daily",
            "status": "discovered",
            "cron_job_ids": ["job-1"],
            "cron_fingerprint": "abc",
        }
    ]
    proposed = [
        {
            "id": "main.cron.daily",
            "status": "discovered",
            "cron_job_ids": ["job-2"],
            "cron_fingerprint": "def",
            "discovered_from": {"cron_instances": [{"job_id": "job-2", "fingerprint": "def"}]},
        }
    ]
    merged, _created, updated, _skipped = merge_workflows(existing, proposed, staged=True)
    row = merged[0]
    assert updated == ["main.cron.daily"]
    assert sorted(row["cron_job_ids"]) == ["job-1", "job-2"]


def test_merge_workflows_staged_skips_active_without_cron_union() -> None:
    existing = [
        {
            "id": "main.cron.daily",
            "status": "active",
            "title": "Hand-authored title",
            "purpose": "Do not overwrite",
            "runtime_status": "active",
            "cron_job_ids": ["job-1"],
        }
    ]
    proposed = [
        {
            "id": "main.cron.daily",
            "status": "discovered",
            "title": "Discovered title",
            "purpose": "Would overwrite",
            "runtime_status": "disabled",
            "cron_job_ids": ["job-2"],
        }
    ]
    merged, created, updated, skipped = merge_workflows(existing, proposed, staged=True)
    assert created == []
    assert updated == []
    assert skipped == ["main.cron.daily"]
    row = merged[0]
    assert row["title"] == "Hand-authored title"
    assert row["runtime_status"] == "active"
    assert row["cron_job_ids"] == ["job-1"]


def test_merge_agents_preserves_notes() -> None:
    existing = [{"id": "main", "name": "Main", "notes": "keep me"}]
    proposed = [{"id": "main", "name": "Updated Main", "workspace": "/new/path"}]
    merged = merge_agents(existing, proposed)
    assert merged[0]["notes"] == "keep me"
    assert merged[0]["workspace"] == "/new/path"

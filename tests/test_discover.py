from openclaw_governance.discover import parse_cron_jobs, slugify, workflow_id_for_cron


def test_slugify() -> None:
    assert slugify("Daily Wiki Refresh") == "daily_wiki_refresh"
    assert slugify("") == "unnamed"


def test_workflow_id_for_cron() -> None:
    assert workflow_id_for_cron("main", "daily-wiki-refresh") == "main.cron.daily_wiki_refresh"


def test_parse_cron_jobs_dedupes_exact_repeats_only() -> None:
    jobs = [
        {"id": "job-1", "name": "Alpha", "enabled": True},
        {"id": "job-1", "name": "Alpha", "enabled": True},
        {"id": "job-2", "name": "Alpha", "enabled": True},
        {"id": "", "name": "job-2", "enabled": True},
    ]
    parsed = parse_cron_jobs("main", jobs)
    assert len(parsed) == 3
    assert [job.job_id for job in parsed] == ["job-1", "job-2", ""]
    assert [job.name for job in parsed] == ["Alpha", "Alpha", "job-2"]

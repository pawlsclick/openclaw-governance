from pathlib import Path

from openclaw_governance.discover import cron_fingerprint, parse_cron_jobs
from openclaw_governance.registry_merge import merge_agents, merge_workflows


def test_cron_fingerprint_stable() -> None:
    a = cron_fingerprint("main", "daily", '{"kind":"cron"}', "hello")
    b = cron_fingerprint("main", "daily", '{"kind":"cron"}', "hello")
    c = cron_fingerprint("main", "daily", '{"kind":"cron"}', "hello world")
    assert a == b
    assert a != c


def test_parse_cron_jobs_dedupes_by_fingerprint() -> None:
    jobs = [
        {
            "id": "job-1",
            "name": "Alpha",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * *"},
            "payload": {"message": "same payload"},
        },
        {
            "id": "job-2",
            "name": "Alpha",
            "enabled": True,
            "schedule": {"kind": "cron", "expr": "0 9 * * *"},
            "payload": {"message": "same payload"},
        },
    ]
    warnings: list[str] = []
    parsed = parse_cron_jobs("main", jobs, warnings=warnings)
    assert len(parsed) == 1
    assert any("DUPLICATE CRON" in warning for warning in warnings)


def test_merge_workflows_staged_skips_active() -> None:
    existing = [
        {
            "id": "main.cron.daily",
            "status": "active",
            "title": "Hand-authored title",
            "purpose": "Do not overwrite",
            "runtime_status": "active",
        }
    ]
    proposed = [
        {
            "id": "main.cron.daily",
            "status": "discovered",
            "title": "Discovered title",
            "purpose": "Would overwrite",
            "runtime_status": "disabled",
        }
    ]
    merged, created, updated, skipped = merge_workflows(existing, proposed, staged=True)
    assert created == []
    assert skipped == ["main.cron.daily"]
    row = merged[0]
    assert row["title"] == "Hand-authored title"
    assert row["runtime_status"] == "disabled"


def test_merge_agents_preserves_notes() -> None:
    existing = [{"id": "main", "name": "Main", "notes": "keep me"}]
    proposed = [{"id": "main", "name": "Updated Main", "workspace": "/new/path"}]
    merged = merge_agents(existing, proposed)
    assert merged[0]["notes"] == "keep me"
    assert merged[0]["workspace"] == "/new/path"

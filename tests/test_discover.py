from openclaw_governance.discover import slugify, workflow_id_for_cron


def test_slugify() -> None:
    assert slugify("Daily Wiki Refresh") == "daily_wiki_refresh"
    assert slugify("") == "unnamed"


def test_workflow_id_for_cron() -> None:
    assert workflow_id_for_cron("main", "daily-wiki-refresh") == "main.cron.daily_wiki_refresh"

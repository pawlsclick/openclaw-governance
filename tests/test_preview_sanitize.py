from openclaw_governance.discover import parse_cron_jobs
from openclaw_governance.preview_sanitize import sanitize_message_preview


def test_sanitize_wallet_address_space_form() -> None:
    preview = "openclaw pay --wallet-address 0x1234567890abcdef1234567890abcdef12345678"
    sanitized = sanitize_message_preview(preview)
    assert "0x1234567890abcdef" not in sanitized
    assert "--wallet-address <redacted>" in sanitized


def test_sanitize_token_and_password_equals_form() -> None:
    preview = "curl --token=sk-secret-abc --password=hunter2"
    sanitized = sanitize_message_preview(preview)
    assert "sk-secret-abc" not in sanitized
    assert "hunter2" not in sanitized
    assert "--token=<redacted>" in sanitized
    assert "--password=<redacted>" in sanitized


def test_parse_cron_jobs_redacts_sensitive_preview() -> None:
    jobs = [
        {
            "id": "job-1",
            "name": "pay",
            "enabled": True,
            "schedule": "0 9 * * *",
            "payload": {
                "message": "run --wallet-address 0xdeadbeef --api-key secret-key-value",
            },
        }
    ]
    parsed = parse_cron_jobs("main", jobs)
    assert len(parsed) == 1
    assert "0xdeadbeef" not in parsed[0].message_preview
    assert "<redacted>" in parsed[0].message_preview
    assert "--wallet-address" in parsed[0].message_preview

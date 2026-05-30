from pathlib import Path

from openclaw_governance.check_registry import Check, check_workflows
from openclaw_governance.config import GovernanceConfig


def _minimal_cron_workflow(**overrides: object) -> dict:
    workflow = {
        "id": "main.cron.daily",
        "agent": "main",
        "title": "Daily",
        "status": "active",
        "purpose": "Run daily",
        "trigger": "cron",
        "orchestration": "openclaw_cron",
        "inputs": [],
        "outputs": [],
        "tools_or_scripts": [],
        "source_docs": [],
        "cron_job_ids": ["job-1"],
        "risk_level": "low",
        "approval_required": False,
        "success_criteria": ["ok"],
        "failure_modes": ["fail"],
        "tests": [],
        "runbook": "workflows/runbooks/main.cron.daily.md",
        "runtime_status": "active",
        "code_management": {"repo_decision": "tbd", "repo_url": "", "notes": ""},
        "cron_fingerprint": "new_fp",
        "discovered_from": {
            "source": "openclaw-gov discover",
            "cron_fingerprint": "new_fp",
            "cron_instances": [{"job_id": "job-1", "fingerprint": "new_fp"}],
        },
    }
    workflow.update(overrides)
    return workflow


def test_check_workflows_cron_fingerprint_mismatch(tmp_path: Path) -> None:
    runbook = tmp_path / "workflows" / "runbooks" / "main.cron.daily.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text("# runbook\n", encoding="utf-8")

    registry = {
        "workflows": [
            _minimal_cron_workflow(
                discovered_from={
                    "source": "openclaw-gov discover",
                    "cron_fingerprint": "old_fp",
                    "cron_instances": [{"job_id": "job-1", "fingerprint": "new_fp"}],
                }
            )
        ]
    }
    check = Check()
    config = GovernanceConfig(
        openclaw_home=tmp_path,
        governance_root=tmp_path,
        accountable_humans=["Operator"],
    )
    check_workflows(tmp_path, registry, check, config)
    assert any("discovered_from.cron_fingerprint" in error for error in check.errors)


def test_check_workflows_cron_fingerprint_aligned(tmp_path: Path) -> None:
    runbook = tmp_path / "workflows" / "runbooks" / "main.cron.daily.md"
    runbook.parent.mkdir(parents=True)
    runbook.write_text("# runbook\n", encoding="utf-8")

    registry = {"workflows": [_minimal_cron_workflow()]}
    check = Check()
    config = GovernanceConfig(
        openclaw_home=tmp_path,
        governance_root=tmp_path,
        accountable_humans=["Operator"],
    )
    check_workflows(tmp_path, registry, check, config)
    assert not any("discovered_from.cron_fingerprint" in error for error in check.errors)

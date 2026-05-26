from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.ship import (
    GitResult,
    changed_governance_files,
    default_branch_name,
    resolve_push,
    run_ship_commit,
    run_ship_start,
    suggest_commit_message,
)


def _config(tmp_path: Path) -> GovernanceConfig:
    gov = tmp_path / "gov"
    gov.mkdir()
    (gov / "workflows").mkdir()
    return GovernanceConfig(openclaw_home=tmp_path / "oc", governance_root=gov)


def test_suggest_commit_message_registry() -> None:
    assert suggest_commit_message(["workflows/registry.yaml"]) == (
        "chore(governance): update workflow registry"
    )


def test_suggest_commit_message_runbooks_only() -> None:
    assert suggest_commit_message(["workflows/runbooks/main.cron.foo.md"]) == (
        "docs(governance): update runbooks"
    )


def test_suggest_commit_message_readme_only() -> None:
    assert suggest_commit_message(["README.md"]) == "docs(governance): refresh README"


def test_suggest_commit_message_mixed() -> None:
    assert suggest_commit_message(["README.md", "workflows/registry.yaml"]) == (
        "chore(governance): sync governance artifacts"
    )


def test_default_branch_name_format(tmp_path: Path) -> None:
    name = default_branch_name(_config(tmp_path), slug="sync")
    assert name.startswith("governance/")
    assert name.endswith("-sync")


def test_resolve_push_flags() -> None:
    assert resolve_push(push=True, no_push=False) is True
    assert resolve_push(push=False, no_push=True) is False
    assert resolve_push(push=True, no_push=True) is None


@patch("openclaw_governance.ship.shutil.which", return_value="/usr/bin/git")
@patch("openclaw_governance.ship.is_git_repo", return_value=True)
@patch("openclaw_governance.ship.current_branch", return_value="main")
@patch("openclaw_governance.ship.has_governance_changes", return_value=True)
def test_ship_start_refuses_uncommitted_on_main(
    _changes,
    _branch,
    _repo,
    _which,
    tmp_path: Path,
) -> None:
    code = run_ship_start(_config(tmp_path))
    assert code == 1


@patch("openclaw_governance.ship.shutil.which", return_value="/usr/bin/git")
@patch("openclaw_governance.ship.is_git_repo", return_value=True)
@patch("openclaw_governance.ship.current_branch", return_value="main")
@patch("openclaw_governance.ship.has_governance_changes", return_value=False)
@patch("openclaw_governance.ship.fetch_origin_base", return_value=True)
@patch("openclaw_governance.ship.git_run")
@patch("openclaw_governance.ship.checkout_branch")
@patch("openclaw_governance.ship.default_branch_name", return_value="governance/2026-05-26-sync")
def test_ship_start_creates_branch(
    _default_branch,
    mock_checkout,
    mock_git_run,
    _fetch,
    _changes,
    _branch,
    _repo,
    _which,
    tmp_path: Path,
    capsys,
) -> None:
    mock_git_run.return_value = GitResult(0, "", "")
    mock_checkout.return_value = GitResult(0, "", "")

    code = run_ship_start(_config(tmp_path))
    assert code == 0
    mock_checkout.assert_called_once()
    assert "governance/2026-05-26-sync" in capsys.readouterr().out


@patch("openclaw_governance.ship.shutil.which", return_value="/usr/bin/git")
@patch("openclaw_governance.ship.is_git_repo", return_value=True)
@patch("openclaw_governance.ship.current_branch", return_value="main")
@patch("openclaw_governance.ship.has_governance_changes", return_value=True)
def test_ship_commit_refuses_on_main(_changes, _branch, _repo, _which, tmp_path: Path) -> None:
    code = run_ship_commit(_config(tmp_path))
    assert code == 1


@patch("openclaw_governance.ship.shutil.which", return_value="/usr/bin/git")
@patch("openclaw_governance.ship.is_git_repo", return_value=True)
@patch("openclaw_governance.ship.current_branch", return_value="governance/feature")
@patch("openclaw_governance.ship.has_governance_changes", return_value=False)
def test_ship_commit_noop_without_changes(_changes, _branch, _repo, _which, tmp_path: Path) -> None:
    code = run_ship_commit(_config(tmp_path))
    assert code == 0


@patch("openclaw_governance.ship.shutil.which", return_value="/usr/bin/git")
@patch("openclaw_governance.ship.is_git_repo", return_value=True)
@patch("openclaw_governance.ship.current_branch", return_value="governance/feature")
@patch("openclaw_governance.ship.has_governance_changes", return_value=True)
@patch("openclaw_governance.ship.changed_governance_files", return_value=["workflows/registry.yaml"])
@patch("openclaw_governance.ship.run_validation_gates", return_value=1)
def test_ship_commit_aborts_when_gates_fail(
    _gates,
    _files,
    _changes,
    _branch,
    _repo,
    _which,
    tmp_path: Path,
) -> None:
    code = run_ship_commit(_config(tmp_path), no_push=True)
    assert code == 1


@patch("openclaw_governance.ship.shutil.which", return_value="/usr/bin/git")
@patch("openclaw_governance.ship.is_git_repo", return_value=True)
@patch("openclaw_governance.ship.current_branch", return_value="governance/feature")
@patch("openclaw_governance.ship.has_governance_changes", return_value=True)
@patch("openclaw_governance.ship.changed_governance_files", return_value=["workflows/registry.yaml"])
@patch("openclaw_governance.ship.run_validation_gates", return_value=0)
@patch("openclaw_governance.ship._pathspecs", return_value=["workflows"])
@patch("openclaw_governance.ship.git_run")
@patch("openclaw_governance.ship.resolve_push", return_value=False)
def test_ship_commit_stages_and_commits(
    _push,
    mock_git_run,
    _specs,
    _gates,
    _files,
    _changes,
    _branch,
    _repo,
    _which,
    tmp_path: Path,
    capsys,
) -> None:
    mock_git_run.return_value = GitResult(0, "", "")

    code = run_ship_commit(_config(tmp_path), no_push=True)
    assert code == 0
    calls = [call.args[1:] for call in mock_git_run.call_args_list]
    assert ("add", "--", "workflows") in calls
    assert any(args[0] == "commit" for args in calls)
    assert "committed:" in capsys.readouterr().out


def test_changed_governance_files_parsing(tmp_path: Path) -> None:
    gov = tmp_path / "gov"
    gov.mkdir()
    (gov / "workflows").mkdir()
    (gov / "workflows" / "registry.yaml").write_text("x\n", encoding="utf-8")

    with patch("openclaw_governance.ship.git_run") as mock_git_run:
        mock_git_run.return_value = GitResult(0, " M workflows/registry.yaml\n", "")
        files = changed_governance_files(gov)
    assert files == ["workflows/registry.yaml"]

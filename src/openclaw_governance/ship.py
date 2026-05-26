"""Git workflow for governance root: branch before writes, commit, optional push/PR."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from openclaw_governance.config import GovernanceConfig
from openclaw_governance.remote import get_git_origin

# Relative paths under governance root that ship stages and tracks.
GOVERNANCE_REL_PATHS: tuple[str, ...] = (
    "workflows",
    "README.md",
    "governance.config.yaml",
    ".github/workflows/governance-drift.yml",
)

BRANCH_PREFIX = "governance"


@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str


def git_run(repo: Path, *args: str, check: bool = False) -> GitResult:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    return GitResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def is_git_repo(repo: Path) -> bool:
    return git_run(repo, "rev-parse", "--is-inside-work-tree").returncode == 0


def current_branch(repo: Path) -> str | None:
    result = git_run(repo, "rev-parse", "--abbrev-ref", "HEAD")
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch and branch != "HEAD" else None


def _pathspecs(repo: Path) -> list[str]:
    specs: list[str] = []
    for rel in GOVERNANCE_REL_PATHS:
        if (repo / rel).exists():
            specs.append(rel)
    return specs


def governance_status_lines(repo: Path) -> list[str]:
    """Return porcelain lines for tracked governance paths (staged or unstaged)."""
    specs = _pathspecs(repo)
    if not specs:
        return []
    result = git_run(repo, "status", "--porcelain", "--", *specs)
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def has_governance_changes(repo: Path) -> bool:
    return bool(governance_status_lines(repo))


def changed_governance_files(repo: Path) -> list[str]:
    """Relative paths with changes (staged or unstaged) under governance artifacts."""
    files: list[str] = []
    for line in governance_status_lines(repo):
        # XY path or XY old -> new
        path_part = line[3:].strip()
        if " -> " in path_part:
            path_part = path_part.split(" -> ", 1)[1]
        files.append(path_part)
    return files


def suggest_commit_message(changed_files: list[str]) -> str:
    paths = {p.replace("\\", "/") for p in changed_files}
    has_registry = any(p == "workflows/registry.yaml" for p in paths)
    runbook_only = paths and all(
        p.startswith("workflows/runbooks/") or p == "workflows/runbooks"
        for p in paths
    )
    readme_only = paths == {"README.md"}

    if has_registry and len(paths) == 1:
        return "chore(governance): update workflow registry"
    if runbook_only:
        return "docs(governance): update runbooks"
    if readme_only:
        return "docs(governance): refresh README"
    return "chore(governance): sync governance artifacts"


def default_branch_name(config: GovernanceConfig, *, slug: str = "sync") -> str:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{BRANCH_PREFIX}/{date}-{slug}"


def fetch_origin_base(repo: Path, base: str) -> bool:
    result = git_run(repo, "fetch", "origin", base)
    if result.returncode != 0:
        print(f"WARN git fetch origin {base} failed (continuing offline): {result.stderr.strip()}")
        return False
    return True


def branch_exists(repo: Path, name: str) -> bool:
    local = git_run(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}")
    if local.returncode == 0:
        return True
    remote = git_run(repo, "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{name}")
    return remote.returncode == 0


def checkout_branch(repo: Path, name: str, *, start_point: str | None = None) -> GitResult:
    if start_point:
        if branch_exists(repo, name):
            return git_run(repo, "checkout", name)
        return git_run(repo, "checkout", "-b", name, start_point)
    return git_run(repo, "checkout", name)


def run_openclaw_gov_gate(config: GovernanceConfig, *extra_args: str) -> int:
    cmd = ["openclaw-gov", *extra_args, "--root", str(config.governance_root)]
    proc = subprocess.run(cmd, check=False)
    return int(proc.returncode)


def run_validation_gates(config: GovernanceConfig) -> int:
    code = run_openclaw_gov_gate(config, "regen", "--check")
    if code != 0:
        print("ERROR regen --check failed; fix README/RACI drift before commit")
        return code
    code = run_openclaw_gov_gate(config, "check")
    if code != 0:
        print("ERROR check failed; fix registry/runbook issues before commit")
        return code
    return 0


def resolve_push(*, push: bool, no_push: bool) -> bool | None:
    """Return True/False for push decision, or None if user declined on TTY."""
    if push and no_push:
        print("ERROR cannot use both --push and --no-push")
        return None
    if push:
        return True
    if no_push:
        return False
    if sys.stdin.isatty():
        try:
            answer = input("Push branch and open PR? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("")
            return False
        return answer in ("y", "yes")
    return False


def gh_available() -> bool:
    if not shutil.which("gh"):
        return False
    proc = subprocess.run(["gh", "auth", "status"], capture_output=True, check=False)
    return proc.returncode == 0


def push_and_create_pr(
    config: GovernanceConfig,
    repo: Path,
    branch: str,
    base: str,
    commit_message: str,
    *,
    dry_run: bool,
) -> int:
    if dry_run:
        print(f"DRY-RUN would: git push -u origin {branch}")
        print(f"DRY-RUN would: gh pr create --base {base} --head {branch}")
        return 0

    if not shutil.which("git"):
        print("ERROR git not on PATH")
        return 1

    push_result = git_run(repo, "push", "-u", "origin", "HEAD")
    if push_result.returncode != 0:
        print(f"ERROR git push failed: {push_result.stderr.strip()}")
        return 1

    if not gh_available():
        print("WARN gh not available or not authenticated; branch pushed but no PR created")
        print(f"     gh pr create --base {base} --head {branch} --title \"{commit_message}\"")
        return 0

    body = (
        "## Summary\n"
        "- Governance registry/runbooks/README sync from openclaw-gov ship workflow.\n\n"
        "## Test plan\n"
        "- [x] openclaw-gov regen --check\n"
        "- [x] openclaw-gov check\n"
    )
    proc = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--base",
            base,
            "--head",
            branch,
            "--title",
            commit_message,
            "--body",
            body,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        print(f"ERROR gh pr create failed: {detail}")
        return 1

    url = (proc.stdout or "").strip()
    if url:
        print(f"PR: {url}")
    return 0


def run_ship_start(
    config: GovernanceConfig,
    *,
    branch: str | None = None,
    base: str | None = None,
    dry_run: bool = False,
) -> int:
    repo = config.governance_root
    base_branch = base or config.remote_default_branch

    if not shutil.which("git"):
        print("ERROR git not on PATH")
        return 1

    if not is_git_repo(repo):
        print(f"ERROR governance root is not a git repository: {repo}")
        print("      run git init and add remote origin first")
        return 1

    current = current_branch(repo)
    if current is None:
        print("ERROR could not determine current git branch")
        return 1

    if not dry_run:
        fetch_origin_base(repo, base_branch)

    if current != base_branch:
        print(f"on feature branch: {current}")
        print("next: make governance changes, then openclaw-gov ship commit")
        return 0

    if has_governance_changes(repo):
        print(f"ERROR uncommitted governance changes on {base_branch}")
        print("      you should have run ship start before making changes")
        print("      stash or reset, then: openclaw-gov ship start")
        return 1

    new_branch = branch or default_branch_name(config)
    start_point = f"origin/{base_branch}"
    remote_ref = git_run(repo, "rev-parse", "--verify", start_point)
    if remote_ref.returncode != 0:
        start_point = base_branch
        local_ref = git_run(repo, "rev-parse", "--verify", base_branch)
        if local_ref.returncode != 0:
            print(f"ERROR cannot find branch {base_branch} or origin/{base_branch}")
            return 1

    if dry_run:
        print(f"DRY-RUN would create/checkout branch: {new_branch} from {start_point}")
        print("next: discover --write, regen --write, check, then ship commit")
        return 0

    result = checkout_branch(repo, new_branch, start_point=start_point)
    if result.returncode != 0:
        print(f"ERROR checkout failed: {result.stderr.strip()}")
        return 1

    print(f"branch: {new_branch}")
    print("next: make governance changes on this branch (discover --write, regen --write, etc.)")
    print("      then: openclaw-gov ship commit")
    return 0


def run_ship_commit(
    config: GovernanceConfig,
    *,
    message: str | None = None,
    base: str | None = None,
    push: bool = False,
    no_push: bool = False,
    dry_run: bool = False,
) -> int:
    repo = config.governance_root
    base_branch = base or config.remote_default_branch

    if not shutil.which("git"):
        print("ERROR git not on PATH")
        return 1

    if not is_git_repo(repo):
        print(f"ERROR governance root is not a git repository: {repo}")
        return 1

    current = current_branch(repo)
    if current is None:
        print("ERROR could not determine current git branch")
        return 1

    if current == base_branch:
        print(f"ERROR on base branch {base_branch}; run openclaw-gov ship start first")
        return 1

    if not has_governance_changes(repo):
        print("nothing to commit (no governance artifact changes)")
        return 0

    changed = changed_governance_files(repo)
    commit_message = message or suggest_commit_message(changed)

    if dry_run:
        print(f"DRY-RUN branch: {current}")
        print(f"DRY-RUN would commit {len(changed)} file(s): {', '.join(changed[:5])}")
        print(f"DRY-RUN message: {commit_message}")
        push_choice = resolve_push(push=push, no_push=no_push)
        if push_choice:
            return push_and_create_pr(
                config, repo, current, base_branch, commit_message, dry_run=True
            )
        return 0

    gate_code = run_validation_gates(config)
    if gate_code != 0:
        return gate_code

    specs = _pathspecs(repo)
    if not specs:
        print("ERROR no governance paths to stage")
        return 1

    add_result = git_run(repo, "add", "--", *specs)
    if add_result.returncode != 0:
        print(f"ERROR git add failed: {add_result.stderr.strip()}")
        return 1

    commit_result = git_run(repo, "commit", "-m", commit_message)
    if commit_result.returncode != 0:
        print(f"ERROR git commit failed: {commit_result.stderr.strip()}")
        return 1

    print(f"committed: {commit_message}")

    push_choice = resolve_push(push=push, no_push=no_push)
    if push_choice is None:
        return 1
    if not push_choice:
        print(f"next: git push -u origin {current}")
        print(f"      gh pr create --base {base_branch} --head {current}")
        return 0

    origin = get_git_origin(repo)
    if config.remote_url and origin is None:
        print("WARN no git origin; push may fail (set remote.url in governance.config.yaml)")

    return push_and_create_pr(
        config, repo, current, base_branch, commit_message, dry_run=False
    )

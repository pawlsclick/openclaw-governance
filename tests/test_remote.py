from openclaw_governance.remote import normalize_git_remote, validate_remote_url


def test_validate_remote_url_https() -> None:
    assert validate_remote_url("https://github.com/org/repo.git") is None


def test_validate_remote_url_git_scp() -> None:
    assert validate_remote_url("git@github.com:org/repo.git") is None


def test_validate_remote_url_rejects_unsafe_chars() -> None:
    assert validate_remote_url("https://evil.com/repo\n") is not None


def test_normalize_git_remote_equivalence() -> None:
    a = normalize_git_remote("https://github.com/org/repo.git")
    b = normalize_git_remote("git@github.com:org/repo")
    assert a == b

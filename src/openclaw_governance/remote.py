"""Validate governance remote URLs and compare with local git origin."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

# Safe for embedding in markdown backticks (no newlines or backticks).
_UNSAFE_URL_CHARS = re.compile(r"[\s`<>]")


def validate_remote_url(url: str) -> str | None:
    """Return an error message if url is invalid; None if OK."""
    if _UNSAFE_URL_CHARS.search(url):
        return "remote.url contains unsupported whitespace or characters"
    trimmed = url.strip()
    if not trimmed:
        return "remote.url must not be empty"
    if trimmed.startswith("git@"):
        if ":" not in trimmed.split("@", 1)[-1]:
            return "git@ remote must look like git@host:owner/repo"
        return None
    if trimmed.startswith("ssh://"):
        parsed = urlparse(trimmed)
        if not parsed.hostname or not parsed.path.strip("/"):
            return "ssh:// remote must include host and repository path"
        return None
    parsed = urlparse(trimmed)
    if parsed.scheme not in ("http", "https"):
        return "remote.url must be https://, git@host:path, or ssh://"
    if not parsed.hostname or not parsed.path.strip("/"):
        return "https remote must include host and repository path"
    return None


def normalize_git_remote(url: str) -> str:
    """Normalize a git remote URL for equality checks."""
    raw = url.strip().rstrip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]

    if raw.startswith("git@"):
        host_path = raw[4:]
        if ":" in host_path:
            host, path = host_path.split(":", 1)
            return f"{host.lower()}/{path.strip('/')}".lower()

    parsed = urlparse(raw)
    if parsed.scheme in ("http", "https", "ssh"):
        host = (parsed.hostname or "").lower()
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return f"{host}/{path}".lower()

    return raw.lower()


def get_git_origin(repo_path: Path) -> str | None:
    """Return origin URL for a git repo, or None if unavailable."""
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return None
    proc = subprocess.run(
        ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    url = proc.stdout.strip()
    return url or None

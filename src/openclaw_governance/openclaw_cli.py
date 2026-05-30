"""Shared OpenClaw CLI subprocess helpers."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_OPENCLAW_TIMEOUT_SECONDS = 45


def run_openclaw_json(
    argv: list[str],
    *,
    timeout_seconds: int = DEFAULT_OPENCLAW_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any] | None, str | None]:
    """Run an openclaw subcommand and parse JSON object from stdout.

    stdout is captured via a temp file instead of a pipe. Large JSON payloads
    (e.g. ``openclaw skills list --json`` on a host with many skills) can be
    truncated when read through ``subprocess.run(capture_output=True)``.
    """
    cmd = ["openclaw", *argv]
    tmp_path: Path | None = None
    proc: subprocess.CompletedProcess[str] | None = None
    raw = ""
    try:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        with tmp_path.open("w", encoding="utf-8") as stdout_file:
            proc = subprocess.run(
                cmd,
                stdout=stdout_file,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        raw = tmp_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, "openclaw CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return None, f"openclaw {' '.join(argv)} timed out after {timeout_seconds}s"
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    assert proc is not None
    if proc.returncode != 0:
        stderr = (proc.stderr or raw or "").strip()
        return None, f"openclaw {' '.join(argv)} failed: {stderr[:200]}"

    start = raw.find("{")
    if start < 0:
        return None, f"openclaw {' '.join(argv)} returned non-JSON output"
    try:
        data = json.loads(raw[start:])
    except json.JSONDecodeError as exc:
        return None, f"openclaw {' '.join(argv)} JSON parse error: {exc}"

    if not isinstance(data, dict):
        return None, f"openclaw {' '.join(argv)} returned non-object JSON"
    return data, None


def openclaw_cli_version(*, timeout_seconds: int = 10) -> str | None:
    try:
        proc = subprocess.run(
            ["openclaw", "--version"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    line = (proc.stdout or proc.stderr or "").strip().splitlines()
    return line[0] if line else None

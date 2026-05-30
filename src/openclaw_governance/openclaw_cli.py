"""Shared OpenClaw CLI subprocess helpers."""

from __future__ import annotations

import json
import subprocess
from typing import Any

DEFAULT_OPENCLAW_TIMEOUT_SECONDS = 45


def run_openclaw_json(
    argv: list[str],
    *,
    timeout_seconds: int = DEFAULT_OPENCLAW_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any] | None, str | None]:
    """Run an openclaw subcommand and parse JSON object from stdout."""
    cmd = ["openclaw", *argv]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        return None, "openclaw CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return None, f"openclaw {' '.join(argv)} timed out after {timeout_seconds}s"

    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        return None, f"openclaw {' '.join(argv)} failed: {stderr[:200]}"

    raw = proc.stdout or ""
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

"""Redact sensitive values from cron command previews for governance artifacts."""

from __future__ import annotations

import re
from typing import Iterable

DEFAULT_SENSITIVE_FLAGS: tuple[str, ...] = (
    "--wallet-address",
    "--private-key",
    "--token",
    "--api-key",
    "--password",
    "--secret",
)

_REDACTED = "<redacted>"


def _flag_patterns(flag: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    name = re.escape(flag.lstrip("-"))
    value = r'(?:"[^"]*"|\'[^\']*\'|[^\s"\']+)'
    return (
        re.compile(rf"(--{name})=({value})", re.IGNORECASE),
        re.compile(rf"(--{name})\s+({value})", re.IGNORECASE),
    )


def sanitize_message_preview(
    preview: str,
    extra_flags: Iterable[str] | None = None,
) -> str:
    """Replace sensitive CLI flag values while preserving command shape."""
    if not preview:
        return preview

    flags = list(DEFAULT_SENSITIVE_FLAGS)
    if extra_flags:
        flags.extend(str(item) for item in extra_flags if item)

    sanitized = preview
    seen: set[str] = set()
    for flag in flags:
        normalized = flag if flag.startswith("--") else f"--{flag}"
        if normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        equals_pattern, space_pattern = _flag_patterns(normalized)
        sanitized = equals_pattern.sub(rf"\1={_REDACTED}", sanitized)
        sanitized = space_pattern.sub(rf"\1 {_REDACTED}", sanitized)
    return sanitized

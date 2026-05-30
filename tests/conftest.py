"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Any

import pytest

from openclaw_governance import openclaw_cli


@pytest.fixture(autouse=True)
def _mock_openclaw_plugins_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests do not require openclaw plugins list on PATH."""
    original = openclaw_cli.run_openclaw_json

    def _fake(
        argv: list[str],
        *,
        timeout_seconds: int = openclaw_cli.DEFAULT_OPENCLAW_TIMEOUT_SECONDS,
    ) -> tuple[dict[str, Any] | None, str | None]:
        if len(argv) >= 2 and argv[0] == "plugins" and argv[1] == "list":
            return {"plugins": []}, None
        return original(argv, timeout_seconds=timeout_seconds)

    for module in (
        "openclaw_governance.openclaw_cli",
        "openclaw_governance.agent_scope",
        "openclaw_governance.discover_plugins",
        "openclaw_governance.discover_skills",
        "openclaw_governance.materialize",
    ):
        monkeypatch.setattr(f"{module}.run_openclaw_json", _fake, raising=False)

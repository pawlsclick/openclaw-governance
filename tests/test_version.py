from importlib.metadata import version
from pathlib import Path

import tomllib

from openclaw_governance import __version__


def test_cli_version_matches_pyproject() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    expected = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert __version__ == expected
    assert version("openclaw-governance") == expected

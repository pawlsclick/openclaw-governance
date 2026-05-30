"""OpenClaw governance engine — discover, validate, and materialize workflow registry."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("openclaw-governance")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"

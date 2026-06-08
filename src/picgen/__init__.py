"""PicGen application package."""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

__all__ = ["__version__"]


def _version_from_pyproject() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with pyproject_path.open("rb") as fh:
            project = tomllib.load(fh).get("project", {})
    except (OSError, tomllib.TOMLDecodeError):
        return "0.0.0"
    version = project.get("version")
    return str(version) if version else "0.0.0"


try:
    __version__ = metadata.version("picgen")
except metadata.PackageNotFoundError:  # pragma: no cover - source tree fallback
    __version__ = _version_from_pyproject()

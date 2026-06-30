from __future__ import annotations

from importlib import metadata
from pathlib import Path
import tomllib


PACKAGE_NAME = "armilar-data-pipeline"
UNKNOWN_VERSION = "0+unknown"


def installed_version(distribution_name: str = PACKAGE_NAME) -> str:
    try:
        return metadata.version(distribution_name)
    except metadata.PackageNotFoundError:
        return UNKNOWN_VERSION


def pyproject_version(repo_root: Path) -> str:
    payload = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def build_user_agent(version: str | None = None) -> str:
    resolved = installed_version() if version is None else version
    return (
        f"ArmilarDataPipeline/{resolved} "
        "(+https://github.com/tomazlucena-crypto/armilar-data-pipeline)"
    )

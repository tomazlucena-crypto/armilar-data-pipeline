from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

from armilar_pipeline.version import UNKNOWN_VERSION, installed_version, pyproject_version


ACTIVE_FILES_WITHOUT_AUTHORED_VERSION = (
    Path("config/step2_icp2021.json"),
    Path("src/armilar_pipeline/__init__.py"),
)


class VersionConsistencyError(RuntimeError):
    pass


def validate_version_consistency(repo_root: Path, *, require_installed: bool = True) -> dict[str, str]:
    project_version = pyproject_version(repo_root)
    package_version = installed_version()
    if require_installed and package_version == UNKNOWN_VERSION:
        raise VersionConsistencyError("package metadata is unavailable; install the project first")
    if package_version != UNKNOWN_VERSION and package_version != project_version:
        raise VersionConsistencyError(
            f"installed version {package_version} does not match pyproject.toml {project_version}"
        )

    config_path = repo_root / "config" / "step2_icp2021.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if "pipeline_version" in config:
        raise VersionConsistencyError("config/step2_icp2021.json must not author pipeline_version")
    user_agent = str(config.get("user_agent", ""))
    if re.search(r"/\d+\.\d+\.\d+", user_agent):
        raise VersionConsistencyError("config/step2_icp2021.json must not author a versioned user_agent")

    offenders = [
        str(path)
        for path in ACTIVE_FILES_WITHOUT_AUTHORED_VERSION
        if re.search(r'__version__\s*=\s*["\']\d+\.\d+\.\d+', (repo_root / path).read_text(encoding="utf-8"))
    ]
    if offenders:
        raise VersionConsistencyError("independent __version__ literal found: " + ", ".join(offenders))

    return {
        "pyproject_version": project_version,
        "installed_version": package_version,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--allow-uninstalled",
        action="store_true",
        help="Allow 0+unknown package metadata for source-checkout diagnostics only.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = validate_version_consistency(
            args.repo_root.resolve(),
            require_installed=not args.allow_uninstalled,
        )
    except VersionConsistencyError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

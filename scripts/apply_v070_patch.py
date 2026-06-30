from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

PATCH_ROOT = Path(__file__).resolve().parents[1]
COPY_ROOTS = ("constitution", "config", "docs", "schemas", "src", "tests", "examples")
COPY_FILES = ("RELEASE_NOTES_V0.7.0.md",)
BASE_VERSION = "0.6.13"
TARGET_VERSION = "0.7.0"


def copy_tree(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def read_project_version(pyproject: Path) -> str:
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError("Could not determine the project version in pyproject.toml")
    return match.group(1)


def replace_once(path: Path, old: str, new: str, description: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text and old not in text:
        return
    if old not in text:
        raise RuntimeError(f"Could not update {description}: expected {old!r} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_pyproject(path: Path) -> None:
    current = read_project_version(path)
    if current not in {BASE_VERSION, TARGET_VERSION}:
        raise RuntimeError(
            f"Repository version is {current}, but this patch requires {BASE_VERSION}. "
            "The public main branch is still 0.6.5; create the v0.7.0 branch from "
            "origin/codex/step2h0-remaining-country-audits, not from main."
        )
    if current == BASE_VERSION:
        replace_once(path, f'version = "{BASE_VERSION}"', f'version = "{TARGET_VERSION}"', "project version")
    script_line = 'armilar-global-weights = "armilar_global_weights.cli:main"'
    text = path.read_text(encoding="utf-8")
    if script_line not in text:
        anchor = 'armilar-matrix = "armilar_matrix_builder.cli:main"'
        if anchor not in text:
            raise RuntimeError("Could not find the armilar-matrix script anchor")
        path.write_text(text.replace(anchor, anchor + "\n" + script_line, 1), encoding="utf-8")


def patch_runtime_versions(repository: Path) -> None:
    init_path = repository / "src" / "armilar_pipeline" / "__init__.py"
    if init_path.exists():
        replace_once(init_path, f'__version__ = "{BASE_VERSION}"', f'__version__ = "{TARGET_VERSION}"', "package version")

    config_path = repository / "config" / "step2_icp2021.json"
    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        current = str(payload.get("pipeline_version", ""))
        if current not in {BASE_VERSION, TARGET_VERSION}:
            raise RuntimeError(f"Unexpected config pipeline_version {current!r}")
        payload["pipeline_version"] = TARGET_VERSION
        user_agent = str(payload.get("user_agent", ""))
        payload["user_agent"] = user_agent.replace(BASE_VERSION, TARGET_VERSION)
        config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    for relative in ("tests/test_config.py", "tests/test_program_architecture.py"):
        path = repository / relative
        if path.exists():
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace(f'"{BASE_VERSION}"', f'"{TARGET_VERSION}"'), encoding="utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    pyproject = repository / "pyproject.toml"
    if not pyproject.exists():
        raise SystemExit(f"pyproject.toml not found in {repository}")

    current = read_project_version(pyproject)
    if current not in {BASE_VERSION, TARGET_VERSION}:
        raise SystemExit(
            f"Cannot apply v0.7.0 over repository version {current}.\n"
            f"Required base: {BASE_VERSION}.\n"
            "Fetch origin, switch to codex/step2h0-remaining-country-audits, "
            "then create armilar-v0.7.0 from that branch."
        )

    for name in COPY_ROOTS:
        source = PATCH_ROOT / name
        if source.exists():
            copy_tree(source, repository / name)
    for name in COPY_FILES:
        shutil.copy2(PATCH_ROOT / name, repository / name)

    patch_pyproject(pyproject)
    patch_runtime_versions(repository)
    print("Applied Armilar v0.7.0 contract patch")
    print("Next: py -m pip install -e . && py -m unittest discover -s tests -v")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

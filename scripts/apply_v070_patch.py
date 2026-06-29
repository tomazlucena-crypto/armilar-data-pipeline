from __future__ import annotations

import shutil
from pathlib import Path

PATCH_ROOT = Path(__file__).resolve().parents[1]
COPY_ROOTS = ("constitution", "config", "docs", "schemas", "src", "tests", "examples")
COPY_FILES = ("RELEASE_NOTES_V0.7.0.md",)


def copy_tree(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(source)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def patch_pyproject(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if 'version = "0.7.0"' not in text:
        if 'version = "0.6.13"' not in text:
            raise RuntimeError("Expected reconciled pyproject version 0.6.13; refusing an unsafe automatic edit")
        text = text.replace('version = "0.6.13"', 'version = "0.7.0"', 1)
    script_line = 'armilar-global-weights = "armilar_global_weights.cli:main"'
    if script_line not in text:
        anchor = 'armilar-matrix = "armilar_matrix_builder.cli:main"'
        if anchor not in text:
            raise RuntimeError("Could not find the armilar-matrix script anchor")
        text = text.replace(anchor, anchor + "\n" + script_line, 1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)
    args = parser.parse_args()
    repository = args.repository.resolve()
    pyproject = repository / "pyproject.toml"
    if not pyproject.exists():
        raise SystemExit(f"pyproject.toml not found in {repository}")
    for name in COPY_ROOTS:
        source = PATCH_ROOT / name
        if source.exists():
            copy_tree(source, repository / name)
    for name in COPY_FILES:
        shutil.copy2(PATCH_ROOT / name, repository / name)
    patch_pyproject(pyproject)
    print("Applied Armilar v0.7.0 contract patch")
    print("Next: python -m pip install -e . && pytest -q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

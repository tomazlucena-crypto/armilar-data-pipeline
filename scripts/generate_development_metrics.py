from __future__ import annotations

import argparse
import ast
import csv
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PRODUCTION_ROOTS = ("src", "scripts")
TEST_ROOTS = ("tests",)


@dataclass(frozen=True)
class MetricValue:
    value: object
    unavailable_reason: str | None = None

    def to_json(self) -> dict[str, object]:
        return {"value": self.value, "unavailable_reason": self.unavailable_reason}


def _python_files(root: Path, folders: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for folder in folders:
        base = root / folder
        if base.exists():
            files.extend(path for path in base.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def _count_lines(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        total += sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return total


def _test_count_from_source(source: str) -> int:
    source = source.lstrip("\ufeff")
    tree = ast.parse(source)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test")
    )


def count_tests(root: Path) -> int:
    return sum(_test_count_from_source(path.read_text(encoding="utf-8-sig")) for path in _python_files(root, TEST_ROOTS))


def count_tests_at_ref(root: Path, ref: str) -> int | None:
    try:
        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref, "--", "tests"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
    except (OSError, subprocess.CalledProcessError):
        return None
    total = 0
    for name in sorted(path for path in listing if path.endswith(".py")):
        try:
            source = subprocess.run(
                ["git", "show", f"{ref}:{name}"],
                cwd=root,
                capture_output=True,
                check=True,
            ).stdout.decode("utf-8-sig")
        except (OSError, subprocess.CalledProcessError):
            return None
        total += _test_count_from_source(source)
    return total


def _largest_file(root: Path) -> dict[str, object]:
    candidates = sorted(
        path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts
    )
    largest = max(candidates, key=lambda path: (path.stat().st_size, str(path.relative_to(root))))
    return {"path": str(largest.relative_to(root)).replace("\\", "/"), "bytes": largest.stat().st_size}


def _artifact_count(root: Path) -> int:
    public = root / "public" / "latest"
    if not public.exists():
        return 0
    return sum(1 for path in public.rglob("*") if path.is_file())


def _csv_rows(path: Path) -> MetricValue:
    if not path.exists():
        return MetricValue(None, f"{path.as_posix()} is unavailable")
    with path.open(encoding="utf-8", newline="") as handle:
        return MetricValue(sum(1 for _ in csv.DictReader(handle)))


def generate_metrics(
    root: Path,
    *,
    baseline_ref: str | None = None,
    suite_duration_seconds: float | None = None,
    pipeline_runtime_seconds: float | None = None,
) -> dict[str, object]:
    production_files = _python_files(root, PRODUCTION_ROOTS)
    test_files = _python_files(root, TEST_ROOTS)
    branch_tests = count_tests(root)
    baseline_tests = count_tests_at_ref(root, baseline_ref) if baseline_ref else None
    return {
        "schema_version": "1.0",
        "production_lines": _count_lines(production_files),
        "test_lines": _count_lines(test_files),
        "test_count": branch_tests,
        "baseline_test_count": MetricValue(
            baseline_tests,
            None if baseline_tests is not None else "baseline ref not provided or unavailable",
        ).to_json(),
        "suite_duration_seconds": MetricValue(
            suite_duration_seconds,
            None if suite_duration_seconds is not None else "suite duration not measured by telemetry generator",
        ).to_json(),
        "module_count": len(production_files),
        "largest_file": _largest_file(root),
        "pipeline_runtime_seconds": MetricValue(
            pipeline_runtime_seconds,
            None if pipeline_runtime_seconds is not None else "pipeline runtime not measured in this run",
        ).to_json(),
        "artifact_count": _artifact_count(root),
        "weights_coverage_rows": _csv_rows(root / "public" / "latest" / "weights_observed_universe.csv").to_json(),
        "prices_coverage_rows": _csv_rows(root / "public" / "latest" / "price_evidence_coverage.csv").to_json(),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("development_metrics.json"))
    parser.add_argument("--baseline-ref", default="")
    parser.add_argument("--fail-on-test-regression", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.repo_root.resolve()
    metrics = generate_metrics(root, baseline_ref=args.baseline_ref or None)
    baseline = metrics["baseline_test_count"]["value"]  # type: ignore[index]
    if args.fail_on_test_regression and baseline is not None and metrics["test_count"] < baseline:
        raise SystemExit(
            f"test count regression: branch={metrics['test_count']} baseline={baseline}"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

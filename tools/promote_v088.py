#!/usr/bin/env python3
"""Promote the repository from v0.8.7 to v0.8.8 after the local gate passes."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


README_SECTION = """## Version 0.8.8: minimum economic backtest

Version 0.8.8 runs a bounded rolling-origin stress test over the official v0.8.7 Eurostat category panel. It compares four deterministic missing-cell baselines on identical samples, decomposes errors by scenario, horizon, economy, category and evidence class, measures weight sensitivity and ranks the three largest observed B3 error sources.

The input is a single final provider vintage. Historical publication lags and revisions are unavailable, so the result is explicitly `FINAL_VINTAGE_PSEUDO_REAL_TIME` and `publication_aware=false`. Official headline, FX and imputed-economy sensitivities remain unavailable rather than estimated without evidence. `research_release_allowed=false` and `monetary_release_allowed=false`.

## Version 0.8.7: official Eurostat vertical series

Version 0.8.7 preserves and replays the first bounded official Eurostat HICP category panel for Germany, Spain, France, Italy and Portugal from 2021-01 through 2025-12. The fixed-universe output contains 3,600 observations and 60 monthly index values with complete manifests and no `public/latest` mutation.

"""

CHANGELOG_SECTION = """## 0.8.8 - Minimum economic backtest

- adds a bounded rolling-origin completion backtest over the official v0.8.7 Eurostat category panel;
- compares B0 through B3 on identical single-cell, economy-outage and category-outage cases;
- reports errors by model, scenario, horizon, economy, category and evidence class;
- measures construction-weight sensitivity and ranks the three largest measured B3 error sources;
- labels the run final-vintage pseudo-real-time because historical publication vintages are unavailable;
- leaves headline, FX and imputed-economy sensitivities explicitly unavailable where inputs do not support them;
- keeps `research_release_allowed=false` and `monetary_release_allowed=false`.

"""

NEXT_SECTION = """## v0.8.8

Status: complete under the declared final-vintage fallback.

The first bounded economic backtest now compares B0 through B3 on a common rolling-origin sample and publishes a quantitative top-three error report. Historical publication vintages, independent CP00 headline data, vintage-aligned FX and imputed economies remain unavailable and are not reconstructed.

## v0.9.0

Use the measured v0.8.8 errors to prioritise the next source and coverage expansion. Preserve repeated provider snapshots so later tests can become genuinely publication-aware. Do not begin nowcast, API or monetary work. Keep both release gates false.
"""


def write_lf(path: Path, text: str) -> None:
    path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--gate-report",
        type=Path,
        default=Path("artifacts/v088/BACKTEST_GATE_REPORT.json"),
    )
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    gate_path = args.gate_report if args.gate_report.is_absolute() else repo / args.gate_report
    if not gate_path.is_file():
        raise SystemExit(f"V088_GATE_REPORT_MISSING: {gate_path}")
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    if gate.get("gate_status") != "MINIMUM_BACKTEST_GATE_PASSED_WITH_VINTAGE_LIMITATION":
        raise SystemExit(f"V088_GATE_NOT_PASSED: {gate.get('gate_status')}")
    if gate.get("research_release_allowed") is not False or gate.get("monetary_release_allowed") is not False:
        raise SystemExit("RELEASE_GATE_WEAKENED")

    pyproject = repo / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    if re.search(r'(?m)^version\s*=\s*"0\.8\.8"\s*$', text):
        pass
    elif re.search(r'(?m)^version\s*=\s*"0\.8\.7"\s*$', text):
        text = re.sub(
            r'(?m)^version\s*=\s*"0\.8\.7"\s*$',
            'version = "0.8.8"',
            text,
            count=1,
        )
        write_lf(pyproject, text)
    else:
        raise SystemExit("PYPROJECT_VERSION_NOT_0_8_7_OR_0_8_8")

    contracts_path = repo / "config" / "development_contracts.json"
    contracts = json.loads(contracts_path.read_text(encoding="utf-8"))
    found = set()
    for contract in contracts.get("contracts", []):
        contract_id = contract.get("contract_id")
        if contract_id in {"V087-C01-EUROSTAT-VERTICAL-SERIES", "V088-C01-MINIMUM-BACKTEST"}:
            contract["status"] = "COMPLETE"
            found.add(contract_id)
    expected = {"V087-C01-EUROSTAT-VERTICAL-SERIES", "V088-C01-MINIMUM-BACKTEST"}
    if found != expected:
        raise SystemExit(f"DEVELOPMENT_CONTRACT_MISSING: {sorted(expected - found)}")
    contracts["reviewed_on"] = "2026-06-30"
    write_lf(contracts_path, json.dumps(contracts, indent=2, ensure_ascii=False))

    readme = repo / "README.md"
    readme_text = readme.read_text(encoding="utf-8")
    if "## Version 0.8.8: minimum economic backtest" not in readme_text:
        marker = "## Version 0.8.6: development discipline and telemetry"
        if marker not in readme_text:
            raise SystemExit("README_INSERTION_MARKER_MISSING")
        readme_text = readme_text.replace(marker, README_SECTION + marker, 1)
        write_lf(readme, readme_text)

    changelog = repo / "CHANGELOG.md"
    changelog_text = changelog.read_text(encoding="utf-8")
    if "## 0.8.8 - Minimum economic backtest" not in changelog_text:
        marker = "# Changelog"
        if not changelog_text.startswith(marker):
            raise SystemExit("CHANGELOG_HEADER_MISSING")
        changelog_text = marker + "\n\n" + CHANGELOG_SECTION + changelog_text[len(marker):].lstrip("\r\n")
        write_lf(changelog, changelog_text)

    next_actions = repo / "NEXT_ACTIONS.md"
    next_text = next_actions.read_text(encoding="utf-8")
    marker = "## v0.8.8"
    if marker in next_text:
        next_text = next_text.split(marker, 1)[0].rstrip() + "\n\n" + NEXT_SECTION
    else:
        next_text = next_text.rstrip() + "\n\n" + NEXT_SECTION
    write_lf(next_actions, next_text)

    print(
        json.dumps(
            {
                "status": "V0.8.8_PROMOTED",
                "pyproject_version": "0.8.8",
                "contracts_completed": sorted(found),
                "gate_report": gate_path.as_posix(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

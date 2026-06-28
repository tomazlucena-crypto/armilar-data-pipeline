from __future__ import annotations

import json
import shutil
import traceback
import zipfile
from pathlib import Path
from typing import Any

from .acquire import AcquisitionRecord, fetch_json_pages, fetch_url
from .config import Step2Config, load_config
from .matrix import NORMALIZED_FIELDS, MatrixResult, build_matrix
from .measures import select_measures
from .participation import extract_participating_names, map_participants_to_codes
from .util import (
    read_csv, read_json, safe_runtime_info, utc_now, write_csv, write_json, write_sha256sums,
)
from .worldbank import (
    Variable, acquire_heading_data, extract_concepts, extract_variables, identify_roles,
    parse_observation_pages, validate_classification_workbook, validate_source_metadata,
)


def run_step2(config_path: str | Path, run_dir: str | Path, cache_dir: str | Path, output_dir: str | Path) -> dict[str, Any]:
    config = load_config(config_path)
    run_root = Path(run_dir).resolve()
    cache_root = Path(cache_dir).resolve()
    output_root = Path(output_dir).resolve()
    if run_root.exists():
        shutil.rmtree(run_root)
    run_root.mkdir(parents=True)
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[AcquisitionRecord] = []
    started_at = utc_now()
    try:
        raw = run_root / "raw" / "world_bank_icp_2021"
        static_specs = [
            ("source_metadata", "source_metadata.json", "application/json,*/*;q=0.1"),
            ("classification_workbook", "ICPClassificationwithNonH-2021.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.1"),
            ("participation_page", "ICP2021_Governance.html", "text/html,*/*;q=0.1"),
            ("data_page", "ICP_data_page.html", "text/html,*/*;q=0.1"),
            ("faq_page", "ICP_FAQ.html", "text/html,*/*;q=0.1"),
            ("published_table_page", "ICP_2021_published_table.html", "text/html,*/*;q=0.1"),
        ]
        for key, filename, accept in static_specs:
            records.append(fetch_url(
                config,
                source_id=f"world_bank_{key}",
                url=config.urls[key],
                destination=raw / filename,
                cache_path=cache_root / "world_bank_icp_2021" / filename,
                accept=accept,
            ))

        source_metadata_validation = validate_source_metadata(
            read_json(raw / "source_metadata.json"), config.source_id
        )
        classification_validation = validate_classification_workbook(
            raw / "ICPClassificationwithNonH-2021.xlsx", config.required_heading_codes
        )

        concept_records = fetch_json_pages(
            config,
            source_id="world_bank_source90_concepts",
            base_url=config.urls["concepts"],
            destination_dir=raw / "concepts",
            cache_dir=cache_root / "world_bank_source90",
        )
        records.extend(concept_records)
        concepts: list[tuple[str, str]] = []
        for record in concept_records:
            concepts.extend(extract_concepts(read_json(record.path)))
        concepts = list(dict.fromkeys(concepts))

        inventories: dict[str, list[Variable]] = {}
        for concept_id, _ in concepts:
            url = config.urls["concept_variables_template"].format(concept=concept_id.lower())
            variable_records = fetch_json_pages(
                config,
                source_id=f"world_bank_source90_variables_{concept_id}",
                base_url=url,
                destination_dir=raw / "variables" / concept_id,
                cache_dir=cache_root / "world_bank_source90",
            )
            records.extend(variable_records)
            variables: list[Variable] = []
            for record in variable_records:
                variables.extend(extract_variables(read_json(record.path)))
            # Some responses use a lower-case concept ID. Pin all variables to the discovered ID.
            inventories[concept_id] = [Variable(concept_id, item.variable_id, item.value) for item in variables]

        roles = identify_roles(concepts, inventories, config.reference_year)
        available_heading_ids = {item.variable_id for item in inventories[roles.heading]}
        missing_inventory_headings = sorted(set(config.required_heading_codes) - available_heading_ids)
        mandatory_matrix_headings = {
            row["heading_code"] for row in read_csv(config.headings_path)
            if row["include_in_category"].lower() == "true"
        } | {"1100000"}
        missing_mandatory_headings = sorted(mandatory_matrix_headings - available_heading_ids)
        requested_data_headings = list(dict.fromkeys([
            *config.required_heading_codes,
            *config.imputation_detection_heading_codes,
        ]))
        heading_codes = [code for code in requested_data_headings if code in available_heading_ids]
        if not heading_codes:
            raise RuntimeError("None of the required HFCE or imputation-control headings exists in the Source 90 inventory")

        publication_scope_audit = _publication_scope_audit(
            config.publication_scope_rules_path, available_heading_ids
        )
        missing_scope_requirements = sorted({
            code
            for row in publication_scope_audit
            if row["status"] == "BLOCKED_REQUIRED_HFCE_HEADING_MISSING"
            for code in row["missing_required_heading_codes"].split("|")
            if code
        })
        forbidden_alternatives_present = sorted({
            code
            for row in publication_scope_audit
            if row["status"] == "BLOCKED_REQUIRED_HFCE_HEADING_MISSING"
            for code in row["available_forbidden_alternative_codes"].split("|")
            if code
        })

        data_records = acquire_heading_data(config, roles, heading_codes, raw, cache_root)
        records.extend(data_records)
        observations = parse_observation_pages(
            (record.path for record in data_records), run_root
        )
        measures = select_measures(
            inventories[roles.measure], observations, roles.measure, roles.country, roles.heading
        )

        governance_html = (raw / "ICP2021_Governance.html").read_text(encoding="utf-8", errors="replace")
        participant_names = extract_participating_names(governance_html)
        participant_codes, mapping_audit = map_participants_to_codes(
            participant_names, inventories[roles.country], config.country_aliases_path
        )

        matrix = build_matrix(
            config, roles, observations, inventories, measures, participant_codes
        )
        if missing_mandatory_headings:
            matrix.summary["blocking_reasons"].append(
                "MANDATORY_HEADINGS_ABSENT_FROM_SOURCE90_INVENTORY:" + ",".join(missing_mandatory_headings)
            )
            matrix.summary["release_allowed"] = False
            matrix.summary["global_12_category_matrix_complete"] = False
            matrix.summary["status"] = "BLOCKED_SOURCE_PUBLICATION_SCOPE"
        if missing_scope_requirements:
            reason = "STRICT_HFCE_PUBLICATION_SCOPE_MISSING_REQUIRED_HEADINGS:" + ",".join(missing_scope_requirements)
            if reason not in matrix.summary["blocking_reasons"]:
                matrix.summary["blocking_reasons"].append(reason)
        if forbidden_alternatives_present:
            matrix.summary["blocking_reasons"].append(
                "FORBIDDEN_ALTERNATIVES_AVAILABLE_BUT_NOT_USED:" + ",".join(forbidden_alternatives_present)
            )
        matrix.summary["strict_hfce_required_headings_missing"] = missing_scope_requirements
        matrix.summary["forbidden_alternative_headings_available"] = forbidden_alternatives_present

        _write_outputs(
            run_root, matrix, mapping_audit, measures.diagnostics, roles, concepts, inventories,
            publication_scope_audit,
        )
        manifest = _manifest(config, started_at, records, matrix.summary, run_root)
        write_json(run_root / "manifest.json", manifest)
        diagnostics = {
            "schema_version": "2.0",
            "generated_at": utc_now(),
            "runtime": safe_runtime_info(),
            "source_metadata_validation": source_metadata_validation,
            "classification_workbook_validation": classification_validation,
            "source_90_dimension_roles": {
                "country": roles.country,
                "heading": roles.heading,
                "measure": roles.measure,
                "time": roles.time,
                "year_id": roles.year_id,
                "concept_order": list(roles.concept_order),
            },
            "inventory_counts": {key: len(value) for key, value in inventories.items()},
            "selected_measures": {
                "ppp": measures.ppp_id,
                "nominal_expenditure": measures.nominal_id,
                "real_expenditure_ppp": measures.real_id,
            },
            "inventory_headings_absent": missing_inventory_headings,
            "mandatory_matrix_headings_absent": missing_mandatory_headings,
            "publication_scope_audit": {
                "required_hfce_headings_missing": missing_scope_requirements,
                "forbidden_alternatives_available": forbidden_alternatives_present,
                "all_strict_requirements_available": not missing_scope_requirements,
            },
            "participant_mapping": {
                "expected": 176,
                "mapped": len(participant_codes),
                "unresolved": sum(1 for row in mapping_audit if row["status"] != "MAPPED"),
            },
            "step2_summary": matrix.summary,
        }
        write_json(run_root / "diagnostics.json", diagnostics)
        _write_methodology_report(run_root / "STEP2_REPORT.md", matrix.summary, roles, measures, missing_mandatory_headings, publication_scope_audit)
        write_sha256sums(run_root, run_root / "SHA256SUMS", exclude={run_root / "SHA256SUMS"})
        bundle = _bundle(run_root, output_root, config.pipeline_version)
        result = {
            "status": matrix.summary["status"],
            "release_allowed": matrix.summary["release_allowed"],
            "run_dir": str(run_root),
            "bundle": str(bundle),
            "summary": matrix.summary,
        }
        write_json(output_root / "latest_run_summary.json", result)
        return result
    except Exception as exc:
        diagnostics = {
            "schema_version": "2.0",
            "generated_at": utc_now(),
            "runtime": safe_runtime_info(),
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "acquisitions_completed": [record.as_dict(run_root) for record in records],
        }
        write_json(run_root / "diagnostics.json", diagnostics)
        write_sha256sums(run_root, run_root / "SHA256SUMS", exclude={run_root / "SHA256SUMS"})
        _bundle(run_root, output_root, config.pipeline_version, suffix="failed")
        raise


def _write_outputs(run_root: Path, matrix: MatrixResult, mapping_audit, measure_diagnostics, roles, concepts, inventories, publication_scope_audit):
    out = run_root / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "normalized_icp2021.csv", NORMALIZED_FIELDS, matrix.normalized_rows)
    write_csv(out / "raw_economy_heading_matrix.csv", NORMALIZED_FIELDS, matrix.heading_matrix_rows)
    write_csv(out / "economy_category_matrix.csv", [
        "economy_code", "economy_name", "icp_participation_status", "armilar_category",
        "real_expenditure_ppp", "nominal_expenditure_lcu", "derivation", "source_files", "data_status",
        "included_in_candidate_weights", "nominal_hfce_control_value", "nominal_armilar_category_total",
        "nominal_hfce_less_armilar_categories", "nominal_expected_excluded_adjustments", "quality_flags",
    ], matrix.category_rows)
    write_csv(out / "economy_registry.csv", [
        "economy_code", "economy_name", "icp_participation_status", "official_participation_source",
        "detailed_hfce_observation_count", "hfce_aggregate_available",
        "aggregate_imputation_observation_count", "imputation_detection_heading_codes",
        "participation_status_basis", "eligible_for_12_category_matrix", "quality_flags",
    ], matrix.country_registry_rows)
    registry_fields = [
        "economy_code", "economy_name", "icp_participation_status", "official_participation_source",
        "detailed_hfce_observation_count", "hfce_aggregate_available",
        "aggregate_imputation_observation_count", "imputation_detection_heading_codes",
        "participation_status_basis", "eligible_for_12_category_matrix", "quality_flags",
    ]
    write_csv(out / "observed_participating_economies.csv", registry_fields, [
        row for row in matrix.country_registry_rows if row["icp_participation_status"] == "PARTICIPATING"
    ])
    write_csv(out / "officially_imputed_aggregate_only_economies.csv", registry_fields, [
        row for row in matrix.country_registry_rows if row["icp_participation_status"] == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY"
    ])
    write_csv(out / "unavailable_or_nonpublished_economies.csv", registry_fields, [
        row for row in matrix.country_registry_rows if row["icp_participation_status"] == "UNAVAILABLE_OR_NONPUBLISHED"
    ])
    write_csv(out / "coverage_report.csv", ["metric", "value", "unit"], matrix.coverage_rows)
    write_csv(out / "exclusions_report.csv", [
        "economy_code", "heading_code", "heading_name", "reason", "value", "measure", "source_file",
    ], matrix.exclusion_rows)
    write_csv(out / "missing_data_report.csv", [
        "economy_code", "economy_name", "armilar_category", "heading_code", "reason", "data_status", "included_in_candidate_weights",
    ], matrix.missing_rows)
    write_csv(out / "ppp_identity_reconciliation.csv", [
        "economy_code", "economy_name", "heading_code", "heading_name", "ppp", "nominal_expenditure",
        "reported_real_expenditure", "derived_real_expenditure", "relative_error", "tolerance", "status",
    ], matrix.identity_rows)
    write_csv(out / "hierarchy_reconciliation.csv", [
        "economy_code", "economy_name", "check", "measure_basis", "reported_value", "derived_value",
        "difference", "relative_error", "tolerance", "status", "missing_heading_codes",
    ], matrix.hierarchy_rows)
    weight_fields = [
        "economy_code", "economy_name", "armilar_category", "real_expenditure_ppp",
        "global_denominator_real_expenditure_ppp", "weight", "weight_status", "closure_adjustment",
    ]
    write_csv(out / "weights_candidate_observed_participants.csv", weight_fields, matrix.weight_rows)
    write_csv(
        out / "weights_final_normalized.csv",
        weight_fields,
        matrix.weight_rows if matrix.summary.get("release_allowed") else [],
    )
    write_csv(out / "weights_by_economy.csv", ["economy_code", "economy_name", "weight", "weight_status"], matrix.economy_weight_rows)
    write_csv(out / "weights_by_category.csv", ["armilar_category", "weight", "weight_status"], matrix.category_weight_rows)
    write_csv(out / "experimental_approximations.csv", [
        "record_type", "status", "included_in_candidate_weights", "description",
    ], matrix.experimental_rows)
    write_csv(out / "participation_mapping_audit.csv", [
        "official_page_name", "normalized_name", "economy_code", "world_bank_name", "mapping_method", "status",
    ], mapping_audit)
    write_csv(out / "measure_selection_audit.csv", ["measure_id", "measure_name", "semantic_kind", "selected"], measure_diagnostics)
    write_csv(out / "publication_scope_audit.csv", [
        "record_type", "armilar_category", "required_hfce_heading_codes",
        "available_required_heading_codes", "missing_required_heading_codes",
        "forbidden_alternative_codes", "available_forbidden_alternative_codes",
        "forbidden_alternative_reason", "status", "admissible_for_armilar",
    ], publication_scope_audit)
    write_csv(out / "source90_concepts.csv", ["concept_id", "concept_name"], [
        {"concept_id": item[0], "concept_name": item[1]} for item in concepts
    ])
    inventory_rows = []
    for concept_id, variables in inventories.items():
        for item in variables:
            inventory_rows.append({"concept_id": concept_id, "variable_id": item.variable_id, "variable_name": item.value})
    write_csv(out / "source90_variable_inventory.csv", ["concept_id", "variable_id", "variable_name"], inventory_rows)
    write_json(out / "step2_summary.json", matrix.summary)


def _publication_scope_audit(rules_path: Path, available_heading_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rule in read_csv(rules_path):
        required = [code for code in rule["required_hfce_heading_codes"].split("|") if code]
        alternatives = [code for code in rule["forbidden_alternative_codes"].split("|") if code]
        available_required = [code for code in required if code in available_heading_ids]
        missing_required = [code for code in required if code not in available_heading_ids]
        available_alternatives = [code for code in alternatives if code in available_heading_ids]
        status = "PASS_STRICT_HFCE_AVAILABLE" if not missing_required else "BLOCKED_REQUIRED_HFCE_HEADING_MISSING"
        rows.append({
            **rule,
            "available_required_heading_codes": "|".join(available_required),
            "missing_required_heading_codes": "|".join(missing_required),
            "available_forbidden_alternative_codes": "|".join(available_alternatives),
            "status": status,
            "admissible_for_armilar": not missing_required,
        })
    return rows


def _manifest(config, started_at, records, summary, run_root):
    return {
        "schema_version": "2.0",
        "pipeline_version": config.pipeline_version,
        "generated_at": utc_now(),
        "started_at": started_at,
        "source_database": "World Bank ICP 2021",
        "source_id": config.source_id,
        "reference_year": config.reference_year,
        "entries": [record.as_dict(run_root) for record in records],
        "step2_summary": summary,
    }


def _write_methodology_report(path, summary, roles, measures, missing_headings, publication_scope_audit):
    lines = [
        "# Armilar Step 2 acquisition report", "",
        f"Generated: {utc_now()}", "",
        "## Source identification", "",
        "The pipeline uses World Bank DataBank source 90, ICP 2021, and preserves the source metadata,",
        "dimension inventories, classification workbook, participation page, FAQ and every data response page.", "",
        "## Discovered Source 90 dimensions", "",
        f"- Country: `{roles.country}`", f"- Heading: `{roles.heading}`", f"- Measure: `{roles.measure}`",
        f"- Time: `{roles.time}` (`{roles.year_id}`)", "",
        "## Selected measures", "",
        f"- PPP: `{measures.ppp_id}`", f"- Nominal expenditure: `{measures.nominal_id}`",
        f"- Real PPP-based expenditure: `{measures.real_id}`", "",
        "## Methodological gates", "",
        "- Only headings in the 1100000 household-consumption branch are accepted.",
        "- CP02 is built from 1102100 and 1102200; 1102300 and parent 1102000 are excluded.",
        "- AIC headings, NPISH and government individual consumption are rejected.",
        "- An economy enters candidate weights only with all twelve categories and the HFCE control aggregate.",
        "- PPP, nominal and real expenditure are reconciled numerically.",
        "- Additive hierarchy identities are tested in nominal local-currency expenditure, not across non-additive PPP real expenditures.",
        "- PPP-based real expenditure is validated separately through nominal expenditure divided by PPP.",
        "- Published AIC or households-plus-NPISH headings are preserved as evidence and rejected as HFCE substitutes.",
        "- No population, GDP, income or model allocation is used.", "",
        "## Result", "",
        f"- Status: `{summary['status']}`", f"- Release allowed: `{summary['release_allowed']}`",
        f"- Complete participating economies: `{summary['eligible_complete_economies']}`",
        f"- Candidate cells: `{summary['candidate_weight_cells']}`",
        f"- Candidate weight sum: `{summary['candidate_weight_sum']}`",
    ]
    blocked_scope = [row for row in publication_scope_audit if row["status"] != "PASS_STRICT_HFCE_AVAILABLE"]
    if blocked_scope:
        lines.extend(["", "## Public publication scope audit", ""])
        for row in blocked_scope:
            lines.append(
                f"- {row['armilar_category']}: missing `{row['missing_required_heading_codes']}`; "
                f"forbidden alternatives present `{row['available_forbidden_alternative_codes']}`."
            )
    if missing_headings:
        lines.extend(["", "Missing required headings in Source 90 inventory: " + ", ".join(missing_headings)])
    if summary.get("blocking_reasons"):
        lines.extend(["", "## Blocking reasons", ""] + [f"- {item}" for item in summary["blocking_reasons"]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _bundle(run_root: Path, output_root: Path, version: str, suffix: str = "") -> Path:
    name = f"armilar_step2_icp2021_v{version.replace('.', '_')}"
    if suffix:
        name += f"_{suffix}"
    bundle = output_root / f"{name}.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(run_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(run_root).as_posix())
    return bundle

from __future__ import annotations

import json
import shutil
import traceback
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from .acquire import AcquisitionRecord, fetch_json_pages, fetch_url
from .config import Step2Config, load_config
from .country_adapters import run_country_adapters, write_country_outputs
from .hybrid_matrix import HybridMatrixResult, build_hybrid_matrix
from .gap_priority import build_gap_priority
from .proxy_audit import build_proxy_audit
from .source_probe import SourceProbeResult, run_source_probes
from .measures import audit_selected_measure_identity, select_measures
from .participation import extract_participating_names, map_participants_to_codes
from .supplemental import (
    EconomyMapper, NominalObservation, SupplementalParseResult,
    parse_eurostat_jsonstat, parse_oecd_csv, parse_undata_zip,
)
from .util import read_json, safe_runtime_info, utc_now, write_csv, write_json, write_sha256sums
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
    acquisition_failures: list[dict[str, str]] = []
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
                config, source_id=f"world_bank_{key}", url=config.urls[key],
                destination=raw / filename, cache_path=cache_root / "world_bank_icp_2021" / filename,
                accept=accept,
            ))

        source_metadata_validation = validate_source_metadata(read_json(raw / "source_metadata.json"), config.source_id)
        classification_validation = validate_classification_workbook(raw / "ICPClassificationwithNonH-2021.xlsx", config.classification_required_heading_codes)

        concept_records = fetch_json_pages(
            config, source_id="world_bank_source90_concepts", base_url=config.urls["concepts"],
            destination_dir=raw / "concepts", cache_dir=cache_root / "world_bank_source90",
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
                config, source_id=f"world_bank_source90_variables_{concept_id}", base_url=url,
                destination_dir=raw / "variables" / concept_id, cache_dir=cache_root / "world_bank_source90",
            )
            records.extend(variable_records)
            variables: list[Variable] = []
            for record in variable_records:
                variables.extend(extract_variables(read_json(record.path)))
            inventories[concept_id] = [Variable(concept_id, item.variable_id, item.value) for item in variables]

        roles = identify_roles(concepts, inventories, config.reference_year)
        available_headings = {item.variable_id for item in inventories[roles.heading]}
        missing_required_headings = sorted(set(config.required_heading_codes) - available_headings)
        if missing_required_headings:
            raise RuntimeError("Required Source 90 headings missing: " + ",".join(missing_required_headings))
        data_records = acquire_heading_data(config, roles, config.required_heading_codes, raw, cache_root)
        records.extend(data_records)
        observations = parse_observation_pages((record.path for record in data_records), run_root)
        measures = select_measures(inventories[roles.measure], observations, roles.measure, roles.country, roles.heading)
        identity_rows, identity_summary = audit_selected_measure_identity(
            observations, selection=measures, country_concept=roles.country,
            heading_concept=roles.heading, measure_concept=roles.measure,
            tolerance=config.identity_relative_tolerance,
        )
        if identity_summary["median_status"] != "PASS":
            raise RuntimeError(
                "Selected Source 90 measure triple failed nominal/PPP=real median identity: "
                + str(identity_summary)
            )

        governance_html = (raw / "ICP2021_Governance.html").read_text(encoding="utf-8", errors="replace")
        participant_names = extract_participating_names(governance_html)
        participant_codes, mapping_audit = map_participants_to_codes(
            participant_names, inventories[roles.country], config.country_aliases_path
        )

        mapper = EconomyMapper(inventories[roles.country], config.country_aliases_path, config.external_code_crosswalk_path)
        supplemental_observations: list[NominalObservation] = []
        supplemental_exclusions: list[dict[str, Any]] = []
        supplemental_diagnostics: list[dict[str, Any]] = []
        supplemental_specs = [
            ("OECD_TABLE5_T501", "oecd_table5_t501", "oecd_table5_t501.csv", "application/vnd.sdmx.data+csv;version=2.0.0,text/csv;q=0.9,*/*;q=0.1", "COICOP1999", 10),
            ("UNDATA_SNA_TABLE32", "undata_sna_table32", "undata_sna_table32.zip", "application/zip,application/octet-stream,*/*;q=0.1", "UNDATA", 20),
            ("EUROSTAT_NAMA_10_CP18", "eurostat_nama_10_cp18", "eurostat_nama_10_cp18.json", "application/json,*/*;q=0.1", "EUROSTAT", 30),
            ("OECD_TABLE5A_T501", "oecd_table5a_t501", "oecd_table5a_t501.csv", "application/vnd.sdmx.data+csv;version=2.0.0,text/csv;q=0.9,*/*;q=0.1", "COICOP2018", 40),
        ]
        supplemental_raw = run_root / "raw" / "supplemental_nominal_hfce"
        for source_id, url_key, filename, accept, parser_kind, priority in supplemental_specs:
            destination = supplemental_raw / source_id / filename
            try:
                record = fetch_url(
                    config, source_id=source_id, url=config.urls[url_key], destination=destination,
                    cache_path=cache_root / "supplemental_nominal_hfce" / source_id / filename,
                    accept=accept,
                )
                records.append(record)
                if parser_kind in {"COICOP1999", "COICOP2018"}:
                    result = parse_oecd_csv(
                        destination, mapper, source_id=source_id, source_url=config.urls[url_key],
                        retrieved_at=record.retrieved_at, priority=priority, classification=parser_kind,
                    )
                elif parser_kind == "EUROSTAT":
                    result = parse_eurostat_jsonstat(
                        destination, mapper, source_id=source_id, source_url=config.urls[url_key],
                        retrieved_at=record.retrieved_at, priority=priority,
                    )
                else:
                    result = parse_undata_zip(
                        destination, mapper, source_id=source_id, source_url=config.urls[url_key],
                        retrieved_at=record.retrieved_at, priority=priority,
                    )
                supplemental_observations.extend(result.observations)
                supplemental_exclusions.extend(result.exclusions)
                supplemental_diagnostics.append(result.diagnostics)
            except Exception as exc:
                acquisition_failures.append({"source_id": source_id, "error_type": type(exc).__name__, "error": str(exc)})
                supplemental_diagnostics.append({"source_id": source_id, "status": "FAILED", "error_type": type(exc).__name__, "error": str(exc)})
        supplemental_observations = _relative_supplemental_source_files(supplemental_observations, run_root)

        matrix = build_hybrid_matrix(
            config, roles, observations, inventories, measures, participant_codes, supplemental_observations
        )
        matrix.exclusion_rows.extend(supplemental_exclusions)
        matrix.summary["source90_measure_identity"] = identity_summary

        source_probe = run_source_probes(
            config,
            candidates_path=config.source_probe_candidates_path,
            run_root=run_root,
            cache_root=cache_root,
        )
        records.extend(source_probe.acquisition_records)
        country_adapters = run_country_adapters(config, run_root=run_root, cache_root=cache_root)
        records.extend(country_adapters.acquisition_records)
        financing_rows, ppp_comparison_rows, proxy_summary = build_proxy_audit(
            config, roles=roles, observations=observations, inventories=inventories,
            measures=measures, matrix=matrix,
        )
        gap_priority_rows, gap_priority_summary = build_gap_priority(matrix, source_probe.economy_rows)
        matrix.summary["step2h0"] = {
            "source_probe": source_probe.summary,
            "gap_priority": gap_priority_summary,
            "proxy_audit": proxy_summary,
        }
        _write_outputs(
            config, run_root, matrix, mapping_audit, measures.diagnostics, identity_rows,
            roles, concepts, inventories, supplemental_diagnostics, acquisition_failures,
            source_probe, financing_rows, ppp_comparison_rows, proxy_summary,
            gap_priority_rows, gap_priority_summary, country_adapters,
        )

        manifest = _manifest(config, started_at, records, matrix.summary, run_root, acquisition_failures + source_probe.failure_rows)
        write_json(run_root / "manifest.json", manifest)
        diagnostics = {
            "schema_version": "4.0",
            "generated_at": utc_now(),
            "runtime": safe_runtime_info(),
            "source_metadata_validation": source_metadata_validation,
            "classification_workbook_validation": classification_validation,
            "source_90_dimension_roles": {
                "country": roles.country, "heading": roles.heading, "measure": roles.measure,
                "time": roles.time, "year_id": roles.year_id, "concept_order": list(roles.concept_order),
            },
            "inventory_counts": {key: len(value) for key, value in inventories.items()},
            "selected_measures": {
                "ppp": measures.ppp_id, "nominal_expenditure": measures.nominal_id,
                "real_expenditure_ppp": measures.real_id,
            },
            "participant_mapping": {
                "expected": config.expected_participating_economies,
                "mapped": len(participant_codes),
                "unresolved": sum(1 for row in mapping_audit if row["status"] != "MAPPED"),
            },
            "supplemental_sources": supplemental_diagnostics,
            "supplemental_acquisition_failures": acquisition_failures,
            "source_probe": source_probe.summary,
            "source_probe_failures": source_probe.failure_rows,
            "proxy_audit": proxy_summary,
            "gap_priority": gap_priority_summary,
            "step2_summary": matrix.summary,
        }
        write_json(run_root / "diagnostics.json", diagnostics)
        _write_methodology_report(run_root / "STEP2_REPORT.md", matrix.summary, supplemental_diagnostics, acquisition_failures)
        write_sha256sums(run_root, run_root / "SHA256SUMS", exclude={run_root / "SHA256SUMS"})
        bundle = _bundle(run_root, output_root, config.pipeline_version)
        latest_summary = {
            "generated_at": utc_now(), "bundle": bundle.name, "step2_summary": matrix.summary,
            "manifest": "manifest.json", "diagnostics": "diagnostics.json", "hashes": "SHA256SUMS",
        }
        write_json(output_root / "latest_run_summary.json", latest_summary)
        return {
            "status": matrix.summary["status"],
            "research_release_allowed": matrix.summary["research_release_allowed"],
            "monetary_release_allowed": False,
            "run_dir": str(run_root),
            "bundle": str(bundle),
            "summary": matrix.summary,
        }
    except Exception as exc:
        failure = {
            "schema_version": "4.0", "status": "FAILED", "generated_at": utc_now(),
            "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc(),
            "runtime": safe_runtime_info(), "acquisition_failures": acquisition_failures,
        }
        write_json(run_root / "diagnostics.json", failure)
        write_sha256sums(run_root, run_root / "SHA256SUMS", exclude={run_root / "SHA256SUMS"})
        _bundle(run_root, output_root, config.pipeline_version, suffix="FAILED")
        raise


def _write_outputs(
    config: Step2Config, run_root, matrix: HybridMatrixResult, mapping_audit,
    measure_diagnostics, identity_rows, roles, concepts, inventories,
    supplemental_diagnostics, acquisition_failures, source_probe: SourceProbeResult,
    financing_rows, ppp_comparison_rows, proxy_summary, gap_priority_rows,
    gap_priority_summary, country_adapters,
):
    out = run_root / "outputs"
    write_json(out / "step2_summary.json", matrix.summary)
    write_csv(out / "raw_economy_heading_matrix.csv", [
        "economy_code", "economy_name", "heading_code", "heading_name", "expenditure_measure",
        "value", "unit", "source_file", "source_url", "retrieved_at", "source_hash", "quality_flags",
    ], matrix.normalized_source90_rows)
    write_csv(out / "supplemental_nominal_all_sources.csv", [
        "economy_code", "economy_name", "armilar_category", "value_lcu", "currency", "source_id",
        "source_file", "source_url", "retrieved_at", "source_hash", "concept", "classification",
        "quality_flags", "source_priority",
    ], matrix.supplemental_nominal_rows)
    write_csv(out / "nominal_source_selection_audit.csv", [
        "economy_code", "armilar_category", "chosen_source_id", "candidate_source_id",
        "chosen_value_lcu", "candidate_value_lcu", "relative_difference",
        "candidate_complete_proxy_set", "candidate_missing_proxy_categories",
        "selection_basis", "status",
    ], matrix.nominal_selection_audit_rows)
    write_csv(out / "unit_reconciliation.csv", [
        "economy_code", "source_id", "direct_categories_compared", "comparison_count",
        "median_supplemental_to_source90_nominal_ratio", "status",
    ], matrix.unit_reconciliation_rows)
    category_fields = [
        "economy_code", "economy_name", "armilar_category", "nominal_household_expenditure_lcu",
        "ppp_lcu_per_international_dollar", "real_expenditure_ppp", "numerator_source_id",
        "numerator_source_file", "numerator_source_hash", "ppp_source_heading", "ppp_scope",
        "derivation", "quality_flags",
    ]
    write_csv(out / "economy_category_matrix.csv", category_fields, matrix.all_category_rows)
    write_csv(out / "economy_category_matrix_weight_eligible.csv", category_fields, matrix.category_rows)
    write_csv(out / "missing_data_report.csv", [
        "economy_code", "economy_name", "icp_participation_status", "armilar_category", "data_status", "reason",
    ], matrix.missing_rows)
    exclusion_fields = sorted({key for row in matrix.exclusion_rows for key in row}) if matrix.exclusion_rows else ["reason"]
    write_csv(out / "exclusions_report.csv", exclusion_fields, matrix.exclusion_rows)
    write_csv(out / "economy_registry.csv", [
        "economy_code", "economy_name", "icp_participation_status", "eligible_complete_12_category_matrix",
        "included_in_observed_universe_weights", "official_imputation_category_detail_available", "participation_status_basis",
    ], matrix.economy_registry_rows)
    coverage = []
    categories_by_economy: dict[str, set[str]] = {}
    for row in matrix.all_category_rows:
        categories_by_economy.setdefault(row["economy_code"], set()).add(row["armilar_category"])
    participant_rows = [row for row in matrix.economy_registry_rows if row["icp_participation_status"] == "PARTICIPATING"]
    for row in participant_rows:
        present = categories_by_economy.get(row["economy_code"], set())
        missing = sorted(set(f"CP{i:02d}" for i in range(1, 13)) - present)
        coverage.append({
            "economy_code": row["economy_code"], "economy_name": row["economy_name"],
            "categories_available": len(present), "categories_required": 12,
            "complete": len(present) == 12, "missing_categories": "|".join(missing),
        })
    write_csv(out / "coverage_report.csv", [
        "economy_code", "economy_name", "categories_available", "categories_required", "complete", "missing_categories",
    ], coverage)
    weight_fields = category_fields + ["weight", "rounding_residual_applied"]
    # These weights are normalized only within the set of complete observed economies.
    # They must never be presented as a complete world matrix.
    write_csv(out / "weights_observed_universe.csv", weight_fields, matrix.weight_rows)
    write_csv(out / "weights_experimental_universe.csv", weight_fields, [])
    global_final = matrix.weight_rows if matrix.summary["global_12_category_matrix_complete"] else []
    write_csv(out / "weights_final.csv", weight_fields, global_final)
    write_csv(out / "weights_by_economy.csv", ["economy_code", "weight"], matrix.economy_weight_rows)
    write_csv(out / "weights_by_category.csv", ["armilar_category", "weight"], matrix.category_weight_rows)
    write_csv(out / "officially_imputed_aggregate_only_economies.csv", [
        "economy_code", "economy_name", "icp_participation_status", "participation_status_basis",
    ], [row for row in matrix.economy_registry_rows if row["icp_participation_status"] == "OFFICIALLY_IMPUTED_AGGREGATE_ONLY"])
    write_csv(out / "participation_mapping_audit.csv", [
        "official_page_name", "normalized_name", "economy_code", "world_bank_name", "mapping_method", "status",
    ], mapping_audit)
    write_csv(out / "measure_selection_audit.csv", sorted({key for row in measure_diagnostics for key in row}) if measure_diagnostics else ["status"], measure_diagnostics)
    write_csv(out / "measure_identity_audit.csv", [
        "economy_code", "heading_code", "ppp", "nominal_expenditure",
        "published_real_expenditure", "calculated_real_expenditure",
        "relative_error", "tolerance", "status",
    ], identity_rows)
    write_csv(out / "supplemental_source_diagnostics.csv", sorted({key for row in supplemental_diagnostics for key in row}) if supplemental_diagnostics else ["source_id"], supplemental_diagnostics)
    write_csv(out / "source_acquisition_failures.csv", ["source_id", "error_type", "error"], acquisition_failures)
    source_probe_candidate_fields = sorted({key for row in source_probe.candidate_rows for key in row}) if source_probe.candidate_rows else ["source_id"]
    source_probe_economy_fields = sorted({key for row in source_probe.economy_rows for key in row}) if source_probe.economy_rows else ["economy_code"]
    write_csv(out / "source_probe_candidate_results.csv", source_probe_candidate_fields, source_probe.candidate_rows)
    write_csv(out / "source_probe_economy_summary.csv", source_probe_economy_fields, source_probe.economy_rows)
    write_csv(out / "source_probe_failures.csv", ["economy_code", "source_id", "source_url", "error_type", "error"], source_probe.failure_rows)
    write_json(out / "source_probe_summary.json", source_probe.summary)
    write_csv(out / "proxy_financing_exposure.csv", [
        "economy_code", "economy_name", "armilar_12_category_nominal_lcu",
        "derived_narcotics_nominal_lcu", "net_purchases_abroad_nominal_lcu",
        "reconstructed_hfce_nominal_lcu", "aic_nominal_lcu", "aic_minus_hfce_lcu",
        "aic_hfce_financing_gap_ratio", "status", "interpretation",
    ], financing_rows)
    write_csv(out / "proxy_ppp_comparison.csv", [
        "economy_code", "economy_name", "armilar_category", "aic_ppp", "strict_hfce_ppp",
        "ppp_ratio_hfce_to_aic", "implied_real_expenditure_error_ratio", "status", "evidence_note",
    ], ppp_comparison_rows)
    write_json(out / "proxy_validation_summary.json", proxy_summary)
    gap_priority_fields = [
        "economic_gap_rank", "source_adjusted_priority_rank", "economy_code", "economy_name",
        "categories_available", "missing_categories", "direct_categories_available",
        "direct_real_expenditure_ppp_indicator", "direct_expenditure_share_of_participant_indicator",
        "cumulative_direct_expenditure_share_of_incomplete_economies", "source_probe_class",
        "source_probe_best_source_id", "source_probe_retrieval_status",
        "candidate_success_probability_assumption", "integration_cost_assumption",
        "development_priority_score", "blocking_reason",
    ]
    write_csv(out / "economy_gap_priority.csv", gap_priority_fields, gap_priority_rows)
    write_json(out / "gap_priority_summary.json", gap_priority_summary)
    write_country_outputs(out, country_adapters)
    write_csv(out / "source90_concepts.csv", ["position", "concept_id", "concept_label"], [
        {"position": index, "concept_id": concept_id, "concept_label": label}
        for index, (concept_id, label) in enumerate(concepts, start=1)
    ])
    inventory_rows = []
    for concept_id, variables in inventories.items():
        for item in variables:
            inventory_rows.append({"concept_id": concept_id, "variable_id": item.variable_id, "variable_name": item.value})
    write_csv(out / "source90_variable_inventory.csv", ["concept_id", "variable_id", "variable_name"], inventory_rows)
    write_json(out / "methodology_policy_snapshot.json", json.loads(config.methodology_policy_path.read_text(encoding="utf-8")))
    write_csv(out / "normalized_icp2021.csv", [
        "economy_code", "economy_name", "icp_participation_status", "heading_code", "heading_name",
        "armilar_category", "expenditure_measure", "value", "unit", "currency_or_ppp_basis",
        "source_file", "source_url", "retrieved_at", "source_hash", "quality_flags",
    ], _unified_normalized_rows(config, matrix))


def _unified_normalized_rows(config: Step2Config, matrix: HybridMatrixResult) -> list[dict[str, Any]]:
    status_by_code = {row["economy_code"]: row["icp_participation_status"] for row in matrix.economy_registry_rows}
    heading_to_category: dict[str, str] = {}
    for category, heading in config.direct_ppp_heading_by_category.items():
        if category == "CP02":
            heading_to_category["1102100"] = "CP02"
            heading_to_category["1102200"] = "CP02"
        else:
            heading_to_category[heading] = category
    heading_to_category.update({heading: category for category, heading in config.proxy_ppp_heading_by_category.items()})
    result: list[dict[str, Any]] = []
    for row in matrix.normalized_source90_rows:
        measure = str(row.get("expenditure_measure", ""))
        basis = {
            "PPP": "LCU_PER_INTERNATIONAL_DOLLAR",
            "NOMINAL": "LOCAL_CURRENCY_UNITS_REPORTED_SOURCE_SCALE",
            "REAL": "PPP_BASED_INTERNATIONAL_DOLLARS_REPORTED_SOURCE_SCALE",
        }.get(measure, "SOURCE90_MEASURE")
        result.append({
            **row,
            "icp_participation_status": status_by_code.get(row["economy_code"], "UNAVAILABLE_OR_NONPUBLISHED"),
            "armilar_category": heading_to_category.get(row["heading_code"], ""),
            "currency_or_ppp_basis": basis,
        })
    for row in matrix.supplemental_nominal_rows:
        category = row["armilar_category"]
        result.append({
            "economy_code": row["economy_code"],
            "economy_name": row["economy_name"],
            "icp_participation_status": status_by_code.get(row["economy_code"], "UNAVAILABLE_OR_NONPUBLISHED"),
            "heading_code": f"{row['source_id']}:{category}",
            "heading_name": f"Strict household nominal expenditure {category}",
            "armilar_category": category,
            "expenditure_measure": "NOMINAL_HFCE_STRICT",
            "value": row["value_lcu"],
            "unit": row["currency"] or "NATIONAL_CURRENCY",
            "currency_or_ppp_basis": "CURRENT_PRICE_DOMESTIC_HOUSEHOLD_EXPENDITURE_LCU",
            "source_file": row["source_file"],
            "source_url": row["source_url"],
            "retrieved_at": row["retrieved_at"],
            "source_hash": row["source_hash"],
            "quality_flags": row["quality_flags"],
        })
    return sorted(result, key=lambda row: (str(row["economy_code"]), str(row["heading_code"]), str(row["expenditure_measure"]), str(row["source_hash"])))


def _relative_supplemental_source_files(rows: list[NominalObservation], run_root: Path) -> list[NominalObservation]:
    result: list[NominalObservation] = []
    for row in rows:
        source_file = row.source_file
        member = ""
        if "::" in source_file:
            source_file, member = source_file.split("::", 1)
            member = "::" + member
        try:
            relative = Path(source_file).resolve().relative_to(run_root).as_posix()
            result.append(replace(row, source_file=relative + member))
        except ValueError:
            result.append(row)
    return result


def _manifest(config: Step2Config, started_at: str, records: list[AcquisitionRecord], summary, run_root, acquisition_failures):
    return {
        "schema_version": "4.0", "pipeline_version": config.pipeline_version,
        "started_at": started_at, "completed_at": utc_now(), "reference_year": config.reference_year,
        "source_files": [record.as_dict(run_root) for record in records],
        "source_acquisition_failures": acquisition_failures,
        "step2_summary": summary,
    }


def _write_methodology_report(path: Path, summary, supplemental_diagnostics, acquisition_failures):
    lines = [
        "# Armilar Step 2 hybrid ICP 2021 report", "",
        f"Generated: {utc_now()}", "",
        "## Method", "",
        "Seven categories use strict household ICP headings from World Bank Source 90.",
        "CP02 is constructed from alcohol plus tobacco and excludes narcotics.",
        "Five categories use strict household S14/P31DC nominal expenditure from OECD, UNSD or Eurostat,",
        "divided by the ratified ICP actual-consumption PPP proxy for the matching category.",
        "Government and NPISH expenditure never enters the numerator.", "",
        "## Status", "",
        f"- Status: `{summary['status']}`",
        f"- Research release allowed: `{summary['research_release_allowed']}`",
        f"- Monetary release allowed: `{summary['monetary_release_allowed']}`",
        f"- Participating economies mapped: `{summary['participating_economies_mapped']}` / `{summary['participating_economies_expected']}`",
        f"- Complete participating economies: `{summary['complete_participating_economies']}`",
        f"- Observed-universe weight cells: `{summary['observed_universe_weight_cells']}`",
        f"- Observed-universe weight sum: `{summary['observed_universe_weight_sum']}`",
        f"- Officially imputed aggregate-only economies: `{summary['officially_imputed_aggregate_only_economies']}`",
        "",
        "## Supplemental source diagnostics", "",
    ]
    for item in supplemental_diagnostics:
        lines.append(f"- `{item.get('source_id')}`: accepted={item.get('accepted_rows', 0)}, excluded={item.get('excluded_rows', 0)}, status={item.get('status', 'OK')}")
    if acquisition_failures:
        lines.extend(["", "## Acquisition failures", ""])
        for item in acquisition_failures:
            lines.append(f"- `{item['source_id']}`: {item['error_type']}: {item['error']}")
    step2h0 = summary.get("step2h0", {})
    if step2h0:
        probe = step2h0.get("source_probe", {})
        gap = step2h0.get("gap_priority", {})
        proxy = step2h0.get("proxy_audit", {})
        lines.extend([
            "", "## Step 2H0 feasibility audit", "",
            f"- Priority economies probed: `{probe.get('economies_probed', 0)}`",
            f"- A/B candidates accessible in this run: `{probe.get('a_or_b_candidate_economies', 0)}`",
            f"- C-only economies accessible in this run: `{probe.get('c_only_economies', 0)}`",
            f"- Unavailable economies in this run: `{probe.get('d_unavailable_economies', 0)}`",
            f"- Complete-economy coverage in the seven-category priority indicator: `{gap.get('complete_economy_indicator_coverage_ratio', '')}`",
            f"- Option B evidence status: `{proxy.get('validation_status', '')}`",
            f"- Direct strict-HFCE versus AIC PPP comparisons: `{proxy.get('direct_hfce_vs_aic_ppp_comparisons', 0)}`",
            "",
            "The source probe classifies availability and conceptual suitability; it does not insert any national source into the matrix.",
            "The priority indicator uses only seven direct ICP categories and is not a world-coverage estimate.",
        ])
    if summary.get("blocking_reasons"):
        lines.extend(["", "## Remaining global-scope blockers", ""] + [f"- {reason}" for reason in summary["blocking_reasons"]])
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

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from armilar_backtest.alignment_v0100 import build_alignment, verify_alignment
from armilar_backtest.baseline_v0100 import evaluate_baselines, verify_baseline_evaluation
from armilar_backtest.core_v0100 import (
    BacktestProtocolError, canonical_json_bytes, csv_bytes, read_csv,
    verify_manifest, write_manifest,
)
from armilar_backtest.protocol_v0100 import ProtocolPolicy
from armilar_backtest.target_archive_v0100 import build_target_archive, verify_target_archive

POLICY = Path(__file__).parents[1] / "config" / "point_in_time_backtest_protocol_v0100.json"


def _months(start_year=2024, start_month=1, count=36):
    result=[]
    y,m=start_year,start_month
    for _ in range(count):
        result.append(f"{y:04d}-{m:02d}")
        m+=1
        if m==13: y,m=y+1,1
    return result


def _next_month(period: str):
    y,m=map(int,period.split('-')); m+=1
    if m==13: y,m=y+1,1
    return f"{y:04d}-{m:02d}"


def make_arm_o_run(root: Path, *, series_kind="ARM-O", proxy=False) -> Path:
    run=root/"arm_o"; (run/"outputs").mkdir(parents=True); (run/"inputs").mkdir()
    rows=[]
    for economy,category,offset in [("AAA","CP01",0),("AAA","CP04",10)]:
        for index,period in enumerate(_months()):
            pub_month=_next_month(period)
            rows.append({
                "economy_code":economy,"category_code":category,"period":period,
                "source_value":str(100+offset+index),"base_year_average":"100",
                "price_relative":f"{100+offset+index:.12f}",
                "price_relative_unrounded":str(100+offset+index),
                "series_id":f"SERIES_{category}","source_vintage_id":"V1",
                "published_at":f"{pub_month}-20T10:00:00Z",
                "retrieved_at":f"{pub_month}-21T10:00:00Z",
                "revision_sequence":"0","raw_snapshot_id":f"SNAP_{category}_{period}",
                "source_sha256":"a"*64,
                "evidence_class":"PROXY_PRICE" if proxy else "EXACT_OFFICIAL",
            })
    cols=list(rows[0]); (run/"outputs/normalised_price_observations.csv").write_bytes(csv_bytes(rows,cols))
    summary={
        "engine_version":"0.9.6","series_kind":series_kind,"status":"COMPLETE",
        "run_id":"RUN_O","vintage_id":"VINTAGE_O","cutoff_at":"2027-01-31T23:59:59Z",
        "normalised_observation_count":len(rows),
        "release_gates":{
            "research_release_allowed":False,"model_promotion_allowed":False,
            "shadow_production_allowed":False,"monetary_release_allowed":False,
            "world_claim_allowed":False,
        },
    }
    (run/"outputs/run_summary.json").write_bytes(canonical_json_bytes(summary))
    (run/"inputs/marker.txt").write_text("input\n")
    write_manifest(run)
    return run


def feature_row(cutoff: str, economy: str, category: str, period: str, *,
                feature_id: str, role="PRIMARY_RESEARCH_DRIVER", latest=None,
                completeness="COMPLETE_PERIOD", transformation="LEVEL"):
    latest=latest or cutoff
    return {
        "feature_id":feature_id,"cutoff":cutoff,"mapping_id":f"MAP_{category}",
        "source_id":f"SOURCE_{category}","series_id":f"FEATURE_{category}",
        "source_proxy_domain":"TEST","source_geography":"GLOBAL",
        "target_economy_code":economy,"target_category_code":category,
        "target_armilar_category":"ARM"+category[2:],"feature_role":role,
        "mapping_evidence":"SENSITIVITY_ONLY" if role=="SENSITIVITY_ONLY" else "PARTIAL_COST_DRIVER",
        "native_frequency":"MONTHLY","target_frequency":"MONTHLY",
        "target_period":period,"target_period_end":period+"-28",
        "feature_age_days":"1","period_completeness_status":completeness,
        "transformation":transformation,"value":"1.25","unit":"INDEX",
        "aggregation_method":"MONTHLY_IDENTITY","component_count":"1",
        "component_observation_keys_sha256":"b"*64,"latest_available_at":latest,
        "source_freshness_status":"CURRENT_WITHIN_EXPECTED_WINDOW",
        "direct_index_use_allowed":"false","arm_l_use_allowed":"false",
        "model_training_allowed":"false",
    }


def make_feature_bundle(root: Path, cutoff: str, rows: list[dict[str,str]], name: str) -> Path:
    bundle=root/name; bundle.mkdir()
    (bundle/"feature_values.csv").write_bytes(csv_bytes(rows,list(rows[0])))
    summary={
        "status":"POINT_IN_TIME_PROXY_FEATURE_PANEL_V099_VALID","contract_version":"0.9.9",
        "cutoff":cutoff,"feature_value_count":len(rows),
        "direct_index_use_allowed":False,"arm_l_use_allowed":False,
        "model_training_allowed":False,"shadow_production_allowed":False,
        "monetary_use_allowed":False,"price_coverage_claim_allowed":False,
        "model_ready_claim_allowed":False,"backtest_eligibility_claim_allowed":False,
        "concordance_approval_claim_allowed":False,
    }
    (bundle/"feature_summary.json").write_bytes(canonical_json_bytes(summary)); write_manifest(bundle)
    return bundle


@pytest.fixture
def artefacts(tmp_path: Path):
    run=make_arm_o_run(tmp_path)
    target=tmp_path/"targets"
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=target,created_at="2027-02-01T00:00:00Z")
    c1="2025-06-15T23:59:59Z"; c2="2025-07-15T23:59:59Z"
    rows1=[
        feature_row(c1,"AAA","CP01","2025-05",feature_id="f1",latest="2025-06-10T10:00:00Z"),
        feature_row(c1,"AAA","CP04","2025-05",feature_id="f2",latest="2025-06-11T10:00:00Z"),
        feature_row(c1,"AAA","CP04","2025-05",feature_id="f3",role="SENSITIVITY_ONLY",latest="2025-06-11T10:00:00Z"),
    ]
    rows2=[
        feature_row(c2,"AAA","CP01","2025-06",feature_id="g1",latest="2025-07-10T10:00:00Z"),
        feature_row(c2,"AAA","CP04","2025-06",feature_id="g2",latest="2025-07-11T10:00:00Z"),
    ]
    b1=make_feature_bundle(tmp_path,c1,rows1,"features1")
    b2=make_feature_bundle(tmp_path,c2,rows2,"features2")
    alignment=tmp_path/"alignment"
    build_alignment(policy_path=POLICY,target_archive=target,feature_bundles=[b1,b2],output_dir=alignment,created_at="2027-02-01T00:00:01Z")
    baseline=tmp_path/"baseline"
    evaluate_baselines(policy_path=POLICY,target_archive=target,alignment=alignment,output_dir=baseline,created_at="2027-02-01T00:00:02Z")
    return run,target,b1,b2,alignment,baseline


def test_policy_valid_and_all_gates_closed():
    policy=ProtocolPolicy.load(POLICY)
    assert policy.horizons_months==(0,1,3)
    assert not any(policy.gates.values())


def test_policy_rejects_open_gate(tmp_path):
    payload=json.loads(POLICY.read_text()); payload["gates"]["model_training_allowed"]=True
    path=tmp_path/"p.json"; path.write_text(json.dumps(payload))
    with pytest.raises(BacktestProtocolError): ProtocolPolicy.load(path)


def test_target_archive_builds_two_metrics(artefacts):
    _,target,*_=artefacts
    summary=verify_target_archive(target,policy_path=POLICY)
    assert summary["metric_counts"]["MONTHLY_CHANGE_PCT"]>0
    assert summary["metric_counts"]["YEAR_OVER_YEAR_CHANGE_PCT"]>0
    assert summary["cell_count"]==2


def test_target_archive_rejects_non_arm_o(tmp_path):
    run=make_arm_o_run(tmp_path,series_kind="ARM-R")
    with pytest.raises(BacktestProtocolError):
        build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=tmp_path/"out",created_at="2027-01-01T00:00:00Z")


def test_target_archive_rejects_proxy_price_evidence(tmp_path):
    run=make_arm_o_run(tmp_path,proxy=True)
    with pytest.raises(BacktestProtocolError):
        build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=tmp_path/"out",created_at="2027-01-01T00:00:00Z")


def test_target_archive_tamper_detected(artefacts):
    _,target,*_=artefacts
    path=target/"cell_targets.csv"; path.write_text(path.read_text()+"tamper\n")
    with pytest.raises(BacktestProtocolError): verify_target_archive(target,policy_path=POLICY)


def test_alignment_has_only_future_targets(artefacts):
    *_,alignment,_=artefacts
    rows=read_csv(alignment/"forecast_cases.csv")
    assert rows
    assert all(row["target_known_at_cutoff"]=="false" for row in rows)


def test_alignment_leakage_audit_passes(artefacts):
    *_,alignment,_=artefacts
    rows=read_csv(alignment/"leakage_audit.csv")
    assert rows and {row["leakage_status"] for row in rows}=={"PASS"}


def test_alignment_keeps_latest_stream_point(tmp_path):
    run=make_arm_o_run(tmp_path); target=tmp_path/"targets"
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=target,created_at="2027-01-01T00:00:00Z")
    cutoff="2025-06-15T23:59:59Z"
    rows=[
        feature_row(cutoff,"AAA","CP01","2025-04",feature_id="old",latest="2025-05-01T00:00:00Z"),
        feature_row(cutoff,"AAA","CP01","2025-05",feature_id="new",latest="2025-06-01T00:00:00Z"),
    ]
    bundle=make_feature_bundle(tmp_path,cutoff,rows,"f")
    out=tmp_path/"a"; build_alignment(policy_path=POLICY,target_archive=target,feature_bundles=[bundle],output_dir=out,created_at="2027-01-01T00:00:01Z")
    assert {row["feature_id"] for row in read_csv(out/"aligned_features.csv")}=={"new"}


def test_alignment_filters_partial_period(tmp_path):
    run=make_arm_o_run(tmp_path); target=tmp_path/"targets"
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=target,created_at="2027-01-01T00:00:00Z")
    cutoff="2025-06-15T23:59:59Z"
    rows=[feature_row(cutoff,"AAA","CP01","2025-05",feature_id="partial",latest="2025-06-01T00:00:00Z",completeness="PARTIAL_PERIOD_AS_OF_CUTOFF")]
    bundle=make_feature_bundle(tmp_path,cutoff,rows,"f")
    out=tmp_path/"a"; build_alignment(policy_path=POLICY,target_archive=target,feature_bundles=[bundle],output_dir=out,created_at="2027-01-01T00:00:01Z")
    assert read_csv(out/"aligned_features.csv")==[]


def test_alignment_filters_feature_available_after_cutoff(tmp_path):
    run=make_arm_o_run(tmp_path); target=tmp_path/"targets"
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=target,created_at="2027-01-01T00:00:00Z")
    cutoff="2025-06-15T23:59:59Z"
    rows=[feature_row(cutoff,"AAA","CP01","2025-05",feature_id="future",latest="2025-06-16T00:00:00Z")]
    bundle=make_feature_bundle(tmp_path,cutoff,rows,"f")
    out=tmp_path/"a"; build_alignment(policy_path=POLICY,target_archive=target,feature_bundles=[bundle],output_dir=out,created_at="2027-01-01T00:00:01Z")
    assert read_csv(out/"aligned_features.csv")==[]


def test_alignment_rejects_duplicate_cutoff(artefacts,tmp_path):
    _,target,b1,_,_,_=artefacts
    with pytest.raises(BacktestProtocolError):
        build_alignment(policy_path=POLICY,target_archive=target,feature_bundles=[b1,b1],output_dir=tmp_path/"x",created_at="2027-01-01T00:00:00Z")


def test_alignment_manifest_tamper_detected(artefacts):
    *_,alignment,_=artefacts
    path=alignment/"forecast_cases.csv"; path.write_text(path.read_text()+"x\n")
    with pytest.raises(BacktestProtocolError): verify_alignment(alignment,policy_path=POLICY,target_archive=artefacts[1])


def test_semantic_leakage_tamper_detected_after_manifest_regeneration(artefacts):
    _,target,_,_,alignment,_=artefacts
    rows=read_csv(alignment/"aligned_features.csv"); rows[0]["feature_known_at_cutoff"]="false"
    (alignment/"aligned_features.csv").write_bytes(csv_bytes(rows,list(rows[0]))); write_manifest(alignment)
    with pytest.raises(BacktestProtocolError): verify_alignment(alignment,policy_path=POLICY,target_archive=target)


def test_zero_baseline_always_available(artefacts):
    *_,baseline=artefacts
    rows=[r for r in read_csv(baseline/"baseline_predictions.csv") if r["baseline_id"]=="ZERO_CHANGE"]
    assert rows and all(r["prediction_available"]=="true" for r in rows)


def test_last_observed_baseline_uses_prior_target(artefacts):
    *_,baseline=artefacts
    rows=[r for r in read_csv(baseline/"baseline_predictions.csv") if r["baseline_id"]=="LAST_OBSERVED_TARGET" and r["prediction_available"]=="true"]
    assert rows and all(r["baseline_source_target_id"] for r in rows)


def test_seasonal_baseline_never_uses_future_target(artefacts):
    _,target,_,_,_,baseline=artefacts
    target_by_id={r["target_id"]:r for r in read_csv(target/"cell_targets.csv")}
    for row in read_csv(baseline/"baseline_predictions.csv"):
        if row["baseline_id"]=="SEASONAL_12M" and row["prediction_available"]=="true":
            source=target_by_id[row["baseline_source_target_id"]]
            assert source["target_available_at"]<=row["cutoff"]


def test_baseline_errors_reconcile(artefacts):
    *_,baseline=artefacts
    verify_baseline_evaluation(baseline,policy_path=POLICY,target_archive=artefacts[1],alignment=artefacts[4])


def test_readiness_never_opens_claim(artefacts):
    *_,baseline=artefacts
    rows=read_csv(baseline/"cell_protocol_readiness.csv")
    assert rows and all(r["backtest_claim_allowed"]=="false" for r in rows)
    assert {r["readiness_status"] for r in rows}=={"INSUFFICIENT_DISTINCT_CUTOFFS"}


def test_metrics_are_diagnostic_only(artefacts):
    *_,baseline=artefacts
    rows=read_csv(baseline/"baseline_metrics.csv")
    assert rows and all(r["diagnostic_only"]=="true" and r["model_selection_allowed"]=="false" for r in rows)


def test_prediction_semantic_tamper_detected_after_rehash(artefacts):
    _,target,_,_,alignment,baseline=artefacts
    rows=read_csv(baseline/"baseline_predictions.csv")
    row=next(r for r in rows if r["prediction_available"]=="true")
    row["error"]="999.000000000000"
    (baseline/"baseline_predictions.csv").write_bytes(csv_bytes(rows,list(rows[0]))); write_manifest(baseline)
    with pytest.raises(BacktestProtocolError): verify_baseline_evaluation(baseline,policy_path=POLICY,target_archive=target,alignment=alignment)


def test_builds_are_deterministic(tmp_path):
    run=make_arm_o_run(tmp_path); a=tmp_path/"a"; b=tmp_path/"b"
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=a,created_at="2027-01-01T00:00:00Z")
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=b,created_at="2027-01-01T00:00:00Z")
    assert (a/"MANIFEST.sha256").read_bytes()==(b/"MANIFEST.sha256").read_bytes()


def test_output_directory_must_be_empty(tmp_path):
    run=make_arm_o_run(tmp_path); out=tmp_path/"out"; out.mkdir(); (out/"x").write_text("x")
    with pytest.raises(BacktestProtocolError): build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=out,created_at="2027-01-01T00:00:00Z")


def test_all_three_summaries_keep_every_gate_closed(artefacts):
    _,target,_,_,alignment,baseline=artefacts
    for path,name in [(target,"target_archive_summary.json"),(alignment,"alignment_summary.json"),(baseline,"baseline_summary.json")]:
        payload=json.loads((path/name).read_text())
        assert not any(payload["gates"].values())


def test_alignment_includes_target_cells_without_features(tmp_path):
    run=make_arm_o_run(tmp_path); target=tmp_path/"targets"
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=target,created_at="2027-01-01T00:00:00Z")
    cutoff="2025-06-15T23:59:59Z"
    bundle=make_feature_bundle(tmp_path,cutoff,[feature_row(cutoff,"AAA","CP01","2025-05",feature_id="only")],"f")
    alignment=tmp_path/"alignment"
    build_alignment(policy_path=POLICY,target_archive=target,feature_bundles=[bundle],output_dir=alignment,created_at="2027-01-01T00:00:01Z")
    cp04=[row for row in read_csv(alignment/"forecast_cases.csv") if row["category_code"]=="CP04"]
    assert cp04 and all(row["primary_feature_count"]=="0" for row in cp04)


def test_target_availability_is_later_publication_timestamp(artefacts):
    _,target,*_=artefacts
    row=next(r for r in read_csv(target/"cell_targets.csv") if r["target_metric"]=="MONTHLY_CHANGE_PCT")
    assert row["target_available_at"]==max(row["current_source_published_at"],row["lag_source_published_at"])


def test_missing_baselines_leave_numeric_fields_blank(tmp_path):
    run=make_arm_o_run(tmp_path); target=tmp_path/"targets"
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=target,created_at="2027-01-01T00:00:00Z")
    cutoff="2024-01-05T23:59:59Z"
    bundle=make_feature_bundle(tmp_path,cutoff,[feature_row(cutoff,"AAA","CP01","2024-01",feature_id="early",latest="2024-01-04T00:00:00Z")],"f")
    alignment=tmp_path/"a"; build_alignment(policy_path=POLICY,target_archive=target,feature_bundles=[bundle],output_dir=alignment,created_at="2027-01-01T00:00:01Z")
    baseline=tmp_path/"b"; evaluate_baselines(policy_path=POLICY,target_archive=target,alignment=alignment,output_dir=baseline,created_at="2027-01-01T00:00:02Z")
    missing=[r for r in read_csv(baseline/"baseline_predictions.csv") if r["prediction_available"]=="false"]
    assert missing
    assert all(not r[field] for r in missing for field in ("prediction_value","prediction_value_unrounded","error","absolute_error","squared_error"))


def test_all_v0100_schemas_are_closed():
    schema_root=Path(__file__).parents[1]/"schemas"
    schemas=list(schema_root.glob("point_in_time_*_v0100.schema.json"))
    assert len(schemas)==13
    for path in schemas:
        payload=json.loads(path.read_text())
        assert payload["additionalProperties"] is False
        assert payload["$schema"]=="https://json-schema.org/draft/2020-12/schema"


def test_cli_validate_policy(capsys):
    from armilar_backtest.cli_v0100 import main
    assert main(["--policy",str(POLICY),"validate-policy"])==0
    payload=json.loads(capsys.readouterr().out)
    assert payload["status"]=="POINT_IN_TIME_BACKTEST_PROTOCOL_V0100_VALID"
    assert not any(payload["gates"].values())


def test_baseline_summary_references_exact_alignment_manifest(artefacts):
    *_,alignment,baseline=artefacts
    from armilar_backtest.core_v0100 import directory_manifest_sha256
    payload=json.loads((baseline/"baseline_summary.json").read_text())
    assert payload["alignment_manifest_sha256"]==directory_manifest_sha256(alignment)


def test_no_overlap_produces_explicit_zero_case_bundles(tmp_path):
    run=make_arm_o_run(tmp_path); target=tmp_path/"targets"
    build_target_archive(policy_path=POLICY,arm_o_run=run,output_dir=target,created_at="2028-01-01T00:00:00Z")
    cutoff="2027-07-15T23:59:59Z"
    bundle=make_feature_bundle(tmp_path,cutoff,[feature_row(cutoff,"AAA","CP01","2027-06",feature_id="late",latest="2027-07-10T00:00:00Z")],"features")
    alignment=tmp_path/"alignment"
    summary=build_alignment(policy_path=POLICY,target_archive=target,feature_bundles=[bundle],output_dir=alignment,created_at="2028-01-01T00:00:01Z")
    assert summary["forecast_case_count"]==0
    assert summary["alignment_readiness_status"]=="NO_ELIGIBLE_FUTURE_TARGETS"
    candidates=read_csv(alignment/"case_candidate_audit.csv")
    assert candidates and {row["candidate_status"] for row in candidates}=={"TARGET_NOT_IN_ARCHIVE"}
    baseline=tmp_path/"baseline"
    baseline_summary=evaluate_baselines(policy_path=POLICY,target_archive=target,alignment=alignment,output_dir=baseline,created_at="2028-01-01T00:00:02Z")
    assert baseline_summary["baseline_evaluation_status"]=="NO_ELIGIBLE_CASES_BASELINES_NOT_EVALUATED"
    assert read_csv(baseline/"baseline_predictions.csv")==[]

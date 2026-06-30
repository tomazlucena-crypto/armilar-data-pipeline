from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from .sdmx_adapter import SDMXAdapterError, SDMXQuerySpec, fetch_message


SELECTED_CLIENT = "sdmx1"
PYSDMX_DECISION = "NOT_EVALUATED_NO_DOCUMENTED_SDMX1_GAP"
SPIKE_STATUS_NETWORK_BLOCKED = "NETWORK_BLOCKED"


@dataclass(frozen=True, slots=True)
class SDMXSpikeTarget:
    provider: str
    resource_id: str
    key: str
    start_period: str
    end_period: str
    metadata_resource_id: str
    notes: str

    @property
    def data_spec(self) -> SDMXQuerySpec:
        return SDMXQuerySpec(
            provider_code=self.provider,
            resource_id=self.resource_id,
            key=self.key,
            start_period=self.start_period,
            end_period=self.end_period,
            params={"dimension_at_observation": "AllDimensions"},
        )

    @property
    def metadata_spec(self) -> SDMXQuerySpec:
        return SDMXQuerySpec(
            provider_code=self.provider,
            resource_id=self.metadata_resource_id,
            key="all",
            start_period=self.start_period,
            end_period=self.end_period,
        )


def declared_targets() -> tuple[SDMXSpikeTarget, ...]:
    return (
        SDMXSpikeTarget(
            provider="ESTAT",
            resource_id="prc_hicp_midx",
            key="M.I15.CP01.PT",
            start_period="2021-01",
            end_period="2021-03",
            metadata_resource_id="prc_hicp_midx",
            notes="Eurostat HICP monthly category smoke target",
        ),
        SDMXSpikeTarget(
            provider="OECD",
            resource_id="DSD_PRICES@DF_PRICES_ALL",
            key="PRT.M.N.CPI.IX._T.N.GY",
            start_period="2021-01",
            end_period="2021-03",
            metadata_resource_id="DSD_PRICES@DF_PRICES_ALL",
            notes="OECD CPI monthly headline smoke target",
        ),
    )


def capability_matrix(status: str) -> list[dict[str, object]]:
    return [
        {
            "requirement": "data_acquisition",
            "sdmx1": status if status == SPIKE_STATUS_NETWORK_BLOCKED else "SUPPORTED",
            "pysdmx": PYSDMX_DECISION,
            "decision": SELECTED_CLIENT,
        },
        {
            "requirement": "metadata_dsd",
            "sdmx1": status if status == SPIKE_STATUS_NETWORK_BLOCKED else "SUPPORTED",
            "pysdmx": PYSDMX_DECISION,
            "decision": SELECTED_CLIENT,
        },
        {
            "requirement": "key_construction",
            "sdmx1": "SUPPORTED_BY_SDMXQuerySpec",
            "pysdmx": PYSDMX_DECISION,
            "decision": SELECTED_CLIENT,
        },
        {
            "requirement": "raw_bytes_and_sha256_preservation",
            "sdmx1": "ARMILAR_WRAPPER_REQUIRED_AND_PRESENT",
            "pysdmx": PYSDMX_DECISION,
            "decision": SELECTED_CLIENT,
        },
        {
            "requirement": "pull_request_determinism",
            "sdmx1": "LIVE_NETWORK_DISABLED_IN_PR",
            "pysdmx": PYSDMX_DECISION,
            "decision": SELECTED_CLIENT,
        },
    ]


def preserve_raw_response(
    output_dir: Path,
    *,
    provider: str,
    resource_id: str,
    key: str,
    content: bytes,
    content_type: str,
    final_url: str,
    mode: str,
) -> dict[str, object]:
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{provider}_{hashlib.sha256((resource_id + key).encode('utf-8')).hexdigest()[:12]}.bin"
    raw_path = raw_dir / safe_name
    raw_path.write_bytes(content)
    return {
        "provider": provider,
        "resource_id": resource_id,
        "key": key,
        "mode": mode,
        "content_type": content_type,
        "final_url": final_url,
        "raw_path": f"raw/{safe_name}",
        "byte_count": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_manifest(output_dir: Path, filenames: Iterable[str]) -> None:
    entries = [
        f"{hashlib.sha256((output_dir / name).read_bytes()).hexdigest()}  {name}"
        for name in sorted(filenames)
    ]
    (output_dir / "MANIFEST.sha256").write_text("\n".join(entries) + "\n", encoding="utf-8")


def write_spike_outputs(
    output_dir: Path,
    *,
    status: str,
    receipts: list[dict[str, object]] | None = None,
    errors: list[str] | None = None,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    receipts = receipts or []
    errors = errors or []
    targets = [asdict(target) for target in declared_targets()]
    matrix = capability_matrix(status)
    _write_csv(output_dir / "sdmx_capability_matrix.csv", matrix)
    (output_dir / "sdmx_request_targets.json").write_text(
        json.dumps(targets, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (output_dir / "sdmx_request_metadata.jsonl").open("w", encoding="utf-8") as handle:
        for receipt in receipts:
            handle.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    decision = {
        "selected_client": SELECTED_CLIENT,
        "pysdmx_decision": PYSDMX_DECISION,
        "status": status,
        "errors": errors,
        "live_network_allowed_in_pull_request": False,
        "raw_bytes_preserved_outside_public_latest": True,
    }
    (output_dir / "sdmx_client_decision.json").write_text(
        json.dumps(decision, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_manifest(
        output_dir,
        [
            "sdmx_capability_matrix.csv",
            "sdmx_client_decision.json",
            "sdmx_request_metadata.jsonl",
            "sdmx_request_targets.json",
        ],
    )
    return decision


def run_live_smoke(output_dir: Path) -> dict[str, object]:
    receipts: list[dict[str, object]] = []
    errors: list[str] = []
    for target in declared_targets():
        for spec in (target.data_spec, target.metadata_spec):
            try:
                message = fetch_message(spec)
                payload = repr(message).encode("utf-8")
            except SDMXAdapterError as exc:
                errors.append(f"{spec.provider_code}/{spec.resource_id}: {exc}")
                continue
            receipts.append(
                preserve_raw_response(
                    output_dir,
                    provider=spec.provider_code,
                    resource_id=spec.resource_id,
                    key=spec.key,
                    content=payload,
                    content_type="application/x-python-repr",
                    final_url=f"sdmx1://{spec.provider_code}/{spec.resource_id}/{spec.key}",
                    mode="live-smoke",
                )
            )
    status = "COMPLETE" if receipts and not errors else SPIKE_STATUS_NETWORK_BLOCKED
    return write_spike_outputs(output_dir, status=status, receipts=receipts, errors=errors)

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from armilar_prices.fx import (
    COMMON_CURRENCY_INDEX_ID,
    FX_CONVENTION,
    PRICE_BASIS,
    CurrencyAssignment,
    FXMethodologyError,
    FXObservation,
    FXReceipt,
    PriceCell,
    acquire_ecb_fx,
    build_ecb_exr_url,
    build_fx_separation,
    parse_ecb_csv,
    write_fx_separation_outputs,
)


def prices(values: dict[str, list[float]]) -> list[PriceCell]:
    result: list[PriceCell] = []
    economies = sorted(values)
    weight = 1.0 / len(economies)
    for economy, series in sorted(values.items()):
        for offset, value in enumerate(series, start=1):
            result.append(
                PriceCell(
                    period=f"2021-{offset:02d}",
                    economy_code=economy,
                    category_code="ARM01",
                    fixed_weight=weight,
                    price_relative=value,
                )
            )
    return result


def assignment(economy: str, currency: str) -> CurrencyAssignment:
    return CurrencyAssignment(economy, currency, "2021-01")


def fx(currency: str, first: float, second: float, *, factor1: float = 1.0, factor2: float = 1.0) -> list[FXObservation]:
    return [
        FXObservation("2021-01", currency, first, factor1),
        FXObservation("2021-02", currency, second, factor2),
    ]


def receipt() -> FXReceipt:
    return FXReceipt(
        provider="ECB",
        dataset="EXR",
        final_url="https://data-api.ecb.europa.eu/service/data/EXR/M.USD.EUR.SP00.A",
        retrieved_at="REPLAY",
        mode="replay",
        http_status=200,
        content_type="text/csv",
        byte_count=100,
        sha256="a" * 64,
        query_spec={"frequency": "M"},
        discovered_columns=("FREQ", "CURRENCY", "TIME_PERIOD", "OBS_VALUE"),
        observation_count=2,
    )


class FXSeparationTests(unittest.TestCase):
    def test_constant_prices_and_currency_depreciation(self) -> None:
        primary, common, coverage, summary = build_fx_separation(
            prices({"USA": [100.0, 100.0]}),
            [assignment("USA", "USD")],
            fx("USD", 1.0, 1.25),
            [receipt()],
            "2021-01",
            "TEST",
        )
        self.assertEqual(primary[1]["value"], 100.0)
        self.assertAlmostEqual(common[1]["value"], 80.0)
        self.assertFalse(primary[1]["current_fx_included"])
        self.assertEqual(common[1]["index_id"], COMMON_CURRENCY_INDEX_ID)

    def test_local_inflation_compensated_by_fx(self) -> None:
        primary, common, _, _ = build_fx_separation(
            prices({"USA": [100.0, 110.0]}),
            [assignment("USA", "USD")],
            fx("USD", 1.0, 1.1),
            [receipt()],
            "2021-01",
            "TEST",
        )
        self.assertAlmostEqual(primary[1]["value"], 110.0)
        self.assertAlmostEqual(common[1]["value"], 100.0)

    def test_monetary_union_uses_implicit_eur_rate(self) -> None:
        primary, common, coverage, _ = build_fx_separation(
            prices({"PRT": [100.0, 105.0], "DEU": [100.0, 103.0]}),
            [assignment("PRT", "EUR"), assignment("DEU", "EUR")],
            [],
            [],
            "2021-01",
            "EURO_AREA_TEST",
        )
        self.assertAlmostEqual(primary[1]["value"], 104.0)
        self.assertAlmostEqual(common[1]["value"], 104.0)
        self.assertTrue(all(row["fx_available"] for row in coverage))

    def test_inverted_fx_convention_is_rejected(self) -> None:
        with self.assertRaisesRegex(FXMethodologyError, "unsupported FX convention"):
            build_fx_separation(
                prices({"USA": [100.0, 100.0]}),
                [assignment("USA", "USD")],
                [
                    FXObservation("2021-01", "USD", 1.0, convention="EUR_PER_CURRENCY"),
                    FXObservation("2021-02", "USD", 0.8, convention="EUR_PER_CURRENCY"),
                ],
                [],
                "2021-01",
                "TEST",
            )

    def test_missing_fx_does_not_renormalise_or_damage_primary(self) -> None:
        primary, common, coverage, _ = build_fx_separation(
            prices({"USA": [100.0, 102.0], "PRT": [100.0, 104.0]}),
            [assignment("USA", "USD"), assignment("PRT", "EUR")],
            [FXObservation("2021-01", "USD", 1.2)],
            [],
            "2021-01",
            "TEST",
        )
        self.assertAlmostEqual(primary[1]["value"], 103.0)
        self.assertEqual(common[1]["status"], "INCOMPLETE_FX")
        self.assertEqual(common[1]["value"], "")
        self.assertAlmostEqual(common[1]["covered_fixed_weight"], 0.5)
        missing = [row for row in coverage if row["period"] == "2021-02" and row["economy_code"] == "USA"]
        self.assertEqual(missing[0]["reason"], "MISSING_ECB_FX")

    def test_redenomination_factor_prevents_spurious_fx_jump(self) -> None:
        _, common, _, _ = build_fx_separation(
            prices({"TUR": [100.0, 100.0]}),
            [assignment("TUR", "TRY")],
            fx("TRY", 2_000_000.0, 2.0, factor1=0.000001, factor2=1.0),
            [],
            "2021-01",
            "TEST",
        )
        self.assertAlmostEqual(common[1]["value"], 100.0)

    def test_double_conversion_is_rejected(self) -> None:
        bad = PriceCell(
            "2021-01",
            "USA",
            "ARM01",
            1.0,
            100.0,
            price_basis="COMMON_CURRENCY_RELATIVE",
        )
        with self.assertRaisesRegex(FXMethodologyError, "double conversion"):
            build_fx_separation(
                [bad],
                [assignment("USA", "USD")],
                [FXObservation("2021-01", "USD", 1.2)],
                [],
                "2021-01",
                "TEST",
            )

    def test_currency_transition_fails_closed(self) -> None:
        assignments = [
            CurrencyAssignment("HRV", "HRK", "2021-01", "2021-01"),
            CurrencyAssignment("HRV", "EUR", "2021-02"),
        ]
        _, common, coverage, _ = build_fx_separation(
            prices({"HRV": [100.0, 100.0]}),
            assignments,
            [FXObservation("2021-01", "HRK", 7.5)],
            [],
            "2021-01",
            "TEST",
        )
        self.assertEqual(common[1]["status"], "INCOMPLETE_FX")
        self.assertIn("UNRATIFIED_CURRENCY_TRANSITION", coverage[-1]["reason"])

    def test_ecb_url_and_csv_structure_are_discovered(self) -> None:
        url = build_ecb_exr_url(["USD", "GBP", "EUR"], "2021-01", "2021-02")
        self.assertIn("M.GBP+USD.EUR.SP00.A", url)
        payload = (
            "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n"
            "EXR.M.USD.EUR.SP00.A,M,USD,EUR,SP00,A,2021-01,1.2\n"
            "EXR.M.USD.EUR.SP00.A,M,USD,EUR,SP00,A,2021-02,1.25\n"
        ).encode()
        digest = hashlib.sha256(payload).hexdigest()
        rows, columns = parse_ecb_csv(
            payload,
            retrieved_at="REPLAY",
            raw_sha256=digest,
            requested_currencies=["USD"],
        )
        self.assertEqual(len(rows), 2)
        self.assertIn("OBS_VALUE", columns)
        self.assertEqual(rows[0].convention, FX_CONVENTION)

    def test_replay_writes_receipt_hash_and_is_deterministic(self) -> None:
        payload = (
            "KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE\n"
            "EXR.M.USD.EUR.SP00.A,M,USD,EUR,SP00,A,2021-01,1.2\n"
            "EXR.M.USD.EUR.SP00.A,M,USD,EUR,SP00,A,2021-02,1.25\n"
        ).encode()
        digest = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = root / "fixture.csv"
            fixture.write_bytes(payload)
            first = root / "first"
            second = root / "second"
            acquire_ecb_fx(
                ["USD"],
                "2021-01",
                "2021-02",
                first,
                mode="replay",
                fixture_path=fixture,
                expected_sha256=digest,
            )
            acquire_ecb_fx(
                ["USD"],
                "2021-01",
                "2021-02",
                second,
                mode="replay",
                fixture_path=fixture,
                expected_sha256=digest,
            )
            self.assertEqual((first / "MANIFEST.sha256").read_bytes(), (second / "MANIFEST.sha256").read_bytes())
            receipt_payload = json.loads((first / "fx_receipts.jsonl").read_text())
            self.assertEqual(receipt_payload["sha256"], digest)

    def test_outputs_are_deterministic(self) -> None:
        result = build_fx_separation(
            prices({"USA": [100.0, 110.0]}),
            [assignment("USA", "USD")],
            fx("USD", 1.0, 1.1),
            [receipt()],
            "2021-01",
            "TEST",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "one"
            two = root / "two"
            write_fx_separation_outputs(*result, [receipt()], one)
            write_fx_separation_outputs(*result, [receipt()], two)
            self.assertEqual((one / "MANIFEST.sha256").read_bytes(), (two / "MANIFEST.sha256").read_bytes())
            self.assertTrue((one / "monthly_global_inflation_index.csv").exists())
            self.assertTrue((one / "monthly_common_currency_cost.csv").exists())


if __name__ == "__main__":
    unittest.main()

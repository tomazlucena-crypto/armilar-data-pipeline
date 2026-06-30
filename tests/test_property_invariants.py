from __future__ import annotations

import math
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies as st

from armilar_global_weights.builder import BuildError, build_release, validate_complete_grid
from armilar_global_weights.models import CATEGORIES, EvidenceClass, WeightCell as GlobalWeightCell
from armilar_prices.completion import (
    CompletionPolicy,
    EconomyProfile,
    ObservedPrice,
    PriceCompletionError,
    WeightCell,
    predict_monthly_rate,
)
from armilar_prices.fx import FXMethodologyError, FXObservation
from armilar_prices.index_engine import IndexBuildError, load_global_weights


settings.register_profile(
    "armilar_ci",
    max_examples=25,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
settings.load_profile("armilar_ci")


def _global_cell(economy: str, category: str, value: float) -> GlobalWeightCell:
    return GlobalWeightCell(
        economy_code=economy,
        category_code=category,
        real_expenditure_central=value,
        real_expenditure_lower=value,
        real_expenditure_upper=value,
        evidence_class=EvidenceClass.A_OFFICIAL_EXACT,
        method_id="DIRECT",
        model_version="property",
        source_ids=("S",),
    )


def _complete_grid_cells(economies: tuple[str, ...], values: list[float]) -> list[GlobalWeightCell]:
    return [
        _global_cell(economy, category, values[index] + 1.0)
        for index, (economy, category) in enumerate(
            (economy, category) for economy in economies for category in CATEGORIES
        )
    ]


class PropertyInvariantTests(unittest.TestCase):
    @given(st.lists(st.floats(min_value=1, max_value=1000, allow_nan=False, allow_infinity=False), min_size=24, max_size=24))
    def test_weight_release_sum_is_exact_and_order_invariant(self, values: list[float]) -> None:
        cells = _complete_grid_cells(("AAA", "BBB"), values)
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = build_release(cells, Path(first_tmp))
            second = build_release(list(reversed(cells)), Path(second_tmp))
            self.assertTrue(math.isclose(first["weight_sum"], 1.0, rel_tol=0.0, abs_tol=1e-18))
            self.assertEqual(first["cell_count"], second["cell_count"])
            self.assertEqual(
                (Path(first_tmp) / "weights_global.csv").read_text(encoding="utf-8"),
                (Path(second_tmp) / "weights_global.csv").read_text(encoding="utf-8"),
            )

    @given(st.sampled_from(CATEGORIES))
    def test_duplicate_weight_cells_are_rejected(self, category: str) -> None:
        cells = [_global_cell("AAA", category, 1.0), _global_cell("AAA", category, 2.0)]
        with self.assertRaises(BuildError):
            validate_complete_grid(cells)

    @given(st.sampled_from(CATEGORIES[:-1]))
    def test_incomplete_grids_are_rejected(self, omitted: str) -> None:
        cells = [_global_cell("AAA", category, 1.0) for category in CATEGORIES if category != omitted]
        with self.assertRaises(BuildError):
            validate_complete_grid(cells)

    @given(st.floats(min_value=0.0, max_value=0.9, allow_nan=False, allow_infinity=False))
    def test_weight_loader_rejects_silent_renormalisation(self, first_weight: float) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weights.csv"
            second_weight = max(0.0, min(0.9, first_weight / 2))
            path.write_text(
                "economy_code,category_code,weight\n"
                f"AAA,CP01,{first_weight:.12f}\n"
                f"AAA,CP02,{second_weight:.12f}\n",
                encoding="utf-8",
            )
            with self.assertRaises(IndexBuildError):
                load_global_weights(path)

    @given(st.floats(min_value=0.01, max_value=0.50, allow_nan=False, allow_infinity=False))
    def test_future_observations_do_not_change_prior_prediction(self, future_change: float) -> None:
        policy = CompletionPolicy(
            "property",
            ("ARM01",),
            2,
            2,
            10,
            Decimal("0.10"),
            Decimal("0.90"),
            Decimal("0.03"),
            (1,),
            False,
            False,
        )
        profiles = {
            "AAA": EconomyProfile("AAA", "R", "H", ()),
            "BBB": EconomyProfile("BBB", "R", "H", ()),
            "CCC": EconomyProfile("CCC", "R", "H", ()),
        }
        weights = {"AAA": Decimal("0.4"), "BBB": Decimal("0.3"), "CCC": Decimal("0.3")}
        base = [
            ObservedPrice("AAA", "HEADLINE", "2021-01", Decimal("100"), "P3_OFFICIAL_HEADLINE", ("A",)),
            ObservedPrice("AAA", "HEADLINE", "2021-02", Decimal("101"), "P3_OFFICIAL_HEADLINE", ("A",)),
            ObservedPrice("BBB", "HEADLINE", "2021-01", Decimal("100"), "P3_OFFICIAL_HEADLINE", ("B",)),
            ObservedPrice("BBB", "HEADLINE", "2021-02", Decimal("101"), "P3_OFFICIAL_HEADLINE", ("B",)),
            ObservedPrice("BBB", "ARM01", "2021-01", Decimal("100"), "P1_OFFICIAL_CATEGORY", ("B",)),
            ObservedPrice("BBB", "ARM01", "2021-02", Decimal("103"), "P1_OFFICIAL_CATEGORY", ("B",)),
            ObservedPrice("CCC", "HEADLINE", "2021-01", Decimal("100"), "P3_OFFICIAL_HEADLINE", ("C",)),
            ObservedPrice("CCC", "HEADLINE", "2021-02", Decimal("101"), "P3_OFFICIAL_HEADLINE", ("C",)),
            ObservedPrice("CCC", "ARM01", "2021-01", Decimal("100"), "P1_OFFICIAL_CATEGORY", ("C",)),
            ObservedPrice("CCC", "ARM01", "2021-02", Decimal("103"), "P1_OFFICIAL_CATEGORY", ("C",)),
        ]
        with_future = base + [
            ObservedPrice("BBB", "ARM01", "2021-03", Decimal(str(103 * (1 + future_change))), "P1_OFFICIAL_CATEGORY", ("B",))
        ]
        first = predict_monthly_rate(
            target_economy="AAA",
            category="ARM01",
            period="2021-02",
            by_key={(row.economy_code, row.category_code, row.period): row for row in base},
            profiles=profiles,
            economy_weights=weights,
            policy=policy,
        )
        second = predict_monthly_rate(
            target_economy="AAA",
            category="ARM01",
            period="2021-02",
            by_key={(row.economy_code, row.category_code, row.period): row for row in with_future},
            profiles=profiles,
            economy_weights=weights,
            policy=policy,
        )
        self.assertEqual(first.central_rate, second.central_rate)

    @given(st.text(min_size=3, max_size=3).filter(lambda value: value != "EUR"))
    def test_fx_conventions_and_inversions_are_rejected(self, code: str) -> None:
        with self.assertRaises(FXMethodologyError):
            FXObservation(
                period="2021-01",
                currency_code=code.upper(),
                currency_units_per_eur=0.9,
                convention="EUR_PER_CURRENCY_UNIT",
                provider="ECB",
                dataset="EXR",
            ).validate()


if __name__ == "__main__":
    unittest.main()

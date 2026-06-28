import csv
import io
import json
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

from armilar_pipeline.supplemental import (
    EconomyMapper, NominalObservation, parse_eurostat_jsonstat,
    parse_oecd_csv, parse_undata_zip, select_nominal_sources,
)
from armilar_pipeline.worldbank import Variable

ROOT = Path(__file__).resolve().parents[1]


def mapper():
    variables = [
        Variable("Country", "DEU", "Germany"),
        Variable("Country", "RUT", "Russian Federation"),
        Variable("Country", "BON", "Bonaire"),
    ]
    return EconomyMapper(variables, ROOT / "config" / "country_name_aliases.csv", ROOT / "config" / "external_economy_codes.csv")


class SupplementalTests(unittest.TestCase):
    def test_oecd_current_price_household_domestic_rows_and_unit_multiplier(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oecd.csv"
            fields = ["FREQ","REF_AREA","SECTOR","TRANSACTION","EXPENDITURE","UNIT_MEASURE","PRICE_BASE","TIME_PERIOD","OBS_VALUE","UNIT_MULT","CURRENCY"]
            rows = [
                ["A","DEU","S14","P31DC","CP04","XDC","V","2021","123.5","6","EUR"],
                ["A","DEU","S14","P31DC","CP12","XDC","V","2021","10","6","EUR"],
            ]
            with path.open("w", newline="", encoding="utf-8") as f:
                w=csv.writer(f); w.writerow(fields); w.writerows(rows)
            result = parse_oecd_csv(path, mapper(), source_id="OECD_TABLE5_T501", source_url="https://example", retrieved_at="2026-01-01T00:00:00Z", priority=10, classification="COICOP1999")
            self.assertEqual(len(result.observations), 2)
            cp04 = next(x for x in result.observations if x.armilar_category == "CP04")
            self.assertEqual(cp04.value_lcu, Decimal("123500000"))
            self.assertEqual(cp04.economy_code, "DEU")

    def test_oecd_coicop2018_cp12_bridge_sums_cp12_and_cp13(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oecd.csv"
            fields = ["FREQ","REF_AREA","SECTOR","TRANSACTION","EXPENDITURE","UNIT_MEASURE","PRICE_BASE","TIME_PERIOD","OBS_VALUE","UNIT_MULT","CURRENCY"]
            rows = [
                ["A","DEU","S14","P31DC","CP12","XDC","V","2021","10","6","EUR"],
                ["A","DEU","S14","P31DC","CP13","XDC","V","2021","20","6","EUR"],
            ]
            with path.open("w", newline="", encoding="utf-8") as f:
                w=csv.writer(f); w.writerow(fields); w.writerows(rows)
            result = parse_oecd_csv(path, mapper(), source_id="OECD_TABLE5A_T501", source_url="https://example", retrieved_at="2026-01-01T00:00:00Z", priority=40, classification="COICOP2018")
            self.assertEqual(len(result.observations), 1)
            self.assertEqual(result.observations[0].value_lcu, Decimal("30000000"))

    def test_eurostat_jsonstat_cp12_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eurostat.json"
            obj = {
                "id": ["freq","unit","coicop18","geo","time"],
                "size": [1,1,3,1,1],
                "dimension": {
                    "freq":{"category":{"index":{"A":0}}},
                    "unit":{"category":{"index":{"CP_MNAC":0}}},
                    "coicop18":{"category":{"index":{"CP04":0,"CP12":1,"CP13":2}}},
                    "geo":{"category":{"index":{"DE":0}}},
                    "time":{"category":{"index":{"2021":0}}},
                },
                "value":{"0":100,"1":20,"2":30},
            }
            path.write_text(json.dumps(obj), encoding="utf-8")
            result = parse_eurostat_jsonstat(path, mapper(), source_id="EUROSTAT_NAMA_10_CP18", source_url="https://example", retrieved_at="2026-01-01T00:00:00Z", priority=30)
            self.assertEqual(len(result.observations), 2)
            cp12 = next(x for x in result.observations if x.armilar_category == "CP12")
            self.assertEqual(cp12.value_lcu, Decimal("50000000"))

    def test_undata_zip_maps_country_and_uses_2021_household_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "undata.zip"
            buffer = io.StringIO()
            fields = ["Country or Area","Sub Group","Item","SNA93 Item Code","Year","Series","Currency","SNA System","Fiscal Year Type","Value"]
            w=csv.DictWriter(buffer, fieldnames=fields); w.writeheader()
            w.writerow({"Country or Area":"Germany","Sub Group":"Individual consumption expenditure of households","Item":"Housing","SNA93 Item Code":"04","Year":"2021","Series":"1100","Currency":"Euro","SNA System":"2008","Fiscal Year Type":"Western calendar year","Value":"1,234"})
            with zipfile.ZipFile(path,"w") as z: z.writestr("SNA.csv", buffer.getvalue())
            result = parse_undata_zip(path, mapper(), source_id="UNDATA_SNA_TABLE32", source_url="https://example", retrieved_at="2026-01-01T00:00:00Z", priority=20)
            self.assertEqual(len(result.observations), 1)
            self.assertEqual(result.observations[0].value_lcu, Decimal("1234"))

    def test_source_selection_uses_one_complete_provider_per_economy(self):
        base = dict(economy_code="DEU", economy_name="Germany", currency="EUR", source_file="x", source_url="u", retrieved_at="t", source_hash="a"*64, concept="c", classification="COICOP1999", quality_flags=(), source_priority=1)
        rows = []
        for category in ("CP04", "CP06", "CP09", "CP10", "CP12"):
            rows.append(NominalObservation(armilar_category=category, value_lcu=Decimal("100"), source_id="OECD_TABLE5_T501", **base))
            rows.append(NominalObservation(armilar_category=category, value_lcu=Decimal("150") if category == "CP04" else Decimal("100"), source_id="UNDATA_SNA_TABLE32", **base))
        selected, audit = select_nominal_sources(rows, priority_order=("OECD_TABLE5_T501","UNDATA_SNA_TABLE32"), relative_tolerance=Decimal("0.02"))
        self.assertEqual({item.source_id for item in selected.values()}, {"OECD_TABLE5_T501"})
        self.assertEqual(len({category for economy, category in selected if economy == "DEU" and category in {"CP04","CP06","CP09","CP10","CP12"}}), 5)
        self.assertIn("ALTERNATIVE_DIVERGENT", {row["status"] for row in audit})

    def test_source_selection_refuses_category_level_provider_mixing(self):
        base = dict(economy_code="DEU", economy_name="Germany", currency="EUR", source_file="x", source_url="u", retrieved_at="t", source_hash="a"*64, concept="c", classification="COICOP1999", quality_flags=(), source_priority=1)
        rows = [
            NominalObservation(armilar_category="CP04", value_lcu=Decimal("100"), source_id="OECD_TABLE5_T501", **base),
            NominalObservation(armilar_category="CP06", value_lcu=Decimal("100"), source_id="UNDATA_SNA_TABLE32", **base),
            NominalObservation(armilar_category="CP09", value_lcu=Decimal("100"), source_id="UNDATA_SNA_TABLE32", **base),
            NominalObservation(armilar_category="CP10", value_lcu=Decimal("100"), source_id="UNDATA_SNA_TABLE32", **base),
            NominalObservation(armilar_category="CP12", value_lcu=Decimal("100"), source_id="UNDATA_SNA_TABLE32", **base),
        ]
        selected, audit = select_nominal_sources(rows, priority_order=("OECD_TABLE5_T501","UNDATA_SNA_TABLE32"), relative_tolerance=Decimal("0.02"))
        self.assertEqual(selected, {})
        self.assertIn("NO_COMPLETE_SOURCE_FOR_ECONOMY", {row["status"] for row in audit})

    def test_undata_plain_csv_is_accepted_as_well_as_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "undata.csv"
            fields = ["Country or Area","Sub Group","Item","SNA93 Item Code","Year","Series","Currency","SNA System","Fiscal Year Type","Value"]
            with path.open("w", newline="", encoding="utf-8") as f:
                w=csv.DictWriter(f, fieldnames=fields); w.writeheader()
                w.writerow({"Country or Area":"Germany","Sub Group":"Individual consumption expenditure of households","Item":"Health","SNA93 Item Code":"06","Year":"2021","Series":"1100","Currency":"Euro","SNA System":"2008","Fiscal Year Type":"Western calendar year","Value":"500"})
            result = parse_undata_zip(path, mapper(), source_id="UNDATA_SNA_TABLE32", source_url="https://example", retrieved_at="2026-01-01T00:00:00Z", priority=20)
            self.assertEqual(len(result.observations), 1)
            self.assertEqual(result.observations[0].armilar_category, "CP06")


if __name__ == "__main__":
    unittest.main()

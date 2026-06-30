from __future__ import annotations

import unittest

from armilar_prices.sdmx_adapter import SDMXAdapterError, SDMXQuerySpec, fetch_message


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def get(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append((args, kwargs))
        return {"ok": True}


class SDMXAdapterContractTests(unittest.TestCase):
    def test_query_is_delegated_to_open_source_client_contract(self) -> None:
        client = FakeClient()
        spec = SDMXQuerySpec(
            provider_code="OECD",
            resource_id="DSD_PRICES@DF_PRICES_ALL",
            key="PRT.M.N.CPI.IX._T.N.GY",
            start_period="2021-01",
            end_period="2021-12",
            params={"dimension_at_observation": "AllDimensions"},
        )
        result = fetch_message(spec, client=client)
        self.assertEqual(result, {"ok": True})
        args, kwargs = client.calls[0]
        self.assertEqual(args, ("data",))
        self.assertEqual(kwargs["resource_id"], "DSD_PRICES@DF_PRICES_ALL")
        self.assertEqual(kwargs["key"], spec.key)
        self.assertEqual(kwargs["params"]["startPeriod"], "2021-01")
        self.assertEqual(kwargs["params"]["endPeriod"], "2021-12")

    def test_invalid_query_fails_before_network(self) -> None:
        with self.assertRaisesRegex(SDMXAdapterError, "resource_id"):
            fetch_message(
                SDMXQuerySpec("OECD", "", "KEY", "2021-01"),
                client=FakeClient(),
            )

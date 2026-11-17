# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The delisting events.

The bytes are the golden every SDK shares, which the chain's own tests assert as
well; the JSON is what the node's Move mirrors render for the same values.
"""

from __future__ import annotations

import unittest
from typing import Any, Dict, List
from unittest import mock

import httpx

import intention_sdk

from intention_sdk.api.dex_account_client import (
    DexAccountClient,
    DexDelistingPlanView,
    DexDelistingRuntimeView,
    DexDelistingView,
)
from intention_sdk.api.intention_client import IntentionClient
from intention_sdk.core.account import Account
from intention_sdk.events.dex_event_decoder import (
    DecodedDexEvent,
    DexDelistingPlanSetEvent,
    DexDelistingPricedEvent,
    DexDelistingSettledEvent,
    DexDelistingSettledLeg,
    DexSymbolClosedEvent,
    decode_dex_event,
    decode_dex_event_data,
    decode_transaction_events,
    is_dex_event,
)
from intention_sdk.types.enums import (
    DelistingLegMarginMode,
    DelistingLegSide,
    DelistingPriceSource,
    SymbolStatus,
)


def _tag(name: str) -> str:
    return f"0x0000000000000000000000000000000000000001::dex::{name}"


def _bits(value: int) -> str:
    """The unsigned decimal reading of a value's 128-bit two's complement."""
    return str(value % 2**128)


_GOLDEN = {
    "DelistingPlanSetEvent": (
        "2a000000070000000100000000f1536500000000100e0000100e0000f0e2536500000000"
        "f4010000c8000000e8030000000000000058a7cf0c0a0600"
    ),
    "DelistingPricedEvent": (
        "2a000000070000000100000090b25b070000000000a493d6000000000030edecffffffff"
        "ffffffffffffffffffd007000000000000805a2418240a0600"
    ),
    "DelistingSettledEvent": (
        "2a0000000700000000000000000000000000000000000000000000000000000000000000"
        "000000010000000000000000000000000000000000000000000000000000000000000002"
        "0000000090b25b070000000001000140420f0000000000a0f99449000000000000000000"
        "000000800f05fdffffffffffffffffffffffff0000000000000000000000000000000000"
        "000000000000000000000000000000d10700000000000000752a18240a0600"
    ),
    "SymbolClosedEvent": (
        "2a000000070000000100000090b25b0700000000020000000000000080841e0000000000"
        "000000000000000040f32993000000000000000000000000030000000000000030edecff"
        "ffffffffffffffffffffffff00000000000000000000000000000000d207000000000000"
        "808f3018240a0600"
    ),
}

_OWNER = "0x0000000000000000000000000000000000000001"
_SUB_ADDRESS = "0x0000000000000000000000000000000000000002"

_EXPECTED: Dict[str, Any] = {
    "DelistingPlanSetEvent": DexDelistingPlanSetEvent(
        perpetual_id=42,
        symbol_id=7,
        plan_version=1,
        t0_secs=1_700_000_000,
        reduce_only_lead_secs=3_600,
        twap_window_secs=3_600,
        reduce_only_at_secs=1_699_996_400,
        max_cancel_per_block=500,
        max_settle_per_block=200,
        block_height=1_000,
        timestamp_us=1_699_900_000_000_000,
    ),
    "DelistingPricedEvent": DexDelistingPricedEvent(
        perpetual_id=42,
        symbol_id=7,
        plan_version=1,
        final_price_subticks=123_450_000,
        sample_weight_us=3_600_000_000,
        price_source=DelistingPriceSource.WINDOW_TWAP,
        expected_total_pnl=-1_250_000,
        block_height=2_000,
        timestamp_us=1_700_000_000_400_000,
    ),
    "DelistingSettledEvent": DexDelistingSettledEvent(
        perpetual_id=42,
        symbol_id=7,
        owner=_OWNER,
        sub_address=_SUB_ADDRESS,
        subaccount_number=0,
        final_price_subticks=123_450_000,
        legs=(
            DexDelistingSettledLeg(
                side=DelistingLegSide.LONG,
                margin_mode=DelistingLegMarginMode.ISOLATED,
                quantums=1_000_000,
                quote_quantums=1_234_500_000,
                realized_pnl=-50_000_000,
                isolated_shortfall=0,
            ),
        ),
        cross_shortfall=0,
        block_height=2_001,
        timestamp_us=1_700_000_000_800_000,
    ),
    "SymbolClosedEvent": DexSymbolClosedEvent(
        perpetual_id=42,
        symbol_id=7,
        plan_version=1,
        final_price_subticks=123_450_000,
        settled_accounts=2,
        settled_quantums=2_000_000,
        settled_quote_quantums=2_469_000_000,
        canceled_orders=3,
        realized_pnl_sum=-1_250_000,
        shortfall_quote=0,
        block_height=2_002,
        timestamp_us=1_700_000_001_200_000,
    ),
}

_JSON_FORM: Dict[str, Dict[str, Any]] = {
    "DelistingPlanSetEvent": {
        "perpetual_id": 42,
        "symbol_id": 7,
        "plan_version": 1,
        "t0_secs": "1700000000",
        "reduce_only_lead_secs": 3600,
        "twap_window_secs": 3600,
        "reduce_only_at_secs": "1699996400",
        "max_cancel_per_block": 500,
        "max_settle_per_block": 200,
        "block_height": "1000",
        "timestamp_us": "1699900000000000",
    },
    "DelistingPricedEvent": {
        "perpetual_id": 42,
        "symbol_id": 7,
        "plan_version": 1,
        "final_price_subticks": "123450000",
        "sample_weight_us": "3600000000",
        "price_source": 0,
        "expected_total_pnl_bits": _bits(-1_250_000),
        "block_height": "2000",
        "timestamp_us": "1700000000400000",
    },
    "DelistingSettledEvent": {
        "perpetual_id": 42,
        "symbol_id": 7,
        "owner": _OWNER,
        "sub_address": _SUB_ADDRESS,
        "subaccount_number": 0,
        "final_price_subticks": "123450000",
        "legs": [
            {
                "side": 0,
                "margin_mode": 1,
                "quantums": "1000000",
                "quote_quantums": "1234500000",
                "realized_pnl_bits": _bits(-50_000_000),
                "isolated_shortfall": "0",
            }
        ],
        "cross_shortfall": "0",
        "block_height": "2001",
        "timestamp_us": "1700000000800000",
    },
    "SymbolClosedEvent": {
        "perpetual_id": 42,
        "symbol_id": 7,
        "plan_version": 1,
        "final_price_subticks": "123450000",
        "settled_accounts": "2",
        "settled_quantums": "2000000",
        "settled_quote_quantums": "2469000000",
        "canceled_orders": "3",
        "realized_pnl_sum_bits": _bits(-1_250_000),
        "shortfall_quote": "0",
        "block_height": "2002",
        "timestamp_us": "1700000001200000",
    },
}


class TestDelistingEvents(unittest.TestCase):
    def test_golden_bytes_decode_into_the_contract_values(self) -> None:
        lengths = {name: len(hex_text) // 2 for name, hex_text in _GOLDEN.items()}
        self.assertEqual(
            lengths,
            {
                "DelistingPlanSetEvent": 60,
                "DelistingPricedEvent": 61,
                "DelistingSettledEvent": 175,
                "SymbolClosedEvent": 116,
            },
        )
        for name, hex_text in _GOLDEN.items():
            with self.subTest(name):
                self.assertTrue(is_dex_event(_tag(name)))
                self.assertEqual(
                    decode_dex_event(_tag(name), hex_text),
                    DecodedDexEvent(name, _EXPECTED[name]),
                )

    def test_json_from_a_move_mirror_decodes_into_the_same_values(self) -> None:
        for name, obj in _JSON_FORM.items():
            with self.subTest(name):
                self.assertEqual(
                    decode_dex_event_data(_tag(name), obj),
                    DecodedDexEvent(name, _EXPECTED[name]),
                )

    def test_appended_fields_are_ignored_and_a_short_payload_is_refused(self) -> None:
        for name, hex_text in _GOLDEN.items():
            with self.subTest(name):
                self.assertEqual(
                    decode_dex_event(_tag(name), f"0x{hex_text}0102030405060708"),
                    DecodedDexEvent(name, _EXPECTED[name]),
                )
                self.assertIsNone(decode_dex_event(_tag(name), hex_text[:-2]))

    def test_a_settled_account_carries_every_leg_in_order(self) -> None:
        def leg(side: str, pnl: str) -> str:
            return (
                f"{side}00"
                "40420f0000000000"
                "a0f99449000000000000000000000000"
                f"{pnl}"
                "00000000000000000000000000000000"
            )

        # Two Cross legs, short after long, then a Cross shortfall of 1000.
        header = _GOLDEN["DelistingSettledEvent"][: 2 * (4 + 4 + 32 + 32 + 4 + 8)]
        two_legs = (
            header
            + "02"
            + leg("00", "80f0fa02000000000000000000000000")
            + leg("01", "800f05fdffffffffffffffffffffffff")
            + "e8030000000000000000000000000000"
            + "d10700000000000000752a18240a0600"
        )
        decoded = decode_dex_event(_tag("DelistingSettledEvent"), two_legs)
        assert decoded is not None
        event = decoded.event
        assert isinstance(event, DexDelistingSettledEvent)
        self.assertEqual(
            [(item.side, item.margin_mode, item.realized_pnl) for item in event.legs],
            [
                (DelistingLegSide.LONG, DelistingLegMarginMode.CROSS, 50_000_000),
                (DelistingLegSide.SHORT, DelistingLegMarginMode.CROSS, -50_000_000),
            ],
        )
        self.assertEqual(event.cross_shortfall, 1_000)

    def test_a_price_source_this_sdk_does_not_know_is_kept_as_read(self) -> None:
        priced = _GOLDEN["DelistingPricedEvent"]
        at = 2 * (4 + 4 + 4 + 8 + 8)
        unknown_source = f"{priced[:at]}07{priced[at + 2:]}"
        decoded = decode_dex_event(_tag("DelistingPricedEvent"), unknown_source)
        assert decoded is not None
        event = decoded.event
        assert isinstance(event, DexDelistingPricedEvent)
        self.assertEqual(event.price_source, 7)

    def test_a_transactions_delisting_events_are_picked_out_with_the_rest(
        self,
    ) -> None:
        decoded = decode_transaction_events(
            [
                {"type": "0x1::coin::CoinDeposit", "data": "00"},
                {
                    "type": _tag("DelistingPricedEvent"),
                    "data": _GOLDEN["DelistingPricedEvent"],
                },
                {
                    "type": _tag("DelistingSettledEvent"),
                    "data": _JSON_FORM["DelistingSettledEvent"],
                },
                {
                    "type": _tag("SymbolClosedEvent"),
                    "data": _GOLDEN["SymbolClosedEvent"],
                },
            ]
        )
        self.assertEqual(
            [(item.index, item.event_type) for item in decoded],
            [
                (1, "DelistingPricedEvent"),
                (2, "DelistingSettledEvent"),
                (3, "SymbolClosedEvent"),
            ],
        )
        self.assertEqual(decoded[1].event, _EXPECTED["DelistingSettledEvent"])

    def test_the_delisting_types_are_root_exports(self) -> None:
        for name in (
            "DexDelistingPlanSetEvent",
            "DexDelistingPricedEvent",
            "DexDelistingSettledEvent",
            "DexDelistingSettledLeg",
            "DexSymbolClosedEvent",
            "DelistingPriceSource",
            "DelistingLegSide",
            "DelistingLegMarginMode",
        ):
            with self.subTest(name):
                self.assertIn(name, intention_sdk.__all__)
                self.assertTrue(hasattr(intention_sdk, name))


class TestSymbolStatus(unittest.TestCase):
    def test_symbol_status_knows_the_chains_names_the_old_one_kept(self) -> None:
        self.assertEqual(SymbolStatus.REDUCE_ONLY, 2)
        self.assertIs(SymbolStatus.CANCEL_ONLY, SymbolStatus.REDUCE_ONLY)
        self.assertEqual(SymbolStatus(2).name, "REDUCE_ONLY")
        self.assertEqual(SymbolStatus.FINAL_SETTLEMENT, 5)
        self.assertEqual(SymbolStatus.PRE_OPEN, 6)
        self.assertEqual(SymbolStatus.CLOSED, 7)
        self.assertEqual(SymbolStatus(7).name, "CLOSED")
        self.assertEqual([status.value for status in SymbolStatus], list(range(8)))


def _delisting_json(perpetual_id: int, **over: Any) -> Dict[str, Any]:
    """One market's delisting as the node renders it."""
    view: Dict[str, Any] = {
        "perpetual_id": perpetual_id,
        "symbol_id": 7,
        "ticker": "AAPL-USDC",
        "symbol_status": 5,
        "phase": "SETTLING",
        "prd_state": "SETTLING",
        "plan": {
            "plan_version": 2,
            "t0_secs": 1700000000,
            "reduce_only_lead_secs": 3600,
            "twap_window_secs": 3600,
            "max_cancel_per_block": 500,
            "max_settle_per_block": 200,
            "reduce_only_at_secs": 1699996400,
            "window_start_secs": 1699996400,
        },
        "indicative_price_subticks": 123450000,
        "final_price_subticks": 123450000,
        "runtime": {
            "plan_version": 2,
            "sample_weight_us": 3600000000,
            "canceled_orders": 3,
            "settled_accounts": 1,
            "settled_quantums": "1000000",
            "settled_quote_quantums": "1234500000",
            "expected_total_pnl": "-1250000",
            "realized_pnl_sum": "-50000000",
            "shortfall_quote": "0",
        },
    }
    view.update(over)
    return view


_SETTLING_VIEW = DexDelistingView(
    perpetual_id=40,
    symbol_id=7,
    ticker="AAPL-USDC",
    symbol_status=5,
    phase="SETTLING",
    prd_state="SETTLING",
    plan=DexDelistingPlanView(
        plan_version=2,
        t0_secs=1_700_000_000,
        reduce_only_lead_secs=3_600,
        twap_window_secs=3_600,
        max_cancel_per_block=500,
        max_settle_per_block=200,
        reduce_only_at_secs=1_699_996_400,
        window_start_secs=1_699_996_400,
    ),
    indicative_price_subticks=123_450_000,
    final_price_subticks=123_450_000,
    runtime=DexDelistingRuntimeView(
        plan_version=2,
        sample_weight_us=3_600_000_000,
        canceled_orders=3,
        settled_accounts=1,
        settled_quantums=1_000_000,
        settled_quote_quantums=1_234_500_000,
        expected_total_pnl=-1_250_000,
        realized_pnl_sum=-50_000_000,
        shortfall_quote=0,
    ),
)

_REAL_ASYNC_CLIENT = httpx.AsyncClient


class _Node:
    """A node that answers every GET with one status and body, and keeps the URLs."""

    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self.body = body
        self.urls: List[str] = []

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.urls.append(str(request.url))
        if isinstance(self.body, str):
            return httpx.Response(self.status, text=self.body)
        return httpx.Response(self.status, json=self.body)

    def serving(self) -> Any:
        """Route the httpx clients the SDK opens to this node while in effect."""

        def client(**kwargs: Any) -> httpx.AsyncClient:
            # The SDK passes its own `transport`, None unless a caller set one.
            kwargs["transport"] = httpx.MockTransport(self._answer)
            return _REAL_ASYNC_CLIENT(**kwargs)

        return mock.patch.object(httpx, "AsyncClient", client)


class TestDelistingReads(unittest.IsolatedAsyncioTestCase):
    async def test_get_delistings_reads_every_plan_signed_totals_and_all(self) -> None:
        scheduled = _delisting_json(
            41,
            phase="SCHEDULED",
            prd_state="PRE_SETTLEMENT",
            symbol_status=0,
            indicative_price_subticks=None,
            final_price_subticks=None,
            runtime=None,
        )
        node = _Node(200, {"delistings": [_delisting_json(40), scheduled]})
        client = DexAccountClient("https://node.example/v1/")
        with node.serving():
            delistings = await client.get_delistings()

        self.assertEqual(node.urls, ["https://node.example/v1/dex/delistings"])
        self.assertEqual(delistings[0], _SETTLING_VIEW)
        self.assertEqual(
            (delistings[1].phase, delistings[1].prd_state, delistings[1].symbol_status),
            ("SCHEDULED", "PRE_SETTLEMENT", 0),
        )
        self.assertIsNone(delistings[1].indicative_price_subticks)
        self.assertIsNone(delistings[1].final_price_subticks)
        self.assertIsNone(delistings[1].runtime)

    async def test_no_plan_is_none_and_a_node_without_the_route_has_none(self) -> None:
        client = DexAccountClient("https://node.example/v1")
        missing = _Node(404, {"message": "Delisting plan not found"})
        with missing.serving():
            self.assertIsNone(await client.get_delisting(42))
            self.assertEqual(await client.get_delistings(), [])
        self.assertEqual(
            missing.urls,
            [
                "https://node.example/v1/dex/delistings/42",
                "https://node.example/v1/dex/delistings",
            ],
        )

        found = _Node(200, _delisting_json(40))
        with found.serving():
            self.assertEqual(await client.get_delisting(40), _SETTLING_VIEW)

    async def test_a_failing_node_is_an_error_not_an_absent_plan(self) -> None:
        client = DexAccountClient("https://node.example/v1")
        broken = _Node(502, "boom")
        with broken.serving():
            with self.assertRaises(httpx.HTTPStatusError):
                await client.get_delisting(42)
            with self.assertRaises(httpx.HTTPStatusError):
                await client.get_delistings()
            bad_ids: List[Any] = [-1, 2**32, 1.5, True, "42"]
            for bad_id in bad_ids:
                with self.subTest(bad_id=bad_id):
                    with self.assertRaisesRegex(ValueError, "must be a u32"):
                        await client.get_delisting(bad_id)
        self.assertEqual(len(broken.urls), 2)

    async def test_a_malformed_view_is_refused(self) -> None:
        client = DexAccountClient("https://node.example/v1")
        runtime = dict(_delisting_json(40)["runtime"], expected_total_pnl="-1.5")
        for body, problem in (
            (_delisting_json(40, runtime=runtime), "runtime.expected_total_pnl"),
            (_delisting_json(40, plan=None), "plan must be an object"),
            (_delisting_json(40, ticker=7), "ticker must be a string"),
            (_delisting_json(40, final_price_subticks=True), "final_price_subticks"),
        ):
            with self.subTest(problem=problem):
                with _Node(200, body).serving():
                    with self.assertRaisesRegex(ValueError, problem):
                        await client.get_delisting(40)

    async def test_the_unified_client_reads_delistings_from_its_node(self) -> None:
        sdk = IntentionClient(
            signer=Account.generate(),
            node_url="https://node.example/v1",
        )
        listed = _Node(200, {"delistings": [_delisting_json(40)]})
        with listed.serving():
            self.assertEqual(await sdk.get_delistings(), [_SETTLING_VIEW])
        missing = _Node(404, {})
        with missing.serving():
            self.assertIsNone(await sdk.get_delisting(40))
        self.assertEqual(
            listed.urls + missing.urls,
            [
                "https://node.example/v1/dex/delistings",
                "https://node.example/v1/dex/delistings/40",
            ],
        )
        await sdk.close()

    def test_the_view_types_are_root_exports(self) -> None:
        for name in (
            "DexDelistingPlanView",
            "DexDelistingRuntimeView",
            "DexDelistingView",
        ):
            with self.subTest(name):
                self.assertIn(name, intention_sdk.__all__)
                self.assertTrue(hasattr(intention_sdk, name))


if __name__ == "__main__":
    unittest.main()

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest
from types import SimpleNamespace

from intention_sdk.core.account import Account
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.events.dex_event_decoder import DecodedTransactionEvent
from intention_sdk.api.dex_executor import DexExecutionResult, PendingTransactionResult
from intention_sdk.types.enums import OrderPositionMode
from intention_sdk.transactions.market_resolver import MarketMetadata, SimpleMarketResolver
from intention_sdk.api.order_client import (
    OrderClient,
    OrderRejectedError,
    order_outcomes_from_events,
)
from intention_sdk.transactions.order_intents import OrderInput, OrderPreflightError, OrderType, TpSlLeg
from intention_sdk.transactions.order_preflight import MarketSnapshot


class FakeExecutor:
    def __init__(self, events=None):
        self.events = list(events or [])
        self.executed = []
        self.submitted = []

    async def execute_orders(self, orders, **options):
        self.executed.append((orders, options))
        return DexExecutionResult("0xabc", {"success": True, "events": []}, self.events)

    async def submit_orders(self, orders, **options):
        self.submitted.append((orders, options))
        return PendingTransactionResult("0xpending")


class FakePreflight:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    async def get_market_snapshot(self, **request):
        self.calls.append(request)
        return self.snapshot


def resolver():
    return SimpleMarketResolver(
        [
            MarketMetadata(
                symbol="BTC-USDC",
                symbol_id=7,
                atomic_resolution=-10,
                quantum_conversion_exponent=-9,
                step_base_quantums=100,
                subticks_per_tick=25,
            )
        ]
    )


def client(executor, preflight_provider=None):
    signer = Account.generate()
    return OrderClient(
        executor=executor,
        signer=signer,
        sub_address=AccountAddress.from_str("0x0"),
        position_mode=OrderPositionMode.NET,
        resolver=resolver(),
        preflight_provider=preflight_provider,
    )


class TestOrderClient(unittest.IsolatedAsyncioTestCase):
    def test_order_outcomes_normalize_structured_json_events(self):
        outcomes = order_outcomes_from_events(
            [
                DecodedTransactionEvent(
                    0,
                    "OrderPlacedEvent",
                    {
                        "order_id": "42",
                        "symbol_id": "7",
                        "client_order_id": {"vec": ["client-42"]},
                    },
                ),
                DecodedTransactionEvent(
                    1,
                    "OrderRejectedEvent",
                    {
                        "order_id": "43",
                        "symbol_id": "7",
                        "reject_reason": "22",
                        "client_order_id": {"vec": []},
                    },
                ),
            ]
        )

        self.assertEqual(outcomes[0].order_id, 42)
        self.assertEqual(outcomes[0].symbol_id, 7)
        self.assertEqual(outcomes[0].client_order_id, "client-42")
        self.assertEqual(outcomes[1].status, "rejected")
        self.assertEqual(outcomes[1].order_id, 43)
        self.assertEqual(outcomes[1].reject_reason_code, 22)
        self.assertIsNone(outcomes[1].client_order_id)

    def test_order_outcomes_collapse_structured_json_to_terminal_status(self):
        outcomes = order_outcomes_from_events(
            [
                DecodedTransactionEvent(
                    0,
                    "OrderPlacedEvent",
                    {
                        "order_id": "42",
                        "symbol_id": "7",
                        "client_order_id": {"vec": ["client-42"]},
                    },
                ),
                DecodedTransactionEvent(
                    1,
                    "OrderRejectedEvent",
                    {
                        "order_id": "42",
                        "symbol_id": "7",
                        "reject_reason": "22",
                        "client_order_id": {"vec": []},
                    },
                ),
            ]
        )

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].status, "rejected")
        self.assertEqual(outcomes[0].order_id, 42)
        self.assertEqual(outcomes[0].reject_reason_code, 22)

    async def test_place_order_waits_and_returns_decoded_outcome(self):
        placed = SimpleNamespace(
            order_id=42,
            client_order_id="0x0123456789abcdef0123456789abcdef",
            symbol_id=7,
        )
        executor = FakeExecutor(
            [DecodedTransactionEvent(0, "OrderPlacedEvent", placed)]
        )
        result = await client(executor).place_order(
            OrderInput(
                symbol="BTC-USDC",
                side="BUY",
                type=OrderType.LIMIT,
                size=0.1,
                price="60000",
            ),
            preflight="local",
        )
        self.assertEqual(result.hash, "0xabc")
        self.assertTrue(result.all_accepted)
        self.assertEqual(result.orders[0].order_id, 42)
        self.assertEqual(len(executor.executed), 1)

    async def test_submit_order_is_no_wait_fast_path(self):
        executor = FakeExecutor()
        result = await client(executor).submit_order(
            OrderInput(
                symbol="BTC-USDC",
                side="BUY",
                type=OrderType.LIMIT,
                size="0.1",
                price="60000",
            )
        )
        self.assertEqual(result.hash, "0xpending")
        self.assertEqual(len(executor.executed), 0)
        self.assertEqual(len(executor.submitted), 1)

    async def test_business_rejection_can_raise_typed_error(self):
        rejected = SimpleNamespace(
            order_id=0,
            client_order_id=None,
            symbol_id=7,
            reject_reason=11,
        )
        executor = FakeExecutor(
            [DecodedTransactionEvent(0, "OrderRejectedEvent", rejected)]
        )
        with self.assertRaises(OrderRejectedError):
            await client(executor).place_order(
                OrderInput(
                    symbol="BTC-USDC",
                    side="BUY",
                    type=OrderType.LIMIT,
                    size="0.1",
                    price="60000",
                ),
                preflight="local",
                throw_on_order_reject=True,
            )

    async def test_structured_json_rejection_raises_order_rejected_error(self):
        executor = FakeExecutor(
            [
                DecodedTransactionEvent(
                    0,
                    "OrderRejectedEvent",
                    {
                        "order_id": "43",
                        "symbol_id": "7",
                        "reject_reason": "22",
                        "client_order_id": {"vec": []},
                    },
                )
            ]
        )

        with self.assertRaises(OrderRejectedError) as raised:
            await client(executor).place_order(
                OrderInput(
                    symbol="BTC-USDC",
                    side="BUY",
                    type=OrderType.LIMIT,
                    size="0.1",
                    price="60000",
                ),
                preflight="local",
                throw_on_order_reject=True,
            )

        self.assertEqual(raised.exception.result.orders[0].order_id, 43)
        self.assertEqual(raised.exception.result.orders[0].reject_reason_code, 22)

    async def test_structured_json_placed_returns_order_action_result(self):
        executor = FakeExecutor(
            [
                DecodedTransactionEvent(
                    0,
                    "OrderPlacedEvent",
                    {
                        "order_id": "42",
                        "symbol_id": "7",
                        "client_order_id": {"vec": ["client-42"]},
                    },
                )
            ]
        )

        result = await client(executor).place_order(
            OrderInput(
                symbol="BTC-USDC",
                side="BUY",
                type=OrderType.LIMIT,
                size="0.1",
                price="60000",
            ),
            preflight="local",
        )

        self.assertTrue(result.all_accepted)
        self.assertEqual(result.orders[0].order_id, 42)
        self.assertEqual(result.orders[0].symbol_id, 7)
        self.assertEqual(result.orders[0].client_order_id, "client-42")

    async def test_attached_market_tpsl_full_preflight_rejects_against_mid(self):
        preflight = FakePreflight(
            MarketSnapshot(
                symbol="BTC-USDC",
                mark_price="50000",
                last_price="48000",
                mid_price="60000",
                fetched_at_ms=1,
            )
        )
        with self.assertRaises(OrderPreflightError) as raised:
            await client(FakeExecutor(), preflight).place_order_with_tpsl(
                OrderInput(
                    symbol="BTC-USDC",
                    side="BUY",
                    type=OrderType.MARKET,
                    size="0.1",
                ),
                tp=TpSlLeg(
                    type=OrderType.TAKE_PROFIT_MARKET,
                    trigger_price="59000",
                ),
                preflight="full",
            )
        self.assertEqual(
            raised.exception.issues[0].code,
            "TAKE_PROFIT_PRICE_WRONG_SIDE",
        )

    async def test_attached_limit_tpsl_uses_entry_price_for_mark_and_last(self):
        preflight = FakePreflight(
            MarketSnapshot(
                symbol="BTC-USDC",
                mark_price="50000",
                last_price="48000",
                mid_price="52000",
                fetched_at_ms=1,
            )
        )
        order_client = client(FakeExecutor(), preflight)

        for side in ("BUY", "SELL"):
            for trigger_price_type in ("MARK_PRICE", "LAST_PRICE"):
                await order_client.preflight_order_with_tpsl(
                    OrderInput(
                        symbol="BTC-USDC",
                        side=side,
                        type=OrderType.LIMIT,
                        size="0.1",
                        price="52000",
                    ),
                    tp=TpSlLeg(
                        type=OrderType.TAKE_PROFIT_MARKET,
                        trigger_price="52000",
                        trigger_price_type=trigger_price_type,
                    ),
                    sl=TpSlLeg(
                        type=OrderType.STOP_MARKET,
                        trigger_price="52000",
                        trigger_price_type=trigger_price_type,
                    ),
                    preflight="full",
                )

        self.assertEqual(preflight.calls, [])

    async def test_attached_limit_tpsl_full_preflight_needs_no_provider(self):
        await client(FakeExecutor()).preflight_order_with_tpsl(
            OrderInput(
                symbol="BTC-USDC",
                side="BUY",
                type=OrderType.LIMIT,
                size="0.1",
                price="52000",
            ),
            tp=TpSlLeg(
                type=OrderType.TAKE_PROFIT_MARKET,
                trigger_price="52000",
            ),
            sl=TpSlLeg(
                type=OrderType.STOP_MARKET,
                trigger_price="52000",
            ),
            preflight="full",
        )

    async def test_attached_market_tpsl_uses_mid_for_mark_and_last(self):
        preflight = FakePreflight(
            MarketSnapshot(
                symbol="BTC-USDC",
                mark_price="50000",
                last_price="48000",
                mid_price="52000",
                fetched_at_ms=1,
            )
        )
        order_client = client(FakeExecutor(), preflight)

        for side in ("BUY", "SELL"):
            for trigger_price_type in ("MARK_PRICE", "LAST_PRICE"):
                await order_client.preflight_order_with_tpsl(
                    OrderInput(
                        symbol="BTC-USDC",
                        side=side,
                        type=OrderType.MARKET,
                        size="0.1",
                    ),
                    tp=TpSlLeg(
                        type=OrderType.TAKE_PROFIT_MARKET,
                        trigger_price="52000",
                        trigger_price_type=trigger_price_type,
                    ),
                    sl=TpSlLeg(
                        type=OrderType.STOP_MARKET,
                        trigger_price="52000",
                        trigger_price_type=trigger_price_type,
                    ),
                    preflight="full",
                )

        self.assertEqual(len(preflight.calls), 4)

    async def test_attached_market_tpsl_requires_mid(self):
        preflight = FakePreflight(
            MarketSnapshot(
                symbol="BTC-USDC",
                mark_price="50000",
                last_price="48000",
                fetched_at_ms=1,
            )
        )

        with self.assertRaises(OrderPreflightError) as raised:
            await client(FakeExecutor(), preflight).preflight_order_with_tpsl(
                OrderInput(
                    symbol="BTC-USDC",
                    side="BUY",
                    type=OrderType.MARKET,
                    size="0.1",
                ),
                tp=TpSlLeg(
                    type=OrderType.TAKE_PROFIT_MARKET,
                    trigger_price="52000",
                ),
                sl=None,
                preflight="full",
            )

        self.assertEqual(raised.exception.issues[0].code, "REFERENCE_PRICE_UNAVAILABLE")
        self.assertEqual(raised.exception.issues[0].field, "tp.trigger_price")

    async def test_position_tpsl_still_uses_child_trigger_price_type(self):
        preflight = FakePreflight(
            MarketSnapshot(
                symbol="BTC-USDC",
                mark_price="60000",
                last_price="50000",
                mid_price="70000",
                fetched_at_ms=1,
            )
        )

        await client(FakeExecutor(), preflight).preflight_position_tpsl(
            symbol="BTC-USDC",
            position_side="LONG",
            size_mode="close_position",
            config_amount=None,
            tp=TpSlLeg(
                type=OrderType.TAKE_PROFIT_MARKET,
                trigger_price="55000",
                trigger_price_type="LAST_PRICE",
            ),
            sl=None,
            preflight="full",
        )


if __name__ == "__main__":
    unittest.main()

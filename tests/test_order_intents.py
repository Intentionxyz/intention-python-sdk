# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.transactions.dex_payloads import (
    DexConditionReplaceOrder,
    DexReplaceTargetKind,
)
from intention_sdk.types.enums import (
    ConditionType,
    DexOrdersVariant,
    Grouping,
    OrderBasicType,
    OrderPositionMode,
    Side,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)
from intention_sdk.transactions.order_intents import (
    BracketOrderGroup,
    ModifyChanges,
    ModifyConditionChanges,
    OrderInput,
    OrderIntents,
    OrderIntentsContext,
    OrderRef,
    OrderType,
    TpSlLeg,
    encode_leg_selection,
    resolve_time_in_force,
)

CID = "0x0123456789abcdef0123456789abcdef"
NEW_CID = "0xfedcba9876543210fedcba9876543210"


class SimpleResolver:
    def symbol_id(self, symbol: str) -> int:
        if symbol != "BTC-USDC":
            raise ValueError(f"unknown symbol: {symbol}")
        return 7

    def to_quantums(self, symbol: str, size) -> int:
        self.symbol_id(symbol)
        return int(float(size) * 10_000_000_000)

    def to_subticks(self, symbol: str, price) -> int:
        self.symbol_id(symbol)
        return int(float(price) * 100_000)


def builder(position_mode: OrderPositionMode = OrderPositionMode.NET) -> OrderIntents:
    return OrderIntents(
        OrderIntentsContext(
            sub_address=AccountAddress(b"\x00" * 32),
            position_mode=position_mode,
            resolver=SimpleResolver(),
        )
    )


class TestOrderIntents(unittest.TestCase):
    def test_resolve_time_in_force_accepts_only_supported_enum_values(self):
        self.assertEqual(
            resolve_time_in_force(OrderType.LIMIT, TimeInForce.IOC),
            TimeInForce.IOC,
        )
        self.assertEqual(
            resolve_time_in_force(OrderType.MARKET, TimeInForce.GTC),
            TimeInForce.GTC,
        )
        self.assertEqual(
            resolve_time_in_force(OrderType.LIMIT, TimeInForce.ALO),
            TimeInForce.ALO,
        )
        with self.assertRaisesRegex(
            ValueError, "post_only cannot be combined with IOC"
        ):
            resolve_time_in_force(OrderType.LIMIT, TimeInForce.IOC, True)
        with self.assertRaisesRegex(
            ValueError, "post_only/ALO is only supported for limit orders"
        ):
            resolve_time_in_force(OrderType.MARKET, TimeInForce.ALO)
        with self.assertRaisesRegex(
            TypeError, "time_in_force must use the TimeInForce enum"
        ):
            resolve_time_in_force(OrderType.LIMIT, "GTC")  # type: ignore[arg-type]
        with self.assertRaisesRegex(
            ValueError, "high-level order API supports only GTC, IOC, and ALO"
        ):
            resolve_time_in_force(OrderType.LIMIT, TimeInForce.FOK)

    def test_encode_leg_selection_hedge_zero_close_uses_side(self):
        side, quantums = encode_leg_selection(
            position_mode=OrderPositionMode.HEDGE,
            intent_side="BUY",
            reduce_only=True,
            position_side="SHORT",
            abs_quantums=0,
        )
        self.assertEqual(side, Side.BUY)
        self.assertEqual(quantums, 0)

    def test_place_order_with_tpsl_hides_parent_child_details(self):
        orders = builder().place_order_with_tpsl(
            OrderInput(
                symbol="BTC-USDC",
                side="BUY",
                type=OrderType.LIMIT,
                size="0.2",
                price="60000",
                client_order_id=CID,
            ),
            tp=TpSlLeg(
                type=OrderType.TAKE_PROFIT_MARKET,
                trigger_price="65000",
            ),
            sl=TpSlLeg(
                type=OrderType.STOP_MARKET,
                trigger_price="57500",
                trigger_price_type="LAST_PRICE",
            ),
        )

        self.assertEqual(orders.variant, DexOrdersVariant.PLACE)
        group = orders.orders[0]
        self.assertEqual(group.grouping, Grouping.NORMAL_TPSL)
        self.assertEqual(len(group.orders), 3)
        entry, tp, sl = group.orders
        self.assertEqual(entry.condition_type, ConditionType.UNSPECIFIED)
        self.assertEqual(tp.order_basic_type, OrderBasicType.MARKET)
        self.assertEqual(sl.order_basic_type, OrderBasicType.MARKET)
        self.assertTrue(tp.reduce_only)
        self.assertEqual(sl.trigger_price_type, TriggerPriceType.LAST_PRICE)

    def test_position_tpsl_close_position_short_uses_buy_zero_leg(self):
        orders = builder(OrderPositionMode.HEDGE).place_position_tpsl(
            symbol="BTC-USDC",
            position_side="SHORT",
            size_mode="close_position",
            tp=TpSlLeg(
                type=OrderType.TAKE_PROFIT_MARKET,
                trigger_price="55000",
            ),
        )

        leg = orders.orders[0].orders[0]
        self.assertEqual(orders.orders[0].grouping, Grouping.POSITION_TPSL)
        self.assertEqual(leg.side, Side.BUY)
        self.assertEqual(leg.quantums, 0)
        self.assertEqual(leg.time_in_force, TimeInForce.IOC)

    def test_modify_condition_order_emits_dedicated_wire(self):
        orders = builder().modify_condition_order(
            OrderRef(order_id=42),
            ModifyConditionChanges(
                symbol="BTC-USDC",
                type=OrderType.STOP_MARKET,
                size_mode="fixed",
                current_size_mode="fixed",
                size="0.2",
                trigger_price="57500",
                trigger_price_type="LAST_PRICE",
                new_client_order_id=NEW_CID,
            ),
        )

        self.assertEqual(orders.variant, DexOrdersVariant.REPLACE_CONDITION)
        replace = orders.orders[0]
        self.assertIsInstance(replace, DexConditionReplaceOrder)
        self.assertEqual(
            replace.target.kind,
            DexReplaceTargetKind.ORDER_ID_WITH_CONTEXT,
        )
        self.assertEqual(replace.target.order_id, 42)
        self.assertEqual(replace.target.symbol_id, 7)
        self.assertEqual(replace.target.symbol_type, SymbolType.PERPETUAL)
        self.assertEqual(replace.quantums, 2_000_000_000)
        self.assertEqual(replace.subticks, 0)
        self.assertEqual(replace.trigger_subticks, 5_750_000_000)
        self.assertEqual(replace.order_basic_type, OrderBasicType.MARKET)
        self.assertEqual(replace.condition_type, ConditionType.STOP_LOSS)
        self.assertEqual(replace.trigger_price_type, TriggerPriceType.LAST_PRICE)
        self.assertEqual(replace.new_client_order_id, NEW_CID)

    def test_modify_condition_order_supports_whole_position_limit(self):
        orders = builder(OrderPositionMode.HEDGE).modify_condition_order(
            OrderRef(client_order_id=CID),
            ModifyConditionChanges(
                symbol="BTC-USDC",
                type=OrderType.TAKE_PROFIT_LIMIT,
                size_mode="close_position",
                current_size_mode="close_position",
                price="66000",
                trigger_price="65000",
            ),
        )

        replace = orders.orders[0]
        self.assertEqual(replace.target.client_order_id, CID)
        self.assertEqual(replace.quantums, 0)
        self.assertEqual(replace.subticks, 6_600_000_000)
        self.assertEqual(replace.trigger_subticks, 6_500_000_000)
        self.assertEqual(replace.order_basic_type, OrderBasicType.LIMIT)
        self.assertEqual(replace.condition_type, ConditionType.TAKE_PROFIT)

    def test_modify_order_resolves_human_price_and_size(self):
        orders = builder().modify_order(
            OrderRef(order_id=43),
            ModifyChanges(
                symbol="BTC-USDC",
                size="0.2",
                price=61_000,
                new_client_order_id=NEW_CID,
            ),
        )
        replace = orders.orders[0]
        self.assertEqual(
            replace.target.kind,
            DexReplaceTargetKind.ORDER_ID_WITH_CONTEXT,
        )
        self.assertEqual(replace.target.order_id, 43)
        self.assertEqual(replace.target.symbol_id, 7)
        self.assertEqual(replace.target.symbol_type, SymbolType.PERPETUAL)
        self.assertEqual(replace.quantums, 2_000_000_000)
        self.assertEqual(replace.subticks, 6_100_000_000)
        self.assertEqual(replace.new_client_order_id, NEW_CID)

    def test_place_orders_keeps_groups_in_one_dex_orders_payload(self):
        orders = builder().place_orders(
            [
                OrderInput(
                    symbol="BTC-USDC",
                    side="BUY",
                    type=OrderType.LIMIT,
                    size="0.1",
                    price="59000",
                ),
                BracketOrderGroup(
                    entry=OrderInput(
                        symbol="BTC-USDC",
                        side="BUY",
                        type=OrderType.MARKET,
                        size="0.1",
                    ),
                    sl=TpSlLeg(
                        type=OrderType.STOP_MARKET,
                        trigger_price="57000",
                    ),
                ),
            ]
        )
        self.assertEqual(orders.variant, DexOrdersVariant.PLACE)
        self.assertEqual(len(orders.orders), 2)
        self.assertEqual(orders.orders[1].grouping, Grouping.NORMAL_TPSL)

    def test_modify_condition_order_rejects_invalid_shapes(self):
        intents = builder()
        with self.assertRaisesRegex(ValueError, "whole-position"):
            intents.modify_condition_order(
                OrderRef(order_id=1),
                ModifyConditionChanges(
                    symbol="BTC-USDC",
                    type=OrderType.STOP_MARKET,
                    size_mode="close_position",
                    size="0.1",
                    trigger_price="57500",
                ),
            )
        with self.assertRaisesRegex(ValueError, "cannot change"):
            intents.modify_condition_order(
                OrderRef(order_id=1),
                ModifyConditionChanges(
                    symbol="BTC-USDC",
                    type=OrderType.STOP_MARKET,
                    size_mode="fixed",
                    current_size_mode="close_position",
                    size="0.1",
                    trigger_price="57500",
                ),
            )
        with self.assertRaisesRegex(ValueError, "market execution"):
            intents.modify_condition_order(
                OrderRef(order_id=1),
                ModifyConditionChanges(
                    symbol="BTC-USDC",
                    type=OrderType.STOP_MARKET,
                    size="0.1",
                    price="57000",
                    trigger_price="57500",
                ),
            )
        with self.assertRaisesRegex(ValueError, "limit execution"):
            intents.modify_condition_order(
                OrderRef(order_id=1),
                ModifyConditionChanges(
                    symbol="BTC-USDC",
                    type=OrderType.STOP_LIMIT,
                    size="0.1",
                    trigger_price="57500",
                ),
            )


if __name__ == "__main__":
    unittest.main()

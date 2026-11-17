# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
05 - DEX Cancel Order Test

Covers: DexPlaceOrder, DexCancelOrder, DexOrders(Cancel)
Flow: Place a limit order -> query active orders to get order_id -> cancel order

Run: python dex-examples/05_dex_cancel_order.py
Optional: ORDER_ID=12345 python dex-examples/05_dex_cancel_order.py
"""

import asyncio
import os
import sys

from _common import (
    MAIN_SUB_ADDRESS,
    TEST_SYMBOL_ID,
    _get_mark_price,
    build_and_submit_dex_orderless,
    fetch_open_order_ids,
    fetch_transaction_by_hash,
    generate_nonce,
    get_node_url,
    get_or_create_account,
    print_env_info,
    print_header,
)

from intention_sdk.api.client import RestClient
from intention_sdk.transactions.dex_payloads import (
    DexCancelOrder,
    DexOrderlessTx,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexTx,
)
from intention_sdk.types.enums import (
    ConditionType,
    CreatedBy,
    DexOrderlessTxVariant,
    DexOrdersVariant,
    OrderBasicType,
    OrderPositionMode,
    Side,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)


async def main():
    print("====================================")
    print("  05 - DEX Cancel Order Test")
    print("====================================")

    rest_client = RestClient(get_node_url())
    account = await get_or_create_account(rest_client)
    print_env_info()
    print("Account address:", account.account_address)

    # ===== Query mark price =====
    mark_price = await _get_mark_price(TEST_SYMBOL_ID)
    print(f"Mark price: {mark_price}")

    SUBTICK_MULTIPLIER = 100_000

    # ===== Get real order_id =====
    target_order_id: int

    if os.getenv("ORDER_ID"):
        target_order_id = int(os.environ["ORDER_ID"])
        print("Using ORDER_ID from environment variable:", target_order_id)
    else:
        # Step 1: Place a limit order (far from market price, ensure it stays in orderbook)
        print_header("1. Place Order (limit order far from market price, ensure it stays in orderbook)")

        buy_subticks = int(mark_price * 0.50) * SUBTICK_MULTIPLIER

        order = DexPlaceOrder(
            sub_address=MAIN_SUB_ADDRESS,
            symbol_id=TEST_SYMBOL_ID,
            symbol_type=SymbolType.PERPETUAL,
            side=Side.BUY,
            quantums=1000000,
            subticks=buy_subticks,
            trigger_subticks=0,
            order_basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            condition_type=ConditionType.UNSPECIFIED,
            trigger_price_type=TriggerPriceType.LAST_PRICE,
            target_order_id=0,
            reduce_only=False,
            position_mode=OrderPositionMode.NET,
            slippage_tolerance_ppm=100000,
        )

        print("Order params:")
        print("  Side: Buy")
        print("  Quantity:", order.quantums)
        print(f"  Price: {buy_subticks} (50% of mark price {mark_price})")
        print("  Type: Limit (GTC)")

        nonce = generate_nonce()
        dex_orders = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([order])])
        dex_tx = DexTx(nonce, dex_orders, CreatedBy.USER)
        orderless_tx = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)

        place_result = await build_and_submit_dex_orderless(rest_client, account, orderless_tx)
        print("Place order tx hash:", place_result["hash"])
        print("Place order status:", "SUCCESS" if place_result["success"] else "FAILED")

        if not place_result["success"]:
            print("Place order failed, cannot proceed with cancel order test")
            sys.exit(1)

        # Step 2: Query active orders to get order_id
        print_header("2. Query Active Orders to Get order_id")

        order_ids = await fetch_open_order_ids(str(account.account_address), limit=1)
        if not order_ids:
            print("Failed to get active order order_id")
            sys.exit(1)

        target_order_id = order_ids[0]
        print("Got order_id:", target_order_id)

    # ===== Cancel order =====
    print_header("3. Build Cancel Order Instruction")

    cancel_order = DexCancelOrder(
        sub_address=MAIN_SUB_ADDRESS,
        target_order_id=target_order_id,
        symbol_type=SymbolType.PERPETUAL,
    )

    print("Cancel order params:")
    print("  Sub-account:", cancel_order.sub_address)
    print("  Target order ID:", cancel_order.target_order_id)

    # Step 3: Submit cancel order
    print_header("4. Submit Cancel Order Transaction")

    nonce = generate_nonce()
    dex_orders = DexOrders(DexOrdersVariant.CANCEL, [cancel_order])
    dex_tx = DexTx(nonce, dex_orders, CreatedBy.USER)
    orderless_tx = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)

    cancel_result = await build_and_submit_dex_orderless(rest_client, account, orderless_tx)
    print("Cancel order tx hash:", cancel_result["hash"])
    print("Cancel order status:", "SUCCESS" if cancel_result["success"] else "FAILED")

    # Step 4: Query cancel order transaction details
    print_header("5. Query Cancel Order Transaction Details")

    cancel_tx_data = await fetch_transaction_by_hash(cancel_result["hash"])
    events = cancel_tx_data.get("events", [])
    print("Cancel order events count:", len(events))

    for event in events:
        short_type = event.get("type", "").split("::")[-1]
        print(f"  event: {short_type}", event.get("data"))

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

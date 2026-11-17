# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
07 - DEX Batch Orders Test

Covers: DexOrders(Place/Cancel/Replace) -- batch place/cancel/replace orders

Run: python dex-examples/07_dex_batch_orders.py
"""

import asyncio

from _common import (
    MAIN_SUB_ADDRESS,
    TEST_SYMBOL_ID,
    _get_mark_price,
    build_and_submit_dex_orderless,
    fetch_open_order_ids,
    generate_nonce,
    get_node_url,
    get_or_create_account,
    print_header,
)

from intention_sdk.api.client import RestClient
from intention_sdk.transactions.dex_payloads import (
    DexCancelOrder,
    DexOrderlessTx,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexReplaceOrder,
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


def make_limit_order(side, quantums, subticks):
    return DexPlaceOrder(
        sub_address=MAIN_SUB_ADDRESS,
        symbol_id=TEST_SYMBOL_ID,
        symbol_type=SymbolType.PERPETUAL,
        side=side,
        quantums=quantums,
        subticks=subticks,
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


async def main():
    print("====================================")
    print("  07 - DEX Batch Orders Test")
    print("====================================")

    rest_client = RestClient(get_node_url())
    account = await get_or_create_account(rest_client)

    # ===== Query mark price =====
    mark_price = await _get_mark_price(TEST_SYMBOL_ID)
    print(f"Mark price: {mark_price}")

    SUBTICK_MULTIPLIER = 100_000

    # 1. Build multiple different orders (far from market price, ensure they stay in orderbook)
    print_header("Build Batch Orders")

    buy1_subticks = int(mark_price * 0.50) * SUBTICK_MULTIPLIER
    buy2_subticks = int(mark_price * 0.45) * SUBTICK_MULTIPLIER
    sell3_subticks = int(mark_price * 2.00) * SUBTICK_MULTIPLIER

    order1 = make_limit_order(Side.BUY, 1000000, buy1_subticks)
    order2 = make_limit_order(Side.BUY, 1000000, buy2_subticks)
    order3 = make_limit_order(Side.SELL, 500000, sell3_subticks)

    print(f"Order 1: Buy  @ {buy1_subticks} (50% of mark price), qty=1000000")
    print(f"Order 2: Buy  @ {buy2_subticks} (45% of mark price), qty=1000000")
    print(f"Order 3: Sell @ {sell3_subticks} (200% of mark price), qty=500000")

    # 2. Batch submit
    print_header("Batch Submit (single transaction)")

    nonce = generate_nonce()
    dex_orders = DexOrders(
        DexOrdersVariant.PLACE, [DexPlaceOrders([order1, order2, order3])]
    )
    dex_tx = DexTx(nonce, dex_orders, CreatedBy.USER)
    orderless_tx = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)

    result = await build_and_submit_dex_orderless(rest_client, account, orderless_tx)
    print(
        "Batch place orders result:",
        result["hash"],
        "SUCCESS" if result["success"] else "FAILED",
    )
    print("Submitted 3 orders in a single transaction")

    # 3. Place 3 limit orders and collect order_ids (for subsequent batch cancel/replace)
    print_header("Place 3 Limit Orders and Collect order_ids")

    owner_addr = str(account.account_address)
    for i in range(3):
        single_subticks = int(mark_price * (0.40 - i * 0.05)) * SUBTICK_MULTIPLIER
        single_order = make_limit_order(Side.BUY, 100000, single_subticks)

        single_nonce = generate_nonce()
        single_dex_orders = DexOrders(
            DexOrdersVariant.PLACE, [DexPlaceOrders([single_order])]
        )
        single_dex_tx = DexTx(single_nonce, single_dex_orders, CreatedBy.USER)
        single_orderless_tx = DexOrderlessTx(DexOrderlessTxVariant.DEX, single_dex_tx)

        single_result = await build_and_submit_dex_orderless(
            rest_client, account, single_orderless_tx
        )
        pct = int((0.40 - i * 0.05) * 100)
        print(
            f"Order {i + 1}: @ {single_subticks} ({pct}% of mark price)",
            single_result["hash"],
            "SUCCESS" if single_result["success"] else "FAILED",
        )

    order_ids = await fetch_open_order_ids(owner_addr, limit=3)
    print("Collected order_ids:", ", ".join(str(oid) for oid in order_ids) or "(none)")

    # 4. Batch cancel
    if len(order_ids) >= 2:
        print_header("Batch Cancel (cancel multiple orders in single transaction)")

        cancel_orders = [
            DexCancelOrder(MAIN_SUB_ADDRESS, oid, SymbolType.PERPETUAL)
            for oid in order_ids
        ]

        print("Cancelling orders:")
        for i, c in enumerate(cancel_orders):
            print(f"  Cancel {i + 1}: order_id={c.target_order_id}")

        cancel_nonce = generate_nonce()
        dex_cancel_orders = DexOrders(DexOrdersVariant.CANCEL, cancel_orders)
        cancel_dex_tx = DexTx(cancel_nonce, dex_cancel_orders, CreatedBy.USER)
        cancel_orderless_tx = DexOrderlessTx(DexOrderlessTxVariant.DEX, cancel_dex_tx)

        cancel_result = await build_and_submit_dex_orderless(
            rest_client, account, cancel_orderless_tx
        )
        print(
            "Batch cancel:",
            cancel_result["hash"],
            "SUCCESS" if cancel_result["success"] else "FAILED",
        )
        print("Cancelled", len(cancel_orders), "orders")
    else:
        print("\nSkipping batch cancel: not enough order_ids collected")

    # 5. Batch replace
    print_header("Place 2 Limit Orders for Batch Replace")

    for i in range(2):
        place_subticks = int(mark_price * (0.35 - i * 0.05)) * SUBTICK_MULTIPLIER
        place_order = make_limit_order(Side.BUY, 200000, place_subticks)

        place_nonce = generate_nonce()
        place_dex_orders = DexOrders(
            DexOrdersVariant.PLACE, [DexPlaceOrders([place_order])]
        )
        place_dex_tx = DexTx(place_nonce, place_dex_orders, CreatedBy.USER)
        place_orderless_tx = DexOrderlessTx(DexOrderlessTxVariant.DEX, place_dex_tx)

        place_result = await build_and_submit_dex_orderless(
            rest_client, account, place_orderless_tx
        )
        pct = int((0.35 - i * 0.05) * 100)
        print(
            f"Pre-replace order {i + 1}: @ {place_subticks} ({pct}% of mark price)",
            place_result["hash"],
            "SUCCESS" if place_result["success"] else "FAILED",
        )

    replace_order_ids = await fetch_open_order_ids(owner_addr, limit=2)
    print(
        "Collected replace order_ids:",
        ", ".join(str(oid) for oid in replace_order_ids) or "(none)",
    )

    if len(replace_order_ids) >= 2:
        print_header("Batch Replace (replace multiple orders in single transaction)")

        replace_orders = [
            DexReplaceOrder.by_order_id(
                sub_address=MAIN_SUB_ADDRESS,
                target_order_id=oid,
                symbol_id=TEST_SYMBOL_ID,
                symbol_type=SymbolType.PERPETUAL,
                quantums=300000,
                subticks=int(mark_price * (0.30 - i * 0.05)) * SUBTICK_MULTIPLIER,
            )
            for i, oid in enumerate(replace_order_ids)
        ]

        print("Replacing orders:")
        for i, r in enumerate(replace_orders):
            pct = int((0.30 - i * 0.05) * 100)
            print(
                f"  Replace {i + 1}: order_id={r.target_order_id} -> qty=300000 price={r.subticks} ({pct}% of mark price)"
            )

        replace_nonce = generate_nonce()
        dex_replace_orders = DexOrders(DexOrdersVariant.REPLACE, replace_orders)
        replace_dex_tx = DexTx(replace_nonce, dex_replace_orders, CreatedBy.USER)
        replace_orderless_tx = DexOrderlessTx(DexOrderlessTxVariant.DEX, replace_dex_tx)

        replace_result = await build_and_submit_dex_orderless(
            rest_client, account, replace_orderless_tx
        )
        print(
            "Batch replace:",
            replace_result["hash"],
            "SUCCESS" if replace_result["success"] else "FAILED",
        )
        print("Replaced", len(replace_orders), "orders")
    else:
        print("\nSkipping batch replace: not enough order_ids collected")

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

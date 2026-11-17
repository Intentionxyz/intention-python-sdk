# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
06 - DEX Replace Order Test (Cancel + Place method)

Covers: DexPlaceOrder, DexCancelOrder, DexOrders(Place/Cancel)
Flow: Place limit order -> query active orders to get order_id -> cancel order -> place new order (modified params)

Run: python dex-examples/06_dex_replace_order.py
Optional: ORDER_ID=12345 python dex-examples/06_dex_replace_order.py
"""

import asyncio
import os
import sys

import httpx

from _common import (
    MAIN_SUB_ADDRESS,
    build_and_submit_dex_orderless,
    fetch_open_order_ids,
    generate_nonce,
    get_dex_sub_accounts,
    get_fullnode_base,
    get_node_url,
    get_or_create_account,
    print_dex_sub_accounts,
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

# ===== Constants =====
ORDER_SYMBOL_ID = 0
SUBTICK_MULTIPLIER = 100000


async def get_mark_price(symbol_id: int) -> float:
    """Query mark price"""
    defaults = {0: 67550, 1: 2025}
    try:
        url = f"{get_fullnode_base()}/v1/dex/mark_prices"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            if resp.is_success:
                data = resp.json()
                for p in data.get("prices", []):
                    if p.get("symbol_id") == symbol_id:
                        return float(p["mark_price"])
    except Exception:
        pass
    return defaults.get(symbol_id, 67550)


async def check_order_status(order_id: str):
    """Query order status via /v1/dex/orders/{orderId}"""
    try:
        url = f"{get_fullnode_base()}/v1/dex/orders/{order_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            if not resp.is_success or resp.status_code == 404:
                return {"exists": False}
            data = resp.json()
            if not data:
                return {"exists": False, "data": data}
            return {"exists": True, "filled_quantums": int(data.get("filled_quantums", 0)), "data": data}
    except Exception:
        return {"exists": False}


async def main():
    print("====================================")
    print("  06 - DEX Replace Order Test (Cancel + Place)")
    print("====================================")
    print("Strategy: Following trading-web frontend, use Cancel + Place two-step replacement\n")

    rest_client = RestClient(get_node_url())
    account = await get_or_create_account(rest_client)
    owner_addr = str(account.account_address)
    print_env_info()
    print("Account address:", owner_addr)

    # ===== Get mark price =====
    mark_price = await get_mark_price(ORDER_SYMBOL_ID)
    print(f"\nBTC-USDC mark price: {mark_price} USDC")

    # ===== Get real order_id =====
    orig_quantums = 1000000
    orig_price_usd = int(mark_price * 0.80)
    orig_subticks = orig_price_usd * SUBTICK_MULTIPLIER

    if os.getenv("ORDER_ID"):
        target_order_id = int(os.environ["ORDER_ID"])
        print("Using ORDER_ID from environment variable:", target_order_id)
    else:
        print_header("1. Place Order (limit order far from market price, ensure it stays in orderbook)")

        order = DexPlaceOrder(
            sub_address=MAIN_SUB_ADDRESS,
            symbol_id=ORDER_SYMBOL_ID,
            symbol_type=SymbolType.PERPETUAL,
            side=Side.BUY,
            quantums=orig_quantums,
            subticks=orig_subticks,
            trigger_subticks=0,
            order_basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            condition_type=ConditionType.UNSPECIFIED,
            trigger_price_type=TriggerPriceType.LAST_PRICE,
            target_order_id=0,
            reduce_only=False,
            position_mode=OrderPositionMode.NET,
        )

        print("Order params:")
        print("  Market: BTC-USDC (symbol_id:", ORDER_SYMBOL_ID, ")")
        print("  Side: Buy")
        print("  Quantity:", orig_quantums)
        print(f"  Price: {orig_subticks} (~{orig_price_usd} USDC, ~80% of mark price {mark_price} USDC)")
        print("  Type: Limit (GTC)")

        nonce1 = generate_nonce()
        dex_orders1 = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([order])])
        dex_tx1 = DexTx(nonce1, dex_orders1, CreatedBy.USER)
        orderless_tx1 = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx1)

        place_result = await build_and_submit_dex_orderless(rest_client, account, orderless_tx1)
        print("Place order tx hash:", place_result["hash"])
        print("Place order status:", "SUCCESS" if place_result["success"] else "FAILED")

        if not place_result["success"]:
            print("Place order failed, cannot proceed with replace order test")
            sys.exit(1)

        print_header("2. Query Active Orders to Get order_id")
        order_ids = await fetch_open_order_ids(owner_addr, limit=1)
        if not order_ids:
            print("Failed to get active order order_id")
            sys.exit(1)
        target_order_id = order_ids[0]
        print("Got order_id:", target_order_id)

    # Verify order status
    print_header("2.5 Verify Order Status")
    order_status = await check_order_status(str(target_order_id))
    if order_status["exists"]:
        print("Order is in orderbook (pending fill)")
        print("  filled_quantums:", order_status.get("filled_quantums"))
    else:
        print("Order is not in orderbook (may have been filled)")

    # ===== Replace Step 1: Cancel order =====
    print_header("3. Cancel Original Order")

    cancel_order = DexCancelOrder(
        sub_address=MAIN_SUB_ADDRESS,
        target_order_id=target_order_id,
        symbol_type=SymbolType.PERPETUAL,
    )

    print("Cancel order params:")
    print("  Sub-account:", cancel_order.sub_address)
    print("  Target order ID:", cancel_order.target_order_id)

    nonce_cancel = generate_nonce()
    dex_orders_cancel = DexOrders(DexOrdersVariant.CANCEL, [cancel_order])
    dex_tx_cancel = DexTx(nonce_cancel, dex_orders_cancel, CreatedBy.USER)
    orderless_tx_cancel = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx_cancel)

    cancel_result = await build_and_submit_dex_orderless(rest_client, account, orderless_tx_cancel)
    print("Cancel order tx hash:", cancel_result["hash"])
    print("Cancel order status:", "SUCCESS" if cancel_result["success"] else "FAILED")

    # ===== Replace Step 2: Place new order =====
    print_header("4. Place New Order (modified params)")

    new_quantums = 1500000
    new_price_usd = int(mark_price * 0.82)
    new_subticks = new_price_usd * SUBTICK_MULTIPLIER

    new_order = DexPlaceOrder(
        sub_address=MAIN_SUB_ADDRESS,
        symbol_id=ORDER_SYMBOL_ID,
        symbol_type=SymbolType.PERPETUAL,
        side=Side.BUY,
        quantums=new_quantums,
        subticks=new_subticks,
        trigger_subticks=0,
        order_basic_type=OrderBasicType.LIMIT,
        time_in_force=TimeInForce.GTC,
        condition_type=ConditionType.UNSPECIFIED,
        trigger_price_type=TriggerPriceType.LAST_PRICE,
        target_order_id=0,
        reduce_only=False,
        position_mode=OrderPositionMode.NET,
    )

    print("New order params (compared to original):")
    print("  Market: BTC-USDC (symbol_id:", ORDER_SYMBOL_ID, ")")
    print("  Side: Buy")
    print(f"  Quantity: {new_quantums} (original: {orig_quantums})")
    print(f"  Price: {new_subticks} (~{new_price_usd} USDC, original: ~{orig_price_usd} USDC)")
    print("  Type: Limit (GTC)")

    nonce_new = generate_nonce()
    dex_orders_new = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([new_order])])
    dex_tx_new = DexTx(nonce_new, dex_orders_new, CreatedBy.USER)
    orderless_tx_new = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx_new)

    new_result = await build_and_submit_dex_orderless(rest_client, account, orderless_tx_new)
    print("New order tx hash:", new_result["hash"])
    print("New order status:", "SUCCESS" if new_result["success"] else "FAILED")

    # Step 5: Replace order result
    print_header("5. Replace Order Result")
    if new_result["success"]:
        print("\nReplace order succeeded (Cancel + Place)!")
        print(f"  Original order_id: {target_order_id} -> cancelled")
        print(f"  New order tx hash: {new_result['hash']}")
    else:
        print("\nNew order submission failed")

    # Final balance query
    print_header("6. Final DEX Sub-accounts")
    dex_accounts = await get_dex_sub_accounts(owner_addr)
    print_dex_sub_accounts(dex_accounts)

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

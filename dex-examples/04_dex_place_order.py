# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
04 - DEX Place Order Test

Covers: DexPlaceOrder, DexPlaceOrders, DexOrders, DexTx, DexOrderlessTx,
      TransactionPayload(DEX_ORDERLESS), RawTransaction.create_orderless(),
      Conditional orders: ConditionType.STOP_LOSS/TAKE_PROFIT, TriggerPriceType

Run: python dex-examples/04_dex_place_order.py
"""

import asyncio

from _common import (
    MAIN_SUB_ADDRESS,
    TEST_SYMBOL_ID,
    build_and_submit_dex_orderless,
    generate_nonce,
    get_node_url,
    get_or_create_account,
    print_env_info,
    print_header,
)

from intention_sdk.api.client import RestClient
from intention_sdk.transactions.dex_payloads import (
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
    print("  04 - DEX Place Order Test")
    print("====================================")

    rest_client = RestClient(get_node_url())
    account = await get_or_create_account(rest_client)
    print_env_info()
    print("Account address:", account.account_address)

    # 1. Build DexPlaceOrder (limit buy order)
    print_header("Build DEX Limit Buy Order")

    order = DexPlaceOrder(
        sub_address=MAIN_SUB_ADDRESS,
        symbol_id=TEST_SYMBOL_ID,
        symbol_type=SymbolType.PERPETUAL,
        side=Side.BUY,
        quantums=1000000,
        subticks=50000000,
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
    print("  Sub-account:", MAIN_SUB_ADDRESS)
    print("  Market:", order.symbol_id)
    print("  Side: Buy")
    print("  Quantity:", order.quantums)
    print("  Price:", order.subticks)
    print("  Type: Limit")

    # 2. Wrap as DEX transaction
    print_header("Wrap DEX Transaction")

    nonce = generate_nonce()
    print("Nonce:", nonce)

    dex_orders = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([order])])
    dex_tx = DexTx(nonce, dex_orders, CreatedBy.USER)
    orderless_tx = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)

    print("Payload built successfully")
    print("  DexOrdersVariant:", DexOrdersVariant.PLACE, "(Place)")
    print("  DexOrderlessTxVariant:", DexOrderlessTxVariant.DEX, "(Dex)")
    print("  CreatedBy:", CreatedBy.USER, "(User)")

    # 3. Submit limit buy order
    print_header("Submit Limit Buy Order")

    result1 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx)
    print("TX Hash:", result1["hash"])
    print("Status:", "SUCCESS" if result1["success"] else "FAILED")

    # 4. Market sell order
    print_header("Build DEX Market Sell Order")

    market_order = DexPlaceOrder(
        sub_address=MAIN_SUB_ADDRESS,
        symbol_id=TEST_SYMBOL_ID,
        symbol_type=SymbolType.PERPETUAL,
        side=Side.SELL,
        quantums=500000,
        subticks=40000000,
        trigger_subticks=0,
        order_basic_type=OrderBasicType.MARKET,
        time_in_force=TimeInForce.IOC,
        condition_type=ConditionType.UNSPECIFIED,
        trigger_price_type=TriggerPriceType.LAST_PRICE,
        target_order_id=0,
        reduce_only=False,
        position_mode=OrderPositionMode.NET,
        slippage_tolerance_ppm=100000,
    )

    nonce2 = generate_nonce()
    dex_orders2 = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([market_order])])
    dex_tx2 = DexTx(nonce2, dex_orders2, CreatedBy.USER)
    orderless_tx2 = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx2)

    result2 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx2)
    print("Market sell order:", result2["hash"], "SUCCESS" if result2["success"] else "FAILED")

    # 5. Hedge bidirectional position mode
    print_header("Hedge Mode Bidirectional Positions (requires running 08 to switch to Hedge mode first)")
    print("Note: Must run 08_dex_user_config to switch to Hedge mode first")

    try:
        hedge_buy = DexPlaceOrder(
            sub_address=MAIN_SUB_ADDRESS,
            symbol_id=TEST_SYMBOL_ID,
            symbol_type=SymbolType.PERPETUAL,
            side=Side.BUY,
            quantums=1000000,
            subticks=50000000,
            trigger_subticks=0,
            order_basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            condition_type=ConditionType.UNSPECIFIED,
            trigger_price_type=TriggerPriceType.LAST_PRICE,
            target_order_id=0,
            reduce_only=False,
            position_mode=OrderPositionMode.HEDGE,
            slippage_tolerance_ppm=100000,
        )

        hedge_sell = DexPlaceOrder(
            sub_address=MAIN_SUB_ADDRESS,
            symbol_id=TEST_SYMBOL_ID,
            symbol_type=SymbolType.PERPETUAL,
            side=Side.SELL,
            quantums=1000000,
            subticks=50000000,
            trigger_subticks=0,
            order_basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            condition_type=ConditionType.UNSPECIFIED,
            trigger_price_type=TriggerPriceType.LAST_PRICE,
            target_order_id=0,
            reduce_only=False,
            position_mode=OrderPositionMode.HEDGE,
            slippage_tolerance_ppm=100000,
        )

        print("Long: Buy 1000000 @ 50000000")
        print("Short: Sell 1000000 @ 50000000")
        print("Expected: In Hedge mode, both positions coexist without netting")

        nonce4 = generate_nonce()
        dex_orders4 = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([hedge_buy])])
        dex_tx4 = DexTx(nonce4, dex_orders4, CreatedBy.USER)
        orderless_tx4 = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx4)
        result4 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx4)
        print("Hedge long:", result4["hash"], "SUCCESS" if result4["success"] else "FAILED")

        nonce5 = generate_nonce()
        dex_orders5 = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([hedge_sell])])
        dex_tx5 = DexTx(nonce5, dex_orders5, CreatedBy.USER)
        orderless_tx5 = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx5)
        result5 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx5)
        print("Hedge short:", result5["hash"], "SUCCESS" if result5["success"] else "FAILED")
    except Exception as e:
        print(f"Hedge mode test skipped: {e}")
        print("Hint: Please run 08_dex_user_config.py to switch to Hedge mode first")

    # 6. StopLoss conditional order
    print_header("StopLoss Conditional Order")

    stop_loss_order = DexPlaceOrder(
        sub_address=MAIN_SUB_ADDRESS,
        symbol_id=TEST_SYMBOL_ID,
        symbol_type=SymbolType.PERPETUAL,
        side=Side.SELL,
        quantums=500000,
        subticks=45000000,
        trigger_subticks=46000000,
        order_basic_type=OrderBasicType.MARKET,
        time_in_force=TimeInForce.IOC,
        condition_type=ConditionType.STOP_LOSS,
        trigger_price_type=TriggerPriceType.MARK_PRICE,
        target_order_id=0,
        reduce_only=True,
        position_mode=OrderPositionMode.NET,
        slippage_tolerance_ppm=100000,
    )

    print("Stop-loss order params:")
    print("  Trigger condition: StopLoss (mark price <= 46000000)")
    print("  Trigger price type: MarkPrice")
    print("  Execution: Market sell 500000")
    print("  reduce_only: true")

    nonce6 = generate_nonce()
    dex_orders6 = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([stop_loss_order])])
    dex_tx6 = DexTx(nonce6, dex_orders6, CreatedBy.USER)
    orderless_tx6 = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx6)
    result6 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx6)
    print("StopLoss:", result6["hash"], "SUCCESS" if result6["success"] else "FAILED")

    # 7. TakeProfit conditional order
    print_header("TakeProfit Conditional Order")

    take_profit_order = DexPlaceOrder(
        sub_address=MAIN_SUB_ADDRESS,
        symbol_id=TEST_SYMBOL_ID,
        symbol_type=SymbolType.PERPETUAL,
        side=Side.SELL,
        quantums=500000,
        subticks=55000000,
        trigger_subticks=54000000,
        order_basic_type=OrderBasicType.MARKET,
        time_in_force=TimeInForce.IOC,
        condition_type=ConditionType.TAKE_PROFIT,
        trigger_price_type=TriggerPriceType.LAST_PRICE,
        target_order_id=0,
        reduce_only=True,
        position_mode=OrderPositionMode.NET,
        slippage_tolerance_ppm=100000,
    )

    print("Take-profit order params:")
    print("  Trigger condition: TakeProfit (last price >= 54000000)")
    print("  Trigger price type: LastPrice")
    print("  Execution: Market sell 500000")
    print("  reduce_only: true")

    nonce7 = generate_nonce()
    dex_orders7 = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([take_profit_order])])
    dex_tx7 = DexTx(nonce7, dex_orders7, CreatedBy.USER)
    orderless_tx7 = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx7)
    result7 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx7)
    print("TakeProfit:", result7["hash"], "SUCCESS" if result7["success"] else "FAILED")

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

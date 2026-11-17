# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
08 - DEX User Config Test

Covers: UserSymbolLeverage, SetUserLeverage, ChangePositionMode,
      ChangeMarginMode, SymbolMarginMode, MarginMode,
      DexUserConfigTx, DexUserConfigTxVariant

Run: python dex-examples/08_dex_user_config.py
"""

import asyncio

from _common import (
    MAIN_SUB_ADDRESS,
    TEST_SYMBOL_ID,
    TEST_SYMBOL_ID_2,
    build_and_submit_dex_orderless,
    generate_nonce,
    get_node_url,
    get_or_create_account,
    print_header,
)

from intention_sdk.api.client import RestClient
from intention_sdk.transactions.dex_payloads import (
    ChangeMarginMode,
    ChangePositionMode,
    DexOrderlessTx,
    DexUserConfigTx,
    SetUserLeverage,
    SymbolMarginMode,
    UserSymbolLeverage,
)
from intention_sdk.types.enums import (
    DexOrderlessTxVariant,
    DexUserConfigTxVariant,
    MarginMode,
    OrderPositionMode,
)


async def main():
    print("====================================")
    print("  08 - DEX User Config Test")
    print("====================================")

    rest_client = RestClient(get_node_url())
    account = await get_or_create_account(rest_client)

    # 1. Set leverage
    print_header("Set User Leverage")

    leverage_settings = [UserSymbolLeverage(TEST_SYMBOL_ID, 100)]
    if TEST_SYMBOL_ID_2 is not None:
        leverage_settings.append(UserSymbolLeverage(TEST_SYMBOL_ID_2, 50))
        print("TEST_SYMBOL_ID_2 detected, will also configure leverage for the second market")

    print("Leverage settings:")
    for lev in leverage_settings:
        print(f"  Market {lev.symbol_id}: {lev.leverage}x")

    nonce1 = generate_nonce()
    set_leverage = SetUserLeverage(nonce1, MAIN_SUB_ADDRESS, leverage_settings)
    config_tx1 = DexUserConfigTx(DexUserConfigTxVariant.SET_USER_LEVERAGE, set_leverage)
    orderless_tx1 = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx1)

    result1 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx1)
    print("Set leverage:", result1["hash"], "SUCCESS" if result1["success"] else "FAILED")

    # 2. Switch position mode Net -> Hedge
    print_header("Switch Position Mode")

    nonce2 = generate_nonce()
    change_to_hedge = ChangePositionMode(nonce2, MAIN_SUB_ADDRESS, OrderPositionMode.HEDGE)
    print("Switching to: Hedge")

    config_tx2 = DexUserConfigTx(DexUserConfigTxVariant.CHANGE_POSITION_MODE, change_to_hedge)
    orderless_tx2 = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx2)

    result2 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx2)
    print("Switch to Hedge:", result2["hash"], "SUCCESS" if result2["success"] else "FAILED")

    # 3. Switch back to Net mode
    print_header("Switch Back to Net Mode")

    nonce3 = generate_nonce()
    change_to_net = ChangePositionMode(nonce3, MAIN_SUB_ADDRESS, OrderPositionMode.NET)

    config_tx3 = DexUserConfigTx(DexUserConfigTxVariant.CHANGE_POSITION_MODE, change_to_net)
    orderless_tx3 = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx3)

    result3 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx3)
    print("Switch to Net:", result3["hash"], "SUCCESS" if result3["success"] else "FAILED")

    # 4. Switch margin mode Cross -> Isolated
    print_header("Switch Margin Mode Cross -> Isolated")

    nonce4 = generate_nonce()
    symbol_margin_mode1 = SymbolMarginMode(TEST_SYMBOL_ID, MarginMode.ISOLATED)
    change_to_isolated = ChangeMarginMode(nonce4, MAIN_SUB_ADDRESS, [symbol_margin_mode1])

    print("Switching to: Isolated (isolated margin)")
    print(f"  Market {TEST_SYMBOL_ID}: Cross -> Isolated")

    config_tx4 = DexUserConfigTx(DexUserConfigTxVariant.CHANGE_MARGIN_MODE, change_to_isolated)
    orderless_tx4 = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx4)

    result4 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx4)
    print("Switch to Isolated:", result4["hash"], "SUCCESS" if result4["success"] else "FAILED")

    # 5. Switch back to Cross mode
    print_header("Switch Margin Mode Isolated -> Cross")

    nonce5 = generate_nonce()
    symbol_margin_mode2 = SymbolMarginMode(TEST_SYMBOL_ID, MarginMode.CROSS)
    change_to_cross = ChangeMarginMode(nonce5, MAIN_SUB_ADDRESS, [symbol_margin_mode2])

    print("Switching to: Cross (cross margin)")
    print(f"  Market {TEST_SYMBOL_ID}: Isolated -> Cross")

    config_tx5 = DexUserConfigTx(DexUserConfigTxVariant.CHANGE_MARGIN_MODE, change_to_cross)
    orderless_tx5 = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx5)

    result5 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx5)
    print("Switch to Cross:", result5["hash"], "SUCCESS" if result5["success"] else "FAILED")

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
11 - DEX Agent Wallet Authorization Test

Covers: AgentApprove, AgentRevoke, DexAgentTx, AgentOperationVariant,
      DexTx (onBehalfOf), delegated order placement

Run: python dex-examples/11_dex_agent_wallet.py
"""

import asyncio
import time

from _common import (
    MAIN_SUB_ADDRESS,
    TEST_SYMBOL_ID,
    build_and_submit_dex_orderless,
    generate_nonce,
    generate_secp256k1_account,
    get_faucet_url,
    get_node_url,
    get_or_create_account,
    print_header,
)

from intention_sdk.api.client import FaucetClient, RestClient
from intention_sdk.transactions.dex_payloads import (
    AgentApprove,
    AgentRevoke,
    DexAgentTx,
    DexOrderlessTx,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexTx,
)
from intention_sdk.types.enums import (
    AgentOperationVariant,
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
    print("  11 - DEX Agent Wallet Authorization Test")
    print("====================================")

    rest_client = RestClient(get_node_url())
    master = await get_or_create_account(rest_client)
    agent = generate_secp256k1_account()

    print("Master account:", master.account_address)
    print("Agent account:", agent.account_address)

    # Fund agent via faucet
    print_header("Fund Agent Account via Faucet")
    try:
        faucet_client = FaucetClient(get_faucet_url(), rest_client)
        await faucet_client.fund_account(agent.account_address, 500_000_000)
        print("Agent faucet funding complete: 5 native coins")
    except Exception as err:
        print(f"Agent faucet funding failed: {err}")
        print("Continuing (Agent may already have a balance)...")

    # 1. Authorize Agent
    print_header("Authorize Agent for Delegated Trading")

    agent_name = "test-agent"
    agent_address = agent.account_address
    expiry_timestamp = int(time.time()) + 86400  # 24h

    agent_approve = AgentApprove(agent_name, agent_address, expiry_timestamp)

    nonce1 = generate_nonce()
    dex_agent_tx1 = DexAgentTx(nonce1, AgentOperationVariant.APPROVE, agent_approve)
    orderless_tx1 = DexOrderlessTx(DexOrderlessTxVariant.DEX_AGENT, dex_agent_tx1)

    print("Authorization params:")
    print("  Name:", agent_name)
    print("  Agent address:", agent_address)
    print("  Expiry:", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expiry_timestamp)))

    result1 = await build_and_submit_dex_orderless(rest_client, master, orderless_tx1)
    print("Authorize Agent:", result1["hash"], "SUCCESS" if result1["success"] else "FAILED")

    # 2. Agent places order on behalf of master (onBehalfOf)
    print_header("Agent Delegated Order Placement (onBehalfOf)")

    place_order = DexPlaceOrder(
        sub_address=MAIN_SUB_ADDRESS,
        symbol_id=TEST_SYMBOL_ID,
        symbol_type=SymbolType.PERPETUAL,
        side=Side.BUY,
        quantums=100000,
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

    nonce2 = generate_nonce()
    dex_orders = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([place_order])])
    master_address = master.account_address
    dex_tx = DexTx(nonce2, dex_orders, CreatedBy.USER, master_address)

    print("Delegated order params:")
    print("  Signer (agent):", agent.account_address)
    print("  onBehalfOf (master):", master_address)
    print("  Order: Buy 100000 @ 50000000")

    orderless_tx2 = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)
    result2 = await build_and_submit_dex_orderless(rest_client, agent, orderless_tx2)
    print("Agent delegated order:", result2["hash"], "SUCCESS" if result2["success"] else "FAILED")

    # 3. Revoke Agent authorization
    print_header("Revoke Agent Authorization")

    agent_revoke = AgentRevoke(agent_name)

    nonce3 = generate_nonce()
    dex_agent_tx3 = DexAgentTx(nonce3, AgentOperationVariant.REVOKE, agent_revoke)
    orderless_tx3 = DexOrderlessTx(DexOrderlessTxVariant.DEX_AGENT, dex_agent_tx3)

    print("Revoke params:")
    print("  Name:", agent_name)

    result3 = await build_and_submit_dex_orderless(rest_client, master, orderless_tx3)
    print("Revoke Agent:", result3["hash"], "SUCCESS" if result3["success"] else "FAILED")

    # 4. Verify Agent cannot place orders after revocation
    print_header("Verify Agent Cannot Place Orders After Revocation")

    try:
        nonce4 = generate_nonce()
        dex_orders4 = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([place_order])])
        dex_tx4 = DexTx(nonce4, dex_orders4, CreatedBy.USER, master_address)
        orderless_tx4 = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx4)

        result4 = await build_and_submit_dex_orderless(rest_client, agent, orderless_tx4)
        print("Post-revocation delegated order:", result4["hash"], "SUCCESS (unexpected)" if result4["success"] else "FAILED (expected)")
    except Exception as err:
        print(f"Post-revocation delegated order failed (expected): {err}")

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

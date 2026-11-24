# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Approve an agent, place a delegated order, and revoke the same approval."""

import asyncio
import os
import secrets
from decimal import Decimal

from intention_sdk import (
    DexTransactionExecutor,
    OrderClient,
    OrderPositionMode,
    OrderRef,
)
from intention_sdk.api.client import FaucetClient

from _common import (
    example_limit_buy,
    get_dex_rest_api_url,
    get_example_market_price,
    get_faucet_url,
    get_node_url,
    load_account_from_env,
    trading_example,
)


async def main() -> None:
    async with trading_example() as (owner, symbol):
        sdk = owner.sdk
        agent = (
            load_account_from_env("AGENT_PRIVATE_KEY")
            if os.getenv("AGENT_PRIVATE_KEY")
            else sdk.accounts.generate_agent_account()
        )
        if not os.getenv("AGENT_PRIVATE_KEY"):
            faucet = FaucetClient(get_faucet_url(), sdk.rest_client)
            await faucet.fund_account(agent.account_address, 500_000_000)

        snapshot = await owner.get_account()
        if snapshot is None:
            raise ValueError("The owner needs a funded trading subaccount")
        mode = OrderPositionMode(int(snapshot["position_mode"]))

        name = "example-" + secrets.token_hex(4)
        approved = await sdk.accounts.approve_agent(
            name, agent, expires_in_secs=24 * 60 * 60
        )
        print("Agent approval confirmed:", approved.hash)
        try:
            delegated = OrderClient(
                executor=DexTransactionExecutor(sdk.rest_client, agent),
                signer=agent,
                sub_address=owner.sub_address,
                position_mode=mode,
                resolver=await sdk.markets.get_resolver(),
                on_behalf_of=sdk.signer.account_address,
                node_url=get_node_url(),
                relayer_url=get_dex_rest_api_url(),
                trust_env=False,
            )
            mark = await get_example_market_price(symbol)
            order = example_limit_buy(symbol, mark * Decimal("0.98"))
            result = await delegated.place_order(order, throw_on_order_reject=True)
            print("Delegated order confirmed:", result.hash, result.orders)
            await delegated.cancel_order(
                OrderRef(client_order_id=order.client_order_id),
                throw_on_order_reject=True,
            )
        finally:
            revoked = await sdk.accounts.revoke_agent(name)
            print("Agent revocation confirmed:", revoked.hash)


if __name__ == "__main__":
    asyncio.run(main())

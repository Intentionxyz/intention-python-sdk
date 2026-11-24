# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Local order lifecycle corresponding to the TypeScript lifecycle example."""

from __future__ import annotations

import asyncio
import os
import secrets

from intention_sdk import (
    Account,
    ClientConfig,
    DexTransactionExecutor,
    MarketMetadata,
    MarketsClient,
    ModifyChanges,
    OrderClient,
    OrderInput,
    OrderIntents,
    OrderIntentsContext,
    OrderPositionMode,
    OrderRef,
    OrderType,
    RestClient,
    SimpleMarketResolver,
    TpSlLeg,
)

from _common import (
    get_dex_rest_api_url,
    get_node_url,
    get_sub_address,
    load_account_from_env,
)


async def main() -> None:
    dry_run = os.getenv("DRY_RUN") == "1"
    signer = (
        Account.generate()
        if dry_run and not os.getenv("PRIVATE_KEY")
        else load_account_from_env()
    )
    sub_address = get_sub_address(signer, int(os.getenv("SUBACCOUNT", "0")))
    symbol = os.getenv("SYMBOL", "BTC-USDC")

    entry = OrderInput(
        symbol=symbol, side="BUY", type=OrderType.LIMIT, size="0.5", price=60_000
    )
    tp = TpSlLeg(type=OrderType.TAKE_PROFIT_MARKET, trigger_price=66_000)
    sl = TpSlLeg(type=OrderType.STOP_MARKET, trigger_price=57_000)

    if dry_run:
        resolver = SimpleMarketResolver(
            [MarketMetadata(symbol, 0, -10, -9, 1_000_000, 100_000)]
        )
        builder = OrderIntents(
            OrderIntentsContext(sub_address, OrderPositionMode.NET, resolver)
        )
        bracket = builder.place_order_with_tpsl(entry, tp=tp, sl=sl)
        print(
            f"Built bracket payload: variant={bracket.variant}, groups={len(bracket.orders)}"
        )
        return

    node_url = get_node_url()
    relayer_url = get_dex_rest_api_url()
    if not relayer_url:
        raise SystemExit(
            "Set DEX_REST_API_URL (or DEX_REST_URL) to the Relayer base URL"
        )

    resolver = await MarketsClient(
        relayer_url, trust_env=False
    ).fetch_perpetual_markets(statuses=("ACTIVE",))
    node = RestClient(node_url, ClientConfig(trust_env=False))
    try:
        client = OrderClient(
            executor=DexTransactionExecutor(node, signer),
            signer=signer,
            sub_address=sub_address,
            position_mode=OrderPositionMode.NET,
            resolver=resolver,
            node_url=node_url,
            relayer_url=relayer_url,
            trust_env=False,
        )
        bracket = await client.place_order_with_tpsl(
            entry, tp=tp, sl=sl, throw_on_order_reject=True
        )
        print("Bracket confirmed:", bracket.hash, bracket.orders)

        client_order_id = "0x" + secrets.token_hex(16)
        order = await client.place_order(
            OrderInput(
                symbol=symbol,
                side="BUY",
                type=OrderType.LIMIT,
                size="0.1",
                price=59_000,
                client_order_id=client_order_id,
            ),
            throw_on_order_reject=True,
        )
        print("Limit order confirmed:", order.hash, order.orders)

        ref = OrderRef(client_order_id=client_order_id)
        replacement_id = "0x" + secrets.token_hex(16)
        modified = await client.modify_order(
            ref,
            ModifyChanges(
                symbol=symbol, price=58_000, new_client_order_id=replacement_id
            ),
            throw_on_order_reject=True,
        )
        print("Modification confirmed:", modified.hash, modified.orders)

        cancelled = await client.cancel_order(
            OrderRef(client_order_id=replacement_id), throw_on_order_reject=True
        )
        print("Cancellation confirmed:", cancelled.hash, cancelled.orders)

        # The test account needs a net position and liquidity for the market close.
        closed = await client.close_position(
            symbol=symbol,
            size="ALL",
            order_type=OrderType.MARKET,
            throw_on_order_reject=True,
        )
        print("Close confirmed:", closed.hash, closed.orders)
    finally:
        await node.close()


if __name__ == "__main__":
    asyncio.run(main())

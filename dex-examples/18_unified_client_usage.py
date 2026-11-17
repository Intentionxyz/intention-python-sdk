# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unified client usage (illustrative; supply a funded signer before running)."""

from __future__ import annotations

from intention_sdk import IntentionClient
from intention_sdk.core.account import Account
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.types.enums import OrderPositionMode
from intention_sdk.transactions.order_intents import OrderInput, OrderType, TpSlLeg


async def trade(signer: Account) -> None:
    sdk = IntentionClient(
        signer=signer,
        node_url="http://127.0.0.1:8080/v1",
        relayer_url="http://127.0.0.1:3000",
        ws_url="ws://127.0.0.1:3000/ws",
    )
    trader = sdk.trader(
        sub_address=AccountAddress.from_str("0x0"),
        position_mode=OrderPositionMode.NET,
    )

    # Market metadata (including subticks_per_tick) is loaded lazily from the
    # relayer before this first order. price/size accept number or string.
    result = await trader.place_order(
        OrderInput(
            symbol="BTC-USDC",
            side="BUY",
            type=OrderType.LIMIT,
            size="0.01",
            price=60_000,
        ),
        timeout_secs=30,
    )
    print(result.hash, result.all_accepted, result.orders)

    # Entry + TP + SL are encoded as one grouped order transaction.
    await trader.place_order_with_tpsl(
        OrderInput(
            symbol="BTC-USDC",
            side="BUY",
            type=OrderType.MARKET,
            size=0.01,
        ),
        tp=TpSlLeg(
            type=OrderType.TAKE_PROFIT_MARKET,
            trigger_price="65000",
        ),
        sl=TpSlLeg(
            type=OrderType.STOP_MARKET,
            trigger_price="57000",
        ),
        preflight="full",
    )

    # The submit_* fast path returns after node acceptance without polling.
    pending = await trader.submit_order(
        OrderInput(
            symbol="BTC-USDC",
            side="SELL",
            type=OrderType.LIMIT,
            size="0.01",
            price="70000",
        )
    )
    print(pending.hash)
    await sdk.close()


if __name__ == "__main__":
    raise SystemExit("Import trade(signer) and pass a funded Account")

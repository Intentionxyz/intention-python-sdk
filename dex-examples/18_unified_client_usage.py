# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unified-client usage corresponding to the TypeScript unified client example."""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Optional

from intention_sdk import (
    Account,
    AccountAddress,
    ClientConfig,
    IntentionClient,
    Network,
    OrderInput,
    OrderType,
)
from intention_sdk.core.address_utils import MAIN_SUB_ADDRESS

from account_client_usage import create_subaccount_example


def create_client(
    *,
    signer: Account,
    node_url: str,
    relayer_url: str,
    ws_url: Optional[str] = None,
) -> IntentionClient:
    return IntentionClient(
        network=Network.CUSTOM,
        signer=signer,
        node_url=node_url,
        relayer_url=relayer_url,
        ws_url=ws_url,
        client_config=ClientConfig(trust_env=False),
    )


async def trade_example(sdk: IntentionClient, sub_address: AccountAddress) -> str:
    # trader() is synchronous. The first trading action loads the market and position mode.
    trader = sdk.trader(sub_address=sub_address)
    result = await trader.place_order(
        OrderInput(
            symbol="BTC-USDC",
            side="BUY",
            type=OrderType.LIMIT,
            price=60_000,
            size="0.01",
        ),
        throw_on_order_reject=True,
    )
    return result.hash


async def account_example(sdk: IntentionClient, sub_address: AccountAddress) -> None:
    """Set leverage for a funded subaccount."""
    trader = sdk.trader(sub_address=sub_address)
    await trader.set_leverage([{"symbol": "BTC-USDC", "leverage": 10}])


def configured_client(signer: Account) -> IntentionClient:
    from _common import get_dex_rest_api_url, get_node_url

    relayer_url = get_dex_rest_api_url()
    if not relayer_url:
        raise ValueError(
            "Set DEX_REST_API_URL (or DEX_REST_URL) to the Relayer base URL"
        )
    return create_client(
        signer=signer,
        node_url=get_node_url(),
        relayer_url=relayer_url,
        ws_url=os.getenv("WS_URL"),
    )


async def trade(
    signer: Account, sub_address: AccountAddress = MAIN_SUB_ADDRESS
) -> None:
    sdk = configured_client(signer)
    try:
        print("Order confirmed:", await trade_example(sdk, sub_address))
    finally:
        await sdk.close()


async def main() -> None:
    from _common import load_account_from_env

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("trade", "account"), nargs="?", default="trade"
    )
    parser.add_argument(
        "--name", default="trading", help="Unique name for a new subaccount"
    )
    parser.add_argument(
        "--sub-address",
        type=AccountAddress.from_str_relaxed,
        help="Funded subaccount for a trade or for setting leverage",
    )
    args = parser.parse_args()

    if args.action == "trade":
        await trade(load_account_from_env(), args.sub_address or MAIN_SUB_ADDRESS)
        return

    sdk = configured_client(load_account_from_env())
    try:
        if args.sub_address is None:
            sub_address = await create_subaccount_example(sdk.accounts, args.name)
            if sub_address is None:
                raise RuntimeError("Transaction did not emit CreateSubAccountEvent")
            print("Created subaccount:", sub_address)
        else:
            await account_example(sdk, args.sub_address)
            print("Leverage set on subaccount:", args.sub_address)
    finally:
        await sdk.close()


if __name__ == "__main__":
    asyncio.run(main())

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Query market history and optional account data without submitting transactions."""

from __future__ import annotations

import asyncio
import os
from typing import Mapping, Optional, Union

import httpx

from _common import (
    TEST_SYMBOL_ID,
    direct_async_client,
    get_dex_api_url,
    get_dex_rest_api_url,
    get_node_url,
    load_account_from_env,
)
from intention_sdk import AccountAddress


async def show_query(
    client: httpx.AsyncClient,
    name: str,
    url: str,
    params: Optional[Mapping[str, Union[str, int]]] = None,
) -> bool:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("code") not in (None, 0):
            raise ValueError(payload.get("message", payload["code"]))
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[FAIL] {name}: {exc}")
        return False

    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    candles = data.get("candles") if isinstance(data, dict) else None
    if isinstance(candles, list):
        print(f"[OK] {name}: {len(candles)} candles")
        if candles:
            latest = candles[0]
            print(
                f"     Latest candle opened at {latest['startedAt']}, close {latest['close']}"
            )
    else:
        print(f"[OK] {name}")
    return True


async def main() -> int:
    relayer = get_dex_rest_api_url()
    if not relayer:
        raise SystemExit(
            "Set DEX_REST_API_URL (or DEX_REST_URL) to the Relayer base URL"
        )

    market = os.getenv("SYMBOL") or {0: "BTC-USDC", 1: "ETH-USDC"}.get(TEST_SYMBOL_ID)
    if not market:
        raise SystemExit("Set SYMBOL to a market ticker such as BTC-USDC")

    owner = os.getenv("ACCOUNT_ADDRESS")
    if owner:
        owner = str(AccountAddress.from_str_relaxed(owner))
    elif os.getenv("PRIVATE_KEY"):
        owner = str(load_account_from_env().account_address)

    candle_url = f"{relayer}/v1/candles/perpetualMarkets/{market}"
    queries: list[tuple[str, str, Optional[Mapping[str, Union[str, int]]]]] = [
        ("Perpetual markets", f"{relayer}/v1/perpetualMarkets", None),
        ("Order book", f"{relayer}/v1/orderbooks/perpetualMarket/{market}", None),
        ("1-minute candles", candle_url, {"resolution": "1m", "limit": 10}),
    ]

    if owner:
        address = {"address": owner}
        queries.extend(
            [
                ("Open orders", f"{relayer}/v1/orders", address),
                ("Order history", f"{relayer}/v1/orderHistory", address),
                ("Fills", f"{relayer}/v1/fills", address),
                (
                    "Trade history",
                    f"{relayer}/v1/tradeHistory",
                    {**address, "limit": 10},
                ),
                ("Positions", f"{relayer}/v1/perpetualPositions", address),
                ("Transfers", f"{relayer}/v1/transfers", address),
                ("Funding payments", f"{relayer}/v1/fundingPayments", address),
                ("Subaccount balances", f"{relayer}/v1/addresses/{owner}", None),
            ]
        )

    node_configured = any(
        os.getenv(key)
        for key in ("INTENTION_NODE_URL", "INTENTION_NODE_API_URL", "FULLNODE_URL")
    )
    if node_configured or os.getenv("DEX_API_URL"):
        dex = get_dex_api_url()
        queries.append(("Node perpetuals", f"{dex}/perpetuals", None))
        if owner:
            queries.extend(
                [
                    ("Agent list", f"{dex}/agents/{owner}", None),
                    ("Node DEX accounts", f"{dex}/accounts/{owner}", None),
                ]
            )

    tx_hash = os.getenv("TX_HASH")
    if tx_hash and not node_configured:
        raise SystemExit("Set INTENTION_NODE_URL (or FULLNODE_URL) when using TX_HASH")
    if node_configured:
        node = get_node_url().rstrip("/")
        queries.append(
            (
                "Index price",
                f"{node}/oracle/prices",
                {"symbol": market, "type": "IndexPrice"},
            )
        )
        if tx_hash:
            queries.append(
                ("Transaction by hash", f"{node}/transactions/by_hash/{tx_hash}", None)
            )

    async with direct_async_client() as client:
        successful = 0
        for name, url, params in queries:
            successful += await show_query(client, name, url, params)

    print(f"{successful}/{len(queries)} queries succeeded")
    return int(successful != len(queries))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

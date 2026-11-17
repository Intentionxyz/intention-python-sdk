# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
14 - DEX REST API Data Query Endpoints Test

Covers all DEX REST API query endpoints used by the trading-web frontend

Environment variables:
  DEX_REST_API_URL  -- New REST API base URL
  DEX_API_URL       -- Legacy DEX API URL
  INTENTION_NODE_URL -- Fullnode URL

Run: python dex-examples/14_dex_rest_queries.py
"""

import asyncio
import json

import httpx

from _common import (
    TEST_SYMBOL_ID,
    get_dex_api_url,
    get_dex_rest_api_url,
    get_fullnode_base,
    get_node_url,
    get_or_create_account,
    print_env_info,
    print_header,
)

from intention_sdk.api.client import RestClient

# ===== Utility functions =====

SYMBOL_ID_TO_TICKER = {0: "BTC-USDC", 1: "ETH-USDC"}


def get_default_market_ticker() -> str:
    return SYMBOL_ID_TO_TICKER.get(TEST_SYMBOL_ID, "BTC-USD")


async def query_endpoint(name: str, url: str) -> dict:
    """Generic GET request with unified success/failure handling"""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            if not response.is_success:
                body = response.text[:200]
                return {"name": name, "url": url, "ok": False, "status": response.status_code, "data": None, "error": f"{response.status_code}: {body}"}
            data = response.json()
            return {"name": name, "url": url, "ok": True, "status": response.status_code, "data": data}
    except Exception as err:
        return {"name": name, "url": url, "ok": False, "status": 0, "data": None, "error": str(err)}


def print_result(result: dict) -> None:
    """Print query result summary"""
    icon = "OK" if result["ok"] else "FAIL"
    print(f"\n[{icon}] {result['name']}")
    print(f"  URL: {result['url']}")

    if not result["ok"]:
        print(f"  Error: {result['error']}")
        return

    data = result["data"]
    if data is None:
        print("  Response: (empty)")
        return

    # Print first 300 characters of JSON
    text = json.dumps(data)
    print(f"  Response: {text[:300]}{'...' if len(text) > 300 else ''}")


async def main():
    print("====================================")
    print("  14 - DEX REST API Data Query Endpoints Test")
    print("====================================\n")

    rest_client = RestClient(get_node_url())
    account = await get_or_create_account(rest_client)
    owner_addr = str(account.account_address)
    print_env_info()
    print("Account address:", owner_addr)

    dex_rest_url = get_dex_rest_api_url()
    dex_api_url = get_dex_api_url()
    fullnode_base = get_fullnode_base()

    print("\nAPI endpoint configuration:")
    print("  DEX REST API (new):", dex_rest_url or "(not configured)")
    print("  DEX API (legacy):", dex_api_url or "(not configured)")
    print("  Fullnode:", fullnode_base or "(not configured)")

    market_ticker = get_default_market_ticker()
    print("  Test market:", market_ticker, f"(symbol_id={TEST_SYMBOL_ID})")

    results = []

    # ==============================
    # A. New DEX REST API Endpoints
    # ==============================

    if dex_rest_url:
        print_header("A. DEX REST API Endpoints (new)")

        endpoints = [
            ("A1. Perpetual market config", f"{dex_rest_url}/v1/perpetualMarkets"),
            ("A2. Order book query", f"{dex_rest_url}/v1/orderbooks/perpetualMarket/{market_ticker}"),
            ("A3. Candlestick data query", f"{dex_rest_url}/v1/candles/perpetualMarkets/{market_ticker}?resolution=1MIN&limit=10"),
            ("A4. Active orders query", f"{dex_rest_url}/v1/orders?address={owner_addr}&status=OPEN,PARTIALLY_FILLED"),
            ("A5. Order history query", f"{dex_rest_url}/v1/orderHistory?address={owner_addr}"),
            ("A6. Fill records query", f"{dex_rest_url}/v1/fills?address={owner_addr}"),
            ("A7. Trade history query", f"{dex_rest_url}/v1/tradeHistory?address={owner_addr}&limit=10"),
            ("A8. Perpetual positions query", f"{dex_rest_url}/v1/perpetualPositions?address={owner_addr}&subaccountNumber=0"),
            ("A9. Transfer records query", f"{dex_rest_url}/v1/transfers?address={owner_addr}"),
            ("A10. Funding rate records query", f"{dex_rest_url}/v1/fundingPayments?address={owner_addr}"),
            ("A11. Sub-account balance query", f"{dex_rest_url}/v1/addresses/{owner_addr}"),
        ]

        for name, url in endpoints:
            result = await query_endpoint(name, url)
            print_result(result)
            results.append(result)

        print_header("A12. Query Order by Transaction Hash (example)")
        print("  Endpoint: GET /v1/dex/orders/by_txn_hash/{txHash}")
        print("  Skipped: requires a valid txHash")
    else:
        print("\nDEX_REST_API_URL not configured, skipping new REST API endpoint tests")

    # ==============================
    # B. Legacy DEX API Endpoints
    # ==============================

    if dex_api_url:
        print_header("B. DEX API Endpoints (legacy)")

        legacy_endpoints = [
            ("B1. Agent list query", f"{dex_api_url}/agents/{owner_addr}"),
            ("B2. Perpetual config query", f"{dex_api_url}/perpetuals"),
            ("B3. Sub-account info query", f"{dex_api_url}/accounts/{owner_addr}"),
        ]

        for name, url in legacy_endpoints:
            result = await query_endpoint(name, url)
            print_result(result)
            results.append(result)
    else:
        print("\nDEX_API_URL not configured, skipping legacy API endpoint tests")

    # ==============================
    # C. Fullnode DEX Endpoints
    # ==============================

    if fullnode_base:
        print_header("C. Fullnode DEX Endpoints")

        fullnode_endpoints = [
            ("C1. Mark price query", f"{fullnode_base}/v1/dex/mark_prices"),
            ("C2. DEX sub-account query", f"{fullnode_base}/v1/dex/accounts/{owner_addr}"),
        ]

        for name, url in fullnode_endpoints:
            result = await query_endpoint(name, url)
            print_result(result)
            results.append(result)
    else:
        print("\nINTENTION_NODE_URL not configured, skipping fullnode DEX endpoint tests")

    # ==============================
    # Summary
    # ==============================

    print_header("Query Results Summary")

    succeeded = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    print(f"Total: {len(results)} endpoints")
    print(f"  Succeeded: {len(succeeded)}")
    print(f"  Failed: {len(failed)}")

    if failed:
        print("\nFailed endpoints:")
        for r in failed:
            print(f"  - {r['name']}: {r['error']}")

    print("\nCovered endpoints list:")
    print("  [New DEX REST API]")
    print("    GET /v1/perpetualMarkets          -- Market config")
    print("    GET /v1/orderbooks/perpetualMarket -- Order book")
    print("    GET /v1/candles/perpetualMarkets   -- Candlestick data")
    print("    GET /v1/orders                     -- Active orders")
    print("    GET /v1/orderHistory               -- Order history")
    print("    GET /v1/fills                      -- Fill records")
    print("    GET /v1/tradeHistory               -- Trade history")
    print("    GET /v1/perpetualPositions          -- Position query")
    print("    GET /v1/transfers                  -- Transfer records")
    print("    GET /v1/fundingPayments            -- Funding rates")
    print("    GET /v1/addresses                  -- Sub-account balance")
    print("    GET /v1/dex/orders/by_txn_hash     -- Query order by hash")
    print("  [Legacy DEX API]")
    print("    GET /agents/:address               -- Agent list")
    print("    GET /perpetuals                    -- Perpetual config")
    print("    GET /accounts/:address             -- Sub-account info")
    print("  [Fullnode DEX]")
    print("    GET /v1/dex/mark_prices            -- Mark prices")
    print("    GET /v1/dex/accounts/:address      -- DEX sub-accounts")

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

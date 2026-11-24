# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared configuration and helpers for the SDK examples."""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import secrets
import sys
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:

    def load_dotenv(*args, **kwargs):
        return False


# Ensure intention_sdk can be imported (project root directory)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from intention_sdk.core.account import Secp256k1PrivateKey  # noqa: E402
from intention_sdk.core.account import Account  # noqa: E402
from intention_sdk.core.account_address import AccountAddress  # noqa: E402
from intention_sdk.core.address_utils import (
    MAIN_SUB_ADDRESS,
    derive_subaccount_address,
)  # noqa: E402
from intention_sdk.api.client import (
    ClientConfig,
    FaucetClient,
    RestClient,
)  # noqa: E402
from intention_sdk.api.intention_client import IntentionClient  # noqa: E402
from intention_sdk.transactions.order_intents import OrderInput, OrderType  # noqa: E402
from intention_sdk.transactions.dex_payloads import DexOrderlessTx  # noqa: E402
from intention_sdk.transactions import (  # noqa: E402
    RawTransaction,
    TransactionPayload,
)

load_dotenv()


# ===== Address utilities =====


def normalize_address(addr: str) -> str:
    """Pad API-returned short address to standard 64-char format (0x + 64 hex chars)"""
    addr = addr.lower().strip()
    if addr.startswith("0x"):
        addr = addr[2:]
    return "0x" + addr.zfill(64)


# ===== Network configuration =====


def get_node_url() -> str:
    return (
        os.getenv("INTENTION_NODE_URL")
        or os.getenv("INTENTION_NODE_API_URL")
        or os.getenv("FULLNODE_URL")
        or "http://127.0.0.1:8080/v1"
    )


def get_faucet_url() -> str:
    return (
        os.getenv("INTENTION_FAUCET_URL")
        or os.getenv("INTENTION_FAUCET_API_URL")
        or "http://127.0.0.1:8081"
    )


def get_dex_rest_api_url() -> str:
    """Relayer base URL, without /v1."""
    return (os.getenv("DEX_REST_API_URL") or os.getenv("DEX_REST_URL") or "").rstrip(
        "/"
    )


def get_dex_api_url() -> str:
    """DEX API base URL (legacy, fullnode /v1/dex)"""
    explicit = os.getenv("DEX_API_URL")
    if explicit:
        return explicit.rstrip("/")
    fullnode = re.sub(r"/v1/?$", "", get_node_url())
    return f"{fullnode}/v1/dex" if fullnode else ""


def get_fullnode_base() -> str:
    """Fullnode base URL (strip trailing /v1)"""
    return re.sub(r"/v1/?$", "", get_node_url())


def create_rest_client() -> RestClient:
    return RestClient(get_node_url(), ClientConfig(trust_env=False))


@contextlib.asynccontextmanager
async def direct_async_client(timeout: float = 30.0):
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        yield client


# ===== Account utilities =====


def load_account_from_env(env_key: str = "PRIVATE_KEY") -> Account:
    """Load a Secp256k1 account from environment variable (EVM address derivation)"""
    hex_key = os.getenv(env_key)
    if not hex_key:
        raise RuntimeError(
            f"Environment variable {env_key} is not set (requires hex-format Secp256k1 private key)"
        )
    return Account.from_private_key(Secp256k1PrivateKey.from_hex(hex_key))


async def get_or_create_account(rest_client: RestClient) -> Account:
    """Get test account: import from PRIVATE_KEY if set, otherwise auto-generate and fund"""
    if os.getenv("PRIVATE_KEY"):
        print("Importing account from PRIVATE_KEY environment variable")
        return load_account_from_env()
    print(
        "PRIVATE_KEY not set, auto-generating new account and requesting faucet funding..."
    )
    account = Account.generate()
    print("New account address:", account.account_address)
    faucet_client = FaucetClient(get_faucet_url(), rest_client)
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            await faucet_client.fund_account(account.account_address, 500_000_000)
            print("Faucet funding complete: 5 native coins")
            break
        except Exception as e:
            if attempt < max_retries:
                print(
                    f"Faucet funding failed (attempt {attempt}): {e}, retrying in {2 * attempt}s..."
                )
                await asyncio.sleep(2 * attempt)
            else:
                raise RuntimeError(
                    f"Faucet funding failed (after {max_retries} retries): {e}"
                ) from e
    return account


# ===== Sub-account address utilities =====


def get_sub_address(account: Account, subaccount_number: int) -> AccountAddress:
    """Get sub-account address: 0 returns MAIN_SUB_ADDRESS, >0 calls derivation function"""
    if subaccount_number == 0:
        return MAIN_SUB_ADDRESS
    return derive_subaccount_address(account.account_address, subaccount_number)


# ===== DEX business constants (overridable via environment variables) =====

TEST_SYMBOL_ID = int(os.getenv("TEST_SYMBOL_ID", "0"))
TEST_ASSET_ID = int(os.getenv("TEST_ASSET_ID", "0"))
TEST_SUBACCOUNT_ID = int(os.getenv("TEST_SUBACCOUNT_ID", "0"))


@contextlib.asynccontextmanager
async def trading_example():
    """Open a trader for a funded test signer and load the selected market."""
    relayer = get_dex_rest_api_url()
    if not relayer:
        raise RuntimeError(
            "Set DEX_REST_API_URL (or DEX_REST_URL) to the Relayer base URL"
        )

    signer = load_account_from_env()
    sdk = IntentionClient(
        signer=signer,
        node_url=get_node_url(),
        relayer_url=relayer,
        client_config=ClientConfig(trust_env=False),
    )
    try:
        resolver = await sdk.markets.get_resolver()
        symbol = os.getenv("SYMBOL")
        if symbol is None:
            symbol = next(
                (
                    name
                    for name in resolver.symbols()
                    if resolver.symbol_id(name) == TEST_SYMBOL_ID
                ),
                None,
            )
        if not symbol or not resolver.has(symbol):
            raise ValueError("Select an active market with SYMBOL or TEST_SYMBOL_ID")
        subaccount = int(
            os.getenv("SUBACCOUNT") or os.getenv("TEST_SUBACCOUNT_ID") or "0"
        )
        trader = sdk.trader(
            sub_address=get_sub_address(signer, subaccount), resolver=resolver
        )
        yield trader, symbol
    finally:
        await sdk.close()


async def get_example_market_price(symbol: str) -> Decimal:
    async with direct_async_client() as client:
        response = await client.get(f"{get_dex_rest_api_url()}/v1/perpetualMarkets")
        response.raise_for_status()
        payload = response.json()
    market = payload.get("data", payload)["markets"][symbol]
    price = Decimal(str(market.get("markPrice") or market.get("oraclePrice") or "0"))
    if not price.is_finite() or price <= 0:
        raise ValueError(f"Market {symbol} needs a positive mark or oracle price")
    return price


def example_limit_buy(symbol: str, price: Decimal) -> OrderInput:
    return OrderInput(
        symbol=symbol,
        side="BUY",
        type=OrderType.LIMIT,
        price=str(price),
        size=os.getenv("SIZE", "0.01"),
        post_only=True,
        client_order_id="0x" + secrets.token_hex(16),
    )


# ===== DEX utilities =====


async def build_and_submit_dex_orderless(
    rest_client: RestClient,
    account: Account,
    dex_orderless_tx: DexOrderlessTx,
    encoding: Optional[str] = None,
    replay_protection_nonce: Optional[int] = None,
) -> Dict[str, Any]:
    """Complete DEX Orderless transaction build-sign-submit flow"""
    payload = TransactionPayload(dex_orderless_tx)
    chain_id = await rest_client.chain_id()
    config = rest_client.client_config
    expiration = int(time.time()) + config.expiration_ttl

    if replay_protection_nonce is None:
        raw_tx = RawTransaction.create_orderless(
            sender=account.account_address,
            payload=payload,
            max_gas_amount=config.max_gas_amount,
            gas_unit_price=config.gas_unit_price,
            expiration_timestamp_secs=expiration,
            chain_id=chain_id,
        )
    else:
        raw_tx = RawTransaction.create_cross_transfer_orderless(
            sender=account.account_address,
            payload=payload,
            replay_protection_nonce=replay_protection_nonce,
            max_gas_amount=config.max_gas_amount,
            gas_unit_price=config.gas_unit_price,
            expiration_timestamp_secs=expiration,
            chain_id=chain_id,
        )

    authenticator = account.sign_transaction_with_authenticator(raw_tx)
    tx_hash = await rest_client.submit_transaction(
        raw_tx, authenticator, encoding=encoding
    )
    await rest_client.wait_for_transaction(tx_hash)

    return {"hash": tx_hash, "success": True}


# ===== DEX sub-account queries =====


async def get_dex_sub_accounts(address: str) -> List[Dict[str, Any]]:
    """Query sub-account balance info via fullnode DEX API"""
    fullnode_url = get_fullnode_base()
    if not fullnode_url:
        return []
    try:
        url = f"{fullnode_url}/v1/dex/accounts/{address}"
        async with direct_async_client() as client:
            response = await client.get(url)
            if not response.is_success:
                return []
            data = response.json()
            return data.get("accounts", [])
    except Exception:
        return []


async def probe_dex_rest_api() -> Dict[str, Any]:
    base_url = get_dex_rest_api_url()
    if not base_url:
        return {
            "ok": False,
            "endpoint": "(DEX_REST_API_URL not set)",
            "status": None,
            "error": "DEX_REST_API_URL is required",
        }

    endpoint = f"{base_url}/v1/perpetualMarkets"
    try:
        async with direct_async_client() as client:
            response = await client.get(endpoint)
        return {
            "ok": response.is_success,
            "endpoint": endpoint,
            "status": response.status_code,
            "error": response.text if not response.is_success else None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "endpoint": endpoint,
            "status": None,
            "error": str(exc),
        }


async def run_live_preflight() -> Dict[str, Any]:
    configured_urls = {
        "INTENTION_NODE_URL": (
            os.getenv("INTENTION_NODE_URL")
            or os.getenv("INTENTION_NODE_API_URL")
            or os.getenv("FULLNODE_URL")
        ),
        "DEX_REST_API_URL": get_dex_rest_api_url(),
    }
    checks: List[Dict[str, Any]] = []

    missing = [name for name, value in configured_urls.items() if not value]
    for name, value in configured_urls.items():
        checks.append(
            {
                "name": f"{name} present",
                "ok": name not in missing,
                "detail": value or "missing",
            }
        )

    result: Dict[str, Any] = {
        "ok": not missing,
        "required_env": list(configured_urls),
        "node_url": configured_urls["INTENTION_NODE_URL"],
        "dex_rest_api_url": configured_urls["DEX_REST_API_URL"],
        "account_source": None,
        "account_address": None,
        "account": None,
        "checks": checks,
    }
    if missing:
        return result

    rest_client = create_rest_client()
    try:
        try:
            account = await get_or_create_account(rest_client)
        except Exception as exc:
            result["ok"] = False
            checks.append({"name": "test account", "ok": False, "detail": str(exc)})
            return result
        result["account"] = account
        result["account_source"] = (
            "PRIVATE_KEY" if os.getenv("PRIVATE_KEY") else "generated+faucet"
        )
        result["account_address"] = str(account.account_address)

        try:
            info = await rest_client.info()
            checks.append(
                {
                    "name": "node info",
                    "ok": True,
                    "detail": f"chain_id={info.get('chain_id', '?')}",
                }
            )
        except Exception as exc:
            result["ok"] = False
            checks.append({"name": "node info", "ok": False, "detail": str(exc)})

        dex_probe = await probe_dex_rest_api()
        checks.append(
            {
                "name": "DEX REST API",
                "ok": dex_probe["ok"],
                "detail": (
                    f"{dex_probe['endpoint']} status={dex_probe['status']}"
                    if dex_probe["ok"]
                    else f"{dex_probe['endpoint']}: {dex_probe['error']}"
                ),
            }
        )
        result["ok"] = bool(result["ok"] and dex_probe["ok"])
        return result
    finally:
        await rest_client.close()


async def bootstrap_enhanced_lane(
    rest_client: RestClient,
    account: Account,
    preferred_symbol_id: Optional[int] = None,
    preferred_subaccount_id: Optional[int] = None,
) -> Dict[str, Any]:
    symbol_id = (
        preferred_symbol_id
        if preferred_symbol_id is not None
        else await get_perpetual_market_symbol_id()
    )
    account_info = await get_primary_dex_account(str(account.account_address))
    if account_info is None:
        raise RuntimeError(
            "No tradable DEX account found; run setup/funding before enhanced lane"
        )

    subaccount_number = preferred_subaccount_id
    if subaccount_number is None:
        subaccount_number = int(
            account_info.get("subaccount_number", TEST_SUBACCOUNT_ID)
        )

    sub_address_value = account_info.get("sub_address")
    if sub_address_value:
        sub_address = AccountAddress.from_str(normalize_address(sub_address_value))
    else:
        sub_address = get_sub_address(account, subaccount_number)

    return {
        "symbol_id": symbol_id,
        "subaccount_number": subaccount_number,
        "sub_address": sub_address,
        "available_margin": int(account_info.get("available_margin", 0) or 0),
        "leverage_hash": "existing-live-state",
    }


async def get_primary_dex_account(address: str) -> Optional[Dict[str, Any]]:
    """Return the most relevant live tradable DEX account for this wallet."""
    accounts = await get_dex_sub_accounts(address)
    if not accounts:
        return None

    def account_key(account: Dict[str, Any]) -> tuple:
        margin = int(account.get("available_margin", 0) or 0)
        assets = account.get("assets", []) or []
        has_assets = 1 if assets else 0
        return (margin, has_assets)

    return max(accounts, key=account_key)


async def get_perpetual_market_symbol_id(ticker: str = "ETH-USDC") -> int:
    """Resolve a live perpetual market id, preferring relayer metadata."""
    relayer_url = get_dex_rest_api_url()
    if relayer_url:
        try:
            async with direct_async_client() as client:
                response = await client.get(f"{relayer_url}/v1/perpetualMarkets")
                if response.is_success:
                    payload = response.json()
                    markets = payload.get("data", {}).get("markets", {})
                    market = markets.get(ticker)
                    if isinstance(market, dict):
                        clob_pair_id = market.get("clobPairId")
                        if clob_pair_id is not None:
                            return int(clob_pair_id)
        except Exception:
            pass
    return TEST_SYMBOL_ID


def get_optional_int_env(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc

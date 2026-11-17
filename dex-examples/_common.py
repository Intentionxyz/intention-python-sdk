# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Shared utility module -- common code for all test scripts

Usage: from _common import get_client, load_account_from_env, ...
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import py_compile
import random
import re
import sys
import time
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
from intention_sdk.core.address_utils import MAIN_SUB_ADDRESS, derive_subaccount_address  # noqa: E402
from intention_sdk.api.client import ClientConfig, FaucetClient, RestClient  # noqa: E402
from intention_sdk.transactions.dex_payloads import (  # noqa: E402
    DexOrderlessTx,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexTx,
    DexUserConfigTx,
    SetUserLeverage,
    UserSymbolLeverage,
)
from intention_sdk.types.enums import (  # noqa: E402
    ConditionType,
    CreatedBy,
    DexOrderlessTxVariant,
    DexOrdersVariant,
    DexUserConfigTxVariant,
    OrderBasicType,
    OrderPositionMode,
    Side,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)
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
        or "http://127.0.0.1:8080/v1"
    )


def get_faucet_url() -> str:
    return (
        os.getenv("INTENTION_FAUCET_URL")
        or os.getenv("INTENTION_FAUCET_API_URL")
        or "http://127.0.0.1:8081"
    )


def get_dex_rest_api_url() -> str:
    """DEX REST API base URL (new version)"""
    return os.getenv("DEX_REST_API_URL", "").rstrip("/")


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


def get_network() -> str:
    return os.getenv("INTENTION_NETWORK", "custom")


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
        raise RuntimeError(f"Environment variable {env_key} is not set (requires hex-format Secp256k1 private key)")
    private_key = Secp256k1PrivateKey.from_hex(hex_key)
    public_key = private_key.public_key()
    evm_bytes = public_key.to_evm_account_bytes()
    address = AccountAddress(evm_bytes)
    return Account(address, private_key)


def generate_secp256k1_account() -> Account:
    """Generate a new Secp256k1 account"""
    return Account.generate()


async def get_or_create_account(rest_client: RestClient) -> Account:
    """Get test account: import from PRIVATE_KEY if set, otherwise auto-generate and fund"""
    if os.getenv("PRIVATE_KEY"):
        print("Importing account from PRIVATE_KEY environment variable")
        return load_account_from_env()
    print("PRIVATE_KEY not set, auto-generating new account and requesting faucet funding...")
    account = generate_secp256k1_account()
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
                print(f"Faucet funding failed (attempt {attempt}): {e}, retrying in {2 * attempt}s...")
                await asyncio.sleep(2 * attempt)
            else:
                raise RuntimeError(f"Faucet funding failed (after {max_retries} retries): {e}") from e
    return account


# ===== Sub-account address utilities =====


def get_sub_address(account: Account, subaccount_number: int) -> AccountAddress:
    """Get sub-account address: 0 returns MAIN_SUB_ADDRESS, >0 calls derivation function"""
    if subaccount_number == 0:
        return MAIN_SUB_ADDRESS
    return derive_subaccount_address(account.account_address, subaccount_number)


# ===== DEX business constants (overridable via environment variables) =====

TEST_SYMBOL_ID = int(os.getenv("TEST_SYMBOL_ID", "1"))
TEST_ASSET_ID = int(os.getenv("TEST_ASSET_ID", "0"))
TEST_SUBACCOUNT_ID = int(os.getenv("TEST_SUBACCOUNT_ID", "1"))
TEST_ORDER_ID = int(os.getenv("ORDER_ID", "1"))

_test_symbol_id_2 = os.getenv("TEST_SYMBOL_ID_2")
TEST_SYMBOL_ID_2: Optional[int] = int(_test_symbol_id_2) if _test_symbol_id_2 else None


# ===== DEX utilities =====


def generate_nonce() -> int:
    """Generate nonce (microsecond-level timestamp + random number)"""
    return int(time.time() * 1000) * 1000 + random.randint(0, 999)


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


# ===== Transaction query utilities =====


async def fetch_transaction_by_hash(tx_hash: str) -> Dict[str, Any]:
    """Fetch transaction details via fullnode API"""
    fullnode_url = get_fullnode_base()
    if not fullnode_url:
        raise RuntimeError("INTENTION_NODE_URL is not set, cannot query transaction details")
    url = f"{fullnode_url}/v1/transactions/by_hash/{tx_hash}"
    async with direct_async_client() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def fetch_open_order_ids(address: str, limit: int = 1) -> List[int]:
    """Read active order_ids directly from on-chain DexUserState resource.

    On-chain state updates immediately after transaction confirmation, with no indexing delay.
    """
    fullnode_url = get_fullnode_base()
    if not fullnode_url:
        return []
    try:
        url = (
            f"{fullnode_url}/v1/accounts/{address}"
            f"/resource/0x1::dex_state::DexUserState"
        )
        async with direct_async_client() as client:
            response = await client.get(url)
            if not response.is_success:
                return []
            body = response.json()
            raw_ids = body.get("data", {}).get("order_ids", [])
            return [int(oid) for oid in raw_ids][:limit]
    except Exception:
        return []


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


# ===== Trading volume accumulation utilities =====


async def _get_mark_price(symbol_id: int) -> float:
    """Query mark price"""
    defaults = {0: 67550, 1: 2025}
    try:
        url = f"{get_fullnode_base()}/v1/dex/mark_prices"
        async with direct_async_client() as client:
            resp = await client.get(url)
            if resp.is_success:
                data = resp.json()
                for p in data.get("prices", []):
                    if p.get("symbol_id") == symbol_id:
                        return float(p["mark_price"])
    except Exception:
        pass
    return defaults.get(symbol_id, 2025)


async def get_mark_price(symbol_id: int) -> float:
    return await _get_mark_price(symbol_id)


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
    required_env = ["INTENTION_NODE_URL", "DEX_REST_API_URL"]
    checks: List[Dict[str, Any]] = []

    missing = [name for name in required_env if not os.getenv(name)]
    for name in required_env:
        checks.append(
            {
                "name": f"{name} present",
                "ok": name not in missing,
                "detail": os.getenv(name) or "missing",
            }
        )

    result: Dict[str, Any] = {
        "ok": not missing,
        "required_env": required_env,
        "node_url": os.getenv("INTENTION_NODE_URL")
        or os.getenv("INTENTION_NODE_API_URL"),
        "dex_rest_api_url": get_dex_rest_api_url(),
        "account_source": None,
        "account_address": None,
        "account": None,
        "checks": checks,
    }
    if missing:
        return result

    rest_client = create_rest_client()
    try:
        account = await get_or_create_account(rest_client)
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
    symbol_id = preferred_symbol_id or await get_perpetual_market_symbol_id()
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


async def _get_parent_volume(address: str) -> float:
    """Query account parent_volume_info trading volume (USD)"""
    fullnode_url = get_fullnode_base()
    if not fullnode_url:
        return 0.0
    try:
        url = f"{fullnode_url}/v1/dex/accounts/{address}"
        async with direct_async_client() as client:
            resp = await client.get(url)
            if not resp.is_success:
                return 0.0
            data = resp.json()
            # API returns {"accounts": [{"parent_volume_info": {"daily_buckets": [...]}}]}
            accounts = data.get("accounts", [])
            if not accounts:
                return 0.0
            vol_info = accounts[0].get("parent_volume_info", {})
            buckets = vol_info.get("daily_buckets", [])
            return sum(float(b.get("volume_usd", 0)) for b in buckets)
    except Exception:
        return 0.0


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


async def ensure_volume(
    rest_client: RestClient,
    account: Account,
    target_volume_usd: float = 100_000,
):
    """
    Accumulate trading volume by repeatedly opening/closing market positions until
    target_volume_usd is met.

    Strategy:
    1. Fund account via faucet for margin (~10,000 USDC)
    2. Set ETH-USDC (symbol_id=1) 10x leverage
    3. Loop: market buy large position -> market sell to close (IOC, reduce_only)
    4. Each round trip accumulates ~100k USD trading volume
    5. Query parent_volume_info to confirm target is met
    """
    addr_str = str(account.account_address)
    trading_account = await get_primary_dex_account(addr_str)
    if trading_account is None:
        raise RuntimeError(
            "No tradable DEX account found via /v1/dex/accounts/{address}; "
            "cannot bootstrap leverage or trading volume."
        )

    sub_address = AccountAddress.from_str(
        normalize_address(trading_account["sub_address"])
    )
    available_margin = int(trading_account.get("available_margin", 0) or 0)
    vol_symbol_id = await get_perpetual_market_symbol_id("ETH-USDC")
    print(
        "  Using tradable DEX account:",
        trading_account.get("sub_address"),
        f"(available_margin={available_margin / 1_000_000:.2f} USDC)",
    )
    print(f"  Using live market symbol_id/clobPairId: {vol_symbol_id}")

    # 1. Check current trading volume
    current_vol = await _get_parent_volume(addr_str)
    print(f"  Current volume: {current_vol:,.0f} USD (target: {target_volume_usd:,.0f})")
    if current_vol >= target_volume_usd:
        print("  Volume requirement already met, skipping")
        return

    # 2. Fund account for margin via faucet
    if available_margin < 20_000_000_000:
        print("  Funding account for margin via faucet (20,000 USDC)...")
        faucet_client = FaucetClient(get_faucet_url(), rest_client)
        await faucet_client.fund_account(account.account_address, 20_000_000_000)
        print("  Faucet funding complete: 200 native coins = ~20,000 USDC")
    else:
        print("  Existing available margin is sufficient, skipping faucet funding")

    # 3. Set 10x leverage
    print(f"  Setting ETH-USDC (symbol_id={vol_symbol_id}) 10x leverage...")
    leverage_info = [UserSymbolLeverage(vol_symbol_id, 10.0)]
    set_lev = SetUserLeverage(
        nonce=generate_nonce(),
        sub_address=sub_address,
        leverage_info=leverage_info,
    )
    config_tx = DexUserConfigTx(DexUserConfigTxVariant.SET_USER_LEVERAGE, set_lev)
    orderless_lev = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx)
    lev_result = await build_and_submit_dex_orderless(
        rest_client, account, orderless_lev
    )
    print(
        "  Leverage setting:",
        "SUCCESS" if lev_result["success"] else "FAILED",
        "hash:", lev_result["hash"],
    )

    # 4. Loop: buy + sell to close
    max_rounds = 5
    for round_num in range(1, max_rounds + 1):
        mark_price = await _get_mark_price(vol_symbol_id)
        # 25 ETH ~ 50k USD notional value
        position_quantums = 25_000_000_000
        # Market order: use mark price + 10% slippage as subticks
        buy_subticks = int(mark_price * 1.10) * 100_000
        sell_subticks = int(mark_price * 0.90) * 100_000

        print(f"  Round {round_num}: mark_price={mark_price}, position=25 ETH (~50k USD)")

        # Buy to open
        buy_order = DexPlaceOrder(
            sub_address=sub_address,
            symbol_id=vol_symbol_id,
            symbol_type=SymbolType.PERPETUAL,
            side=Side.BUY,
            quantums=position_quantums,
            subticks=buy_subticks,
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
        nonce_buy = generate_nonce()
        dex_orders_buy = DexOrders(
            DexOrdersVariant.PLACE, [DexPlaceOrders([buy_order])]
        )
        dex_tx_buy = DexTx(nonce_buy, dex_orders_buy, CreatedBy.USER)
        orderless_buy = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx_buy)
        buy_result = await build_and_submit_dex_orderless(
            rest_client, account, orderless_buy
        )
        print(
            f"    Buy: {'SUCCESS' if buy_result['success'] else 'FAILED'}",
            "hash:", buy_result["hash"],
        )

        await asyncio.sleep(1)

        # Sell to close (reduce_only)
        sell_order = DexPlaceOrder(
            sub_address=sub_address,
            symbol_id=vol_symbol_id,
            symbol_type=SymbolType.PERPETUAL,
            side=Side.SELL,
            quantums=position_quantums,
            subticks=sell_subticks,
            trigger_subticks=0,
            order_basic_type=OrderBasicType.MARKET,
            time_in_force=TimeInForce.IOC,
            condition_type=ConditionType.UNSPECIFIED,
            trigger_price_type=TriggerPriceType.LAST_PRICE,
            target_order_id=0,
            reduce_only=True,
            position_mode=OrderPositionMode.NET,
            slippage_tolerance_ppm=100000,
        )
        nonce_sell = generate_nonce()
        dex_orders_sell = DexOrders(
            DexOrdersVariant.PLACE, [DexPlaceOrders([sell_order])]
        )
        dex_tx_sell = DexTx(nonce_sell, dex_orders_sell, CreatedBy.USER)
        orderless_sell = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx_sell)
        sell_result = await build_and_submit_dex_orderless(
            rest_client, account, orderless_sell
        )
        print(
            f"    Sell: {'SUCCESS' if sell_result['success'] else 'FAILED'}",
            "hash:", sell_result["hash"],
        )

        await asyncio.sleep(1)

        # Check trading volume
        current_vol = await _get_parent_volume(addr_str)
        print(f"    Volume: {current_vol:,.0f} USD")
        if current_vol >= target_volume_usd:
            print(f"  Volume target met ({current_vol:,.0f} >= {target_volume_usd:,.0f})")
            return

    print(f"  Warning: after {max_rounds} rounds, volume is {current_vol:,.0f} USD, target may not be met")


# ===== Output utilities =====


def print_header(title: str) -> None:
    print(f"\n===== {title} =====")


def print_env_info() -> None:
    print("Network:", get_network())
    print("Fullnode:", get_node_url())
    print("Faucet:", get_faucet_url())


def print_live_example_intro(
    title: str,
    required_envs: Optional[List[str]] = None,
    optional_envs: Optional[List[str]] = None,
    notes: Optional[List[str]] = None,
) -> None:
    print(f"Mode: live example ({title})")
    if required_envs:
        print("Required env:", ", ".join(required_envs))
    if optional_envs:
        print("Optional env:", ", ".join(optional_envs))
    if notes:
        for note in notes:
            print("Note:", note)


def get_optional_int_env(name: str) -> Optional[int]:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


def ensure_python_source_compiles(path: str) -> None:
    py_compile.compile(path, doraise=True)


def print_dex_sub_accounts(sub_accounts: List[Dict[str, Any]]) -> None:
    if not sub_accounts:
        print("  (No DEX sub-account data)")
        return
    for sub in sub_accounts:
        number = sub.get("subaccount_number")
        label = f"Sub-account #{number}" if number is not None else f"Sub-account ({sub.get('sub_address', '?')})"
        print(f"  {label}:")
        print(f"    Address: {sub.get('sub_address', '?')}")
        margin = sub.get("available_margin", 0)
        print(f"    Available margin: {margin} quantums = {margin / 1_000_000} USDC")
        pos_mode = sub.get("position_mode", 0)
        print(f"    Position mode: {'Net' if pos_mode == 0 else 'Hedge'}")
        print(f"    Rates: taker={sub.get('taker_rate', 0)} maker={sub.get('maker_rate', 0)}")
        assets = sub.get("assets", [])
        if assets:
            print("    Assets:")
            for asset in assets:
                aid = asset.get("asset_id", -1)
                q = asset.get("quantums", 0)
                lbl = "USDC" if aid == 0 else f"asset_{aid}"
                display = f"{q} quantums = {q / 1_000_000} USDC" if aid == 0 else f"{q} quantums"
                print(f"      {lbl}: {display}")
        else:
            print("    Assets: (none)")
        perps = sub.get("perps", [])
        if perps:
            print("    Perpetual positions:")
            for perp in perps:
                print(f"      #{perp.get('perpetual_id', '?')}: long={perp.get('long_quantums', 0)} short={perp.get('short_quantums', 0)} margin_mode={perp.get('margin_mode', 0)}")
        leverage_infos = sub.get("leverage_infos", [])
        if leverage_infos:
            print("    Leverage:")
            for lev in leverage_infos:
                print(f"      symbol_{lev.get('symbol_id', '?')}: {lev.get('im_leverage', '?')}x (exp={lev.get('exponent', '?')})")


def print_txn_details(label: str, txn: Dict[str, Any]) -> None:
    print(f"{label}:")
    print("  Hash:", txn.get("hash", "?"))
    print("  Status:", "SUCCESS" if txn.get("success") else "FAILED")
    print("  VM Status:", txn.get("vm_status", "?"))
    print("  Gas used:", txn.get("gas_used", "?"))
    print("  Version:", txn.get("version", "?"))
    ts = txn.get("timestamp")
    if ts:
        from datetime import datetime, timezone

        dt = datetime.fromtimestamp(int(ts) / 1_000_000, tz=timezone.utc)
        print("  Timestamp:", dt.isoformat())

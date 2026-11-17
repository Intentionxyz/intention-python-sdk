#!/usr/bin/env python3
# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Official Intention live verification harness.

Run one explicit lane at a time:

- `--lane preflight` emits only `VERDICT: PRECHECK-READY` or `VERDICT: ENV-FAIL`
- `--lane minimal` emits only `VERDICT: PASS`, `VERDICT: ENV-FAIL`, or
  `VERDICT: LIVE-FAIL`
- `--lane enhanced` emits only `VERDICT: PASS`, `VERDICT: ENV-FAIL`, or
  `VERDICT: LIVE-FAIL`
- `--lane json-coverage` emits only `VERDICT: PASS` or `VERDICT: LIVE-FAIL`

Required env for preflight and the minimal lane:

- `INTENTION_NODE_URL`
- `DEX_REST_API_URL`

Optional bootstrap and operator context:

- `PRIVATE_KEY`
- `INTENTION_NETWORK`
- `INTENTION_FAUCET_URL`

Optional enhanced-lane inputs:

- `TEST_SYMBOL_ID`
- `TEST_SUBACCOUNT_ID`

The `json-coverage` lane is a captured-request e2e lane. It does not require a live
node or privileged roles; it verifies that every JSON-supported orderless payload
family reaches the `POST /transactions` HTTP boundary as `application/json`.
"""

from __future__ import annotations

import asyncio
import argparse
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:

    def load_dotenv(*args, **kwargs):
        return False

from _common import (
    build_and_submit_dex_orderless,
    generate_nonce,
    get_optional_int_env,
)
from _json_request_coverage import run_captured_json_request_coverage
from intention_sdk import (
    ConditionType,
    CreatedBy,
    DexOrderlessTx,
    DexOrderlessTxVariant,
    DexOrders,
    DexOrdersVariant,
    DexPlaceOrder,
    DexPlaceOrders,
    DexTx,
    OrderBasicType,
    OrderPositionMode,
    Side,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)

load_dotenv()

PRECHECK_READY_EXIT = 0
PASS_EXIT = 0
ENV_FAIL_EXIT = 2
LIVE_FAIL_EXIT = 3


def _print_preflight_details(result: dict) -> None:
    print("Lane: preflight")
    print("Required env:", ", ".join(result["required_env"]))
    print("Node URL:", result["node_url"] or "(not set)")
    print("DEX REST URL:", result["dex_rest_api_url"] or "(not set)")
    print("Account source:", result["account_source"] or "(unknown)")
    print(
        "Account address:",
        result["account_address"] or "(unavailable before account bootstrap)",
    )
    for check in result["checks"]:
        status = "OK" if check["ok"] else "FAIL"
        print(f"[{status}] {check['name']}: {check['detail']}")


def _emit_verdict(verdict: str, detail_lines: list[str], exit_code: int) -> int:
    for line in detail_lines:
        print(line)
    print(f"VERDICT: {verdict}")
    return exit_code


def _get_enhanced_symbol_id() -> Optional[int]:
    return get_optional_int_env("TEST_SYMBOL_ID")


def _get_enhanced_subaccount_id() -> Optional[int]:
    return get_optional_int_env("TEST_SUBACCOUNT_ID")


async def _run_preflight_lane() -> int:
    from _common import run_live_preflight

    result = await run_live_preflight()
    _print_preflight_details(result)
    if not result["ok"]:
        return _emit_verdict("ENV-FAIL", [], ENV_FAIL_EXIT)
    return _emit_verdict("PRECHECK-READY", [], PRECHECK_READY_EXIT)


async def _run_minimal_lane() -> int:
    from _common import create_rest_client, probe_dex_rest_api, run_live_preflight

    preflight = await run_live_preflight()
    _print_preflight_details(preflight)
    if not preflight["ok"]:
        return _emit_verdict("ENV-FAIL", [], ENV_FAIL_EXIT)

    rest_client = create_rest_client()
    account = preflight["account"]
    try:
        account_info = await rest_client.account(account.account_address)
        dex_probe = await probe_dex_rest_api()
        if not dex_probe["ok"]:
            return _emit_verdict(
                "LIVE-FAIL",
                [
                    "Lane: minimal",
                    (
                        "DEX REST probe failed after preflight via "
                        f"{dex_probe['endpoint']}: {dex_probe['error']}"
                    ),
                ],
                LIVE_FAIL_EXIT,
            )

        return _emit_verdict(
            "PASS",
            [
                "Lane: minimal",
                (
                    f"Account {account.account_address} sequence_number="
                    f"{account_info.get('sequence_number', '?')}"
                ),
                (
                    "DEX REST probe succeeded via "
                    f"{dex_probe['endpoint']} (status={dex_probe['status']})"
                ),
            ],
            PASS_EXIT,
        )
    except Exception as exc:
        return _emit_verdict(
            "LIVE-FAIL",
            [
                "Lane: minimal",
                f"Read-only live validation failed: {exc}",
            ],
            LIVE_FAIL_EXIT,
        )
    finally:
        await rest_client.close()


async def _run_enhanced_lane() -> int:
    from _common import bootstrap_enhanced_lane, create_rest_client, get_mark_price
    from _common import run_live_preflight

    preflight = await run_live_preflight()
    _print_preflight_details(preflight)
    if not preflight["ok"]:
        return _emit_verdict("ENV-FAIL", [], ENV_FAIL_EXIT)

    rest_client = create_rest_client()
    account = preflight["account"]
    symbol_id = _get_enhanced_symbol_id()
    subaccount_id = _get_enhanced_subaccount_id()

    try:
        bootstrap = await bootstrap_enhanced_lane(
            rest_client,
            account,
            preferred_symbol_id=symbol_id,
            preferred_subaccount_id=subaccount_id,
        )
        symbol_id = bootstrap["symbol_id"]
        subaccount_id = bootstrap["subaccount_number"]
        sub_address = bootstrap["sub_address"]
        mark_price = await get_mark_price(symbol_id)
        market_subticks = max(1, int(mark_price * 1.10) * 100_000)
        order = DexPlaceOrder(
            sub_address=sub_address,
            symbol_id=symbol_id,
            symbol_type=SymbolType.PERPETUAL,
            side=Side.BUY,
            quantums=1_000_000,
            subticks=market_subticks,
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
        nonce = generate_nonce()
        dex_orders = DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([order])])
        dex_tx = DexTx(nonce, dex_orders, CreatedBy.USER)
        orderless = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)
        result = await build_and_submit_dex_orderless(
            rest_client, account, orderless
        )
        return _emit_verdict(
            "PASS",
            [
                "Lane: enhanced",
                f"Submitted live DEX orderless transaction hash={result['hash']}",
                (
                    "Bootstrap source: "
                    f"{preflight['account_source']}"
                ),
                (
                    "Bootstrap details: "
                    f"subaccount={subaccount_id}, available_margin="
                    f"{bootstrap['available_margin'] / 1_000_000:.2f} USDC, "
                    f"leverage_hash={bootstrap['leverage_hash']}"
                ),
                (
                    "Enhanced inputs: "
                    f"TEST_SYMBOL_ID={symbol_id}, TEST_SUBACCOUNT_ID={subaccount_id}"
                ),
            ],
            PASS_EXIT,
        )
    except Exception as exc:
        return _emit_verdict(
            "LIVE-FAIL",
            [
                "Lane: enhanced",
                f"Live DEX orderless submission failed: {exc}",
                (
                    "Bootstrap source: "
                    f"{preflight['account_source']}"
                ),
                (
                    "Enhanced inputs: "
                    f"TEST_SYMBOL_ID={symbol_id}, TEST_SUBACCOUNT_ID={subaccount_id}"
                ),
            ],
            LIVE_FAIL_EXIT,
        )
    finally:
        await rest_client.close()


async def _run_json_coverage_lane() -> int:
    try:
        result = await run_captured_json_request_coverage()
        return _emit_verdict(
            "PASS",
            [
                "Lane: json-coverage",
                (
                    "Captured JSON submit requests: "
                    f"{result['json_case_count']} payload cases"
                ),
                (
                    "Payload families: "
                    f"{', '.join(result['payload_families'])}"
                ),
                (
                    "Helper default content type: "
                    f"{result['helper_default_content_type']}"
                ),
                (
                    "BCS opt-out content type: "
                    f"{result['bcs_opt_out_content_type']}"
                ),
            ],
            PASS_EXIT,
        )
    except Exception as exc:
        return _emit_verdict(
            "LIVE-FAIL",
            [
                "Lane: json-coverage",
                f"Captured JSON request coverage failed: {exc}",
            ],
            LIVE_FAIL_EXIT,
        )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Official Intention live verification harness"
    )
    parser.add_argument(
        "--lane",
        required=True,
        choices=("preflight", "minimal", "enhanced", "json-coverage"),
        help="Verification lane to execute",
    )
    args = parser.parse_args()

    if args.lane == "preflight":
        return await _run_preflight_lane()
    if args.lane == "minimal":
        return await _run_minimal_lane()
    if args.lane == "json-coverage":
        return await _run_json_coverage_lane()
    return await _run_enhanced_lane()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

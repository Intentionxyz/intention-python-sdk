# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Captured e2e request coverage for JSON transaction submission paths."""

from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from typing import Any, Dict, List

import httpx

from intention_sdk.core.account import Account
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.api.client import (
    MIME_BCS_SIGNED_TRANSACTION,
    MIME_JSON,
    ClientConfig,
    RestClient,
)
from intention_sdk.transactions.dex_payloads import (
    DexOrderlessTx,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexTx,
)
from intention_sdk.types.enums import (
    ConditionType,
    CreatedBy,
    DexOrderlessTxVariant,
    DexOrdersVariant,
    Grouping,
    OrderBasicType,
    OrderPositionMode,
    Side,
    StpMode,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)
from intention_sdk.core.account import Secp256k1PrivateKey as PrivateKey

REPO_ROOT = Path(__file__).resolve().parent.parent
DEX_EXAMPLES_DIR = REPO_ROOT / "dex-examples"
DEX_COMMON_PATH = DEX_EXAMPLES_DIR / "_common.py"
JSON_COVERAGE_PATH = DEX_EXAMPLES_DIR / "_json_request_coverage.py"
PRIVATE_KEY = (
    "secp256k1-priv-"
    "0x1111111111111111111111111111111111111111111111111111111111111111"
)


def _load_dex_common():
    return _load_dex_module("dex_examples_common", DEX_COMMON_PATH)


def _load_json_coverage():
    return _load_dex_module("dex_examples_json_request_coverage", JSON_COVERAGE_PATH)


def _load_dex_module(module_name: str, module_path: Path):
    if "dotenv" not in sys.modules:
        dotenv_stub = types.ModuleType("dotenv")
        dotenv_stub.load_dotenv = lambda *args, **kwargs: False
        sys.modules["dotenv"] = dotenv_stub
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dex_common = _load_dex_common()


def _canonical_account() -> Account:
    private_key = PrivateKey.from_hex(PRIVATE_KEY)
    return Account(
        AccountAddress(private_key.public_key().to_evm_account_bytes()),
        private_key,
    )


def _place_orderless() -> DexOrderlessTx:
    order = DexPlaceOrder(
        sub_address=AccountAddress(b"\x00" * 32),
        symbol_id=7,
        symbol_type=SymbolType.PERPETUAL,
        side=Side.BUY,
        quantums=1000,
        subticks=2000,
        trigger_subticks=0,
        order_basic_type=OrderBasicType.LIMIT,
        time_in_force=TimeInForce.GTC,
        condition_type=ConditionType.UNSPECIFIED,
        trigger_price_type=TriggerPriceType.LAST_PRICE,
        target_order_id=0,
        reduce_only=False,
        position_mode=OrderPositionMode.NET,
        slippage_tolerance_ppm=100_000,
        client_order_id="0x0123456789abcdef0123456789abcdef",
        stp_mode=StpMode.EXPIRE_MAKER,
    )
    dex_tx = DexTx(
        123456789,
        DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([order], Grouping.NA)]),
        CreatedBy.USER,
    )
    return DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)


class CapturedSubmitServer:
    def __init__(self):
        self.submissions: List[Dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1":
            return httpx.Response(200, json={"chain_id": 4})
        if request.method == "POST" and request.url.path == "/v1/transactions":
            self.submissions.append(
                {
                    "content_type": request.headers.get("Content-Type"),
                    "body": request.content,
                }
            )
            return httpx.Response(200, json={"hash": "0xabc"})
        if (
            request.method == "GET"
            and request.url.path == "/v1/transactions/by_hash/0xabc"
        ):
            return httpx.Response(
                200,
                json={
                    "type": "user_transaction",
                    "success": True,
                    "vm_status": "Executed successfully",
                },
            )
        return httpx.Response(
            404, text=f"Unexpected request: {request.method} {request.url}"
        )


class TestDexExamplesJsonSubmitRequestCoverage(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = CapturedSubmitServer()
        self.client = RestClient(
            "http://node/v1",
            ClientConfig(http2=False, trust_env=False, transaction_wait_in_seconds=1),
        )
        await self.client.client.aclose()
        self.client.client = httpx.AsyncClient(
            transport=httpx.MockTransport(self.server.handler),
            base_url="http://node",
            trust_env=False,
        )

    async def asyncTearDown(self):
        await self.client.close()

    async def test_dex_examples_submit_helper_uses_json_by_default(self):
        result = await dex_common.build_and_submit_dex_orderless(
            self.client,
            _canonical_account(),
            _place_orderless(),
        )

        self.assertEqual(result, {"hash": "0xabc", "success": True})
        self.assertEqual(len(self.server.submissions), 1)
        submission = self.server.submissions[0]
        self.assertEqual(submission["content_type"], MIME_JSON)
        body = json.loads(submission["body"])
        self.assertEqual(body["payload"]["dex_type"], "dex_payload")
        self.assertEqual(body["payload"]["operation"], "place")

    async def test_dex_examples_submit_helper_keeps_explicit_bcs_opt_out(self):
        result = await dex_common.build_and_submit_dex_orderless(
            self.client,
            _canonical_account(),
            _place_orderless(),
            encoding="bcs",
        )

        self.assertEqual(result, {"hash": "0xabc", "success": True})
        self.assertEqual(len(self.server.submissions), 1)
        submission = self.server.submissions[0]
        self.assertEqual(submission["content_type"], MIME_BCS_SIGNED_TRANSACTION)
        with self.assertRaises(UnicodeDecodeError):
            submission["body"].decode("utf-8")

    async def test_captured_json_coverage_lane_covers_all_supported_paths(self):
        coverage = _load_json_coverage()

        result = await coverage.run_captured_json_request_coverage()

        self.assertEqual(result["json_case_count"], 25)
        self.assertEqual(
            set(result["payload_families"]),
            {
                "dex_payload",
                "dex_transfer_payload",
                "dex_agent_payload",
                "dex_user_config_payload",
                "vault_payload",
            },
        )
        self.assertIn("dex_place", result["case_names"])
        self.assertIn("transfer_cross_mint_with_proof", result["case_names"])
        self.assertIn("user_adjust_isolated_margin", result["case_names"])
        self.assertIn("vault_clp_batch_create", result["case_names"])
        self.assertTrue(all(ct == MIME_JSON for ct in result["json_content_types"]))
        self.assertEqual(result["helper_default_content_type"], MIME_JSON)
        self.assertEqual(
            result["bcs_opt_out_content_type"], MIME_BCS_SIGNED_TRANSACTION
        )


if __name__ == "__main__":
    unittest.main()

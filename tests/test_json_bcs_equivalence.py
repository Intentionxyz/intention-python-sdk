# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Environment-gated JSON-vs-BCS submission equivalence test."""

from __future__ import annotations

import os
import time
import unittest

from intention_sdk.core.account import Account
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.api.client import RestClient
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
from intention_sdk.transactions import RawTransaction, TransactionPayload


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise unittest.SkipTest(f"{name} is required for JSON-vs-BCS live equivalence")
    return value


def _test_account() -> Account:
    private_key = PrivateKey.from_str(_required_env("PRIVATE_KEY"))
    return Account(
        AccountAddress(private_key.public_key().to_evm_account_bytes()),
        private_key,
    )


def _build_place_order(account: Account, chain_id: int, nonce: int, client_order_id: str):
    order = DexPlaceOrder(
        sub_address=AccountAddress(bytes.fromhex(os.getenv("INTENTION_TEST_SUB_ADDRESS", "00" * 32))),
        symbol_id=int(_required_env("INTENTION_TEST_SYMBOL_ID")),
        symbol_type=SymbolType[
            os.getenv("INTENTION_TEST_SYMBOL_TYPE", "PERPETUAL").upper()
        ],
        side=Side[os.getenv("INTENTION_TEST_SIDE", "BUY").upper()],
        quantums=int(os.getenv("INTENTION_TEST_QUANTUMS", "1000")),
        subticks=int(os.getenv("INTENTION_TEST_SUBTICKS", "1000")),
        trigger_subticks=0,
        order_basic_type=OrderBasicType.LIMIT,
        time_in_force=TimeInForce.GTC,
        condition_type=ConditionType.UNSPECIFIED,
        trigger_price_type=TriggerPriceType.LAST_PRICE,
        target_order_id=0,
        reduce_only=False,
        position_mode=OrderPositionMode.NET,
        slippage_tolerance_ppm=int(
            os.getenv("INTENTION_TEST_SLIPPAGE_TOLERANCE_PPM", "100000")
        ),
        client_order_id=client_order_id,
        stp_mode=StpMode.EXPIRE_MAKER,
    )
    dex_tx = DexTx(
        nonce,
        DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([order], Grouping.NA)]),
        CreatedBy.USER,
    )
    payload = TransactionPayload(
        DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)
    )
    return RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=int(os.getenv("INTENTION_TEST_MAX_GAS_AMOUNT", "200000")),
        gas_unit_price=int(os.getenv("INTENTION_TEST_GAS_UNIT_PRICE", "100")),
        expiration_timestamp_secs=int(time.time())
        + int(os.getenv("INTENTION_TEST_EXPIRATION_TTL", "30")),
        chain_id=chain_id,
    )


@unittest.skipUnless(
    os.getenv("INTENTION_RUN_JSON_BCS_EQUIVALENCE") == "1",
    "set INTENTION_RUN_JSON_BCS_EQUIVALENCE=1 to run the live equivalence test",
)
class TestJsonBcsEquivalence(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = RestClient(_required_env("INTENTION_NODE_URL"))

    async def asyncTearDown(self):
        await self.client.close()

    async def test_same_logical_order_is_accepted_as_json_and_bcs(self):
        account = _test_account()
        chain_id = await self.client.chain_id()
        nonce_base = int(time.time_ns())

        json_tx = _build_place_order(
            account,
            chain_id,
            nonce_base,
            "0x" + f"{nonce_base:032x}"[-32:],
        )
        bcs_tx = _build_place_order(
            account,
            chain_id,
            nonce_base + 1,
            "0x" + f"{nonce_base + 1:032x}"[-32:],
        )

        json_hash = await self.client.submit_transaction(
            json_tx, account.sign_transaction_with_authenticator(json_tx), encoding="json"
        )
        bcs_hash = await self.client.submit_transaction(
            bcs_tx, account.sign_transaction_with_authenticator(bcs_tx), encoding="bcs"
        )

        await self.client.wait_for_transaction(json_hash)
        await self.client.wait_for_transaction(bcs_hash)
        json_result = await self.client.transaction_by_hash(json_hash)
        bcs_result = await self.client.transaction_by_hash(bcs_hash)

        self.assertTrue(json_result.get("success"), json_result)
        self.assertTrue(bcs_result.get("success"), bcs_result)
        self.assertEqual(
            json_result.get("vm_status"),
            bcs_result.get("vm_status"),
        )

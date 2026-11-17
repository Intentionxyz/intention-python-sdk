# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from intention_sdk.core.account import Account
from intention_sdk.transactions.account_client import AccountClient, AccountIntents
from intention_sdk.api.dex_executor import DexExecutionResult, PendingTransactionResult
from intention_sdk.transactions.dex_payloads import (
    AdjustIsolatedMargin,
    ChangeMarginMode,
    ChangePositionMode,
    DexAgentTx,
    DexTransferTx,
    DexUserConfigTx,
    SetUserLeverage,
)
from intention_sdk.types.enums import (
    DexOrderlessTxVariant,
    DexTransferVariant,
    DexUserConfigTxVariant,
    MarginMode,
    OrderPositionMode,
)
from intention_sdk.transactions.market_resolver import MarketMetadata, SimpleMarketResolver


class TestAccountIntents(unittest.TestCase):
    def setUp(self):
        self.resolver = SimpleMarketResolver(
            [
                MarketMetadata(
                    symbol="BTC-USDC",
                    symbol_id=7,
                    atomic_resolution=-10,
                    quantum_conversion_exponent=-9,
                    step_base_quantums=100,
                    subticks_per_tick=25,
                )
            ]
        )
        self.intents = AccountIntents(self.resolver)

    def test_user_settings_build_friendly_symbol_inputs(self):
        leverage = self.intents.set_leverage(
            "0x0", [{"symbol": "BTC-USDC", "leverage": "5"}], nonce=1
        )
        self.assertEqual(leverage.variant, DexOrderlessTxVariant.DEX_USER_CONFIG)
        self.assertIsInstance(leverage.inner, DexUserConfigTx)
        self.assertEqual(
            leverage.inner.variant, DexUserConfigTxVariant.SET_USER_LEVERAGE
        )
        self.assertIsInstance(leverage.inner.payload, SetUserLeverage)
        self.assertEqual(leverage.inner.payload.leverage_info[0].symbol_id, 7)

        position = self.intents.set_position_mode("0x0", "hedge", nonce=2)
        self.assertIsInstance(position.inner.payload, ChangePositionMode)
        self.assertEqual(position.inner.payload.position_mode, OrderPositionMode.HEDGE)

        margin = self.intents.set_margin_mode(
            "0x0",
            [{"symbol": "BTC-USDC", "mode": "isolated"}],
            nonce=3,
        )
        self.assertIsInstance(margin.inner.payload, ChangeMarginMode)
        self.assertEqual(
            margin.inner.payload.margin_modes[0].margin_mode,
            MarginMode.ISOLATED,
        )

    def test_adjust_margin_and_decimal_transfer(self):
        margin = self.intents.adjust_isolated_margin(
            "0x0",
            symbol="BTC-USDC",
            side="long",
            action="add",
            amount="1.25",
            nonce=4,
        )
        self.assertIsInstance(margin.inner.payload, AdjustIsolatedMargin)
        self.assertEqual(margin.inner.payload.delta_long, 1_250_000)

        transfer = self.intents.transfer_between_subaccounts(
            "0x1",
            "0x2",
            amount=2.5,
            nonce=5,
        )
        self.assertIsInstance(transfer.inner, DexTransferTx)
        self.assertEqual(transfer.inner.variant, DexTransferVariant.INTERNAL_TRANSFER)
        self.assertEqual(transfer.inner.payload[0].amount, 2_500_000)

    def test_agent_builder_generates_valid_wire(self):
        agent = Account.generate()
        orderless = self.intents.approve_agent(
            "bot", agent, expires_in_secs=60, nonce=6
        )
        self.assertEqual(orderless.variant, DexOrderlessTxVariant.DEX_AGENT)
        self.assertIsInstance(orderless.inner, DexAgentTx)


class FakeExecutor:
    def __init__(self):
        self.executed = []
        self.submitted = []

    async def execute_orderless(self, orderless, **options):
        self.executed.append((orderless, options))
        return DexExecutionResult("0xabc", {"success": True}, [])

    async def submit_orderless(self, orderless, **options):
        self.submitted.append((orderless, options))
        return PendingTransactionResult("0xpending")


class TestAccountClient(unittest.IsolatedAsyncioTestCase):
    async def test_actions_wait_and_submit_variants_do_not(self):
        executor = FakeExecutor()
        client = AccountClient(
            executor=executor,
            signer=Account.generate(),
            node_url="http://localhost:8080/v1",
        )
        result = await client.create_subaccount("trading")
        pending = await client.submit_create_subaccount("fast")
        self.assertEqual(result.hash, "0xabc")
        self.assertEqual(pending.hash, "0xpending")
        self.assertEqual(len(executor.executed), 1)
        self.assertEqual(len(executor.submitted), 1)


if __name__ == "__main__":
    unittest.main()

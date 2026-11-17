# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

import intention_sdk

from intention_sdk.core.account import Account
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.api.intention_client import IntentionClient
from intention_sdk.types.enums import OrderPositionMode
from intention_sdk.transactions.market_resolver import MarketMetadata, SimpleMarketResolver


class TestUnifiedClient(unittest.IsolatedAsyncioTestCase):
    async def test_construction_and_trader_are_network_free(self):
        signer = Account.generate()
        sdk = IntentionClient(
            signer=signer,
            node_url="http://localhost:8080/v1",
            relayer_url="http://localhost:3000",
            ws_url="ws://localhost:3000/ws",
        )
        resolver = SimpleMarketResolver(
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
        trader = sdk.trader(
            sub_address="0x0",
            position_mode=OrderPositionMode.NET,
            resolver=resolver,
        )
        self.assertEqual(trader.sub_address, AccountAddress.from_str("0x0"))
        self.assertEqual(sdk.config.relayer_url, "http://localhost:3000")
        self.assertIsInstance(sdk.vaults, intention_sdk.VaultClient)
        self.assertIs(intention_sdk.IntentionClient, IntentionClient)
        await sdk.close()


if __name__ == "__main__":
    unittest.main()

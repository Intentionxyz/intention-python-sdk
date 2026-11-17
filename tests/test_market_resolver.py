# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from intention_sdk.transactions.market_resolver import MarketMetadata, SimpleMarketResolver


class TestSimpleMarketResolver(unittest.TestCase):
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

    def test_number_and_string_inputs_use_exact_decimal_scaling(self):
        self.assertEqual(
            self.resolver.to_quantums("BTC-USDC", "0.123456789"),
            1_234_567_800,
        )
        self.assertEqual(self.resolver.to_quantums("BTC-USDC", 0.1), 1_000_000_000)
        self.assertEqual(
            self.resolver.to_subticks("BTC-USDC", "60000.12349"),
            6_000_012_325,
        )

    def test_market_api_accepts_camel_and_snake_case(self):
        camel = MarketMetadata.from_api(
            "BTC-USDC",
            {
                "clobPairId": "7",
                "atomicResolution": -10,
                "quantumConversionExponent": -9,
                "stepBaseQuantums": "100",
                "subticksPerTick": "25",
                "status": "ACTIVE",
            },
        )
        snake = MarketMetadata.from_api(
            "BTC-USDC",
            {
                "clob_pair_id": "7",
                "atomic_resolution": -10,
                "quantum_conversion_exponent": -9,
                "step_base_quantums": "100",
                "subticks_per_tick": "25",
            },
        )
        self.assertEqual(camel.symbol_id, snake.symbol_id)
        self.assertEqual(camel.subticks_per_tick, 25)


if __name__ == "__main__":
    unittest.main()

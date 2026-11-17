# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import unittest

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.bcs import Serializer
from intention_sdk.transactions.dex_payloads import DexReplaceOrder
from intention_sdk.types.enums import SymbolType

EXPECTED_BCS = (
    "0000000000000000000000000000000000000000000000000000000000000000"
    "0208070605040302012c000000020001c03afc120000000000"
)


class TestReplaceOrderContext(unittest.TestCase):
    def test_order_id_context_matches_cross_sdk_bcs_fixture(self):
        order = DexReplaceOrder.by_order_id(
            AccountAddress(bytes(32)),
            0x0102030405060708,
            symbol_id=44,
            symbol_type=SymbolType.PERPETUAL,
            subticks=318_520_000,
        )
        serializer = Serializer()
        order.serialize(serializer)

        self.assertEqual(serializer.to_bytes().hex(), EXPECTED_BCS)


if __name__ == "__main__":
    unittest.main()

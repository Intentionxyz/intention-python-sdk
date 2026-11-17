# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import unittest

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.bcs import Deserializer, Serializer
from intention_sdk.transactions.dex_payloads import AdjustIsolatedMargin, DexUserConfigTx
from intention_sdk.types.enums import DexUserConfigTxVariant

# Cross-SDK reference vectors, computed from raw BCS primitives and shared with
# the TS / Go / C++ SDKs.
#   nonce=1, symbol_id=1, delta_long=100000, delta_short=-50000
_SUB = "0x00000000000000000000000049e34fb381864d539519caa1f02862c7ff89843d"
_PAYLOAD_NONE = "010000000000000000000000000000000000000049e34fb381864d539519caa1f02862c7ff89843d01000000a086010000000000b03cffffffffffff00"
_USER_CONFIG = "05" + _PAYLOAD_NONE
_PAYLOAD_SOME = "010000000000000000000000000000000000000049e34fb381864d539519caa1f02862c7ff89843d01000000a086010000000000b03cffffffffffff0100000000000000000000000049e34fb381864d539519caa1f02862c7ff89843d"


def _hex(serializable) -> str:
    serializer = Serializer()
    serializable.serialize(serializer)
    return serializer.to_bytes().hex()


class TestAdjustIsolatedMargin(unittest.TestCase):
    def setUp(self):
        self.sub = AccountAddress.from_str(_SUB)

    def test_payload_bcs_none(self):
        margin = AdjustIsolatedMargin(1, self.sub, 1, 100000, -50000)
        self.assertEqual(_hex(margin), _PAYLOAD_NONE)

    def test_user_config_wrapper_bcs(self):
        cfg = DexUserConfigTx(
            DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN,
            AdjustIsolatedMargin(1, self.sub, 1, 100000, -50000),
        )
        self.assertEqual(_hex(cfg), _USER_CONFIG)

    def test_payload_bcs_on_behalf_of(self):
        margin = AdjustIsolatedMargin(
            1, self.sub, 1, 100000, -50000, on_behalf_of=self.sub
        )
        self.assertEqual(_hex(margin), _PAYLOAD_SOME)

    def test_payload_round_trip(self):
        margin = AdjustIsolatedMargin(7, self.sub, 3, -123, 456)
        back = AdjustIsolatedMargin.deserialize(
            Deserializer(bytes.fromhex(_hex(margin)))
        )
        self.assertEqual(back.nonce, 7)
        self.assertEqual(back.symbol_id, 3)
        self.assertEqual(back.delta_long, -123)
        self.assertEqual(back.delta_short, 456)
        self.assertEqual(
            back.sub_address.to_string_long(), self.sub.to_string_long()
        )
        self.assertIsNone(back.on_behalf_of)

    def test_user_config_round_trip(self):
        cfg = DexUserConfigTx(
            DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN,
            AdjustIsolatedMargin(1, self.sub, 1, 100000, -50000),
        )
        back = DexUserConfigTx.deserialize(Deserializer(bytes.fromhex(_hex(cfg))))
        self.assertEqual(
            back.variant, DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN
        )
        self.assertIsInstance(back.payload, AdjustIsolatedMargin)
        self.assertEqual(back.payload.delta_short, -50000)


if __name__ == "__main__":
    unittest.main()

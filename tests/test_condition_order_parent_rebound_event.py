# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import struct
import unittest

import intention_sdk
from intention_sdk.events import dex_event_decoder as ded
from intention_sdk import events


EVENT_TYPE = "0x1::dex::ConditionOrderParentReboundEvent"


def fixture() -> bytes:
    return b"".join(
        [
            struct.pack("<QQQ", 43, 42, 84),
            b"\x11" * 32,
            b"\x22" * 32,
            struct.pack("<II", 7, 2),
            b"\x00",  # Option<String>::None
            struct.pack("<QQ", 123, 1_700_000_000_123_456),
        ]
    )


class TestConditionOrderParentReboundEvent(unittest.TestCase):
    def test_direct_and_unified_bcs_decoders(self):
        payload = fixture()
        direct = events.decode_condition_order_parent_rebound_event(payload)

        self.assertEqual(direct.order_id, 43)
        self.assertEqual(direct.old_parent_order_id, 42)
        self.assertEqual(direct.new_parent_order_id, 84)
        self.assertEqual(str(direct.owner), "0x" + "11" * 32)
        self.assertEqual(str(direct.sub_address), "0x" + "22" * 32)

        decoded = ded.decode_dex_event(EVENT_TYPE, "0x" + payload.hex())
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.event_type, "ConditionOrderParentReboundEvent")
        self.assertIsInstance(decoded.event, ded.DexConditionOrderParentReboundEvent)
        self.assertEqual(decoded.event.old_parent_order_id, 42)
        self.assertEqual(decoded.event.new_parent_order_id, 84)
        self.assertIs(
            intention_sdk.DexConditionOrderParentReboundEvent,
            ded.DexConditionOrderParentReboundEvent,
        )

    def test_structured_rest_event_data(self):
        data = {
            "order_id": "43",
            "old_parent_order_id": "42",
            "new_parent_order_id": "84",
            "owner": "0x" + "11" * 32,
            "sub_address": "0x0",
            "symbol_id": 7,
            "condition_type": 2,
            "client_order_id": {"vec": []},
            "block_height": "123",
            "block_timestamp": "1700000000123456",
        }

        decoded = ded.decode_dex_event_data(EVENT_TYPE, data)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(
            decoded.event,
            ded.DexConditionOrderParentReboundEvent(
                order_id=43,
                old_parent_order_id=42,
                new_parent_order_id=84,
                owner="0x" + "11" * 32,
                sub_address="0x" + "00" * 20,
                symbol_id=7,
                condition_type=2,
                client_order_id=None,
                block_height=123,
                block_timestamp=1_700_000_000_123_456,
            ),
        )


if __name__ == "__main__":
    unittest.main()

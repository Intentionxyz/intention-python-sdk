# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import struct
import unittest

import intention_sdk
from intention_sdk.events import dex_event_decoder as ded
from intention_sdk import events


EVENT_TYPE = "0x1::dex::ConditionOrderActivatedEvent"


def fixture() -> bytes:
    return b"".join(
        [
            struct.pack("<QQ", 43, 42),
            b"\x11" * 32,
            b"\x22" * 32,
            struct.pack("<II", 7, 2),
            b"\x00",  # Option<String>::None
            b"\x01",  # is_activated
            struct.pack("<IQQ", 1, 123, 1_700_000_000_123_456),
        ]
    )


class TestConditionOrderActivatedEvent(unittest.TestCase):
    def test_direct_and_unified_bcs_decoders(self):
        payload = fixture()
        direct = events.decode_condition_order_activated_event(payload)

        self.assertEqual(direct.order_id, 43)
        self.assertEqual(direct.parent_order_id, 42)
        self.assertEqual(str(direct.owner), "0x" + "11" * 32)
        self.assertEqual(str(direct.sub_address), "0x" + "22" * 32)
        self.assertTrue(direct.is_activated)
        self.assertEqual(direct.activation_state, 1)

        decoded = ded.decode_dex_event(EVENT_TYPE, "0x" + payload.hex())
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.event_type, "ConditionOrderActivatedEvent")
        self.assertIsInstance(decoded.event, ded.DexConditionOrderActivatedEvent)
        self.assertEqual(decoded.event.parent_order_id, 42)
        self.assertTrue(decoded.event.is_activated)
        self.assertIs(
            intention_sdk.DexConditionOrderActivatedEvent,
            ded.DexConditionOrderActivatedEvent,
        )

    def test_structured_rest_event_data(self):
        data = {
            "order_id": "43",
            "parent_order_id": "42",
            "owner": "0x" + "11" * 32,
            "sub_address": "0x0",
            "symbol_id": 7,
            "condition_type": 2,
            "client_order_id": {"vec": []},
            "is_activated": True,
            "activation_state": 1,
            "block_height": "123",
            "block_timestamp": "1700000000123456",
        }

        decoded = ded.decode_dex_event_data(EVENT_TYPE, data)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(
            decoded.event,
            ded.DexConditionOrderActivatedEvent(
                order_id=43,
                parent_order_id=42,
                owner="0x" + "11" * 32,
                sub_address="0x" + "00" * 20,
                symbol_id=7,
                condition_type=2,
                client_order_id=None,
                is_activated=True,
                activation_state=1,
                block_height=123,
                block_timestamp=1_700_000_000_123_456,
            ),
        )


if __name__ == "__main__":
    unittest.main()

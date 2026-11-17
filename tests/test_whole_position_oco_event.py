# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import struct
import unittest

import intention_sdk
from intention_sdk.events import dex_event_decoder as ded
from intention_sdk import events


EVENT_TYPE = "0x1::dex::WholePositionOcoUpdatedEvent"


def fixture() -> bytes:
    return b"".join(
        [
            b"\x11" * 32,
            b"\x22" * 32,
            struct.pack("<IIQ", 7, 1, 0),
            b"\x01",
            struct.pack("<Q", 0),
            b"\x00",
            struct.pack("<IQQ", 2, 11, 22),
        ]
    )


class TestWholePositionOcoUpdatedEvent(unittest.TestCase):
    def test_direct_and_unified_decoders_preserve_some_zero_and_none(self):
        payload = fixture()
        direct = events.decode_whole_position_oco_updated_event(payload)

        self.assertEqual(str(direct.owner), "0x" + "11" * 32)
        self.assertEqual(str(direct.sub_address), "0x" + "22" * 32)
        self.assertEqual(direct.symbol_id, 7)
        self.assertEqual(direct.position_side, 1)
        self.assertEqual(direct.group_id, 0)
        self.assertEqual(direct.take_profit_order_id, 0)
        self.assertIsNone(direct.stop_loss_order_id)
        self.assertEqual(direct.update_type, 2)
        self.assertEqual(direct.block_height, 11)
        self.assertEqual(direct.block_timestamp, 22)

        self.assertTrue(ded.is_dex_event(EVENT_TYPE))
        decoded = ded.decode_dex_event(EVENT_TYPE, "0x" + payload.hex())
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.event_type, "WholePositionOcoUpdatedEvent")
        self.assertIsInstance(
            decoded.event,
            ded.DexWholePositionOcoUpdatedEvent,
        )
        self.assertEqual(decoded.event.take_profit_order_id, 0)
        self.assertIsNone(decoded.event.stop_loss_order_id)
        self.assertIs(
            intention_sdk.DexWholePositionOcoUpdatedEvent,
            ded.DexWholePositionOcoUpdatedEvent,
        )

    def test_structured_rest_event_data_preserves_move_option(self):
        owner = "0x" + "11" * 32
        sub_address = "0x" + "00" * 20
        data = {
            "owner": owner,
            "sub_address": "0x0",
            "symbol_id": 7,
            "position_side": 2,
            "group_id": "0",
            "take_profit_order_id": {"vec": ["0"]},
            "stop_loss_order_id": {"vec": []},
            "update_type": 1,
            "block_height": "11",
            "block_timestamp": "22",
        }

        decoded = ded.decode_dex_event_data(EVENT_TYPE, data)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.event_type, "WholePositionOcoUpdatedEvent")
        self.assertEqual(
            decoded.event,
            ded.DexWholePositionOcoUpdatedEvent(
                owner=owner,
                sub_address=sub_address,
                symbol_id=7,
                position_side=2,
                group_id=0,
                take_profit_order_id=0,
                stop_loss_order_id=None,
                update_type=1,
                block_height=11,
                block_timestamp=22,
            ),
        )

        self.assertEqual(
            ded.decode_transaction_events([{"type": EVENT_TYPE, "data": data}]),
            [
                ded.DecodedTransactionEvent(
                    index=0,
                    event_type=decoded.event_type,
                    event=decoded.event,
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import unittest

from intention_sdk.bcs import Serializer
from intention_sdk.events.dex_event_decoder import (
    DexFundingRateEvent,
    decode_dex_event_data,
    decode_transaction_events,
    is_dex_event,
)


ORDER_PLACED_TAG = "0x1::dex::OrderPlacedEvent"
FUNDING_RATE_TAG = "0x1::dex::FundingRateEvent"


class TestDexStructuredEvents(unittest.TestCase):
    def test_funding_rate_bcs_is_typed(self) -> None:
        serializer = Serializer()
        serializer.serialize_u32(7)
        serializer.serialize_i32(-25)
        serializer.serialize_u64(101000)
        serializer.serialize_u64(99)
        serializer.serialize_u64(123456)

        decoded = decode_dex_event_data(
            FUNDING_RATE_TAG,
            "0x" + serializer.to_bytes().hex(),
        )

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.event_type, "FundingRateEvent")
        self.assertEqual(
            decoded.event,
            DexFundingRateEvent(
                symbol_id=7,
                funding_rate_ppm=-25,
                mark_price=101000,
                block_height=99,
                timestamp=123456,
            ),
        )

    def test_structured_order_placed_is_preserved(self) -> None:
        data = {
            "order_id": "42",
            "state": 1,
            "client_order_id": {"vec": ["client-42"]},
        }

        decoded = decode_dex_event_data(ORDER_PLACED_TAG, data)

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.event_type, "OrderPlacedEvent")
        self.assertEqual(decoded.event, data)

    def test_new_structured_dex_event_does_not_need_registry_entry(self) -> None:
        data = {
            "symbol_id": 7,
            "funding_rate_ppm": 25,
            "mark_price": "101000",
            "block_height": "99",
            "timestamp": "123456",
        }

        self.assertTrue(is_dex_event(FUNDING_RATE_TAG))
        decoded = decode_dex_event_data(FUNDING_RATE_TAG, data)
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded.event_type, "FundingRateEvent")
        self.assertEqual(decoded.event, data)

    def test_batch_preserves_structured_dex_events_only(self) -> None:
        events = [
            {"type": "0x1::coin::DepositEvent", "data": {"amount": "1"}},
            {"type": ORDER_PLACED_TAG, "data": {"order_id": "42"}},
            {"type": FUNDING_RATE_TAG, "data": {"symbol_id": 7}},
        ]

        decoded = decode_transaction_events(events)

        self.assertEqual(
            [(event.index, event.event_type) for event in decoded],
            [(1, "OrderPlacedEvent"), (2, "FundingRateEvent")],
        )

    def test_non_dex_structured_event_is_rejected(self) -> None:
        self.assertIsNone(
            decode_dex_event_data(
                "0x1::coin::DepositEvent",
                {"amount": "1"},
            )
        )


if __name__ == "__main__":
    unittest.main()

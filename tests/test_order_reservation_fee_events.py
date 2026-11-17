# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest
from typing import Optional

from intention_sdk.events import dex_event_decoder as ded
from intention_sdk.bcs import Serializer
from intention_sdk.events.events import (
    decode_condition_order_placed_event,
    decode_order_amended_event,
    decode_order_placed_event,
)


def _write_subaccount_id(serializer: Serializer) -> None:
    serializer.serialize_fixed_bytes(bytes([1]) * 32)
    serializer.serialize_u32(2)
    serializer.serialize_fixed_bytes(bytes([3]) * 32)
    serializer.serialize_fixed_bytes(bytes(16))


def _write_trailing_rate(
    serializer: Serializer, rate: Optional[int], *, omit: bool
) -> None:
    if omit:
        return
    serializer.serialize_bool(rate is not None)
    if rate is not None:
        serializer.serialize_u32(rate)


def _order_placed_bytes(
    rate: Optional[int] = None, *, omit_rate: bool = False
) -> bytes:
    serializer = Serializer()
    _write_subaccount_id(serializer)
    serializer.serialize_u32(1)
    serializer.serialize_u32(2)
    serializer.serialize_u32(1)
    serializer.serialize_i64(10)
    serializer.serialize_u64(20)
    serializer.serialize_u32(2)
    serializer.serialize_u32(4)
    serializer.serialize_u32(0)
    serializer.serialize_u32(0)
    serializer.serialize_u64(30)
    serializer.serialize_u64(0)
    serializer.serialize_u64(40)
    serializer.serialize_u32(0)
    serializer.serialize_bytes(bytes([4, 5]))
    serializer.serialize_u64(10)
    serializer.serialize_u64(0)
    serializer.serialize_i128(6)
    serializer.serialize_i128(7)
    serializer.serialize_bool(False)
    serializer.serialize_u32(0)
    serializer.serialize_u32(0)
    serializer.serialize_u32(0)
    serializer.serialize_u32(0)
    serializer.serialize_u32(50)
    serializer.serialize_u64(0)
    serializer.serialize_u32(0)
    serializer.serialize_i64(0)
    serializer.serialize_bool(False)
    serializer.serialize_option_str(None)
    serializer.serialize_u64(60)
    serializer.serialize_u64(70)
    _write_trailing_rate(serializer, rate, omit=omit_rate)
    return serializer.to_bytes()


def _order_amended_bytes(
    rate: Optional[int] = None, *, omit_rate: bool = False
) -> bytes:
    serializer = Serializer()
    serializer.serialize_u64(40)
    serializer.serialize_fixed_bytes(bytes([1]) * 32)
    serializer.serialize_fixed_bytes(bytes([2]) * 32)
    serializer.serialize_u32(1)
    serializer.serialize_i64(10)
    serializer.serialize_i64(8)
    serializer.serialize_u64(10)
    serializer.serialize_u64(8)
    serializer.serialize_bool(True)
    serializer.serialize_option_str(None)
    serializer.serialize_u64(60)
    serializer.serialize_u64(70)
    _write_trailing_rate(serializer, rate, omit=omit_rate)
    return serializer.to_bytes()


class TestOrderReservationFeeEvents(unittest.TestCase):
    def test_direct_decoders_support_new_and_historical_layouts(self) -> None:
        self.assertIsNone(
            decode_order_placed_event(
                _order_placed_bytes(omit_rate=True)
            ).reservation_fee_rate_ppm
        )
        self.assertEqual(
            decode_order_placed_event(
                _order_placed_bytes(450)
            ).reservation_fee_rate_ppm,
            450,
        )
        self.assertIsNone(
            decode_condition_order_placed_event(
                _order_placed_bytes(None)
            ).reservation_fee_rate_ppm
        )
        self.assertIsNone(
            decode_order_amended_event(
                _order_amended_bytes(omit_rate=True)
            ).reservation_fee_rate_ppm
        )
        self.assertEqual(
            decode_order_amended_event(
                _order_amended_bytes(500)
            ).reservation_fee_rate_ppm,
            500,
        )

    def test_unified_decoder_exposes_all_three_events(self) -> None:
        placed = ded.decode_dex_event(
            "0x1::dex::OrderPlacedEvent",
            "0x" + _order_placed_bytes(450).hex(),
        )
        condition = ded.decode_dex_event(
            "0x1::dex::ConditionOrderPlacedEvent",
            "0x" + _order_placed_bytes(None).hex(),
        )
        amended = ded.decode_dex_event(
            "0x1::dex::OrderAmendedEvent",
            "0x" + _order_amended_bytes(500).hex(),
        )
        assert placed is not None and condition is not None and amended is not None
        self.assertEqual(placed.event.reservation_fee_rate_ppm, 450)
        self.assertIsNone(condition.event.reservation_fee_rate_ppm)
        self.assertEqual(amended.event.reservation_fee_rate_ppm, 500)


if __name__ == "__main__":
    unittest.main()

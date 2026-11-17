# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from intention_sdk.events import dex_event_decoder as ded
from intention_sdk.events import events as event_decoders
from intention_sdk.bcs import Serializer


def _hex(s: Serializer) -> str:
    return "0x" + s.to_bytes().hex()


def _bool_payload(value: bool) -> str:
    s = Serializer()
    s.serialize_bool(value)
    return _hex(s)


def _u32_payload(value: int) -> str:
    s = Serializer()
    s.serialize_u32(value)
    return _hex(s)


def _batch_system_config_payload() -> str:
    s = Serializer()
    s.serialize_u32(3)
    s.serialize_u32(2)
    s.serialize_u32(1)
    return _hex(s)


def _batch_op_failed_payload() -> str:
    s = Serializer()
    s.serialize_u32(2)
    s.serialize_u32(42)
    s.serialize_u8(10)
    s.serialize_u64(1359)
    return _hex(s)


class TestListingEventDecoders(unittest.TestCase):
    def test_create_perpetual_event(self) -> None:
        event_type = "CreatePerpetualEvent"
        decoded = ded.decode_dex_event(
            f"0x1::dex::{event_type}",
            _bool_payload(True),
        )
        assert decoded is not None
        self.assertEqual(decoded.event_type, event_type)
        self.assertTrue(decoded.event.success)
        self.assertTrue(ded.is_dex_event(f"0x1::dex::{event_type}"))

    def test_set_symbol_events(self) -> None:
        for event_type in (
            "SetSymbolRiskLimitsEvent",
            "SetSymbolFundingEvent",
            "SetSymbolBackstopEvent",
            "SetSymbolFeeOverrideEvent",
            "SetSymbolSpecEvent",
        ):
            with self.subTest(event_type=event_type):
                decoded = ded.decode_dex_event(
                    f"0x1::dex::{event_type}",
                    _u32_payload(77),
                )
                assert decoded is not None
                self.assertEqual(decoded.event_type, event_type)
                self.assertEqual(decoded.event.perpetual_id, 77)

        direct = event_decoders.decode_set_symbol_spec_event(
            bytes([77, 0, 0, 0])
        )
        self.assertEqual(direct.perpetual_id, 77)

    def test_batch_listing_events(self) -> None:
        decoded = ded.decode_dex_event(
            "0x1::dex::BatchSystemConfigEvent",
            _batch_system_config_payload(),
        )
        assert decoded is not None
        self.assertEqual(decoded.event_type, "BatchSystemConfigEvent")
        self.assertEqual(decoded.event.total, 3)
        self.assertEqual(decoded.event.succeeded, 2)
        self.assertEqual(decoded.event.failed, 1)

        failed = ded.decode_dex_event(
            "0x1::dex::BatchOpFailedEvent",
            _batch_op_failed_payload(),
        )
        assert failed is not None
        self.assertEqual(failed.event_type, "BatchOpFailedEvent")
        self.assertEqual(failed.event.index, 2)
        self.assertEqual(failed.event.id, 42)
        self.assertEqual(failed.event.sub_op_kind, 10)
        self.assertEqual(failed.event.reason_code, 1359)

        direct = event_decoders.decode_batch_op_failed_event(
            bytes([2, 0, 0, 0, 42, 0, 0, 0, 10, 79, 5, 0, 0, 0, 0, 0, 0])
        )
        self.assertEqual(direct.reason_code, 1359)

    def test_decode_transaction_events_keeps_only_emitted_listing_events(
        self,
    ) -> None:
        decoded = ded.decode_transaction_events(
            [
                {
                    "type": "0x1::dex::SetSymbolSpecEvent",
                    "data": _u32_payload(77),
                },
                {
                    "type": "0x1::dex::BatchOpFailedEvent",
                    "data": _batch_op_failed_payload(),
                },
                {
                    "type": "0x1::dex::SetListingMultisigRequiredEvent",
                    "data": _bool_payload(True),
                },
            ]
        )

        self.assertEqual(len(decoded), 2)
        self.assertEqual(decoded[0].index, 0)
        self.assertEqual(decoded[0].event_type, "SetSymbolSpecEvent")
        self.assertEqual(decoded[1].index, 1)
        self.assertEqual(decoded[1].event_type, "BatchOpFailedEvent")


if __name__ == "__main__":
    unittest.main()

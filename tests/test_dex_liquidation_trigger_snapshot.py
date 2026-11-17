# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Contract tests for the liquidation trigger snapshot tail.

Reference payloads pin the trigger snapshot fields on the liquidation action
events. Keeping independently encoded bytes catches changes that a test using
only the SDK serializer could reproduce without detecting.
"""

from __future__ import annotations

import unittest

from intention_sdk.events import dex_event_decoder as ded

_RISK_TRANSFER_TAG = "0x1::dex::LiquidationRiskTransferEvent"
_INTERNAL_OFFSET_TAG = "0x1::dex::LiquidationInternalOffsetEvent"
_FAILED_TAG = "0x1::dex::LiquidationFailedEvent"

# chain golden: liquidation_risk_transfer_bcs_layout_matches_contract_tuple
_CORE_RISK_TRANSFER_HEX = (
    "20" + "11" * 32
    + "20" + "22" * 32
    + "33" * 32
    + "44" * 32
    + "07000000"
    + "65000000"
    + "01"
    + "00"
    + "fa" * 32
    + "40e2010000000000"
    + "cd81010000000000"
    + "efffffffffffffff"
    + "6cd9ffffffffffff"
    + "c7ffffffffffffff"
    + "5800000000000000"
    + "9210000000000000"
    + "927a080000000000"
    + "03000000"
    + "ffffffff"
    + "c7cfffffffffffffffffffffffffffff"
    + "32090100000000000000000000000000"
    + "01" + "65000000" + "8c81010000000000"
)

# chain golden: liquidation_internal_offset_bcs_layout_matches_contract_tuple
_CORE_INTERNAL_OFFSET_HEX = (
    "2012121212121212121212121212121212121212121212121212121212121212"
    "1220232323232323232323232323232323232323232323232323232323232323"
    "2323343434343434343434343434343434343434343434343434343434343434"
    "3434454545454545454545454545454545454545454545454545454545454545"
    "454508000000ca000000007d640300000000000bae000000000000e1ffffffff"
    "ffffff38feffffffffffff150300000000000023fbffffffffffff1f14000000"
    "000000a0de0b000000000004000000ffffffff32a9ffffffffffffffffffffff"
    "ffffff0100000000000000010000000000000002070000000100000000002000"
    "ca0000000bae000000000000"
)

# chain golden: liquidation_failed_bcs_layout_matches_contract_tuple_and_...
_CORE_FAILED_HEX = (
    "2013131313131313131313131313131313131313131313131313131313131313"
    "1320242424242424242424242424242424242424242424242424242424242424"
    "2424353535353535353535353535353535353535353535353535353535353535"
    "3535464646464646464646464646464646464646464646464646464646464646"
    "464609000000ffffffff0002031118000000000000583e0f0000000000050000"
    "00ffffffffcb7dffffffffffffffffffffffffffff0200000000000000010000"
    "0000000000020700000001000000000020002f010000d12f010000000000"
)


class LiquidationTriggerSnapshotTest(unittest.TestCase):
    """The blocked case: Core's live RiskTransfer wire form must decode."""

    def test_core_risk_transfer_golden_decodes_losslessly(self):
        decoded = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG, _CORE_RISK_TRANSFER_HEX
        )
        self.assertIsNotNone(
            decoded, "Core-emitted RiskTransfer BCS must decode"
        )
        event = decoded.event

        # Fields the ADL suite asserts on, ahead of the trigger tail.
        self.assertEqual(event.quantums, 123_456)
        self.assertEqual(event.price, 98_765)
        self.assertEqual(ded.to_i64(event.fee_bits), -17)
        self.assertEqual(ded.to_i64(event.realized_pnl_bits), -9_876)
        self.assertEqual(ded.to_i64(event.source_residual_settled_bits), -57)
        self.assertEqual(event.source_residual_bound_quantums, 88)
        self.assertEqual(event.block_height, 4_242)
        self.assertEqual(event.timestamp_us, 555_666)
        self.assertEqual(event.action_seq, 3)

        # Trigger snapshot must survive intact.
        self.assertEqual(event.trigger_nc, -12_345)
        self.assertEqual(event.trigger_mmr, 67_890)
        self.assertEqual(len(event.trigger_marks), 1)
        self.assertEqual(event.trigger_marks[0].symbol_id, 101)
        self.assertEqual(event.trigger_marks[0].mark_subticks, 98_700)

    def test_trigger_nc_bits_keeps_raw_pattern_and_restores_signed(self):
        """Both representations are available and consistent."""
        event = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG, _CORE_RISK_TRANSFER_HEX
        ).event
        # Raw two's-complement u128 pattern is preserved untouched.
        self.assertEqual(event.trigger_nc_bits, (-12_345) % 2**128)
        # ...and reads back as the negative value it represents.
        self.assertEqual(event.trigger_nc, -12_345)
        self.assertEqual(ded.to_i128(event.trigger_nc_bits), -12_345)
        # The raw pattern must NOT be mistaken for a plain unsigned value.
        self.assertGreater(event.trigger_nc_bits, 2**127)

    def test_core_internal_offset_golden_keeps_trigger_snapshot(self):
        """Previously decoded "successfully" while dropping the trigger tail."""
        decoded = ded.decode_dex_event_data(
            _INTERNAL_OFFSET_TAG, _CORE_INTERNAL_OFFSET_HEX
        )
        self.assertIsNotNone(decoded)
        event = decoded.event
        self.assertEqual(event.trigger_nc, -22_222)
        # u128 MMR beyond the u64 range must survive without truncation.
        self.assertEqual(event.trigger_mmr, 2**64 + 1)
        self.assertEqual(
            [(m.symbol_id, m.mark_subticks) for m in event.trigger_marks],
            [(7, 2**53 + 1), (202, 44_555)],
        )

    def test_core_failed_golden_keeps_trigger_snapshot(self):
        decoded = ded.decode_dex_event_data(_FAILED_TAG, _CORE_FAILED_HEX)
        self.assertIsNotNone(decoded)
        event = decoded.event
        self.assertEqual(event.trigger_nc, -33_333)
        self.assertEqual(event.trigger_mmr, 2**64 + 2)
        self.assertEqual(
            [(m.symbol_id, m.mark_subticks) for m in event.trigger_marks],
            [(7, 2**53 + 1), (303, 77_777)],
        )

    def test_trigger_marks_vector_preserves_order(self):
        """BCS sequences are ordered; marks must not be re-sorted or deduped."""
        event = ded.decode_dex_event_data(
            _FAILED_TAG, _CORE_FAILED_HEX
        ).event
        self.assertEqual(
            [m.symbol_id for m in event.trigger_marks], [7, 303]
        )


class RiskTransferTrailingLayoutTest(unittest.TestCase):
    """Layout dispatch: supported tails decode, unsupported ones raise."""

    @staticmethod
    def _payload(*, bound: bool, trigger: bool) -> bytes:
        full = bytes.fromhex(_CORE_RISK_TRANSFER_HEX)
        body, bound_bytes, rest = full[:212], full[212:220], full[220:-45]
        tail = full[-45:] if trigger else b""
        return body + (bound_bytes if bound else b"") + rest + tail

    def test_legacy_layout_without_bound_or_trigger(self):
        event = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG, self._payload(bound=False, trigger=False).hex()
        ).event
        self.assertEqual(event.source_residual_bound_quantums, 0)
        self.assertEqual(event.trigger_nc_bits, 0)
        self.assertEqual(event.trigger_marks, ())

    def test_v5_layout_with_bound_only(self):
        event = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG, self._payload(bound=True, trigger=False).hex()
        ).event
        self.assertEqual(event.source_residual_bound_quantums, 88)
        self.assertEqual(event.trigger_marks, ())

    def test_current_layout_with_bound_and_trigger(self):
        event = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG, self._payload(bound=True, trigger=True).hex()
        ).event
        self.assertEqual(event.source_residual_bound_quantums, 88)
        self.assertEqual(event.trigger_nc, -12_345)

    def test_release_layout_without_bound_keeps_trigger_snapshot(self):
        """Release/v2.3 carries the snapshot without the later residual bound."""
        event = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG,
            self._payload(bound=False, trigger=True).hex(),
        ).event
        self.assertEqual(event.source_residual_bound_quantums, 0)
        self.assertEqual(event.block_height, 4_242)
        self.assertEqual(event.trigger_nc, -12_345)
        self.assertEqual(event.trigger_mmr, 67_890)
        self.assertEqual(
            [(mark.symbol_id, mark.mark_subticks) for mark in event.trigger_marks],
            [(101, 98_700)],
        )

    def test_extra_trailing_bytes_are_rejected(self):
        payload = bytes.fromhex(_CORE_RISK_TRANSFER_HEX) + b"\x00"
        with self.assertRaises(ValueError):
            ded._decode_liquidation_risk_transfer_event(payload)

    def test_truncated_trigger_mark_vector_is_rejected(self):
        payload = bytearray(self._payload(bound=False, trigger=True))
        payload[-13] = 2  # Claims two marks while only one encoded mark remains.
        self.assertIsNone(
            ded.decode_dex_event_data(_RISK_TRANSFER_TAG, bytes(payload).hex())
        )


class TriggerSnapshotJsonParityTest(unittest.TestCase):
    """The Move-ABI JSON channel must yield the same values as BCS."""

    def test_json_matches_bcs_for_risk_transfer(self):
        from_bcs = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG, _CORE_RISK_TRANSFER_HEX
        ).event
        payload = {
            "flow_instance_id": "0x" + "11" * 32,
            "source_risk_unit_id": "0x" + "22" * 32,
            "source_account": "0x" + "33" * 32,
            "sub_address": "0x" + "44" * 32,
            "subaccount_number": 7,
            "symbol_id": 101,
            "risk_unit_type": 1,
            "side": 0,
            "takeover_account": "0x" + "fa" * 32,
            "quantums": 123_456,
            "price": 98_765,
            "fee_bits": str((-17) % 2**64),
            "realized_pnl_bits": str((-9_876) % 2**64),
            "source_residual_settled_bits": str((-57) % 2**64),
            "source_residual_bound_quantums": 88,
            "block_height": 4_242,
            "timestamp_us": 555_666,
            "action_seq": 3,
            "tx_index": 4_294_967_295,
            "trigger_nc_bits": str((-12_345) % 2**128),
            "trigger_mmr": 67_890,
            "trigger_marks": [{"symbol_id": 101, "mark_subticks": 98_700}],
        }
        from_json = ded.decode_dex_event_data(_RISK_TRANSFER_TAG, payload).event
        self.assertEqual(from_json, from_bcs)
        self.assertEqual(from_json.trigger_nc, -12_345)

    def test_json_without_trigger_keys_stays_backward_compatible(self):
        payload = {
            "flow_instance_id": "0x1122",
            "source_risk_unit_id": "0x3344",
            "source_account": "0x" + "33" * 32,
            "sub_address": "0x" + "44" * 32,
            "subaccount_number": 7,
            "symbol_id": 101,
            "risk_unit_type": 1,
            "side": 0,
            "takeover_account": "0x" + "fa" * 32,
            "quantums": 1,
            "price": 2,
            "fee_bits": 0,
            "realized_pnl_bits": 0,
            "block_height": 1,
            "timestamp_us": 1,
            "action_seq": 1,
            "tx_index": 4_294_967_295,
        }
        event = ded.decode_dex_event_data(_RISK_TRANSFER_TAG, payload).event
        self.assertEqual(event.trigger_nc_bits, 0)
        self.assertEqual(event.trigger_mmr, 0)
        self.assertEqual(event.trigger_marks, ())

    def test_json_snapshot_without_residual_bound_uses_compatibility_zero(self):
        payload = {
            "flow_instance_id": "0x1122",
            "source_risk_unit_id": "0x3344",
            "source_account": "0x" + "33" * 32,
            "sub_address": "0x" + "44" * 32,
            "subaccount_number": 7,
            "symbol_id": 101,
            "risk_unit_type": 1,
            "side": 0,
            "takeover_account": "0x" + "fa" * 32,
            "quantums": 123_456,
            "price": 98_765,
            "fee_bits": str((-17) % 2**64),
            "realized_pnl_bits": str((-9_876) % 2**64),
            "source_residual_settled_bits": str((-57) % 2**64),
            "block_height": 4_242,
            "timestamp_us": 555_666,
            "action_seq": 3,
            "tx_index": 4_294_967_295,
            "trigger_nc_bits": str((-12_345) % 2**128),
            "trigger_mmr": 67_890,
            "trigger_marks": [{"symbol_id": 101, "mark_subticks": 98_700}],
        }
        event = ded.decode_dex_event_data(_RISK_TRANSFER_TAG, payload).event
        self.assertEqual(event.source_residual_bound_quantums, 0)
        self.assertEqual(event.trigger_nc, -12_345)
        self.assertEqual(
            [(mark.symbol_id, mark.mark_subticks) for mark in event.trigger_marks],
            [(101, 98_700)],
        )


if __name__ == "__main__":
    unittest.main()

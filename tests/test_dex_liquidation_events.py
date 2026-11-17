# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for DEX liquidation event decoding (BCS + JSON dual transport).

Mirrors the ts-sdk and go-sdk adaptation: the chain
moved liquidation telemetry from the old ``DexExecutionResult`` gRPC stream onto
the standard transaction event stream. On the node REST, native-executor events
(``FillEvent`` etc.) arrive as hex BCS strings while the Move-ABI liquidation
events arrive as JSON objects, so the decoder must support both channels.
"""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from typing import Optional

from intention_sdk.events import dex_event_decoder as ded
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.bcs import Serializer

_U64 = 2**64


def _to_u64_bits(value: int) -> int:
    """Two's-complement bit pattern of a signed int as an unsigned u64."""
    return value % _U64


def _addr_bytes(b: int) -> bytes:
    return bytes([b]) * AccountAddress.LENGTH


def _addr_str(b: int) -> str:
    return str(AccountAddress(_addr_bytes(b)))


def _addr_hex(b: int) -> str:
    return "0x" + f"{b:02x}" * AccountAddress.LENGTH


def _write_subaccount(
    s: Serializer, addr_b: int, number: int, sub_b: int
) -> None:
    s.serialize_fixed_bytes(_addr_bytes(addr_b))
    s.serialize_u32(number)
    s.serialize_fixed_bytes(_addr_bytes(sub_b))
    s.serialize_fixed_bytes(b"\x00" * 16)  # user_name


def _fill_event_hex(
    trailing: Optional[bool],
    remaining_quantums: Optional[tuple[int, int]] = None,
) -> str:
    """Serialize historical or current FillEvent trailing layouts."""
    s = Serializer()
    s.serialize_u32(1)  # symbol_id
    for v in (10, 11, 12, 13, 14, 15, 16):  # fill_order_id .. fill_timestamp
        s.serialize_u64(v)
    _write_subaccount(s, 2, 3, 0x68)  # maker_subaccount_id
    s.serialize_u32(0)  # maker_direction
    s.serialize_u64(100)  # maker_open_quantums
    s.serialize_u64(0)  # maker_close_quantums
    s.serialize_i128(5)  # maker_opening_fee
    s.serialize_i128(6)  # maker_closing_fee
    s.serialize_u32(1)  # maker_new_state
    s.serialize_i128(-7)  # maker_realized_pnl
    s.serialize_option_str(None)  # maker_client_order_id
    _write_subaccount(s, 4, 5, 0x68)  # taker_subaccount_id
    s.serialize_u32(1)  # taker_direction
    s.serialize_u64(100)  # taker_open_quantums
    s.serialize_u64(0)  # taker_close_quantums
    s.serialize_i128(8)  # taker_opening_fee
    s.serialize_i128(9)  # taker_closing_fee
    s.serialize_u32(2)  # taker_new_state
    s.serialize_i128(10)  # taker_realized_pnl
    s.serialize_option_str(None)  # taker_client_order_id
    if remaining_quantums is not None:
        s.serialize_u64(remaining_quantums[0])  # maker_remaining_quantums
        s.serialize_u64(remaining_quantums[1])  # taker_remaining_quantums
    if trailing is not None:
        s.serialize_bool(trailing)
    return "0x" + s.to_bytes().hex()


class TestFillEventIsLiquidation(unittest.TestCase):
    def test_current_layout_includes_order_progress_before_liquidation(self) -> None:
        decoded = ded.decode_dex_event(
            "0x1::dex::FillEvent",
            _fill_event_hex(True, remaining_quantums=(5, 7)),
        )
        assert decoded is not None
        self.assertEqual(decoded.event.maker_remaining_quantums, 5)
        self.assertEqual(decoded.event.taker_remaining_quantums, 7)
        self.assertTrue(decoded.event.is_liquidation)

    def test_current_layout_without_optional_final_bool_defaults_false(self) -> None:
        decoded = ded.decode_dex_event(
            "0x1::dex::FillEvent",
            _fill_event_hex(None, remaining_quantums=(5, 7)),
        )
        assert decoded is not None
        self.assertEqual(decoded.event.maker_remaining_quantums, 5)
        self.assertEqual(decoded.event.taker_remaining_quantums, 7)
        self.assertFalse(decoded.event.is_liquidation)

    def test_trailing_true(self) -> None:
        decoded = ded.decode_dex_event(
            "0x1::dex::FillEvent", _fill_event_hex(True)
        )
        assert decoded is not None
        self.assertIsNone(decoded.event.maker_remaining_quantums)
        self.assertIsNone(decoded.event.taker_remaining_quantums)
        self.assertEqual(decoded.event_type, "FillEvent")
        self.assertTrue(decoded.event.is_liquidation)

    def test_trailing_false(self) -> None:
        decoded = ded.decode_dex_event(
            "0x1::dex::FillEvent", _fill_event_hex(False)
        )
        assert decoded is not None
        self.assertFalse(decoded.event.is_liquidation)

    def test_omitted_defaults_false(self) -> None:
        decoded = ded.decode_dex_event(
            "0x1::dex::FillEvent", _fill_event_hex(None)
        )
        assert decoded is not None
        self.assertFalse(decoded.event.is_liquidation)
        # Other fields must not regress.
        self.assertEqual(decoded.event.symbol_id, 1)
        self.assertEqual(decoded.event.taker_realized_pnl, 10)


class TestDecodeDexEventDataDispatch(unittest.TestCase):
    def test_string_data_routes_to_bcs(self) -> None:
        decoded = ded.decode_dex_event_data(
            "0x1::dex::FillEvent", _fill_event_hex(True)
        )
        assert decoded is not None
        self.assertEqual(decoded.event_type, "FillEvent")
        self.assertTrue(decoded.event.is_liquidation)

    def test_transaction_events_decodes_hex_fill(self) -> None:
        events = [
            {"type": "0x1::coin::Deposit", "data": "0x00"},
            {"type": "0x1::dex::FillEvent", "data": _fill_event_hex(True)},
        ]
        out = ded.decode_transaction_events(events)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].index, 1)
        self.assertEqual(out[0].event_type, "FillEvent")
        self.assertTrue(out[0].event.is_liquidation)


def _to_i64(bits: int) -> int:
    return bits - _U64 if bits >= 2**63 else bits


# ---------------------------------------------------------------------------
# 0002 LiquidationRiskTransferEvent
# ---------------------------------------------------------------------------

_RISK_TRANSFER_TAG = "0x1::dex::LiquidationRiskTransferEvent"

# the chain's current-v5 cross-routing golden:
# cross_f15_same_block_activation_mixed_final_state, event index 0.
_RISK_TRANSFER_V5_GOLDEN_HEX = (
    "0x"
    "202b0f5747fcd8280979d86063aa4e31291411d4adb53a2063c46bdd8c8de9e5c"
    "520b542d02b7cbb54f01e22fb402e239c2279eff277b4beb6f84369034854d459f"
    "e8181818181818181818181818181818181818181818181818181818181818181"
    "000000000000000000000000992e5f4efb3298cf6c0248592a6ed757fd70792d"
    "080000000c0000000000facadeaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    "aaaaaaaaaaaaaaaa0a0000000000000063000000000000000000000000000000f6"
    "ffffffffffffff000000000000000052000000000000007800000000000000b80b"
    "00000000000001000000ffffffff"
)


def _risk_transfer_hex(
    source_residual_bound_quantums: Optional[int] = None,
) -> str:
    s = Serializer()
    s.serialize_bytes(bytes([0x11, 0x22]))  # flow_instance_id
    s.serialize_bytes(bytes([0x33, 0x44]))  # source_risk_unit_id
    s.serialize_fixed_bytes(_addr_bytes(3))  # source_account
    s.serialize_fixed_bytes(_addr_bytes(0x68))  # sub_address
    s.serialize_u32(1)  # subaccount_number
    s.serialize_u32(7)  # symbol_id
    s.serialize_u8(1)  # risk_unit_type
    s.serialize_u8(0)  # side
    s.serialize_fixed_bytes(_addr_bytes(0xFA))  # takeover_account
    s.serialize_u64(1000000)  # quantums
    s.serialize_u64(99999)  # price
    s.serialize_u64(42)  # fee_bits
    s.serialize_u64(_to_u64_bits(-1234))  # realized_pnl_bits
    s.serialize_u64(_to_u64_bits(-7))  # source_residual_settled_bits
    if source_residual_bound_quantums is not None:
        s.serialize_u64(source_residual_bound_quantums)
    s.serialize_u64(58409)  # block_height
    s.serialize_u64(1700000000000000)  # timestamp_us
    s.serialize_u32(7)  # action_seq
    s.serialize_u32(4294967295)  # tx_index
    return "0x" + s.to_bytes().hex()


def _risk_transfer_json(
    source_residual_bound_quantums: Optional[int] = None,
) -> dict:
    payload = {
        "flow_instance_id": "0x1122",
        "source_risk_unit_id": "0x3344",
        "source_account": _addr_hex(3),
        "sub_address": _addr_hex(0x68),
        "subaccount_number": 1,
        "symbol_id": 7,
        "risk_unit_type": 1,
        "side": 0,
        "takeover_account": _addr_hex(0xFA),
        "quantums": "1000000",
        "price": "99999",
        "fee_bits": "42",
        "realized_pnl_bits": str(_to_u64_bits(-1234)),
        "source_residual_settled_bits": str(_to_u64_bits(-7)),
        "block_height": "58409",
        "timestamp_us": "1700000000000000",
        "action_seq": 7,
        "tx_index": 4294967295,
    }
    if source_residual_bound_quantums is not None:
        payload["source_residual_bound_quantums"] = str(source_residual_bound_quantums)
    return payload


class TestDecodeLiquidationRiskTransferEvent(unittest.TestCase):
    def test_current_v5_golden_decodes_without_trailing_field_shift(self) -> None:
        decoded = ded.decode_transaction_events(
            [
                {"type": "0x1::coin::Deposit", "data": "0x00"},
                {
                    "type": _RISK_TRANSFER_TAG,
                    "data": _RISK_TRANSFER_V5_GOLDEN_HEX,
                },
            ]
        )

        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0].index, 1)
        self.assertEqual(decoded[0].event_type, "LiquidationRiskTransferEvent")
        event = decoded[0].event
        self.assertEqual(event.source_residual_bound_quantums, 82)
        self.assertEqual(event.block_height, 120)
        self.assertEqual(event.timestamp_us, 3000)
        self.assertEqual(event.action_seq, 1)
        self.assertEqual(event.tx_index, 2**32 - 1)

    def test_bcs_rejects_ambiguous_trailing_layout(self) -> None:
        decoded = ded.decode_transaction_events(
            [
                {
                    "type": _RISK_TRANSFER_TAG,
                    "data": _risk_transfer_hex() + "00",
                }
            ]
        )

        self.assertEqual(decoded, [])

    def test_bcs_rejects_current_layout_truncated_to_historical_length(
        self,
    ) -> None:
        decoded = ded.decode_transaction_events(
            [
                {
                    "type": _RISK_TRANSFER_TAG,
                    "data": _RISK_TRANSFER_V5_GOLDEN_HEX[:-16],
                }
            ]
        )

        self.assertEqual(decoded, [])

    def test_bcs_decode(self) -> None:
        decoded = ded.decode_dex_event(_RISK_TRANSFER_TAG, _risk_transfer_hex())
        assert decoded is not None
        self.assertEqual(decoded.event_type, "LiquidationRiskTransferEvent")
        e = decoded.event
        self.assertEqual(_to_i64(e.realized_pnl_bits), -1234)
        self.assertEqual(_to_i64(e.source_residual_settled_bits), -7)
        self.assertEqual(e.source_residual_bound_quantums, 0)
        self.assertEqual(e.side, 0)
        self.assertEqual(e.risk_unit_type, 1)
        self.assertEqual(e.symbol_id, 7)
        self.assertEqual(e.tx_index, 4294967295)
        self.assertEqual(e.flow_instance_id, bytes([0x11, 0x22]))

    def test_bcs_json_parity(self) -> None:
        from_bcs = ded.decode_dex_event(_RISK_TRANSFER_TAG, _risk_transfer_hex())
        from_json = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG, _risk_transfer_json()
        )
        assert from_bcs is not None and from_json is not None
        self.assertEqual(from_json.event, from_bcs.event)

    def test_current_bcs_json_parity_includes_residual_bound(self) -> None:
        from_bcs = ded.decode_dex_event(
            _RISK_TRANSFER_TAG,
            _risk_transfer_hex(source_residual_bound_quantums=82),
        )
        from_json = ded.decode_dex_event_data(
            _RISK_TRANSFER_TAG,
            _risk_transfer_json(source_residual_bound_quantums=82),
        )

        assert from_bcs is not None and from_json is not None
        self.assertEqual(from_json.event, from_bcs.event)
        self.assertEqual(from_json.event.source_residual_bound_quantums, 82)

    def test_json_rejects_non_system_transaction_index(self) -> None:
        payload = _risk_transfer_json(source_residual_bound_quantums=82)
        payload["tx_index"] = 0

        decoded = ded.decode_transaction_events(
            [{"type": _RISK_TRANSFER_TAG, "data": payload}]
        )

        self.assertEqual(decoded, [])


# ---------------------------------------------------------------------------
# 0006 LiquidationDirectAdlEvent
# ---------------------------------------------------------------------------

_DIRECT_ADL_TAG = "0x1::dex::LiquidationDirectAdlEvent"

# the chain's current-v5 cross-routing golden:
# cross_f15_same_block_activation_mixed_final_state, event index 1.
_DIRECT_ADL_V5_GOLDEN_HEX = (
    "0x"
    "202b0f5747fcd8280979d86063aa4e31291411d4adb53a2063c46bdd8c8de9e5c"
    "520b542d02b7cbb54f01e22fb402e239c2279eff277b4beb6f84369034854d459f"
    "e8181818181818181818181818181818181818181818181818181818181818181"
    "000000000000000000000000992e5f4efb3298cf6c0248592a6ed757fd70792d"
    "080000000b00000000000a00000000000000630000000000000000000000000000"
    "00f6ffffffffffffff000000000000000000000000000000007800000000000000"
    "b80b00000000000000000000ffffffff"
)


def _direct_adl_v5_json() -> dict:
    return {
        "flow_instance_id": (
            "0x2b0f5747fcd8280979d86063aa4e31291411d4adb53a2063c46bdd8c8de9e5c5"
        ),
        "source_risk_unit_id": (
            "0xb542d02b7cbb54f01e22fb402e239c2279eff277b4beb6f84369034854d459fe"
        ),
        "source_account": _addr_hex(0x81),
        # The REST API may omit leading zeroes from an address.
        "sub_address": "0x992e5f4efb3298cf6c0248592a6ed757fd70792d",
        "subaccount_number": 8,
        "symbol_id": 11,
        "risk_unit_type": 0,
        "side": 0,
        "target_quantums": "10",
        "bankruptcy_subticks": "99",
        "source_fee_bits": "0",
        "source_realized_pnl_bits": str(_to_u64_bits(-10)),
        "source_residual_settled_bits": "0",
        "source_residual_bound_quantums": "0",
        "block_height": "120",
        "timestamp_us": "3000",
        "action_seq": 0,
        "tx_index": str(2**32 - 1),
    }


def _direct_adl_signed_bits_hex() -> str:
    serializer = Serializer()
    serializer.serialize_bytes(bytes([0x11]) * 32)
    serializer.serialize_bytes(bytes([0x22]) * 32)
    serializer.serialize_fixed_bytes(_addr_bytes(0x33))
    serializer.serialize_fixed_bytes(_addr_bytes(0x44))
    serializer.serialize_u32(7)
    serializer.serialize_u32(101)
    serializer.serialize_u8(1)
    serializer.serialize_u8(0)
    serializer.serialize_u64(123456)
    serializer.serialize_u64(98765)
    serializer.serialize_u64(_to_u64_bits(-17))
    serializer.serialize_u64(_to_u64_bits(-9876))
    serializer.serialize_u64(_to_u64_bits(-57))
    serializer.serialize_u64(88)
    serializer.serialize_u64(4242)
    serializer.serialize_u64(555666)
    serializer.serialize_u32(3)
    serializer.serialize_u32(2**32 - 1)
    return "0x" + serializer.to_bytes().hex()


class TestDecodeLiquidationDirectAdlEvent(unittest.TestCase):
    def test_current_v5_bcs_golden_decodes_from_transaction_batch(self) -> None:
        decoded = ded.decode_transaction_events(
            [
                {"type": "0x1::coin::Deposit", "data": "0x00"},
                {
                    "type": _DIRECT_ADL_TAG,
                    "data": _DIRECT_ADL_V5_GOLDEN_HEX,
                },
            ]
        )

        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0].index, 1)
        self.assertEqual(decoded[0].event_type, "LiquidationDirectAdlEvent")
        event = decoded[0].event
        self.assertEqual(event.source_account, _addr_str(0x81))
        self.assertEqual(event.subaccount_number, 8)
        self.assertEqual(event.symbol_id, 11)
        self.assertEqual(event.risk_unit_type, 0)
        self.assertEqual(event.side, 0)
        self.assertEqual(event.target_quantums, 10)
        self.assertEqual(event.bankruptcy_subticks, 99)
        self.assertEqual(_to_i64(event.source_realized_pnl_bits), -10)
        self.assertEqual(event.source_residual_bound_quantums, 0)
        self.assertEqual(event.block_height, 120)
        self.assertEqual(event.timestamp_us, 3000)
        self.assertEqual(event.action_seq, 0)
        self.assertEqual(event.tx_index, 2**32 - 1)

    def test_json_transport_matches_bcs_typed_payload(self) -> None:
        from_bcs = ded.decode_dex_event(
            _DIRECT_ADL_TAG,
            _DIRECT_ADL_V5_GOLDEN_HEX,
        )
        from_json = ded.decode_dex_event_data(
            _DIRECT_ADL_TAG,
            _direct_adl_v5_json(),
        )

        assert from_bcs is not None and from_json is not None
        self.assertIsInstance(from_json.event, ded.DexLiquidationDirectAdlEvent)
        self.assertEqual(from_json.event, from_bcs.event)
        self.assertEqual(_to_i64(from_json.event.source_realized_pnl_bits), -10)

    def test_bcs_with_trailing_bytes_is_rejected(self) -> None:
        decoded = ded.decode_transaction_events(
            [
                {
                    "type": _DIRECT_ADL_TAG,
                    "data": _DIRECT_ADL_V5_GOLDEN_HEX + "00",
                }
            ]
        )

        self.assertEqual(decoded, [])

    def test_truncated_bcs_is_rejected(self) -> None:
        decoded = ded.decode_dex_event(
            _DIRECT_ADL_TAG,
            _DIRECT_ADL_V5_GOLDEN_HEX[:-2],
        )

        self.assertIsNone(decoded)

    def test_json_with_boolean_integer_field_is_rejected(self) -> None:
        payload = _direct_adl_v5_json()
        payload["target_quantums"] = True

        decoded = ded.decode_dex_event_data(_DIRECT_ADL_TAG, payload)

        self.assertIsNone(decoded)

    def test_json_with_missing_required_field_is_rejected(self) -> None:
        payload = _direct_adl_v5_json()
        del payload["source_account"]

        decoded = ded.decode_dex_event_data(_DIRECT_ADL_TAG, payload)

        self.assertIsNone(decoded)

    def test_signed_bit_fields_keep_their_unsigned_u64_wire_values(self) -> None:
        decoded = ded.decode_dex_event(
            _DIRECT_ADL_TAG,
            _direct_adl_signed_bits_hex(),
        )

        assert decoded is not None
        event = decoded.event
        self.assertEqual(event.source_fee_bits, _to_u64_bits(-17))
        self.assertEqual(event.source_realized_pnl_bits, _to_u64_bits(-9876))
        self.assertEqual(
            event.source_residual_settled_bits,
            _to_u64_bits(-57),
        )
        self.assertEqual(_to_i64(event.source_fee_bits), -17)
        self.assertEqual(_to_i64(event.source_realized_pnl_bits), -9876)
        self.assertEqual(_to_i64(event.source_residual_settled_bits), -57)

    def test_typed_payload_is_immutable(self) -> None:
        decoded = ded.decode_dex_event(
            _DIRECT_ADL_TAG,
            _DIRECT_ADL_V5_GOLDEN_HEX,
        )

        assert decoded is not None
        with self.assertRaises(FrozenInstanceError):
            decoded.event.symbol_id = 12


class TestDecodeTransactionEventsMixedTransport(unittest.TestCase):
    def test_mixed_hex_and_json(self) -> None:
        events = [
            {"type": "0x1::dex::FillEvent", "data": _fill_event_hex(True)},
            {"type": _RISK_TRANSFER_TAG, "data": _risk_transfer_json()},
            {"type": "0x1::coin::Deposit", "data": "0x00"},
        ]
        out = ded.decode_transaction_events(events)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].event_type, "FillEvent")
        self.assertEqual(out[1].event_type, "LiquidationRiskTransferEvent")
        self.assertEqual(out[1].index, 1)


# ---------------------------------------------------------------------------
# 0003 LiquidationInternalOffsetEvent
# ---------------------------------------------------------------------------

_INTERNAL_OFFSET_TAG = "0x1::dex::LiquidationInternalOffsetEvent"


def _internal_offset_hex() -> str:
    s = Serializer()
    s.serialize_bytes(bytes([0xAB, 0xCD]))
    s.serialize_bytes(bytes([0xDC, 0xBA]))
    s.serialize_fixed_bytes(_addr_bytes(1))
    s.serialize_fixed_bytes(_addr_bytes(0x68))
    s.serialize_u32(9)  # subaccount_number
    s.serialize_u32(7)  # symbol_id
    s.serialize_u8(0)  # risk_unit_type
    s.serialize_u64(2**64 - 1)  # quantums (u64::MAX)
    s.serialize_u64(12345)  # price
    s.serialize_u64(200)  # total_fee_bits
    s.serialize_u64(_to_u64_bits(-50))  # total_realized_pnl_bits
    s.serialize_u64(150)  # long_realized_pnl_bits
    s.serialize_u64(_to_u64_bits(-200))  # short_realized_pnl_bits
    s.serialize_u64(58409)  # block_height
    s.serialize_u64(1700000000000000)  # timestamp_us
    s.serialize_u32(3)  # action_seq
    s.serialize_u32(4294967295)  # tx_index
    return "0x" + s.to_bytes().hex()


def _internal_offset_json() -> dict:
    return {
        "flow_instance_id": "0xabcd",
        "source_risk_unit_id": "0xdcba",
        "source_account": _addr_hex(1),
        "sub_address": _addr_hex(0x68),
        "subaccount_number": 9,
        "symbol_id": 7,
        "risk_unit_type": 0,
        "quantums": str(2**64 - 1),
        "price": "12345",
        "total_fee_bits": "200",
        "total_realized_pnl_bits": str(_to_u64_bits(-50)),
        "long_realized_pnl_bits": "150",
        "short_realized_pnl_bits": str(_to_u64_bits(-200)),
        "block_height": "58409",
        "timestamp_us": "1700000000000000",
        "action_seq": 3,
        "tx_index": 4294967295,
    }


class TestDecodeLiquidationInternalOffsetEvent(unittest.TestCase):
    def test_bcs_and_parity(self) -> None:
        from_bcs = ded.decode_dex_event(
            _INTERNAL_OFFSET_TAG, _internal_offset_hex()
        )
        assert from_bcs is not None
        self.assertEqual(
            from_bcs.event_type, "LiquidationInternalOffsetEvent"
        )
        e = from_bcs.event
        self.assertEqual(_to_i64(e.long_realized_pnl_bits), 150)
        self.assertEqual(_to_i64(e.short_realized_pnl_bits), -200)
        self.assertEqual(_to_i64(e.total_realized_pnl_bits), -50)
        self.assertEqual(e.quantums, 2**64 - 1)
        self.assertEqual(e.tx_index, 4294967295)
        from_json = ded.decode_dex_event_data(
            _INTERNAL_OFFSET_TAG, _internal_offset_json()
        )
        assert from_json is not None
        self.assertEqual(from_json.event, from_bcs.event)


# ---------------------------------------------------------------------------
# 0004 LiquidationFailedEvent + JSON e2e + golden
# ---------------------------------------------------------------------------

_FAILED_TAG = "0x1::dex::LiquidationFailedEvent"


def _failed_hex() -> str:
    s = Serializer()
    s.serialize_bytes(bytes([0xDE, 0xAD]))
    s.serialize_bytes(bytes([0xBE, 0xEF]))
    s.serialize_fixed_bytes(_addr_bytes(2))
    s.serialize_fixed_bytes(_addr_bytes(0x68))
    s.serialize_u32(0)  # subaccount_number
    s.serialize_u32(4294967295)  # symbol_id (account-level sentinel u32::MAX)
    s.serialize_u8(1)  # risk_unit_type
    s.serialize_u8(3)  # step
    s.serialize_u8(9)  # reason_code
    s.serialize_u64(58409)  # block_height
    s.serialize_u64(1700000000000000)  # timestamp_us
    s.serialize_u32(2)  # action_seq
    s.serialize_u32(4294967295)  # tx_index
    return "0x" + s.to_bytes().hex()


def _failed_json() -> dict:
    return {
        "flow_instance_id": "0xdead",
        "source_risk_unit_id": "0xbeef",
        "source_account": _addr_hex(2),
        "sub_address": _addr_hex(0x68),
        "subaccount_number": 0,
        "symbol_id": 4294967295,
        "risk_unit_type": 1,
        "step": 3,
        "reason_code": 9,
        "block_height": "58409",
        "timestamp_us": "1700000000000000",
        "action_seq": 2,
        "tx_index": 4294967295,
    }


class TestDecodeLiquidationFailedEvent(unittest.TestCase):
    def test_bcs_and_parity(self) -> None:
        from_bcs = ded.decode_dex_event(_FAILED_TAG, _failed_hex())
        assert from_bcs is not None
        self.assertEqual(from_bcs.event_type, "LiquidationFailedEvent")
        e = from_bcs.event
        self.assertEqual(e.symbol_id, 4294967295)
        self.assertEqual(e.step, 3)
        self.assertEqual(e.reason_code, 9)
        from_json = ded.decode_dex_event_data(_FAILED_TAG, _failed_json())
        assert from_json is not None
        self.assertEqual(from_json.event, from_bcs.event)


class TestDecodeTransactionEventsLiquidationE2E(unittest.TestCase):
    """A realistic REST batch mixing hex-BCS FillEvent (native executor) with
    all three JSON Move-ABI liquidation events, plus an unrelated event."""

    def test_full_mixed_batch(self) -> None:
        events = [
            {"type": "0x1::coin::Withdraw", "data": "0x01"},
            {"type": "0x1::dex::FillEvent", "data": _fill_event_hex(True)},
            {"type": _RISK_TRANSFER_TAG, "data": _risk_transfer_json()},
            {"type": _INTERNAL_OFFSET_TAG, "data": _internal_offset_json()},
            {"type": _FAILED_TAG, "data": _failed_json()},
        ]
        out = ded.decode_transaction_events(events)
        self.assertEqual(len(out), 4)
        self.assertEqual(
            [d.event_type for d in out],
            [
                "FillEvent",
                "LiquidationRiskTransferEvent",
                "LiquidationInternalOffsetEvent",
                "LiquidationFailedEvent",
            ],
        )
        self.assertEqual([d.index for d in out], [1, 2, 3, 4])
        self.assertTrue(out[0].event.is_liquidation)
        self.assertEqual(_to_i64(out[1].event.realized_pnl_bits), -1234)
        self.assertEqual(_to_i64(out[2].event.short_realized_pnl_bits), -200)


def _golden_risk_transfer_leg(flow: str, side: int, pnl_bits: str) -> dict:
    return {
        "flow_instance_id": flow,
        "source_risk_unit_id": "0x01",
        "source_account": _addr_hex(1),
        "sub_address": _addr_hex(0x68),
        "subaccount_number": 0,
        "symbol_id": 1,
        "risk_unit_type": 1,
        "side": side,
        "takeover_account": _addr_hex(0xFA),
        "quantums": "1",
        "price": "1",
        "fee_bits": "0",
        "realized_pnl_bits": pnl_bits,
        "source_residual_settled_bits": "0",
        "block_height": "1",
        "timestamp_us": "1",
        "action_seq": 0,
        "tx_index": 4294967295,
    }


class TestGoldenRiskTransferThreeLeg(unittest.TestCase):
    """Golden vector from a real on-chain 3-leg RiskTransfer under one flow.
    Cross-checked against the chain JSON payload."""

    def test_three_legs(self) -> None:
        flow = "0x97a5c364"
        legs = [
            ("BTC", 1, "18446744064010459018", -9699092598),
            ("ETH", 0, "17265743", 17265743),
            ("SOL", 1, "18446744073644341161", -65210455),
        ]
        flow_bytes = None
        for name, side, pnl_bits, want in legs:
            decoded = ded.decode_dex_event_data(
                _RISK_TRANSFER_TAG,
                _golden_risk_transfer_leg(flow, side, pnl_bits),
            )
            assert decoded is not None, name
            e = decoded.event
            self.assertEqual(_to_i64(e.realized_pnl_bits), want, name)
            self.assertEqual(e.side, side, name)
            if flow_bytes is None:
                flow_bytes = e.flow_instance_id
            else:
                self.assertEqual(e.flow_instance_id, flow_bytes, name)


if __name__ == "__main__":
    unittest.main()

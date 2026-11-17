# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for canonical ADL execution events in the transaction event stream."""

from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

import intention_sdk

from intention_sdk.events import dex_event_decoder as ded
from intention_sdk.bcs import Serializer

_ADL_EXECUTION_TAG = "0x1::dex::AdlExecutionEvent"
_DIRECT_ADL_TAG = "0x1::dex::LiquidationDirectAdlEvent"
_ADL_V5_CATALOG = json.loads(
    (Path(__file__).with_name("test_fixtures") / "adl_v5_golden.json").read_text()
)
_ADL_V7_FIXTURE = json.loads(
    (
        Path(__file__).with_name("test_fixtures") / "adl_v7_round_half_up_golden.json"
    ).read_text()
)
_CURRENT_RECEIPT = json.loads(
    (
        Path(__file__).with_name("test_fixtures") / "adl_unified_remainder_v9.json"
    ).read_text()
)["chunks"][1]


def _catalog_chunks(case_name: str) -> tuple[str, ...]:
    case = next(item for item in _ADL_V5_CATALOG["cases"] if item["name"] == case_name)
    return tuple("0x" + chunk for chunk in case["chunks"])


(_DIRECT_SINGLETON_V5_GOLDEN_HEX,) = _catalog_chunks("direct_singleton")


def _decode_catalog_case(case_name: str) -> tuple[ded.DexAdlExecutionEvent, ...]:
    events = []
    for payload in _catalog_chunks(case_name):
        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, payload)
        assert decoded is not None
        assert isinstance(decoded.event, ded.DexAdlExecutionEvent)
        events.append(decoded.event)
    return tuple(events)


def _replace_uint(
    payload: str,
    byte_offset: int,
    byte_length: int,
    value: int,
) -> str:
    raw = bytearray.fromhex(payload.removeprefix("0x"))
    raw[byte_offset : byte_offset + byte_length] = value.to_bytes(
        byte_length,
        "little",
    )
    return "0x" + raw.hex()


def _matching_direct_source_v5_hex() -> str:
    serializer = Serializer()
    serializer.serialize_bytes(bytes([0x75]) * 32)
    serializer.serialize_bytes(bytes([0x76]) * 32)
    serializer.serialize_fixed_bytes(bytes([0x91]) * 32)
    serializer.serialize_fixed_bytes(bytes([0x92]) * 32)
    serializer.serialize_u32(8)
    serializer.serialize_u32(7)
    serializer.serialize_u8(0)
    serializer.serialize_u8(0)
    serializer.serialize_u64(100)
    serializer.serialize_u64(12345)
    serializer.serialize_u64(10_000_000)
    serializer.serialize_u64((-5_000_000) % 2**64)
    serializer.serialize_u64(0)
    serializer.serialize_u64(1)
    serializer.serialize_u64(750)
    serializer.serialize_u64(1_000)
    serializer.serialize_u32(0)
    serializer.serialize_u32(2**32 - 1)
    return "0x" + serializer.to_bytes().hex()


class TestDecodeAdlExecutionEventV5(unittest.TestCase):
    def test_public_decoder_reads_algorithm_v7_round_half_up_fixture(self) -> None:
        payload = "0x" + _ADL_V7_FIXTURE["canonicalBcsHex"]

        decoded = intention_sdk.decode_transaction_events(
            [{"type": _ADL_EXECUTION_TAG, "data": payload}]
        )

        self.assertEqual(len(decoded), 1)
        event = decoded[0].event
        self.assertIsInstance(event, ded.DexAdlExecutionEvent)
        assert isinstance(event, ded.DexAdlExecutionEvent)
        self.assertEqual(event.schema_version, 5)
        self.assertEqual(event.selected_prefix_header.algorithm_version, 7)
        self.assertEqual(event.selected_prefix_header.target_quantums, 70_000_000)
        self.assertEqual(
            event.audit_entries[0].realized_pnl_signed.abs_value, 115_552_211
        )
        self.assertEqual(
            _ADL_V7_FIXTURE["workedExample"]["sourceRealizedPnlQuantums"],
            "-115552211",
        )
        self.assertEqual(
            event.input_snapshot_hash.hex(), _ADL_V7_FIXTURE["inputSnapshotHashHex"]
        )
        self.assertEqual(
            event.selected_prefix_hash.hex(), _ADL_V7_FIXTURE["selectedPrefixHashHex"]
        )
        self.assertEqual(
            event.execution_fills_digest.hex(),
            _ADL_V7_FIXTURE["executionFillsDigestHex"],
        )
        self.assertEqual(
            intention_sdk.decode_transaction_events(
                [{"type": _ADL_EXECUTION_TAG, "data": payload[:-2]}]
            ),
            [],
        )
        self.assertEqual(
            intention_sdk.decode_transaction_events(
                [{"type": _ADL_EXECUTION_TAG, "data": payload + "00"}]
            ),
            [],
        )

    def test_current_v5_single_chunk_golden_decodes_typed_payload(self) -> None:
        decoded = ded.decode_dex_event_data(
            _ADL_EXECUTION_TAG,
            _DIRECT_SINGLETON_V5_GOLDEN_HEX,
        )

        assert decoded is not None
        self.assertEqual(decoded.event_type, "AdlExecutionEvent")
        self.assertIsInstance(decoded.event, ded.DexAdlExecutionEvent)
        event = decoded.event
        self.assertEqual(event.schema_version, 5)
        self.assertEqual(event.adl_event_id.trigger_block_height, 750)
        self.assertEqual(event.adl_event_id.trigger_index_in_block, 0)
        self.assertEqual(event.chunk_index, 0)
        self.assertEqual(event.total_chunks, 1)
        self.assertEqual(event.audit_entries_start_index, 0)
        self.assertEqual(event.audit_entries_end_index_exclusive, 1)

        header = event.selected_prefix_header
        self.assertEqual(header.schema_version, 5)
        self.assertEqual(header.algorithm_version, 4)
        self.assertEqual(header.price_version, 749)
        self.assertEqual(header.pre_adl_state_version, 750)
        self.assertEqual(header.queue_key.symbol_id, 7)
        self.assertEqual(
            header.queue_key.opponent_side,
            ded.DexAdlPositionSide.SHORT,
        )
        self.assertEqual(
            header.trigger_source,
            ded.DexAdlTriggerSource.LIQUIDATION_RESIDUAL,
        )
        self.assertEqual(
            header.trigger_reasons,
            (ded.DexAdlTriggerSource.LIQUIDATION_RESIDUAL,),
        )
        self.assertEqual(
            header.source_locator.source_kind,
            ded.DexAdlSourceKind.DIRECT_LIQUIDATION,
        )
        locator = header.source_locator.direct_liquidation_locator
        assert locator is not None
        self.assertEqual(locator.block_height, 750)
        self.assertEqual(locator.direct_liquidation_index_in_block, 0)
        self.assertEqual(locator.flow_instance_id, bytes([0x75]) * 32)
        self.assertEqual(locator.action_seq, 0)
        self.assertEqual(header.source_risk_holder.subaccount_number, 8)
        self.assertEqual(
            header.original_liquidated_account,
            header.source_risk_holder,
        )
        self.assertEqual(
            header.source_position_key.position_side,
            ded.DexAdlPositionSide.LONG,
        )
        self.assertEqual(
            header.source_position_key.margin_mode,
            ded.DexAdlMarginMode.CROSS,
        )
        self.assertEqual(header.bankruptcy_subticks, 12345)
        self.assertEqual(header.target_quantums, 100)
        self.assertEqual(header.total_executed_quantums, 100)
        self.assertEqual(header.stop_reason, ded.DexAdlStopReason.TARGET_FILLED)

        self.assertEqual(len(event.audit_entries), 1)
        entry = event.audit_entries[0]
        self.assertEqual(entry.schema_version, 5)
        self.assertEqual(entry.audit_entry_index, 0)
        self.assertEqual(
            entry.execution_pass,
            ded.DexAdlExecutionPass.NET_EXPOSURE,
        )
        self.assertEqual(entry.rank_index, 1)
        self.assertEqual(
            entry.position_key.position_side,
            ded.DexAdlPositionSide.SHORT,
        )
        self.assertEqual(entry.raw_side_quantums_before, 100)
        self.assertEqual(entry.opposite_side_quantums_before, 0)
        self.assertEqual(
            entry.score_numerator_signed,
            ded.DexAdlSignedValue(ded.DexAdlSign.POSITIVE, 25),
        )
        self.assertEqual(entry.score_denominator, 10)
        self.assertEqual(
            entry.execution_status,
            ded.DexAdlExecutionStatus.EXECUTED,
        )
        self.assertEqual(entry.executed_quantums, 100)
        self.assertEqual(
            entry.realized_pnl_signed,
            ded.DexAdlSignedValue(ded.DexAdlSign.POSITIVE, 5),
        )
        self.assertEqual(entry.skip_reason_code, ded.DexAdlSkipReasonCode.NONE)
        self.assertIsNone(event.vault_takeover_fill)

        self.assertEqual(
            event.input_snapshot_hash.hex(),
            "6a9995b5728f36d9be1d3eb938d70b870cae58d67ab55d67fca8e5c78cc94695",
        )
        self.assertEqual(
            event.selected_prefix_hash.hex(),
            "de0577166437665ee8f2633a7396c5ecc8b64bac06bb1e48cd39ea30275a5c1e",
        )
        self.assertEqual(
            event.execution_fills_digest.hex(),
            "a4940d4c7af06ad8177394eda04e4bd6711176fc9b67ce32dedf251a31da45e2",
        )

    def test_signed_value_rejects_negative_zero(self) -> None:
        positive_five = "0105000000000000000000000000000000"
        negative_zero = "0200000000000000000000000000000000"
        malformed = _DIRECT_SINGLETON_V5_GOLDEN_HEX.replace(
            positive_five,
            negative_zero,
            1,
        )

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, malformed)

        self.assertIsNone(decoded)

    def test_direct_and_execution_batch_preserves_order_and_indexes(self) -> None:
        decoded = ded.decode_transaction_events(
            [
                {"type": "0x1::coin::Deposit", "data": "0x00"},
                {"type": _DIRECT_ADL_TAG, "data": _matching_direct_source_v5_hex()},
                {
                    "type": _ADL_EXECUTION_TAG,
                    "data": _DIRECT_SINGLETON_V5_GOLDEN_HEX,
                },
            ]
        )

        self.assertEqual(
            [item.event_type for item in decoded],
            ["LiquidationDirectAdlEvent", "AdlExecutionEvent"],
        )
        self.assertEqual([item.index for item in decoded], [1, 2])
        direct = decoded[0].event
        execution = decoded[1].event
        locator = (
            execution.selected_prefix_header.source_locator.direct_liquidation_locator
        )
        assert locator is not None
        self.assertEqual(locator.flow_instance_id, direct.flow_instance_id)
        self.assertEqual(locator.action_seq, direct.action_seq)

    def test_truncated_execution_does_not_drop_valid_batch_neighbor(self) -> None:
        decoded = ded.decode_transaction_events(
            [
                {"type": _DIRECT_ADL_TAG, "data": _matching_direct_source_v5_hex()},
                {
                    "type": _ADL_EXECUTION_TAG,
                    "data": _DIRECT_SINGLETON_V5_GOLDEN_HEX[:-2],
                },
                {"type": "0x1::coin::Deposit", "data": "0x00"},
            ]
        )

        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0].index, 0)
        self.assertEqual(decoded[0].event_type, "LiquidationDirectAdlEvent")

    def test_two_pass_golden_preserves_execution_passes_and_signed_pnl(
        self,
    ) -> None:
        (payload,) = _catalog_chunks("two_pass")

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, payload)

        assert decoded is not None
        entries = decoded.event.audit_entries
        self.assertEqual(
            [entry.execution_pass for entry in entries],
            [
                ded.DexAdlExecutionPass.NET_EXPOSURE,
                ded.DexAdlExecutionPass.HEDGE_UNWIND,
            ],
        )
        self.assertEqual(
            [entry.realized_pnl_signed.abs_value for entry in entries],
            [1, 2],
        )
        self.assertEqual(
            [entry.execution_status for entry in entries],
            [
                ded.DexAdlExecutionStatus.EXECUTED,
                ded.DexAdlExecutionStatus.EXECUTED,
            ],
        )

    def test_skipped_boundary_golden_preserves_status_and_reason(self) -> None:
        (payload,) = _catalog_chunks("skipped_boundary")

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, payload)

        assert decoded is not None
        entries = decoded.event.audit_entries
        self.assertEqual(
            [entry.execution_status for entry in entries],
            [
                ded.DexAdlExecutionStatus.SKIPPED,
                ded.DexAdlExecutionStatus.EXECUTED,
                ded.DexAdlExecutionStatus.BOUNDARY,
            ],
        )
        self.assertEqual(
            [entry.skip_reason_code for entry in entries],
            [
                ded.DexAdlSkipReasonCode.BELOW_MIN_FILL_SIZE,
                ded.DexAdlSkipReasonCode.NONE,
                ded.DexAdlSkipReasonCode.NONE,
            ],
        )
        self.assertEqual(
            [entry.executed_quantums for entry in entries],
            [0, 10, 0],
        )

    def test_vault_takeover_golden_preserves_optional_final_fill(self) -> None:
        # The historical catalog's receipt includes the retired binding u64.
        # Use current chain bytes for this invariant, rather than rewriting it.
        payload = "0x" + _CURRENT_RECEIPT["bcs_hex"]

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, payload)

        assert decoded is not None
        event = decoded.event
        self.assertEqual(
            event.selected_prefix_header.stop_reason,
            ded.DexAdlStopReason.RANKED_PASSES_EXHAUSTED,
        )
        self.assertEqual(
            sum(entry.executed_quantums for entry in event.audit_entries),
            2,
        )
        vault = event.vault_takeover_fill
        assert vault is not None
        self.assertEqual(vault.schema_version, 5)
        self.assertEqual(vault.leftover_quantums, 4)
        self.assertEqual(vault.bankruptcy_subticks, 80)
        self.assertEqual(vault.fee_charged, 0)
        self.assertFalse(hasattr(vault, "vault_config_version"))
        # The retired independent-vault receipt is not the current fresh-chain layout.
        (old_payload,) = _catalog_chunks("vault_takeover")
        self.assertIsNone(ded.decode_dex_event(_ADL_EXECUTION_TAG, old_payload))

    def test_multi_chunk_batch_keeps_each_physical_event(self) -> None:
        chunks = _catalog_chunks("multi_chunk")
        transaction_events = [{"type": "0x1::coin::Deposit", "data": "0x00"}]
        transaction_events.extend(
            {"type": _ADL_EXECUTION_TAG, "data": chunk} for chunk in chunks
        )

        decoded = ded.decode_transaction_events(transaction_events)

        self.assertEqual(len(decoded), 3)
        self.assertEqual([item.index for item in decoded], [1, 2, 3])
        self.assertEqual(
            [item.event_type for item in decoded],
            ["AdlExecutionEvent"] * 3,
        )
        events = [item.event for item in decoded]
        self.assertEqual([event.chunk_index for event in events], [0, 1, 2])
        self.assertEqual([event.total_chunks for event in events], [3, 3, 3])
        self.assertEqual(
            [
                (
                    event.audit_entries_start_index,
                    event.audit_entries_end_index_exclusive,
                )
                for event in events
            ],
            [(0, 1), (1, 2), (2, 3)],
        )
        self.assertTrue(
            all(event.adl_event_id == events[0].adl_event_id for event in events)
        )
        self.assertTrue(
            all(
                event.selected_prefix_header == events[0].selected_prefix_header
                for event in events
            )
        )
        self.assertTrue(
            all(
                event.input_snapshot_hash == events[0].input_snapshot_hash
                for event in events
            )
        )
        self.assertTrue(
            all(
                event.selected_prefix_hash == events[0].selected_prefix_hash
                for event in events
            )
        )
        self.assertTrue(
            all(
                event.execution_fills_digest == events[0].execution_fills_digest
                for event in events
            )
        )
        self.assertTrue(
            all(
                not isinstance(entry, ded.DexFillEvent)
                for event in events
                for entry in event.audit_entries
            )
        )

    def test_complete_multi_chunk_set_passes_structural_validation(self) -> None:
        chunks = _decode_catalog_case("multi_chunk")

        result = ded.validate_adl_execution_event_chunks(chunks)

        self.assertIsNone(result)

    def test_wrong_event_schema_is_rejected(self) -> None:
        (payload,) = _catalog_chunks("direct_singleton")
        wrong_schema = _replace_uint(payload, 0, 2, 4)

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, wrong_schema)

        self.assertIsNone(decoded)

    def test_wrong_nested_schema_is_rejected(self) -> None:
        (payload,) = _catalog_chunks("direct_singleton")
        wrong_header_schema = _replace_uint(payload, 50, 2, 4)

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, wrong_header_schema)

        self.assertIsNone(decoded)

    def test_wrong_algorithm_version_is_rejected(self) -> None:
        (payload,) = _catalog_chunks("direct_singleton")
        # 3 is below the supported floor, 10 is above the current ceiling (v9).
        for unsupported in (3, 10):
            wrong_algorithm = _replace_uint(payload, 52, 8, unsupported)

            decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, wrong_algorithm)

            self.assertIsNone(decoded)

    def test_retired_source_kind_is_rejected(self) -> None:
        (payload,) = _catalog_chunks("direct_singleton")
        retired_source_kind = _replace_uint(payload, 84, 1, 1)

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, retired_source_kind)

        self.assertIsNone(decoded)

    def test_direct_source_without_locator_is_rejected(self) -> None:
        (chunk,) = _decode_catalog_case("direct_singleton")
        missing_locator = replace(
            chunk.selected_prefix_header.source_locator,
            direct_liquidation_locator=None,
        )
        malformed = replace(
            chunk,
            selected_prefix_header=replace(
                chunk.selected_prefix_header,
                source_locator=missing_locator,
            ),
        )

        with self.assertRaisesRegex(ValueError, "requires.*locator"):
            ded.validate_adl_execution_event_chunks((malformed,))

    def test_zero_total_chunks_is_rejected(self) -> None:
        (payload,) = _catalog_chunks("direct_singleton")
        zero_total_chunks = _replace_uint(payload, 26, 8, 0)

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, zero_total_chunks)

        self.assertIsNone(decoded)

    def test_chunk_index_out_of_range_is_rejected(self) -> None:
        (payload,) = _catalog_chunks("direct_singleton")
        out_of_range = _replace_uint(payload, 18, 8, 1)

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, out_of_range)

        self.assertIsNone(decoded)

    def test_reversed_audit_entry_range_is_rejected(self) -> None:
        (payload,) = _catalog_chunks("direct_singleton")
        reversed_range = _replace_uint(payload, 34, 8, 2)

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, reversed_range)

        self.assertIsNone(decoded)

    def test_audit_entry_range_length_mismatch_is_rejected(self) -> None:
        (payload,) = _catalog_chunks("direct_singleton")
        mismatched_range = _replace_uint(payload, 42, 8, 2)

        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, mismatched_range)

        self.assertIsNone(decoded)

    def test_audit_entry_indexes_must_match_declared_range(self) -> None:
        (chunk,) = _decode_catalog_case("direct_singleton")
        wrong_entry = replace(chunk.audit_entries[0], audit_entry_index=1)
        wrong_chunk = replace(chunk, audit_entries=(wrong_entry,))

        with self.assertRaisesRegex(ValueError, "audit entry indexes"):
            ded.validate_adl_execution_event_chunks((wrong_chunk,))

    def test_vault_takeover_is_only_allowed_on_final_chunk(self) -> None:
        decoded = ded.decode_dex_event(_ADL_EXECUTION_TAG, _CURRENT_RECEIPT["bcs_hex"])
        assert decoded is not None
        chunk = decoded.event
        assert isinstance(chunk, ded.DexAdlExecutionEvent)
        non_final_chunk = replace(chunk, chunk_index=0, total_chunks=2)

        with self.assertRaisesRegex(ValueError, "Vault takeover.*final chunk"):
            ded.validate_adl_execution_event_chunks((non_final_chunk,))

    def test_empty_chunk_set_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "chunk set must not be empty"):
            ded.validate_adl_execution_event_chunks(())

    def test_missing_chunk_is_rejected(self) -> None:
        chunks = _decode_catalog_case("multi_chunk")

        with self.assertRaisesRegex(ValueError, "complete physical chunk set"):
            ded.validate_adl_execution_event_chunks(chunks[:2])

    def test_duplicate_chunk_index_is_rejected(self) -> None:
        chunks = _decode_catalog_case("multi_chunk")
        duplicated = (chunks[0], chunks[0], chunks[2])

        with self.assertRaisesRegex(ValueError, "chunk indexes"):
            ded.validate_adl_execution_event_chunks(duplicated)

    def test_chunk_identity_mismatch_is_rejected(self) -> None:
        canonical = _decode_catalog_case("multi_chunk")
        second = canonical[1]
        mismatches = {
            "event id": replace(
                second,
                adl_event_id=replace(
                    second.adl_event_id,
                    trigger_index_in_block=1,
                ),
            ),
            "total chunks": replace(second, total_chunks=4),
            "header": replace(
                second,
                selected_prefix_header=replace(
                    second.selected_prefix_header,
                    price_version=0,
                ),
            ),
            "input snapshot": replace(second, input_snapshot_hash=bytes(32)),
            "selected prefix": replace(second, selected_prefix_hash=bytes(32)),
            "fill digest": replace(second, execution_fills_digest=bytes(32)),
        }

        for label, mismatched_second in mismatches.items():
            with self.subTest(label=label):
                chunks = (canonical[0], mismatched_second, canonical[2])
                with self.assertRaisesRegex(
                    ValueError,
                    "same logical ADL event",
                ):
                    ded.validate_adl_execution_event_chunks(chunks)

    def test_gap_between_chunk_audit_ranges_is_rejected(self) -> None:
        chunks = list(_decode_catalog_case("multi_chunk"))
        shifted_entry = replace(chunks[1].audit_entries[0], audit_entry_index=2)
        chunks[1] = replace(
            chunks[1],
            audit_entries_start_index=2,
            audit_entries_end_index_exclusive=3,
            audit_entries=(shifted_entry,),
        )

        with self.assertRaisesRegex(ValueError, "audit ranges must be contiguous"):
            ded.validate_adl_execution_event_chunks(chunks)


if __name__ == "__main__":
    unittest.main()

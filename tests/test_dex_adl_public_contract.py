# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Offline release contract for current-v5 ADL transaction events."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import intention_sdk
import intention_sdk.events.dex_event_decoder as dex_event_decoder
from intention_sdk import decode_transaction_events
from intention_sdk.events.dex_event_decoder import (
    DexAdlExecutionEvent,
    DexFillEvent,
    DexLiquidationDirectAdlEvent,
    DexLiquidationRiskTransferEvent,
    validate_adl_execution_event_chunks,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "test_fixtures"
_FIXTURE_PATH = _FIXTURE_DIR / "adl_v5_event_contract.json"
_CHAIN_EVENT_BCS_SHA256 = {
    "LiquidationRiskTransferEvent": (
        "c3caf2b157b7bee30299464bcdc6227262370ad7cbfc374d176e3088b8c516ba"
    ),
    "LiquidationDirectAdlEvent": (
        "c2ad734cbb2a141900b2eb6c1802ebba4484090804bbd48518a0b15115e05952"
    ),
    "AdlExecutionEvent": (
        "fa05287e60ec74403ce02b94a392f6c3d99ab203436e52fa46caba2fde5cc82d"
    ),
}
_ADL_PUBLIC_MODEL_NAMES = (
    "DexLiquidationTriggerMark",
    "DexLiquidationRiskTransferEvent",
    "DexLiquidationInternalOffsetEvent",
    "DexLiquidationFailedEvent",
    "DexLiquidationDirectAdlEvent",
    "DexAdlExecutionEvent",
    "DexAdlEventId",
    "DexAdlSelectedPrefixHeader",
    "DexAdlAuditEntry",
    "DexAdlVaultTakeoverFill",
    "DexAdlPositionKey",
    "DexAdlAccountLocator",
    "DexAdlQueueKey",
    "DexAdlSourceLocator",
    "DexAdlDirectLiquidationLocator",
    "DexAdlSignedValue",
)


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


class TestAdlV5PublicContract(unittest.TestCase):
    def test_fixture_pins_chain_schema_algorithm_and_source(self) -> None:
        fixture = _load_fixture()

        self.assertEqual(fixture["schemaVersion"], 5)
        self.assertEqual(fixture["algorithmVersion"], 4)
        self.assertEqual(
            fixture["source"]["case"],
            "cross_f15_same_block_activation_mixed_final_state",
        )
        chain_events = {
            item["type"].rsplit("::", 1)[-1]: item["data"]
            for item in fixture["events"]
            if item["type"].rsplit("::", 1)[-1] in _CHAIN_EVENT_BCS_SHA256
        }
        self.assertEqual(set(chain_events), set(_CHAIN_EVENT_BCS_SHA256))
        for event_type, payload in chain_events.items():
            with self.subTest(event_type=event_type):
                digest = hashlib.sha256(
                    bytes.fromhex(payload.removeprefix("0x"))
                ).hexdigest()
                self.assertEqual(digest, _CHAIN_EVENT_BCS_SHA256[event_type])

    def test_mixed_transaction_batch_preserves_known_order_and_indexes(
        self,
    ) -> None:
        fixture = _load_fixture()

        decoded = decode_transaction_events(fixture["events"])

        self.assertEqual(
            [item.index for item in decoded],
            fixture["expected"]["decodedIndexes"],
        )
        self.assertEqual(
            [item.event_type for item in decoded],
            fixture["expected"]["eventTypes"],
        )
        self.assertIsInstance(decoded[0].event, DexFillEvent)
        self.assertIsInstance(decoded[1].event, DexLiquidationRiskTransferEvent)
        self.assertIsInstance(decoded[2].event, DexLiquidationDirectAdlEvent)
        self.assertIsInstance(decoded[3].event, DexAdlExecutionEvent)
        fill = decoded[0].event
        assert isinstance(fill, DexFillEvent)
        self.assertFalse(fill.is_liquidation)

    def test_current_risk_transfer_coordinates_match_chain_golden(self) -> None:
        fixture = _load_fixture()
        decoded = decode_transaction_events(fixture["events"])
        risk_transfer = decoded[1].event
        assert isinstance(risk_transfer, DexLiquidationRiskTransferEvent)
        expected = fixture["expected"]["riskTransfer"]

        self.assertEqual(
            risk_transfer.source_residual_bound_quantums,
            expected["sourceResidualBoundQuantums"],
        )
        self.assertEqual(risk_transfer.block_height, expected["blockHeight"])
        self.assertEqual(risk_transfer.timestamp_us, expected["timestampUs"])
        self.assertEqual(risk_transfer.action_seq, expected["actionSeq"])
        self.assertEqual(risk_transfer.tx_index, expected["txIndex"])

    def test_direct_source_and_execution_identity_are_traceable(self) -> None:
        fixture = _load_fixture()
        decoded = decode_transaction_events(fixture["events"])
        direct = decoded[2].event
        execution = decoded[3].event
        assert isinstance(direct, DexLiquidationDirectAdlEvent)
        assert isinstance(execution, DexAdlExecutionEvent)
        expected_direct = fixture["expected"]["directAdl"]
        expected = fixture["expected"]["execution"]
        locator = (
            execution.selected_prefix_header.source_locator.direct_liquidation_locator
        )
        assert locator is not None

        self.assertEqual(direct.block_height, expected_direct["blockHeight"])
        self.assertEqual(direct.timestamp_us, expected_direct["timestampUs"])
        self.assertEqual(direct.action_seq, expected_direct["actionSeq"])
        self.assertEqual(direct.tx_index, expected_direct["txIndex"])
        self.assertEqual(locator.flow_instance_id, direct.flow_instance_id)
        self.assertEqual(locator.action_seq, direct.action_seq)
        self.assertEqual(locator.block_height, direct.block_height)
        self.assertEqual(
            execution.adl_event_id.trigger_block_height,
            expected["triggerBlockHeight"],
        )
        self.assertEqual(
            execution.adl_event_id.trigger_index_in_block,
            expected["triggerIndexInBlock"],
        )
        self.assertEqual(execution.chunk_index, expected["chunkIndex"])
        self.assertEqual(execution.total_chunks, expected["totalChunks"])
        self.assertEqual(
            execution.audit_entries_start_index,
            expected["auditEntriesStartIndex"],
        )
        self.assertEqual(
            execution.audit_entries_end_index_exclusive,
            expected["auditEntriesEndIndexExclusive"],
        )
        self.assertEqual(
            [entry.executed_quantums for entry in execution.audit_entries],
            expected["executedQuantums"],
        )
        self.assertIsNone(validate_adl_execution_event_chunks((execution,)))

    def test_live_chain_algorithm_v5_execution_event_decodes(self) -> None:
        """Algorithm version 5 superseded 4 on chain; both must stay decodable.

        The reference payload records an algorithm-version-5 AdlExecutionEvent.
        Its header layout matches the earlier layout, but the decoder must
        recognize the updated algorithm version.
        """
        fixture = json.loads(
            (
                _FIXTURE_DIR
                / "adl_execution_algorithm_v5.json"
            ).read_text(encoding="utf-8")
        )
        payload = fixture["event"]["data"]
        raw = bytes.fromhex(payload.removeprefix("0x"))
        self.assertEqual(len(raw), fixture["byteLength"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture["sha256"])

        decoded = decode_transaction_events(
            [{"type": fixture["event"]["type"], "data": payload}]
        )
        self.assertEqual(len(decoded), 1)
        event = decoded[0].event
        self.assertIsInstance(event, DexAdlExecutionEvent)
        self.assertEqual(event.schema_version, fixture["schemaVersion"])
        self.assertEqual(
            event.selected_prefix_header.algorithm_version,
            fixture["algorithmVersion"],
        )
        # Structural coherence: the chunk carries exactly the audit range it declares.
        self.assertEqual(
            len(event.audit_entries),
            event.audit_entries_end_index_exclusive - event.audit_entries_start_index,
        )
        self.assertIsNone(validate_adl_execution_event_chunks((event,)))

    def test_live_chain_algorithm_v6_execution_event_decodes(self) -> None:
        """The public decoder accepts the current ADL event contract."""
        fixture = json.loads(
            (
                _FIXTURE_DIR
                / "adl_execution_algorithm_v6.json"
            ).read_text(encoding="utf-8")
        )
        payload = fixture["event"]["data"]
        raw = bytes.fromhex(payload.removeprefix("0x"))
        self.assertEqual(len(raw), fixture["byteLength"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture["sha256"])

        decoded = decode_transaction_events(
            [{"type": fixture["event"]["type"], "data": payload}]
        )

        self.assertEqual(len(decoded), 1)
        event = decoded[0].event
        self.assertIsInstance(event, DexAdlExecutionEvent)
        assert isinstance(event, DexAdlExecutionEvent)
        self.assertEqual(event.schema_version, fixture["schemaVersion"])
        self.assertEqual(
            event.selected_prefix_header.algorithm_version,
            fixture["algorithmVersion"],
        )
        self.assertEqual(
            len(event.audit_entries),
            event.audit_entries_end_index_exclusive - event.audit_entries_start_index,
        )
        validate_adl_execution_event_chunks((event,))

    def test_live_chain_algorithm_v9_execution_event_decodes(self) -> None:
        """The public decoder accepts the current default-v9 chain ADL event contract."""
        fixture = json.loads(
            (
                _FIXTURE_DIR
                / "adl_execution_algorithm_v9.json"
            ).read_text(encoding="utf-8")
        )
        payload = fixture["event"]["data"]
        raw = bytes.fromhex(payload.removeprefix("0x"))
        self.assertEqual(len(raw), fixture["byteLength"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture["sha256"])

        decoded = decode_transaction_events(
            [{"type": fixture["event"]["type"], "data": payload}]
        )

        self.assertEqual(len(decoded), 1)
        event = decoded[0].event
        self.assertIsInstance(event, DexAdlExecutionEvent)
        assert isinstance(event, DexAdlExecutionEvent)
        self.assertEqual(event.schema_version, fixture["schemaVersion"])
        self.assertEqual(
            event.selected_prefix_header.algorithm_version,
            fixture["algorithmVersion"],
        )
        self.assertEqual(
            len(event.audit_entries),
            event.audit_entries_end_index_exclusive - event.audit_entries_start_index,
        )
        validate_adl_execution_event_chunks((event,))

    def test_adl_models_are_exported_from_root(self) -> None:
        self.assertIs(
            intention_sdk.decode_transaction_events, decode_transaction_events
        )
        for name in _ADL_PUBLIC_MODEL_NAMES:
            with self.subTest(name=name):
                self.assertIn(name, intention_sdk.__all__)
                self.assertIs(
                    getattr(intention_sdk, name),
                    getattr(dex_event_decoder, name),
                )


if __name__ == "__main__":
    unittest.main()

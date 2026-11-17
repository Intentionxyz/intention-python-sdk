# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-SDK contract for the shared TypeScript ADL execution fixture."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import intention_sdk
from intention_sdk.events.dex_event_decoder import DexAdlExecutionEvent

_FIXTURE_DIR = Path(__file__).resolve().parent / "test_fixtures"
_FIXTURE_PATH = _FIXTURE_DIR / "adl_execution_typescript.json"


def _load_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


class TestAdlCrossSdkContract(unittest.TestCase):
    def test_fixture_matches_frozen_typescript_payload(self) -> None:
        fixture = _load_fixture()
        raw = bytes.fromhex(fixture["event"]["data"].removeprefix("0x"))

        self.assertEqual(len(raw), fixture["byteLength"])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), fixture["sha256"])

    def test_typescript_payload_decodes_through_python_root_api(self) -> None:
        fixture = _load_fixture()
        expected = fixture["expected"]

        decoded = getattr(intention_sdk, "decode_transaction_events")(
            [fixture["event"]]
        )

        self.assertEqual(len(decoded), 1)
        self.assertEqual(decoded[0].event_type, expected["eventType"])
        event = decoded[0].event
        self.assertIsInstance(event, DexAdlExecutionEvent)
        assert isinstance(event, DexAdlExecutionEvent)
        self.assertEqual(event.schema_version, expected["schemaVersion"])
        self.assertEqual(
            event.selected_prefix_header.schema_version,
            expected["schemaVersion"],
        )
        self.assertEqual(
            event.selected_prefix_header.algorithm_version,
            expected["algorithmVersion"],
        )
        self.assertEqual(
            event.adl_event_id.trigger_block_height,
            expected["triggerBlockHeight"],
        )
        self.assertEqual(
            event.adl_event_id.trigger_index_in_block,
            expected["triggerIndexInBlock"],
        )
        self.assertEqual(event.chunk_index, expected["chunkIndex"])
        self.assertEqual(event.total_chunks, expected["totalChunks"])
        self.assertLess(event.chunk_index, event.total_chunks)
        self.assertEqual(
            len(event.audit_entries),
            event.audit_entries_end_index_exclusive - event.audit_entries_start_index,
        )

        direct = event.selected_prefix_header.source_locator.direct_liquidation_locator
        self.assertIsNotNone(direct)
        assert direct is not None
        self.assertEqual(len(direct.flow_instance_id), 32)
        for commitment in (
            event.input_snapshot_hash,
            event.selected_prefix_hash,
            event.execution_fills_digest,
        ):
            self.assertEqual(len(commitment), 32)


if __name__ == "__main__":
    unittest.main()

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Public contract for unified trading and ADL event decoding coexistence."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import intention_sdk

_FIXTURE_PATH = (
    Path(__file__).resolve().parent / "test_fixtures" / "adl_v5_event_contract.json"
)


class TestMainAdlCoexistence(unittest.IsolatedAsyncioTestCase):
    async def test_unified_client_and_adl_decoder_share_the_public_package(
        self,
    ) -> None:
        client_type = getattr(intention_sdk, "IntentionClient", None)
        self.assertIsNotNone(client_type)
        assert client_type is not None

        sdk = client_type(
            signer=intention_sdk.Account.generate(),
            node_url="http://localhost:8080/v1",
            relayer_url="http://localhost:3000",
            ws_url="ws://localhost:3000/ws",
        )
        self.addAsyncCleanup(sdk.close)

        fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
        decoded = intention_sdk.decode_transaction_events(fixture["events"])
        execution = next(
            item for item in decoded if item.event_type == "AdlExecutionEvent"
        ).event

        self.assertEqual(sdk.config.node_url, "http://localhost:8080/v1")
        self.assertEqual(execution.schema_version, fixture["schemaVersion"])
        self.assertEqual(
            execution.selected_prefix_header.algorithm_version,
            fixture["algorithmVersion"],
        )
        self.assertEqual(
            len(execution.audit_entries),
            execution.audit_entries_end_index_exclusive
            - execution.audit_entries_start_index,
        )


if __name__ == "__main__":
    unittest.main()

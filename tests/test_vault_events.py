# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import json
import unittest
from pathlib import Path

import intention_sdk
from intention_sdk.events.dex_event_decoder import (
    decode_dex_event_data,
    decode_transaction_events,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestVaultEvents(unittest.TestCase):
    def test_core_bcs_golden_decodes_as_typed_public_event(self):
        fixture = json.loads((FIXTURES / "vault_internal_offset_v1.json").read_text())
        result = decode_dex_event_data(
            "0x1::dex::VaultInternalOffsetEvent", fixture["bcs_hex"]
        )
        self.assertIsNotNone(result, "SDK must recognize the new core event")
        self.assertIsInstance(result.event, intention_sdk.DexVaultInternalOffsetEvent)
        data = {
            field["name"]: (
                "0x" + field["value"] if field["type"] == "address" else field["value"]
            )
            for field in fixture["fields"]
        }
        self.assertEqual(
            result, decode_dex_event_data("0x1::dex::VaultInternalOffsetEvent", data)
        )
        self.assertEqual(result.event.quantums, 2)
        self.assertEqual(result.event.total_realized_pnl_bits - (1 << 128), -40)

    def test_offset_schema_precision_and_malformed_transport(self):
        fixture = json.loads((FIXTURES / "vault_internal_offset_v1.json").read_text())
        tag = "0x1::dex::VaultInternalOffsetEvent"
        data = {f["name"]: "0x" + f["value"] if f["type"] == "address" else f["value"] for f in fixture["fields"]}
        for key, value in [("schema_version", "2"), ("status", 4), ("quantums", -1), ("quantums", True), ("quantums", 1.5), ("quantums", str(1 << 64)), ("total_fee", str(1 << 128)), ("vault_account", "0xGG"), ("extra", 1)]:
            self.assertIsNone(decode_dex_event_data(tag, {**data, key: value}), (key, value))
        for raw in [fixture["bcs_hex"][:-2], fixture["bcs_hex"] + "00", fixture["bcs_hex"] + "f", fixture["bcs_hex"] + "GG"]:
            self.assertIsNone(decode_dex_event_data(tag, raw))
        wide = decode_dex_event_data(tag, {**data, "quantums": str((1 << 64) - 1), "total_fee": str((1 << 128) - 1)})
        self.assertEqual(wide.event.quantums, (1 << 64) - 1)
        self.assertEqual(wide.event.total_fee, (1 << 128) - 1)
        for status in range(4):
            self.assertEqual(decode_dex_event_data(tag, {**data, "status": status}).event.status, status)
        events = [{"type": "0x1::coin::Other", "data": "00"}, {"type": tag, "data": fixture["bcs_hex"]}]
        self.assertEqual([event.index for event in decode_transaction_events(events)], [1])

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Current chain ADL bytes, read through the refactored public Python package."""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from pathlib import Path

from intention_sdk import DexAdlExecutionEvent, DexSystemAccounts, decode_dex_event


FIXTURES = Path(__file__).with_name("test_fixtures")


class CurrentAdlContract(unittest.TestCase):
    def test_system_account_public_value_uses_single_receiver(self) -> None:
        accounts = DexSystemAccounts.from_json({"liquidationTakeoverAddress": "0x11"})
        self.assertEqual(asdict(accounts), {"liquidation_takeover_address": "0x11"})

    def test_current_chain_remainders_use_the_liquidation_vault(self) -> None:
        # Expected quantities come from the checked-in reference event fixtures.
        fixture = json.loads((FIXTURES / "adl_unified_remainder_v9.json").read_text())
        source_owners = set()
        for chunk in fixture["chunks"]:
            with self.subTest(target=chunk["target_quantums"]):
                decoded = decode_dex_event(
                    "0x1::dex::AdlExecutionEvent", chunk["bcs_hex"]
                )
                self.assertIsNotNone(decoded)
                assert decoded is not None
                event = decoded.event
                self.assertIsInstance(event, DexAdlExecutionEvent)
                assert isinstance(event, DexAdlExecutionEvent)
                source_owners.add(
                    event.selected_prefix_header.source_risk_holder.owner_address
                )
                self.assertEqual(
                    str(event.selected_prefix_header.total_executed_quantums),
                    chunk["target_quantums"],
                )
                receipt = event.vault_takeover_fill
                self.assertIsNotNone(receipt)
                assert receipt is not None
                self.assertEqual(
                    str(receipt.leftover_quantums), chunk["vault_takeover_quantums"]
                )
                self.assertEqual(
                    str(receipt.bankruptcy_subticks), chunk["bankruptcy_subticks"]
                )
                self.assertEqual(
                    int(receipt.vault_account.owner_address, 16),
                    int(fixture["liquidation_vault_address"], 16),
                )
        self.assertEqual(len(source_owners), 2)

    def test_current_tail_preserves_real_hedge_closes_before_the_vault(self) -> None:
        fixture = json.loads(
            (FIXTURES / "adl_liquidation_vault_tail_v9.json").read_text()
        )
        for chunk in fixture["chunks"]:
            decoded = decode_dex_event("0x1::dex::AdlExecutionEvent", chunk["bcs_hex"])
            self.assertIsNotNone(decoded)
            assert decoded is not None
            event = decoded.event
            assert isinstance(event, DexAdlExecutionEvent)
            filled = [
                entry for entry in event.audit_entries if entry.executed_quantums > 0
            ]
            self.assertTrue(any(entry.execution_pass == 2 for entry in filled[:-1]))
            tail = filled[-1]
            self.assertEqual(
                int(tail.position_key.account.owner_address, 16),
                int(fixture["liquidation_vault_address"], 16),
            )
            self.assertEqual(
                (tail.score_numerator_signed.abs_value, tail.score_denominator), (0, 0)
            )

    def test_current_receipt_rejects_truncated_or_trailing_bytes(self) -> None:
        fixture = json.loads((FIXTURES / "adl_unified_remainder_v9.json").read_text())
        payload = fixture["chunks"][0]["bcs_hex"]
        self.assertIsNone(decode_dex_event("0x1::dex::AdlExecutionEvent", payload[:-2]))
        self.assertIsNone(
            decode_dex_event("0x1::dex::AdlExecutionEvent", payload + "00")
        )

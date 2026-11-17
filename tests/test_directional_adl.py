import json
import unittest
from pathlib import Path
from intention_sdk.events.dex_event_decoder import decode_dex_event


class CurrentDirectionalAdlReader(unittest.TestCase):
    def test_reads_actual_chain_tail_and_receipt(self):
        for name in ('adl_liquidation_vault_tail_v9', 'adl_unified_remainder_v9'):
            fixture = json.loads((Path(__file__).parent / 'test_fixtures' / (name + '.json')).read_text())
            source_owners = set()
            for index, chunk in enumerate(fixture['chunks']):
                decoded = decode_dex_event('0x1::dex::AdlExecutionEvent', chunk['bcs_hex'])
                self.assertIsNotNone(decoded)
                event = decoded.event
                self.assertEqual(event.selected_prefix_header.algorithm_version, 9)
                header = event.selected_prefix_header
                source_side = 2 if name == 'adl_unified_remainder_v9' and index == 1 else 1
                self.assertEqual(header.source_position_key.position_side, source_side)
                self.assertEqual(header.queue_key.opponent_side, 3 - source_side)
                source_owners.add(header.source_risk_holder.owner_address)
                self.assertEqual(str(header.total_executed_quantums), chunk['target_quantums'])
                if name == 'adl_liquidation_vault_tail_v9':
                    filled = [entry for entry in event.audit_entries if entry.executed_quantums > 0]
                    tail = filled[-1]
                    self.assertTrue(any(entry.execution_pass == 2 for entry in filled[:-1]), 'ordinary hedge closes before Vault')
                    self.assertEqual(int(tail.position_key.account.owner_address, 16), int(fixture['liquidation_vault_address'], 16))
                    self.assertEqual((tail.score_numerator_signed.abs_value, tail.score_denominator), (0, 0))
                if chunk['vault_takeover_quantums'] is not None:
                    self.assertEqual(str(event.vault_takeover_fill.leftover_quantums), chunk['vault_takeover_quantums'])
                    self.assertEqual(int(event.vault_takeover_fill.vault_account.owner_address, 16), int(fixture['liquidation_vault_address'], 16))
                    self.assertEqual(str(event.vault_takeover_fill.bankruptcy_subticks), chunk['bankruptcy_subticks'])
            if name == 'adl_unified_remainder_v9':
                self.assertEqual(len(source_owners), 2, 'receipts retain two distinct sources')

    def test_system_identity_has_no_independent_binding(self):
        from dataclasses import asdict
        from intention_sdk.api.dex_account_client import DexSystemAccounts
        accounts = DexSystemAccounts.from_json({'liquidationTakeoverAddress': '0x11'})
        self.assertEqual(asdict(accounts), {'liquidation_takeover_address': '0x11'})

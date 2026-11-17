# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import json
import unittest
from pathlib import Path

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.events.events import decode_account_transfer_event

_FIXTURE = Path(__file__).resolve().parent / "test_fixtures" / "phase3_event_parity.json"


class TestPhase3EventFixture(unittest.TestCase):
    """The checked-in event fixture decodes into the values it states.

    Only the offline example read this fixture, and it printed what it decoded
    without comparing it, so when AccountTransferEvent gained to_subaccount the
    fixture kept the old layout and nothing said so until the example crashed.
    """

    def test_account_transfer_decodes_into_its_expected_values(self) -> None:
        with _FIXTURE.open("r", encoding="utf-8") as fixture_file:
            fixture = json.load(fixture_file)["single_events"]["decode_account_transfer_event"]

        event = decode_account_transfer_event(bytes.fromhex(fixture["hex"]))

        self.assertIsNotNone(event.fee_account)
        # Addresses compare as addresses: the fixture writes the zero subaccount as 0x0.
        expected = dict(fixture["expected"])
        for field in ("from_account", "to_account", "to_subaccount", "fee_account"):
            expected[field] = AccountAddress.from_str(expected[field])
        decoded = {
            "from_account": event.from_account,
            "to_account": event.to_account,
            "to_subaccount": event.to_subaccount,
            "asset_id": str(event.asset_id),
            "original_amount": str(event.original_amount),
            "net_amount": str(event.net_amount),
            "fee_amount": str(event.fee_amount),
            "fee_account": event.fee_account,
        }
        self.assertEqual(decoded, expected)


if __name__ == "__main__":
    unittest.main()

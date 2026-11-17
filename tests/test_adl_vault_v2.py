# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import unittest
from pathlib import Path

import intention_sdk

from intention_sdk.api.dex_account_client import DexSystemAccounts
from intention_sdk.events.dex_event_decoder import (
    DexAdlVaultInitializedEvent,
    decode_dex_event,
)


_FIXTURE = json.loads(
    (Path(__file__).with_name("test_fixtures") / "adl_vault_v2_chain.json").read_text()
)


class TestAdlVaultV2Contract(unittest.TestCase):
    def test_current_system_identity_and_historical_binding_event_are_typed(
        self,
    ) -> None:
        accounts = DexSystemAccounts.from_json(
            {
                "liquidationTakeoverAddress": "0x11",
                "adlVaultAddress": None,
                "adlVaultConfigVersion": None,
            }
        )
        self.assertEqual(accounts.liquidation_takeover_address, "0x11")

        decoded = decode_dex_event(
            "0x1::dex::AdlVaultInitializedEvent",
            "0x" + _FIXTURE["bindingEventBcsHex"],
        )
        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertIsInstance(decoded.event, DexAdlVaultInitializedEvent)
        event = decoded.event
        assert isinstance(event, DexAdlVaultInitializedEvent)
        self.assertEqual(event.vault_address, _FIXTURE["vaultAddress"])
        self.assertEqual(event.vault_config_version, 2)

    def test_retired_independent_vault_execution_is_not_a_current_receipt(self) -> None:
        decoded = decode_dex_event(
            "0x1::dex::AdlExecutionEvent",
            "0x" + _FIXTURE["executionEventBcsHex"],
        )
        # This historical execution includes the removed binding-version u64.
        # The fresh-chain current receipt must not silently interpret those bytes
        # as quantity/price. Current chain golden coverage lives in the new tests.
        self.assertIsNone(decoded)

    def test_v2_types_are_root_exports(self) -> None:
        for name in (
            "DexSystemAccounts",
            "DexAdlVaultInitializedEvent",
        ):
            self.assertTrue(hasattr(intention_sdk, name), name)


if __name__ == "__main__":
    unittest.main()

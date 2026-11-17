# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import unittest

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.bcs import Serializer, Deserializer
from intention_sdk.transactions.dex_payloads import (RegisterReferralCode, BindReferrer,
    ClaimReferralRewards, ReferralParameters, SetReferralConfig, DexUserConfigTx, DexOrderlessTx)
from intention_sdk.types.enums import DexUserConfigTxVariant, DexOrderlessTxVariant
from intention_sdk.transactions.json_submit import _dex_orderless_nonce


def encoded(value):
    serializer = Serializer()
    value.serialize(serializer)
    return serializer.to_bytes()


class ReferralTest(unittest.TestCase):
    def test_chain_wire_vectors_and_nonce(self):
        actions = [
            DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, DexUserConfigTx(
                DexUserConfigTxVariant.REGISTER_REFERRAL_CODE, RegisterReferralCode(123, "ABC123"))),
            DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, DexUserConfigTx(
                DexUserConfigTxVariant.BIND_REFERRER, BindReferrer(123, "ABC123"))),
            DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, ClaimReferralRewards(123)),
            DexOrderlessTx(DexOrderlessTxVariant.DEX_SYSTEM_CONFIG, SetReferralConfig(123,
                ReferralParameters(40_000, 100_000, 1_000_000_000, 25_000_000_000, 1_000_000_000_000_000, 1_000_000))),
        ]
        vectors = [
            "01067b0000000000000006414243313233",
            "01077b0000000000000006414243313233",
            "03047b0000000000000000",
            "02247b00000000000000409c0000a086010000ca9a3b0000000000ba1dd2050000000080c6a47e8d030040420f000000000000",
        ]
        for i, action in enumerate(actions):
            with self.subTest(action=i):
                self.assertEqual(encoded(action).hex(), vectors[i])
                self.assertEqual(_dex_orderless_nonce(action), 123)
                if i < 3:
                    self.assertEqual(encoded(DexOrderlessTx.deserialize(Deserializer(encoded(action)))), encoded(action))

    def test_codes_and_claim_validation(self):
        self.assertNotEqual(encoded(RegisterReferralCode(1, "ABC123")), encoded(RegisterReferralCode(1, "abc123")))
        for code in ["short", "ABCDE_"]:
            with self.assertRaises(ValueError):
                RegisterReferralCode(1, code)
        with self.assertRaises(TypeError):
            ClaimReferralRewards(1, 1_000_000, [])

    def test_claimall_agent_and_json_wire(self):
        from intention_sdk.transactions.json_submit import _render_dex_transfer_payload
        master = AccountAddress.from_str("0x1")
        claim = ClaimReferralRewards(2**64 - 1, on_behalf_of=master)
        self.assertEqual(encoded(claim).hex(), "04" + "ff" * 8 + "01" + "00" * 31 + "01")
        parsed = DexOrderlessTx.deserialize(Deserializer(bytes.fromhex("03") + encoded(claim)))
        self.assertEqual(parsed.inner.on_behalf_of, master)
        payload = _render_dex_transfer_payload(claim)
        self.assertEqual(payload["nonce"], str(2**64 - 1))
        self.assertEqual(payload["on_behalf_of"], str(master))
        self.assertNotIn("amount", payload)
        self.assertNotIn("sources", payload)
        with self.assertRaises(Exception):
            encoded(ClaimReferralRewards(2**64))

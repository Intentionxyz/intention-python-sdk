# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The chain's variant numbering for the payload slot, the orderless envelope and
its gated payloads.

The expected numbers are written out rather than derived from the enums, so a
renumbering fails here instead of agreeing with itself. These numberings are
consensus critical: they are BCS variant tags, and ``16 + tag`` is the kind byte
an ``Execute`` binds into the operation id the owners sign.
"""

from __future__ import annotations

import unittest

import intention_sdk
import intention_sdk.types
from intention_sdk.bcs import Deserializer, Serializer
from intention_sdk.transactions.dex_payloads import (
    CreateSubAccount,
    DexAgentTx,
    DexOrderlessTx,
    DexTransferTx,
    InternalTransferItem,
    RawOrderlessInner,
    TransactionPayload,
)
from intention_sdk.transactions.multisig_payloads import (
    GatedPayload,
    MultisigOpExecute,
    op_kind_byte,
)
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.types.enums import (
    AccountType,
    DexOrderlessTxVariant,
    DexTransferVariant,
    GatedPayloadVariant,
    TransactionPayloadVariants,
)


def _bcs(value) -> bytes:
    serializer = Serializer()
    value.serialize(serializer)
    return serializer.to_bytes()


class TransactionPayloadNumberingTest(unittest.TestCase):
    def test_payload_variants_match_the_chain(self) -> None:
        # Tag 1 (ModuleBundle) is deprecated on chain and deliberately absent.
        self.assertEqual(
            {variant.name: int(variant) for variant in TransactionPayloadVariants},
            {
                "SCRIPT": 0,
                "ENTRY_FUNCTION": 2,
                "MULTISIG": 3,
                "PAYLOAD": 4,
                "DEX_ORDERLESS": 5,
            },
        )

    def test_the_payload_slot_writes_the_orderless_tag(self) -> None:
        self.assertEqual(TransactionPayload.DEX_ORDERLESS, 5)
        payload = TransactionPayload(
            DexOrderlessTx(DexOrderlessTxVariant.DEX_AGENT, RawOrderlessInner(b"\x77"))
        )
        self.assertEqual(_bcs(payload).hex(), "050477")

    def test_the_phantom_config_enum_is_gone(self) -> None:
        # DexConfigTxVariant (USER_CONFIG=0, SYSTEM_CONFIG=1) never matched any
        # chain enum; DexOrderlessTxVariant carries the real tags.
        self.assertFalse(hasattr(intention_sdk, "DexConfigTxVariant"))
        self.assertFalse(hasattr(intention_sdk.types, "DexConfigTxVariant"))
        self.assertNotIn("DexConfigTxVariant", intention_sdk.__all__)


class OrderlessVariantNumberingTest(unittest.TestCase):
    def test_orderless_variants_match_the_chain(self) -> None:
        self.assertEqual(
            {variant.name: int(variant) for variant in DexOrderlessTxVariant},
            {
                "DEX": 0,
                "DEX_USER_CONFIG": 1,
                "DEX_SYSTEM_CONFIG": 2,
                "DEX_TRANSFER": 3,
                "DEX_AGENT": 4,
                "MULTISIG": 5,
                "VALIDATOR": 6,
            },
        )

    def test_the_variant_is_the_first_byte_of_the_envelope(self) -> None:
        for variant, tag in (
            (DexOrderlessTxVariant.DEX_AGENT, "04"),
            (DexOrderlessTxVariant.MULTISIG, "05"),
        ):
            with self.subTest(variant=variant):
                envelope = DexOrderlessTx(variant, RawOrderlessInner(b"\x77"))
                self.assertEqual(_bcs(envelope).hex(), tag + "77")

    def test_orderless_decoding_rejects_the_variants_it_does_not_model(self) -> None:
        # 2 and 6 exist on the chain but are built elsewhere; 7 exists nowhere.
        for tag in (2, 6, 7):
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    DexOrderlessTx.deserialize(Deserializer(bytes([tag, 0x00])))


class GatedPayloadNumberingTest(unittest.TestCase):
    def test_gated_variants_match_the_chain(self) -> None:
        self.assertEqual(
            {variant.name: int(variant) for variant in GatedPayloadVariant},
            {
                "DEX_TRANSFER": 0,
                "DEX_AGENT": 1,
                "CREATE_SUB_ACCOUNT": 2,
                "VALIDATOR": 3,
            },
        )

    def test_an_execute_binds_sixteen_plus_the_gated_variant(self) -> None:
        transfer = DexTransferTx(
            1,
            DexTransferVariant.INTERNAL_TRANSFER,
            [
                InternalTransferItem(
                    AccountAddress(b"\x00" * 32),
                    AccountAddress(b"\x00" * 31 + b"\x01"),
                    0,
                    1,
                    AccountType.PERP,
                )
            ],
        )
        for gated, kind in (
            (GatedPayload.transfer(transfer), 16),
            (GatedPayload.agent(DexAgentTx.revoke_all(2)), 17),
            (GatedPayload.create_sub_account(CreateSubAccount(3, "desk")), 18),
        ):
            with self.subTest(kind=kind):
                self.assertEqual(op_kind_byte(MultisigOpExecute(gated)), kind)

    def test_gated_payloads_round_trip_under_their_tags(self) -> None:
        for gated, tag in (
            (GatedPayload.agent(DexAgentTx.revoke_all(2)), 1),
            (GatedPayload.create_sub_account(CreateSubAccount(3, "desk")), 2),
        ):
            with self.subTest(tag=tag):
                encoded = _bcs(gated)
                self.assertEqual(encoded[0], tag)
                decoded = GatedPayload.deserialize(Deserializer(encoded))
                self.assertEqual(decoded.variant, gated.variant)
                self.assertEqual(_bcs(decoded), encoded)

    def test_gated_decoding_rejects_every_other_variant(self) -> None:
        # 3 is the validator payload, which this SDK does not model; 4 and up are
        # undefined. Neither may fall through into one of the modelled payloads.
        for tag in (3, 4, 127):
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError):
                    GatedPayload.deserialize(Deserializer(bytes([tag, 0x00])))


if __name__ == "__main__":
    unittest.main()

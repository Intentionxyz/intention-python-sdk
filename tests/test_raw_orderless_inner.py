# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The orderless seam and the proof that rides its envelope.

Both are cross-language contracts with
``intention_types::transaction::dex_sys_config``. The assertions are on raw bytes
rather than round trips, so they fail when either side of the contract moves
instead of agreeing with whatever this encoder currently does.
"""

from __future__ import annotations

import unittest

from intention_sdk.bcs import Serializer
from intention_sdk.transactions.dex_payloads import (
    BridgeSignature,
    DexOrderlessTx,
    MultiSigProof,
    RawOrderlessInner,
)
from intention_sdk.types.enums import DexOrderlessTxVariant


def _serialize(value) -> str:
    serializer = Serializer()
    value.serialize(serializer)
    return serializer.to_bytes().hex()


def _leading(byte: int) -> bytes:
    return bytes([byte]) + b"\x00" * 31


class MultiSigProofTest(unittest.TestCase):
    def test_expiry_sits_between_the_digest_and_the_signatures(self) -> None:
        """Pins the expiry's position.

        Omitting the field is not a graceful degradation: the chain reads the
        signature vector's length prefix as the u64's first byte and rejects the
        transaction with an error naming neither the field nor the side that
        differs.
        """
        proof = MultiSigProof(
            op_digest=b"\x11" * 32,
            expires_at_secs=0x0102030405060708,
            signatures=[BridgeSignature(r=_leading(0xAA), s=_leading(0xBB), v=27)],
        )

        self.assertEqual(
            _serialize(proof),
            "11" * 32  # op_digest
            + "0807060504030201"  # expires_at_secs, u64 little-endian
            + "01"  # signatures: uleb128 length
            + "aa" + "00" * 31  # r
            + "bb" + "00" * 31  # s
            + "1b",  # v = 27
        )

    def test_round_trip(self) -> None:
        proof = MultiSigProof(
            op_digest=b"\x5e" * 32,
            expires_at_secs=99,
            signatures=[BridgeSignature(r=_leading(0xA1), s=_leading(0xB2), v=28)],
        )
        from intention_sdk.bcs import Deserializer

        decoded = MultiSigProof.deserialize(
            Deserializer(bytes.fromhex(_serialize(proof)))
        )
        self.assertEqual(decoded.op_digest, proof.op_digest)
        self.assertEqual(decoded.expires_at_secs, proof.expires_at_secs)
        self.assertEqual(len(decoded.signatures), 1)
        self.assertEqual(decoded.signatures[0].v, 28)

    def test_rejects_a_digest_that_is_not_32_bytes(self) -> None:
        with self.assertRaises(ValueError):
            MultiSigProof(op_digest=b"\x11" * 31, expires_at_secs=0, signatures=[])


class RawOrderlessInnerTest(unittest.TestCase):
    def test_writes_the_body_verbatim(self) -> None:
        """Nothing may be added around the body -- no length prefix, no padding.

        The caller computes signatures over bytes it serialized itself, so a byte
        this module inserts is a byte no signer covered.
        """
        tx = DexOrderlessTx(
            DexOrderlessTxVariant.DEX_AGENT,
            RawOrderlessInner(bytes([0xDE, 0xAD, 0xBE, 0xEF])),
        )

        self.assertEqual(_serialize(tx), "04" + "deadbeef")

    def test_carries_the_system_config_proof_slot(self) -> None:
        """The proof slot follows from the variant.

        This is the whole reason the type exists: a caller that models a
        system-config operation itself still gets somewhere to put its multisig.
        """
        inner = RawOrderlessInner(bytes([0x01, 0x02]))

        self.assertEqual(
            _serialize(DexOrderlessTx(DexOrderlessTxVariant.DEX_SYSTEM_CONFIG, inner)),
            "02" + "0102" + "00",  # Option::None
        )

        proof = MultiSigProof(
            op_digest=b"\x5e" * 32,
            expires_at_secs=0x0102030405060708,
            signatures=[BridgeSignature(r=_leading(0xA1), s=_leading(0xB2), v=27)],
        )

        self.assertEqual(
            _serialize(
                DexOrderlessTx(
                    DexOrderlessTxVariant.DEX_SYSTEM_CONFIG, inner, multi_sig_proof=proof
                )
            ),
            "02"
            + "0102"
            + "01"  # Option::Some
            + "5e" * 32
            + "0807060504030201"
            + "01"
            + "a1" + "00" * 31
            + "b2" + "00" * 31
            + "1b",
        )

    def test_adds_no_proof_to_other_variants(self) -> None:
        """The Option belongs to DexSystemConfig alone.

        Writing it for the transfer path would break the one that already worked.
        """
        proof = MultiSigProof(op_digest=b"\x5e" * 32, expires_at_secs=0, signatures=[])

        for variant in (
            DexOrderlessTxVariant.DEX,
            DexOrderlessTxVariant.DEX_USER_CONFIG,
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexOrderlessTxVariant.DEX_AGENT,
            DexOrderlessTxVariant.VAULT,
        ):
            with self.subTest(variant=variant):
                got = _serialize(
                    DexOrderlessTx(
                        variant, RawOrderlessInner(bytes([0x77])), multi_sig_proof=proof
                    )
                )
                self.assertTrue(
                    got.endswith("77"),
                    "variant %s grew something after the body: %s" % (variant, got),
                )

    def test_default_is_none_so_existing_callers_are_unchanged(self) -> None:
        """A caller that never heard of the proof still encodes Option::None."""
        tx = DexOrderlessTx(
            DexOrderlessTxVariant.DEX_SYSTEM_CONFIG, RawOrderlessInner(b"\x09")
        )
        self.assertIsNone(tx.multi_sig_proof)
        self.assertTrue(_serialize(tx).endswith("00"))


if __name__ == "__main__":
    unittest.main()

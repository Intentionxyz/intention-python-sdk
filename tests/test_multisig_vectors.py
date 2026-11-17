# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Multisig signing against checked-in reference vectors.

Operations are rebuilt from the recorded inputs, then compared with the expected
bytes and digests. This checks payload construction as well as hashing.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import List

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.bcs import Deserializer, Serializer
from intention_sdk.transactions.dex_payloads import (
    AccountTransferItem,
    AgentApprove,
    AgentRevoke,
    BridgeSignature,
    CreateSubAccount,
    CrossTransferItem,
    DexAgentTx,
    DexOrderlessTx,
    DexTransferTx,
    InternalTransferItem,
)
from intention_sdk.types.enums import (
    AccountType,
    AgentOperationVariant,
    CrossTransferOption,
    DexOrderlessTxVariant,
    DexTransferVariant,
    MultisigOpVariant,
)
from intention_sdk.transactions.typed_data import domain_separator
from intention_sdk.transactions.multisig_payloads import (
    DexMultisigTx,
    GatedPayload,
    KeyProofEd25519,
    MultisigOp,
    MultisigOpCreate,
    MultisigOpExecute,
    MultisigOpInstall,
    MultisigOpRemove,
    MultisigOpRotateKey,
    MultisigOpUpdatePolicy,
    MultisigProof,
    multisig_operation_id,
    multisig_owners_digest,
    derive_multisig_account_address,
    op_kind_byte,
    submit_operation_name,
)
from intention_sdk.transactions.multisig_typed_data import (
    approval_digest,
    create_approval_digest,
    key_challenge_digest,
    submit_struct_hash,
)
from intention_sdk.transactions.vault_payloads import VaultDepositTx, VaultTx
from intention_sdk.types.vault import VaultTxVariant

_VECTORS = json.loads(
    (Path(__file__).parent / "testdata" / "multisig_signing_vectors.json").read_text()
)

CHAIN_ID = _VECTORS["chain_id"]
ACCOUNT = AccountAddress.from_str(_VECTORS["account"])
EPOCH = _VECTORS["authority_epoch"]
EXPIRES = _VECTORS["expires_at_secs"]


def _hex(value: bytes) -> str:
    return "0x" + value.hex()


def _bytes(value: str) -> bytes:
    return bytes.fromhex(value[2:] if value.startswith("0x") else value)


def _repeated(byte: int, length: int = 32) -> bytes:
    return bytes([byte]) * length


def _evm(byte: int) -> AccountAddress:
    return AccountAddress(b"\x00" * 12 + bytes([byte]) * 20)


def _bcs(value) -> bytes:
    serializer = Serializer()
    value.serialize(serializer)
    return serializer.to_bytes()


OWNERS = [_repeated(0xA1, 20), _repeated(0xA2, 20), _repeated(0xA3, 20)]


def _key_proof() -> KeyProofEd25519:
    return KeyProofEd25519(_repeated(0x02), bytes(64))


def _account_transfer(nonce: int, items) -> MultisigOpExecute:
    return MultisigOpExecute(
        GatedPayload.transfer(
            DexTransferTx(
                nonce,
                DexTransferVariant.ACCOUNT_TRANSFER,
                [
                    AccountTransferItem(_evm(to), 0, amount, AccountType.PERP)
                    for to, amount in items
                ],
            )
        )
    )


def _cross_transfer(nonce: int, option, items) -> MultisigOpExecute:
    return MultisigOpExecute(
        GatedPayload.transfer(
            DexTransferTx(
                nonce,
                DexTransferVariant.CROSS_TRANSFER,
                [
                    CrossTransferItem(_evm(to), 0, amount, AccountType.PERP)
                    for to, amount in items
                ],
                option,
            )
        )
    )


def _internal_transfer(nonce: int, items) -> MultisigOpExecute:
    return MultisigOpExecute(
        GatedPayload.transfer(
            DexTransferTx(
                nonce,
                DexTransferVariant.INTERNAL_TRANSFER,
                [
                    InternalTransferItem(
                        _evm(src), _evm(dst), 0, amount, AccountType.PERP
                    )
                    for src, dst, amount in items
                ],
            )
        )
    )


def every_operation() -> List[MultisigOp]:
    """The eighteen reference operations in fixture order, with explicit inputs."""
    return [
        MultisigOpCreate(OWNERS, 2, _repeated(0x00)),
        MultisigOpInstall(OWNERS, 2),
        MultisigOpUpdatePolicy(OWNERS, 3),
        MultisigOpRemove(_repeated(0x01), _key_proof()),
        MultisigOpRotateKey(_repeated(0x01), _key_proof()),
        _account_transfer(17, [(0x5A, 1_000_500_000)]),
        _account_transfer(18, [(0x5A, 1), (0x5B, 2)]),
        _cross_transfer(19, CrossTransferOption.BURN, [(0x6A, 5_000_000)]),
        _cross_transfer(20, CrossTransferOption.BURN, [(0x6A, 1), (0x6B, 2)]),
        # A mint credits a bridge deposit: not an owner's business, so no document.
        _cross_transfer(21, CrossTransferOption.MINT, [(0x6A, 1)]),
        _internal_transfer(22, [(0x11, 0x12, 7_250_000)]),
        _internal_transfer(23, [(0x11, 0x12, 1), (0x11, 0x13, 2)]),
        # Non-mainnet and meaningless on a policy account: no document.
        MultisigOpExecute(
            GatedPayload.transfer(
                DexTransferTx(
                    24,
                    DexTransferVariant.FAUCET_MINT,
                    [CrossTransferItem(_evm(0x11), 0, 1, AccountType.PERP)],
                )
            )
        ),
        MultisigOpExecute(
            GatedPayload.agent(
                DexAgentTx(
                    25,
                    AgentOperationVariant.APPROVE,
                    AgentApprove("market-maker", _evm(0x7A), 1_900_000_000),
                )
            )
        ),
        MultisigOpExecute(
            GatedPayload.agent(
                DexAgentTx(
                    26, AgentOperationVariant.REVOKE, AgentRevoke("market-maker")
                )
            )
        ),
        MultisigOpExecute(GatedPayload.agent(DexAgentTx.revoke_all(29))),
        MultisigOpExecute(GatedPayload.create_sub_account(CreateSubAccount(27, "treasury"))),
        MultisigOpExecute(
            GatedPayload.vault(
                VaultTx(VaultTxVariant.DEPOSIT, VaultDepositTx(3, 28, 10_000_000))
            )
        ),
    ]


class MultisigVectorsTest(unittest.TestCase):
    def test_the_fixture_is_the_version_this_sdk_implements(self) -> None:
        self.assertEqual(_VECTORS["authorization_version"], 1)
        self.assertEqual(len(_VECTORS["operations"]), 18)

    def test_the_domain_separator_is_the_one_the_chain_hashes(self) -> None:
        self.assertEqual(
            _hex(domain_separator(CHAIN_ID)), _VECTORS["domain"]["separator"]
        )

    def test_every_operation_reproduces_its_bytes_and_digests(self) -> None:
        operations = every_operation()
        for expected, op in zip(_VECTORS["operations"], operations):
            with self.subTest(expected["name"]):
                self.assertEqual(_hex(_bcs(op)), expected["op_bcs"], "operation BCS")
                self.assertEqual(op_kind_byte(op), expected["op_kind"], "kind byte")
                self.assertEqual(
                    submit_operation_name(op),
                    expected["submit_operation"],
                    "envelope operation name",
                )

                op_id = multisig_operation_id(CHAIN_ID, ACCOUNT, EPOCH, op, EXPIRES)
                self.assertEqual(_hex(op_id), expected["op_id"], "operation id")

                envelope = submit_struct_hash(
                    CHAIN_ID,
                    ACCOUNT,
                    op,
                    _VECTORS["submit_nonce"],
                    _bytes(_VECTORS["submit_txn_digest"]),
                )
                self.assertEqual(
                    _hex(envelope),
                    expected["submit_struct_hash"],
                    "envelope struct hash",
                )

                digest = approval_digest(
                    CHAIN_ID, ACCOUNT, EPOCH, op, EXPIRES, op_id
                )
                if expected["approval_digest"] is None:
                    # A refusal, not an omission: an operation whose fields cannot
                    # be shown must not be approvable, and an implementation that
                    # produced a digest here would let a partner sign something the
                    # chain refuses.
                    self.assertIsNone(digest, "must not be approvable")
                else:
                    self.assertEqual(
                        _hex(digest), expected["approval_digest"], "approval digest"
                    )

    def test_create_reproduces_its_bytes_digest_and_address(self) -> None:
        create = _VECTORS["create"]
        creator = AccountAddress.from_str(create["creator"])
        op = MultisigOpCreate(create["owners"], create["threshold"], _bytes(create["salt"]))

        self.assertEqual(_hex(_bcs(op)), create["op_bcs"], "operation BCS")

        op_id = multisig_operation_id(
            CHAIN_ID, ACCOUNT, create["authority_epoch"], op, EXPIRES
        )
        self.assertEqual(_hex(op_id), create["op_id"], "operation id")
        self.assertEqual(
            _hex(create_approval_digest(CHAIN_ID, ACCOUNT, creator, op, EXPIRES, op_id)),
            create["approval_digest"],
            "approval digest",
        )

    def test_the_derived_address_is_a_pure_function_of_creator_and_salt(self) -> None:
        # Pinned because a wrong derivation is the one mistake that cannot be
        # recovered from: funds are sent to the address before the policy is
        # installed, and nobody holds a key for the one that was computed wrong.
        create = _VECTORS["create"]
        creator = AccountAddress.from_str(create["creator"])
        derived = derive_multisig_account_address(creator, _bytes(create["salt"]))

        self.assertEqual(
            derived.to_string_long(),
            "0x000000000000000000000000e7fff47cbfa3957f8d7fa7c02f1cef17aa8e2f99",
        )
        self.assertEqual(
            bytes(derived.address)[:12],
            bytes(12),
            "a derived address must be EVM-formatted so a wallet can render it",
        )
        self.assertNotEqual(
            derive_multisig_account_address(creator, _repeated(0x05)).to_string_long(),
            derived.to_string_long(),
            "a different salt must give a different account",
        )

    def test_the_key_challenge_digest_matches(self) -> None:
        challenge = _VECTORS["key_challenge"]
        self.assertEqual(
            _hex(
                key_challenge_digest(
                    CHAIN_ID,
                    ACCOUNT,
                    challenge["authority_epoch"],
                    _bytes(challenge["new_auth_key"]),
                    challenge["op_kind"],
                )
            ),
            challenge["digest"],
        )
        # The challenge's ``operation`` is the operation *kind*, and the fixture's is
        # a ``Remove``. Stated because the field is a bare uint8 in the dialog: a
        # caller that passed the gated-payload kind, or the ``16 +`` form the
        # operation id uses, would produce a signature the chain cannot match to the
        # handover it is being presented for.
        self.assertEqual(challenge["op_kind"], MultisigOpVariant.REMOVE)

    def test_the_owners_digest_is_the_one_the_event_reports(self) -> None:
        self.assertEqual(
            _hex(multisig_owners_digest(OWNERS)),
            "0x722e732621398d7da39e5660da787eac27341e74a86b5bb111a8e17dbd45b1a6",
        )

    def test_the_envelope_carries_nonce_account_operation_and_an_optional_proof(
        self,
    ) -> None:
        """The whole envelope, which the fixture does not cover: its cases stop at
        the operation, because that is what owners sign.

        The two strings below were printed by the chain's own types (a
        ``bcs::to_bytes`` over ``DexOrderlessTx::Multisig``), so they pin the
        part an SDK gets wrong silently: the envelope's field order and the
        ``Option<MultisigProof>`` tag. A proof written in the wrong place
        does not fail as a missing field -- the node reads the next length byte as
        data and answers ``INVALID_SIGNATURE``.
        """
        op = MultisigOpExecute(GatedPayload.agent(DexAgentTx.revoke_all(29)))
        op_id = multisig_operation_id(CHAIN_ID, ACCOUNT, EPOCH, op, EXPIRES)
        proof = MultisigProof(
            op_id,
            EPOCH,
            EXPIRES,
            [
                BridgeSignature(_repeated(0x31), _repeated(0x32), 27),
                BridgeSignature(_repeated(0x41), _repeated(0x42), 28),
            ],
        )
        envelope = DexOrderlessTx(
            DexOrderlessTxVariant.MULTISIG, DexMultisigTx(7, ACCOUNT, op, proof)
        )

        self.assertEqual(
            _hex(_bcs(envelope)),
            "0x060700000000000000000000000000000000000000111111111111111111111111111111111111111105021d000000000000000201ee20e2ba2928a3c191dff8f1244c7b335fe8064ba8a11ad628abac979e18333a030000000000000000d2496b0000000002313131313131313131313131313131313131313131313131313131313131313132323232323232323232323232323232323232323232323232323232323232321b414141414141414141414141414141414141414141414141414141414141414142424242424242424242424242424242424242424242424242424242424242421c",
        )

        # And it reads back: a decoder that cannot is one the explorer and the
        # mempool mirror do not have.
        decoded = DexOrderlessTx.deserialize(Deserializer(_bcs(envelope)))
        self.assertEqual(decoded.variant, DexOrderlessTxVariant.MULTISIG)
        self.assertEqual(decoded.inner.nonce, 7)
        self.assertEqual(decoded.inner.proof.signatures[1].v, 28)
        self.assertEqual(_bcs(decoded.inner.op), _bcs(op))

    def test_a_rotate_key_envelope_carries_no_proof(self) -> None:
        # The one operation authorized by the account's own key plus the incoming
        # key's challenge. The chain refuses a surplus proof here as firmly as a
        # missing one, and it does so in the mempool.
        op = MultisigOpRotateKey(_repeated(0x01), _key_proof())
        self.assertFalse(op.requires_threshold_proof)

        envelope = DexOrderlessTx(
            DexOrderlessTxVariant.MULTISIG, DexMultisigTx(8, ACCOUNT, op)
        )

        self.assertEqual(
            _hex(_bcs(envelope)),
            "0x0608000000000000000000000000000000000000001111111111111111111111111111111111111111040101010101010101010101010101010101010101010101010101010101010101010202020202020202020202020202020202020202020202020202020202020202400000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
        )

    def test_a_revoke_all_is_not_a_revoke_with_an_empty_name(self) -> None:
        # On chain the two are different operations with different typed-data
        # documents, so they must not collapse into one here either.
        revoke_all = MultisigOpExecute(GatedPayload.agent(DexAgentTx.revoke_all(29)))
        empty_name = MultisigOpExecute(
            GatedPayload.agent(
                DexAgentTx(29, AgentOperationVariant.REVOKE, AgentRevoke(""))
            )
        )
        self.assertNotEqual(_bcs(revoke_all), _bcs(empty_name))

        op_id = multisig_operation_id(CHAIN_ID, ACCOUNT, EPOCH, revoke_all, EXPIRES)
        other_id = multisig_operation_id(CHAIN_ID, ACCOUNT, EPOCH, empty_name, EXPIRES)
        self.assertNotEqual(op_id, other_id)
        self.assertNotEqual(
            approval_digest(CHAIN_ID, ACCOUNT, EPOCH, revoke_all, EXPIRES, op_id),
            approval_digest(CHAIN_ID, ACCOUNT, EPOCH, empty_name, EXPIRES, other_id),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Native multisig accounts: the wire types, the operation id, and the derived address.

An account's authority is one optional on-chain record. Absent, the account is
controlled by the key its address derives from -- every account that has never run
a multisig operation. Present, it names either one control key or a k-of-n owner
set, and the operations that move funds or hand out authority then travel as
:class:`DexMultisigTx` carrying the owners' EIP-712 approvals *in the payload*
rather than in the transaction authenticator: an orderless transaction lives 65
seconds, which is not long enough for a committee to sign an envelope, while a
proof can be collected over days and submitted by any owner.

Consensus-critical: bytes must match the on-chain multisig signing contract.
``test_multisig_vectors.py`` reproduces the checked-in reference vectors.
Changes to the signing contract invalidate previously collected approvals.
"""

from __future__ import annotations

import hashlib
from enum import IntEnum
from typing import List, Optional, Sequence, Union

from ..core.account_address import AccountAddress
from ..bcs import Deserializer, Serializer
from .dex_payloads import (
    BridgeSignature,
    CreateSubAccount,
    DexAgentTx,
    DexTransferTx,
)
from ..types.enums import (
    AuthorityKindVariant,
    GatedPayloadVariant,
    KeyProofVariant,
    MultisigOpVariant,
)
from ..core.crypto import keccak256

# --- Constants ------------------------------------------------------------

#: Signing-payload version, bound into every operation id.
MULTISIG_AUTHORIZATION_VERSION = 1
#: Layout version of a stored authority record.
AUTHORITY_VERSION = 1
#: Largest owner set a policy may name.
MAX_POLICY_OWNERS = 10
#: Longest a threshold proof stays submittable: thirty days.
MAX_PROOF_VALIDITY_SECS = 30 * 24 * 60 * 60

#: State-key prefix of the per-account authority record.
DEX_AUTHORITY_PREFIX = b"dex.authority.v1"
#: State-key prefix of one consumed operation id.
DEX_MULTISIG_OP_USED_PREFIX = b"dex.multisig.op.used.v1"
#: Domain string hashed into a derived multisig address.
MULTISIG_ADDRESS_DOMAIN = b"dex.multisig.v1"

_OWNER_LENGTH = 20
_DIGEST_LENGTH = 32

#: The chain's ``EvmSignature`` has the same layout as :class:`BridgeSignature`
#: (``r[32] || s[32] || v``), so that type is reused rather than duplicated.
EvmSignature = BridgeSignature


def owner_bytes(owner: Union[str, bytes, AccountAddress]) -> bytes:
    """An owner is twenty bytes.

    Owners sign EIP-712 typed data with ordinary EVM wallets and the chain recovers
    them from the signature, so an owner entry is an EVM address and never this
    chain's 32-byte form. Accepts either spelling and keeps the twenty bytes, which
    is what BCS carries.
    """
    if isinstance(owner, AccountAddress):
        raw = bytes(owner.address)
        if any(raw[:12]):
            raise ValueError(f"owner {owner} is not an EVM address")
        return raw[12:]
    if isinstance(owner, str):
        text = owner[2:] if owner.lower().startswith("0x") else owner
        owner = bytes.fromhex(text)
    if len(owner) != _OWNER_LENGTH:
        raise ValueError(f"an owner address must be exactly 20 bytes, got {len(owner)}")
    return bytes(owner)


def _fixed(name: str, value: bytes, length: int) -> bytes:
    if len(value) != length:
        raise ValueError(f"{name} must be exactly {length} bytes, got {len(value)}")
    return bytes(value)


def evm_signature_from_compact(signature: Union[str, bytes]) -> EvmSignature:
    """Split a wallet's 65-byte ``r || s || v`` into the shape the proof carries.

    ``v`` is passed through as the wallet gave it: the chain subtracts 27 when it is
    27 or above, so both spellings of a recovery id verify.
    """
    if isinstance(signature, str):
        text = signature[2:] if signature.lower().startswith("0x") else signature
        signature = bytes.fromhex(text)
    if len(signature) != 65:
        raise ValueError(
            f"a wallet signature must be 65 bytes (r||s||v), got {len(signature)}"
        )
    return BridgeSignature(signature[:32], signature[32:64], signature[64])


# --- Proofs ---------------------------------------------------------------


class MultisigProof:
    """The k-of-n approvals for one operation, collected off chain.

    ``op_id`` is recomputed on chain; it travels so that a mismatch reports itself
    as a proof-id error rather than as a bare threshold failure.
    """

    op_id: bytes
    authority_epoch: int  # u64
    expires_at_secs: int  # u64
    signatures: List[EvmSignature]

    def __init__(
        self,
        op_id: bytes,
        authority_epoch: int,
        expires_at_secs: int,
        signatures: Sequence[EvmSignature],
    ):
        self.op_id = _fixed("MultisigProof op_id", op_id, _DIGEST_LENGTH)
        self.authority_epoch = authority_epoch
        self.expires_at_secs = expires_at_secs
        self.signatures = list(signatures)

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_fixed_bytes(self.op_id)
        serializer.serialize_u64(self.authority_epoch)
        serializer.serialize_u64(self.expires_at_secs)
        serializer.serialize_u32_as_uleb128(len(self.signatures))
        for signature in self.signatures:
            signature.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> "MultisigProof":
        op_id = deserializer.deserialize_fixed_bytes(_DIGEST_LENGTH)
        authority_epoch = deserializer.deserialize_u64()
        expires_at_secs = deserializer.deserialize_u64()
        signatures = [
            BridgeSignature.deserialize(deserializer)
            for _ in range(deserializer.deserialize_u32_from_uleb128())
        ]
        return MultisigProof(op_id, authority_epoch, expires_at_secs, signatures)


class KeyProof:
    """A new control key proving it can sign, when authority is handed to it.

    Without it an owner set could hand an account to an address nobody holds a key
    for, which is indistinguishable from destroying it.
    """

    variant: KeyProofVariant

    def serialize(self, serializer: Serializer) -> None:  # pragma: no cover - base
        raise NotImplementedError

    @staticmethod
    def deserialize(deserializer: Deserializer) -> "KeyProof":
        variant = KeyProofVariant(deserializer.deserialize_u32_from_uleb128())
        if variant == KeyProofVariant.SECP256K1:
            return KeyProofSecp256k1(BridgeSignature.deserialize(deserializer))
        public_key = deserializer.deserialize_fixed_bytes(_DIGEST_LENGTH)
        signature = deserializer.deserialize_bytes()
        return KeyProofEd25519(public_key, signature)


class KeyProofSecp256k1(KeyProof):
    """secp256k1: an EIP-712 signature over ``IntentionMultisig_KeyChallenge``.

    No public key travels: recovery yields the signer's address directly, and for
    this scheme the address *is* the authentication key.
    """

    def __init__(self, signature: EvmSignature):
        self.variant = KeyProofVariant.SECP256K1
        self.signature = signature

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.signature.serialize(serializer)


class KeyProofEd25519(KeyProof):
    """Ed25519: a plain signature over the BCS-encoded challenge.

    The public key travels because an Ed25519 authentication key is a hash of it
    and cannot be recovered from the signature.
    """

    def __init__(self, public_key: bytes, signature: bytes):
        self.variant = KeyProofVariant.ED25519
        self.public_key = _fixed("an Ed25519 public key", public_key, _DIGEST_LENGTH)
        self.signature = bytes(signature)

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        serializer.serialize_fixed_bytes(self.public_key)
        # A ``Vec<u8>``, so length-prefixed -- unlike the public key, which is a
        # fixed-size array on the chain.
        serializer.serialize_bytes(self.signature)


# --- Gated payloads -------------------------------------------------------


class GatedPayload:
    """One payload executed as the account, with the owners' approval.

    Exactly the operations an agent key cannot be delegated: they move funds out of
    the account or hand out authority. Each variant is the unchanged transaction
    type, so the chain reuses the existing handler with the policy account
    substituted for the sender.
    """

    variant: GatedPayloadVariant
    inner: Union[DexTransferTx, DexAgentTx, CreateSubAccount]

    def __init__(self, variant: GatedPayloadVariant, inner) -> None:
        self.variant = variant
        self.inner = inner

    @staticmethod
    def transfer(inner: DexTransferTx) -> "GatedPayload":
        return GatedPayload(GatedPayloadVariant.DEX_TRANSFER, inner)

    @staticmethod
    def agent(inner: DexAgentTx) -> "GatedPayload":
        return GatedPayload(GatedPayloadVariant.DEX_AGENT, inner)

    @staticmethod
    def create_sub_account(inner: CreateSubAccount) -> "GatedPayload":
        return GatedPayload(GatedPayloadVariant.CREATE_SUB_ACCOUNT, inner)

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.inner.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> "GatedPayload":
        variant = GatedPayloadVariant(deserializer.deserialize_u32_from_uleb128())
        if variant == GatedPayloadVariant.DEX_TRANSFER:
            return GatedPayload(variant, DexTransferTx.deserialize(deserializer))
        if variant == GatedPayloadVariant.DEX_AGENT:
            return GatedPayload(variant, DexAgentTx.deserialize(deserializer))
        if variant == GatedPayloadVariant.CREATE_SUB_ACCOUNT:
            return GatedPayload(variant, CreateSubAccount.deserialize(deserializer))
        raise ValueError(f"Unknown GatedPayload variant: {variant}")

    @property
    def nonce(self) -> int:
        """The inner payload's replay nonce, which the signed digest covers."""
        return self.inner.nonce

    @property
    def is_any_owner(self) -> bool:
        """Whether any single owner may submit this with no threshold proof.

        Always false, and deliberately so: every gated payload needs k-of-n. The
        class is kept as a reserved shape on the chain, so this is one predicate
        rather than an authorization model to re-litigate if an operation is ever
        admitted back into it.
        """
        return False


# --- Operations -----------------------------------------------------------


class MultisigOp:
    """What a :class:`DexMultisigTx` asks for."""

    variant: MultisigOpVariant

    def serialize(self, serializer: Serializer) -> None:  # pragma: no cover - base
        raise NotImplementedError

    @property
    def requires_threshold_proof(self) -> bool:
        """Whether this operation is authorized by a threshold proof, which is also
        exactly when :class:`DexMultisigTx` must carry one.

        ``RotateKey`` is the lone resident of the other class: it is authorized by
        the account's own key plus the incoming key's challenge, so no owner signs
        it. The chain refuses a surplus proof as well as a missing one, and both
        verdicts are taken in the mempool.
        """
        return self.variant != MultisigOpVariant.ROTATE_KEY

    @staticmethod
    def deserialize(deserializer: Deserializer) -> "MultisigOp":
        variant = MultisigOpVariant(deserializer.deserialize_u32_from_uleb128())
        if variant in (
            MultisigOpVariant.CREATE,
            MultisigOpVariant.INSTALL,
            MultisigOpVariant.UPDATE_POLICY,
        ):
            owners = [
                deserializer.deserialize_fixed_bytes(_OWNER_LENGTH)
                for _ in range(deserializer.deserialize_u32_from_uleb128())
            ]
            threshold = deserializer.deserialize_u8()
            if variant == MultisigOpVariant.CREATE:
                return MultisigOpCreate(
                    owners, threshold, deserializer.deserialize_fixed_bytes(_DIGEST_LENGTH)
                )
            if variant == MultisigOpVariant.INSTALL:
                return MultisigOpInstall(owners, threshold)
            return MultisigOpUpdatePolicy(owners, threshold)
        if variant in (MultisigOpVariant.REMOVE, MultisigOpVariant.ROTATE_KEY):
            new_auth_key = deserializer.deserialize_fixed_bytes(_DIGEST_LENGTH)
            proof = KeyProof.deserialize(deserializer)
            if variant == MultisigOpVariant.REMOVE:
                return MultisigOpRemove(new_auth_key, proof)
            return MultisigOpRotateKey(new_auth_key, proof)
        return MultisigOpExecute(GatedPayload.deserialize(deserializer))


def _serialize_owners(serializer: Serializer, owners: Sequence[bytes]) -> None:
    serializer.serialize_u32_as_uleb128(len(owners))
    for owner in owners:
        serializer.serialize_fixed_bytes(_fixed("an owner address", owner, _OWNER_LENGTH))


class MultisigOpCreate(MultisigOp):
    """Install a policy on a fresh derived address.

    The proof is signed by the *new* owner set: nothing is being taken from anyone,
    so it is a liveness check rather than an approval -- evidence that at least
    ``threshold`` of the listed addresses are keys someone holds, before funds are
    sent to an address only they can move.
    """

    def __init__(
        self,
        owners: Sequence[Union[str, bytes, AccountAddress]],
        threshold: int,
        salt: bytes,
    ):
        self.variant = MultisigOpVariant.CREATE
        self.owners = [owner_bytes(owner) for owner in owners]
        self.threshold = threshold
        self.salt = _fixed("a Create salt", salt, _DIGEST_LENGTH)

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        _serialize_owners(serializer, self.owners)
        serializer.serialize_u8(self.threshold)
        serializer.serialize_fixed_bytes(self.salt)


class MultisigOpInstall(MultisigOp):
    """Put an existing key-controlled account under a policy, keeping its address
    and its history. Sent by the account itself, co-signed by the new owner set."""

    def __init__(
        self, owners: Sequence[Union[str, bytes, AccountAddress]], threshold: int
    ):
        self.variant = MultisigOpVariant.INSTALL
        self.owners = [owner_bytes(owner) for owner in owners]
        self.threshold = threshold

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        _serialize_owners(serializer, self.owners)
        serializer.serialize_u8(self.threshold)


class MultisigOpUpdatePolicy(MultisigOp):
    """Change the owner set or the threshold.

    Approved by the current set *and* the proposed one: the first is the
    authorization, the second keeps a mistyped owner list from stranding the
    account's funds behind addresses nobody can sign for.
    """

    def __init__(
        self, owners: Sequence[Union[str, bytes, AccountAddress]], threshold: int
    ):
        self.variant = MultisigOpVariant.UPDATE_POLICY
        self.owners = [owner_bytes(owner) for owner in owners]
        self.threshold = threshold

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        _serialize_owners(serializer, self.owners)
        serializer.serialize_u8(self.threshold)


class MultisigOpRemove(MultisigOp):
    """Leave the policy and hand the account to one key.

    The owners must name that key and it must co-sign: otherwise "remove the
    policy" would silently re-arm whichever key the account had before, which for a
    derived address is no key at all.

    The signing order is fixed by the data: the incoming key signs the challenge
    first, the operation is assembled around that proof, and only then do owners
    approve -- their digest covers the finished operation.
    """

    def __init__(self, new_auth_key: bytes, new_key_proof: KeyProof):
        self.variant = MultisigOpVariant.REMOVE
        self.new_auth_key = _fixed("a new auth key", new_auth_key, _DIGEST_LENGTH)
        self.new_key_proof = new_key_proof

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        serializer.serialize_fixed_bytes(self.new_auth_key)
        self.new_key_proof.serialize(serializer)


class MultisigOpRotateKey(MultisigOp):
    """Rotate a single-key account's control key without changing its address. Sent
    by the current key and co-signed by the new one, so it carries no owner proof."""

    def __init__(self, new_auth_key: bytes, new_key_proof: KeyProof):
        self.variant = MultisigOpVariant.ROTATE_KEY
        self.new_auth_key = _fixed("a new auth key", new_auth_key, _DIGEST_LENGTH)
        self.new_key_proof = new_key_proof

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        serializer.serialize_fixed_bytes(self.new_auth_key)
        self.new_key_proof.serialize(serializer)


class MultisigOpExecute(MultisigOp):
    """Run one gated payload as the account."""

    def __init__(self, payload: GatedPayload):
        self.variant = MultisigOpVariant.EXECUTE
        self.payload = payload

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.payload.serialize(serializer)

    @property
    def requires_threshold_proof(self) -> bool:
        return not self.payload.is_any_owner


class DexMultisigTx:
    """Manage or act as a multisig account.

    ``nonce`` is the envelope's replay protection, spent by the submitting key;
    ``account`` is the account being managed or acted for, which for a derived
    address is never the sender.
    """

    nonce: int  # u64
    account: AccountAddress
    op: MultisigOp
    proof: Optional[MultisigProof]

    def __init__(
        self,
        nonce: int,
        account: AccountAddress,
        op: MultisigOp,
        proof: Optional[MultisigProof] = None,
    ):
        self.nonce = nonce
        self.account = account
        self.op = op
        self.proof = proof

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.account.serialize(serializer)
        self.op.serialize(serializer)
        serializer.serialize_bool(self.proof is not None)
        if self.proof is not None:
            self.proof.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> "DexMultisigTx":
        nonce = deserializer.deserialize_u64()
        account = AccountAddress.deserialize(deserializer)
        op = MultisigOp.deserialize(deserializer)
        proof = MultisigProof.deserialize(deserializer) if deserializer.deserialize_bool() else None
        return DexMultisigTx(nonce, account, op, proof)


# --- Operation id ---------------------------------------------------------


def op_kind_byte(op: MultisigOp) -> int:
    """The ``kind`` byte an operation id binds.

    A gated payload's own kind is folded in, so an ``Execute(DexTransfer)`` proof
    cannot be presented as an ``Execute(DexAgent)`` even though both are
    ``MultisigOp::Execute``. The ``16 +`` keeps the two numbering spaces from
    colliding as the enums grow.
    """
    if isinstance(op, MultisigOpExecute):
        return 16 + int(op.payload.variant)
    return int(op.variant)


def _bcs(value) -> bytes:
    serializer = Serializer()
    value.serialize(serializer)
    return serializer.to_bytes()


def multisig_operation_id(
    chain_id: int,
    account: AccountAddress,
    authority_epoch: int,
    op: MultisigOp,
    expires_at_secs: int,
) -> bytes:
    """The replay key the owners sign, and the id the chain records as spent.

    Every field closes an attack: ``chain_id`` stops a signature made on one network
    from verifying on another, ``account`` stops it moving to another account under
    the same owners, ``authority_epoch`` retires it when the owner set changes, the
    kind byte stops a proof for one kind of operation being presented as another,
    the payload digest covers every payload byte, and ``expires_at_secs`` bounds how
    long a collected-but-unused approval stays dangerous.
    """
    serializer = Serializer()
    serializer.serialize_u8(chain_id)
    serializer.serialize_u8(MULTISIG_AUTHORIZATION_VERSION)
    account.serialize(serializer)
    serializer.serialize_u64(authority_epoch)
    serializer.serialize_u8(op_kind_byte(op))
    # A fixed-size array on the chain, so no length prefix.
    serializer.serialize_fixed_bytes(keccak256(_bcs(op)))
    serializer.serialize_u64(expires_at_secs)
    return keccak256(serializer.to_bytes())


def submit_operation_name(op: MultisigOp) -> str:
    """The operation name the submitting owner's envelope dialog shows, and the same
    string the REST payload view reports. Stable: it is hashed into the envelope."""
    if isinstance(op, MultisigOpExecute):
        return {
            GatedPayloadVariant.DEX_TRANSFER: "execute_transfer",
            GatedPayloadVariant.DEX_AGENT: "execute_agent",
            GatedPayloadVariant.CREATE_SUB_ACCOUNT: "execute_create_subaccount",
        }[op.payload.variant]
    return {
        MultisigOpVariant.CREATE: "create_policy",
        MultisigOpVariant.INSTALL: "install_policy",
        MultisigOpVariant.UPDATE_POLICY: "update_policy",
        MultisigOpVariant.REMOVE: "remove_policy",
        MultisigOpVariant.ROTATE_KEY: "rotate_key",
    }[op.variant]


# --- Derived address ------------------------------------------------------


def derive_multisig_account_address(
    creator: AccountAddress, salt: bytes
) -> AccountAddress:
    """The address a ``Create`` installs a policy on.

    Keyless by construction: twenty bytes of a hash, so no public key derives to it
    and the chain's ``derive(pubkey) == sender`` check can never hold for it. Both
    creator and salt are in the preimage, so one creator can hold several multisig
    accounts and the address is computable before the transaction is sent.

    SHA3-256, not Keccak-256: the same hash the subaccount derivation uses, and
    the leading twenty bytes are right-aligned so every derived address in this
    system stays EVM-formatted and a wallet can render it.
    """
    digest = hashlib.sha3_256(
        MULTISIG_ADDRESS_DOMAIN
        + bytes(creator.address)
        + _fixed("a Create salt", salt, _DIGEST_LENGTH)
    ).digest()
    padding = b"\x00" * (AccountAddress.LENGTH - _OWNER_LENGTH)
    return AccountAddress(padding + digest[:_OWNER_LENGTH])


def multisig_owners_digest(
    owners: Sequence[Union[str, bytes, AccountAddress]]
) -> bytes:
    """The commitment to an owner set that ``AuthorityChangedEvent`` carries and the
    ``/dex/authority`` endpoint reports.

    The members themselves are not in the event -- an owner set is up to ten
    addresses of consensus-visible payload -- so this is how a reader checks that
    the set it holds is the set that was installed.
    """
    serializer = Serializer()
    _serialize_owners(serializer, [owner_bytes(owner) for owner in owners])
    return keccak256(b"INTENTION_MULTISIG_OWNERS" + serializer.to_bytes())


# --- State keys -----------------------------------------------------------


def dex_authority_raw_key(account: AccountAddress) -> bytes:
    """The raw state key of one account's authority record."""
    return DEX_AUTHORITY_PREFIX + bytes(account.address)


def dex_multisig_op_used_raw_key(op_id: bytes) -> bytes:
    """The raw state key of one consumed operation id."""
    return DEX_MULTISIG_OP_USED_PREFIX + _fixed(
        "an operation id", op_id, _DIGEST_LENGTH
    )


# --- Policy checks --------------------------------------------------------


def validate_multisig_policy(
    owners: Sequence[Union[str, bytes, AccountAddress]], threshold: int
) -> Optional[str]:
    """The shape checks the chain applies on every write, so a caller can fail before
    paying for a transaction: size, uniqueness, no zero owner, and a threshold that
    is reachable.

    Returns the offending reason rather than raising, because the caller that
    assembles a policy from user input wants to show it.
    """
    if not owners:
        return "a policy needs at least one owner"
    if len(owners) > MAX_POLICY_OWNERS:
        return f"a policy may name at most {MAX_POLICY_OWNERS} owners, got {len(owners)}"
    if threshold == 0 or threshold > len(owners):
        return f"a threshold of {threshold} is not reachable with {len(owners)} owners"
    try:
        normalized = [owner_bytes(owner) for owner in owners]
    except ValueError as error:
        return str(error)
    if any(owner == b"\x00" * _OWNER_LENGTH for owner in normalized):
        return "the zero address cannot be an owner"
    if len(set(normalized)) != len(normalized):
        return "an owner is listed twice"
    return None


# --- Error codes ----------------------------------------------------------


class MultisigErrorCode(IntEnum):
    """Consensus-visible rejection codes for multisig execution.

    Free-form text cannot travel in an execution status -- it feeds the transaction
    info hash -- so the reason arrives as an abort code. ``0x5xxxx`` is Move's
    ``PERMISSION_DENIED`` category, continuing above the Admin Control block.
    """

    AUTHORITY_NOT_FOUND = 0x50040
    AUTHORITY_EXISTS = 0x50041
    AUTHORITY_KIND_MISMATCH = 0x50042
    AUTHORITY_KEY_MISMATCH = 0x50043
    DIRECT_SUBMISSION_BLOCKED = 0x50044
    NOT_OWNER = 0x50045
    PROOF_REQUIRED = 0x50046
    PROOF_INVALID = 0x50047
    SIGNATURE_INVALID = 0x50048
    SIGNER_NOT_OWNER = 0x50049
    THRESHOLD_NOT_MET = 0x5004A
    EPOCH_MISMATCH = 0x5004B
    PROOF_EXPIRED = 0x5004C
    OPERATION_ALREADY_USED = 0x5004D
    POLICY_INVALID = 0x5004E
    KEY_PROOF_INVALID = 0x5004F
    AUTHORITY_STORE_FAILED = 0x50050
    OVERFLOW = 0x50051
    DERIVED_ADDRESS_MISMATCH = 0x50052
    SUBMITTER_NOT_ACCOUNT = 0x50053


_MULTISIG_REASON_NAMES = {
    MultisigErrorCode.AUTHORITY_NOT_FOUND: "DEX_MULTISIG_AUTHORITY_NOT_FOUND",
    MultisigErrorCode.AUTHORITY_EXISTS: "DEX_MULTISIG_AUTHORITY_EXISTS",
    MultisigErrorCode.AUTHORITY_KIND_MISMATCH: "DEX_MULTISIG_AUTHORITY_KIND_MISMATCH",
    MultisigErrorCode.AUTHORITY_KEY_MISMATCH: "DEX_MULTISIG_AUTHORITY_KEY_MISMATCH",
    MultisigErrorCode.DIRECT_SUBMISSION_BLOCKED: "DEX_MULTISIG_DIRECT_SUBMISSION_BLOCKED",
    MultisigErrorCode.NOT_OWNER: "DEX_MULTISIG_NOT_OWNER",
    MultisigErrorCode.PROOF_REQUIRED: "DEX_MULTISIG_PROOF_REQUIRED",
    MultisigErrorCode.PROOF_INVALID: "DEX_MULTISIG_PROOF_INVALID",
    MultisigErrorCode.SIGNATURE_INVALID: "DEX_MULTISIG_SIGNATURE_INVALID",
    MultisigErrorCode.SIGNER_NOT_OWNER: "DEX_MULTISIG_SIGNER_NOT_OWNER",
    MultisigErrorCode.THRESHOLD_NOT_MET: "DEX_MULTISIG_THRESHOLD_NOT_MET",
    MultisigErrorCode.EPOCH_MISMATCH: "DEX_MULTISIG_EPOCH_MISMATCH",
    MultisigErrorCode.PROOF_EXPIRED: "DEX_MULTISIG_PROOF_EXPIRED",
    MultisigErrorCode.OPERATION_ALREADY_USED: "DEX_MULTISIG_OPERATION_ALREADY_USED",
    MultisigErrorCode.POLICY_INVALID: "DEX_MULTISIG_POLICY_INVALID",
    MultisigErrorCode.KEY_PROOF_INVALID: "DEX_MULTISIG_KEY_PROOF_INVALID",
    MultisigErrorCode.AUTHORITY_STORE_FAILED: "DEX_MULTISIG_AUTHORITY_STORE_FAILED",
    MultisigErrorCode.OVERFLOW: "DEX_MULTISIG_OVERFLOW",
    MultisigErrorCode.DERIVED_ADDRESS_MISMATCH: "DEX_MULTISIG_DERIVED_ADDRESS_MISMATCH",
    MultisigErrorCode.SUBMITTER_NOT_ACCOUNT: "DEX_MULTISIG_SUBMITTER_NOT_ACCOUNT",
}


def multisig_reason_name(abort_code: int) -> Optional[str]:
    """The reason name for an abort code, or ``None`` if it is not a multisig one.

    ``None`` rather than a guess: an abort code from another subsystem named as a
    multisig failure would send a caller looking at the wrong proof.
    """
    try:
        return _MULTISIG_REASON_NAMES[MultisigErrorCode(abort_code)]
    except ValueError:
        return None


# --- Authority record -----------------------------------------------------


class MultisigPolicy:
    """A fixed k-of-n owner set, as stored on chain."""

    def __init__(
        self, owners: Sequence[bytes], threshold: int, created_at_secs: int
    ) -> None:
        self.owners = [bytes(owner) for owner in owners]
        self.threshold = threshold
        self.created_at_secs = created_at_secs

    @staticmethod
    def deserialize(deserializer: Deserializer) -> "MultisigPolicy":
        owners = [
            deserializer.deserialize_fixed_bytes(_OWNER_LENGTH)
            for _ in range(deserializer.deserialize_u32_from_uleb128())
        ]
        return MultisigPolicy(owners, deserializer.deserialize_u8(), deserializer.deserialize_u64())


class AccountAuthority:
    """What controls an account, decoded from the stored record.

    No record at all is the default and means the key the address derives from --
    which is why the chain's read endpoint answers 404 rather than rendering a
    default.
    """

    def __init__(
        self,
        version: int,
        epoch: int,
        kind: AuthorityKindVariant,
        auth_key: Optional[bytes] = None,
        policy: Optional[MultisigPolicy] = None,
        updated_at_secs: int = 0,
    ) -> None:
        self.version = version
        #: Bumped by every change, so a change retires every outstanding approval.
        #: Monotonic for the life of the account, and it does not restart when an
        #: account leaves a policy.
        self.epoch = epoch
        self.kind = kind
        self.auth_key = auth_key
        self.policy = policy
        self.updated_at_secs = updated_at_secs

    @staticmethod
    def deserialize(deserializer: Deserializer) -> "AccountAuthority":
        version = deserializer.deserialize_u8()
        epoch = deserializer.deserialize_u64()
        kind = AuthorityKindVariant(deserializer.deserialize_u32_from_uleb128())
        auth_key = None
        policy = None
        if kind == AuthorityKindVariant.KEY:
            auth_key = deserializer.deserialize_fixed_bytes(_DIGEST_LENGTH)
        else:
            policy = MultisigPolicy.deserialize(deserializer)
        return AccountAuthority(
            version, epoch, kind, auth_key, policy, deserializer.deserialize_u64()
        )

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Authenticators: the key and signature attached to a transaction.

Mirrors transactions/authenticator.ts. The chain accepts a secp256k1
authenticator directly at variant 1, without the SingleSender/SingleKey
nesting, and that is the path every signature here takes; the nested form is
kept only so a transaction carrying it still round-trips.
"""

from __future__ import annotations

import hashlib
from enum import IntEnum
from typing import Union

from ..bcs import Deserializer, Serializable, Serializer
from .raw_transaction import RawTransaction, SimpleTransaction, as_raw_transaction
from ..core.crypto import (
    AnyPublicKey,
    AnySignature,
    Secp256k1PublicKey,
    Secp256k1Signature,
)


class AccountAuthenticatorVariant(IntEnum):
    """Wire tags for per-account authenticators. Only SINGLE_KEY is produced."""

    ED25519 = 0
    MULTI_ED25519 = 1
    SINGLE_KEY = 2
    MULTI_KEY = 3
    NO_ACCOUNT_AUTHENTICATOR = 4


class TransactionAuthenticatorVariant(IntEnum):
    """Wire tags for transaction authenticators. SECP256K1 and SINGLE_SENDER are produced."""

    ED25519 = 0
    SECP256K1 = 1
    MULTI_ED25519 = 2
    MULTI_AGENT = 3
    FEE_PAYER = 4
    SINGLE_SENDER = 5


class AccountAuthenticatorSingleKey(Serializable):
    """A single scheme-tagged key and signature."""

    public_key: AnyPublicKey
    signature: AnySignature

    def __init__(
        self,
        public_key: Union[AnyPublicKey, Secp256k1PublicKey],
        signature: Union[AnySignature, Secp256k1Signature],
    ) -> None:
        self.public_key = (
            public_key
            if isinstance(public_key, AnyPublicKey)
            else AnyPublicKey(public_key)
        )
        self.signature = (
            signature if isinstance(signature, AnySignature) else AnySignature(signature)
        )

    def verify(self, message: bytes) -> bool:
        return self.public_key.verify(message, self.signature)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AccountAuthenticatorSingleKey):
            return NotImplemented
        return (
            self.public_key == other.public_key and self.signature == other.signature
        )

    def __hash__(self) -> int:
        return hash((self.public_key, self.signature))

    def __str__(self) -> str:
        return f"AccountAuthenticatorSingleKey(public_key={self.public_key}, signature={self.signature})"

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(AccountAuthenticatorVariant.SINGLE_KEY)
        self.public_key.serialize(serializer)
        self.signature.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AccountAuthenticatorSingleKey:
        variant = deserializer.deserialize_u32_from_uleb128()
        if variant != AccountAuthenticatorVariant.SINGLE_KEY:
            raise ValueError(f"Unsupported AccountAuthenticator variant: {variant}")
        return AccountAuthenticatorSingleKey.deserialize_inner(deserializer)

    @staticmethod
    def deserialize_inner(deserializer: Deserializer) -> AccountAuthenticatorSingleKey:
        """Read the body, with the variant tag already consumed."""
        return AccountAuthenticatorSingleKey(
            AnyPublicKey.deserialize(deserializer),
            AnySignature.deserialize(deserializer),
        )


class TransactionAuthenticatorSecp256k1(Serializable):
    """The chain's direct secp256k1 authenticator, without the nesting."""

    public_key: Secp256k1PublicKey
    signature: Secp256k1Signature

    def __init__(
        self, public_key: Secp256k1PublicKey, signature: Secp256k1Signature
    ) -> None:
        self.public_key = public_key
        self.signature = signature

    def verify(self, message: bytes) -> bool:
        return self.public_key.verify(message, self.signature)

    def verify_digest(self, digest: bytes) -> bool:
        return self.public_key.verify_digest(digest, self.signature)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TransactionAuthenticatorSecp256k1):
            return NotImplemented
        return (
            self.public_key == other.public_key and self.signature == other.signature
        )

    def __hash__(self) -> int:
        return hash((self.public_key, self.signature))

    def __str__(self) -> str:
        return f"TransactionAuthenticatorSecp256k1(public_key={self.public_key}, signature={self.signature})"

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(TransactionAuthenticatorVariant.SECP256K1)
        self.public_key.serialize(serializer)
        self.signature.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> TransactionAuthenticatorSecp256k1:
        variant = deserializer.deserialize_u32_from_uleb128()
        if variant != TransactionAuthenticatorVariant.SECP256K1:
            raise ValueError(f"Unsupported TransactionAuthenticator variant: {variant}")
        return TransactionAuthenticatorSecp256k1.deserialize_inner(deserializer)

    @staticmethod
    def deserialize_inner(
        deserializer: Deserializer,
    ) -> TransactionAuthenticatorSecp256k1:
        """Read the body, with the variant tag already consumed."""
        return TransactionAuthenticatorSecp256k1(
            Secp256k1PublicKey.deserialize(deserializer),
            Secp256k1Signature.deserialize(deserializer),
        )


TransactionAuthenticator = Union[
    TransactionAuthenticatorSecp256k1, AccountAuthenticatorSingleKey
]


def to_secp256k1_transaction_authenticator(
    authenticator: AccountAuthenticatorSingleKey,
) -> TransactionAuthenticatorSecp256k1:
    """Unwrap a single-key authenticator into the chain's direct secp256k1 form."""
    return TransactionAuthenticatorSecp256k1(
        authenticator.public_key.public_key, authenticator.signature.signature
    )


def deserialize_transaction_authenticator(
    deserializer: Deserializer,
) -> TransactionAuthenticator:
    """Read whichever authenticator form a signed transaction carries."""
    variant = deserializer.deserialize_u32_from_uleb128()
    if variant == TransactionAuthenticatorVariant.SECP256K1:
        return TransactionAuthenticatorSecp256k1.deserialize_inner(deserializer)
    if variant == TransactionAuthenticatorVariant.SINGLE_SENDER:
        return AccountAuthenticatorSingleKey.deserialize(deserializer)
    raise ValueError(f"Unsupported TransactionAuthenticator variant: {variant}")


# ============================================================================
# SignedTransaction
# ============================================================================


class SignedTransaction(Serializable):
    """A transaction together with the authenticator that vouches for it."""

    transaction: RawTransaction
    authenticator: TransactionAuthenticator

    def __init__(
        self,
        transaction: RawTransaction,
        authenticator: TransactionAuthenticator,
    ) -> None:
        self.transaction = transaction
        # Every signature this SDK produces takes the chain's direct secp256k1
        # path; a single-key authenticator is unwrapped into it here so that the
        # choice is made once, in one place.
        if isinstance(authenticator, AccountAuthenticatorSingleKey):
            authenticator = to_secp256k1_transaction_authenticator(authenticator)
        self.authenticator = authenticator

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SignedTransaction):
            return NotImplemented
        return (
            self.transaction == other.transaction
            and self.authenticator == other.authenticator
        )

    def __str__(self) -> str:
        return f"Transaction: {self.transaction}Authenticator: {self.authenticator}"

    def bytes(self) -> bytes:
        return self.bcs_to_bytes()

    def hash(self) -> str:
        """The hash the chain files this transaction under."""
        prefix = hashlib.sha3_256(b"INTENTION::Transaction").digest()
        digest = hashlib.sha3_256(prefix + bytes([0]) + self.bytes()).hexdigest()
        return f"0x{digest}"

    def verify(self) -> bool:
        return self.authenticator.verify(self.transaction.keyed())

    def serialize(self, serializer: Serializer) -> None:
        self.transaction.serialize(serializer)
        if isinstance(self.authenticator, TransactionAuthenticatorSecp256k1):
            # Serializes its own variant tag.
            self.authenticator.serialize(serializer)
        else:
            serializer.serialize_u32_as_uleb128(
                TransactionAuthenticatorVariant.SINGLE_SENDER
            )
            self.authenticator.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> SignedTransaction:
        transaction = RawTransaction.deserialize(deserializer)
        authenticator = deserialize_transaction_authenticator(deserializer)
        return SignedTransaction(transaction, authenticator)


def generate_signed_transaction(
    transaction: Union[SimpleTransaction, RawTransaction],
    sender_authenticator: AccountAuthenticatorSingleKey,
) -> bytes:
    """BCS bytes of a signed transaction, ready to POST to a node."""
    return SignedTransaction(
        as_raw_transaction(transaction), sender_authenticator
    ).bcs_to_bytes()

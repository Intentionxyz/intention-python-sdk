# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Secp256k1 keys and signatures, and the variant-tagged wrappers around them.

Mirrors core/crypto.ts. Only secp256k1 exists: it is the scheme the chain uses
for user accounts, and an EVM-compatible address is derived from it.
"""

from __future__ import annotations

import hashlib
from enum import IntEnum

from Crypto.Hash import keccak as _keccak
from ecdsa import SECP256k1, VerifyingKey, util

from ..bcs import Deserializer, Serializable, Serializer


def keccak256(data: bytes) -> bytes:
    """Keccak-256, **not** NIST SHA3-256.

    The two differ only in padding, so a swap produces digests that look right
    and are not -- wrong addresses and signatures the chain rejects.
    """
    digest = _keccak.new(digest_bits=256)
    digest.update(data)
    return digest.digest()


class AnyPublicKeyVariant(IntEnum):
    """Wire tag inside AnyPublicKey. Only SECP256K1 is produced."""

    ED25519 = 0
    SECP256K1 = 1
    KEYLESS = 3


class AnySignatureVariant(IntEnum):
    """Wire tag inside AnySignature. Only SECP256K1 is produced."""

    ED25519 = 0
    SECP256K1 = 1
    KEYLESS = 3


class Secp256k1PublicKey(Serializable):
    """Uncompressed secp256k1 public key: the 0x04 prefix plus a 64-byte point."""

    LENGTH: int = 65
    POINT_LENGTH: int = 64

    key: VerifyingKey

    def __init__(self, key: VerifyingKey) -> None:
        self.key = key

    @staticmethod
    def from_bytes(data: bytes) -> Secp256k1PublicKey:
        """Accept the point with or without its 0x04 prefix."""
        if len(data) == Secp256k1PublicKey.LENGTH and data[0] == 0x04:
            data = data[1:]
        elif len(data) != Secp256k1PublicKey.POINT_LENGTH:
            raise ValueError(
                f"Secp256k1PublicKey length should be {Secp256k1PublicKey.LENGTH}, got {len(data)}"
            )
        return Secp256k1PublicKey(
            VerifyingKey.from_string(data, SECP256k1, hashlib.sha3_256)
        )

    def to_bytes(self) -> bytes:
        """The 65 bytes that go on the wire."""
        return b"\x04" + self.key.to_string()

    def to_evm_account_bytes(self) -> bytes:
        """The 32-byte account address: keccak of the point, low 20 bytes, left-padded."""
        evm_bytes = keccak256(self.key.to_string())[-20:]
        return b"\x00" * 12 + evm_bytes

    def hex(self) -> str:
        return f"0x{self.to_bytes().hex()}"

    def __str__(self) -> str:
        return self.hex()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secp256k1PublicKey):
            return NotImplemented
        return self.key.to_string() == other.key.to_string()

    def __hash__(self) -> int:
        return hash(self.key.to_string())

    # --- Verification ---
    #
    # The TypeScript SDK has no verify: a browser wallet signs and the chain
    # checks. Here the tests both sign and check, so the counterpart to each
    # signing path lives alongside it.

    def verify(self, message: bytes, signature: Secp256k1Signature) -> bool:
        """Counterpart to :meth:`Secp256k1PrivateKey.sign` (wraps in EIP-712)."""
        from .account import eip712_sign_hash

        return self.verify_digest(eip712_sign_hash(message), signature)

    def verify_digest(self, digest: bytes, signature: Secp256k1Signature) -> bool:
        """Counterpart to :meth:`Secp256k1PrivateKey.sign_digest`."""
        try:
            return bool(
                self.key.verify_digest(
                    signature.to_bytes(), digest, sigdecode=util.sigdecode_string
                )
            )
        except Exception:
            return False

    # --- BCS ---

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_bytes(self.to_bytes())

    @staticmethod
    def deserialize(deserializer: Deserializer) -> Secp256k1PublicKey:
        return Secp256k1PublicKey.from_bytes(deserializer.deserialize_bytes())


class Secp256k1Signature(Serializable):
    """64-byte secp256k1 signature, ``r || s``, with s normalised low."""

    LENGTH: int = 64

    signature: bytes

    def __init__(self, signature: bytes) -> None:
        if len(signature) != Secp256k1Signature.LENGTH:
            raise ValueError(
                f"Secp256k1Signature length should be {Secp256k1Signature.LENGTH}, "
                f"got {len(signature)}"
            )
        self.signature = bytes(signature)

    def to_bytes(self) -> bytes:
        return self.signature

    def hex(self) -> str:
        return f"0x{self.signature.hex()}"

    def __str__(self) -> str:
        return self.hex()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secp256k1Signature):
            return NotImplemented
        return self.signature == other.signature

    def __hash__(self) -> int:
        return hash(self.signature)

    # --- BCS ---

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_bytes(self.signature)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> Secp256k1Signature:
        return Secp256k1Signature(deserializer.deserialize_bytes())


class AnyPublicKey(Serializable):
    """A public key tagged with its scheme."""

    variant: AnyPublicKeyVariant
    public_key: Secp256k1PublicKey

    def __init__(self, public_key: Secp256k1PublicKey) -> None:
        self.variant = AnyPublicKeyVariant.SECP256K1
        self.public_key = public_key

    def to_bytes(self) -> bytes:
        """Raw bytes of the wrapped key, without the variant tag."""
        return self.public_key.to_bytes()

    def verify(self, message: bytes, signature: AnySignature) -> bool:
        return self.public_key.verify(message, signature.signature)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AnyPublicKey):
            return NotImplemented
        return self.variant == other.variant and self.public_key == other.public_key

    def __hash__(self) -> int:
        return hash((self.variant, self.public_key))

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.public_key.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AnyPublicKey:
        variant = deserializer.deserialize_u32_from_uleb128()
        if variant != AnyPublicKeyVariant.SECP256K1:
            raise ValueError(f"Unsupported AnyPublicKey variant: {variant}")
        return AnyPublicKey(Secp256k1PublicKey.deserialize(deserializer))


class AnySignature(Serializable):
    """A signature tagged with its scheme."""

    variant: AnySignatureVariant
    signature: Secp256k1Signature

    def __init__(self, signature: Secp256k1Signature) -> None:
        self.variant = AnySignatureVariant.SECP256K1
        self.signature = signature

    def to_bytes(self) -> bytes:
        """Raw bytes of the wrapped signature, without the variant tag."""
        return self.signature.to_bytes()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AnySignature):
            return NotImplemented
        return self.variant == other.variant and self.signature == other.signature

    def __hash__(self) -> int:
        return hash((self.variant, self.signature))

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.signature.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AnySignature:
        variant = deserializer.deserialize_u32_from_uleb128()
        if variant != AnySignatureVariant.SECP256K1:
            raise ValueError(f"Unsupported AnySignature variant: {variant}")
        return AnySignature(Secp256k1Signature.deserialize(deserializer))

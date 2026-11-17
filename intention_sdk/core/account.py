# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Accounts and the private keys behind them.

Mirrors core/account.ts: a secp256k1 key, the EVM-compatible address derived
from it, and the two signing paths a transaction can take.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Union

from ecdsa import SECP256k1, SigningKey, util

from ..bcs import Deserializer, Serializable, Serializer
from .account_address import AccountAddress
from .crypto import AnyPublicKey, AnySignature, Secp256k1PublicKey, Secp256k1Signature, keccak256

_AIP80_PREFIX = "secp256k1-priv-"


# --- EIP-712 ---------------------------------------------------------------
#
# A wallet can only render one opaque hash for an arbitrary payload, so the
# transaction bytes are wrapped in a named struct before signing. The chain
# rebuilds the same wrapper, so the two cannot drift apart.

_DOMAIN_SEPARATOR: Optional[bytes] = None
_TYPE_HASH: Optional[bytes] = None


def _domain_separator() -> bytes:
    global _DOMAIN_SEPARATOR
    if _DOMAIN_SEPARATOR is None:
        _DOMAIN_SEPARATOR = keccak256(
            keccak256(b"EIP712Domain(string name)") + keccak256(b"Intention")
        )
    return _DOMAIN_SEPARATOR


def _type_hash() -> bytes:
    global _TYPE_HASH
    if _TYPE_HASH is None:
        _TYPE_HASH = keccak256(b"IntentionTransaction(bytes32 digest)")
    return _TYPE_HASH


def eip712_sign_hash(signing_message: bytes) -> bytes:
    """The 32 bytes actually signed for an Intention transaction."""
    struct_hash = keccak256(_type_hash() + keccak256(signing_message))
    return keccak256(b"\x19\x01" + _domain_separator() + struct_hash)


def _normalise_low_s(signature: bytes) -> bytes:
    """Fold s into the lower half of the curve order, as the chain requires."""
    order = SECP256k1.generator.order()
    r, s = util.sigdecode_string(signature, order)
    if s > order // 2:
        return util.sigencode_string(r, (-s) % order, order)
    return signature


class Secp256k1PrivateKey(Serializable):
    """A secp256k1 signing key."""

    LENGTH: int = 32

    key: SigningKey

    def __init__(self, key: Union[SigningKey, bytes, str]) -> None:
        if isinstance(key, SigningKey):
            self.key = key
            return
        if isinstance(key, str):
            key_bytes = bytes.fromhex(_strip_private_key_prefixes(key))
        else:
            key_bytes = bytes(key)
        if len(key_bytes) != Secp256k1PrivateKey.LENGTH:
            raise ValueError(
                f"Secp256k1PrivateKey length should be {Secp256k1PrivateKey.LENGTH}, "
                f"got {len(key_bytes)}"
            )
        self.key = SigningKey.from_string(key_bytes, SECP256k1, hashlib.sha3_256)

    @staticmethod
    def from_hex(value: Union[str, bytes]) -> Secp256k1PrivateKey:
        """Parse a key from hex, with or without ``0x`` or the AIP-80 prefix."""
        return Secp256k1PrivateKey(value)

    @staticmethod
    def generate() -> Secp256k1PrivateKey:
        return Secp256k1PrivateKey(SigningKey.generate(SECP256k1, hashfunc=hashlib.sha3_256))

    def public_key(self) -> Secp256k1PublicKey:
        return Secp256k1PublicKey(self.key.verifying_key)

    def to_evm_account_bytes(self) -> bytes:
        """The 32-byte account address this key owns."""
        return self.public_key().to_evm_account_bytes()

    def to_bytes(self) -> bytes:
        return self.key.to_string()

    def hex(self) -> str:
        return f"0x{self.to_bytes().hex()}"

    def __str__(self) -> str:
        return self.hex()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Secp256k1PrivateKey):
            return NotImplemented
        return self.key.to_string() == other.key.to_string()

    def __hash__(self) -> int:
        return hash(self.key.to_string())

    # --- Signing ---

    def sign(self, message: bytes) -> Secp256k1Signature:
        """Wrap ``message`` in the EIP-712 struct and sign the result."""
        return self.sign_digest(eip712_sign_hash(message))

    def sign_digest(self, digest: bytes) -> Secp256k1Signature:
        """Sign 32 bytes that are already a finished digest.

        :meth:`sign` wraps what it is given in ``IntentionTransaction(bytes32
        digest)``, which is all a wallet can render -- one opaque hash.
        Transactions that move funds or grant authority are signed over named
        fields instead (see ``transactions/typed_data``, which builds the digest
        from the payload), so that digest arrives here finished and must not be
        wrapped a second time.
        """
        if len(digest) != 32:
            raise ValueError("digest must be exactly 32 bytes")
        signature = self.key.sign_digest_deterministic(
            digest, hashfunc=hashlib.sha256, sigencode=util.sigencode_string
        )
        return Secp256k1Signature(_normalise_low_s(signature))

    # --- BCS ---

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_bytes(self.to_bytes())

    @staticmethod
    def deserialize(deserializer: Deserializer) -> Secp256k1PrivateKey:
        return Secp256k1PrivateKey(deserializer.deserialize_bytes())


def _strip_private_key_prefixes(value: str) -> str:
    if value.startswith(_AIP80_PREFIX):
        value = value[len(_AIP80_PREFIX) :]
    if value[:2].lower() == "0x":
        value = value[2:]
    return value


class Account:
    """A signing key together with the address it controls."""

    account_address: AccountAddress
    private_key: Secp256k1PrivateKey

    def __init__(
        self, account_address: AccountAddress, private_key: Secp256k1PrivateKey
    ) -> None:
        self.account_address = account_address
        self.private_key = private_key

    @staticmethod
    def from_private_key(
        private_key: Secp256k1PrivateKey, address: Optional[AccountAddress] = None
    ) -> Account:
        """Build an account, deriving its address from the key unless given one."""
        return Account(
            address or AccountAddress(private_key.to_evm_account_bytes()), private_key
        )

    @staticmethod
    def generate() -> Account:
        return Account.from_private_key(Secp256k1PrivateKey.generate())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Account):
            return NotImplemented
        return (
            self.account_address == other.account_address
            and self.private_key == other.private_key
        )

    def __hash__(self) -> int:
        return hash((self.account_address, self.private_key))

    def address(self) -> AccountAddress:
        return self.account_address

    def public_key(self) -> Secp256k1PublicKey:
        return self.private_key.public_key()

    def any_public_key(self) -> AnyPublicKey:
        """The public key with its scheme tag, as authenticators carry it."""
        return AnyPublicKey(self.public_key())

    # --- Signing ---

    def sign(self, message: bytes) -> AnySignature:
        return AnySignature(self.private_key.sign(message))

    def sign_transaction(self, transaction) -> AnySignature:
        """Sign a transaction, letting the payload decide what the signature covers.

        Anything that moves funds or grants authority is signed over named fields
        a wallet can render; ``transactions.typed_data`` decides which payloads
        those are and builds the digest from the payload itself. Everything else
        -- orders, leverage, admin operations -- is signed by an agent key with
        no dialog to render, and keeps the opaque wrapper. The chain makes the
        same choice from the same rules, so the two cannot drift apart.
        """
        from ..transactions import as_raw_transaction
        from ..transactions.signing_message import (
            generate_signing_message_for_transaction,
        )
        from ..transactions.typed_data import typed_data_digest

        raw = as_raw_transaction(transaction)
        typed = typed_data_digest(raw)
        if typed is not None:
            return AnySignature(self.private_key.sign_digest(typed))
        return self.sign(generate_signing_message_for_transaction(raw))

    def sign_transaction_with_authenticator(self, transaction):
        """Sign a transaction and wrap the result as a transaction authenticator."""
        from ..transactions.authenticator import AccountAuthenticatorSingleKey

        return AccountAuthenticatorSingleKey(
            self.any_public_key(), self.sign_transaction(transaction)
        )

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Account addresses.

Addresses are 32 bytes. Accounts created from a secp256k1 key are
EVM-compatible: the low 20 bytes carry the EVM address and the high 12 bytes
are zero, so they render as ``0x`` + 40 chars with an EIP-55 checksum, the same
form the TypeScript and Go SDKs and the relayer API use.
"""

from __future__ import annotations

from typing import Union

from ..bcs import Deserializer, Serializable, Serializer


class ParseAddressError(Exception):
    """Raised when a value cannot be read as an account address."""


AccountAddressInput = Union[str, bytes, bytearray, memoryview, "AccountAddress"]


class AccountAddress(Serializable):
    address: bytes

    LENGTH: int = 32
    EVM_LENGTH: int = 20

    def __init__(self, address: bytes) -> None:
        if len(address) != AccountAddress.LENGTH:
            raise ParseAddressError("Expected address of length 32")
        self.address = bytes(address)

    # --- Comparison ---

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AccountAddress):
            return NotImplemented
        return self.address == other.address

    def __hash__(self) -> int:
        return hash(self.address)

    def equals(self, other: AccountAddress) -> bool:
        return self == other

    # --- Classification ---

    def is_special(self) -> bool:
        """Whether this is one of the reserved addresses ``0x0`` to ``0xf``.

        Special means the first 31 bytes are zero and the last is below 16, so
        the address matches ``^0x0{63}[0-9a-f]$`` and has a one-char short form.
        """
        return all(b == 0 for b in self.address[:-1]) and self.address[-1] < 0b10000

    def is_evm_compatible(self) -> bool:
        """Whether the high 12 bytes are zero, leaving a 20-byte EVM address."""
        return all(
            b == 0
            for b in self.address[: AccountAddress.LENGTH - AccountAddress.EVM_LENGTH]
        )

    # --- Rendering ---

    def __str__(self) -> str:
        return f"0x{self.to_string_without_prefix()}"

    def __repr__(self) -> str:
        return self.__str__()

    def to_string_without_prefix(self) -> str:
        """Canonical form: EVM for EVM-compatible, short for special, long otherwise."""
        if self.is_evm_compatible():
            return _to_eip55_checksum(self.address[-AccountAddress.EVM_LENGTH :].hex())
        if self.is_special():
            return self.address.hex().lstrip("0") or "0"
        return self.address.hex()

    def to_string_long(self) -> str:
        return f"0x{self.to_string_long_without_prefix()}"

    def to_string_long_without_prefix(self) -> str:
        return self.address.hex()

    def to_string_short(self) -> str:
        return f"0x{self.to_string_short_without_prefix()}"

    def to_string_short_without_prefix(self) -> str:
        return self.address.hex().lstrip("0") or "0"

    # --- Factories ---

    @staticmethod
    def from_str(address: str) -> AccountAddress:
        """Parse a canonical address, rejecting anything else.

        Accepts long form (``0x`` + 64 chars), the short form of a special
        address (``0x0`` to ``0xf``) and EVM form (``0x`` + 40 chars). Rejects
        a missing ``0x``, padding zeroes and the short form of a non-special
        address. Use :meth:`from_str_relaxed` where the input is not canonical.
        """
        if not address.startswith("0x"):
            raise ParseAddressError("Hex string must start with a leading 0x.")

        out = AccountAddress.from_str_relaxed(address)
        body_length = len(address) - 2

        if body_length == AccountAddress.LENGTH * 2:
            return out
        if out.is_special():
            if body_length != 1:
                raise ParseAddressError(
                    "The given hex string is a special address not in LONG form, "
                    "it must be 0x0 to 0xf without padding zeroes."
                )
            return out
        if out.is_evm_compatible():
            if body_length != AccountAddress.EVM_LENGTH * 2:
                raise ParseAddressError(
                    "The given hex string is an EVM-compatible address not in LONG "
                    "form, it must be 0x + 40 chars."
                )
            return out
        raise ParseAddressError(
            "The given hex string is not a special address, it must be represented "
            "as 0x + 64 chars."
        )

    @staticmethod
    def from_str_relaxed(address: str) -> AccountAddress:
        """Parse 1 to 64 hex chars, with or without ``0x``, padding allowed."""
        body = address[2:] if address.startswith("0x") else address

        if len(body) < 1:
            raise ParseAddressError(
                "Hex string is too short, must be 1 to 64 chars long, excluding the "
                "leading 0x."
            )
        if len(body) > AccountAddress.LENGTH * 2:
            raise ParseAddressError(
                "Hex string is too long, must be 1 to 64 chars long, excluding the "
                "leading 0x."
            )

        try:
            return AccountAddress(bytes.fromhex(body.rjust(AccountAddress.LENGTH * 2, "0")))
        except ValueError as exc:
            raise ParseAddressError(f"Hex string contains invalid hex characters: {exc}") from exc

    @staticmethod
    def from_(address: AccountAddressInput) -> AccountAddress:
        """Accept any of the forms an address arrives in."""
        if isinstance(address, AccountAddress):
            return address
        if isinstance(address, str):
            return AccountAddress.from_str(address)
        return AccountAddress(bytes(address))

    # --- BCS ---

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_fixed_bytes(self.address)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AccountAddress:
        return AccountAddress(deserializer.deserialize_fixed_bytes(AccountAddress.LENGTH))


def _to_eip55_checksum(address: str) -> str:
    """Mixed-case checksum of a 40-char EVM address, per EIP-55.

    Keccak-256, not SHA3-256: the two differ in padding and a silent swap would
    produce addresses that look right and are not. pycryptodome is a hard
    dependency precisely so this cannot fall back.
    """
    from Crypto.Hash import keccak

    lower = address.lower()
    digest = keccak.new(digest_bits=256, data=lower.encode("ascii")).hexdigest()
    return "".join(
        char.upper() if "a" <= char <= "f" and int(digest[i], 16) >= 8 else char
        for i, char in enumerate(lower)
    )

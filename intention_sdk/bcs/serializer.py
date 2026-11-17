# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""BCS (Binary Canonical Serialization) - Serializer."""

from __future__ import annotations

import typing
from abc import ABC, abstractmethod

MAX_U8 = 2**8 - 1
MAX_U16 = 2**16 - 1
MAX_U32 = 2**32 - 1
MAX_U64 = 2**64 - 1
MAX_U128 = 2**128 - 1
MAX_U256 = 2**256 - 1

MIN_I8 = -(2**7)
MAX_I8 = 2**7 - 1
MIN_I16 = -(2**15)
MAX_I16 = 2**15 - 1
MIN_I32 = -(2**31)
MAX_I32 = 2**31 - 1
MIN_I64 = -(2**63)
MAX_I64 = 2**63 - 1
MIN_I128 = -(2**127)
MAX_I128 = 2**127 - 1
MIN_I256 = -(2**255)
MAX_I256 = 2**255 - 1


class Serializable(ABC):
    """Base class for every BCS-serializable type."""

    @abstractmethod
    def serialize(self, serializer: Serializer) -> None: ...

    def bcs_to_bytes(self) -> bytes:
        serializer = Serializer()
        self.serialize(serializer)
        return serializer.to_bytes()

    def to_string_without_prefix(self) -> str:
        return self.bcs_to_bytes().hex()

    def __str__(self) -> str:
        return f"0x{self.to_string_without_prefix()}"


def _validate_range(value: int, min_value: int, max_value: int) -> None:
    if value < min_value or value > max_value:
        raise ValueError(f"{value} is out of range: [{min_value}, {max_value}]")


class Serializer:
    """Writes values in Binary Canonical Serialization format."""

    _buffer: bytearray

    def __init__(self) -> None:
        self._buffer = bytearray()

    def to_bytes(self) -> bytes:
        """Serialized output accumulated so far."""
        return bytes(self._buffer)

    # --- Fixed-width integers ---

    def serialize_bool(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise ValueError(f"{value} is not a boolean value")
        self._buffer.append(1 if value else 0)

    def serialize_u8(self, value: int) -> None:
        _validate_range(value, 0, MAX_U8)
        self._write_uint(value, 1)

    def serialize_u16(self, value: int) -> None:
        _validate_range(value, 0, MAX_U16)
        self._write_uint(value, 2)

    def serialize_u32(self, value: int) -> None:
        _validate_range(value, 0, MAX_U32)
        self._write_uint(value, 4)

    def serialize_u64(self, value: int) -> None:
        _validate_range(value, 0, MAX_U64)
        self._write_uint(value, 8)

    def serialize_u128(self, value: int) -> None:
        _validate_range(value, 0, MAX_U128)
        self._write_uint(value, 16)

    def serialize_u256(self, value: int) -> None:
        _validate_range(value, 0, MAX_U256)
        self._write_uint(value, 32)

    def serialize_i8(self, value: int) -> None:
        _validate_range(value, MIN_I8, MAX_I8)
        self._write_int(value, 1)

    def serialize_i16(self, value: int) -> None:
        _validate_range(value, MIN_I16, MAX_I16)
        self._write_int(value, 2)

    def serialize_i32(self, value: int) -> None:
        _validate_range(value, MIN_I32, MAX_I32)
        self._write_int(value, 4)

    def serialize_i64(self, value: int) -> None:
        _validate_range(value, MIN_I64, MAX_I64)
        self._write_int(value, 8)

    def serialize_i128(self, value: int) -> None:
        _validate_range(value, MIN_I128, MAX_I128)
        self._write_int(value, 16)

    def serialize_i256(self, value: int) -> None:
        _validate_range(value, MIN_I256, MAX_I256)
        self._write_int(value, 32)

    # --- Variable-length values ---

    def serialize_u32_as_uleb128(self, value: int) -> None:
        _validate_range(value, 0, MAX_U32)
        while value >> 7 != 0:
            self._buffer.append((value & 0x7F) | 0x80)
            value >>= 7
        self._buffer.append(value)

    def serialize_bytes(self, value: bytes) -> None:
        """Length-prefixed bytes."""
        self.serialize_u32_as_uleb128(len(value))
        self._buffer.extend(value)

    def serialize_fixed_bytes(self, value: bytes) -> None:
        """Raw bytes, no length prefix."""
        self._buffer.extend(value)

    def serialize_str(self, value: str) -> None:
        self.serialize_bytes(value.encode("utf-8"))

    # --- Composite values ---

    def serialize(self, value: Serializable) -> None:
        """Serialize a value that knows how to serialize itself."""
        value.serialize(self)

    def serialize_vector(self, values: typing.Sequence[Serializable]) -> None:
        """Length-prefixed sequence of self-serializing values."""
        self.serialize_u32_as_uleb128(len(values))
        for value in values:
            value.serialize(self)

    def serialize_option(self, value: typing.Optional[Serializable]) -> None:
        """Presence flag followed by the value when present."""
        self.serialize_bool(value is not None)
        if value is not None:
            value.serialize(self)

    def serialize_option_str(self, value: typing.Optional[str]) -> None:
        self.serialize_bool(value is not None)
        if value is not None:
            self.serialize_str(value)

    def serialize_option_bytes(self, value: typing.Optional[bytes]) -> None:
        self.serialize_bool(value is not None)
        if value is not None:
            self.serialize_bytes(value)

    # --- Internals ---

    def _write_uint(self, value: int, length: int) -> None:
        self._buffer.extend(value.to_bytes(length, "little", signed=False))

    def _write_int(self, value: int, length: int) -> None:
        self._buffer.extend(value.to_bytes(length, "little", signed=True))

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""BCS (Binary Canonical Serialization) - Deserializer."""

from __future__ import annotations

import typing

T = typing.TypeVar("T")


class Deserializer:
    """Reads values written in Binary Canonical Serialization format."""

    _data: bytes
    _offset: int

    def __init__(self, data: bytes) -> None:
        self._data = bytes(data)
        self._offset = 0

    def remaining(self) -> int:
        return len(self._data) - self._offset

    # --- Fixed-width integers ---

    def deserialize_bool(self) -> bool:
        value = self._read(1)[0]
        if value == 0:
            return False
        if value == 1:
            return True
        raise ValueError(f"BCS deserialize: invalid bool value {value}")

    def deserialize_u8(self) -> int:
        return self._read_uint(1)

    def deserialize_u16(self) -> int:
        return self._read_uint(2)

    def deserialize_u32(self) -> int:
        return self._read_uint(4)

    def deserialize_u64(self) -> int:
        return self._read_uint(8)

    def deserialize_u128(self) -> int:
        return self._read_uint(16)

    def deserialize_u256(self) -> int:
        return self._read_uint(32)

    def deserialize_i8(self) -> int:
        return self._read_int(1)

    def deserialize_i16(self) -> int:
        return self._read_int(2)

    def deserialize_i32(self) -> int:
        return self._read_int(4)

    def deserialize_i64(self) -> int:
        return self._read_int(8)

    def deserialize_i128(self) -> int:
        return self._read_int(16)

    def deserialize_i256(self) -> int:
        return self._read_int(32)

    # --- Variable-length values ---

    def deserialize_u32_from_uleb128(self) -> int:
        result = 0
        shift = 0
        while True:
            byte = self._read(1)[0]
            result |= (byte & 0x7F) << shift
            if byte & 0x80 == 0:
                break
            shift += 7
            if shift >= 35:
                raise ValueError("BCS deserialize: ULEB128 overflow")
        if result > 2**32 - 1:
            raise ValueError("BCS deserialize: ULEB128 exceeds u32")
        return result

    def deserialize_bytes(self) -> bytes:
        """Length-prefixed bytes."""
        return self.deserialize_fixed_bytes(self.deserialize_u32_from_uleb128())

    def deserialize_fixed_bytes(self, length: int) -> bytes:
        """Raw bytes, no length prefix."""
        return self._read(length)

    def deserialize_str(self) -> str:
        return self.deserialize_bytes().decode("utf-8")

    # --- Composite values ---

    def deserialize_struct(self, struct: typing.Any) -> typing.Any:
        """Delegate to the type own ``deserialize`` classmethod."""
        return struct.deserialize(self)

    def deserialize_vector(
        self, read_element: typing.Callable[[Deserializer], T]
    ) -> typing.List[T]:
        """Length-prefixed sequence, each element read by ``read_element``."""
        length = self.deserialize_u32_from_uleb128()
        return [read_element(self) for _ in range(length)]

    def deserialize_option_bool(self) -> typing.Optional[bool]:
        if not self.deserialize_bool():
            return None
        return self.deserialize_bool()

    def deserialize_option_str(self) -> typing.Optional[str]:
        if not self.deserialize_bool():
            return None
        return self.deserialize_str()

    # --- Internals ---

    def _read(self, length: int) -> bytes:
        if length < 0:
            raise ValueError(f"BCS deserialize: negative length {length}")
        if self._offset + length > len(self._data):
            raise ValueError(
                f"BCS deserialize: need {length} bytes but only {self.remaining()} remaining"
            )
        chunk = self._data[self._offset : self._offset + length]
        self._offset += length
        return chunk

    def _read_uint(self, length: int) -> int:
        return int.from_bytes(self._read(length), "little", signed=False)

    def _read_int(self, length: int) -> int:
        return int.from_bytes(self._read(length), "little", signed=True)

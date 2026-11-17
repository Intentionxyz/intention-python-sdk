# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from enum import Enum
from typing import Union

from .common import ParsingError, ParsingResult

HexInput = Union[str, bytes, bytearray, memoryview]


class HexInvalidReason(str, Enum):
    TOO_SHORT = "too_short"
    INVALID_LENGTH = "invalid_length"
    INVALID_HEX_CHARS = "invalid_hex_chars"


class Hex:
    _data: bytes

    def __init__(self, data: bytes):
        self._data = bytes(data)

    def to_bytes(self) -> bytes:
        return self._data

    def to_string_without_prefix(self) -> str:
        return self._data.hex()

    def to_string(self) -> str:
        return f"0x{self.to_string_without_prefix()}"

    def __bytes__(self) -> bytes:
        return self.to_bytes()

    def __str__(self) -> str:
        return self.to_string()

    def __repr__(self) -> str:
        return self.to_string()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Hex):
            return NotImplemented
        return self._data == other._data

    def equals(self, other: "Hex") -> bool:
        return self == other

    @staticmethod
    def from_hex_string(value: str) -> "Hex":
        normalized = value[2:] if value.startswith("0x") else value
        if len(normalized) == 0:
            raise ParsingError(
                "Hex string is too short, must be at least 1 char long, excluding the optional leading 0x.",
                HexInvalidReason.TOO_SHORT,
            )
        if len(normalized) % 2 != 0:
            raise ParsingError(
                "Hex string must be an even number of hex characters.",
                HexInvalidReason.INVALID_LENGTH,
            )
        try:
            return Hex(bytes.fromhex(normalized))
        except ValueError as exc:
            raise ParsingError(
                f"Hex string contains invalid hex characters: {exc}",
                HexInvalidReason.INVALID_HEX_CHARS,
            ) from exc

    @staticmethod
    def from_hex_input(hex_input: HexInput) -> "Hex":
        if isinstance(hex_input, str):
            return Hex.from_hex_string(hex_input)
        return Hex(bytes(hex_input))

    @staticmethod
    def hex_input_to_bytes(hex_input: HexInput) -> bytes:
        return Hex.from_hex_input(hex_input).to_bytes()

    @staticmethod
    def hex_input_to_string(hex_input: HexInput) -> str:
        return Hex.from_hex_input(hex_input).to_string()

    @staticmethod
    def hex_input_to_string_without_prefix(hex_input: HexInput) -> str:
        return Hex.from_hex_input(hex_input).to_string_without_prefix()

    @staticmethod
    def is_valid(value: str) -> ParsingResult[HexInvalidReason]:
        try:
            Hex.from_hex_string(value)
            return ParsingResult(valid=True)
        except ParsingError as exc:
            return ParsingResult(
                valid=False,
                invalid_reason=exc.invalid_reason,
                invalid_reason_message=str(exc),
            )


def hex_to_ascii_string(hex_input: HexInput) -> str:
    return Hex.hex_input_to_bytes(hex_input).decode()


# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""BCS encoding is frozen: every vector here predates the rewrite.

``bcs/`` was rewritten against our own TypeScript implementation, which is only
safe if the bytes did not move -- a signature over different bytes is a
signature the chain rejects, and nothing about it looks wrong until it is
submitted. ``bcs_golden_vectors.json`` was captured from the serializer that
preceded it, so these assertions compare the new encoder against one that was
known to work, not against itself.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from intention_sdk.bcs import Deserializer, Serializer

VECTORS = json.loads(
    (Path(__file__).parent / "bcs_golden_vectors.json").read_text(encoding="utf-8")
)


class BcsGoldenVectors(unittest.TestCase):
    def test_integers(self) -> None:
        for width, cases in VECTORS["ints"].items():
            for value_str, expected in cases.items():
                value = int(value_str)
                with self.subTest(width=width, value=value):
                    serializer = Serializer()
                    getattr(serializer, f"serialize_{width}")(value)
                    self.assertEqual(serializer.to_bytes().hex(), expected)

                    deserializer = Deserializer(bytes.fromhex(expected))
                    self.assertEqual(
                        getattr(deserializer, f"deserialize_{width}")(), value
                    )
                    self.assertEqual(deserializer.remaining(), 0)

    def test_uleb128(self) -> None:
        for value_str, expected in VECTORS["uleb128"].items():
            value = int(value_str)
            with self.subTest(value=value):
                serializer = Serializer()
                serializer.serialize_u32_as_uleb128(value)
                self.assertEqual(serializer.to_bytes().hex(), expected)
                self.assertEqual(
                    Deserializer(bytes.fromhex(expected)).deserialize_u32_from_uleb128(),
                    value,
                )

    def test_strings(self) -> None:
        for value, expected in VECTORS["strings"].items():
            with self.subTest(value=value[:16]):
                serializer = Serializer()
                serializer.serialize_str(value)
                self.assertEqual(serializer.to_bytes().hex(), expected)
                self.assertEqual(
                    Deserializer(bytes.fromhex(expected)).deserialize_str(), value
                )

    def test_bytes(self) -> None:
        for value_hex, expected in VECTORS["bytes"].items():
            value = bytes.fromhex(value_hex)
            with self.subTest(length=len(value)):
                serializer = Serializer()
                serializer.serialize_bytes(value)
                self.assertEqual(serializer.to_bytes().hex(), expected)
                self.assertEqual(
                    Deserializer(bytes.fromhex(expected)).deserialize_bytes(), value
                )

    def test_bool(self) -> None:
        for value_str, expected in VECTORS["bool"].items():
            value = value_str == "True"
            with self.subTest(value=value):
                serializer = Serializer()
                serializer.serialize_bool(value)
                self.assertEqual(serializer.to_bytes().hex(), expected)
                self.assertEqual(
                    Deserializer(bytes.fromhex(expected)).deserialize_bool(), value
                )

    def test_mixed_streams(self) -> None:
        """Values written back to back, so a stray byte anywhere shows up."""
        for index, case in enumerate(VECTORS["mixed"]):
            with self.subTest(case=index):
                serializer = Serializer()
                for kind, value in case["ops"]:
                    if kind == "bool":
                        serializer.serialize_bool(value)
                    elif kind == "str":
                        serializer.serialize_str(value)
                    elif kind == "bytes":
                        serializer.serialize_bytes(bytes.fromhex(value))
                    else:
                        getattr(serializer, f"serialize_{kind}")(value)
                self.assertEqual(serializer.to_bytes().hex(), case["hex"])

    def test_range_checks_reject(self) -> None:
        serializer = Serializer()
        for method, value in (
            ("serialize_u8", 256),
            ("serialize_u8", -1),
            ("serialize_i8", 128),
            ("serialize_i8", -129),
            ("serialize_u32_as_uleb128", 2**32),
        ):
            with self.subTest(method=method, value=value):
                with self.assertRaises(ValueError):
                    getattr(serializer, method)(value)

    def test_short_read_raises(self) -> None:
        with self.assertRaises(ValueError):
            Deserializer(b"\x01").deserialize_u64()


if __name__ == "__main__":
    unittest.main()

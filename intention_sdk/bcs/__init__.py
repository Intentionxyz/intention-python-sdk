# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""BCS (Binary Canonical Serialization) primitives."""

from .deserializer import Deserializer
from .serializer import (
    MAX_I8,
    MAX_I16,
    MAX_I32,
    MAX_I64,
    MAX_I128,
    MAX_I256,
    MAX_U8,
    MAX_U16,
    MAX_U32,
    MAX_U64,
    MAX_U128,
    MAX_U256,
    MIN_I8,
    MIN_I16,
    MIN_I32,
    MIN_I64,
    MIN_I128,
    MIN_I256,
    Serializable,
    Serializer,
)

__all__ = [
    "Deserializer",
    "Serializable",
    "Serializer",
    "MAX_U8",
    "MAX_U16",
    "MAX_U32",
    "MAX_U64",
    "MAX_U128",
    "MAX_U256",
    "MIN_I8",
    "MAX_I8",
    "MIN_I16",
    "MAX_I16",
    "MIN_I32",
    "MAX_I32",
    "MIN_I64",
    "MAX_I64",
    "MIN_I128",
    "MAX_I128",
    "MIN_I256",
    "MAX_I256",
]

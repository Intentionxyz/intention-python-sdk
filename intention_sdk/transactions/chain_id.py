# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The chain identifier carried by every transaction."""

from __future__ import annotations

from typing import Union

from ..bcs import Deserializer, Serializable, Serializer


class ChainId(Serializable):
    """A single u8 naming the network a transaction is meant for."""

    chain_id: int

    def __init__(self, chain_id: Union[ChainId, int]) -> None:
        self.chain_id = chain_id.chain_id if isinstance(chain_id, ChainId) else int(chain_id)

    def __int__(self) -> int:
        return self.chain_id

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ChainId):
            return self.chain_id == other.chain_id
        if isinstance(other, int):
            return self.chain_id == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.chain_id)

    def __str__(self) -> str:
        return str(self.chain_id)

    def __repr__(self) -> str:
        return f"ChainId({self.chain_id})"

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u8(self.chain_id)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> ChainId:
        return ChainId(deserializer.deserialize_u8())

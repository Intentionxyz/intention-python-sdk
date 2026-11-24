# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from ..bcs import Deserializer, Serializer


class SubaccountId:
    """
    Subaccount identity (main address + number + derived sub-address + user_name).
    BCS layout (fixed size, 84 bytes):
      address:     [u8; 32]  (32 bytes)
      number:      u32       (4 bytes LE)
      sub_address: [u8; 32]  (32 bytes)
      user_name:   [u8; 16]  (16 bytes)
    """

    address: bytes  # 32 bytes
    number: int  # u32
    sub_address: bytes  # 32 bytes
    user_name: bytes  # 16 bytes

    def __init__(
        self,
        address: bytes,
        number: int,
        sub_address: bytes,
        user_name: bytes = b"\x00" * 16,
    ):
        if len(address) != 32:
            raise ValueError("SubaccountId address must be exactly 32 bytes")
        if len(sub_address) != 32:
            raise ValueError("SubaccountId sub_address must be exactly 32 bytes")
        if len(user_name) != 16:
            raise ValueError("SubaccountId user_name must be exactly 16 bytes")
        self.address = address
        self.number = number
        self.sub_address = sub_address
        self.user_name = user_name

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_fixed_bytes(self.address)
        serializer.serialize_u32(self.number)
        serializer.serialize_fixed_bytes(self.sub_address)
        serializer.serialize_fixed_bytes(self.user_name)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> SubaccountId:
        return SubaccountId(
            address=deserializer.deserialize_fixed_bytes(32),
            number=deserializer.deserialize_u32(),
            sub_address=deserializer.deserialize_fixed_bytes(32),
            user_name=deserializer.deserialize_fixed_bytes(16),
        )

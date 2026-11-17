# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The unsigned transaction, and the single-signer wrapper around it.

Mirrors transactions/raw_transaction.ts.
"""

from __future__ import annotations

import hashlib
from typing import Optional, Union

from ..bcs import MAX_U64, Deserializer, Serializable, Serializer
from ..core.account_address import AccountAddress
from .chain_id import ChainId
from .dex_payloads import TransactionPayload, is_cross_transfer_orderless_payload

RAW_TRANSACTION_SALT = b"INTENTION::RawTransaction"


class RawTransaction(Serializable):
    """A transaction before it is signed."""

    sender: AccountAddress
    sequence_number: int
    payload: TransactionPayload
    max_gas_amount: int
    gas_unit_price: int
    expiration_timestamp_secs: int
    chain_id: ChainId

    def __init__(
        self,
        sender: AccountAddress,
        sequence_number: int,
        payload: TransactionPayload,
        max_gas_amount: int,
        gas_unit_price: int,
        expiration_timestamp_secs: int,
        chain_id: Union[ChainId, int],
    ) -> None:
        self.sender = sender
        self.sequence_number = sequence_number
        self.payload = payload
        self.max_gas_amount = max_gas_amount
        self.gas_unit_price = gas_unit_price
        self.expiration_timestamp_secs = expiration_timestamp_secs
        self.chain_id = ChainId(chain_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RawTransaction):
            return NotImplemented
        return (
            self.sender == other.sender
            and self.sequence_number == other.sequence_number
            and self.payload == other.payload
            and self.max_gas_amount == other.max_gas_amount
            and self.gas_unit_price == other.gas_unit_price
            and self.expiration_timestamp_secs == other.expiration_timestamp_secs
            and self.chain_id == other.chain_id
        )

    def __str__(self) -> str:
        return (
            "RawTransaction:\n"
            f"    sender: {self.sender}\n"
            f"    sequence_number: {self.sequence_number}\n"
            f"    payload: {self.payload}\n"
            f"    max_gas_amount: {self.max_gas_amount}\n"
            f"    gas_unit_price: {self.gas_unit_price}\n"
            f"    expiration_timestamp_secs: {self.expiration_timestamp_secs}\n"
            f"    chain_id: {self.chain_id}\n"
        )

    # --- Factories ---

    @staticmethod
    def create_orderless(
        sender: AccountAddress,
        payload: TransactionPayload,
        max_gas_amount: int,
        gas_unit_price: int,
        expiration_timestamp_secs: int,
        chain_id: Union[ChainId, int],
    ) -> RawTransaction:
        """An orderless transaction, which carries MAX_U64 in place of a sequence number."""
        if is_cross_transfer_orderless_payload(payload):
            raise ValueError(
                "CrossTransfer requires an explicit replay nonce; "
                "use create_cross_transfer_orderless"
            )
        return RawTransaction(
            sender,
            MAX_U64,
            payload,
            max_gas_amount,
            gas_unit_price,
            expiration_timestamp_secs,
            chain_id,
        )

    @staticmethod
    def create_cross_transfer_orderless(
        sender: AccountAddress,
        payload: TransactionPayload,
        replay_protection_nonce: int,
        max_gas_amount: int,
        gas_unit_price: int,
        expiration_timestamp_secs: int,
        chain_id: Union[ChainId, int],
    ) -> RawTransaction:
        """A CrossTransfer, which replaces the sequence number with its own replay nonce."""
        if not is_cross_transfer_orderless_payload(payload):
            raise ValueError(
                "create_cross_transfer_orderless requires a CrossTransfer orderless payload"
            )
        if isinstance(replay_protection_nonce, bool) or not isinstance(
            replay_protection_nonce, int
        ):
            raise ValueError("CrossTransfer replay nonce is required and must be an int")
        if replay_protection_nonce < 0 or replay_protection_nonce > MAX_U64:
            raise ValueError("CrossTransfer replay nonce must be in the u64 range")
        if replay_protection_nonce == MAX_U64:
            raise ValueError(
                "CrossTransfer replay nonce must not use the reserved MAX_U64 value"
            )
        return RawTransaction(
            sender,
            replay_protection_nonce,
            payload,
            max_gas_amount,
            gas_unit_price,
            expiration_timestamp_secs,
            chain_id,
        )

    # --- Signing input ---

    def prehash(self) -> bytes:
        """The domain-separating prefix the signing message starts with."""
        return hashlib.sha3_256(RAW_TRANSACTION_SALT).digest()

    def keyed(self) -> bytes:
        """The bytes a signature covers: the prefix followed by this transaction."""
        return self.prehash() + self.bcs_to_bytes()

    # --- BCS ---

    def serialize(self, serializer: Serializer) -> None:
        self.sender.serialize(serializer)
        serializer.serialize_u64(self.sequence_number)
        self.payload.serialize(serializer)
        serializer.serialize_u64(self.max_gas_amount)
        serializer.serialize_u64(self.gas_unit_price)
        serializer.serialize_u64(self.expiration_timestamp_secs)
        self.chain_id.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> RawTransaction:
        return RawTransaction(
            AccountAddress.deserialize(deserializer),
            deserializer.deserialize_u64(),
            TransactionPayload.deserialize(deserializer),
            deserializer.deserialize_u64(),
            deserializer.deserialize_u64(),
            deserializer.deserialize_u64(),
            ChainId.deserialize(deserializer),
        )


class SimpleTransaction:
    """A raw transaction with one signer."""

    raw_transaction: RawTransaction
    fee_payer_address: Optional[AccountAddress]

    def __init__(
        self,
        raw_transaction: RawTransaction,
        fee_payer_address: Optional[AccountAddress] = None,
    ) -> None:
        self.raw_transaction = raw_transaction
        self.fee_payer_address = fee_payer_address

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SimpleTransaction):
            return NotImplemented
        return (
            self.raw_transaction == other.raw_transaction
            and self.fee_payer_address == other.fee_payer_address
        )

    def __str__(self) -> str:
        return str(self.raw_transaction)


def as_raw_transaction(
    transaction: Union[SimpleTransaction, RawTransaction]
) -> RawTransaction:
    """Unwrap a SimpleTransaction, or pass a RawTransaction through."""
    if isinstance(transaction, SimpleTransaction):
        return transaction.raw_transaction
    return transaction

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shared build/sign/submit/wait orchestration for user-level DEX clients."""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..core.account import Account
from .client import ApiError, RestClient
from ..events.dex_event_decoder import DecodedTransactionEvent, decode_transaction_events
from ..transactions.dex_payloads import DexOrderlessTx, DexOrders, DexTx
from ..types.enums import CreatedBy, DexOrderlessTxVariant
from ..bcs import MAX_U64
from ..transactions import (
    RawTransaction,
    TransactionPayload,
    is_cross_transfer_orderless_payload,
)


class TransactionTimeoutError(TimeoutError):
    def __init__(self, txn_hash: str, timeout_secs: float):
        super().__init__(
            f"transaction {txn_hash} was not confirmed within {timeout_secs:g}s"
        )
        self.txn_hash = txn_hash
        self.timeout_secs = timeout_secs


class TransactionExecutionError(RuntimeError):
    def __init__(self, txn_hash: str, transaction: Dict[str, Any]):
        vm_status = transaction.get("vm_status", "unknown VM failure")
        super().__init__(f"transaction {txn_hash} failed: {vm_status}")
        self.txn_hash = txn_hash
        self.transaction = transaction


@dataclass(frozen=True)
class PendingTransactionResult:
    hash: str


@dataclass(frozen=True)
class DexExecutionResult:
    hash: str
    transaction: Dict[str, Any]
    events: List[DecodedTransactionEvent]


@dataclass(frozen=True)
class SubmitOptions:
    max_gas_amount: Optional[int] = None
    gas_unit_price: Optional[int] = None
    expiration_timestamp_secs: Optional[int] = None
    encoding: Optional[str] = None
    # Independent from the CrossTransfer business nonce embedded in the payload.
    # A cryptographically random u64 is generated when omitted.
    replay_protection_nonce: Optional[int] = None


def _cross_transfer_replay_nonce(configured: Optional[int]) -> int:
    if configured is not None:
        return configured
    while True:
        nonce = secrets.randbits(64)
        if nonce != MAX_U64:
            return nonce


class DexTransactionExecutor:
    """Submit DEX orderless transactions with one consistent confirmation path."""

    def __init__(self, rest_client: RestClient, signer: Account):
        self.rest_client = rest_client
        self.signer = signer

    async def submit_orderless(
        self,
        orderless_tx: DexOrderlessTx,
        *,
        options: Optional[SubmitOptions] = None,
    ) -> PendingTransactionResult:
        options = options or SubmitOptions()
        config = self.rest_client.client_config
        expiration = options.expiration_timestamp_secs
        if expiration is None:
            expiration = int(time.time()) + config.expiration_ttl
        payload = TransactionPayload(orderless_tx)
        raw_args = {
            "sender": self.signer.account_address,
            "payload": payload,
            "max_gas_amount": (
                options.max_gas_amount
                if options.max_gas_amount is not None
                else config.max_gas_amount
            ),
            "gas_unit_price": (
                options.gas_unit_price
                if options.gas_unit_price is not None
                else config.gas_unit_price
            ),
            "expiration_timestamp_secs": expiration,
            "chain_id": await self.rest_client.chain_id(),
        }
        if is_cross_transfer_orderless_payload(payload):
            raw = RawTransaction.create_cross_transfer_orderless(
                replay_protection_nonce=_cross_transfer_replay_nonce(
                    options.replay_protection_nonce
                ),
                **raw_args,
            )
        else:
            raw = RawTransaction.create_orderless(**raw_args)
        authenticator = self.signer.sign_transaction_with_authenticator(raw)
        txn_hash = await self.rest_client.submit_transaction(
            raw, authenticator, encoding=options.encoding
        )
        return PendingTransactionResult(txn_hash)

    async def wait_for_transaction(
        self,
        txn_hash: str,
        *,
        timeout_secs: float = 30,
        poll_interval_secs: float = 1,
        check_success: bool = True,
    ) -> Dict[str, Any]:
        if timeout_secs <= 0:
            raise ValueError("timeout_secs must be positive")
        if poll_interval_secs <= 0:
            raise ValueError("poll_interval_secs must be positive")
        deadline = time.monotonic() + timeout_secs
        while time.monotonic() < deadline:
            try:
                transaction = await self.rest_client.transaction_by_hash(txn_hash)
            except ApiError as exc:
                if exc.status_code != 404:
                    raise
            else:
                if transaction.get("type") != "pending_transaction":
                    if check_success and not transaction.get("success", False):
                        raise TransactionExecutionError(txn_hash, transaction)
                    return transaction
            await asyncio.sleep(poll_interval_secs)
        raise TransactionTimeoutError(txn_hash, timeout_secs)

    async def execute_orderless(
        self,
        orderless_tx: DexOrderlessTx,
        *,
        options: Optional[SubmitOptions] = None,
        timeout_secs: float = 30,
        poll_interval_secs: float = 1,
    ) -> DexExecutionResult:
        pending = await self.submit_orderless(orderless_tx, options=options)
        transaction = await self.wait_for_transaction(
            pending.hash,
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
        )
        raw_events = transaction.get("events")
        events = (
            decode_transaction_events(raw_events)
            if isinstance(raw_events, list)
            else []
        )
        return DexExecutionResult(pending.hash, transaction, events)

    async def submit_orders(
        self,
        orders: DexOrders,
        *,
        nonce: Optional[int] = None,
        created_by: CreatedBy = CreatedBy.USER,
        on_behalf_of: Optional[Any] = None,
        options: Optional[SubmitOptions] = None,
    ) -> PendingTransactionResult:
        dex_tx = DexTx(
            int(time.time() * 1_000_000) if nonce is None else nonce,
            orders,
            created_by,
            on_behalf_of,
        )
        orderless = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)
        return await self.submit_orderless(orderless, options=options)

    async def execute_orders(
        self,
        orders: DexOrders,
        *,
        nonce: Optional[int] = None,
        created_by: CreatedBy = CreatedBy.USER,
        on_behalf_of: Optional[Any] = None,
        options: Optional[SubmitOptions] = None,
        timeout_secs: float = 30,
        poll_interval_secs: float = 1,
    ) -> DexExecutionResult:
        dex_tx = DexTx(
            int(time.time() * 1_000_000) if nonce is None else nonce,
            orders,
            created_by,
            on_behalf_of,
        )
        orderless = DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx)
        return await self.execute_orderless(
            orderless,
            options=options,
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
        )

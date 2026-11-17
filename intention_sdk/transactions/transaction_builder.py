# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Standalone transaction helper functions - TS-aligned module-level helpers.

These functions wrap existing substrate primitives (RestClient, transactions.py)
to match the TypeScript SDK's stateless module-level helper pattern.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from typing_extensions import TypedDict

from .authenticator import generate_signed_transaction
from .signing_message import (
    generate_signing_message_for_transaction,
    generate_user_transaction_hash,
)

IntentionClientConfig = TypedDict("IntentionClientConfig", {"nodeUrl": str})

LedgerInfo = TypedDict(
    "LedgerInfo",
    {
        "chain_id": int,
        "epoch": str,
        "ledger_version": str,
        "oldest_ledger_version": str,
        "ledger_timestamp": str,
        "node_role": str,
        "oldest_block_height": str,
        "block_height": str,
        "git_hash": str,
    },
)


async def submit_transaction(
    config: IntentionClientConfig,
    transaction: Any,
    sender_authenticator: Optional[Any] = None,
    *,
    encoding: Optional[str] = None,
    client_config: Optional[Dict[str, Any]] = None,
) -> dict:
    """POST a signed transaction to the node.

    Passing only ``transaction`` preserves the original BCS-bytes helper behavior.
    Passing ``transaction`` + ``sender_authenticator`` uses the shared JSON/BCS
    submission encoder, defaulting to JSON like the low-level ``RestClient``.
    """
    import httpx

    from ..api.client import (
        MIME_BCS_SIGNED_TRANSACTION,
        ClientConfig,
        build_submission_body,
    )

    url = config["nodeUrl"].rstrip("/")
    if sender_authenticator is None:
        content_type = MIME_BCS_SIGNED_TRANSACTION
        body = transaction
    else:
        content_type, body = build_submission_body(
            _client_config_from_options(client_config),
            transaction,
            sender_authenticator,
            encoding,
        )

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{url}/transactions",
            content=body,
            headers={
                "Content-Type": content_type,
            },
        )
        response.raise_for_status()
        return response.json()


def _client_config_from_options(options: Optional[Dict[str, Any]]) -> ClientConfig:
    from ..api.client import ClientConfig

    if not options:
        return ClientConfig()

    key_map = {
        "defaultSubmissionEncoding": "default_submission_encoding",
        "jsonUnsupportedPayloadFallback": "json_unsupported_payload_fallback",
    }
    normalized = {}
    for key, value in options.items():
        normalized[key_map.get(key, key)] = value
    allowed = ClientConfig.__dataclass_fields__
    return ClientConfig(
        **{
            key: value
            for key, value in normalized.items()
            if key in allowed
        }
    )


async def get_ledger_info(config: IntentionClientConfig) -> LedgerInfo:
    """GET ledger info from the node."""
    import httpx

    url = config["nodeUrl"].rstrip("/")
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def wait_for_transaction(
    config: IntentionClientConfig,
    txn_hash: str,
    *,
    timeout_secs: int = 20,
    check_success: bool = True,
) -> dict:
    """Poll until the transaction is confirmed or timeout."""
    import asyncio

    import httpx

    url = config["nodeUrl"].rstrip("/")
    deadline = asyncio.get_event_loop().time() + timeout_secs
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            try:
                resp = await client.get(
                    f"{url}/transactions/by_hash/{txn_hash}",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("type") != "pending_transaction":
                        if check_success and not data.get("success"):
                            raise RuntimeError(
                                f"Transaction failed: {data.get('vm_status')}"
                            )
                        return data
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
    raise TimeoutError(f"Transaction {txn_hash} not confirmed within {timeout_secs}s")


async def build_transaction(
    intention_config: Any,
    sender: Any,
    payload: Any,
    options: Optional[Dict[str, Any]] = None,
) -> Any:
    """Wrap a payload in a transaction this chain can take.

    Every transaction here is orderless, so there is no sequence number to go
    and fetch: create_orderless puts MAX_U64 in its place. A CrossTransfer
    needs its own replay nonce and so is built through
    RawTransaction.create_cross_transfer_orderless instead.
    """
    from .raw_transaction import RawTransaction, SimpleTransaction

    options = options or {}
    sender_address = sender.address() if hasattr(sender, "address") else sender
    raw_txn = RawTransaction.create_orderless(
        sender=sender_address,
        payload=payload,
        max_gas_amount=options.get("max_gas_amount", 200_000),
        gas_unit_price=options.get("gas_unit_price", 100),
        expiration_timestamp_secs=options.get(
            "expiration_timestamp_secs", int(time.time()) + 30
        ),
        chain_id=options.get("chain_id", 4),
    )
    return SimpleTransaction(raw_txn)

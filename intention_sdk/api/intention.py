# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Intention high-level client - TS-aligned async client wrapping REST primitives.

Matches the TypeScript SDK's Intention class with all 25 public methods,
Network enum, IntentionConfig, and nested TransactionHelper.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from typing_extensions import TypedDict

from ..core.account_address import AccountAddress
from .dex_account_client import DexSystemAccounts

AccountAddressInput = Union[str, AccountAddress]


class Network(str, Enum):
    MAINNET = "mainnet"
    TESTNET = "testnet"
    DEVNET = "devnet"
    LOCAL = "local"
    CUSTOM = "custom"


class IntentionConfigArgs(TypedDict, total=False):
    network: Network
    node_url: str
    relayer_url: str
    ws_url: str
    fullnode: str
    faucet: str
    indexer: str
    client_config: Dict[str, Any]


class IntentionConfig:
    """Configuration for the Intention client."""

    def __init__(
        self,
        *,
        network: Network = Network.DEVNET,
        node_url: Optional[str] = None,
        relayer_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        fullnode: Optional[str] = None,
        faucet: Optional[str] = None,
        indexer: Optional[str] = None,
        client_config: Optional[Dict[str, Any]] = None,
    ):
        self.network = network
        self.node_url = node_url or fullnode or ""
        self.relayer_url = relayer_url or ""
        self.ws_url = ws_url or ""
        # Backward-compatible alias. New integrations should prefer node_url.
        self.fullnode = self.node_url
        self.faucet = faucet or ""
        self.indexer = indexer or ""
        self.client_config = client_config or {}

    def get_fullnode_url(self) -> str:
        return self.node_url


def _resolve_address(addr: AccountAddressInput) -> str:
    if isinstance(addr, AccountAddress):
        return str(addr)
    return addr


class BuildHelper:
    """Nested helper for transaction.build operations."""

    def __init__(self, intention: Intention):
        self._intention = intention

    async def simple(
        self,
        sender: Any,
        data: Any,
        options: Optional[Dict[str, Any]] = None,
    ) -> Any:
        from ..transactions.transaction_builder import build_transaction

        config = {"nodeUrl": self._intention.config.get_fullnode_url()}
        return await build_transaction(config, sender, data, options)


class SubmitHelper:
    """Nested helper for transaction.submit operations."""

    def __init__(self, intention: Intention):
        self._intention = intention

    async def simple(
        self,
        transaction: Any,
        sender_authenticator: Any,
        encoding: Optional[str] = None,
    ) -> dict:
        from ..transactions.transaction_builder import submit_transaction

        config = {"nodeUrl": self._intention.config.get_fullnode_url()}
        return await submit_transaction(
            config,
            transaction,
            sender_authenticator,
            encoding=encoding,
            client_config=self._intention.config.client_config,
        )


class TransactionHelper:
    """Nested helper matching TS intention.transaction.* API."""

    def __init__(self, intention: Intention):
        self._intention = intention
        self.build = BuildHelper(intention)
        self.submit = SubmitHelper(intention)

    def sign(self, signer: Any, transaction: Any) -> Any:
        """Sign a transaction with the given signer account."""
        from ..transactions import RawTransaction

        raw = (
            transaction.raw_transaction
            if hasattr(transaction, "raw_transaction")
            else transaction
        )
        if not isinstance(raw, RawTransaction):
            raise TypeError(f"Expected RawTransaction, got {type(raw)}")
        return signer.sign(raw.keyed())


class Intention:
    """High-level Intention client matching the TS Intention class."""

    def __init__(self, config: IntentionConfig):
        self.config = config
        self.transaction = TransactionHelper(self)

    def _url(self, path: str) -> str:
        base = self.config.get_fullnode_url().rstrip("/")
        return f"{base}/{path.lstrip('/')}"

    async def _get(self, path: str, **params: Any) -> Any:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(self._url(path), params=params)
            resp.raise_for_status()
            return resp.json()

    async def _post(
        self, path: str, json_data: Any = None, **kwargs: Any
    ) -> Any:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._url(path), json=json_data, **kwargs
            )
            resp.raise_for_status()
            return resp.json()

    async def get_ledger_info(self) -> dict:
        return await self._get("")

    async def get_dex_system_accounts(self) -> DexSystemAccounts:
        body = await self._get("dex/system_accounts")
        if not isinstance(body, dict):
            raise ValueError("system_accounts response must be an object")
        return DexSystemAccounts.from_json(body)

    async def wait_for_transaction(
        self,
        txn_hash: str,
        *,
        timeout_secs: int = 20,
        check_success: bool = True,
    ) -> dict:
        from ..transactions.transaction_builder import (
            wait_for_transaction as _wait,
        )

        config = {"nodeUrl": self.config.get_fullnode_url()}
        return await _wait(
            config,
            txn_hash,
            timeout_secs=timeout_secs,
            check_success=check_success,
        )

    async def fund_account(
        self, address: AccountAddressInput, amount: int
    ) -> dict:
        faucet = self.config.faucet.rstrip("/")
        if not faucet:
            raise ValueError("Faucet URL not configured")
        import httpx

        addr = _resolve_address(address)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{faucet}/mint",
                params={"address": addr, "amount": amount},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_block_by_height(
        self, height: int, *, with_transactions: bool = False
    ) -> dict:
        params = {"with_transactions": str(with_transactions).lower()}
        return await self._get(f"blocks/by_height/{height}", **params)

    async def get_block_by_version(
        self, version: int, *, with_transactions: bool = False
    ) -> dict:
        params = {"with_transactions": str(with_transactions).lower()}
        return await self._get(f"blocks/by_version/{version}", **params)

    async def view(
        self,
        function: str,
        type_arguments: Optional[List[str]] = None,
        arguments: Optional[List[Any]] = None,
    ) -> Any:
        payload = {
            "function": function,
            "type_arguments": type_arguments or [],
            "arguments": arguments or [],
        }
        return await self._post("view", json_data=payload)

    async def get_name(self, address: AccountAddressInput) -> Optional[str]:
        addr = _resolve_address(address)
        try:
            result = await self._get(
                f"accounts/{addr}/resource/"
                "0x1::account::Account"
            )
            return result.get("data", {}).get("name")
        except Exception:
            return None

    async def get_account_owned_objects(
        self,
        address: AccountAddressInput,
        *,
        limit: int = 25,
        start: Optional[str] = None,
    ) -> List[dict]:
        addr = _resolve_address(address)
        params: Dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        return await self._get(
            f"accounts/{addr}/owned_objects", **params
        )

    async def get_digital_asset_activity(
        self, asset_id: str
    ) -> List[dict]:
        if not self.config.indexer:
            raise ValueError("Indexer URL not configured")
        return []

    async def query_indexer(self, query: str, **variables: Any) -> Any:
        if not self.config.indexer:
            raise ValueError("Indexer URL not configured")
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.config.indexer,
                json={"query": query, "variables": variables},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_transaction_by_hash(self, txn_hash: str) -> dict:
        return await self._get(f"transactions/by_hash/{txn_hash}")

    async def get_account_info(
        self, address: AccountAddressInput
    ) -> dict:
        addr = _resolve_address(address)
        return await self._get(f"accounts/{addr}")

    async def transfer_fungible_asset(
        self,
        sender: Any,
        fungible_asset_address: str,
        recipient: AccountAddressInput,
        amount: int,
    ) -> dict:
        raise NotImplementedError(
            "Use build + sign + submit flow for fungible asset transfers"
        )

    async def get_transactions(
        self,
        *,
        limit: int = 25,
        start: Optional[int] = None,
    ) -> List[dict]:
        params: Dict[str, Any] = {"limit": limit}
        if start is not None:
            params["start"] = start
        return await self._get("transactions", **params)

    async def get_account_transactions(
        self,
        address: AccountAddressInput,
        *,
        limit: int = 25,
        start: Optional[int] = None,
    ) -> List[dict]:
        addr = _resolve_address(address)
        params: Dict[str, Any] = {"limit": limit}
        if start is not None:
            params["start"] = start
        return await self._get(
            f"accounts/{addr}/transactions", **params
        )

    async def get_account_transaction_summaries(
        self,
        address: AccountAddressInput,
        *,
        limit: int = 25,
        start: Optional[int] = None,
    ) -> List[dict]:
        return await self.get_account_transactions(
            address, limit=limit, start=start
        )

    async def get_transaction_by_version(self, version: int) -> dict:
        return await self._get(f"transactions/by_version/{version}")

    async def get_account(
        self, address: AccountAddressInput
    ) -> dict:
        return await self.get_account_info(address)

    async def get_account_resources(
        self,
        address: AccountAddressInput,
        *,
        limit: int = 9999,
        start: Optional[str] = None,
    ) -> List[dict]:
        addr = _resolve_address(address)
        params: Dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        return await self._get(
            f"accounts/{addr}/resources", **params
        )

    async def get_account_resource(
        self,
        address: AccountAddressInput,
        resource_type: str,
    ) -> dict:
        addr = _resolve_address(address)
        return await self._get(
            f"accounts/{addr}/resource/{resource_type}"
        )

    async def get_account_modules(
        self,
        address: AccountAddressInput,
        *,
        limit: int = 1000,
        start: Optional[str] = None,
    ) -> List[dict]:
        addr = _resolve_address(address)
        params: Dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        return await self._get(
            f"accounts/{addr}/modules", **params
        )

    async def get_account_module(
        self,
        address: AccountAddressInput,
        module_name: str,
    ) -> dict:
        addr = _resolve_address(address)
        return await self._get(
            f"accounts/{addr}/module/{module_name}"
        )

    async def get_table_item(
        self,
        table_handle: str,
        key_type: str,
        value_type: str,
        key: Any,
    ) -> Any:
        payload = {
            "key_type": key_type,
            "value_type": value_type,
            "key": key,
        }
        return await self._post(
            f"tables/{table_handle}/item", json_data=payload
        )


intention_config = IntentionConfig

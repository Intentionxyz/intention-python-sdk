# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx

from ..core.account_address import AccountAddress
from ..transactions.json_submit import (
    UnsupportedJsonPayloadError,
    generate_submit_transaction_request,
)
from ..transactions import (
    RawTransaction,
    SignedTransaction,
    TransactionPayload,
)

MIME_BCS_SIGNED_TRANSACTION = "application/x.intention.signed_transaction+bcs"
MIME_JSON = "application/json"


@dataclass
class ClientConfig:
    expiration_ttl: int = 30
    gas_unit_price: int = 100
    max_gas_amount: int = 100_000
    transaction_wait_in_seconds: int = 20
    http2: bool = True
    trust_env: bool = True
    api_key: Optional[str] = None
    # Wire encoding for transaction submission. JSON is the default, matching the
    # TS SDK. BCS signing is unchanged; JSON only re-encodes the signed txn.
    default_submission_encoding: str = "json"
    # When a payload has no JSON renderer and no explicit encoding was requested:
    # "error" raises (TS-aligned default), "bcs" silently falls back to BCS.
    # Callers submitting a payload the JSON renderer has no shape for should pass
    # encoding="bcs" or opt into the "bcs" fallback.
    json_unsupported_payload_fallback: str = "error"


def _bcs_submission_body(
    transaction: Any, sender_authenticator: Any
) -> Tuple[str, bytes]:
    raw = getattr(transaction, "raw_transaction", transaction)
    signed = SignedTransaction(raw, sender_authenticator)
    return MIME_BCS_SIGNED_TRANSACTION, signed.bytes()


def build_submission_body(
    config: ClientConfig,
    transaction: Any,
    sender_authenticator: Any,
    encoding: Optional[str] = None,
) -> Tuple[str, bytes]:
    """Resolve the submission encoding and return ``(content_type, body)``.

    ``encoding`` overrides the config default. JSON rendering that hits an
    unsupported payload falls back to BCS only when no explicit encoding was
    requested and the config opts into the BCS fallback; otherwise it raises.
    """
    resolved = encoding or config.default_submission_encoding or "json"
    if resolved == "json":
        try:
            request = generate_submit_transaction_request(
                transaction, sender_authenticator
            )
            return MIME_JSON, json.dumps(request).encode("utf-8")
        except UnsupportedJsonPayloadError:
            if (
                encoding is None
                and config.json_unsupported_payload_fallback == "bcs"
            ):
                return _bcs_submission_body(transaction, sender_authenticator)
            raise
    return _bcs_submission_body(transaction, sender_authenticator)


class RestClient:
    """Minimal Intention fullnode REST client."""

    def __init__(self, base_url: str, client_config: ClientConfig = ClientConfig()):
        self.base_url = base_url.rstrip("/")
        self.client_config = client_config
        self._chain_id: Optional[int] = None
        headers = {}
        if client_config.api_key:
            headers["Authorization"] = f"Bearer {client_config.api_key}"
        try:
            self.client = httpx.AsyncClient(
                http2=client_config.http2,
                trust_env=client_config.trust_env,
                timeout=httpx.Timeout(60.0, pool=None),
                headers=headers,
            )
        except ImportError as exc:
            if "SOCKS proxy" not in str(exc):
                raise
            self.client = httpx.AsyncClient(
                http2=client_config.http2,
                trust_env=False,
                timeout=httpx.Timeout(60.0, pool=None),
                headers=headers,
            )

    async def close(self) -> None:
        await self.client.aclose()

    async def info(self) -> Dict[str, Any]:
        return await self._get_json("")

    async def chain_id(self) -> int:
        if self._chain_id is None:
            self._chain_id = int((await self.info())["chain_id"])
        return self._chain_id

    async def current_timestamp(self) -> int:
        timestamp = int((await self.info())["ledger_timestamp"])
        if timestamp > 10**12:
            return timestamp // 1_000_000
        return timestamp

    async def account(
        self, account_address: AccountAddress, ledger_version: Optional[int] = None
    ) -> Dict[str, Any]:
        return await self._get_json(
            f"accounts/{account_address}",
            params={"ledger_version": ledger_version},
        )

    async def account_resource(
        self,
        account_address: AccountAddress,
        resource_type: str,
        ledger_version: Optional[int] = None,
    ) -> Dict[str, Any]:
        try:
            return await self._get_json(
                f"accounts/{account_address}/resource/{resource_type}",
                params={"ledger_version": ledger_version},
            )
        except ApiError as exc:
            if exc.status_code == 404:
                raise ResourceNotFound(resource_type, resource_type) from exc
            raise

    async def account_sequence_number(
        self, account_address: AccountAddress, ledger_version: Optional[int] = None
    ) -> int:
        try:
            return int((await self.account(account_address, ledger_version))["sequence_number"])
        except ApiError as exc:
            if exc.status_code == 404:
                return 0
            raise

    async def submit_bcs_transaction(self, signed_transaction: SignedTransaction) -> str:
        body = await self._post_bytes_json(
            "transactions",
            signed_transaction.bytes(),
            {"Content-Type": MIME_BCS_SIGNED_TRANSACTION},
        )
        return str(body["hash"])

    async def create_bcs_transaction(
        self,
        sender: Any,
        payload: Any,
        sequence_number: Optional[int] = None,
    ) -> RawTransaction:
        if sequence_number is None:
            sequence_number = await self.account_sequence_number(sender.address())
        tx_payload = (
            payload if isinstance(payload, TransactionPayload)
            else TransactionPayload(payload)
        )
        return RawTransaction(
            sender.address(),
            sequence_number,
            tx_payload,
            self.client_config.max_gas_amount,
            self.client_config.gas_unit_price,
            await self.current_timestamp() + self.client_config.expiration_ttl,
            await self.chain_id(),
        )

    async def create_bcs_signed_transaction(
        self,
        sender: Any,
        payload: Any,
        sequence_number: Optional[int] = None,
    ) -> SignedTransaction:
        raw_transaction = await self.create_bcs_transaction(
            sender, payload, sequence_number
        )
        return SignedTransaction(
            raw_transaction,
            sender.sign_transaction(raw_transaction),
        )

    async def submit_transaction(
        self,
        transaction: Any,
        sender_authenticator: Any,
        encoding: Optional[str] = None,
    ) -> str:
        """Submit a signed transaction, encoding it as JSON (default) or BCS.

        ``transaction`` may be a ``RawTransaction`` or ``SimpleTransaction``;
        ``encoding`` overrides ``ClientConfig.default_submission_encoding``.
        """
        content_type, body = build_submission_body(
            self.client_config, transaction, sender_authenticator, encoding
        )
        result = await self._post_bytes_json(
            "transactions", body, {"Content-Type": content_type}
        )
        return str(result["hash"])

    async def transaction_by_hash(self, txn_hash: str) -> Dict[str, Any]:
        return await self._get_json(f"transactions/by_hash/{txn_hash}")

    async def wait_for_transaction(self, txn_hash: str) -> None:
        deadline = time.monotonic() + self.client_config.transaction_wait_in_seconds
        while time.monotonic() < deadline:
            try:
                txn = await self.transaction_by_hash(txn_hash)
            except ApiError as exc:
                if exc.status_code != 404:
                    raise
                await asyncio.sleep(1)
                continue
            if txn.get("type") != "pending_transaction":
                if not txn.get("success", False):
                    raise ApiError(f"{txn.get('vm_status', txn)} - {txn_hash}", 400)
                return
            await asyncio.sleep(1)
        raise TimeoutError(f"transaction {txn_hash} timed out")

    async def submit_and_wait_for_bcs_transaction(
        self, signed_transaction: SignedTransaction
    ) -> Dict[str, Any]:
        txn_hash = await self.submit_bcs_transaction(signed_transaction)
        await self.wait_for_transaction(txn_hash)
        return await self.transaction_by_hash(txn_hash)

    async def view(
        self,
        function: str,
        type_arguments: list[str],
        arguments: list[Any],
        ledger_version: Optional[int] = None,
    ) -> bytes:
        response = await self._post_json(
            "view",
            {
                "function": function,
                "type_arguments": type_arguments,
                "arguments": arguments,
            },
            params={"ledger_version": ledger_version},
        )
        return response.content

    async def _get_json(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        response = await self.client.get(
            self._url(endpoint),
            params=self._clean_params(params),
            headers={"Accept": "application/json"},
        )
        return self._json_or_error(response)

    async def _post_json(
        self,
        endpoint: str,
        data: Dict[str, Any],
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        response = await self.client.post(
            self._url(endpoint),
            params=self._clean_params(params),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=data,
        )
        if response.status_code >= 400:
            raise ApiError(response.text, response.status_code)
        return response

    async def _post_bytes_json(
        self,
        endpoint: str,
        payload: bytes,
        headers: Dict[str, str],
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        response = await self.client.post(
            self._url(endpoint),
            params=self._clean_params(params),
            headers=headers,
            content=payload,
        )
        return self._json_or_error(response)

    def _url(self, endpoint: str) -> str:
        return self.base_url if not endpoint else f"{self.base_url}/{endpoint}"

    @staticmethod
    def _clean_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        return {k: v for k, v in (params or {}).items() if v is not None}

    @staticmethod
    def _json_or_error(response: httpx.Response) -> Any:
        if response.status_code >= 400:
            raise ApiError(response.text, response.status_code)
        return response.json()


class FaucetClient:
    def __init__(
        self, base_url: str, rest_client: RestClient, auth_token: Optional[str] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.rest_client = rest_client
        self.headers: Dict[str, str] = {}
        if auth_token:
            self.headers["Authorization"] = f"Bearer {auth_token}"

    async def fund_account(
        self, address: AccountAddress, amount: int, wait_for_transaction: bool = True
    ) -> str:
        response = await self.rest_client.client.post(
            f"{self.base_url}/mint",
            params={"amount": amount, "address": str(address)},
            headers=self.headers,
        )
        if response.status_code >= 400:
            raise ApiError(response.text, response.status_code)
        txn_hash = response.json()[0]
        if wait_for_transaction:
            await self.rest_client.wait_for_transaction(txn_hash)
        return txn_hash

    async def healthy(self) -> bool:
        response = await self.rest_client.client.get(self.base_url)
        return response.text == "tap:ok"


class ApiError(Exception):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


class AccountNotFound(Exception):
    def __init__(self, message: str, account: AccountAddress):
        super().__init__(message)
        self.account = account


class ResourceNotFound(Exception):
    def __init__(self, message: str, resource: str):
        super().__init__(message)
        self.resource = resource

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Read-only DEX account, order, and relayer open-order clients."""

from __future__ import annotations

import re
from dataclasses import dataclass, fields
from typing import Any, Dict, List, Mapping, Optional, Union
from urllib.parse import urlencode

import httpx

from ..core.account_address import AccountAddress

AddressInput = Union[str, AccountAddress]


@dataclass(frozen=True)
class DexSystemAccounts:
    """Current system identity: the Liquidation Vault also receives ADL remainders."""

    liquidation_takeover_address: str

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "DexSystemAccounts":
        liquidation = value.get("liquidationTakeoverAddress")
        if not isinstance(liquidation, str):
            raise ValueError("liquidationTakeoverAddress must be a string")
        return cls(liquidation_takeover_address=liquidation)


@dataclass(frozen=True)
class DexAuthority:
    """What controls one account, as ``GET /v1/dex/authority/{account}`` reports it.

    ``epoch`` is reported for both kinds and keeps counting across a ``Remove``: it
    is what the next proof has to name, and an account that has left a policy does
    not start again at one.

    Absence of a record is not represented here -- the read returns ``None`` for
    it, because "the key this address derives from controls the account" is a
    different answer from any record, and it is the answer for every account that
    has never run a multisig operation.
    """

    account: str
    version: int
    epoch: int
    updated_at_secs: int
    #: ``"key"`` for a single named control key, ``"policy"`` for a k-of-n set.
    kind: str
    #: Set when ``kind`` is ``"key"``.
    auth_key: Optional[str] = None
    #: Set when ``kind`` is ``"policy"``: how many distinct owners must approve.
    threshold: Optional[int] = None
    #: Set when ``kind`` is ``"policy"``: the owners, lowercase 20-byte hex.
    owners: Optional[List[str]] = None
    #: Set when ``kind`` is ``"policy"``: the commitment the audit event carries,
    #: which ``multisig_owners_digest`` recomputes from a list of owners.
    owners_digest: Optional[str] = None
    created_at_secs: Optional[int] = None

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "DexAuthority":
        kind = value.get("kind")
        if kind not in ("key", "policy"):
            raise ValueError("authority kind must be 'key' or 'policy'")
        return cls(
            account=str(value["account"]),
            version=int(value["version"]),
            epoch=int(value["epoch"]),
            updated_at_secs=int(value["updated_at_secs"]),
            kind=kind,
            auth_key=value.get("auth_key"),
            threshold=value.get("threshold"),
            owners=list(value["owners"]) if "owners" in value else None,
            owners_digest=value.get("owners_digest"),
            created_at_secs=(
                int(value["created_at_secs"]) if "created_at_secs" in value else None
            ),
        )


def _json_integer(value: Any, name: str) -> int:
    """An integer sent as a JSON number or, past 64 bits, a decimal string."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    raise ValueError(f"{name} must be an integer, got {value!r}")


def _json_optional_integer(value: Any, name: str) -> Optional[int]:
    return None if value is None else _json_integer(value, name)


def _json_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


@dataclass(frozen=True)
class DexDelistingPlanView:
    """A market's delisting plan: the fields of the chain's plan key.

    ``t0_secs`` is the end of trading in Unix seconds, ``reduce_only_at_secs``
    is ``t0_secs - reduce_only_lead_secs`` and ``window_start_secs``, when the
    price window opens, ``t0_secs - twap_window_secs``; all three are 0 once
    the plan is cancelled.
    """

    plan_version: int
    t0_secs: int
    reduce_only_lead_secs: int
    twap_window_secs: int
    max_cancel_per_block: int
    max_settle_per_block: int
    reduce_only_at_secs: int
    window_start_secs: int

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "DexDelistingPlanView":
        return cls(
            **{
                field.name: _json_integer(value.get(field.name), f"plan.{field.name}")
                for field in fields(cls)
            }
        )


@dataclass(frozen=True)
class DexDelistingRuntimeView:
    """A delisting's progress, kept on chain from the price window on.

    ``sample_weight_us`` is the microseconds of samples behind the TWAP.
    ``expected_total_pnl``, every position's PnL at the final price, and
    ``realized_pnl_sum``, the settlement PnL of the accounts settled so far,
    are signed. ``shortfall_quote`` is what the liquidation takeover account
    made good.
    """

    plan_version: int
    sample_weight_us: int
    canceled_orders: int
    settled_accounts: int
    settled_quantums: int
    settled_quote_quantums: int
    expected_total_pnl: int
    realized_pnl_sum: int
    shortfall_quote: int

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "DexDelistingRuntimeView":
        return cls(
            **{
                field.name: _json_integer(
                    value.get(field.name), f"runtime.{field.name}"
                )
                for field in fields(cls)
            }
        )


@dataclass(frozen=True)
class DexDelistingView:
    """One market's delisting, as /dex/delistings returns it.

    ``ticker`` is ``BASE-QUOTE`` from the market's display info, empty when it
    has none, and ``symbol_status`` a ``SymbolStatus`` value, kept as read.
    ``phase`` is ``SCHEDULED``, ``REDUCE_ONLY``, ``SETTLING``, ``CLOSED`` or
    ``CANCELLED``; ``prd_state`` is ``TRADING``, ``PRE_SETTLEMENT``,
    ``SETTLING`` or ``CLOSED``. ``indicative_price_subticks`` is the TWAP so
    far inside the price window and the final price from T0 on, None before;
    ``final_price_subticks`` is None before T0 and ``runtime`` None before the
    price window opens.
    """

    perpetual_id: int
    symbol_id: int
    ticker: str
    symbol_status: int
    phase: str
    prd_state: str
    plan: DexDelistingPlanView
    indicative_price_subticks: Optional[int]
    final_price_subticks: Optional[int]
    runtime: Optional[DexDelistingRuntimeView]

    @classmethod
    def from_json(cls, value: Mapping[str, Any]) -> "DexDelistingView":
        plan = value.get("plan")
        runtime = value.get("runtime")
        if not isinstance(plan, Mapping):
            raise ValueError("plan must be an object")
        if runtime is not None and not isinstance(runtime, Mapping):
            raise ValueError("runtime must be an object or null")
        return cls(
            perpetual_id=_json_integer(value.get("perpetual_id"), "perpetual_id"),
            symbol_id=_json_integer(value.get("symbol_id"), "symbol_id"),
            ticker=_json_string(value.get("ticker"), "ticker"),
            symbol_status=_json_integer(value.get("symbol_status"), "symbol_status"),
            phase=_json_string(value.get("phase"), "phase"),
            prd_state=_json_string(value.get("prd_state"), "prd_state"),
            plan=DexDelistingPlanView.from_json(plan),
            indicative_price_subticks=_json_optional_integer(
                value.get("indicative_price_subticks"), "indicative_price_subticks"
            ),
            final_price_subticks=_json_optional_integer(
                value.get("final_price_subticks"), "final_price_subticks"
            ),
            runtime=(
                None if runtime is None else DexDelistingRuntimeView.from_json(runtime)
            ),
        )


def _address(value: AddressInput) -> str:
    return str(value)


def _same_address(left: str, right: AddressInput) -> bool:
    def canonical(value: str) -> str:
        text = value.lower()
        if text.startswith("0x"):
            text = text[2:]
        return text.lstrip("0") or "0"

    return canonical(left) == canonical(_address(right))


def _parse_integer_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [_parse_integer_fields(item) for item in value]
    if not isinstance(value, dict):
        return value
    integer_names = {
        "available_margin",
        "quantums",
        "short_quantums",
        "long_quantums",
        "funding_index",
        "long_position_value",
        "short_position_value",
        "short_imr_quota",
        "long_imr_quota",
        "short_mmr_quota",
        "long_mmr_quota",
        "short_imr_close_fee",
        "long_imr_close_fee",
        "volume_usd",
        "maker_volume_usd",
        "utc_day_start",
        "fee_inflow",
        "last_trade_timestamp_sec",
        "cumulative_volume_usd",
        "timestamp",
        "target_order_id",
        "order_id",
        "remaining_quantums",
        "filled_quantums",
        "opening_fee",
        "closing_fee",
    }
    result = {}
    for key, item in value.items():
        if key in integer_names and not isinstance(item, (dict, list)):
            result[key] = int(item)
        else:
            result[key] = _parse_integer_fields(item)
    return result


class DexAccountClient:
    def __init__(
        self,
        node_url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        trust_env: bool = True,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.node_url = node_url.rstrip("/")
        self.headers = dict(headers or {})
        self.trust_env = trust_env
        # Normally None, which lets httpx open real connections. A caller passes
        # one to exercise these reads without a node -- including the 404 the
        # authority read has to treat as an answer, which is the case most likely
        # to be got wrong and the hardest to reach against a live chain.
        self.transport = transport

    async def _fetch(self, path: str) -> httpx.Response:
        if not self.node_url:
            raise ValueError("node_url is required for DEX account queries")
        async with httpx.AsyncClient(
            trust_env=self.trust_env, transport=self.transport
        ) as client:
            return await client.get(
                f"{self.node_url}/{path.lstrip('/')}",
                headers={"Accept": "application/json", **self.headers},
            )

    async def _get(self, path: str) -> Any:
        response = await self._fetch(path)
        response.raise_for_status()
        return response.json()

    async def _get_optional(self, path: str) -> Optional[Any]:
        """Like :meth:`_get`, but a 404 is an answer rather than a failure.

        Only for reads where absence means something: the authority record below is
        absent for every account that has never run a multisig operation, and
        raising there would make an ordinary account look like a broken node.
        """
        if not self.node_url:
            raise ValueError("node_url is required for DEX account queries")
        async with httpx.AsyncClient(
            trust_env=self.trust_env, transport=self.transport
        ) as client:
            response = await client.get(
                f"{self.node_url}/{path.lstrip('/')}",
                headers={"Accept": "application/json", **self.headers},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def get_authority(self, address: AddressInput) -> Optional[DexAuthority]:
        """What controls an account, or ``None`` when it has no authority record.

        ``None`` is the default and not an error: the account is controlled by the
        key its address derives from, which is every account that has never run a
        multisig operation.
        """
        body = await self._get_optional(f"dex/authority/{_address(address)}")
        if body is None:
            return None
        if not isinstance(body, Mapping):
            raise ValueError("authority response must be an object")
        return DexAuthority.from_json(body)

    async def is_multisig_operation_used(self, op_id: Union[str, bytes]) -> bool:
        """Whether one multisig operation id has already been executed.

        Approvals are collected off chain and any owner may submit them, so the
        same signed operation can be handed in twice. The chain accepts it once and
        records the id; this is how a caller tells "my withdrawal already went
        through" from "my submission was lost".
        """
        if isinstance(op_id, (bytes, bytearray)):
            op_id = "0x" + bytes(op_id).hex()
        body = await self._get(f"dex/multisig/op/{op_id}")
        if not isinstance(body, Mapping) or not isinstance(body.get("used"), bool):
            raise ValueError("multisig operation response carried no `used` flag")
        return bool(body["used"])

    async def get_accounts(self, address: AddressInput) -> List[Dict[str, Any]]:
        body = await self._get(f"dex/accounts/{_address(address)}")
        accounts = body.get("accounts", []) if isinstance(body, dict) else []
        return [
            _parse_integer_fields(account)
            for account in accounts
            if isinstance(account, dict)
        ]

    async def get_system_accounts(self) -> DexSystemAccounts:
        body = await self._get("dex/system_accounts")
        if not isinstance(body, Mapping):
            raise ValueError("system_accounts response must be an object")
        return DexSystemAccounts.from_json(body)

    async def get_account(
        self, address: AddressInput, sub_address: AddressInput
    ) -> Optional[Dict[str, Any]]:
        accounts = await self.get_accounts(address)
        return next(
            (
                account
                for account in accounts
                if _same_address(str(account.get("sub_address", "")), sub_address)
            ),
            None,
        )

    async def get_positions(
        self, address: AddressInput, sub_address: AddressInput
    ) -> List[Dict[str, Any]]:
        account = await self.get_account(address, sub_address)
        return list(account.get("perps", [])) if account else []

    async def get_balances(
        self, address: AddressInput, sub_address: AddressInput
    ) -> List[Dict[str, Any]]:
        account = await self.get_account(address, sub_address)
        return list(account.get("assets", [])) if account else []

    async def get_order(self, order_id: int) -> Dict[str, Any]:
        body = await self._get(f"dex/orders/{order_id}")
        if not isinstance(body, dict):
            raise ValueError("order response must be an object")
        return _parse_integer_fields(body)

    async def get_delistings(self) -> List[DexDelistingView]:
        """Every market with a delisting plan, by perpetual_id, cancelled and
        closed ones included. A node that predates
        delisting has no such route, and its 404 reads as no plans.
        """
        response = await self._fetch("dex/delistings")
        if response.status_code == 404:
            return []
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, Mapping):
            raise ValueError("delistings response must be an object")
        delistings = body.get("delistings", [])
        if not isinstance(delistings, list) or not all(
            isinstance(item, Mapping) for item in delistings
        ):
            raise ValueError("delistings must be a list of objects")
        return [DexDelistingView.from_json(item) for item in delistings]

    async def get_delisting(self, perpetual_id: int) -> Optional[DexDelistingView]:
        """One market's delisting, or None when it has no plan (a 404)."""
        if (
            isinstance(perpetual_id, bool)
            or not isinstance(perpetual_id, int)
            or not 0 <= perpetual_id <= 0xFFFFFFFF
        ):
            raise ValueError(f"perpetual_id must be a u32, got {perpetual_id!r}")
        response = await self._fetch(f"dex/delistings/{perpetual_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, Mapping):
            raise ValueError("delisting response must be an object")
        return DexDelistingView.from_json(body)


class RelayerOpenOrdersProvider:
    def __init__(
        self,
        relayer_url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        trust_env: bool = True,
    ):
        self.relayer_url = relayer_url.rstrip("/")
        self.headers = dict(headers or {})
        self.trust_env = trust_env

    async def get_open_orders(
        self,
        *,
        address: AddressInput,
        sub_address: AddressInput,
        symbol_id: Optional[int] = None,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if not self.relayer_url:
            raise ValueError("relayer_url is required for cancel_all")
        query = urlencode(
            {
                "address": _address(address),
                "status": "OPEN,PARTIALLY_FILLED",
                "subAddress": _address(sub_address),
            }
        )
        async with httpx.AsyncClient(trust_env=self.trust_env) as client:
            response = await client.get(
                f"{self.relayer_url}/v1/orders?{query}",
                headers={"Accept": "application/json", **self.headers},
            )
            response.raise_for_status()
            body = response.json()
        if isinstance(body, Mapping) and body.get("code") not in (None, 0):
            raise RuntimeError(
                f"get_open_orders API error: {body.get('message', body.get('code'))}"
            )
        data = body.get("data", body) if isinstance(body, Mapping) else {}
        raw_orders = data.get("orders", []) if isinstance(data, Mapping) else []
        orders = []
        for raw in raw_orders:
            if not isinstance(raw, Mapping):
                continue
            raw_symbol_id = raw.get("clobPairId")
            record = {
                "order_id": int(raw["id"]),
                "client_order_id": raw.get("clientId"),
                "symbol_id": (
                    int(raw_symbol_id) if raw_symbol_id is not None else None
                ),
                "symbol": raw.get("ticker"),
                "sub_address": str(raw.get("subAddress", "")),
            }
            if not _same_address(record["sub_address"], sub_address):
                continue
            if symbol_id is not None and record["symbol_id"] not in (
                None,
                symbol_id,
            ):
                continue
            if (
                symbol_id is not None
                and record["symbol_id"] is None
                and symbol is not None
                and record["symbol"] != symbol
            ):
                continue
            orders.append(record)
        return orders

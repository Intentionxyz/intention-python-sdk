# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Vault REST API client for querying vault state from the chain's REST API.

Wraps the vault-specific REST endpoints:
- GET /v1/vaults
- GET /v1/vaults/:vault_id
- GET /v1/vaults/:vault_id/depositors
- GET /v1/vaults/:vault_id/positions
- GET /v1/vaults/:vault_id/orders
- GET /v1/vaults/clp/allowlist
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import httpx

# =============================================================================
# Response Types
# =============================================================================


@dataclass
class SubaccountIdResponse:
    """Subaccount ID in API responses."""

    address: str
    number: int
    sub_address: str
    user_name: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> SubaccountIdResponse:
        return SubaccountIdResponse(
            address=d.get("address", ""),
            number=int(d.get("number", 0)),
            sub_address=d.get("sub_address", ""),
            user_name=d.get("user_name", ""),
        )


@dataclass
class VaultState:
    """Vault state from the chain."""

    vault_id: int
    vault_type: int  # 0 = CLP, 1 = UserVault
    status: int  # 0 = Active, 1 = Paused, 2 = Closed
    nav_e6: str  # i128 as string
    tvl_usdc: str  # i128 as string
    total_shares: str  # i128 as string
    lockup_seconds: int
    always_proportional_close: bool
    vault_name: str
    strategy_description: str
    created_ts_us: str
    updated_ts_us: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> VaultState:
        return VaultState(
            vault_id=_coerce_int(d.get("vault_id", 0)),
            vault_type=_coerce_vault_type(d.get("vault_type", 0)),
            status=_coerce_vault_status(d.get("status", 0)),
            nav_e6=str(d.get("nav_e6", "0")),
            tvl_usdc=str(d.get("tvl_usdc", "0")),
            total_shares=str(d.get("total_shares", "0")),
            lockup_seconds=_coerce_int(d.get("lockup_seconds", 0)),
            always_proportional_close=_coerce_bool(
                d.get("always_proportional_close", False)
            ),
            vault_name=str(d.get("vault_name", "")),
            strategy_description=str(d.get("strategy_description", "")),
            created_ts_us=str(d.get("created_ts_us", "")),
            updated_ts_us=str(d.get("updated_ts_us", "")),
        )


@dataclass
class DepositorPosition:
    """Depositor position in a vault."""

    vault_id: int
    depositor: SubaccountIdResponse
    shares: str  # i128 as string
    avg_cost_nav_e6: str
    last_deposit_ts_us: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> DepositorPosition:
        depositor_data = d.get("depositor", {})
        return DepositorPosition(
            vault_id=_coerce_int(d.get("vault_id", 0)),
            depositor=SubaccountIdResponse.from_dict(depositor_data),
            shares=str(d.get("shares", "0")),
            avg_cost_nav_e6=str(d.get("avg_cost_nav_e6", "0")),
            last_deposit_ts_us=str(d.get("last_deposit_ts_us", "")),
        )


@dataclass
class VaultPosition:
    """Vault perpetual position."""

    symbol_id: int
    long_quantums: str
    short_quantums: str
    long_position_value: str
    short_position_value: str

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> VaultPosition:
        return VaultPosition(
            symbol_id=_coerce_int(d.get("symbol_id", 0)),
            long_quantums=str(d.get("long_quantums", "0")),
            short_quantums=str(d.get("short_quantums", "0")),
            long_position_value=str(d.get("long_position_value", "0")),
            short_position_value=str(d.get("short_position_value", "0")),
        )


@dataclass
class VaultOrder:
    """Vault active order."""

    order_id: str
    symbol_id: int
    side: int
    quantums: str
    subticks: str
    order_type: int

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> VaultOrder:
        return VaultOrder(
            order_id=str(d.get("order_id", "")),
            symbol_id=_coerce_int(d.get("symbol_id", 0)),
            side=_coerce_int(d.get("side", 0)),
            quantums=str(d.get("quantums", "0")),
            subticks=str(d.get("subticks", "0")),
            order_type=_coerce_int(d.get("order_type", 0)),
        )


@dataclass
class ClpAllowlistEntry:
    """CLP trader allowlist entry."""

    clp_account: SubaccountIdResponse
    traders: List[str]  # hex addresses

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ClpAllowlistEntry:
        return ClpAllowlistEntry(
            clp_account=SubaccountIdResponse.from_dict(d.get("clp_account", {})),
            traders=d.get("traders", []),
        )


# =============================================================================
# Vault API Client
# =============================================================================


class VaultClient:
    """
    Client for querying vault-related data from the chain's REST API.

    Example::

        client = VaultClient("https://api.example.com")
        vaults = await client.get_vaults()
        vault = await client.get_vault(1)
        depositors = await client.get_depositors(1)
    """

    def __init__(self, base_url: str, trust_env: bool = True):
        self.base_url = base_url.rstrip("/")
        self.trust_env = trust_env

    async def _fetch_json(self, path: str) -> Any:
        async with httpx.AsyncClient(trust_env=self.trust_env) as client:
            response = await client.get(f"{self.base_url}{path}")
            if not response.is_success:
                raise Exception(
                    f"Vault API request failed: {response.status_code} "
                    f"{response.reason_phrase} ({path})"
                )
            return response.json()

    async def get_vaults(self) -> List[VaultState]:
        """List all vaults."""
        data = await self._fetch_json("/v1/vaults")
        return [VaultState.from_dict(v) for v in _unwrap_list(data, "vaults")]

    async def get_vault(self, vault_id: int) -> VaultState:
        """Get a specific vault by ID."""
        data = await self._fetch_json(f"/v1/vaults/{vault_id}")
        return VaultState.from_dict(data)

    async def get_depositors(self, vault_id: int) -> List[DepositorPosition]:
        """Get depositor positions for a vault."""
        data = await self._fetch_json(f"/v1/vaults/{vault_id}/depositors")
        return [DepositorPosition.from_dict(d) for d in _unwrap_list(data, "depositors")]

    async def get_positions(self, vault_id: int) -> List[VaultPosition]:
        """Get perpetual positions held by a vault."""
        data = await self._fetch_json(f"/v1/vaults/{vault_id}/positions")
        return [VaultPosition.from_dict(p) for p in _unwrap_list(data, "accounts", "positions")]

    async def get_orders(self, vault_id: int) -> List[VaultOrder]:
        """Get active orders for a vault."""
        data = await self._fetch_json(f"/v1/vaults/{vault_id}/orders")
        return [VaultOrder.from_dict(o) for o in _unwrap_list(data, "accounts", "orders")]

    async def get_clp_allowlist(self) -> List[ClpAllowlistEntry]:
        """Get CLP trader allowlist."""
        data = await self._fetch_json("/v1/vaults/clp/allowlist")
        return [ClpAllowlistEntry.from_dict(e) for e in _unwrap_list(data, "allowlist", "entries")]


def _coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "active"}
    return bool(value)


def _coerce_vault_type(value: Any) -> int:
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapping = {
            "clp": 0,
            "uservault": 1,
            "user_vault": 1,
            "user vault": 1,
        }
        if normalized in mapping:
            return mapping[normalized]
    return _coerce_int(value, 0)


def _coerce_vault_status(value: Any) -> int:
    if isinstance(value, str):
        normalized = value.strip().lower()
        mapping = {"active": 0, "paused": 1, "closed": 2}
        if normalized in mapping:
            return mapping[normalized]
    return _coerce_int(value, 0)


def _unwrap_list(data: Any, *keys: str) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []

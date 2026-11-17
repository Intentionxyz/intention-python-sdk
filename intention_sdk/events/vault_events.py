# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0
"""Vault schema v1: exact BCS/JSON decoding, preserving signed bit fields."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from ..core.account_address import AccountAddress
from ..bcs import Deserializer


@dataclass(frozen=True)
class DexVaultInternalOffsetEvent:
    schema_version: int
    vault_account: str
    sub_address: str
    subaccount_number: int
    symbol_id: int
    status: int
    quantums: int
    before_long_quantums: int
    before_short_quantums: int
    after_long_quantums: int
    after_short_quantums: int
    price: int
    offset_quote: int
    long_released_cost: int
    short_released_cost: int
    long_realized_pnl_bits: int
    short_realized_pnl_bits: int
    total_realized_pnl_bits: int
    total_fee: int
    block_height: int
    timestamp_us: int
    action_seq: int


VAULT_EVENT_NAMES = (
    "VaultInternalOffsetEvent",
)


def _uint(value: Any, bits: int) -> int:
    if isinstance(value, str):
        if (
            len(value) > len(str((1 << bits) - 1))
            or re.fullmatch(r"[0-9]+", value) is None
        ):
            raise ValueError("invalid unsigned decimal")
        value = int(value)
    if type(value) is not int or not 0 <= value < (1 << bits):
        raise ValueError("unsigned integer outside ABI range")
    return value


def _address(value: Any) -> str:
    if isinstance(value, str):
        raw = value[2:] if value.startswith("0x") else value
        if re.fullmatch(r"[0-9a-fA-F]{1,64}", raw) is None:
            raise ValueError("invalid address")
        return str(AccountAddress(bytes.fromhex(raw.zfill(64))))
    if isinstance(value, list) and len(value) == 32:
        return str(AccountAddress(bytes(_uint(v, 8) for v in value)))
    raise ValueError("invalid address")


def _record(value: Any, keys: Tuple[str, ...]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ValueError("Vault event fields do not match schema v1")
    return value


def _read_vault_internal_offset_event(d: Deserializer) -> DexVaultInternalOffsetEvent:
    return DexVaultInternalOffsetEvent(
        schema_version=d.deserialize_u64(),
        vault_account=str(AccountAddress(d.deserialize_fixed_bytes(32))),
        sub_address=str(AccountAddress(d.deserialize_fixed_bytes(32))),
        subaccount_number=d.deserialize_u32(),
        symbol_id=d.deserialize_u32(),
        status=d.deserialize_u8(),
        quantums=d.deserialize_u64(),
        before_long_quantums=d.deserialize_u64(),
        before_short_quantums=d.deserialize_u64(),
        after_long_quantums=d.deserialize_u64(),
        after_short_quantums=d.deserialize_u64(),
        price=d.deserialize_u64(),
        offset_quote=d.deserialize_u128(),
        long_released_cost=d.deserialize_u128(),
        short_released_cost=d.deserialize_u128(),
        long_realized_pnl_bits=d.deserialize_u128(),
        short_realized_pnl_bits=d.deserialize_u128(),
        total_realized_pnl_bits=d.deserialize_u128(),
        total_fee=d.deserialize_u128(),
        block_height=d.deserialize_u64(),
        timestamp_us=d.deserialize_u64(),
        action_seq=d.deserialize_u32(),
    )


def _json_vault_internal_offset_event(data: Any) -> DexVaultInternalOffsetEvent:
    data = _record(
        data,
        (
            "schema_version",
            "vault_account",
            "sub_address",
            "subaccount_number",
            "symbol_id",
            "status",
            "quantums",
            "before_long_quantums",
            "before_short_quantums",
            "after_long_quantums",
            "after_short_quantums",
            "price",
            "offset_quote",
            "long_released_cost",
            "short_released_cost",
            "long_realized_pnl_bits",
            "short_realized_pnl_bits",
            "total_realized_pnl_bits",
            "total_fee",
            "block_height",
            "timestamp_us",
            "action_seq",
        ),
    )
    return DexVaultInternalOffsetEvent(
        schema_version=_uint(data["schema_version"], 64),
        vault_account=_address(data["vault_account"]),
        sub_address=_address(data["sub_address"]),
        subaccount_number=_uint(data["subaccount_number"], 32),
        symbol_id=_uint(data["symbol_id"], 32),
        status=_uint(data["status"], 8),
        quantums=_uint(data["quantums"], 64),
        before_long_quantums=_uint(data["before_long_quantums"], 64),
        before_short_quantums=_uint(data["before_short_quantums"], 64),
        after_long_quantums=_uint(data["after_long_quantums"], 64),
        after_short_quantums=_uint(data["after_short_quantums"], 64),
        price=_uint(data["price"], 64),
        offset_quote=_uint(data["offset_quote"], 128),
        long_released_cost=_uint(data["long_released_cost"], 128),
        short_released_cost=_uint(data["short_released_cost"], 128),
        long_realized_pnl_bits=_uint(data["long_realized_pnl_bits"], 128),
        short_realized_pnl_bits=_uint(data["short_realized_pnl_bits"], 128),
        total_realized_pnl_bits=_uint(data["total_realized_pnl_bits"], 128),
        total_fee=_uint(data["total_fee"], 128),
        block_height=_uint(data["block_height"], 64),
        timestamp_us=_uint(data["timestamp_us"], 64),
        action_seq=_uint(data["action_seq"], 32),
    )


def decode_vault_event(name: str, data: Any):
    if isinstance(data, str) and data.lstrip().startswith(('"', "{")):
        data = json.loads(data)
    if isinstance(data, Mapping):
        event = _JSON[name](data)
    elif isinstance(data, str):
        raw = data[2:] if data.startswith("0x") else data
        if re.fullmatch(r"(?:[0-9a-fA-F]{2})+", raw) is None:
            raise ValueError("invalid BCS hex")
        d = Deserializer(bytes.fromhex(raw))
        event = _BCS[name](d)
        if d.remaining() != 0:
            raise ValueError("trailing Vault event bytes")
    else:
        raise ValueError("unsupported event transport")
    if event.schema_version != 1 or event.status > 3:
        raise ValueError("unsupported Vault schema/status")
    return event


_BCS = {
    "VaultInternalOffsetEvent": _read_vault_internal_offset_event,
}
_JSON = {
    "VaultInternalOffsetEvent": _json_vault_internal_offset_event,
}

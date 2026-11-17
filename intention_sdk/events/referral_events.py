# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0
"""Strict BCS decoding for referral events."""
from __future__ import annotations

from typing import Any, Dict
import re
from ..core.account_address import AccountAddress
from ..bcs import Deserializer, Serializer

REFERRAL_EVENT_NAMES = {
    "ReferralCodeRegisteredEvent", "ReferralBoundEvent", "ReferralConfigUpdatedEvent",
    "ReferralRewardsClaimedEvent", "DexReferralFeeEvent",
    "ReferralReservedCodesUpdatedEvent",
}


def _address(d: Deserializer) -> str:
    return str(AccountAddress(d.deserialize_fixed_bytes(32))).lower()


def _reserved_codes(codes):
    if not isinstance(codes, list) or len(codes) > 256 or any(
        not isinstance(code, str) or not re.fullmatch(r"[A-Z0-9]{6,20}", code)
        or (i > 0 and codes[i - 1] >= code) for i, code in enumerate(codes)
    ):
        raise ValueError("Invalid canonical reserved code list")
    return codes


def _parameters(d: Deserializer) -> Dict[str, Any]:
    return dict(invitee_fee_discount_ppm=d.deserialize_u32(), commission_rate_ppm=d.deserialize_u32(),
                referral_threshold_volume=d.deserialize_u64(), discount_volume_cap=d.deserialize_u64(),
                commission_volume_cap=d.deserialize_u64(), min_claim_amount=d.deserialize_u64())


def _count(d: Deserializer, maximum: int) -> int:
    value = d.deserialize_u32_from_uleb128()
    if value > maximum:
        raise ValueError("Referral event vector is too large")
    return value


def decode_referral_event_bytes(name: str, data: bytes) -> Dict[str, Any]:
    d = Deserializer(data)
    if name == "ReferralReservedCodesUpdatedEvent":
        value = dict(revision=d.deserialize_u64(), effective_block_height=d.deserialize_u64(),
                     codes=_reserved_codes([d.deserialize_str() for _ in range(_count(d, 256))]))
    elif name == "ReferralCodeRegisteredEvent":
        value = dict(master=_address(d), code=d.deserialize_str())
    elif name == "ReferralBoundEvent":
        value = dict(referee_master=_address(d), referrer_master=_address(d),
                     code=d.deserialize_str(), volume_at_bind_usd=d.deserialize_u64())
    elif name == "ReferralConfigUpdatedEvent":
        config = dict(version=d.deserialize_u8(), revision=d.deserialize_u64(), effective_block_height=d.deserialize_u64(),
                      parameters=_parameters(d), previous_parameters=None)
        if _count(d, 1):
            config["previous_parameters"] = _parameters(d)
        if config["version"] != 1:
            raise ValueError("Unsupported referral config version")
        value = dict(config=config)
    elif name == "ReferralRewardsClaimedEvent":
        value = dict(master=_address(d), amount=d.deserialize_u64(), total_claimed=d.deserialize_u64())
    elif name == "DexReferralFeeEvent":
        value = dict(block_height=d.deserialize_u64(), symbol_id=d.deserialize_u32(), fill_order_id=d.deserialize_u64(),
                     master=_address(d), sub_address=_address(d), discount=d.deserialize_u64(), commission=d.deserialize_u64())
    else:
        raise ValueError("Unknown referral event")
    if d.remaining():
        raise ValueError("Trailing referral event bytes")
    return value


decodeReferralEventBytes = decode_referral_event_bytes


def decode_referral_event_json(name: str, value: Dict[str, Any]) -> Dict[str, Any]:
    """Re-encode source JSON into the same strict BCS validation path."""
    s = Serializer()

    def number(obj: Dict[str, Any], key: str, bits: int = 64) -> None:
        raw = obj[key]
        if isinstance(raw, bool) or not isinstance(raw, (str, int)):
            raise ValueError("Invalid referral JSON integer")
        if not str(raw).isdigit():
            raise ValueError("Invalid referral JSON integer")
        n = int(raw)
        if not 0 <= n < (1 << bits):
            raise ValueError("Referral JSON integer overflow")
        getattr(s, f"serialize_u{bits}")(n)

    def address(obj: Dict[str, Any], key: str) -> None:
        AccountAddress.from_str_relaxed(obj[key]).serialize(s)

    def parameters(p: Dict[str, Any]) -> None:
        for key in ("invitee_fee_discount_ppm", "commission_rate_ppm"):
            number(p, key, 32)
        for key in ("referral_threshold_volume", "discount_volume_cap", "commission_volume_cap", "min_claim_amount"):
            number(p, key)

    if name == "ReferralReservedCodesUpdatedEvent":
        number(value, "revision")
        number(value, "effective_block_height")
        codes = _reserved_codes(value["codes"])
        s.serialize_u32_as_uleb128(len(codes))
        for code in codes:
            s.serialize_str(code)
    elif name == "ReferralCodeRegisteredEvent":
        address(value, "master")
        s.serialize_str(value["code"])
    elif name == "ReferralBoundEvent":
        address(value, "referee_master")
        address(value, "referrer_master")
        s.serialize_str(value["code"])
        number(value, "volume_at_bind_usd")
    elif name == "ReferralConfigUpdatedEvent":
        c = value["config"]
        number(c, "version", 8)
        number(c, "revision")
        number(c, "effective_block_height")
        parameters(c["parameters"])
        previous = c["previous_parameters"]
        s.serialize_u32_as_uleb128(0 if previous is None else 1)
        if previous is not None:
            parameters(previous)
    elif name == "ReferralRewardsClaimedEvent":
        address(value, "master")
        number(value, "amount")
        number(value, "total_claimed")
    elif name == "DexReferralFeeEvent":
        number(value, "block_height")
        number(value, "symbol_id", 32)
        number(value, "fill_order_id")
        address(value, "master")
        address(value, "sub_address")
        fields = ("discount", "commission")
        for key in fields:
            number(value, key)
    else:
        raise ValueError("Unknown referral event")
    return decode_referral_event_bytes(name, s.to_bytes())

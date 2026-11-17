# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0
"""Committed Referral queries and user actions. Monetary strings never use floats."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Dict, List, Literal, Optional, TypedDict

import httpx

from ..core.account import Account
from ..core.account_address import AccountAddress
from .dex_executor import DexTransactionExecutor, SubmitOptions
from ..transactions.dex_payloads import (
    BindReferrer, ClaimReferralRewards, DexOrderlessTx, DexUserConfigTx,
    ReferralParameters, RegisterReferralCode, SetReferralConfig,
    MultiSigProof,
)
from ..types.enums import DexOrderlessTxVariant, DexUserConfigTxVariant


class ReferralPublicParameters(TypedDict):
    inviteeFeeDiscountPpm: int
    commissionRatePpm: int
    referralThresholdVolume: str
    discountVolumeCap: str
    commissionVolumeCap: str
    minClaimAmount: str
    referralThresholdVolumeQuantums: str
    discountVolumeCapQuantums: str
    commissionVolumeCapQuantums: str
    minClaimAmountQuantums: str


class ReferralConfig(TypedDict):
    revision: str
    effectiveBlockHeight: str
    active: Optional[ReferralPublicParameters]
    pending: Optional[ReferralPublicParameters]
    gateActive: bool
    asOfBlockHeight: str
    sourceSeqId: str


class ReferralOverview(TypedDict):
    master: str
    tradersReferred: int
    code: Optional[str]
    referredBy: Optional[Dict[str, str]]
    commissionAccrued: str
    claimed: str
    claimable: str
    claimableQuantums: str
    totalReferralDiscount: str
    lifetimeVolume: str
    volumeSinceBound: Optional[str]
    canRegisterCode: bool
    canBind: bool
    config: ReferralConfig


class ReferralCodeResolution(TypedDict):
    code: str
    referrer: str
    asOfBlockHeight: str
    sourceSeqId: str


class ReferralSource(TypedDict):
    refereeMaster: str
    refereeSub: str
    commissionAccrued: str


class ReferralInvitee(TypedDict):
    master: str
    timeJoined: Optional[int]
    volumeSinceBound: str
    feePaid: str
    commissionAccrued: str


class ReferralClaim(TypedDict):
    id: str
    amount: str
    amountQuantums: str
    transactionHash: Optional[str]
    totalClaimed: str
    blockHeight: str
    timestamp: Optional[int]


class ReferralFill(TypedDict):
    fillId: str
    symbolId: int
    role: str
    master: str
    subAddress: str
    orderId: str
    fee: str
    referralDiscount: str
    referralCommission: str
    blockHeight: str
    timestamp: Optional[int]


class ReferralPage(TypedDict):
    items: List[Any]
    nextCursor: str
    asOfBlockHeight: str
    sourceSeqId: str


class ReferralInviteesPage(ReferralPage):
    totalCount: int


class ReferralClaimsPage(ReferralPage):
    totalCount: int


ReferralInviteeSortBy = Literal["timeJoined", "volumeSinceBound", "feePaid", "commissionAccrued"]
ReferralSortOrder = Literal["asc", "desc"]


def _validate_numbered_page(page: Optional[int], cursor: str) -> None:
    if page is not None and (
        isinstance(page, bool) or not isinstance(page, int) or page < 1 or cursor
    ):
        raise ValueError("Referral page must be a positive integer without cursor")


def _address(value: Any) -> AccountAddress:
    if isinstance(value, AccountAddress):
        return value
    return AccountAddress.from_str_relaxed(str(value))


class ReferralClient:
    def __init__(
        self, relayer_url: str, *, executor: Optional[DexTransactionExecutor] = None,
        signer: Optional[Account] = None, headers: Optional[Dict[str, str]] = None,
        trust_env: bool = False, transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.base_url = re.sub(r"/v1$", "", relayer_url.rstrip("/"))
        self.executor, self.signer = executor, signer
        self.client = httpx.AsyncClient(
            headers=headers, trust_env=trust_env, transport=transport, timeout=15.0
        )

    async def close(self):
        await self.client.aclose()

    async def _get(self, path: str, **query):
        if not self.base_url:
            raise ValueError("Referral queries require relayer_url")
        response = await self.client.get(
            f"{self.base_url}/v1/dex/referral/{path}",
            params={k: v for k, v in query.items() if v is not None and v != ""},
        )
        response.raise_for_status()
        body = response.json()
        if body.get("code") != 0 or body.get("data") is None:
            raise ValueError(f"Referral API error: {body.get('message', 'invalid response')}")
        return body["data"]

    async def get_config(self) -> ReferralConfig:
        return await self._get("config")

    async def resolve_code(self, code: str) -> ReferralCodeResolution:
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9]{6,20}", code):
            raise ValueError("Referral code must be 6-20 ASCII letters or digits")
        return await self._get(f"codes/{code.upper()}")

    async def get_reserved_codes(self) -> Dict[str, Any]:
        return await self._get("reserved-codes")

    async def get_code_availability(self, code: str) -> Dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9]{6,20}", code):
            raise ValueError("Referral code must be 6-20 ASCII letters or digits")
        return await self._get(f"codes/{code.upper()}/availability")

    async def get_overview(self, master: Any) -> ReferralOverview:
        return await self._get(str(_address(master)))

    async def get_invitees(
        self, master: Any, *, limit=50, cursor="", page: Optional[int] = None,
        sort_by: Optional[ReferralInviteeSortBy] = None,
        sort_order: Optional[ReferralSortOrder] = None,
    ) -> ReferralInviteesPage:
        """Server-side sorting; omitted values use timeJoined desc. Reset paging on sort changes."""
        _validate_numbered_page(page, cursor)
        if sort_by is not None and sort_by not in ("timeJoined", "volumeSinceBound", "feePaid", "commissionAccrued"):
            raise ValueError("Invalid referral sort_by")
        if sort_order is not None and sort_order not in ("asc", "desc"):
            raise ValueError("Invalid referral sort_order")
        return await self._get(
            f"{_address(master)}/referrals", limit=limit, cursor=cursor, page=page,
            sortBy=sort_by, sortOrder=sort_order,
        )

    async def get_sources(
        self, master: Any, *, limit=50, cursor=""
    ) -> ReferralPage:
        return await self._get(
            f"{_address(master)}/sources", limit=limit, cursor=cursor,
        )

    async def get_claims(
        self, master: Any, *, limit=50, cursor="", page: Optional[int] = None
    ) -> ReferralClaimsPage:
        _validate_numbered_page(page, cursor)
        return await self._get(
            f"{_address(master)}/claims", limit=limit, cursor=cursor, page=page
        )

    async def get_fills(self, master: Any, *, limit=50, cursor="") -> ReferralPage:
        return await self._get(f"{_address(master)}/fills", limit=limit, cursor=cursor)

    @staticmethod
    def build_register_code(code: str, nonce: int) -> DexOrderlessTx:
        return DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, DexUserConfigTx(
            DexUserConfigTxVariant.REGISTER_REFERRAL_CODE, RegisterReferralCode(nonce, code)
        ))

    @staticmethod
    def build_bind_referrer(code: str, nonce: int) -> DexOrderlessTx:
        return DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, DexUserConfigTx(
            DexUserConfigTxVariant.BIND_REFERRER, BindReferrer(nonce, code)
        ))

    @staticmethod
    def build_set_config(parameters: ReferralParameters, nonce: int,
                         proof: Optional[MultiSigProof] = None) -> DexOrderlessTx:
        return DexOrderlessTx(DexOrderlessTxVariant.DEX_SYSTEM_CONFIG,
                              SetReferralConfig(nonce, parameters), proof)

    async def build_claim(self, master: Any, nonce: int, *,
                          on_behalf_of: Optional[Any] = None) -> DexOrderlessTx:
        config = await self.get_config()
        if not config["gateActive"] or config["active"] is None:
            raise ValueError("Referral claim is not active")
        overview = await self.get_overview(master)
        if int(overview["claimableQuantums"]) < int(config["active"]["minClaimAmountQuantums"]):
            raise ValueError("Claim is below the configured minimum")
        return DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, ClaimReferralRewards(
            nonce, on_behalf_of=None if on_behalf_of is None else _address(on_behalf_of),
        ))

    async def _execute(self, tx: DexOrderlessTx, options: Optional[SubmitOptions]):
        if self.executor is None:
            raise ValueError("Referral actions require IntentionClient.referrals")
        return await self.executor.execute_orderless(tx, options=options)

    async def register_code(self, code: str, nonce: int, options=None):
        return await self._execute(self.build_register_code(code, nonce), options)

    async def set_config(self, parameters: ReferralParameters, nonce: int,
                         proof: Optional[MultiSigProof] = None, options=None):
        # Committee proof is part of the BCS envelope; JSON submission does not
        # preserve it. Keep the same existing executor/signature path.
        options = replace(options or SubmitOptions(), encoding="bcs")
        return await self._execute(self.build_set_config(parameters, nonce, proof), options)

    async def bind_referrer(self, code: str, nonce: int, options=None):
        return await self._execute(self.build_bind_referrer(code, nonce), options)

    async def claim(self, nonce: int, *, on_behalf_of=None, options=None):
        if self.signer is None:
            raise ValueError("Referral actions require a signer")
        master = on_behalf_of or self.signer.account_address
        tx = await self.build_claim(master, nonce, on_behalf_of=on_behalf_of)
        return await self._execute(tx, options)

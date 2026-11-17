# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Optional live-data checks performed before an order transaction is sent."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional
from urllib.parse import quote

import httpx


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    mark_price: Optional[str] = None
    last_price: Optional[str] = None
    mid_price: Optional[str] = None
    trigger_protect_ppm: Optional[int] = None
    condition_price_deviation_ppm: Optional[int] = None
    fetched_at_ms: int = 0
    mark_price_at_ms: Optional[int] = None
    last_price_at_ms: Optional[int] = None
    mid_price_at_ms: Optional[int] = None


class RelayerOrderPreflightProvider:
    """REST-backed mark/last/mid/policy snapshot provider."""

    def __init__(
        self,
        node_url: str,
        relayer_url: str,
        *,
        headers: Optional[Mapping[str, str]] = None,
        trust_env: bool = True,
    ):
        self.node_url = node_url.rstrip("/")
        self.relayer_url = relayer_url.rstrip("/")
        self.headers = dict(headers or {})
        self.trust_env = trust_env

    async def _get(self, url: str, *, allow_not_found: bool = False) -> Optional[Any]:
        async with httpx.AsyncClient(trust_env=self.trust_env) as client:
            response = await client.get(
                url, headers={"Accept": "application/json", **self.headers}
            )
            if allow_not_found and response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _data(body: Any) -> Any:
        if isinstance(body, Mapping):
            if body.get("code") not in (None, 0):
                raise RuntimeError(
                    f"order preflight API error: "
                    f"{body.get('message', body.get('code'))}"
                )
            return body.get("data", body)
        return body

    async def get_market_snapshot(
        self, *, symbol: str, symbol_id: int
    ) -> MarketSnapshot:
        if not self.node_url or not self.relayer_url:
            raise ValueError(
                "full order preflight requires both node_url and relayer_url"
            )
        mark_body = await self._get(f"{self.node_url}/dex/mark_prices")
        marks = mark_body.get("prices", []) if isinstance(mark_body, Mapping) else []
        mark = next(
            (
                item
                for item in marks
                if isinstance(item, Mapping)
                and (
                    item.get("ticker") == symbol
                    or (
                        item.get("symbol_id") is not None
                        and int(item["symbol_id"]) == symbol_id
                    )
                )
            ),
            {},
        )
        trades_body = self._data(
            await self._get(
                f"{self.relayer_url}/v1/trades/perpetualMarket/"
                f"{quote(symbol, safe='')}?limit=1&page=1"
            )
        )
        trades = (
            trades_body.get("trades", []) if isinstance(trades_body, Mapping) else []
        )
        trade = trades[0] if trades and isinstance(trades[0], Mapping) else {}
        book_body = self._data(
            await self._get(
                f"{self.relayer_url}/v1/orderbooks/perpetualMarket/"
                f"{quote(symbol, safe='')}"
            )
        )
        bids = book_body.get("bids", []) if isinstance(book_body, Mapping) else []
        asks = book_body.get("asks", []) if isinstance(book_body, Mapping) else []
        bid = bids[0].get("price") if bids and isinstance(bids[0], Mapping) else None
        ask = asks[0].get("price") if asks and isinstance(asks[0], Mapping) else None
        mid = (
            str((float(bid) + float(ask)) / 2)
            if bid is not None and ask is not None
            else None
        )
        policy = await self._get(
            f"{self.node_url}/dex/trading_policy/{symbol_id}",
            allow_not_found=True,
        )
        if policy is None:
            policy = await self._get(f"{self.node_url}/dex/perpetuals/{symbol_id}")
            trigger_protect = 0
        else:
            trigger_protect = policy.get("trigger_protect_ppm")
        now_ms = int(time.time() * 1000)
        mark_timestamp = mark.get("timestamp")
        if mark_timestamp is not None:
            mark_timestamp = int(mark_timestamp) // 1000
        trade_timestamp = trade.get("createdAt")
        book_timestamp = (
            book_body.get("timestamp") if isinstance(book_body, Mapping) else None
        )
        return MarketSnapshot(
            symbol=symbol,
            mark_price=(
                str(mark.get("mark_price"))
                if mark.get("mark_price") is not None
                else None
            ),
            last_price=(
                str(trade.get("price")) if trade.get("price") is not None else None
            ),
            mid_price=mid,
            trigger_protect_ppm=(
                int(trigger_protect) if trigger_protect is not None else None
            ),
            condition_price_deviation_ppm=(
                int(policy["condition_price_deviation_ppm"])
                if isinstance(policy, Mapping)
                and policy.get("condition_price_deviation_ppm") is not None
                else None
            ),
            fetched_at_ms=now_ms,
            mark_price_at_ms=mark_timestamp,
            last_price_at_ms=(
                int(trade_timestamp) if trade_timestamp is not None else None
            ),
            mid_price_at_ms=(
                int(book_timestamp) if book_timestamp is not None else None
            ),
        )

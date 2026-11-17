# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Market metadata and exact human-value conversion for DEX order clients."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

import httpx

NumberLike = Union[int, float, str]
QUOTE_ATOMIC_RESOLUTION = -6


def _field(data: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in data and data[name] is not None:
            return data[name]
    return None


def _scaled_integer(value: NumberLike, exponent: int) -> int:
    """Return ``truncate(value * 10**exponent)`` without binary-float math."""

    if isinstance(value, bool):
        raise ValueError("boolean is not a decimal value")
    try:
        decimal = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid decimal value: {value!r}") from exc
    if not decimal.is_finite():
        raise ValueError(f"non-finite decimal value: {value!r}")
    scaled = decimal.scaleb(exponent)
    return int(scaled.to_integral_value(rounding=ROUND_DOWN))


@dataclass(frozen=True)
class MarketMetadata:
    symbol: str
    symbol_id: int
    atomic_resolution: int
    quantum_conversion_exponent: int
    step_base_quantums: int
    subticks_per_tick: int
    quote_atomic_resolution: int = QUOTE_ATOMIC_RESOLUTION
    status: Optional[str] = None

    @classmethod
    def from_api(cls, symbol: str, value: Mapping[str, Any]) -> "MarketMetadata":
        symbol_id = _field(value, "clobPairId", "clob_pair_id", "perpetualId", "id")
        atomic_resolution = _field(
            value, "atomicResolution", "atomic_resolution", "base_atomic_resolution"
        )
        quantum_exponent = _field(
            value,
            "quantumConversionExponent",
            "quantum_conversion_exponent",
        )
        step = _field(value, "stepBaseQuantums", "step_base_quantums", "step_size")
        tick = _field(value, "subticksPerTick", "subticks_per_tick", "tick_size")
        missing = [
            name
            for name, item in (
                ("clobPairId", symbol_id),
                ("atomicResolution", atomic_resolution),
                ("quantumConversionExponent", quantum_exponent),
                ("stepBaseQuantums", step),
                ("subticksPerTick", tick),
            )
            if item is None
        ]
        if missing:
            raise ValueError(
                f"market {symbol!r} is missing metadata fields: {', '.join(missing)}"
            )
        quote_resolution = _field(
            value, "quoteAtomicResolution", "quote_atomic_resolution"
        )
        return cls(
            symbol=symbol,
            symbol_id=int(symbol_id),
            atomic_resolution=int(atomic_resolution),
            quantum_conversion_exponent=int(quantum_exponent),
            step_base_quantums=int(step),
            subticks_per_tick=int(tick),
            quote_atomic_resolution=(
                QUOTE_ATOMIC_RESOLUTION
                if quote_resolution is None
                else int(quote_resolution)
            ),
            status=(
                str(_field(value, "status"))
                if _field(value, "status") is not None
                else None
            ),
        )


class SimpleMarketResolver:
    """In-memory market resolver populated from relayer market metadata."""

    def __init__(self, markets: Iterable[MarketMetadata] = ()):
        self._markets: Dict[str, MarketMetadata] = {}
        for market in markets:
            self.upsert(market)

    def upsert(self, market: MarketMetadata) -> None:
        self._markets[market.symbol] = market

    def has(self, symbol: str) -> bool:
        return symbol in self._markets

    def symbols(self) -> List[str]:
        return list(self._markets)

    def metadata(self, symbol: str) -> MarketMetadata:
        try:
            return self._markets[symbol]
        except KeyError as exc:
            raise ValueError(
                f"unknown market {symbol!r}; load it through "
                "client.markets.get_resolver()"
            ) from exc

    def symbol_id(self, symbol: str) -> int:
        return self.metadata(symbol).symbol_id

    def to_quantums(self, symbol: str, size: NumberLike) -> int:
        market = self.metadata(symbol)
        value = _scaled_integer(size, -market.atomic_resolution)
        if market.step_base_quantums > 0:
            value -= value % market.step_base_quantums
        return value

    def to_subticks(self, symbol: str, price: NumberLike) -> int:
        market = self.metadata(symbol)
        exponent = (
            -market.quantum_conversion_exponent
            + market.atomic_resolution
            - market.quote_atomic_resolution
        )
        value = _scaled_integer(price, exponent)
        if market.subticks_per_tick > 0:
            value -= value % market.subticks_per_tick
        return value


class MarketsClient:
    """Fetch and cache ``GET /v1/perpetualMarkets`` metadata."""

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
        self._resolver: Optional[SimpleMarketResolver] = None

    async def fetch_perpetual_markets(
        self,
        *,
        statuses: Optional[Sequence[str]] = None,
        rest_url: Optional[str] = None,
    ) -> SimpleMarketResolver:
        base = (rest_url or self.relayer_url).rstrip("/")
        if not base:
            raise ValueError("fetch_perpetual_markets requires relayer_url or rest_url")
        async with httpx.AsyncClient(trust_env=self.trust_env) as client:
            response = await client.get(
                f"{base}/v1/perpetualMarkets",
                headers={"Accept": "application/json", **self.headers},
            )
            response.raise_for_status()
            body = response.json()
        if isinstance(body, Mapping) and body.get("code") not in (None, 0):
            raise RuntimeError(
                f"fetch_perpetual_markets API error: "
                f"{body.get('message', body.get('code'))}"
            )
        data = body.get("data", body) if isinstance(body, Mapping) else {}
        raw_markets = data.get("markets", data) if isinstance(data, Mapping) else {}
        if not isinstance(raw_markets, Mapping):
            raise ValueError("perpetualMarkets response does not contain a market map")
        allowed = set(statuses or ())
        markets = []
        for symbol, raw in raw_markets.items():
            if not isinstance(raw, Mapping):
                continue
            market = MarketMetadata.from_api(str(symbol), raw)
            if allowed and market.status is not None and market.status not in allowed:
                continue
            markets.append(market)
        return SimpleMarketResolver(markets)

    async def get_resolver(self, *, refresh: bool = False) -> SimpleMarketResolver:
        if refresh or self._resolver is None:
            self._resolver = await self.fetch_perpetual_markets(statuses=("ACTIVE",))
        return self._resolver

    def clear_cache(self) -> None:
        self._resolver = None

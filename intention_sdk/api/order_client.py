# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Executable high-level order API built on top of :mod:`order_intents`."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

from ..core.account import Account
from ..core.account_address import AccountAddress
from .dex_account_client import DexAccountClient, RelayerOpenOrdersProvider
from .dex_executor import (
    DexTransactionExecutor,
    PendingTransactionResult,
    SubmitOptions,
)
from ..types.enums import CreatedBy, OrderPositionMode
from ..transactions.order_intents import (
    BracketOrderGroup,
    MarketResolver,
    ModifyChanges,
    ModifyConditionChanges,
    OrderGroup,
    OrderInput,
    OrderIntents,
    OrderIntentsContext,
    OrderPreflightError,
    OrderRef,
    OrderType,
    OrderValidationIssue,
    PositionTpSlGroup,
    TpSlLeg,
)
from ..transactions.order_preflight import MarketSnapshot, RelayerOrderPreflightProvider


class PreflightProvider(Protocol):
    async def get_market_snapshot(
        self, *, symbol: str, symbol_id: int
    ) -> MarketSnapshot: ...


@dataclass(frozen=True)
class OrderOutcome:
    status: str
    order_id: Optional[int]
    client_order_id: Optional[str]
    symbol_id: int
    reject_reason_code: Optional[int] = None


@dataclass(frozen=True)
class OrderActionResult:
    hash: str
    transaction: Dict[str, Any]
    orders: List[OrderOutcome]
    all_accepted: Optional[bool]


class OrderRejectedError(RuntimeError):
    def __init__(self, result: OrderActionResult):
        self.result = result
        self.rejected_orders = [
            order for order in result.orders if order.status == "rejected"
        ]
        super().__init__(
            f"DEX rejected {len(self.rejected_orders)} order(s) "
            f"in transaction {result.hash}"
        )


def _event_value(event: Any, field: str, default: Any = None) -> Any:
    if isinstance(event, Mapping):
        return event.get(field, default)
    return getattr(event, field, default)


def _event_int(event: Any, field: str, default: Optional[int]) -> Optional[int]:
    value = _event_value(event, field)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _event_client_order_id(event: Any) -> Optional[str]:
    value = _event_value(event, "client_order_id")
    if isinstance(value, Mapping):
        values = value.get("vec")
        value = values[0] if isinstance(values, list) and len(values) == 1 else None
    return value if isinstance(value, str) else None


def order_outcomes_from_events(events: Sequence[Any]) -> List[OrderOutcome]:
    outcomes: List[OrderOutcome] = []
    indexes: Dict[str, int] = {}
    statuses = {
        "OrderPlacedEvent": "placed",
        "ConditionOrderPlacedEvent": "placed",
        "OrderFilledEvent": "filled",
        "OrderCancelledEvent": "cancelled",
        "OrderAmendedEvent": "amended",
        "OrderRejectedEvent": "rejected",
    }
    for index, decoded in enumerate(events):
        status = statuses.get(decoded.event_type)
        if status is None:
            continue
        event = decoded.event
        order_id = _event_int(event, "order_id", 0) or None
        client_order_id = _event_client_order_id(event)
        symbol_id = _event_int(event, "symbol_id", 0) or 0
        key = (
            f"order:{order_id}"
            if order_id is not None
            else f"client:{client_order_id}"
            if client_order_id is not None
            else f"event:{index}"
        )
        outcome = OrderOutcome(
            status=status,
            order_id=order_id,
            client_order_id=client_order_id,
            symbol_id=symbol_id,
            reject_reason_code=(
                _event_int(event, "reject_reason", None)
                if status == "rejected"
                else None
            ),
        )
        existing = indexes.get(key)
        if existing is None:
            indexes[key] = len(outcomes)
            outcomes.append(outcome)
        else:
            outcomes[existing] = outcome
    return outcomes


class OrderClient:
    """Order methods submit and wait by default; ``submit_*`` is the fast path."""

    def __init__(
        self,
        *,
        executor: DexTransactionExecutor,
        signer: Account,
        sub_address: AccountAddress,
        position_mode: OrderPositionMode,
        resolver: MarketResolver,
        node_url: str = "",
        relayer_url: str = "",
        headers: Optional[Dict[str, str]] = None,
        trust_env: bool = True,
        submit_options: Optional[SubmitOptions] = None,
        created_by: CreatedBy = CreatedBy.USER,
        on_behalf_of: Optional[AccountAddress] = None,
        preflight_provider: Optional[PreflightProvider] = None,
        account_provider: Optional[DexAccountClient] = None,
        open_orders_provider: Optional[RelayerOpenOrdersProvider] = None,
    ):
        self.executor = executor
        self.signer = signer
        self.sub_address = sub_address
        self.position_mode = position_mode
        self.resolver = resolver
        self.builder = OrderIntents(
            OrderIntentsContext(
                sub_address=sub_address,
                position_mode=position_mode,
                resolver=resolver,
            )
        )
        self.submit_options = submit_options
        self.created_by = created_by
        self.on_behalf_of = on_behalf_of
        self.preflight_provider = preflight_provider
        if self.preflight_provider is None and node_url and relayer_url:
            self.preflight_provider = RelayerOrderPreflightProvider(
                node_url,
                relayer_url,
                headers=headers,
                trust_env=trust_env,
            )
        self.account_provider = account_provider
        if self.account_provider is None and node_url:
            self.account_provider = DexAccountClient(
                node_url, headers=headers, trust_env=trust_env
            )
        self.open_orders_provider = open_orders_provider
        if self.open_orders_provider is None and relayer_url:
            self.open_orders_provider = RelayerOpenOrdersProvider(
                relayer_url, headers=headers, trust_env=trust_env
            )

    @staticmethod
    def _issue(
        code: str, message: str, symbol: str, field: Optional[str] = None
    ) -> OrderValidationIssue:
        return OrderValidationIssue(code, message, field=field, symbol=symbol)

    def _check_snapshot_age(
        self,
        snapshot: MarketSnapshot,
        *,
        price_type: str,
        max_price_age_ms: Optional[int],
    ) -> List[OrderValidationIssue]:
        if max_price_age_ms is None:
            return []
        if price_type == "LAST_PRICE":
            timestamp = snapshot.last_price_at_ms
        elif price_type == "MID_PRICE":
            timestamp = snapshot.mid_price_at_ms
        else:
            timestamp = snapshot.mark_price_at_ms
        if timestamp is None:
            return []
        if int(time.time() * 1000) - timestamp > max_price_age_ms:
            return [
                self._issue(
                    "REFERENCE_PRICE_STALE",
                    f"{price_type} reference price is stale",
                    snapshot.symbol,
                )
            ]
        return []

    def _check_leg_against_reference(
        self,
        *,
        symbol: str,
        position_side: Optional[str],
        entry_side: Optional[str],
        kind: str,
        leg: TpSlLeg,
        snapshot: MarketSnapshot,
        max_price_age_ms: Optional[int],
    ) -> List[OrderValidationIssue]:
        price_type = leg.trigger_price_type
        reference = (
            snapshot.last_price if price_type == "LAST_PRICE" else snapshot.mark_price
        )
        if reference is None:
            return [
                self._issue(
                    "REFERENCE_PRICE_UNAVAILABLE",
                    f"{price_type} reference price is unavailable",
                    symbol,
                    f"{kind}.trigger_price",
                )
            ]
        issues = self._check_snapshot_age(
            snapshot,
            price_type=price_type,
            max_price_age_ms=max_price_age_ms,
        )
        trigger = self.resolver.to_subticks(symbol, leg.trigger_price)
        reference_subticks = self.resolver.to_subticks(symbol, reference)
        opens_long = (
            position_side == "LONG"
            if position_side in ("LONG", "SHORT")
            else entry_side != "SELL"
        )
        valid = (
            trigger >= reference_subticks
            if kind == "tp" and opens_long
            else trigger <= reference_subticks
            if kind == "tp"
            else trigger <= reference_subticks
            if opens_long
            else trigger >= reference_subticks
        )
        if not valid:
            issues.append(
                self._issue(
                    "TAKE_PROFIT_PRICE_WRONG_SIDE"
                    if kind == "tp"
                    else "STOP_ORDER_PRICE_WRONG_SIDE",
                    f"{kind.upper()} trigger price is on the wrong side of "
                    f"the current {price_type.lower()}",
                    symbol,
                    f"{kind}.trigger_price",
                )
            )
        if (
            price_type == "LAST_PRICE"
            and snapshot.mark_price is not None
            and snapshot.trigger_protect_ppm is not None
        ):
            mark = self.resolver.to_subticks(symbol, snapshot.mark_price)
            if mark > 0:
                deviation = abs(reference_subticks - mark) * 1_000_000 // mark
                if deviation > snapshot.trigger_protect_ppm:
                    issues.append(
                        self._issue(
                            "TRIGGER_PRICE_PROTECTION",
                            "last price is outside the configured mark-price "
                            "protection band",
                            symbol,
                            f"{kind}.trigger_price_type",
                        )
                    )
        if (
            leg.price is not None
            and snapshot.condition_price_deviation_ppm is not None
            and trigger > 0
        ):
            limit_price = self.resolver.to_subticks(symbol, leg.price)
            deviation = abs(limit_price - trigger) * 1_000_000 // trigger
            if deviation > snapshot.condition_price_deviation_ppm:
                issues.append(
                    self._issue(
                        "CONDITION_LIMIT_PRICE_DEVIATION",
                        "condition limit price is outside the configured "
                        "trigger-price deviation",
                        symbol,
                        f"{kind}.price",
                    )
                )
        return issues

    def _check_attached_leg_against_mid(
        self,
        *,
        entry: OrderInput,
        kind: str,
        leg: TpSlLeg,
        snapshot: MarketSnapshot,
        max_price_age_ms: Optional[int],
    ) -> List[OrderValidationIssue]:
        """Validate an attached Market-entry leg against BBO mid only."""

        reference = snapshot.mid_price
        if reference is None:
            return [
                self._issue(
                    "REFERENCE_PRICE_UNAVAILABLE",
                    "MID_PRICE reference price is unavailable",
                    entry.symbol,
                    f"{kind}.trigger_price",
                )
            ]
        try:
            reference_subticks = self.resolver.to_subticks(entry.symbol, reference)
        except (TypeError, ValueError):
            reference_subticks = 0
        if reference_subticks <= 0:
            return [
                self._issue(
                    "REFERENCE_PRICE_UNAVAILABLE",
                    "MID_PRICE reference price is unavailable",
                    entry.symbol,
                    f"{kind}.trigger_price",
                )
            ]
        issues = self._check_snapshot_age(
            snapshot,
            price_type="MID_PRICE",
            max_price_age_ms=max_price_age_ms,
        )
        trigger = self.resolver.to_subticks(entry.symbol, leg.trigger_price)
        opens_long = (
            entry.position_side == "LONG"
            if self.position_mode == OrderPositionMode.HEDGE
            else entry.side != "SELL"
        )
        valid = (
            trigger >= reference_subticks
            if kind == "tp" and opens_long
            else trigger <= reference_subticks
            if kind == "tp"
            else trigger <= reference_subticks
            if opens_long
            else trigger >= reference_subticks
        )
        if not valid:
            issues.append(
                self._issue(
                    "TAKE_PROFIT_PRICE_WRONG_SIDE"
                    if kind == "tp"
                    else "STOP_ORDER_PRICE_WRONG_SIDE",
                    f"{kind.upper()} trigger price is on the wrong side of "
                    "the current BBO mid",
                    entry.symbol,
                    f"{kind}.trigger_price",
                )
            )
        return issues

    async def _snapshot(self, symbol: str, preflight: str) -> Optional[MarketSnapshot]:
        mode = preflight
        if mode == "auto":
            mode = "full" if self.preflight_provider is not None else "local"
        if mode == "local":
            return None
        if mode != "full":
            raise ValueError("preflight must be 'auto', 'local', or 'full'")
        if self.preflight_provider is None:
            raise OrderPreflightError(
                [
                    self._issue(
                        "PREFLIGHT_PROVIDER_UNAVAILABLE",
                        "full preflight requires node_url and relayer_url "
                        "or an injected preflight provider",
                        symbol,
                    )
                ]
            )
        return await self.preflight_provider.get_market_snapshot(
            symbol=symbol, symbol_id=self.resolver.symbol_id(symbol)
        )

    async def preflight_order(
        self,
        order: OrderInput,
        *,
        preflight: str = "auto",
        max_price_age_ms: Optional[int] = None,
    ) -> None:
        issues = self.builder.validate_order(order)
        if issues:
            raise OrderPreflightError(issues)
        if order.type not in (
            OrderType.STOP_LIMIT,
            OrderType.STOP_MARKET,
            OrderType.TAKE_PROFIT_LIMIT,
            OrderType.TAKE_PROFIT_MARKET,
        ):
            return
        snapshot = await self._snapshot(order.symbol, preflight)
        if snapshot is None:
            return
        leg = TpSlLeg(
            type=order.type,
            trigger_price=order.trigger_price,
            trigger_price_type=order.trigger_price_type,
            price=order.price,
        )
        kind = (
            "tp"
            if order.type in (OrderType.TAKE_PROFIT_LIMIT, OrderType.TAKE_PROFIT_MARKET)
            else "sl"
        )
        issues = self._check_leg_against_reference(
            symbol=order.symbol,
            position_side=order.position_side,
            entry_side=("SELL" if order.side == "BUY" else "BUY"),
            kind=kind,
            leg=leg,
            snapshot=snapshot,
            max_price_age_ms=max_price_age_ms,
        )
        if issues:
            raise OrderPreflightError(issues)

    async def preflight_order_with_tpsl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg],
        sl: Optional[TpSlLeg],
        preflight: str = "auto",
        max_price_age_ms: Optional[int] = None,
    ) -> None:
        issues = self.builder.validate_order_with_tpsl(entry, tp=tp, sl=sl)
        if issues:
            raise OrderPreflightError(issues)
        if preflight not in ("auto", "local", "full"):
            raise ValueError("preflight must be 'auto', 'local', or 'full'")
        if entry.type == OrderType.LIMIT:
            return
        snapshot = await self._snapshot(entry.symbol, preflight)
        if snapshot is None:
            return
        for kind, leg in (("tp", tp), ("sl", sl)):
            if leg is not None:
                issues.extend(
                    self._check_attached_leg_against_mid(
                        entry=entry,
                        kind=kind,
                        leg=leg,
                        snapshot=snapshot,
                        max_price_age_ms=max_price_age_ms,
                    )
                )
        if issues:
            raise OrderPreflightError(issues)

    async def preflight_position_tpsl(
        self,
        *,
        symbol: str,
        position_side: Optional[str],
        size_mode: str,
        config_amount: Optional[Any],
        tp: Optional[TpSlLeg],
        sl: Optional[TpSlLeg],
        preflight: str = "auto",
        max_price_age_ms: Optional[int] = None,
    ) -> None:
        issues = self.builder.validate_position_tpsl(
            symbol=symbol,
            position_side=position_side,
            size_mode=size_mode,
            config_amount=config_amount,
            tp=tp,
            sl=sl,
        )
        if issues:
            raise OrderPreflightError(issues)
        snapshot = await self._snapshot(symbol, preflight)
        if snapshot is None:
            return
        for kind, leg in (("tp", tp), ("sl", sl)):
            if leg is not None:
                issues.extend(
                    self._check_leg_against_reference(
                        symbol=symbol,
                        position_side=position_side,
                        entry_side=None,
                        kind=kind,
                        leg=leg,
                        snapshot=snapshot,
                        max_price_age_ms=max_price_age_ms,
                    )
                )
        if issues:
            raise OrderPreflightError(issues)

    async def _execute(
        self,
        orders: Any,
        *,
        timeout_secs: float,
        poll_interval_secs: float,
        throw_on_order_reject: bool,
        include_orders: bool,
    ) -> OrderActionResult:
        executed = await self.executor.execute_orders(
            orders,
            created_by=self.created_by,
            on_behalf_of=self.on_behalf_of,
            options=self.submit_options,
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
        )
        outcomes = order_outcomes_from_events(executed.events) if include_orders else []
        result = OrderActionResult(
            hash=executed.hash,
            transaction=executed.transaction,
            orders=outcomes,
            all_accepted=(
                None
                if not outcomes
                else not any(order.status == "rejected" for order in outcomes)
            ),
        )
        if throw_on_order_reject and result.all_accepted is False:
            raise OrderRejectedError(result)
        return result

    async def _submit(self, orders: Any) -> PendingTransactionResult:
        return await self.executor.submit_orders(
            orders,
            created_by=self.created_by,
            on_behalf_of=self.on_behalf_of,
            options=self.submit_options,
        )

    async def place_order(
        self,
        order: OrderInput,
        *,
        timeout_secs: float = 30,
        poll_interval_secs: float = 1,
        preflight: str = "auto",
        max_price_age_ms: Optional[int] = None,
        throw_on_order_reject: bool = False,
        include_orders: bool = True,
    ) -> OrderActionResult:
        await self.preflight_order(
            order, preflight=preflight, max_price_age_ms=max_price_age_ms
        )
        return await self._execute(
            self.builder.place_order(order),
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
            throw_on_order_reject=throw_on_order_reject,
            include_orders=include_orders,
        )

    async def submit_order(
        self, order: OrderInput, *, preflight: str = "local"
    ) -> PendingTransactionResult:
        await self.preflight_order(order, preflight=preflight)
        return await self._submit(self.builder.place_order(order))

    async def place_order_with_tpsl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
        timeout_secs: float = 30,
        poll_interval_secs: float = 1,
        preflight: str = "auto",
        max_price_age_ms: Optional[int] = None,
        throw_on_order_reject: bool = False,
        include_orders: bool = True,
    ) -> OrderActionResult:
        await self.preflight_order_with_tpsl(
            entry,
            tp=tp,
            sl=sl,
            preflight=preflight,
            max_price_age_ms=max_price_age_ms,
        )
        return await self._execute(
            self.builder.place_order_with_tpsl(entry, tp=tp, sl=sl),
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
            throw_on_order_reject=throw_on_order_reject,
            include_orders=include_orders,
        )

    async def submit_order_with_tpsl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
        preflight: str = "local",
    ) -> PendingTransactionResult:
        await self.preflight_order_with_tpsl(entry, tp=tp, sl=sl, preflight=preflight)
        return await self._submit(
            self.builder.place_order_with_tpsl(entry, tp=tp, sl=sl)
        )

    async def place_order_with_tp_sl(self, *args: Any, **kwargs: Any):
        return await self.place_order_with_tpsl(*args, **kwargs)

    async def submit_order_with_tp_sl(self, *args: Any, **kwargs: Any):
        return await self.submit_order_with_tpsl(*args, **kwargs)

    async def place_position_tpsl(
        self,
        *,
        symbol: str,
        position_side: Optional[str],
        size_mode: str,
        config_amount: Optional[Any] = None,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
        timeout_secs: float = 30,
        poll_interval_secs: float = 1,
        preflight: str = "auto",
        max_price_age_ms: Optional[int] = None,
        throw_on_order_reject: bool = False,
        include_orders: bool = True,
    ) -> OrderActionResult:
        await self.preflight_position_tpsl(
            symbol=symbol,
            position_side=position_side,
            size_mode=size_mode,
            config_amount=config_amount,
            tp=tp,
            sl=sl,
            preflight=preflight,
            max_price_age_ms=max_price_age_ms,
        )
        return await self._execute(
            self.builder.place_position_tpsl(
                symbol=symbol,
                position_side=position_side,
                size_mode=size_mode,
                config_amount=config_amount,
                tp=tp,
                sl=sl,
            ),
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
            throw_on_order_reject=throw_on_order_reject,
            include_orders=include_orders,
        )

    async def submit_position_tpsl(
        self,
        *,
        symbol: str,
        position_side: Optional[str],
        size_mode: str,
        config_amount: Optional[Any] = None,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
        preflight: str = "local",
    ) -> PendingTransactionResult:
        await self.preflight_position_tpsl(
            symbol=symbol,
            position_side=position_side,
            size_mode=size_mode,
            config_amount=config_amount,
            tp=tp,
            sl=sl,
            preflight=preflight,
        )
        return await self._submit(
            self.builder.place_position_tpsl(
                symbol=symbol,
                position_side=position_side,
                size_mode=size_mode,
                config_amount=config_amount,
                tp=tp,
                sl=sl,
            )
        )

    async def place_position_tp_sl(self, **kwargs: Any):
        return await self.place_position_tpsl(**kwargs)

    async def submit_position_tp_sl(self, **kwargs: Any):
        return await self.submit_position_tpsl(**kwargs)

    async def place_orders(
        self,
        groups: Sequence[OrderGroup],
        *,
        timeout_secs: float = 30,
        poll_interval_secs: float = 1,
        preflight: str = "auto",
        throw_on_order_reject: bool = False,
        include_orders: bool = True,
    ) -> OrderActionResult:
        for group in groups:
            if isinstance(group, OrderInput):
                await self.preflight_order(group, preflight=preflight)
            elif isinstance(group, BracketOrderGroup):
                await self.preflight_order_with_tpsl(
                    group.entry,
                    tp=group.tp,
                    sl=group.sl,
                    preflight=preflight,
                )
            elif isinstance(group, PositionTpSlGroup):
                await self.preflight_position_tpsl(
                    symbol=group.symbol,
                    position_side=group.position_side,
                    size_mode=group.size_mode,
                    config_amount=group.config_amount,
                    tp=group.tp,
                    sl=group.sl,
                    preflight=preflight,
                )
        return await self._execute(
            self.builder.place_orders(groups),
            timeout_secs=timeout_secs,
            poll_interval_secs=poll_interval_secs,
            throw_on_order_reject=throw_on_order_reject,
            include_orders=include_orders,
        )

    async def submit_orders(
        self, groups: Sequence[OrderGroup], *, preflight: str = "local"
    ) -> PendingTransactionResult:
        for group in groups:
            if isinstance(group, OrderInput):
                await self.preflight_order(group, preflight=preflight)
            elif isinstance(group, BracketOrderGroup):
                await self.preflight_order_with_tpsl(
                    group.entry,
                    tp=group.tp,
                    sl=group.sl,
                    preflight=preflight,
                )
            elif isinstance(group, PositionTpSlGroup):
                await self.preflight_position_tpsl(
                    symbol=group.symbol,
                    position_side=group.position_side,
                    size_mode=group.size_mode,
                    config_amount=group.config_amount,
                    tp=group.tp,
                    sl=group.sl,
                    preflight=preflight,
                )
        return await self._submit(self.builder.place_orders(groups))

    async def cancel_order(
        self, ref: OrderRef, **execution_options: Any
    ) -> OrderActionResult:
        return await self._execute(
            self.builder.cancel_order(ref),
            timeout_secs=execution_options.pop("timeout_secs", 30),
            poll_interval_secs=execution_options.pop("poll_interval_secs", 1),
            throw_on_order_reject=execution_options.pop("throw_on_order_reject", False),
            include_orders=execution_options.pop("include_orders", True),
        )

    async def submit_cancel_order(self, ref: OrderRef) -> PendingTransactionResult:
        return await self._submit(self.builder.cancel_order(ref))

    async def cancel_orders(
        self, refs: Sequence[OrderRef], **execution_options: Any
    ) -> OrderActionResult:
        return await self._execute(
            self.builder.cancel_orders(refs),
            timeout_secs=execution_options.pop("timeout_secs", 30),
            poll_interval_secs=execution_options.pop("poll_interval_secs", 1),
            throw_on_order_reject=execution_options.pop("throw_on_order_reject", False),
            include_orders=execution_options.pop("include_orders", True),
        )

    async def submit_cancel_orders(
        self, refs: Sequence[OrderRef]
    ) -> PendingTransactionResult:
        return await self._submit(self.builder.cancel_orders(refs))

    async def _open_order_refs(self, symbol: Optional[str] = None) -> List[OrderRef]:
        if self.open_orders_provider is None:
            raise ValueError("cancel_all requires relayer_url or open_orders_provider")
        open_orders = await self.open_orders_provider.get_open_orders(
            address=self.on_behalf_of or self.signer.account_address,
            sub_address=self.sub_address,
            symbol_id=(self.resolver.symbol_id(symbol) if symbol else None),
            symbol=symbol,
        )
        return [OrderRef(order_id=order["order_id"]) for order in open_orders]

    async def cancel_all(
        self, *, symbol: Optional[str] = None, **execution_options: Any
    ) -> OrderActionResult:
        refs = await self._open_order_refs(symbol)
        if not refs:
            raise ValueError("no matching open orders to cancel")
        return await self.cancel_orders(refs, **execution_options)

    async def submit_cancel_all(
        self, *, symbol: Optional[str] = None
    ) -> PendingTransactionResult:
        refs = await self._open_order_refs(symbol)
        if not refs:
            raise ValueError("no matching open orders to cancel")
        return await self.submit_cancel_orders(refs)

    async def modify_order(
        self,
        ref: OrderRef,
        changes: ModifyChanges,
        **execution_options: Any,
    ) -> OrderActionResult:
        return await self._execute(
            self.builder.modify_order(ref, changes),
            timeout_secs=execution_options.pop("timeout_secs", 30),
            poll_interval_secs=execution_options.pop("poll_interval_secs", 1),
            throw_on_order_reject=execution_options.pop("throw_on_order_reject", False),
            include_orders=execution_options.pop("include_orders", True),
        )

    async def modify_orders(
        self,
        changes: Sequence[Tuple[OrderRef, ModifyChanges]],
        **execution_options: Any,
    ) -> OrderActionResult:
        return await self._execute(
            self.builder.modify_orders(changes),
            timeout_secs=execution_options.pop("timeout_secs", 30),
            poll_interval_secs=execution_options.pop("poll_interval_secs", 1),
            throw_on_order_reject=execution_options.pop("throw_on_order_reject", False),
            include_orders=execution_options.pop("include_orders", True),
        )

    async def submit_modify_order(
        self, ref: OrderRef, changes: ModifyChanges
    ) -> PendingTransactionResult:
        return await self._submit(self.builder.modify_order(ref, changes))

    async def submit_modify_orders(
        self, changes: Sequence[Tuple[OrderRef, ModifyChanges]]
    ) -> PendingTransactionResult:
        return await self._submit(self.builder.modify_orders(changes))

    async def modify_condition_order(
        self,
        ref: OrderRef,
        changes: ModifyConditionChanges,
        **execution_options: Any,
    ) -> OrderActionResult:
        return await self._execute(
            self.builder.modify_condition_order(ref, changes),
            timeout_secs=execution_options.pop("timeout_secs", 30),
            poll_interval_secs=execution_options.pop("poll_interval_secs", 1),
            throw_on_order_reject=execution_options.pop("throw_on_order_reject", False),
            include_orders=execution_options.pop("include_orders", True),
        )

    async def modify_condition_orders(
        self,
        changes: Sequence[Tuple[OrderRef, ModifyConditionChanges]],
        **execution_options: Any,
    ) -> OrderActionResult:
        return await self._execute(
            self.builder.modify_condition_orders(changes),
            timeout_secs=execution_options.pop("timeout_secs", 30),
            poll_interval_secs=execution_options.pop("poll_interval_secs", 1),
            throw_on_order_reject=execution_options.pop("throw_on_order_reject", False),
            include_orders=execution_options.pop("include_orders", True),
        )

    async def submit_modify_condition_order(
        self, ref: OrderRef, changes: ModifyConditionChanges
    ) -> PendingTransactionResult:
        return await self._submit(self.builder.modify_condition_order(ref, changes))

    async def submit_modify_condition_orders(
        self, changes: Sequence[Tuple[OrderRef, ModifyConditionChanges]]
    ) -> PendingTransactionResult:
        return await self._submit(self.builder.modify_condition_orders(changes))

    async def _close_order(
        self,
        *,
        symbol: str,
        position_side: Optional[str] = None,
        size: Any = "ALL",
        order_type: OrderType = OrderType.MARKET,
        price: Optional[Any] = None,
    ) -> OrderInput:
        size_quantums: Optional[int] = None
        resolved_size = size
        if size == "ALL":
            if self.account_provider is None:
                raise ValueError(
                    "full-position close requires node_url or account_provider"
                )
            positions = await self.account_provider.get_positions(
                self.on_behalf_of or self.signer.account_address,
                self.sub_address,
            )
            symbol_id = self.resolver.symbol_id(symbol)
            position = next(
                (
                    item
                    for item in positions
                    if int(item.get("perpetual_id", -1)) == symbol_id
                ),
                None,
            )
            if position is None:
                raise ValueError(f"no open position for {symbol}")
            if self.position_mode == OrderPositionMode.HEDGE:
                if position_side not in ("LONG", "SHORT"):
                    raise ValueError("hedge full-position close requires position_side")
                field = "long_quantums" if position_side == "LONG" else "short_quantums"
                size_quantums = abs(int(position.get(field, 0)))
            else:
                long_value = abs(int(position.get("long_quantums", 0)))
                short_value = abs(int(position.get("short_quantums", 0)))
                if long_value and short_value:
                    raise ValueError(
                        "net position snapshot contains both long and short quantums"
                    )
                position_side = "LONG" if long_value else "SHORT"
                size_quantums = long_value or short_value
            if not size_quantums:
                raise ValueError(f"position for {symbol} has zero quantums")
            resolved_size = None
        side = "SELL" if position_side != "SHORT" else "BUY"
        return OrderInput(
            symbol=symbol,
            side=side,
            type=order_type,
            size=resolved_size,
            size_quantums=size_quantums,
            price=price,
            reduce_only=True,
            position_side=position_side,
        )

    async def close_position(
        self,
        *,
        symbol: str,
        position_side: Optional[str] = None,
        size: Any = "ALL",
        order_type: OrderType = OrderType.MARKET,
        price: Optional[Any] = None,
        **execution_options: Any,
    ) -> OrderActionResult:
        order = await self._close_order(
            symbol=symbol,
            position_side=position_side,
            size=size,
            order_type=order_type,
            price=price,
        )
        return await self.place_order(order, **execution_options)

    async def close_positions(
        self, positions: Sequence[Dict[str, Any]], **execution_options: Any
    ) -> OrderActionResult:
        orders = [await self._close_order(**position) for position in positions]
        return await self.place_orders(orders, **execution_options)

    async def submit_close_position(self, **position: Any) -> PendingTransactionResult:
        return await self.submit_order(
            await self._close_order(**position), preflight="local"
        )

    async def submit_close_positions(
        self, positions: Sequence[Dict[str, Any]]
    ) -> PendingTransactionResult:
        orders = [await self._close_order(**position) for position in positions]
        return await self.submit_orders(orders, preflight="local")

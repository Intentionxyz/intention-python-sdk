# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""High-level DEX order intent helpers.

The raw DEX wire remains available in ``dex_transactions``. This module keeps
the common order-entry UX aligned with the TypeScript SDK: callers describe the
order they want, while the SDK maps it to grouping, TP/SL legs, hedge
``position_side`` selection, and condition-replace wire details.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Protocol, Sequence, Tuple, Union

from ..core.account_address import AccountAddress
from .dex_payloads import (
    DexCancelOrder,
    DexCancelTarget,
    DexConditionReplaceOrder,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexReplaceOrder,
    DexReplaceTarget,
    DexTx,
)
from ..types.enums import (
    ConditionType,
    CreatedBy,
    DexOrdersVariant,
    Grouping,
    OrderBasicType,
    OrderPositionMode,
    Side,
    StpMode,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)

DEFAULT_SLIPPAGE_TOLERANCE_PPM = 100_000
NumberLike = Union[int, float, str]
SizeValue = Union[int, float, str]
PriceValue = Union[int, float, str]


class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP_LIMIT = "STOP_LIMIT"
    STOP_MARKET = "STOP_MARKET"
    TAKE_PROFIT_LIMIT = "TAKE_PROFIT_LIMIT"
    TAKE_PROFIT_MARKET = "TAKE_PROFIT_MARKET"


class MarketResolver(Protocol):
    def symbol_id(self, symbol: str) -> int: ...

    def to_quantums(self, symbol: str, size: NumberLike) -> int: ...

    def to_subticks(self, symbol: str, price: NumberLike) -> int: ...


@dataclass(frozen=True)
class OrderInput:
    symbol: str
    side: str
    type: OrderType
    size: Optional[SizeValue] = None
    price: Optional[PriceValue] = None
    trigger_price: Optional[PriceValue] = None
    trigger_price_type: str = "MARK_PRICE"
    reduce_only: bool = False
    time_in_force: Optional[TimeInForce] = None
    post_only: bool = False
    position_side: Optional[str] = None
    client_order_id: Optional[str] = None
    # Advanced exact-wire override, used for full-position closes.
    size_quantums: Optional[int] = None


@dataclass(frozen=True)
class TpSlLeg:
    type: OrderType
    trigger_price: PriceValue
    trigger_price_type: str = "MARK_PRICE"
    price: Optional[PriceValue] = None
    client_order_id: Optional[str] = None


@dataclass(frozen=True)
class OrderRef:
    order_id: Optional[int] = None
    client_order_id: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.order_id is None) == (self.client_order_id is None):
            raise ValueError(
                "OrderRef requires exactly one of order_id or client_order_id"
            )


@dataclass(frozen=True)
class ModifyChanges:
    price: Optional[PriceValue] = None
    size: Optional[SizeValue] = None
    new_client_order_id: Optional[str] = None
    # When set, price/size are human values and are resolved to wire units.
    # Omitting symbol preserves the legacy wire-unit behavior.
    symbol: Optional[str] = None


@dataclass(frozen=True)
class ModifyConditionChanges:
    symbol: str
    type: OrderType
    trigger_price: Union[int, str]
    size_mode: str = "fixed"
    size: Optional[Union[int, str]] = None
    price: Optional[Union[int, str]] = None
    trigger_price_type: str = "MARK_PRICE"
    new_client_order_id: Optional[str] = None
    # Enables client-side immutability validation when the target snapshot is known.
    current_size_mode: Optional[str] = None


@dataclass(frozen=True)
class BracketOrderGroup:
    entry: OrderInput
    tp: Optional[TpSlLeg] = None
    sl: Optional[TpSlLeg] = None


@dataclass(frozen=True)
class PositionTpSlGroup:
    symbol: str
    position_side: Optional[str]
    size_mode: str
    config_amount: Optional[SizeValue] = None
    tp: Optional[TpSlLeg] = None
    sl: Optional[TpSlLeg] = None


OrderGroup = Union[OrderInput, BracketOrderGroup, PositionTpSlGroup]


@dataclass(frozen=True)
class OrderValidationIssue:
    code: str
    message: str
    field: Optional[str] = None
    symbol: Optional[str] = None
    group_index: Optional[int] = None


class OrderPreflightError(ValueError):
    def __init__(self, issues: Sequence[OrderValidationIssue]):
        self.issues = list(issues)
        super().__init__(
            self.issues[0].message if self.issues else "order preflight failed"
        )


@dataclass(frozen=True)
class OrderIntentsContext:
    sub_address: AccountAddress
    position_mode: OrderPositionMode
    resolver: MarketResolver
    symbol_type: SymbolType = SymbolType.PERPETUAL
    slippage_tolerance_ppm: int = DEFAULT_SLIPPAGE_TOLERANCE_PPM
    stp_mode: StpMode = StpMode.EXPIRE_MAKER


def order_type_to_basics(order_type: OrderType) -> Tuple[OrderBasicType, ConditionType]:
    if order_type == OrderType.LIMIT:
        return OrderBasicType.LIMIT, ConditionType.UNSPECIFIED
    if order_type == OrderType.MARKET:
        return OrderBasicType.MARKET, ConditionType.UNSPECIFIED
    if order_type == OrderType.STOP_LIMIT:
        return OrderBasicType.LIMIT, ConditionType.STOP_LOSS
    if order_type == OrderType.STOP_MARKET:
        return OrderBasicType.MARKET, ConditionType.STOP_LOSS
    if order_type == OrderType.TAKE_PROFIT_LIMIT:
        return OrderBasicType.LIMIT, ConditionType.TAKE_PROFIT
    if order_type == OrderType.TAKE_PROFIT_MARKET:
        return OrderBasicType.MARKET, ConditionType.TAKE_PROFIT
    raise ValueError(f"unknown OrderType: {order_type!r}")


def resolve_time_in_force(
    order_type: OrderType,
    time_in_force: Optional[TimeInForce] = None,
    post_only: bool = False,
) -> TimeInForce:
    if time_in_force is not None and not isinstance(time_in_force, TimeInForce):
        raise TypeError("time_in_force must use the TimeInForce enum")
    if time_in_force not in (
        None,
        TimeInForce.GTC,
        TimeInForce.IOC,
        TimeInForce.ALO,
    ):
        raise ValueError("high-level order API supports only GTC, IOC, and ALO")
    if post_only and time_in_force == TimeInForce.IOC:
        raise ValueError("post_only cannot be combined with IOC")
    if (post_only or time_in_force == TimeInForce.ALO) and order_type_to_basics(
        order_type
    )[0] != OrderBasicType.LIMIT:
        raise ValueError("post_only/ALO is only supported for limit orders")
    if post_only or time_in_force == TimeInForce.ALO:
        return TimeInForce.ALO
    if time_in_force is not None:
        return time_in_force
    basic_type, _ = order_type_to_basics(order_type)
    return TimeInForce.IOC if basic_type == OrderBasicType.MARKET else TimeInForce.GTC


def encode_leg_selection(
    *,
    position_mode: OrderPositionMode,
    intent_side: str,
    reduce_only: bool,
    position_side: Optional[str],
    abs_quantums: int,
) -> Tuple[Side, int]:
    abs_value = abs(abs_quantums)
    if position_mode == OrderPositionMode.HEDGE:
        if position_side is None:
            raise ValueError("Hedge mode requires position_side ('LONG' | 'SHORT')")
        side = (
            Side.BUY
            if reduce_only and abs_value == 0 and position_side == "SHORT"
            else Side.SELL if reduce_only else Side.BUY
        )
        quantums = abs_value if position_side == "LONG" else -abs_value
        return side, quantums
    return Side.BUY if intent_side == "BUY" else Side.SELL, abs_value


def cancel_target_from_ref(ref: OrderRef) -> DexCancelTarget:
    if ref.order_id is not None:
        return DexCancelTarget.by_order_id(ref.order_id)
    assert ref.client_order_id is not None
    return DexCancelTarget.by_client_order_id(ref.client_order_id)


def replace_target_from_ref(
    ref: OrderRef,
    *,
    symbol_id: Optional[int] = None,
    symbol_type: SymbolType = SymbolType.PERPETUAL,
) -> DexReplaceTarget:
    if ref.order_id is not None:
        if symbol_id is not None:
            return DexReplaceTarget.by_order_id_with_context(
                ref.order_id,
                symbol_id,
                symbol_type,
            )
        return DexReplaceTarget.by_order_id(ref.order_id)
    assert ref.client_order_id is not None
    return DexReplaceTarget.by_client_order_id(ref.client_order_id)


def _trigger_price_type(kind: str) -> TriggerPriceType:
    return (
        TriggerPriceType.MARK_PRICE
        if kind == "MARK_PRICE"
        else TriggerPriceType.LAST_PRICE
    )


class OrderIntents:
    def __init__(self, ctx: OrderIntentsContext):
        self.ctx = ctx

    def _build_place_order(
        self,
        order: OrderInput,
        force_reduce_only: Optional[bool] = None,
    ) -> DexPlaceOrder:
        basic_type, condition_type = order_type_to_basics(order.type)
        abs_quantums = (
            abs(order.size_quantums)
            if order.size_quantums is not None
            else (
                self.ctx.resolver.to_quantums(order.symbol, order.size)
                if order.size is not None
                else 0
            )
        )
        side, quantums = encode_leg_selection(
            position_mode=self.ctx.position_mode,
            intent_side=order.side,
            reduce_only=(
                force_reduce_only
                if force_reduce_only is not None
                else order.reduce_only
            ),
            position_side=order.position_side,
            abs_quantums=abs_quantums,
        )
        subticks = (
            self.ctx.resolver.to_subticks(order.symbol, order.price)
            if order.price is not None
            else 0
        )
        trigger_subticks = (
            self.ctx.resolver.to_subticks(order.symbol, order.trigger_price)
            if order.trigger_price is not None
            else 0
        )
        reduce_only = (
            force_reduce_only if force_reduce_only is not None else order.reduce_only
        )

        return DexPlaceOrder(
            sub_address=self.ctx.sub_address,
            symbol_id=self.ctx.resolver.symbol_id(order.symbol),
            symbol_type=self.ctx.symbol_type,
            side=side,
            quantums=quantums,
            subticks=subticks,
            trigger_subticks=trigger_subticks,
            order_basic_type=basic_type,
            time_in_force=resolve_time_in_force(
                order.type, order.time_in_force, order.post_only
            ),
            condition_type=condition_type,
            trigger_price_type=_trigger_price_type(order.trigger_price_type),
            target_order_id=0,
            reduce_only=reduce_only,
            position_mode=self.ctx.position_mode,
            slippage_tolerance_ppm=self.ctx.slippage_tolerance_ppm,
            client_order_id=order.client_order_id,
            stp_mode=self.ctx.stp_mode,
        )

    def _known_symbol_issue(self, symbol: str) -> List[OrderValidationIssue]:
        try:
            self.ctx.resolver.symbol_id(symbol)
        except (KeyError, ValueError):
            return [
                OrderValidationIssue(
                    "UNKNOWN_MARKET",
                    f"unknown market {symbol!r}",
                    field="symbol",
                    symbol=symbol,
                )
            ]
        return []

    def _positive_value_issues(
        self,
        symbol: str,
        value: Optional[NumberLike],
        *,
        field: str,
        converter: str,
    ) -> List[OrderValidationIssue]:
        if value is None:
            return [
                OrderValidationIssue(
                    f"REQUIRED_{field.upper()}",
                    f"{field} is required",
                    field=field,
                    symbol=symbol,
                )
            ]
        try:
            resolved = getattr(self.ctx.resolver, converter)(symbol, value)
        except (TypeError, ValueError):
            return [
                OrderValidationIssue(
                    f"INVALID_{field.upper()}",
                    f"{field} must be a valid decimal value",
                    field=field,
                    symbol=symbol,
                )
            ]
        if resolved <= 0:
            return [
                OrderValidationIssue(
                    f"{field.upper()}_MUST_BE_POSITIVE",
                    f"{field} must resolve to a positive wire value",
                    field=field,
                    symbol=symbol,
                )
            ]
        return []

    def validate_order(self, order: OrderInput) -> List[OrderValidationIssue]:
        issues = self._known_symbol_issue(order.symbol)
        if issues:
            return issues
        if (
            self.ctx.position_mode == OrderPositionMode.HEDGE
            and order.position_side not in ("LONG", "SHORT")
        ):
            issues.append(
                OrderValidationIssue(
                    "REQUIRED_POSITION_SIDE",
                    "hedge mode requires position_side ('LONG' or 'SHORT')",
                    field="position_side",
                    symbol=order.symbol,
                )
            )
        if order.size_quantums is not None:
            if order.size is not None:
                issues.append(
                    OrderValidationIssue(
                        "AMBIGUOUS_SIZE",
                        "provide size or size_quantums, not both",
                        field="size",
                        symbol=order.symbol,
                    )
                )
            elif order.size_quantums <= 0:
                issues.append(
                    OrderValidationIssue(
                        "SIZE_MUST_BE_POSITIVE",
                        "size_quantums must be positive",
                        field="size_quantums",
                        symbol=order.symbol,
                    )
                )
        else:
            issues.extend(
                self._positive_value_issues(
                    order.symbol,
                    order.size,
                    field="size",
                    converter="to_quantums",
                )
            )
        basic_type, condition_type = order_type_to_basics(order.type)
        if basic_type == OrderBasicType.LIMIT:
            issues.extend(
                self._positive_value_issues(
                    order.symbol,
                    order.price,
                    field="price",
                    converter="to_subticks",
                )
            )
        elif order.price is not None:
            issues.append(
                OrderValidationIssue(
                    "UNEXPECTED_LIMIT_PRICE",
                    "market orders must not include price",
                    field="price",
                    symbol=order.symbol,
                )
            )
        if condition_type != ConditionType.UNSPECIFIED:
            issues.extend(
                self._positive_value_issues(
                    order.symbol,
                    order.trigger_price,
                    field="trigger_price",
                    converter="to_subticks",
                )
            )
        elif order.trigger_price is not None:
            issues.append(
                OrderValidationIssue(
                    "UNEXPECTED_TRIGGER_PRICE",
                    "non-conditional orders must not include trigger_price",
                    field="trigger_price",
                    symbol=order.symbol,
                )
            )
        if order.post_only and basic_type != OrderBasicType.LIMIT:
            issues.append(
                OrderValidationIssue(
                    "POST_ONLY_REQUIRES_LIMIT",
                    "post_only is only supported for limit orders",
                    field="post_only",
                    symbol=order.symbol,
                )
            )
        if order.post_only and order.time_in_force == TimeInForce.IOC:
            issues.append(
                OrderValidationIssue(
                    "POST_ONLY_TIF_CONFLICT",
                    "post_only cannot be combined with IOC",
                    field="time_in_force",
                    symbol=order.symbol,
                )
            )
        return issues

    def _validate_tpsl_leg(
        self, symbol: str, kind: str, leg: TpSlLeg, *, position_level: bool
    ) -> List[OrderValidationIssue]:
        valid_types = (
            (OrderType.TAKE_PROFIT_MARKET, OrderType.TAKE_PROFIT_LIMIT)
            if kind == "tp"
            else (OrderType.STOP_MARKET, OrderType.STOP_LIMIT)
        )
        issues: List[OrderValidationIssue] = []
        if leg.type not in valid_types:
            issues.append(
                OrderValidationIssue(
                    f"INVALID_{kind.upper()}_ORDER_TYPE",
                    f"{kind.upper()} leg has an incompatible order type",
                    field=f"{kind}.type",
                    symbol=symbol,
                )
            )
        issues.extend(
            self._positive_value_issues(
                symbol,
                leg.trigger_price,
                field=f"{kind}_trigger_price",
                converter="to_subticks",
            )
        )
        basic_type, _ = order_type_to_basics(leg.type)
        if basic_type == OrderBasicType.LIMIT:
            if not position_level:
                issues.append(
                    OrderValidationIssue(
                        "TPSL_LIMIT_NOT_SUPPORTED",
                        "attached order TP/SL currently supports market legs only",
                        field=f"{kind}.type",
                        symbol=symbol,
                    )
                )
            issues.extend(
                self._positive_value_issues(
                    symbol,
                    leg.price,
                    field=f"{kind}_price",
                    converter="to_subticks",
                )
            )
        elif leg.price is not None:
            issues.append(
                OrderValidationIssue(
                    "UNEXPECTED_LIMIT_PRICE",
                    f"{kind.upper()} market leg must not include price",
                    field=f"{kind}.price",
                    symbol=symbol,
                )
            )
        return issues

    def _direction_issues(
        self,
        entry: OrderInput,
        kind: str,
        leg: TpSlLeg,
        reference: NumberLike,
    ) -> List[OrderValidationIssue]:
        trigger = self.ctx.resolver.to_subticks(entry.symbol, leg.trigger_price)
        ref = self.ctx.resolver.to_subticks(entry.symbol, reference)
        opens_long = (
            entry.position_side == "LONG"
            if self.ctx.position_mode == OrderPositionMode.HEDGE
            else entry.side == "BUY"
        )
        valid = (
            trigger >= ref
            if kind == "tp" and opens_long
            else (
                trigger <= ref
                if kind == "tp"
                else trigger <= ref if opens_long else trigger >= ref
            )
        )
        if valid:
            return []
        code = (
            "TAKE_PROFIT_PRICE_MUST_ABOVE_REF"
            if kind == "tp" and opens_long
            else (
                "TAKE_PROFIT_PRICE_MUST_BELOW_REF"
                if kind == "tp"
                else (
                    "STOP_ORDER_PRICE_MUST_BELOW_REF"
                    if opens_long
                    else "STOP_ORDER_PRICE_MUST_ABOVE_REF"
                )
            )
        )
        return [
            OrderValidationIssue(
                code,
                f"{kind.upper()} trigger price is on the wrong side of "
                "the reference price",
                field=f"{kind}.trigger_price",
                symbol=entry.symbol,
            )
        ]

    def validate_order_with_tpsl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
    ) -> List[OrderValidationIssue]:
        issues = self.validate_order(entry)
        if order_type_to_basics(entry.type)[1] != ConditionType.UNSPECIFIED:
            issues.append(
                OrderValidationIssue(
                    "INVALID_BRACKET_ENTRY",
                    "attached TP/SL requires a LIMIT or MARKET entry",
                    field="type",
                    symbol=entry.symbol,
                )
            )
        if entry.reduce_only:
            issues.append(
                OrderValidationIssue(
                    "REDUCE_ONLY_CANNOT_HAVE_TPSL",
                    "reduce-only entry orders cannot have attached TP/SL",
                    field="reduce_only",
                    symbol=entry.symbol,
                )
            )
        if tp is None and sl is None:
            issues.append(
                OrderValidationIssue(
                    "REQUIRED_TPSL",
                    "at least one TP or SL leg is required",
                    symbol=entry.symbol,
                )
            )
        if tp is not None:
            issues.extend(
                self._validate_tpsl_leg(entry.symbol, "tp", tp, position_level=False)
            )
        if sl is not None:
            issues.extend(
                self._validate_tpsl_leg(entry.symbol, "sl", sl, position_level=False)
            )
        if entry.type == OrderType.LIMIT and entry.price is not None:
            if tp is not None:
                issues.extend(self._direction_issues(entry, "tp", tp, entry.price))
            if sl is not None:
                issues.extend(self._direction_issues(entry, "sl", sl, entry.price))
        return issues

    def validate_position_tpsl(
        self,
        *,
        symbol: str,
        position_side: Optional[str],
        size_mode: str,
        config_amount: Optional[SizeValue] = None,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
    ) -> List[OrderValidationIssue]:
        issues = self._known_symbol_issue(symbol)
        if self.ctx.position_mode == OrderPositionMode.HEDGE and position_side not in (
            "LONG",
            "SHORT",
        ):
            issues.append(
                OrderValidationIssue(
                    "REQUIRED_POSITION_SIDE",
                    "hedge mode requires position_side ('LONG' or 'SHORT')",
                    field="position_side",
                    symbol=symbol,
                )
            )
        if size_mode not in ("fixed", "close_position"):
            issues.append(
                OrderValidationIssue(
                    "INVALID_SIZE_MODE",
                    "size_mode must be 'fixed' or 'close_position'",
                    field="size_mode",
                    symbol=symbol,
                )
            )
        elif size_mode == "fixed":
            issues.extend(
                self._positive_value_issues(
                    symbol,
                    config_amount,
                    field="config_amount",
                    converter="to_quantums",
                )
            )
        if tp is None and sl is None:
            issues.append(
                OrderValidationIssue(
                    "REQUIRED_TPSL",
                    "at least one TP or SL leg is required",
                    symbol=symbol,
                )
            )
        if tp is not None:
            issues.extend(
                self._validate_tpsl_leg(symbol, "tp", tp, position_level=True)
            )
        if sl is not None:
            issues.extend(
                self._validate_tpsl_leg(symbol, "sl", sl, position_level=True)
            )
        return issues

    def validate_orders(
        self, groups: Sequence[OrderGroup]
    ) -> List[OrderValidationIssue]:
        issues: List[OrderValidationIssue] = []
        for index, group in enumerate(groups):
            if isinstance(group, OrderInput):
                found = self.validate_order(group)
            elif isinstance(group, BracketOrderGroup):
                found = self.validate_order_with_tpsl(
                    group.entry, tp=group.tp, sl=group.sl
                )
            else:
                found = self.validate_position_tpsl(
                    symbol=group.symbol,
                    position_side=group.position_side,
                    size_mode=group.size_mode,
                    config_amount=group.config_amount,
                    tp=group.tp,
                    sl=group.sl,
                )
            issues.extend(
                OrderValidationIssue(
                    issue.code,
                    issue.message,
                    issue.field,
                    issue.symbol,
                    index,
                )
                for issue in found
            )
        return issues

    @staticmethod
    def assert_valid(issues: Sequence[OrderValidationIssue]) -> None:
        if issues:
            raise OrderPreflightError(issues)

    def _build_child_leg(self, entry: OrderInput, leg: TpSlLeg) -> DexPlaceOrder:
        child_side = "SELL" if entry.side == "BUY" else "BUY"
        return self._build_place_order(
            OrderInput(
                symbol=entry.symbol,
                side=child_side,
                type=leg.type,
                size=entry.size,
                price=leg.price,
                trigger_price=leg.trigger_price,
                trigger_price_type=leg.trigger_price_type,
                position_side=entry.position_side,
                client_order_id=leg.client_order_id,
            ),
            force_reduce_only=True,
        )

    def _build_position_leg(
        self,
        *,
        symbol: str,
        position_side: Optional[str],
        size_mode: str,
        config_amount: Optional[SizeValue],
        leg: TpSlLeg,
    ) -> DexPlaceOrder:
        size = config_amount if size_mode == "fixed" else None
        side = (
            "BUY"
            if size_mode == "close_position" and position_side == "SHORT"
            else "SELL"
        )
        return self._build_place_order(
            OrderInput(
                symbol=symbol,
                side=side,
                type=leg.type,
                size=size,
                price=leg.price,
                trigger_price=leg.trigger_price,
                trigger_price_type=leg.trigger_price_type,
                position_side=position_side,
                client_order_id=leg.client_order_id,
            ),
            force_reduce_only=True,
        )

    def place_order(self, order: OrderInput) -> DexOrders:
        self.assert_valid(self.validate_order(order))
        return DexOrders(
            DexOrdersVariant.PLACE,
            [DexPlaceOrders([self._build_place_order(order)], Grouping.NA)],
        )

    def place_order_with_tpsl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
    ) -> DexOrders:
        self.assert_valid(self.validate_order_with_tpsl(entry, tp=tp, sl=sl))
        orders = [self._build_place_order(entry)]
        if tp is not None:
            orders.append(self._build_child_leg(entry, tp))
        if sl is not None:
            orders.append(self._build_child_leg(entry, sl))
        return DexOrders(
            DexOrdersVariant.PLACE,
            [DexPlaceOrders(orders, Grouping.NORMAL_TPSL)],
        )

    def place_order_with_tp_sl(
        self,
        entry: OrderInput,
        *,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
    ) -> DexOrders:
        return self.place_order_with_tpsl(entry, tp=tp, sl=sl)

    def place_position_tpsl(
        self,
        *,
        symbol: str,
        position_side: Optional[str],
        size_mode: str,
        config_amount: Optional[SizeValue] = None,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
    ) -> DexOrders:
        self.assert_valid(
            self.validate_position_tpsl(
                symbol=symbol,
                position_side=position_side,
                size_mode=size_mode,
                config_amount=config_amount,
                tp=tp,
                sl=sl,
            )
        )
        orders = []
        if tp is not None:
            orders.append(
                self._build_position_leg(
                    symbol=symbol,
                    position_side=position_side,
                    size_mode=size_mode,
                    config_amount=config_amount,
                    leg=tp,
                )
            )
        if sl is not None:
            orders.append(
                self._build_position_leg(
                    symbol=symbol,
                    position_side=position_side,
                    size_mode=size_mode,
                    config_amount=config_amount,
                    leg=sl,
                )
            )
        return DexOrders(
            DexOrdersVariant.PLACE,
            [DexPlaceOrders(orders, Grouping.POSITION_TPSL)],
        )

    def place_position_tp_sl(
        self,
        *,
        symbol: str,
        position_side: Optional[str],
        size_mode: str,
        config_amount: Optional[SizeValue] = None,
        tp: Optional[TpSlLeg] = None,
        sl: Optional[TpSlLeg] = None,
    ) -> DexOrders:
        return self.place_position_tpsl(
            symbol=symbol,
            position_side=position_side,
            size_mode=size_mode,
            config_amount=config_amount,
            tp=tp,
            sl=sl,
        )

    def place_orders(self, groups: Sequence[OrderGroup]) -> DexOrders:
        if not groups:
            raise ValueError("groups cannot be empty")
        self.assert_valid(self.validate_orders(groups))
        batches: List[DexPlaceOrders] = []
        for group in groups:
            if isinstance(group, OrderInput):
                batches.append(
                    DexPlaceOrders(
                        [self._build_place_order(group)],
                        Grouping.NA,
                    )
                )
            elif isinstance(group, BracketOrderGroup):
                items = [self._build_place_order(group.entry)]
                if group.tp is not None:
                    items.append(self._build_child_leg(group.entry, group.tp))
                if group.sl is not None:
                    items.append(self._build_child_leg(group.entry, group.sl))
                batches.append(DexPlaceOrders(items, Grouping.NORMAL_TPSL))
            else:
                items = []
                if group.tp is not None:
                    items.append(
                        self._build_position_leg(
                            symbol=group.symbol,
                            position_side=group.position_side,
                            size_mode=group.size_mode,
                            config_amount=group.config_amount,
                            leg=group.tp,
                        )
                    )
                if group.sl is not None:
                    items.append(
                        self._build_position_leg(
                            symbol=group.symbol,
                            position_side=group.position_side,
                            size_mode=group.size_mode,
                            config_amount=group.config_amount,
                            leg=group.sl,
                        )
                    )
                batches.append(DexPlaceOrders(items, Grouping.POSITION_TPSL))
        return DexOrders(DexOrdersVariant.PLACE, batches)

    def close_position(
        self,
        *,
        symbol: str,
        side: str,
        size: SizeValue,
        position_side: Optional[str] = None,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[PriceValue] = None,
        client_order_id: Optional[str] = None,
    ) -> DexOrders:
        return self.place_order(
            OrderInput(
                symbol=symbol,
                side=side,
                type=order_type,
                size=size,
                price=price,
                reduce_only=True,
                position_side=position_side,
                client_order_id=client_order_id,
            )
        )

    def cancel_order(self, ref: OrderRef) -> DexOrders:
        return DexOrders(
            DexOrdersVariant.CANCEL,
            [
                DexCancelOrder(
                    self.ctx.sub_address,
                    cancel_target_from_ref(ref),
                    self.ctx.symbol_type,
                )
            ],
        )

    def cancel_orders(self, refs: Sequence[OrderRef]) -> DexOrders:
        return DexOrders(
            DexOrdersVariant.CANCEL,
            [
                DexCancelOrder(
                    self.ctx.sub_address,
                    cancel_target_from_ref(ref),
                    self.ctx.symbol_type,
                )
                for ref in refs
            ],
        )

    def modify_order(self, ref: OrderRef, changes: ModifyChanges) -> DexOrders:
        quantums = changes.size
        subticks = changes.price
        if changes.symbol is not None:
            quantums = (
                self.ctx.resolver.to_quantums(changes.symbol, changes.size)
                if changes.size is not None
                else None
            )
            subticks = (
                self.ctx.resolver.to_subticks(changes.symbol, changes.price)
                if changes.price is not None
                else None
            )
        else:
            if changes.size is not None and not isinstance(changes.size, int):
                raise ValueError(
                    "modify_order size requires symbol unless already in wire quantums"
                )
            if changes.price is not None and not isinstance(changes.price, int):
                raise ValueError(
                    "modify_order price requires symbol unless already in wire subticks"
                )
        return DexOrders(
            DexOrdersVariant.REPLACE,
            [
                DexReplaceOrder(
                    self.ctx.sub_address,
                    replace_target_from_ref(
                        ref,
                        symbol_id=(
                            self.ctx.resolver.symbol_id(changes.symbol)
                            if changes.symbol is not None
                            else None
                        ),
                        symbol_type=self.ctx.symbol_type,
                    ),
                    quantums,
                    subticks,
                    changes.new_client_order_id,
                )
            ],
        )

    def modify_orders(
        self, changes: Sequence[Tuple[OrderRef, ModifyChanges]]
    ) -> DexOrders:
        items = []
        for ref, change in changes:
            built = self.modify_order(ref, change)
            items.extend(built.orders)
        return DexOrders(DexOrdersVariant.REPLACE, items)

    def modify_condition_order(
        self,
        ref: OrderRef,
        changes: ModifyConditionChanges,
    ) -> DexOrders:
        return DexOrders(
            DexOrdersVariant.REPLACE_CONDITION,
            [self._build_condition_replace(ref, changes)],
        )

    def modify_condition_orders(
        self,
        changes: Sequence[Tuple[OrderRef, ModifyConditionChanges]],
    ) -> DexOrders:
        return DexOrders(
            DexOrdersVariant.REPLACE_CONDITION,
            [self._build_condition_replace(ref, change) for ref, change in changes],
        )

    def _build_condition_replace(
        self,
        ref: OrderRef,
        changes: ModifyConditionChanges,
    ) -> DexConditionReplaceOrder:
        basic_type, condition_type = order_type_to_basics(changes.type)
        if condition_type == ConditionType.UNSPECIFIED:
            raise ValueError(
                "modify_condition_order requires a STOP_* or TAKE_PROFIT_* type"
            )

        if basic_type == OrderBasicType.LIMIT:
            if changes.price is None:
                raise ValueError(
                    "modify_condition_order limit execution requires price"
                )
            subticks = self.ctx.resolver.to_subticks(changes.symbol, changes.price)
        else:
            if changes.price is not None:
                raise ValueError(
                    "modify_condition_order market execution must not include price"
                )
            subticks = 0

        valid_size_modes = ("fixed", "close_position")
        if changes.size_mode not in valid_size_modes:
            raise ValueError("modify_condition_order size_mode is invalid")
        if (
            changes.current_size_mode is not None
            and changes.current_size_mode not in valid_size_modes
        ):
            raise ValueError("modify_condition_order current_size_mode is invalid")
        if (
            changes.current_size_mode is not None
            and changes.current_size_mode != changes.size_mode
        ):
            raise ValueError(
                "modify_condition_order cannot change condition size mode"
            )

        if changes.size_mode == "close_position":
            if changes.size is not None:
                raise ValueError(
                    "modify_condition_order whole-position condition cannot specify size"
                )
            quantums = 0
        else:
            if changes.size is None:
                raise ValueError("modify_condition_order fixed size requires size")
            quantums = self.ctx.resolver.to_quantums(changes.symbol, changes.size)

        return DexConditionReplaceOrder(
            self.ctx.sub_address,
            replace_target_from_ref(
                ref,
                symbol_id=self.ctx.resolver.symbol_id(changes.symbol),
                symbol_type=self.ctx.symbol_type,
            ),
            quantums,
            subticks,
            self.ctx.resolver.to_subticks(changes.symbol, changes.trigger_price),
            basic_type,
            condition_type,
            _trigger_price_type(changes.trigger_price_type),
            changes.new_client_order_id,
        )

    def to_dex_tx(
        self,
        orders: DexOrders,
        nonce: int,
        created_by: CreatedBy = CreatedBy.USER,
        on_behalf_of: Optional[AccountAddress] = None,
    ) -> DexTx:
        return DexTx(nonce, orders, created_by, on_behalf_of)

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import math
import re
from enum import IntEnum
from typing import Any, List, Optional, Union

from ..core.account_address import AccountAddress
from ..bcs import MAX_I64, MAX_U32, MAX_U64, MIN_I64, Deserializer, Serializable, Serializer
from ..types.enums import (
    AccountType,
    AgentOperationVariant,
    ConditionType,
    CreatedBy,
    CrossTransferOption,
    DexOrderlessTxVariant,
    DexOrdersVariant,
    DexTransferVariant,
    DexUserConfigTxVariant,
    Grouping,
    MarginMode,
    OrderBasicType,
    OrderPositionMode,
    Side,
    StpMode,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)

# =============================================================================
# Constants
# =============================================================================

VALID_EXPONENT = -4
DEX_DEFAULT_SLIPPAGE_TOLERANCE_PPM = 100_000
_UNSET = object()


def _place_order_field_error(field: str, expectation: str) -> ValueError:
    return ValueError(f"invalid place order request: field {field} {expectation}")


def _validate_required_int_field(
    field: str,
    value: Any,
    minimum: int,
    maximum: int,
    type_name: str,
) -> int:
    if value is None:
        raise _place_order_field_error(field, f"is required and must be {type_name}")
    if isinstance(value, bool) or not isinstance(value, int):
        raise _place_order_field_error(field, f"must be {type_name}, got {value!r}")
    if value < minimum or value > maximum:
        raise _place_order_field_error(
            field,
            f"must be {type_name} in range [{minimum}, {maximum}], got {value!r}",
        )
    return value


def _validate_required_bool_field(field: str, value: Any) -> bool:
    if value is None:
        raise _place_order_field_error(field, "is required and must be bool")
    if not isinstance(value, bool):
        raise _place_order_field_error(field, f"must be bool, got {value!r}")
    return value


def _validate_required_account_address(field: str, value: Any) -> AccountAddress:
    if value is None:
        raise _place_order_field_error(field, "is required and must be AccountAddress")
    if not isinstance(value, AccountAddress):
        raise _place_order_field_error(
            field,
            f"must be AccountAddress, got {value!r}",
        )
    return value


# Canonical client_order_id: "0x" + 32 lowercase hex chars
# (16 bytes / 128 bits). The chain-side `validate_client_order_id_format`
# enforces lowercase only. The SDK does not normalize user input; malformed
# strings are rejected locally before serialization.
_CLIENT_ORDER_ID_REGEX = re.compile(r"^0x[0-9a-f]{32}$")
_CLIENT_ORDER_ID_NONE_LITERAL = "0x00000000000000000000000000000000"


def _validate_client_order_id(s: str) -> str:
    """Validate a user-supplied client_order_id and return it unchanged.

    Raises ValueError on format violation or the reserved all-zero sentinel -
    matches the Rust ``validate_client_order_id_format`` helper.
    """

    if not _CLIENT_ORDER_ID_REGEX.fullmatch(s):
        raise ValueError(
            f"client_order_id must match `^0x[0-9a-f]{{32}}$` (lowercase hex), got {s!r}"
        )
    if s == _CLIENT_ORDER_ID_NONE_LITERAL:
        raise ValueError(
            "client_order_id `0x00..00` is reserved as the absent sentinel and cannot be used"
        )
    return s


def leverage_to_im_leverage(leverage: float) -> int:
    if leverage <= 0:
        raise ValueError("leverage must be positive")
    return math.ceil(1 / leverage / 10**VALID_EXPONENT)


def im_leverage_to_leverage(im_leverage: int) -> float:
    if im_leverage <= 0:
        raise ValueError("imLeverage must be positive")
    return 1 / (im_leverage * 10**VALID_EXPONENT)


# =============================================================================
# Agent Wallet
# =============================================================================


class AgentApprove:
    name: str
    agent_address: AccountAddress
    expiry_timestamp: int  # u64

    def __init__(self, name: str, agent_address: AccountAddress, expiry_timestamp: int):
        self.name = name
        self.agent_address = agent_address
        self.expiry_timestamp = expiry_timestamp

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_str(self.name)
        self.agent_address.serialize(serializer)
        serializer.serialize_u64(self.expiry_timestamp)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AgentApprove:
        name = deserializer.deserialize_str()
        agent_address = AccountAddress.deserialize(deserializer)
        expiry_timestamp = deserializer.deserialize_u64()
        return AgentApprove(name, agent_address, expiry_timestamp)


class AgentRevoke:
    name: str

    def __init__(self, name: str):
        self.name = name

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_str(self.name)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AgentRevoke:
        return AgentRevoke(deserializer.deserialize_str())


class AgentRevokeAll:
    """End every grant this master holds.

    No fields: the operation names an end state rather than a record, so its BCS is
    the variant tag alone. Declarative and idempotent -- an account with no grants
    is a silent success with an empty write set, not a ``DexAgentNotFound``.
    """

    def serialize(self, serializer: Serializer) -> None:
        # Intentionally empty: the variant tag carries the whole operation.
        return None

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AgentRevokeAll:
        return AgentRevokeAll()


class DexAgentTx:
    nonce: int  # u64
    variant: AgentOperationVariant
    operation: Union[AgentApprove, AgentRevoke, AgentRevokeAll]

    def __init__(
        self,
        nonce: int,
        variant: AgentOperationVariant,
        operation: Union[AgentApprove, AgentRevoke, AgentRevokeAll],
    ):
        self.nonce = nonce
        self.variant = variant
        self.operation = operation

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        serializer.serialize_u32_as_uleb128(self.variant)
        self.operation.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexAgentTx:
        nonce = deserializer.deserialize_u64()
        variant = AgentOperationVariant(deserializer.deserialize_u32_from_uleb128())
        if variant == AgentOperationVariant.APPROVE:
            operation: Union[AgentApprove, AgentRevoke] = AgentApprove.deserialize(
                deserializer
            )
        elif variant == AgentOperationVariant.REVOKE:
            operation = AgentRevoke.deserialize(deserializer)
        elif variant == AgentOperationVariant.REVOKE_ALL:
            operation = AgentRevokeAll.deserialize(deserializer)
        else:
            raise ValueError(f"Unknown AgentOperationVariant: {variant}")
        return DexAgentTx(nonce, variant, operation)

    @staticmethod
    def revoke_all(nonce: int) -> DexAgentTx:
        """Revoke every grant: the variant and its empty operation always travel
        together."""
        return DexAgentTx(nonce, AgentOperationVariant.REVOKE_ALL, AgentRevokeAll())


# =============================================================================
# DEX Order Types
# =============================================================================


class DexPlaceOrder:
    sub_address: AccountAddress
    symbol_id: int  # u32
    symbol_type: SymbolType
    side: Side
    quantums: int  # i64
    subticks: int  # u64
    trigger_subticks: int  # u64
    order_basic_type: OrderBasicType
    time_in_force: TimeInForce
    condition_type: ConditionType
    trigger_price_type: TriggerPriceType
    target_order_id: int  # u64
    reduce_only: bool
    position_mode: OrderPositionMode
    # Slippage tolerance in PPM; only validated on-chain for market orders.
    slippage_tolerance_ppm: int  # u32
    # Optional user-supplied client_order_id ("0x" + 32 lowercase hex chars).
    # Format when set: "0x" + 32 lowercase hex chars (16 bytes / 128 bits).
    # None = no client_order_id set.
    #
    # Uniqueness scope: globally unique within the signer `address` for OPEN
    # orders (across all sub_addresses, all symbol_ids); released when the
    # order leaves OPEN. The chain rejects collisions with
    # DUPLICATE_CLIENT_ORDER_ID and unknown ids on cancel with
    # CLIENT_ORDER_ID_NOT_FOUND.
    client_order_id: Optional[str]  # Option<String>
    # Self-Trade Prevention mode. Default: EXPIRE_MAKER (cancel maker, taker continues).
    stp_mode: StpMode

    def __init__(
        self,
        sub_address: AccountAddress,
        symbol_id: int,
        symbol_type: SymbolType,
        side: Side,
        quantums: int,
        subticks: int,
        trigger_subticks: int,
        order_basic_type: OrderBasicType,
        time_in_force: TimeInForce,
        condition_type: ConditionType,
        trigger_price_type: TriggerPriceType,
        target_order_id: int,
        reduce_only: bool,
        position_mode: OrderPositionMode,
        slippage_tolerance_ppm: Any = _UNSET,
        client_order_id: Optional[str] = None,
        stp_mode: StpMode = StpMode.EXPIRE_MAKER,
    ):
        slippage_value = (
            DEX_DEFAULT_SLIPPAGE_TOLERANCE_PPM
            if slippage_tolerance_ppm is _UNSET
            else slippage_tolerance_ppm
        )
        self.sub_address = _validate_required_account_address(
            "sub_address", sub_address
        )
        self.symbol_id = _validate_required_int_field(
            "symbol_id", symbol_id, 0, MAX_U32, "u32"
        )
        self.symbol_type = symbol_type
        self.side = side
        self.quantums = _validate_required_int_field(
            "quantums", quantums, MIN_I64, MAX_I64, "i64"
        )
        self.subticks = _validate_required_int_field(
            "subticks", subticks, 0, MAX_U64, "u64"
        )
        self.trigger_subticks = _validate_required_int_field(
            "trigger_subticks", trigger_subticks, 0, MAX_U64, "u64"
        )
        self.order_basic_type = order_basic_type
        self.time_in_force = time_in_force
        self.condition_type = condition_type
        self.trigger_price_type = trigger_price_type
        self.target_order_id = _validate_required_int_field(
            "target_order_id", target_order_id, 0, MAX_U64, "u64"
        )
        self.reduce_only = _validate_required_bool_field("reduce_only", reduce_only)
        self.position_mode = position_mode
        self.slippage_tolerance_ppm = _validate_required_int_field(
            "slippage_tolerance_ppm", slippage_value, 0, MAX_U32, "u32"
        )
        self.client_order_id = (
            None
            if client_order_id is None
            else _validate_client_order_id(client_order_id)
        )
        self.stp_mode = stp_mode

    def serialize(self, serializer: Serializer) -> None:
        self.sub_address.serialize(serializer)
        serializer.serialize_u32(self.symbol_id)
        serializer.serialize_u8(self.symbol_type)
        serializer.serialize_u8(self.side)
        serializer.serialize_i64(self.quantums)
        serializer.serialize_u64(self.subticks)
        serializer.serialize_u64(self.trigger_subticks)
        serializer.serialize_u8(self.order_basic_type)
        serializer.serialize_u8(self.time_in_force)
        serializer.serialize_u8(self.condition_type)
        serializer.serialize_u8(self.trigger_price_type)
        serializer.serialize_u64(self.target_order_id)
        serializer.serialize_bool(self.reduce_only)
        serializer.serialize_u8(self.position_mode)
        serializer.serialize_u32(self.slippage_tolerance_ppm)
        # BCS Option<String>: 0x00 = None; 0x01 + ULEB128 length + UTF-8 bytes = Some.
        if self.client_order_id is None:
            serializer.serialize_bool(False)
        else:
            serializer.serialize_bool(True)
            serializer.serialize_str(self.client_order_id)
        serializer.serialize_u8(self.stp_mode)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexPlaceOrder:
        order = DexPlaceOrder(
            sub_address=AccountAddress.deserialize(deserializer),
            symbol_id=deserializer.deserialize_u32(),
            symbol_type=SymbolType(deserializer.deserialize_u8()),
            side=Side(deserializer.deserialize_u8()),
            quantums=deserializer.deserialize_i64(),
            subticks=deserializer.deserialize_u64(),
            trigger_subticks=deserializer.deserialize_u64(),
            order_basic_type=OrderBasicType(deserializer.deserialize_u8()),
            time_in_force=TimeInForce(deserializer.deserialize_u8()),
            condition_type=ConditionType(deserializer.deserialize_u8()),
            trigger_price_type=TriggerPriceType(deserializer.deserialize_u8()),
            target_order_id=deserializer.deserialize_u64(),
            reduce_only=deserializer.deserialize_bool(),
            position_mode=OrderPositionMode(deserializer.deserialize_u8()),
            slippage_tolerance_ppm=deserializer.deserialize_u32(),
        )
        if deserializer.deserialize_bool():
            order.client_order_id = deserializer.deserialize_str()
        order.stp_mode = StpMode(deserializer.deserialize_u8())
        return order


class DexPlaceOrders:
    orders: List[DexPlaceOrder]
    grouping: Grouping

    def __init__(self, orders: List[DexPlaceOrder], grouping: Grouping = Grouping.NA):
        self._validate_orders(orders, grouping)
        self.orders = orders
        self.grouping = grouping

    @staticmethod
    def _is_tpsl_order(order: DexPlaceOrder) -> bool:
        return order.condition_type in (
            ConditionType.TAKE_PROFIT,
            ConditionType.STOP_LOSS,
        )

    @staticmethod
    def _validate_orders(orders: List[DexPlaceOrder], grouping: Grouping) -> None:
        if not orders:
            raise ValueError("DexPlaceOrders requires at least one order")

        tp_count = sum(
            1 for order in orders if order.condition_type == ConditionType.TAKE_PROFIT
        )
        sl_count = sum(
            1 for order in orders if order.condition_type == ConditionType.STOP_LOSS
        )

        if grouping == Grouping.NA:
            return

        if grouping == Grouping.NORMAL_TPSL:
            if len(orders) > 3:
                raise ValueError(
                    f"Grouping.NORMAL_TPSL allows at most 3 orders, got {len(orders)}"
                )
            if DexPlaceOrders._is_tpsl_order(orders[0]):
                raise ValueError(
                    "Grouping.NORMAL_TPSL requires the first order to be a normal order "
                    "(condition_type = UNSPECIFIED)"
                )
            if tp_count > 1:
                raise ValueError(
                    f"Grouping.NORMAL_TPSL allows at most 1 TAKE_PROFIT order, got {tp_count}"
                )
            if sl_count > 1:
                raise ValueError(
                    f"Grouping.NORMAL_TPSL allows at most 1 STOP_LOSS order, got {sl_count}"
                )
            if any(
                order.order_basic_type != OrderBasicType.MARKET for order in orders[1:]
            ):
                raise ValueError(
                    "Grouping.NORMAL_TPSL TP/SL child orders must use market execution"
                )
            return

        if grouping == Grouping.POSITION_TPSL:
            if len(orders) > 2:
                raise ValueError(
                    f"Grouping.POSITION_TPSL allows at most 2 orders, got {len(orders)}"
                )
            if tp_count > 1:
                raise ValueError(
                    f"Grouping.POSITION_TPSL allows at most 1 TAKE_PROFIT order, got {tp_count}"
                )
            if sl_count > 1:
                raise ValueError(
                    f"Grouping.POSITION_TPSL allows at most 1 STOP_LOSS order, got {sl_count}"
                )
            if any(not DexPlaceOrders._is_tpsl_order(order) for order in orders):
                raise ValueError(
                    "Grouping.POSITION_TPSL only allows TAKE_PROFIT and STOP_LOSS orders"
                )
            if any(
                order.quantums == 0
                and not order.reduce_only
                and order.side not in (Side.CLOSEALL_LONG, Side.CLOSEALL_SHORT)
                for order in orders
            ):
                raise ValueError("whole-position orders require reduce_only = true")
            return

        raise ValueError(f"Unknown grouping type: {grouping}")

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(len(self.orders))
        for order in self.orders:
            order.serialize(serializer)
        serializer.serialize_u32_as_uleb128(self.grouping)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexPlaceOrders:
        length = deserializer.deserialize_u32_from_uleb128()
        orders = [DexPlaceOrder.deserialize(deserializer) for _ in range(length)]
        grouping = Grouping(deserializer.deserialize_u32_from_uleb128())
        return DexPlaceOrders(orders, grouping)


class DexCancelTargetKind(IntEnum):
    """Discriminator for DexCancelTarget (BCS enum tag, uleb128-encoded)."""

    ORDER_ID = 0
    CLIENT_ORDER_ID = 1


class DexCancelTarget:
    """Selects which key a cancel applies to.

    One-of semantics:
      - kind == ORDER_ID:         order_id is populated
      - kind == CLIENT_ORDER_ID:  client_order_id (string) is populated
                                  (scope is account-global, no symbol_id needed)
    """

    kind: DexCancelTargetKind
    order_id: int  # u64, used when kind == ORDER_ID
    client_order_id: str  # "0x" + 32 lowercase hex; used when kind == CLIENT_ORDER_ID

    def __init__(
        self,
        kind: DexCancelTargetKind,
        order_id: int = 0,
        client_order_id: str = "",
    ):
        self.kind = kind
        self.order_id = order_id
        self.client_order_id = client_order_id

    @staticmethod
    def by_order_id(target_order_id: int) -> DexCancelTarget:
        """Cancel a single order by its chain-assigned order_id."""
        return DexCancelTarget(
            kind=DexCancelTargetKind.ORDER_ID,
            order_id=target_order_id,
        )

    @staticmethod
    def by_client_order_id(client_order_id: str) -> DexCancelTarget:
        """Cancel the single OPEN order under the signer `address` carrying
        `client_order_id`. Scope is account-global, no symbol_id
        is required. Format-validated as provided.
        """
        return DexCancelTarget(
            kind=DexCancelTargetKind.CLIENT_ORDER_ID,
            client_order_id=_validate_client_order_id(client_order_id),
        )

    def serialize(self, serializer: Serializer) -> None:
        # BCS enum: variant tag (uleb128) + variant payload.
        serializer.serialize_u32_as_uleb128(int(self.kind))
        if self.kind == DexCancelTargetKind.ORDER_ID:
            serializer.serialize_u64(self.order_id)
        elif self.kind == DexCancelTargetKind.CLIENT_ORDER_ID:
            serializer.serialize_str(self.client_order_id)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexCancelTarget:
        tag = deserializer.deserialize_u32_from_uleb128()
        kind = DexCancelTargetKind(tag)
        if kind == DexCancelTargetKind.ORDER_ID:
            return DexCancelTarget(kind=kind, order_id=deserializer.deserialize_u64())
        if kind == DexCancelTargetKind.CLIENT_ORDER_ID:
            return DexCancelTarget(
                kind=kind,
                client_order_id=deserializer.deserialize_str(),
            )
        raise ValueError(f"Unknown DexCancelTargetKind tag: {tag}")


class DexCancelOrder:
    sub_address: AccountAddress
    target: DexCancelTarget
    symbol_type: SymbolType

    def __init__(
        self,
        sub_address: AccountAddress,
        target: DexCancelTarget,
        symbol_type: SymbolType,
    ):
        self.sub_address = sub_address
        self.target = target
        self.symbol_type = symbol_type

    @staticmethod
    def by_order_id(
        sub_address: AccountAddress,
        target_order_id: int,
        symbol_type: SymbolType,
    ) -> DexCancelOrder:
        return DexCancelOrder(
            sub_address=sub_address,
            target=DexCancelTarget.by_order_id(target_order_id),
            symbol_type=symbol_type,
        )

    @staticmethod
    def by_client_order_id(
        sub_address: AccountAddress,
        client_order_id: str,
        symbol_type: SymbolType,
    ) -> DexCancelOrder:
        """Cancel the single OPEN order under the signer `address` carrying
        `client_order_id` (account-global scope: no
        `symbol_id` is needed).
        """
        return DexCancelOrder(
            sub_address=sub_address,
            target=DexCancelTarget.by_client_order_id(client_order_id),
            symbol_type=symbol_type,
        )

    def serialize(self, serializer: Serializer) -> None:
        self.sub_address.serialize(serializer)
        self.target.serialize(serializer)
        serializer.serialize_u8(self.symbol_type)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexCancelOrder:
        return DexCancelOrder(
            sub_address=AccountAddress.deserialize(deserializer),
            target=DexCancelTarget.deserialize(deserializer),
            symbol_type=SymbolType(deserializer.deserialize_u8()),
        )


class DexReplaceTargetKind(IntEnum):
    ORDER_ID = 0
    CLIENT_ORDER_ID = 1
    ORDER_ID_WITH_CONTEXT = 2


class DexReplaceTarget:
    kind: DexReplaceTargetKind
    order_id: int
    client_order_id: str
    symbol_id: int
    symbol_type: SymbolType

    def __init__(
        self,
        kind: DexReplaceTargetKind,
        order_id: int = 0,
        client_order_id: str = "",
        symbol_id: int = 0,
        symbol_type: SymbolType = SymbolType.UNSPECIFIED,
    ):
        self.kind = kind
        self.order_id = order_id
        self.client_order_id = client_order_id
        self.symbol_id = symbol_id
        self.symbol_type = symbol_type

    @staticmethod
    def by_order_id(target_order_id: int) -> DexReplaceTarget:
        """Build the legacy tag-0 target."""
        return DexReplaceTarget(
            kind=DexReplaceTargetKind.ORDER_ID, order_id=target_order_id
        )

    @staticmethod
    def by_order_id_with_context(
        target_order_id: int,
        symbol_id: int,
        symbol_type: SymbolType,
    ) -> DexReplaceTarget:
        return DexReplaceTarget(
            kind=DexReplaceTargetKind.ORDER_ID_WITH_CONTEXT,
            order_id=target_order_id,
            symbol_id=symbol_id,
            symbol_type=symbol_type,
        )

    @staticmethod
    def by_client_order_id(client_order_id: str) -> DexReplaceTarget:
        return DexReplaceTarget(
            kind=DexReplaceTargetKind.CLIENT_ORDER_ID,
            client_order_id=_validate_client_order_id(client_order_id),
        )

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(int(self.kind))
        if self.kind == DexReplaceTargetKind.ORDER_ID:
            serializer.serialize_u64(self.order_id)
        elif self.kind == DexReplaceTargetKind.CLIENT_ORDER_ID:
            serializer.serialize_str(self.client_order_id)
        elif self.kind == DexReplaceTargetKind.ORDER_ID_WITH_CONTEXT:
            serializer.serialize_u64(self.order_id)
            serializer.serialize_u32(self.symbol_id)
            serializer.serialize_u32_as_uleb128(int(self.symbol_type))

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexReplaceTarget:
        tag = deserializer.deserialize_u32_from_uleb128()
        kind = DexReplaceTargetKind(tag)
        if kind == DexReplaceTargetKind.ORDER_ID:
            return DexReplaceTarget(kind=kind, order_id=deserializer.deserialize_u64())
        if kind == DexReplaceTargetKind.CLIENT_ORDER_ID:
            return DexReplaceTarget(kind=kind, client_order_id=deserializer.deserialize_str())
        if kind == DexReplaceTargetKind.ORDER_ID_WITH_CONTEXT:
            return DexReplaceTarget(
                kind=kind,
                order_id=deserializer.deserialize_u64(),
                symbol_id=deserializer.deserialize_u32(),
                symbol_type=SymbolType(deserializer.deserialize_u32_from_uleb128()),
            )
        raise ValueError(f"Unknown DexReplaceTargetKind tag: {tag}")


class DexReplaceOrder:
    sub_address: AccountAddress
    target: DexReplaceTarget
    quantums: Optional[int]  # Option<i64>
    subticks: Optional[int]  # Option<u64>
    new_client_order_id: Optional[str]

    def __init__(
        self,
        sub_address: AccountAddress,
        target: DexReplaceTarget,
        quantums: Optional[int] = None,
        subticks: Optional[int] = None,
        new_client_order_id: Optional[str] = None,
    ):
        self.sub_address = sub_address
        self.target = target
        self.quantums = quantums
        self.subticks = subticks
        self.new_client_order_id = (
            None
            if new_client_order_id is None
            else _validate_client_order_id(new_client_order_id)
        )

    @staticmethod
    def by_order_id(
        sub_address: AccountAddress,
        target_order_id: int,
        *,
        symbol_id: int,
        symbol_type: SymbolType,
        quantums: Optional[int] = None,
        subticks: Optional[int] = None,
        new_client_order_id: Optional[str] = None,
    ) -> DexReplaceOrder:
        return DexReplaceOrder(
            sub_address,
            DexReplaceTarget.by_order_id_with_context(
                target_order_id,
                symbol_id,
                symbol_type,
            ),
            quantums,
            subticks,
            new_client_order_id,
        )

    @staticmethod
    def by_order_id_with_context(
        sub_address: AccountAddress,
        target_order_id: int,
        symbol_id: int,
        symbol_type: SymbolType,
        quantums: int,
        subticks: int,
        trigger_subticks: int,
        order_basic_type: OrderBasicType,
        condition_type: ConditionType,
        trigger_price_type: TriggerPriceType,
        new_client_order_id: Optional[str] = None,
    ) -> DexConditionReplaceOrder:
        return DexConditionReplaceOrder(
            sub_address,
            DexReplaceTarget.by_order_id_with_context(
                target_order_id,
                symbol_id,
                symbol_type,
            ),
            quantums,
            subticks,
            trigger_subticks,
            order_basic_type,
            condition_type,
            trigger_price_type,
            new_client_order_id,
        )

    @staticmethod
    def by_client_order_id(
        sub_address: AccountAddress,
        target_client_order_id: str,
        quantums: Optional[int] = None,
        subticks: Optional[int] = None,
        new_client_order_id: Optional[str] = None,
    ) -> DexReplaceOrder:
        return DexReplaceOrder(
            sub_address,
            DexReplaceTarget.by_client_order_id(target_client_order_id),
            quantums,
            subticks,
            new_client_order_id,
        )

    def serialize(self, serializer: Serializer) -> None:
        self.sub_address.serialize(serializer)
        self.target.serialize(serializer)
        if self.quantums is None:
            serializer.serialize_bool(False)
        else:
            serializer.serialize_bool(True)
            serializer.serialize_i64(self.quantums)
        if self.subticks is None:
            serializer.serialize_bool(False)
        else:
            serializer.serialize_bool(True)
            serializer.serialize_u64(self.subticks)
        if self.new_client_order_id is None:
            serializer.serialize_bool(False)
        else:
            serializer.serialize_bool(True)
            serializer.serialize_str(self.new_client_order_id)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexReplaceOrder:
        return DexReplaceOrder(
            sub_address=AccountAddress.deserialize(deserializer),
            target=DexReplaceTarget.deserialize(deserializer),
            quantums=deserializer.deserialize_i64() if deserializer.deserialize_bool() else None,
            subticks=deserializer.deserialize_u64() if deserializer.deserialize_bool() else None,
            new_client_order_id=deserializer.deserialize_str() if deserializer.deserialize_bool() else None,
        )


class DexConditionReplaceOrder:
    sub_address: AccountAddress
    target: DexReplaceTarget
    quantums: int
    subticks: int
    trigger_subticks: int
    order_basic_type: OrderBasicType
    condition_type: ConditionType
    trigger_price_type: TriggerPriceType
    new_client_order_id: Optional[str]

    def __init__(
        self,
        sub_address: AccountAddress,
        target: DexReplaceTarget,
        quantums: int,
        subticks: int,
        trigger_subticks: int,
        order_basic_type: OrderBasicType,
        condition_type: ConditionType,
        trigger_price_type: TriggerPriceType,
        new_client_order_id: Optional[str] = None,
    ):
        if trigger_subticks == 0:
            raise ValueError("condition replace trigger_subticks must be non-zero")
        if condition_type == ConditionType.UNSPECIFIED:
            raise ValueError("condition replace condition_type must be specified")
        if order_basic_type == OrderBasicType.MARKET and subticks != 0:
            raise ValueError(
                "condition replace market execution must not specify subticks"
            )
        if order_basic_type == OrderBasicType.LIMIT and subticks == 0:
            raise ValueError("condition replace limit execution must specify subticks")
        if order_basic_type == OrderBasicType.UNSPECIFIED:
            raise ValueError(
                "condition replace order_basic_type must be MARKET or LIMIT"
            )

        self.sub_address = sub_address
        self.target = target
        self.quantums = quantums
        self.subticks = subticks
        self.trigger_subticks = trigger_subticks
        self.order_basic_type = order_basic_type
        self.condition_type = condition_type
        self.trigger_price_type = trigger_price_type
        self.new_client_order_id = (
            None
            if new_client_order_id is None
            else _validate_client_order_id(new_client_order_id)
        )

    @staticmethod
    def by_order_id(
        sub_address: AccountAddress,
        target_order_id: int,
        quantums: int,
        subticks: int,
        trigger_subticks: int,
        order_basic_type: OrderBasicType,
        condition_type: ConditionType,
        trigger_price_type: TriggerPriceType,
        new_client_order_id: Optional[str] = None,
    ) -> DexConditionReplaceOrder:
        return DexConditionReplaceOrder(
            sub_address,
            DexReplaceTarget.by_order_id(target_order_id),
            quantums,
            subticks,
            trigger_subticks,
            order_basic_type,
            condition_type,
            trigger_price_type,
            new_client_order_id,
        )

    @staticmethod
    def by_client_order_id(
        sub_address: AccountAddress,
        target_client_order_id: str,
        quantums: int,
        subticks: int,
        trigger_subticks: int,
        order_basic_type: OrderBasicType,
        condition_type: ConditionType,
        trigger_price_type: TriggerPriceType,
        new_client_order_id: Optional[str] = None,
    ) -> DexConditionReplaceOrder:
        return DexConditionReplaceOrder(
            sub_address,
            DexReplaceTarget.by_client_order_id(target_client_order_id),
            quantums,
            subticks,
            trigger_subticks,
            order_basic_type,
            condition_type,
            trigger_price_type,
            new_client_order_id,
        )

    def serialize(self, serializer: Serializer) -> None:
        self.sub_address.serialize(serializer)
        self.target.serialize(serializer)
        serializer.serialize_i64(self.quantums)
        serializer.serialize_u64(self.subticks)
        serializer.serialize_u64(self.trigger_subticks)
        serializer.serialize_u8(self.order_basic_type)
        serializer.serialize_u8(self.condition_type)
        serializer.serialize_u8(self.trigger_price_type)
        serializer.serialize_option_str(self.new_client_order_id)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexConditionReplaceOrder:
        return DexConditionReplaceOrder(
            sub_address=AccountAddress.deserialize(deserializer),
            target=DexReplaceTarget.deserialize(deserializer),
            quantums=deserializer.deserialize_i64(),
            subticks=deserializer.deserialize_u64(),
            trigger_subticks=deserializer.deserialize_u64(),
            order_basic_type=OrderBasicType(deserializer.deserialize_u8()),
            condition_type=ConditionType(deserializer.deserialize_u8()),
            trigger_price_type=TriggerPriceType(deserializer.deserialize_u8()),
            new_client_order_id=deserializer.deserialize_str() if deserializer.deserialize_bool() else None,
        )


# =============================================================================
# DexOrders - variant container
# =============================================================================


class DexOrders:
    variant: DexOrdersVariant
    orders: Union[
        List[DexPlaceOrders],
        List[DexCancelOrder],
        List[DexReplaceOrder],
        List[DexConditionReplaceOrder],
    ]

    def __init__(
        self,
        variant: DexOrdersVariant,
        orders: Optional[
            Union[
                List[DexPlaceOrders],
                List[DexCancelOrder],
                List[DexReplaceOrder],
                List[DexConditionReplaceOrder],
            ]
        ] = None,
    ):
        if orders is None:
            orders = []
        if variant == DexOrdersVariant.PLACE:
            self._validate_place_order_client_order_ids(orders)  # type: ignore[arg-type]
        self.variant = variant
        self.orders = orders

    @classmethod
    def replace_maker_only(cls, orders: List[DexReplaceOrder]) -> DexOrders:
        """An amend whose replacement order is rejected rather than filled if it would cross.

        Use it for any amend not meant to take liquidity: the node packs it on arrival, where a
        plain replace waits out the taker delay first. The guarantee is the engine's -- asking for
        this shape and then pricing through the book costs the amend, never a fill. On the
        cancel-and-replace path (a new price, a larger size, or a new client order id) the target
        is already cancelled by the time the replacement is matched, so a crossing replacement
        leaves neither order.
        """
        return cls(DexOrdersVariant.REPLACE_MAKER_ONLY, orders)

    @classmethod
    def noop(cls) -> DexOrders:
        """The in-flight cancel: no orders, and consuming the nonce is the whole effect.

        Submit it with the nonce of an order that may not have landed yet, and the two race for
        that nonce; exactly one wins and the loser is discarded with no effect on chain. A
        committed noop is the receipt -- it holds the nonce long enough that the order it cancels
        can never be admitted again. An order already resting on the book needs a cancel naming it
        instead: by then the engine knows the order and the nonce is no help.
        """
        return cls(DexOrdersVariant.NOOP)

    @staticmethod
    def _validate_place_order_client_order_ids(
        groups: List[DexPlaceOrders],
    ) -> None:
        seen = set()
        for group in groups:
            for order in group.orders:
                if order.client_order_id is None:
                    continue
                client_order_id = _validate_client_order_id(order.client_order_id)
                key = (order.sub_address.to_string_long(), client_order_id)
                if key in seen:
                    raise ValueError(
                        "duplicate client_order_id "
                        f"{client_order_id!r} in place batch for sub_address "
                        f"{order.sub_address.to_string_long()}"
                    )
                seen.add(key)

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u8(self.variant)
        if self.variant == DexOrdersVariant.NOOP:
            # The tag is the whole payload. Writing an empty vector here would append a trailing
            # zero byte the node does not read, and the transaction would not deserialise.
            return
        serializer.serialize_u32_as_uleb128(len(self.orders))
        for order in self.orders:
            order.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexOrders:
        variant = DexOrdersVariant(deserializer.deserialize_u8())
        if variant == DexOrdersVariant.NOOP:
            return DexOrders(variant)
        length = deserializer.deserialize_u32_from_uleb128()
        if variant == DexOrdersVariant.PLACE:
            orders_list: list = [
                DexPlaceOrders.deserialize(deserializer) for _ in range(length)
            ]
        elif variant == DexOrdersVariant.CANCEL:
            orders_list = [
                DexCancelOrder.deserialize(deserializer) for _ in range(length)
            ]
        elif variant == DexOrdersVariant.REPLACE:
            orders_list = [
                DexReplaceOrder.deserialize(deserializer) for _ in range(length)
            ]
        elif variant == DexOrdersVariant.REPLACE_MAKER_ONLY:
            orders_list = [
                DexReplaceOrder.deserialize(deserializer) for _ in range(length)
            ]
        elif variant == DexOrdersVariant.REPLACE_CONDITION:
            orders_list = [
                DexConditionReplaceOrder.deserialize(deserializer)
                for _ in range(length)
            ]
        else:
            raise ValueError(f"Unknown DexOrders variant: {variant}")
        return DexOrders(variant, orders_list)


# =============================================================================
# DexTx
# =============================================================================


class DexTx:
    nonce: int  # u64
    orders: DexOrders
    created_by: CreatedBy
    on_behalf_of: Optional[AccountAddress]

    def __init__(
        self,
        nonce: int,
        orders: DexOrders,
        created_by: CreatedBy,
        on_behalf_of: Optional[AccountAddress] = None,
    ):
        self.nonce = nonce
        self.orders = orders
        self.created_by = created_by
        self.on_behalf_of = on_behalf_of

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.orders.serialize(serializer)
        serializer.serialize_u8(self.created_by)
        serializer.serialize_option(self.on_behalf_of)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexTx:
        nonce = deserializer.deserialize_u64()
        orders = DexOrders.deserialize(deserializer)
        created_by = CreatedBy(deserializer.deserialize_u8())
        has_on_behalf_of = deserializer.deserialize_bool()
        on_behalf_of = (
            AccountAddress.deserialize(deserializer) if has_on_behalf_of else None
        )
        return DexTx(nonce, orders, created_by, on_behalf_of)


# =============================================================================
# Transfer Types
# =============================================================================


class InternalTransferItem:
    from_subaddress: AccountAddress
    to_subaddress: AccountAddress
    asset_id: int  # u32
    amount: int  # u64
    account_type: AccountType

    def __init__(
        self,
        from_subaddress: AccountAddress,
        to_subaddress: AccountAddress,
        asset_id: int,
        amount: int,
        account_type: AccountType,
    ):
        self.from_subaddress = from_subaddress
        self.to_subaddress = to_subaddress
        self.asset_id = asset_id
        self.amount = amount
        self.account_type = account_type

    def serialize(self, serializer: Serializer) -> None:
        self.from_subaddress.serialize(serializer)
        self.to_subaddress.serialize(serializer)
        serializer.serialize_u32(self.asset_id)
        serializer.serialize_u64(self.amount)
        serializer.serialize_u8(self.account_type)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> InternalTransferItem:
        return InternalTransferItem(
            from_subaddress=AccountAddress.deserialize(deserializer),
            to_subaddress=AccountAddress.deserialize(deserializer),
            asset_id=deserializer.deserialize_u32(),
            amount=deserializer.deserialize_u64(),
            account_type=AccountType(deserializer.deserialize_u8()),
        )


class AccountTransferItem:
    to_account: AccountAddress
    asset_id: int  # u32
    amount: int  # u64
    account_type: AccountType

    def __init__(
        self,
        to_account: AccountAddress,
        asset_id: int,
        amount: int,
        account_type: AccountType,
    ):
        self.to_account = to_account
        self.asset_id = asset_id
        self.amount = amount
        self.account_type = account_type

    def serialize(self, serializer: Serializer) -> None:
        self.to_account.serialize(serializer)
        serializer.serialize_u32(self.asset_id)
        serializer.serialize_u64(self.amount)
        serializer.serialize_u8(self.account_type)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AccountTransferItem:
        return AccountTransferItem(
            to_account=AccountAddress.deserialize(deserializer),
            asset_id=deserializer.deserialize_u32(),
            amount=deserializer.deserialize_u64(),
            account_type=AccountType(deserializer.deserialize_u8()),
        )


class CrossTransferItem:
    to_account: AccountAddress
    asset_id: int  # u32
    amount: int  # u64
    account_type: AccountType

    def __init__(
        self,
        to_account: AccountAddress,
        asset_id: int,
        amount: int,
        account_type: AccountType,
    ):
        self.to_account = to_account
        self.asset_id = asset_id
        self.amount = amount
        self.account_type = account_type

    def serialize(self, serializer: Serializer) -> None:
        self.to_account.serialize(serializer)
        serializer.serialize_u32(self.asset_id)
        serializer.serialize_u64(self.amount)
        serializer.serialize_u8(self.account_type)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> CrossTransferItem:
        return CrossTransferItem(
            to_account=AccountAddress.deserialize(deserializer),
            asset_id=deserializer.deserialize_u32(),
            amount=deserializer.deserialize_u64(),
            account_type=AccountType(deserializer.deserialize_u8()),
        )


class BridgeSignature:
    r: bytes
    s: bytes
    v: int  # u8

    def __init__(self, r: bytes, s: bytes, v: int):
        if len(r) != 32:
            raise ValueError("BridgeSignature r must be exactly 32 bytes")
        if len(s) != 32:
            raise ValueError("BridgeSignature s must be exactly 32 bytes")
        if v < 0 or v > 255:
            raise ValueError("BridgeSignature v must fit into u8")
        self.r = r
        self.s = s
        self.v = v

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_fixed_bytes(self.r)
        serializer.serialize_fixed_bytes(self.s)
        serializer.serialize_u8(self.v)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> BridgeSignature:
        return BridgeSignature(
            r=deserializer.deserialize_fixed_bytes(32),
            s=deserializer.deserialize_fixed_bytes(32),
            v=deserializer.deserialize_u8(),
        )


class MultiSigProof:
    """The n/m multisig carried alongside a privileged DexSystemConfig operation.

    Covers the listing and fee committees, and the bridge's own signer set when it
    authorises its own rotation. Mirrors
    ``intention_types::transaction::dex_sys_config::MultiSigProof``.

    The chain's ``EvmSignature`` has the same layout as :class:`BridgeSignature`
    here (``r[32] || s[32] || v``), so that type is reused rather than duplicated.

    This SDK models no operation that needs a proof. The type lives here because
    the proof rides the :class:`DexOrderlessTx` envelope, which this module owns;
    whoever builds the operation builds the proof to go with it.
    """

    op_digest: bytes
    expires_at_secs: int  # u64
    signatures: List[BridgeSignature]

    def __init__(
        self,
        op_digest: bytes,
        expires_at_secs: int,
        signatures: List[BridgeSignature],
    ):
        if len(op_digest) != 32:
            raise ValueError("MultiSigProof op_digest must be exactly 32 bytes")
        if expires_at_secs < 0 or expires_at_secs > MAX_U64:
            raise ValueError("MultiSigProof expires_at_secs must fit into u64")
        self.op_digest = op_digest
        self.expires_at_secs = expires_at_secs
        self.signatures = signatures

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_fixed_bytes(self.op_digest)
        # expires_at_secs sits BETWEEN op_digest and signatures, which is the only
        # position the chain reads it from. Omitting it does not degrade
        # gracefully: the chain reads the signature vector's length prefix as this
        # u64's first byte and rejects the transaction with an error naming
        # neither the field nor the side that differs.
        serializer.serialize_u64(self.expires_at_secs)
        serializer.serialize_u32_as_uleb128(len(self.signatures))
        for signature in self.signatures:
            signature.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> MultiSigProof:
        op_digest = deserializer.deserialize_fixed_bytes(32)
        expires_at_secs = deserializer.deserialize_u64()
        count = deserializer.deserialize_u32_from_uleb128()
        signatures = [BridgeSignature.deserialize(deserializer) for _ in range(count)]
        return MultiSigProof(op_digest, expires_at_secs, signatures)


class BridgeProof:
    msg_id: bytes
    signer_epoch: int  # u64
    signatures: List[BridgeSignature]

    def __init__(
        self, msg_id: bytes, signer_epoch: int, signatures: List[BridgeSignature]
    ):
        if len(msg_id) != 32:
            raise ValueError("BridgeProof msg_id must be exactly 32 bytes")
        self.msg_id = msg_id
        self.signer_epoch = signer_epoch
        self.signatures = signatures

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_fixed_bytes(self.msg_id)
        serializer.serialize_u64(self.signer_epoch)
        serializer.serialize_u32_as_uleb128(len(self.signatures))
        for signature in self.signatures:
            signature.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> BridgeProof:
        msg_id = deserializer.deserialize_fixed_bytes(32)
        signer_epoch = deserializer.deserialize_u64()
        length = deserializer.deserialize_u32_from_uleb128()
        signatures = [BridgeSignature.deserialize(deserializer) for _ in range(length)]
        return BridgeProof(
            msg_id=msg_id, signer_epoch=signer_epoch, signatures=signatures
        )


class DexTransferTx:
    """Note: serialization order is variant -> nonce -> items (non-intuitive)."""

    nonce: int  # u64
    variant: DexTransferVariant
    payload: Union[
        List[InternalTransferItem],
        List[AccountTransferItem],
        List[CrossTransferItem],
    ]
    option: Optional[CrossTransferOption]
    bridge_proof: Optional[BridgeProof]

    def __init__(
        self,
        nonce: int,
        variant: DexTransferVariant,
        payload: Union[
            List[InternalTransferItem],
            List[AccountTransferItem],
            List[CrossTransferItem],
        ],
        option: Optional[CrossTransferOption] = None,
        bridge_proof: Optional[BridgeProof] = None,
    ):
        self.nonce = nonce
        self.variant = variant
        self.payload = payload
        self.option = option
        self.bridge_proof = bridge_proof

    def serialize(self, serializer: Serializer) -> None:
        # Note: variant first, then nonce (matches TS SDK order)
        serializer.serialize_u32_as_uleb128(self.variant)
        serializer.serialize_u64(self.nonce)
        if self.variant == DexTransferVariant.CROSS_TRANSFER:
            if self.option is None:
                raise ValueError("Cross-transfer requires a transaction-level option")
            serializer.serialize_u8(self.option)
            serializer.serialize_u32_as_uleb128(len(self.payload))
            for item in self.payload:
                item.serialize(serializer)
            serializer.serialize_option(self.bridge_proof)
        elif self.variant == DexTransferVariant.FAUCET_MINT:
            serializer.serialize_u32_as_uleb128(len(self.payload))
            for item in self.payload:
                item.serialize(serializer)
        elif self.variant in (
            DexTransferVariant.INTERNAL_TRANSFER,
            DexTransferVariant.ACCOUNT_TRANSFER,
        ):
            serializer.serialize_u32_as_uleb128(len(self.payload))
            for item in self.payload:
                item.serialize(serializer)
        else:
            raise ValueError(f"Unknown DexTransferTx variant: {self.variant}")

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexTransferTx:
        variant = DexTransferVariant(deserializer.deserialize_u32_from_uleb128())
        nonce = deserializer.deserialize_u64()
        if variant == DexTransferVariant.CLAIM_REFERRAL_REWARDS:
            master = AccountAddress.deserialize(deserializer) if deserializer.deserialize_bool() else None
            return ClaimReferralRewards(nonce, on_behalf_of=master)
        if variant == DexTransferVariant.INTERNAL_TRANSFER:
            length = deserializer.deserialize_u32_from_uleb128()
            items: list = [
                InternalTransferItem.deserialize(deserializer) for _ in range(length)
            ]
        elif variant == DexTransferVariant.ACCOUNT_TRANSFER:
            length = deserializer.deserialize_u32_from_uleb128()
            items = [
                AccountTransferItem.deserialize(deserializer) for _ in range(length)
            ]
        elif variant == DexTransferVariant.CROSS_TRANSFER:
            option = CrossTransferOption(deserializer.deserialize_u8())
            length = deserializer.deserialize_u32_from_uleb128()
            items = [CrossTransferItem.deserialize(deserializer) for _ in range(length)]
            has_bridge_proof = deserializer.deserialize_bool()
            bridge_proof = (
                BridgeProof.deserialize(deserializer) if has_bridge_proof else None
            )
            return DexTransferTx(
                nonce,
                variant,
                items,
                option=option,
                bridge_proof=bridge_proof,
            )
        elif variant == DexTransferVariant.FAUCET_MINT:
            length = deserializer.deserialize_u32_from_uleb128()
            items = [CrossTransferItem.deserialize(deserializer) for _ in range(length)]
        else:
            raise ValueError(f"Unknown DexTransferTx variant: {variant}")
        return DexTransferTx(nonce, variant, items)


# =============================================================================
# User Config Types
# =============================================================================


class UserSymbolLeverage:
    symbol_id: int  # u32
    leverage: float

    def __init__(self, symbol_id: int, leverage: float):
        if leverage <= 0:
            raise ValueError("Leverage must be positive")
        self.symbol_id = symbol_id
        self.leverage = leverage
        self._im_leverage = leverage_to_im_leverage(leverage)
        self._exponent = VALID_EXPONENT

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32(self.symbol_id)
        serializer.serialize_i32(self._im_leverage)
        serializer.serialize_i32(self._exponent)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> UserSymbolLeverage:
        symbol_id = deserializer.deserialize_u32()
        im_lev = deserializer.deserialize_i32()
        deserializer.deserialize_i32()  # exponent (always -4)
        leverage = im_leverage_to_leverage(im_lev)
        return UserSymbolLeverage(symbol_id, leverage)


class SetUserLeverage:
    nonce: int  # u64
    sub_address: AccountAddress
    leverage_info: List[UserSymbolLeverage]
    on_behalf_of: Optional[AccountAddress]

    def __init__(
        self,
        nonce: int,
        sub_address: AccountAddress,
        leverage_info: List[UserSymbolLeverage],
        on_behalf_of: Optional[AccountAddress] = None,
    ):
        self.nonce = nonce
        self.sub_address = sub_address
        self.leverage_info = leverage_info
        self.on_behalf_of = on_behalf_of

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.sub_address.serialize(serializer)
        serializer.serialize_u32_as_uleb128(len(self.leverage_info))
        for info in self.leverage_info:
            info.serialize(serializer)
        serializer.serialize_option(self.on_behalf_of)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> SetUserLeverage:
        nonce = deserializer.deserialize_u64()
        sub_address = AccountAddress.deserialize(deserializer)
        length = deserializer.deserialize_u32_from_uleb128()
        leverage_info = [
            UserSymbolLeverage.deserialize(deserializer) for _ in range(length)
        ]
        has_on_behalf_of = deserializer.deserialize_bool()
        on_behalf_of = (
            AccountAddress.deserialize(deserializer) if has_on_behalf_of else None
        )
        return SetUserLeverage(nonce, sub_address, leverage_info, on_behalf_of)


class ChangePositionMode:
    nonce: int  # u64
    sub_address: AccountAddress
    position_mode: OrderPositionMode
    on_behalf_of: Optional[AccountAddress]

    def __init__(
        self,
        nonce: int,
        sub_address: AccountAddress,
        position_mode: OrderPositionMode,
        on_behalf_of: Optional[AccountAddress] = None,
    ):
        self.nonce = nonce
        self.sub_address = sub_address
        self.position_mode = position_mode
        self.on_behalf_of = on_behalf_of

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.sub_address.serialize(serializer)
        serializer.serialize_u8(self.position_mode)
        serializer.serialize_option(self.on_behalf_of)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> ChangePositionMode:
        nonce = deserializer.deserialize_u64()
        sub_address = AccountAddress.deserialize(deserializer)
        position_mode = OrderPositionMode(deserializer.deserialize_u8())
        has_on_behalf_of = deserializer.deserialize_bool()
        on_behalf_of = (
            AccountAddress.deserialize(deserializer) if has_on_behalf_of else None
        )
        return ChangePositionMode(nonce, sub_address, position_mode, on_behalf_of)


class SymbolMarginMode:
    symbol_id: int  # u32
    margin_mode: MarginMode

    def __init__(self, symbol_id: int, margin_mode: MarginMode):
        self.symbol_id = symbol_id
        self.margin_mode = margin_mode

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32(self.symbol_id)
        serializer.serialize_u8(self.margin_mode)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> SymbolMarginMode:
        return SymbolMarginMode(
            symbol_id=deserializer.deserialize_u32(),
            margin_mode=MarginMode(deserializer.deserialize_u8()),
        )


class ChangeMarginMode:
    nonce: int  # u64
    sub_address: AccountAddress
    margin_modes: List[SymbolMarginMode]
    on_behalf_of: Optional[AccountAddress]

    def __init__(
        self,
        nonce: int,
        sub_address: AccountAddress,
        margin_modes: List[SymbolMarginMode],
        on_behalf_of: Optional[AccountAddress] = None,
    ):
        self.nonce = nonce
        self.sub_address = sub_address
        self.margin_modes = margin_modes
        self.on_behalf_of = on_behalf_of

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.sub_address.serialize(serializer)
        serializer.serialize_u32_as_uleb128(len(self.margin_modes))
        for mode in self.margin_modes:
            mode.serialize(serializer)
        serializer.serialize_option(self.on_behalf_of)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> ChangeMarginMode:
        nonce = deserializer.deserialize_u64()
        sub_address = AccountAddress.deserialize(deserializer)
        length = deserializer.deserialize_u32_from_uleb128()
        margin_modes = [
            SymbolMarginMode.deserialize(deserializer) for _ in range(length)
        ]
        has_on_behalf_of = deserializer.deserialize_bool()
        on_behalf_of = (
            AccountAddress.deserialize(deserializer) if has_on_behalf_of else None
        )
        return ChangeMarginMode(nonce, sub_address, margin_modes, on_behalf_of)


class CreateSubAccount:
    nonce: int  # u64
    name: str

    def __init__(self, nonce: int, name: str):
        self.nonce = nonce
        self.name = name

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        serializer.serialize_str(self.name)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> CreateSubAccount:
        return CreateSubAccount(nonce=deserializer.deserialize_u64(), name=deserializer.deserialize_str())


class ModifySubAccount:
    nonce: int  # u64
    name: str
    sub_address: AccountAddress
    on_behalf_of: Optional[AccountAddress]

    def __init__(
        self,
        nonce: int,
        name: str,
        sub_address: AccountAddress,
        on_behalf_of: Optional[AccountAddress] = None,
    ):
        self.nonce = nonce
        self.name = name
        self.sub_address = sub_address
        self.on_behalf_of = on_behalf_of

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        serializer.serialize_str(self.name)
        self.sub_address.serialize(serializer)
        serializer.serialize_option(self.on_behalf_of)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> ModifySubAccount:
        nonce = deserializer.deserialize_u64()
        name = deserializer.deserialize_str()
        sub_address = AccountAddress.deserialize(deserializer)
        has_on_behalf_of = deserializer.deserialize_bool()
        on_behalf_of = (
            AccountAddress.deserialize(deserializer) if has_on_behalf_of else None
        )
        return ModifySubAccount(
            nonce=nonce,
            name=name,
            sub_address=sub_address,
            on_behalf_of=on_behalf_of,
        )


class AdjustIsolatedMargin:
    """Per-side add / remove of isolated-margin collateral on an existing
    isolated position, mirroring the chain ``AdjustIsolatedMarginTx``.

    Semantics:
      - ``delta_long > 0`` moves USDC from the account balance into the
        long-side ``long_imr_quota``; ``delta_long < 0`` releases from the long
        pool back to the balance. ``delta_short`` follows the same sign
        convention for the short side. At least one of the two deltas must be
        non-zero.
      - The net balance change applied by the engine equals
        ``-(delta_long + delta_short)``.

    BCS field order is fixed to match the chain definition:
      nonce (u64) -> sub_address (AccountAddress) -> symbol_id (u32) ->
      delta_long (i64) -> delta_short (i64) -> on_behalf_of (Option<AccountAddress>).
    """

    nonce: int  # u64
    sub_address: AccountAddress
    symbol_id: int  # u32
    delta_long: int  # i64
    delta_short: int  # i64
    on_behalf_of: Optional[AccountAddress]

    def __init__(
        self,
        nonce: int,
        sub_address: AccountAddress,
        symbol_id: int,
        delta_long: int,
        delta_short: int,
        on_behalf_of: Optional[AccountAddress] = None,
    ):
        self.nonce = nonce
        self.sub_address = sub_address
        self.symbol_id = symbol_id
        self.delta_long = delta_long
        self.delta_short = delta_short
        self.on_behalf_of = on_behalf_of

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.sub_address.serialize(serializer)
        serializer.serialize_u32(self.symbol_id)
        serializer.serialize_i64(self.delta_long)
        serializer.serialize_i64(self.delta_short)
        serializer.serialize_option(self.on_behalf_of)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> AdjustIsolatedMargin:
        nonce = deserializer.deserialize_u64()
        sub_address = AccountAddress.deserialize(deserializer)
        symbol_id = deserializer.deserialize_u32()
        delta_long = deserializer.deserialize_i64()
        delta_short = deserializer.deserialize_i64()
        has_on_behalf_of = deserializer.deserialize_bool()
        on_behalf_of = (
            AccountAddress.deserialize(deserializer) if has_on_behalf_of else None
        )
        return AdjustIsolatedMargin(
            nonce=nonce,
            sub_address=sub_address,
            symbol_id=symbol_id,
            delta_long=delta_long,
            delta_short=delta_short,
            on_behalf_of=on_behalf_of,
        )


class RegisterReferralCode:
    def __init__(self, nonce: int, code: str):
        if not re.fullmatch(r"[A-Za-z0-9]{6,20}", code):
            raise ValueError("Referral code must be 6-20 ASCII letters or digits")
        self.nonce = nonce
        self.code = code

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        serializer.serialize_str(self.code)

    @classmethod
    def deserialize(cls, deserializer: Deserializer):
        return cls(deserializer.deserialize_u64(), deserializer.deserialize_str())


class BindReferrer(RegisterReferralCode):
    pass


class ClaimReferralRewards(DexTransferTx):
    def __init__(
        self,
        nonce: int,
        *,
        on_behalf_of: Optional[AccountAddress] = None,
    ):
        super().__init__(nonce, DexTransferVariant.CLAIM_REFERRAL_REWARDS, [])
        self.on_behalf_of = on_behalf_of

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        serializer.serialize_u64(self.nonce)
        serializer.serialize_bool(self.on_behalf_of is not None)
        if self.on_behalf_of is not None:
            self.on_behalf_of.serialize(serializer)


class DexUserConfigTx:
    variant: DexUserConfigTxVariant
    payload: Union[
        SetUserLeverage,
        ChangePositionMode,
        ChangeMarginMode,
        CreateSubAccount,
        ModifySubAccount,
        AdjustIsolatedMargin,
        RegisterReferralCode,
        BindReferrer,
    ]

    def __init__(
        self,
        variant: DexUserConfigTxVariant,
        payload: Union[
            SetUserLeverage,
            ChangePositionMode,
            ChangeMarginMode,
            CreateSubAccount,
            ModifySubAccount,
            AdjustIsolatedMargin,
            RegisterReferralCode,
            BindReferrer,
        ],
    ):
        self.variant = variant
        self.payload = payload

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.payload.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexUserConfigTx:
        variant = DexUserConfigTxVariant(deserializer.deserialize_u32_from_uleb128())
        if variant == DexUserConfigTxVariant.SET_USER_LEVERAGE:
            payload = SetUserLeverage.deserialize(deserializer)
        elif variant == DexUserConfigTxVariant.CHANGE_POSITION_MODE:
            payload = ChangePositionMode.deserialize(deserializer)
        elif variant == DexUserConfigTxVariant.CHANGE_MARGIN_MODE:
            payload = ChangeMarginMode.deserialize(deserializer)
        elif variant == DexUserConfigTxVariant.CREATE_SUB_ACCOUNT:
            payload = CreateSubAccount.deserialize(deserializer)
        elif variant == DexUserConfigTxVariant.MODIFY_SUB_ACCOUNT:
            payload = ModifySubAccount.deserialize(deserializer)
        elif variant == DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN:
            payload = AdjustIsolatedMargin.deserialize(deserializer)
        elif variant == DexUserConfigTxVariant.REGISTER_REFERRAL_CODE:
            payload = RegisterReferralCode.deserialize(deserializer)
        elif variant == DexUserConfigTxVariant.BIND_REFERRER:
            payload = BindReferrer.deserialize(deserializer)
        else:
            raise ValueError(f"Unknown DexUserConfigTx variant: {variant}")
        return DexUserConfigTx(variant, payload)


# =============================================================================
# DexOrderlessTx - top-level variant dispatcher
# =============================================================================


class RawOrderlessInner:
    """An already-serialized DexOrderlessTx inner body, under a caller-supplied variant.

    Admin and system-config operations are deliberately not modelled in this SDK.
    They are owned by the services that hold the keys for them, and they live in a
    separate admin SDK. This type is what makes that possible without either side
    forking the transaction stack: the caller owns the variant number and the
    body's layout, and this module keeps owning the envelope, the signing message
    and the authenticator.

    It knows nothing about any particular operation, and it should stay that way.
    If a variant belongs in this SDK, model it properly; if it does not, it goes
    through here::

        body = Serializer()
        body.serialize_u32_as_uleb128(my_inner_variant)  # the inner tag, if any
        # ... the operation's own fields ...
        tx = DexOrderlessTx(
            DexOrderlessTxVariant.DEX_SYSTEM_CONFIG,
            RawOrderlessInner(body.to_bytes()),
            proof,  # written because the variant says DEX_SYSTEM_CONFIG
        )

    ``body`` is written verbatim, so it must already be valid BCS for whatever the
    chain expects after the variant tag. Nothing here can check that; the caller's
    own golden vectors are what keep it honest.
    """

    body: bytes

    def __init__(self, body: bytes):
        self.body = body

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_fixed_bytes(self.body)


class ReferralParameters:
    def __init__(
        self,
        invitee_fee_discount_ppm: int,
        commission_rate_ppm: int,
        referral_threshold_volume: int,
        discount_volume_cap: int,
        commission_volume_cap: int,
        min_claim_amount: int,
    ):
        if not 0 <= invitee_fee_discount_ppm <= 1_000_000 or not (
            0 <= commission_rate_ppm <= 1_000_000
        ):
            raise ValueError("Invalid referral rate")
        if referral_threshold_volume <= 0 or min_claim_amount <= 0:
            raise ValueError("Invalid referral threshold or minimum claim")
        self.invitee_fee_discount_ppm = invitee_fee_discount_ppm
        self.commission_rate_ppm = commission_rate_ppm
        self.referral_threshold_volume = referral_threshold_volume
        self.discount_volume_cap = discount_volume_cap
        self.commission_volume_cap = commission_volume_cap
        self.min_claim_amount = min_claim_amount

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32(self.invitee_fee_discount_ppm)
        serializer.serialize_u32(self.commission_rate_ppm)
        serializer.serialize_u64(self.referral_threshold_volume)
        serializer.serialize_u64(self.discount_volume_cap)
        serializer.serialize_u64(self.commission_volume_cap)
        serializer.serialize_u64(self.min_claim_amount)


class SetReferralConfig:
    def __init__(self, nonce: int, parameters: ReferralParameters):
        self.nonce = nonce
        self.parameters = parameters

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(36)
        serializer.serialize_u64(self.nonce)
        self.parameters.serialize(serializer)


class DexOrderlessTx:
    variant: DexOrderlessTxVariant
    # ``DexMultisigTx`` is named by string: the multisig module imports the inner
    # transactions it gates from here, so a runtime import back would close a cycle.
    inner: Union[
        DexTx,
        DexUserConfigTx,
        DexTransferTx,
        DexAgentTx,
        "DexMultisigTx",
        RawOrderlessInner,
        SetReferralConfig,
    ]
    multi_sig_proof: Optional[MultiSigProof]

    def __init__(
        self,
        variant: DexOrderlessTxVariant,
        inner: Union[
            DexTx,
            DexUserConfigTx,
            DexTransferTx,
            DexAgentTx,
            "DexMultisigTx",
            RawOrderlessInner,
            SetReferralConfig,
        ],
        multi_sig_proof: Optional[MultiSigProof] = None,
    ):
        self.variant = variant
        self.inner = inner
        # The second field of the chain's DexSystemConfig variant:
        #
        #     DexSystemConfig(DexSystemConfigTx, Option<MultiSigProof>)
        #
        # ``None`` encodes Option::None, the legacy single-signer path and what
        # every caller wants until committee multisig is in use. Ignored for the
        # other variants, none of which carry a proof.
        self.multi_sig_proof = multi_sig_proof

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.inner.serialize(serializer)

        # DexSystemConfig alone carries a second field. Omitting it makes the node
        # reject every system-config transaction: over BCS it runs out of bytes
        # ("expected option type"), and over JSON it rebuilds the payload with
        # None, re-serializes it a byte longer than what was signed, and reports
        # INVALID_SIGNATURE -- an error that points at neither the field nor the
        # side that differs. The other variants take no proof, so the tag is
        # written only here.
        if self.variant == DexOrderlessTxVariant.DEX_SYSTEM_CONFIG:
            serializer.serialize_bool(self.multi_sig_proof is not None)
            if self.multi_sig_proof is not None:
                self.multi_sig_proof.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> DexOrderlessTx:
        variant = DexOrderlessTxVariant(deserializer.deserialize_u32_from_uleb128())
        if variant == DexOrderlessTxVariant.DEX:
            inner = DexTx.deserialize(deserializer)
        elif variant == DexOrderlessTxVariant.DEX_USER_CONFIG:
            inner = DexUserConfigTx.deserialize(deserializer)
        elif variant == DexOrderlessTxVariant.DEX_TRANSFER:
            inner = DexTransferTx.deserialize(deserializer)
        elif variant == DexOrderlessTxVariant.DEX_AGENT:
            inner = DexAgentTx.deserialize(deserializer)
        elif variant == DexOrderlessTxVariant.VAULT:
            from .vault_payloads import VaultTx

            inner = VaultTx.deserialize(deserializer)
        elif variant == DexOrderlessTxVariant.MULTISIG:
            # Imported inside the branch for the same reason the vault types are:
            # that module imports this one.
            from .multisig_payloads import DexMultisigTx

            inner = DexMultisigTx.deserialize(deserializer)
        else:
            raise ValueError(f"Unknown DexOrderlessTx variant: {variant}")
        return DexOrderlessTx(variant, inner)


# ============================================================================
# TransactionPayload
# ============================================================================


class TransactionPayload(Serializable):
    """The payload slot of a transaction.

    Every DEX and admin operation arrives as an orderless payload, which the
    chain numbers 5. The lower numbers belong to Move scripts and entry
    functions; those cannot pay for themselves on this chain, so nothing here
    builds or reads one.
    """

    DEX_ORDERLESS: int = 5

    variant: int
    value: "DexOrderlessTx"

    def __init__(self, payload: "DexOrderlessTx") -> None:
        if not isinstance(payload, DexOrderlessTx):
            raise ValueError(
                f"Unsupported transaction payload: {type(payload).__name__}"
            )
        self.variant = TransactionPayload.DEX_ORDERLESS
        self.value = payload

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TransactionPayload):
            return NotImplemented
        return self.variant == other.variant and self.value == other.value

    def __str__(self) -> str:
        return str(self.value)

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.value.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> TransactionPayload:
        variant = deserializer.deserialize_u32_from_uleb128()
        if variant != TransactionPayload.DEX_ORDERLESS:
            raise ValueError(f"Unsupported transaction payload variant: {variant}")
        return TransactionPayload(DexOrderlessTx.deserialize(deserializer))


# Name kept for parity with the TypeScript SDK, where the orderless payload has
# its own type.
TransactionPayloadDexOrderless = TransactionPayload


def is_cross_transfer_orderless_payload(payload: object) -> bool:
    """Whether this payload is a CrossTransfer, which needs its own replay nonce."""
    if not isinstance(payload, TransactionPayload):
        return False
    inner = payload.value
    return (
        isinstance(inner, DexOrderlessTx)
        and inner.variant == DexOrderlessTxVariant.DEX_TRANSFER
        and isinstance(inner.inner, DexTransferTx)
        and inner.inner.variant == DexTransferVariant.CROSS_TRANSFER
    )

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from ..core.account_address import AccountAddress
from ..bcs import Deserializer


def _read_address(deserializer: Deserializer) -> AccountAddress:
    return AccountAddress(deserializer.deserialize_fixed_bytes(AccountAddress.LENGTH))


def _read_option_string(deserializer: Deserializer) -> Optional[str]:
    return deserializer.deserialize_str() if deserializer.deserialize_bool() else None


def _read_option_u64(deserializer: Deserializer) -> Optional[int]:
    return deserializer.deserialize_u64() if deserializer.deserialize_bool() else None


def _read_trailing_option_u32(deserializer: Deserializer) -> Optional[int]:
    if deserializer.remaining() == 0:
        return None
    return deserializer.deserialize_u32() if deserializer.deserialize_bool() else None


@dataclass(frozen=True)
class SubaccountId:
    address: AccountAddress
    number: int
    sub_address: AccountAddress
    user_name: bytes


def _read_subaccount_id(deserializer: Deserializer) -> SubaccountId:
    return SubaccountId(
        address=_read_address(deserializer),
        number=deserializer.deserialize_u32(),
        sub_address=_read_address(deserializer),
        user_name=deserializer.deserialize_fixed_bytes(16),
    )


@dataclass(frozen=True)
class InternalTransferEvent:
    success: bool


def decode_internal_transfer_event(data: bytes) -> InternalTransferEvent:
    deserializer = Deserializer(data)
    return InternalTransferEvent(success=deserializer.deserialize_bool())


@dataclass(frozen=True)
class AccountTransferEvent:
    from_account: AccountAddress
    #: The owner the chain resolved the recipient address to.
    to_account: AccountAddress
    #: Set when the money landed on a subaccount; zero when it landed on the main
    #: account. The payload carries one recipient address and the chain decides
    #: which it was, so without this field there is no way to tell them apart.
    to_subaccount: AccountAddress
    asset_id: int
    original_amount: int
    net_amount: int
    fee_amount: int
    fee_account: Optional[AccountAddress] = None


def decode_account_transfer_event(data: bytes) -> AccountTransferEvent:
    deserializer = Deserializer(data)
    from_account = _read_address(deserializer)
    to_account = _read_address(deserializer)
    to_subaccount = _read_address(deserializer)
    asset_id = deserializer.deserialize_u32()
    original_amount = deserializer.deserialize_u64()
    net_amount = deserializer.deserialize_u64()
    fee_amount = deserializer.deserialize_u64()
    fee_account = _read_address(deserializer) if deserializer.deserialize_bool() else None
    return AccountTransferEvent(
        from_account=from_account,
        to_account=to_account,
        to_subaccount=to_subaccount,
        asset_id=asset_id,
        original_amount=original_amount,
        net_amount=net_amount,
        fee_amount=fee_amount,
        fee_account=fee_account,
    )


@dataclass(frozen=True)
class CrossTransferEvent:
    success: bool
    msg_id: bytes
    to_account: AccountAddress
    original_amount: int
    net_amount: int
    fee_amount: int
    fee_account: Optional[AccountAddress]
    option: int


def decode_cross_transfer_event(data: bytes) -> CrossTransferEvent:
    deserializer = Deserializer(data)
    success = deserializer.deserialize_bool()
    msg_id = deserializer.deserialize_bytes()
    to_account = _read_address(deserializer)
    original_amount = deserializer.deserialize_u64()
    net_amount = deserializer.deserialize_u64()
    fee_amount = deserializer.deserialize_u64()
    fee_account = _read_address(deserializer) if deserializer.deserialize_bool() else None
    option = deserializer.deserialize_u8()
    return CrossTransferEvent(
        success=success,
        msg_id=msg_id,
        to_account=to_account,
        original_amount=original_amount,
        net_amount=net_amount,
        fee_amount=fee_amount,
        fee_account=fee_account,
        option=option,
    )


@dataclass(frozen=True)
class FaucetMintEvent:
    success: bool
    to_account: AccountAddress
    asset_id: int
    original_amount: int
    net_amount: int
    fee_amount: int
    fee_account: Optional[AccountAddress]


def decode_faucet_mint_event(data: bytes) -> FaucetMintEvent:
    deserializer = Deserializer(data)
    success = deserializer.deserialize_bool()
    to_account = _read_address(deserializer)
    asset_id = deserializer.deserialize_u32()
    original_amount = deserializer.deserialize_u64()
    net_amount = deserializer.deserialize_u64()
    fee_amount = deserializer.deserialize_u64()
    fee_account = _read_address(deserializer) if deserializer.deserialize_bool() else None
    return FaucetMintEvent(
        success=success,
        to_account=to_account,
        asset_id=asset_id,
        original_amount=original_amount,
        net_amount=net_amount,
        fee_amount=fee_amount,
        fee_account=fee_account,
    )


@dataclass(frozen=True)
class SuccessEvent:
    success: bool


def _decode_success_event(data: bytes) -> SuccessEvent:
    deserializer = Deserializer(data)
    return SuccessEvent(success=deserializer.deserialize_bool())


decode_create_spot_event = _decode_success_event
decode_create_perpetual_event = _decode_success_event
decode_update_leverage_event = _decode_success_event
decode_set_account_fee_rate_event = _decode_success_event
decode_set_fee_config_event = _decode_success_event
decode_update_bridge_signers_event = _decode_success_event
decode_set_bridge_fees_event = _decode_success_event
decode_set_faucet_mint_enabled_event = _decode_success_event


@dataclass(frozen=True)
class SetSymbolTradingPolicyEvent:
    perpetual_id: int


def decode_set_symbol_trading_policy_event(
    data: bytes,
) -> SetSymbolTradingPolicyEvent:
    deserializer = Deserializer(data)
    return SetSymbolTradingPolicyEvent(perpetual_id=deserializer.deserialize_u32())


@dataclass(frozen=True)
class SetSymbolLeverageTierEvent:
    perpetual_id: int
    tier: int


def decode_set_symbol_leverage_tier_event(
    data: bytes,
) -> SetSymbolLeverageTierEvent:
    deserializer = Deserializer(data)
    return SetSymbolLeverageTierEvent(
        perpetual_id=deserializer.deserialize_u32(),
        tier=deserializer.deserialize_u32(),
    )


@dataclass(frozen=True)
class SetSymbolDisplayInfoEvent:
    perpetual_id: int


def decode_set_symbol_display_info_event(data: bytes) -> SetSymbolDisplayInfoEvent:
    deserializer = Deserializer(data)
    return SetSymbolDisplayInfoEvent(perpetual_id=deserializer.deserialize_u32())


@dataclass(frozen=True)
class SetSymbolRiskLimitsEvent:
    perpetual_id: int


def decode_set_symbol_risk_limits_event(data: bytes) -> SetSymbolRiskLimitsEvent:
    deserializer = Deserializer(data)
    return SetSymbolRiskLimitsEvent(perpetual_id=deserializer.deserialize_u32())


@dataclass(frozen=True)
class SetSymbolFundingEvent:
    perpetual_id: int


def decode_set_symbol_funding_event(data: bytes) -> SetSymbolFundingEvent:
    deserializer = Deserializer(data)
    return SetSymbolFundingEvent(perpetual_id=deserializer.deserialize_u32())


@dataclass(frozen=True)
class SetSymbolBackstopEvent:
    perpetual_id: int


def decode_set_symbol_backstop_event(data: bytes) -> SetSymbolBackstopEvent:
    deserializer = Deserializer(data)
    return SetSymbolBackstopEvent(perpetual_id=deserializer.deserialize_u32())


@dataclass(frozen=True)
class SetSymbolFeeOverrideEvent:
    perpetual_id: int


def decode_set_symbol_fee_override_event(
    data: bytes,
) -> SetSymbolFeeOverrideEvent:
    deserializer = Deserializer(data)
    return SetSymbolFeeOverrideEvent(perpetual_id=deserializer.deserialize_u32())


@dataclass(frozen=True)
class SetSymbolSpecEvent:
    perpetual_id: int


def decode_set_symbol_spec_event(data: bytes) -> SetSymbolSpecEvent:
    deserializer = Deserializer(data)
    return SetSymbolSpecEvent(perpetual_id=deserializer.deserialize_u32())


@dataclass(frozen=True)
class BatchSystemConfigEvent:
    total: int
    succeeded: int
    failed: int


def decode_batch_system_config_event(data: bytes) -> BatchSystemConfigEvent:
    deserializer = Deserializer(data)
    return BatchSystemConfigEvent(
        total=deserializer.deserialize_u32(),
        succeeded=deserializer.deserialize_u32(),
        failed=deserializer.deserialize_u32(),
    )


@dataclass(frozen=True)
class BatchOpFailedEvent:
    index: int
    id: int
    sub_op_kind: int
    reason_code: int


def decode_batch_op_failed_event(data: bytes) -> BatchOpFailedEvent:
    deserializer = Deserializer(data)
    return BatchOpFailedEvent(
        index=deserializer.deserialize_u32(),
        id=deserializer.deserialize_u32(),
        sub_op_kind=deserializer.deserialize_u8(),
        reason_code=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class SymbolOpenedEvent:
    perpetual_id: int
    listing_time: int
    opening_mark_price: int


def decode_symbol_opened_event(data: bytes) -> SymbolOpenedEvent:
    deserializer = Deserializer(data)
    return SymbolOpenedEvent(
        perpetual_id=deserializer.deserialize_u32(),
        listing_time=deserializer.deserialize_u64(),
        opening_mark_price=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class CreateSubAccountEvent:
    sub_address: AccountAddress


def decode_create_sub_account_event(data: bytes) -> CreateSubAccountEvent:
    deserializer = Deserializer(data)
    return CreateSubAccountEvent(sub_address=_read_address(deserializer))


@dataclass(frozen=True)
class ModifySubAccountEvent:
    sub_address: AccountAddress
    name: str


def decode_modify_sub_account_event(data: bytes) -> ModifySubAccountEvent:
    deserializer = Deserializer(data)
    return ModifySubAccountEvent(
        sub_address=_read_address(deserializer),
        name=deserializer.deserialize_str(),
    )


@dataclass(frozen=True)
class SetUserLeverageEvent:
    sub_address: AccountAddress


def decode_set_user_leverage_event(data: bytes) -> SetUserLeverageEvent:
    deserializer = Deserializer(data)
    return SetUserLeverageEvent(sub_address=_read_address(deserializer))


@dataclass(frozen=True)
class ChangePositionModeEvent:
    sub_address: AccountAddress


def decode_change_position_mode_event(data: bytes) -> ChangePositionModeEvent:
    deserializer = Deserializer(data)
    return ChangePositionModeEvent(sub_address=_read_address(deserializer))


@dataclass(frozen=True)
class ChangeMarginModeEvent:
    sub_address: AccountAddress


def decode_change_margin_mode_event(data: bytes) -> ChangeMarginModeEvent:
    deserializer = Deserializer(data)
    return ChangeMarginModeEvent(sub_address=_read_address(deserializer))


@dataclass(frozen=True)
class OrderPlacedEvent:
    subaccount_id: SubaccountId
    symbol_id: int
    symbol_type: int
    side: int
    quantums: int
    subticks: int
    order_basic_type: int
    time_in_force: int
    condition_type: int
    operation: int
    timestamp: int
    target_order_id: int
    order_id: int
    state: int
    transaction_id: bytes
    remaining_quantums: int
    filled_quantums: int
    opening_fee: int
    closing_fee: int
    reduce_only: bool
    position_mode: int
    created_by: int
    canceled_by: int
    reject_reason: int
    slippage_tolerance_ppm: int
    trigger_subticks: int
    trigger_price_type: int
    parent_order_id: int
    is_activated: bool
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int
    reservation_fee_rate_ppm: Optional[int] = None


def decode_order_placed_event(data: bytes) -> OrderPlacedEvent:
    deserializer = Deserializer(data)
    return OrderPlacedEvent(
        subaccount_id=_read_subaccount_id(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        symbol_type=deserializer.deserialize_u32(),
        side=deserializer.deserialize_u32(),
        quantums=deserializer.deserialize_i64(),
        subticks=deserializer.deserialize_u64(),
        order_basic_type=deserializer.deserialize_u32(),
        time_in_force=deserializer.deserialize_u32(),
        condition_type=deserializer.deserialize_u32(),
        operation=deserializer.deserialize_u32(),
        timestamp=deserializer.deserialize_u64(),
        target_order_id=deserializer.deserialize_u64(),
        order_id=deserializer.deserialize_u64(),
        state=deserializer.deserialize_u32(),
        transaction_id=deserializer.deserialize_bytes(),
        remaining_quantums=deserializer.deserialize_u64(),
        filled_quantums=deserializer.deserialize_u64(),
        opening_fee=deserializer.deserialize_i128(),
        closing_fee=deserializer.deserialize_i128(),
        reduce_only=deserializer.deserialize_bool(),
        position_mode=deserializer.deserialize_u32(),
        created_by=deserializer.deserialize_u32(),
        canceled_by=deserializer.deserialize_u32(),
        reject_reason=deserializer.deserialize_u32(),
        slippage_tolerance_ppm=deserializer.deserialize_u32(),
        trigger_subticks=deserializer.deserialize_u64(),
        trigger_price_type=deserializer.deserialize_u32(),
        parent_order_id=deserializer.deserialize_i64(),
        is_activated=deserializer.deserialize_bool(),
        client_order_id=_read_option_string(deserializer),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
        reservation_fee_rate_ppm=_read_trailing_option_u32(deserializer),
    )


ConditionOrderPlacedEvent = OrderPlacedEvent


def decode_condition_order_placed_event(data: bytes) -> ConditionOrderPlacedEvent:
    return decode_order_placed_event(data)


@dataclass(frozen=True)
class ConditionOrderActivatedEvent:
    order_id: int
    parent_order_id: int
    owner: AccountAddress
    sub_address: AccountAddress
    symbol_id: int
    condition_type: int
    client_order_id: Optional[str]
    is_activated: bool
    activation_state: int
    block_height: int
    block_timestamp: int


def decode_condition_order_activated_event(
    data: bytes,
) -> ConditionOrderActivatedEvent:
    deserializer = Deserializer(data)
    return ConditionOrderActivatedEvent(
        order_id=deserializer.deserialize_u64(),
        parent_order_id=deserializer.deserialize_u64(),
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        condition_type=deserializer.deserialize_u32(),
        client_order_id=_read_option_string(deserializer),
        is_activated=deserializer.deserialize_bool(),
        activation_state=deserializer.deserialize_u32(),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class ConditionOrderParentReboundEvent:
    order_id: int
    old_parent_order_id: int
    new_parent_order_id: int
    owner: AccountAddress
    sub_address: AccountAddress
    symbol_id: int
    condition_type: int
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


def decode_condition_order_parent_rebound_event(
    data: bytes,
) -> ConditionOrderParentReboundEvent:
    deserializer = Deserializer(data)
    return ConditionOrderParentReboundEvent(
        order_id=deserializer.deserialize_u64(),
        old_parent_order_id=deserializer.deserialize_u64(),
        new_parent_order_id=deserializer.deserialize_u64(),
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        condition_type=deserializer.deserialize_u32(),
        client_order_id=_read_option_string(deserializer),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class ConditionOrderTriggeredEvent:
    order_id: int
    owner: AccountAddress
    sub_address: AccountAddress
    symbol_id: int
    condition_type: int
    state: int
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


def decode_condition_order_triggered_event(
    data: bytes,
) -> ConditionOrderTriggeredEvent:
    deserializer = Deserializer(data)
    return ConditionOrderTriggeredEvent(
        order_id=deserializer.deserialize_u64(),
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        condition_type=deserializer.deserialize_u32(),
        state=deserializer.deserialize_u32(),
        client_order_id=_read_option_string(deserializer),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class WholePositionOcoUpdatedEvent:
    owner: AccountAddress
    sub_address: AccountAddress
    symbol_id: int
    position_side: int
    group_id: int
    take_profit_order_id: Optional[int]
    stop_loss_order_id: Optional[int]
    update_type: int
    block_height: int
    block_timestamp: int


def decode_whole_position_oco_updated_event(
    data: bytes,
) -> WholePositionOcoUpdatedEvent:
    deserializer = Deserializer(data)
    return WholePositionOcoUpdatedEvent(
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        position_side=deserializer.deserialize_u32(),
        group_id=deserializer.deserialize_u64(),
        take_profit_order_id=_read_option_u64(deserializer),
        stop_loss_order_id=_read_option_u64(deserializer),
        update_type=deserializer.deserialize_u32(),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class OrderFilledEvent:
    order_id: int
    owner: AccountAddress
    sub_address: AccountAddress
    symbol_id: int
    remaining_quantums: int
    basic_type: int
    side: int
    state: int
    transaction_id: bytes
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


def decode_order_filled_event(data: bytes) -> OrderFilledEvent:
    deserializer = Deserializer(data)
    return OrderFilledEvent(
        order_id=deserializer.deserialize_u64(),
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        remaining_quantums=deserializer.deserialize_u64(),
        basic_type=deserializer.deserialize_u32(),
        side=deserializer.deserialize_u32(),
        state=deserializer.deserialize_u32(),
        transaction_id=deserializer.deserialize_bytes(),
        client_order_id=_read_option_string(deserializer),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class OrderCancelledEvent:
    order_id: int
    owner: AccountAddress
    sub_address: AccountAddress
    symbol_id: int
    remaining_quantums: int
    canceled_by: int
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


def decode_order_cancelled_event(data: bytes) -> OrderCancelledEvent:
    deserializer = Deserializer(data)
    return OrderCancelledEvent(
        order_id=deserializer.deserialize_u64(),
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        remaining_quantums=deserializer.deserialize_u64(),
        canceled_by=deserializer.deserialize_u32(),
        client_order_id=_read_option_string(deserializer),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class OrderAmendedEvent:
    order_id: int
    owner: AccountAddress
    sub_address: AccountAddress
    symbol_id: int
    old_quantums: int
    new_quantums: int
    old_remaining_quantums: int
    new_remaining_quantums: int
    kept_priority: bool
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int
    reservation_fee_rate_ppm: Optional[int] = None


def decode_order_amended_event(data: bytes) -> OrderAmendedEvent:
    deserializer = Deserializer(data)
    return OrderAmendedEvent(
        order_id=deserializer.deserialize_u64(),
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        old_quantums=deserializer.deserialize_i64(),
        new_quantums=deserializer.deserialize_i64(),
        old_remaining_quantums=deserializer.deserialize_u64(),
        new_remaining_quantums=deserializer.deserialize_u64(),
        kept_priority=deserializer.deserialize_bool(),
        client_order_id=_read_option_string(deserializer),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
        reservation_fee_rate_ppm=_read_trailing_option_u32(deserializer),
    )


@dataclass(frozen=True)
class OrderRejectedEvent:
    order_id: int
    owner: AccountAddress
    sub_address: AccountAddress
    symbol_id: int
    reject_reason: int
    transaction_id: bytes
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


def decode_order_rejected_event(data: bytes) -> OrderRejectedEvent:
    deserializer = Deserializer(data)
    return OrderRejectedEvent(
        order_id=deserializer.deserialize_u64(),
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        reject_reason=deserializer.deserialize_u32(),
        transaction_id=deserializer.deserialize_bytes(),
        client_order_id=_read_option_string(deserializer),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class FillEvent:
    symbol_id: int
    fill_order_id: int
    maker_order_id: int
    taker_order_id: int
    filled_quantums: int
    match_subticks: int
    block_height: int
    fill_timestamp: int
    maker_subaccount_id: SubaccountId
    maker_direction: int
    maker_open_quantums: int
    maker_close_quantums: int
    maker_opening_fee: int
    maker_closing_fee: int
    maker_new_state: int
    maker_realized_pnl: int
    maker_client_order_id: Optional[str]
    taker_subaccount_id: SubaccountId
    taker_direction: int
    taker_open_quantums: int
    taker_close_quantums: int
    taker_opening_fee: int
    taker_closing_fee: int
    taker_new_state: int
    taker_realized_pnl: int
    taker_client_order_id: Optional[str]


def decode_fill_event(data: bytes) -> FillEvent:
    deserializer = Deserializer(data)
    return FillEvent(
        symbol_id=deserializer.deserialize_u32(),
        fill_order_id=deserializer.deserialize_u64(),
        maker_order_id=deserializer.deserialize_u64(),
        taker_order_id=deserializer.deserialize_u64(),
        filled_quantums=deserializer.deserialize_u64(),
        match_subticks=deserializer.deserialize_u64(),
        block_height=deserializer.deserialize_u64(),
        fill_timestamp=deserializer.deserialize_u64(),
        maker_subaccount_id=_read_subaccount_id(deserializer),
        maker_direction=deserializer.deserialize_u32(),
        maker_open_quantums=deserializer.deserialize_u64(),
        maker_close_quantums=deserializer.deserialize_u64(),
        maker_opening_fee=deserializer.deserialize_i128(),
        maker_closing_fee=deserializer.deserialize_i128(),
        maker_new_state=deserializer.deserialize_u32(),
        maker_realized_pnl=deserializer.deserialize_i128(),
        maker_client_order_id=_read_option_string(deserializer),
        taker_subaccount_id=_read_subaccount_id(deserializer),
        taker_direction=deserializer.deserialize_u32(),
        taker_open_quantums=deserializer.deserialize_u64(),
        taker_close_quantums=deserializer.deserialize_u64(),
        taker_opening_fee=deserializer.deserialize_i128(),
        taker_closing_fee=deserializer.deserialize_i128(),
        taker_new_state=deserializer.deserialize_u32(),
        taker_realized_pnl=deserializer.deserialize_i128(),
        taker_client_order_id=_read_option_string(deserializer),
    )


@dataclass(frozen=True)
class FundingRateEvent:
    symbol_id: int
    funding_rate_ppm: int
    mark_price: int
    block_height: int
    timestamp: int


def decode_funding_rate_event(data: bytes) -> FundingRateEvent:
    deserializer = Deserializer(data)
    return FundingRateEvent(
        symbol_id=deserializer.deserialize_u32(),
        funding_rate_ppm=deserializer.deserialize_i32(),
        mark_price=deserializer.deserialize_u64(),
        block_height=deserializer.deserialize_u64(),
        timestamp=deserializer.deserialize_u64(),
    )


@dataclass(frozen=True)
class AccountUpdatedEvent:
    owner: AccountAddress
    sub_address: AccountAddress
    asset_id: int
    new_balance: int
    reason: int
    block_height: int
    timestamp: int


def decode_account_updated_event(data: bytes) -> AccountUpdatedEvent:
    deserializer = Deserializer(data)
    return AccountUpdatedEvent(
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        asset_id=deserializer.deserialize_u32(),
        new_balance=deserializer.deserialize_u64(),
        reason=deserializer.deserialize_u8(),
        block_height=deserializer.deserialize_u64(),
        timestamp=deserializer.deserialize_u64(),
    )


_FIXTURE_DECODERS: Dict[str, Callable[[bytes], Any]] = {
    "decode_internal_transfer_event": decode_internal_transfer_event,
    "decode_account_transfer_event": decode_account_transfer_event,
    "decode_cross_transfer_event": decode_cross_transfer_event,
    "decode_faucet_mint_event": decode_faucet_mint_event,
    "decode_create_spot_event": decode_create_spot_event,
    "decode_create_perpetual_event": decode_create_perpetual_event,
    "decode_update_leverage_event": decode_update_leverage_event,
    "decode_set_account_fee_rate_event": decode_set_account_fee_rate_event,
    "decode_set_fee_config_event": decode_set_fee_config_event,
    "decode_update_bridge_signers_event": decode_update_bridge_signers_event,
    "decode_set_bridge_fees_event": decode_set_bridge_fees_event,
    "decode_set_faucet_mint_enabled_event": decode_set_faucet_mint_enabled_event,
    "decode_set_symbol_trading_policy_event": decode_set_symbol_trading_policy_event,
    "decode_set_symbol_leverage_tier_event": decode_set_symbol_leverage_tier_event,
    "decode_set_symbol_display_info_event": decode_set_symbol_display_info_event,
    "decode_set_symbol_risk_limits_event": decode_set_symbol_risk_limits_event,
    "decode_set_symbol_funding_event": decode_set_symbol_funding_event,
    "decode_set_symbol_backstop_event": decode_set_symbol_backstop_event,
    "decode_set_symbol_fee_override_event": decode_set_symbol_fee_override_event,
    "decode_set_symbol_spec_event": decode_set_symbol_spec_event,
    "decode_batch_system_config_event": decode_batch_system_config_event,
    "decode_batch_op_failed_event": decode_batch_op_failed_event,
    "decode_symbol_opened_event": decode_symbol_opened_event,
    "decode_create_sub_account_event": decode_create_sub_account_event,
    "decode_modify_sub_account_event": decode_modify_sub_account_event,
    "decode_set_user_leverage_event": decode_set_user_leverage_event,
    "decode_change_position_mode_event": decode_change_position_mode_event,
    "decode_change_margin_mode_event": decode_change_margin_mode_event,
    "decode_order_placed_event": decode_order_placed_event,
    "decode_order_filled_event": decode_order_filled_event,
    "decode_order_cancelled_event": decode_order_cancelled_event,
    "decode_order_rejected_event": decode_order_rejected_event,
    "decode_condition_order_activated_event": decode_condition_order_activated_event,
    "decode_fill_event": decode_fill_event,
    "decode_funding_rate_event": decode_funding_rate_event,
    "decode_account_updated_event": decode_account_updated_event,
}


# ---------------------------------------------------------------------------
# Account authority (native multisig) events
#
# ``auth_key``, ``owners_digest`` and ``op_id`` are declared ``Vec<u8>`` on the
# chain rather than ``[u8; 32]``, so each one carries a ULEB length byte. They are
# read with ``to_bytes`` for that reason; reading them as fixed 32 bytes would
# consume the length byte as data and shift every field after it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorityChangedEvent:
    """Emitted by every authority change, whichever of the five operations made it.

    One event for all of them, with ``op_kind`` saying which, so "how did control of
    this account change" is a single stream to follow.
    """

    account: AccountAddress
    #: The epoch being replaced; zero when the account had no record.
    old_epoch: int
    #: The epoch now in force. Monotonic for the life of the account, which is what
    #: retires every approval signed against an earlier owner set.
    new_epoch: int
    #: 0 = a named control key, 1 = a k-of-n policy (``AuthorityKindVariant``).
    kind: int
    #: The named control key, or 32 zero bytes for a policy.
    auth_key: bytes
    #: Approvals required. Zero for a key record.
    threshold: int
    #: Size of the owner set. Zero for a key record.
    owner_count: int
    #: Commitment to the owner list, or 32 zero bytes for a key record. The members
    #: themselves are not in the event -- an owner set is up to ten addresses of
    #: consensus-visible payload -- so a reader that holds a set checks it against
    #: this (``multisig_owners_digest``) and reads the record when it needs them.
    owners_digest: bytes
    #: Which multisig operation made the change (``MultisigOpVariant``).
    op_kind: int
    #: Who submitted the change.
    executor: AccountAddress


def decode_authority_changed_event(data: bytes) -> AuthorityChangedEvent:
    deserializer = Deserializer(data)
    return AuthorityChangedEvent(
        account=_read_address(deserializer),
        old_epoch=deserializer.deserialize_u64(),
        new_epoch=deserializer.deserialize_u64(),
        kind=deserializer.deserialize_u8(),
        auth_key=deserializer.deserialize_bytes(),
        threshold=deserializer.deserialize_u8(),
        owner_count=deserializer.deserialize_u32(),
        owners_digest=deserializer.deserialize_bytes(),
        op_kind=deserializer.deserialize_u8(),
        executor=_read_address(deserializer),
    )


@dataclass(frozen=True)
class MultisigOperationExecutedEvent:
    """Emitted when an account under a policy executes a gated payload."""

    #: The account the payload executed as, not the owner who submitted it.
    account: AccountAddress
    #: The replay key the owners signed. The chain records it as spent, so the same
    #: approved operation cannot be handed in twice.
    op_id: bytes
    #: Which payload ran (``GatedPayloadVariant``).
    payload_kind: int
    #: The authority epoch the approvals were counted against.
    authority_epoch: int
    #: Which owner submitted it.
    executor: AccountAddress
    #: Approvals counted.
    signature_count: int


def decode_multisig_operation_executed_event(
    data: bytes,
) -> MultisigOperationExecutedEvent:
    deserializer = Deserializer(data)
    return MultisigOperationExecutedEvent(
        account=_read_address(deserializer),
        op_id=deserializer.deserialize_bytes(),
        payload_kind=deserializer.deserialize_u8(),
        authority_epoch=deserializer.deserialize_u64(),
        executor=_read_address(deserializer),
        signature_count=deserializer.deserialize_u8(),
    )

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from .vault_events import (
    VAULT_EVENT_NAMES as _VAULT_EVENT_NAMES,
    DexVaultInternalOffsetEvent,
    decode_vault_event as _decode_vault_event,
)
from ..core.account_address import AccountAddress
from ..bcs import Deserializer
from .referral_events import REFERRAL_EVENT_NAMES, decode_referral_event_bytes, decode_referral_event_json
from ..core.hex import Hex, ParsingError


def _read_address(deserializer: Deserializer) -> str:
    return str(AccountAddress(deserializer.deserialize_fixed_bytes(AccountAddress.LENGTH)))


@dataclass(frozen=True)
class DexSubaccountId:
    address: str
    number: int
    sub_address: str
    user_name: bytes


@dataclass(frozen=True)
class DexAssetPosition:
    asset_id: int
    balance: int
    locked: int


@dataclass(frozen=True)
class DexPerpPosition:
    perpetual_id: int
    short_quantums: int
    long_quantums: int
    delta_sell_closing_long: int
    delta_buy_opening_long: int
    delta_sell_closing_short: int
    delta_buy_opening_short: int
    margin_mode: int
    funding_index: int
    long_position_value: int
    short_position_value: int
    long_imr_quota: int
    short_imr_quota: int
    long_mmr_quota: int
    short_mmr_quota: int
    long_bankrupt_price: int
    short_bankrupt_price: int
    long_imr_close_fee: int
    short_imr_close_fee: int


@dataclass(frozen=True)
class DexLeverageInfo:
    tier: int
    min_notional: int
    max_notional: int
    im_leverage: int
    mm_leverage: int
    exponent: int
    maintenance_deduction: int


@dataclass(frozen=True)
class DexSymbolLeverage:
    symbol_id: int
    leverage_info: DexLeverageInfo


@dataclass(frozen=True)
class DexSymbolMarginMode:
    symbol_id: int
    margin_mode: int


# NOTE: `daily_buckets` was removed from the on-chain `AccountEvent` parent
# volume snapshot (the per-day breakdown moved off-chain). This type is kept as
# a standalone public type for auxiliary/off-chain volume data and is no longer
# part of `DexParentVolumeInfo`.
@dataclass(frozen=True)
class DexDailyVolumeBucket:
    volume_usd: int
    maker_volume_usd: int
    utc_day_start: int
    fee_inflow: int


@dataclass(frozen=True)
class DexParentVolumeInfo:
    type: int
    last_trade_timestamp_sec: int
    cumulative_volume_usd: int
    volume_threshold_reached: bool


@dataclass(frozen=True)
class DexMarkPriceInfo:
    symbol_id: int
    mark_price: int
    exponent: int


@dataclass(frozen=True)
class DexIndexPriceInfo:
    symbol_id: int
    index_price: int
    exponent: int


@dataclass(frozen=True)
class DexFundingPredictionInfo:
    symbol_id: int
    funding_rate_ppm: int
    timestamp: int


@dataclass(frozen=True)
class DexFundingRateEvent:
    symbol_id: int
    funding_rate_ppm: int
    mark_price: int
    block_height: int
    timestamp: int


@dataclass(frozen=True)
class DexFillEvent:
    symbol_id: int
    fill_order_id: int
    maker_order_id: int
    taker_order_id: int
    filled_quantums: int
    match_subticks: int
    block_height: int
    fill_timestamp: int
    maker_subaccount_id: DexSubaccountId
    maker_direction: int
    maker_open_quantums: int
    maker_close_quantums: int
    maker_opening_fee: int
    maker_closing_fee: int
    maker_new_state: int
    maker_realized_pnl: int
    maker_client_order_id: Optional[str]
    taker_subaccount_id: DexSubaccountId
    taker_direction: int
    taker_open_quantums: int
    taker_close_quantums: int
    taker_opening_fee: int
    taker_closing_fee: int
    taker_new_state: int
    taker_realized_pnl: int
    taker_client_order_id: Optional[str]
    # Order progress was merged from the retired per-order OrderFilledEvent.
    # None means that the payload predates this schema extension.
    maker_remaining_quantums: Optional[int] = None
    taker_remaining_quantums: Optional[int] = None
    # True for synthetic liquidation / ADL / self-cross fills. This field is
    # after the two remaining-quantums fields in the current on-chain layout.
    is_liquidation: bool = False


@dataclass(frozen=True)
class DexOrderPlacedEvent:
    subaccount_id: DexSubaccountId
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
    # Optional client_order_id: "0x" + 32 lowercase hex chars
    # when the placer set a tag, ``None`` otherwise.
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int
    reservation_fee_rate_ppm: Optional[int] = None


@dataclass(frozen=True)
class DexOrderCancelledEvent:
    order_id: int
    owner: str
    sub_address: str
    symbol_id: int
    remaining_quantums: int
    canceled_by: int
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexOrderAmendedEvent:
    order_id: int
    owner: str
    sub_address: str
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


@dataclass(frozen=True)
class DexOrderRejectedEvent:
    order_id: int
    owner: str
    sub_address: str
    symbol_id: int
    reject_reason: int
    transaction_id: bytes
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexOrderFilledEvent:
    order_id: int
    owner: str
    sub_address: str
    symbol_id: int
    remaining_quantums: int
    basic_type: int
    side: int
    state: int
    transaction_id: bytes
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


DexConditionOrderPlacedEvent = DexOrderPlacedEvent


@dataclass(frozen=True)
class DexConditionOrderActivatedEvent:
    order_id: int
    parent_order_id: int
    owner: str
    sub_address: str
    symbol_id: int
    condition_type: int
    client_order_id: Optional[str]
    is_activated: bool
    activation_state: int
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexConditionOrderParentReboundEvent:
    order_id: int
    old_parent_order_id: int
    new_parent_order_id: int
    owner: str
    sub_address: str
    symbol_id: int
    condition_type: int
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexConditionOrderTriggeredEvent:
    order_id: int
    owner: str
    sub_address: str
    symbol_id: int
    condition_type: int
    state: int
    client_order_id: Optional[str]
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexWholePositionOcoUpdatedEvent:
    owner: str
    sub_address: str
    symbol_id: int
    position_side: int
    group_id: int
    take_profit_order_id: Optional[int]
    stop_loss_order_id: Optional[int]
    update_type: int
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexAccountEvent:
    subaccount_id: DexSubaccountId
    position_mode: int
    taker_rate: int
    maker_rate: int
    assets_size: int
    perps_size: int
    assets: List[DexAssetPosition]
    perps: List[DexPerpPosition]
    leverage_infos_size: int
    leverage_infos: List[DexSymbolLeverage]
    margin_modes_size: int
    margin_modes: List[DexSymbolMarginMode]
    parent_volume_info: DexParentVolumeInfo
    block_height: int
    timestamp: int


@dataclass(frozen=True)
class DexMarkPriceEvent:
    prices: List[DexMarkPriceInfo]
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexIndexPriceEvent:
    prices: List[DexIndexPriceInfo]
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexFundingPredictionEvent:
    predictions: List[DexFundingPredictionInfo]
    block_height: int
    block_timestamp: int


@dataclass(frozen=True)
class DexFeeStatementEvent:
    #: Storage amounts are in the native coin's smallest unit (1e-8 of a coin).
    execution_gas_units: int
    io_gas_units: int
    storage_fee: int
    storage_fee_refund: int
    total_charge_gas_units: int


@dataclass(frozen=True)
class DexAdminControlInitializedEvent:
    admin_signer_epoch: int
    admin_delay_secs: int
    admin_action_expiry_secs: int
    committee_digest: bytes


@dataclass(frozen=True)
class DexAdminControlEnabledEvent:
    enabled_at_secs: int


@dataclass(frozen=True)
class DexAdminActionScheduledEvent:
    operation_id: bytes
    payload_digest: bytes
    action_kind: int
    signer_epoch: int
    proposer: str
    scheduled_at_secs: int
    executable_at_secs: int
    expires_at_secs: int
    signature_count: int


@dataclass(frozen=True)
class DexAdminActionExecutedEvent:
    operation_id: bytes
    payload_digest: bytes
    action_kind: int
    signer_epoch: int
    executor: str
    scheduled_at_secs: int
    executable_at_secs: int
    expires_at_secs: int
    executed_at_secs: int
    signature_count: int


@dataclass(frozen=True)
class DexAdminActionCancelledEvent:
    operation_id: bytes
    payload_digest: bytes
    action_kind: int
    signer_epoch: int
    executor: str
    scheduled_at_secs: int
    executable_at_secs: int
    expires_at_secs: int
    cancelled_at_secs: int
    signature_count: int


@dataclass(frozen=True)
class DexAdminActionExpiredEvent:
    operation_id: bytes
    payload_digest: bytes
    action_kind: int
    signer_epoch: int
    executor: str
    scheduled_at_secs: int
    executable_at_secs: int
    expires_at_secs: int
    expired_at_secs: int


@dataclass(frozen=True)
class DexAdminActionInvalidatedEvent:
    operation_id: bytes
    payload_digest: bytes
    action_kind: int
    signer_epoch: int
    current_signer_epoch: int
    executor: str
    scheduled_at_secs: int
    executable_at_secs: int
    expires_at_secs: int
    invalidated_at_secs: int


@dataclass(frozen=True)
class DexAdminControlCommitteeUpdatedEvent:
    operation_id: bytes
    old_epoch: int
    new_epoch: int
    old_committee_digest: bytes
    new_committee_digest: bytes
    executed_at_secs: int


@dataclass(frozen=True)
class DexAdminControlPolicyUpdatedEvent:
    operation_id: bytes
    old_policy_epoch: int
    new_policy_epoch: int
    old_admin_delay_secs: int
    new_admin_delay_secs: int
    old_admin_action_expiry_secs: int
    new_admin_action_expiry_secs: int
    executed_at_secs: int


@dataclass(frozen=True)
class DexFeeConfigUpdatedEvent:
    old_config_digest: bytes
    new_config_digest: bytes
    signer_epoch: int


@dataclass(frozen=True)
class DexAdminControlRoleUpdatedEvent:
    operation_id: bytes
    action: int
    role_mask: int
    target_count: int
    targets_digest: bytes


@dataclass(frozen=True)
class DexSuccessEvent:
    success: bool


@dataclass(frozen=True)
class DexSetSymbolTradingPolicyEvent:
    perpetual_id: int


@dataclass(frozen=True)
class DexSetSymbolLeverageTierEvent:
    perpetual_id: int
    tier: int


@dataclass(frozen=True)
class DexSetSymbolDisplayInfoEvent:
    perpetual_id: int


@dataclass(frozen=True)
class DexSetSymbolRiskLimitsEvent:
    perpetual_id: int


@dataclass(frozen=True)
class DexSetSymbolFundingEvent:
    perpetual_id: int


@dataclass(frozen=True)
class DexSetSymbolBackstopEvent:
    perpetual_id: int


@dataclass(frozen=True)
class DexSetSymbolFeeOverrideEvent:
    perpetual_id: int


@dataclass(frozen=True)
class DexSetSymbolSpecEvent:
    perpetual_id: int


@dataclass(frozen=True)
class DexBatchSystemConfigEvent:
    total: int
    succeeded: int
    failed: int


@dataclass(frozen=True)
class DexBatchOpFailedEvent:
    index: int
    id: int
    sub_op_kind: int
    reason_code: int


@dataclass(frozen=True)
class DexSymbolOpenedEvent:
    perpetual_id: int
    listing_time: int
    opening_mark_price: int


# Delisting events. Their signed fields travel as u128
# two's-complement bits (``*_bits``) and are restored here as signed ints.
@dataclass(frozen=True)
class DexDelistingPlanSetEvent:
    """A delisting plan was created, moved or cancelled; the plan as written.

    ``t0_secs`` and ``reduce_only_at_secs`` are 0 when the plan was cancelled.
    """

    perpetual_id: int
    symbol_id: int
    plan_version: int
    t0_secs: int
    reduce_only_lead_secs: int
    twap_window_secs: int
    reduce_only_at_secs: int
    max_cancel_per_block: int
    max_settle_per_block: int
    block_height: int
    timestamp_us: int


@dataclass(frozen=True)
class DexDelistingPricedEvent:
    """A delisting market was priced, once, in the block that reached T0.

    ``price_source`` is a ``DelistingPriceSource`` value, kept as read, and
    ``expected_total_pnl`` is every position's PnL at the final price.
    """

    perpetual_id: int
    symbol_id: int
    plan_version: int
    final_price_subticks: int
    sample_weight_us: int
    price_source: int
    expected_total_pnl: int
    block_height: int
    timestamp_us: int


@dataclass(frozen=True)
class DexDelistingSettledLeg:
    """One leg of a settled account; an account's longs come before its shorts.

    ``side`` and ``margin_mode`` are ``DelistingLegSide`` and
    ``DelistingLegMarginMode`` values. ``realized_pnl`` is fee-free, and
    ``isolated_shortfall`` is always 0 on a Cross leg.
    """

    side: int
    margin_mode: int
    quantums: int
    quote_quantums: int
    realized_pnl: int
    isolated_shortfall: int


@dataclass(frozen=True)
class DexDelistingSettledEvent:
    """An account was settled at the final price, one event per account.

    ``cross_shortfall`` is what the liquidation takeover account made good.
    """

    perpetual_id: int
    symbol_id: int
    owner: str
    sub_address: str
    subaccount_number: int
    final_price_subticks: int
    legs: Tuple[DexDelistingSettledLeg, ...]
    cross_shortfall: int
    block_height: int
    timestamp_us: int


@dataclass(frozen=True)
class DexSymbolClosedEvent:
    """A delisted market closed for good: its last delisting event.

    ``realized_pnl_sum`` equals the priced event's ``expected_total_pnl``.
    """

    perpetual_id: int
    symbol_id: int
    plan_version: int
    final_price_subticks: int
    settled_accounts: int
    settled_quantums: int
    settled_quote_quantums: int
    canceled_orders: int
    realized_pnl_sum: int
    shortfall_quote: int
    block_height: int
    timestamp_us: int


# Liquidation telemetry events. Signed "bits" fields carry an i64/i128
# bit-cast to unsigned; recover the signed value with ``to_i64`` / ``to_i128``.
@dataclass(frozen=True)
class DexLiquidationTriggerMark:
    """One Mark used by the liquidation trigger predicate.

    Mirrors the on-chain liquidation trigger mark. ``mark_subticks`` of
    zero means no usable Mark was available for that symbol.
    """

    symbol_id: int
    mark_subticks: int


class _TriggerSnapshotMixin:
    """Shared accessors for the liquidation trigger snapshot tail.

    ``trigger_nc_bits`` keeps Core's raw two's-complement u128 bit pattern so the
    wire value survives untouched; ``trigger_nc`` exposes it as the signed i128 it
    actually represents. Reading the bit pattern as an unsigned integer turns a
    negative NC into a ~3.4e38 value and silently inverts ``NC < MMR``, so prefer
    ``trigger_nc`` for comparisons.
    """

    trigger_nc_bits: int

    @property
    def trigger_nc(self) -> int:
        """Trigger-time net collateral as a signed i128."""
        return to_i128(self.trigger_nc_bits)


@dataclass(frozen=True)
class DexLiquidationRiskTransferEvent(_TriggerSnapshotMixin):
    flow_instance_id: bytes
    source_risk_unit_id: bytes
    source_account: str
    sub_address: str
    subaccount_number: int
    symbol_id: int
    risk_unit_type: int
    side: int
    takeover_account: str
    quantums: int
    price: int
    fee_bits: int
    realized_pnl_bits: int
    source_residual_settled_bits: int
    source_residual_bound_quantums: int
    block_height: int
    timestamp_us: int
    action_seq: int
    tx_index: int
    # Trigger snapshot tail. Absent on pre-trigger layouts, which decode to the
    # zero values below (mirroring how a missing residual bound decodes to 0).
    trigger_nc_bits: int = 0
    trigger_mmr: int = 0
    trigger_marks: Tuple[DexLiquidationTriggerMark, ...] = ()


@dataclass(frozen=True)
class DexLiquidationDirectAdlEvent:
    flow_instance_id: bytes
    source_risk_unit_id: bytes
    source_account: str
    sub_address: str
    subaccount_number: int
    symbol_id: int
    risk_unit_type: int
    side: int
    target_quantums: int
    bankruptcy_subticks: int
    source_fee_bits: int
    source_realized_pnl_bits: int
    source_residual_settled_bits: int
    source_residual_bound_quantums: int
    block_height: int
    timestamp_us: int
    action_seq: int
    tx_index: int


class DexAdlSign(IntEnum):
    ZERO = 0
    POSITIVE = 1
    NEGATIVE = 2


class DexAdlExecutionPass(IntEnum):
    NET_EXPOSURE = 1
    HEDGE_UNWIND = 2


class DexAdlExecutionStatus(IntEnum):
    EXECUTED = 1
    PARTIAL_EXECUTED = 2
    SKIPPED = 3
    BOUNDARY = 4


class DexAdlStopReason(IntEnum):
    TARGET_FILLED = 1
    RANKED_PASSES_EXHAUSTED = 2


class DexAdlSkipReasonCode(IntEnum):
    NONE = 0
    POSITION_NOT_FOUND = 1
    INSUFFICIENT_REDUCIBLE_SIZE = 2
    SIDE_MISMATCH = 3
    ACCOUNT_STATE_CHANGED = 4
    BELOW_MIN_FILL_SIZE = 5
    OTHER_CAN_PROCESS_FAILED = 6


class DexAdlPositionSide(IntEnum):
    LONG = 1
    SHORT = 2


class DexAdlMarginMode(IntEnum):
    CROSS = 0
    ISOLATED = 1
    PORTFOLIO = 2


class DexAdlTriggerSource(IntEnum):
    LIQUIDATION_RESIDUAL = 1
    BACKSTOP_LOSS_THRESHOLD = 2
    BACKSTOP_POSITION_LIMIT = 3
    MANUAL = 4


class DexAdlSourceKind(IntEnum):
    DIRECT_LIQUIDATION = 3


@dataclass(frozen=True)
class DexAdlSignedValue:
    sign: DexAdlSign
    abs_value: int

    def __post_init__(self) -> None:
        if (self.sign == DexAdlSign.ZERO) != (self.abs_value == 0):
            raise ValueError("ADL signed value must use zero sign exactly for zero")


@dataclass(frozen=True)
class DexAdlEventId:
    trigger_block_height: int
    trigger_index_in_block: int


@dataclass(frozen=True)
class DexAdlDirectLiquidationLocator:
    block_height: int
    direct_liquidation_index_in_block: int
    flow_instance_id: bytes
    action_seq: int


@dataclass(frozen=True)
class DexAdlSourceLocator:
    source_kind: DexAdlSourceKind
    direct_liquidation_locator: Optional[DexAdlDirectLiquidationLocator]


@dataclass(frozen=True)
class DexAdlAccountLocator:
    owner_address: str
    subaccount_number: int
    sub_address: str


@dataclass(frozen=True)
class DexAdlPositionKey:
    account: DexAdlAccountLocator
    symbol_id: int
    position_side: DexAdlPositionSide
    margin_mode: DexAdlMarginMode


@dataclass(frozen=True)
class DexAdlQueueKey:
    symbol_id: int
    opponent_side: DexAdlPositionSide


@dataclass(frozen=True)
class DexAdlSelectedPrefixHeader:
    schema_version: int
    algorithm_version: int
    price_version: int
    pre_adl_state_version: int
    queue_key: DexAdlQueueKey
    trigger_source: DexAdlTriggerSource
    trigger_reasons: Tuple[DexAdlTriggerSource, ...]
    source_locator: DexAdlSourceLocator
    source_risk_holder: DexAdlAccountLocator
    original_liquidated_account: Optional[DexAdlAccountLocator]
    source_position_key: DexAdlPositionKey
    bankruptcy_subticks: int
    target_quantums: int
    total_executed_quantums: int
    stop_reason: DexAdlStopReason


@dataclass(frozen=True)
class DexAdlAuditEntry:
    schema_version: int
    audit_entry_index: int
    execution_pass: DexAdlExecutionPass
    rank_index: int
    position_key: DexAdlPositionKey
    raw_side_quantums_before: int
    opposite_side_quantums_before: int
    score_numerator_signed: DexAdlSignedValue
    score_denominator: int
    execution_status: DexAdlExecutionStatus
    executed_quantums: int
    realized_pnl_signed: DexAdlSignedValue
    skip_reason_code: DexAdlSkipReasonCode


@dataclass(frozen=True)
class DexAdlVaultTakeoverFill:
    schema_version: int
    vault_account: DexAdlAccountLocator
    leftover_quantums: int
    bankruptcy_subticks: int
    fee_charged: int


@dataclass(frozen=True)
class DexAdlExecutionEvent:
    schema_version: int
    adl_event_id: DexAdlEventId
    chunk_index: int
    total_chunks: int
    audit_entries_start_index: int
    audit_entries_end_index_exclusive: int
    selected_prefix_header: DexAdlSelectedPrefixHeader
    audit_entries: Tuple[DexAdlAuditEntry, ...]
    vault_takeover_fill: Optional[DexAdlVaultTakeoverFill]
    input_snapshot_hash: bytes
    selected_prefix_hash: bytes
    execution_fills_digest: bytes


@dataclass(frozen=True)
class DexAdlVaultInitializedEvent:
    schema_version: int
    vault_address: str
    vault_sub_address: str
    vault_config_version: int


@dataclass(frozen=True)
class DexLiquidationInternalOffsetEvent(_TriggerSnapshotMixin):
    flow_instance_id: bytes
    source_risk_unit_id: bytes
    source_account: str
    sub_address: str
    subaccount_number: int
    symbol_id: int
    risk_unit_type: int
    quantums: int
    price: int
    total_fee_bits: int
    total_realized_pnl_bits: int
    long_realized_pnl_bits: int
    short_realized_pnl_bits: int
    block_height: int
    timestamp_us: int
    action_seq: int
    tx_index: int
    trigger_nc_bits: int = 0
    trigger_mmr: int = 0
    trigger_marks: Tuple[DexLiquidationTriggerMark, ...] = ()


@dataclass(frozen=True)
class DexLiquidationFailedEvent(_TriggerSnapshotMixin):
    flow_instance_id: bytes
    source_risk_unit_id: bytes
    source_account: str
    sub_address: str
    subaccount_number: int
    # Account-level failures (no symbol) use the sentinel u32::MAX (4294967295).
    symbol_id: int
    risk_unit_type: int
    step: int
    reason_code: int
    block_height: int
    timestamp_us: int
    action_seq: int
    tx_index: int
    trigger_nc_bits: int = 0
    trigger_mmr: int = 0
    trigger_marks: Tuple[DexLiquidationTriggerMark, ...] = ()


DexEventPayload = Union[
    DexVaultInternalOffsetEvent,
    DexFillEvent,
    DexFundingRateEvent,
    DexLiquidationRiskTransferEvent,
    DexLiquidationDirectAdlEvent,
    DexAdlExecutionEvent,
    DexAdlVaultInitializedEvent,
    DexLiquidationInternalOffsetEvent,
    DexLiquidationFailedEvent,
    DexOrderPlacedEvent,
    DexOrderCancelledEvent,
    DexOrderAmendedEvent,
    DexOrderRejectedEvent,
    DexOrderFilledEvent,
    DexConditionOrderPlacedEvent,
    DexConditionOrderActivatedEvent,
    DexConditionOrderParentReboundEvent,
    DexConditionOrderTriggeredEvent,
    DexWholePositionOcoUpdatedEvent,
    DexAccountEvent,
    DexMarkPriceEvent,
    DexIndexPriceEvent,
    DexFundingPredictionEvent,
    DexSuccessEvent,
    DexSetSymbolTradingPolicyEvent,
    DexSetSymbolLeverageTierEvent,
    DexSetSymbolDisplayInfoEvent,
    DexSetSymbolRiskLimitsEvent,
    DexSetSymbolFundingEvent,
    DexSetSymbolBackstopEvent,
    DexSetSymbolFeeOverrideEvent,
    DexSetSymbolSpecEvent,
    DexBatchSystemConfigEvent,
    DexBatchOpFailedEvent,
    DexSymbolOpenedEvent,
    DexDelistingPlanSetEvent,
    DexDelistingPricedEvent,
    DexDelistingSettledEvent,
    DexSymbolClosedEvent,
    DexFeeStatementEvent,
    DexAdminControlInitializedEvent,
    DexAdminControlEnabledEvent,
    DexAdminActionScheduledEvent,
    DexAdminActionExecutedEvent,
    DexAdminActionCancelledEvent,
    DexAdminActionExpiredEvent,
    DexAdminActionInvalidatedEvent,
    DexAdminControlCommitteeUpdatedEvent,
    DexAdminControlPolicyUpdatedEvent,
    DexFeeConfigUpdatedEvent,
    DexAdminControlRoleUpdatedEvent,
    Mapping[str, Any],
]


@dataclass(frozen=True)
class DecodedDexEvent:
    event_type: str
    event: DexEventPayload


@dataclass(frozen=True)
class DecodedTransactionEvent:
    index: int
    event_type: str
    event: DexEventPayload


EVENT_TAGS: Dict[str, str] = {
    "FILL": "::dex::FillEvent",
    "FUNDING_RATE": "::dex::FundingRateEvent",
    "ORDER_PLACED": "::dex::OrderPlacedEvent",
    "ORDER_CANCELLED": "::dex::OrderCancelledEvent",
    "ORDER_AMENDED": "::dex::OrderAmendedEvent",
    "ORDER_REJECTED": "::dex::OrderRejectedEvent",
    "ORDER_FILLED": "::dex::OrderFilledEvent",
    "CONDITION_ORDER_PLACED": "::dex::ConditionOrderPlacedEvent",
    "CONDITION_ORDER_ACTIVATED": "::dex::ConditionOrderActivatedEvent",
    "CONDITION_ORDER_PARENT_REBOUND": "::dex::ConditionOrderParentReboundEvent",
    "CONDITION_ORDER_TRIGGERED": "::dex::ConditionOrderTriggeredEvent",
    "WHOLE_POSITION_OCO_UPDATED": "::dex::WholePositionOcoUpdatedEvent",
    "ACCOUNT": "::dex::AccountEvent",
    "MARK_PRICE": "::dex::MarkPriceEvent",
    "INDEX_PRICE": "::dex::IndexPriceEvent",
    "FUNDING_PREDICTION": "::dex::FundingPredictionEvent",
    "SET_SYMBOL_TRADING_POLICY": "::dex::SetSymbolTradingPolicyEvent",
    "SET_SYMBOL_LEVERAGE_TIER": "::dex::SetSymbolLeverageTierEvent",
    "SET_SYMBOL_DISPLAY_INFO": "::dex::SetSymbolDisplayInfoEvent",
    "SET_SYMBOL_RISK_LIMITS": "::dex::SetSymbolRiskLimitsEvent",
    "SET_SYMBOL_FUNDING": "::dex::SetSymbolFundingEvent",
    "SET_SYMBOL_BACKSTOP": "::dex::SetSymbolBackstopEvent",
    "SET_SYMBOL_FEE_OVERRIDE": "::dex::SetSymbolFeeOverrideEvent",
    "SET_SYMBOL_SPEC": "::dex::SetSymbolSpecEvent",
    "SYMBOL_OPENED": "::dex::SymbolOpenedEvent",
    "DELISTING_PLAN_SET": "::dex::DelistingPlanSetEvent",
    "DELISTING_PRICED": "::dex::DelistingPricedEvent",
    "DELISTING_SETTLED": "::dex::DelistingSettledEvent",
    "SYMBOL_CLOSED": "::dex::SymbolClosedEvent",
    "CREATE_SPOT": "::dex::CreateSpotEvent",
    "CREATE_PERPETUAL": "::dex::CreatePerpetualEvent",
    "UPDATE_LEVERAGE": "::dex::UpdateLeverageEvent",
    "SET_ACCOUNT_FEE_RATE": "::dex::SetAccountFeeRateEvent",
    "SET_FEE_CONFIG": "::dex::SetFeeConfigEvent",
    "UPDATE_BRIDGE_SIGNERS": "::dex::UpdateBridgeSignersEvent",
    "SET_BRIDGE_FEES": "::dex::SetBridgeFeesEvent",
    "SET_FAUCET_MINT_ENABLED": "::dex::SetFaucetMintEnabledEvent",
    "BATCH_SYSTEM_CONFIG": "::dex::BatchSystemConfigEvent",
    "BATCH_OP_FAILED": "::dex::BatchOpFailedEvent",
    "ADMIN_CONTROL_INITIALIZED": "::dex::AdminControlInitializedEvent",
    "ADMIN_CONTROL_ENABLED": "::dex::AdminControlEnabledEvent",
    "ADMIN_ACTION_SCHEDULED": "::dex::AdminActionScheduledEvent",
    "ADMIN_ACTION_EXECUTED": "::dex::AdminActionExecutedEvent",
    "ADMIN_ACTION_CANCELLED": "::dex::AdminActionCancelledEvent",
    "ADMIN_ACTION_EXPIRED": "::dex::AdminActionExpiredEvent",
    "ADMIN_ACTION_INVALIDATED": "::dex::AdminActionInvalidatedEvent",
    "ADMIN_CONTROL_ROTATED": "::dex::AdminControlRotatedEvent",
    "ADMIN_CONTROL_POLICY_UPDATED": "::dex::AdminControlPolicyUpdatedEvent",
    "ADMIN_CONTROL_LISTING_SIGNER_SET_UPDATED": "::dex::AdminControlListingSignerSetUpdatedEvent",
    "FEE_SIGNER_SET_UPDATED": "::dex::FeeSignerSetUpdatedEvent",
    "FEE_CONFIG_UPDATED": "::dex::FeeConfigUpdatedEvent",
    "ADMIN_CONTROL_ROLE_UPDATED": "::dex::AdminControlRoleUpdatedEvent",
    "LIQUIDATION_RISK_TRANSFER": "::dex::LiquidationRiskTransferEvent",
    "LIQUIDATION_DIRECT_ADL": "::dex::LiquidationDirectAdlEvent",
    "ADL_EXECUTION": "::dex::AdlExecutionEvent",
    "ADL_VAULT_INITIALIZED": "::dex::AdlVaultInitializedEvent",
    "LIQUIDATION_INTERNAL_OFFSET": "::dex::LiquidationInternalOffsetEvent",
    "LIQUIDATION_FAILED": "::dex::LiquidationFailedEvent",
    "FEE_STATEMENT": "::transaction_fee::FeeStatement",
}

_SUCCESS_EVENT_TYPES = (
    ("CREATE_SPOT", "CreateSpotEvent"),
    ("CREATE_PERPETUAL", "CreatePerpetualEvent"),
    ("UPDATE_LEVERAGE", "UpdateLeverageEvent"),
    ("SET_ACCOUNT_FEE_RATE", "SetAccountFeeRateEvent"),
    ("SET_FEE_CONFIG", "SetFeeConfigEvent"),
    ("UPDATE_BRIDGE_SIGNERS", "UpdateBridgeSignersEvent"),
    ("SET_BRIDGE_FEES", "SetBridgeFeesEvent"),
    ("SET_FAUCET_MINT_ENABLED", "SetFaucetMintEnabledEvent"),
)

_TX_INDEX_SYSTEM = 2**32 - 1
_ADL_EVENT_SCHEMA_VERSION_V5 = 5
# The chain mirrors these in its ADL execution contract. V7
# changes filled-quote settlement semantics only, V8 admits managed Vault
# accounts as ranked opponents, and V9 scopes source exclusion to the legs
# being liquidated; the schema-v5 header layout remains byte-identical across
# all of them. Callers that care read algorithm_version directly.
_ADL_ALGORITHM_VERSION_V4 = 4
_ADL_ALGORITHM_VERSION_V5 = 5
_ADL_ALGORITHM_VERSION_V6 = 6
_ADL_ALGORITHM_VERSION_V7 = 7
_ADL_ALGORITHM_VERSION_V8 = 8
_ADL_ALGORITHM_VERSION_V9 = 9
_ADL_ALGORITHM_VERSIONS_SUPPORTED = (
    _ADL_ALGORITHM_VERSION_V4,
    _ADL_ALGORITHM_VERSION_V5,
    _ADL_ALGORITHM_VERSION_V6,
    _ADL_ALGORITHM_VERSION_V7,
    _ADL_ALGORITHM_VERSION_V8,
    _ADL_ALGORITHM_VERSION_V9,
)


def _require_system_tx_index(value: int, event_name: str) -> int:
    if value != _TX_INDEX_SYSTEM:
        raise ValueError(f"{event_name} must use the system transaction index")
    return value


def to_i64(bits: int) -> int:
    """Recover a signed i64 from its unsigned u64 bit pattern."""
    return bits - 2**64 if bits >= 2**63 else bits


def to_i128(bits: int) -> int:
    """Recover a signed i128 from its unsigned u128 bit pattern."""
    return bits - 2**128 if bits >= 2**127 else bits


# Internal aliases kept so existing call sites and tests continue to work.
_to_i64 = to_i64
_to_i128 = to_i128


def _j_int(value: Any) -> int:
    """Parse a JSON integer field: JSON number, decimal string, or 0x hex."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("0x", "0X")):
            return int(text, 16)
        return int(text)
    return int(value)


def _j_exact_int(value: Any) -> int:
    """Parse an integer without coercing booleans or non-integer JSON values."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise TypeError("expected a JSON integer or integer string")
    return _j_int(value)


def _j_bytes(value: Any) -> bytes:
    text = str(value)
    if text.startswith(("0x", "0X")):
        text = text[2:]
    return bytes.fromhex(text)


def _j_address(value: Any) -> str:
    text = str(value)
    if text.startswith(("0x", "0X")):
        text = text[2:]
    text = text.rjust(AccountAddress.LENGTH * 2, "0")
    return str(AccountAddress(bytes.fromhex(text)))


def _j_option_u64(value: Any) -> Optional[int]:
    if not isinstance(value, Mapping):
        raise ValueError("invalid Move Option<u64> event field")
    vector = value.get("vec")
    if not isinstance(vector, list) or len(vector) > 1:
        raise ValueError("invalid Move Option<u64> event field")
    return None if not vector else _j_int(vector[0])


def _j_option_string(value: Any) -> Optional[str]:
    if not isinstance(value, Mapping):
        raise ValueError("invalid Move Option<String> event field")
    vector = value.get("vec")
    if not isinstance(vector, list) or len(vector) > 1:
        raise ValueError("invalid Move Option<String> event field")
    if not vector:
        return None
    if not isinstance(vector[0], str):
        raise ValueError("invalid Move Option<String> event field")
    return vector[0]


def _read_subaccount_id(deserializer: Deserializer) -> DexSubaccountId:
    return DexSubaccountId(
        address=_read_address(deserializer),
        number=deserializer.deserialize_u32(),
        sub_address=_read_address(deserializer),
        user_name=deserializer.deserialize_fixed_bytes(16),
    )


def _read_option_string(deserializer: Deserializer) -> Optional[str]:
    return deserializer.deserialize_str() if deserializer.deserialize_bool() else None


def _read_option_u64(deserializer: Deserializer) -> Optional[int]:
    return deserializer.deserialize_u64() if deserializer.deserialize_bool() else None


def _read_trailing_option_u32(deserializer: Deserializer) -> Optional[int]:
    if deserializer.remaining() == 0:
        return None
    return deserializer.deserialize_u32() if deserializer.deserialize_bool() else None


def _read_asset_position(deserializer: Deserializer) -> DexAssetPosition:
    return DexAssetPosition(
        asset_id=deserializer.deserialize_u32(),
        balance=deserializer.deserialize_i128(),
        locked=deserializer.deserialize_i128(),
    )


def _read_perp_position(deserializer: Deserializer) -> DexPerpPosition:
    return DexPerpPosition(
        perpetual_id=deserializer.deserialize_u32(),
        short_quantums=deserializer.deserialize_u64(),
        long_quantums=deserializer.deserialize_u64(),
        delta_sell_closing_long=deserializer.deserialize_i64(),
        delta_buy_opening_long=deserializer.deserialize_i64(),
        delta_sell_closing_short=deserializer.deserialize_i64(),
        delta_buy_opening_short=deserializer.deserialize_i64(),
        margin_mode=deserializer.deserialize_u32(),
        funding_index=deserializer.deserialize_i128(),
        long_position_value=deserializer.deserialize_i128(),
        short_position_value=deserializer.deserialize_i128(),
        long_imr_quota=deserializer.deserialize_i128(),
        short_imr_quota=deserializer.deserialize_i128(),
        long_mmr_quota=deserializer.deserialize_u128(),
        short_mmr_quota=deserializer.deserialize_u128(),
        long_bankrupt_price=deserializer.deserialize_i128(),
        short_bankrupt_price=deserializer.deserialize_i128(),
        long_imr_close_fee=deserializer.deserialize_u128(),
        short_imr_close_fee=deserializer.deserialize_u128(),
    )


def _read_leverage_info(deserializer: Deserializer) -> DexLeverageInfo:
    return DexLeverageInfo(
        tier=deserializer.deserialize_u8(),
        min_notional=deserializer.deserialize_i128(),
        max_notional=deserializer.deserialize_i128(),
        im_leverage=deserializer.deserialize_i32(),
        mm_leverage=deserializer.deserialize_i32(),
        exponent=deserializer.deserialize_i32(),
        maintenance_deduction=deserializer.deserialize_i64(),
    )


def _read_symbol_leverage(deserializer: Deserializer) -> DexSymbolLeverage:
    return DexSymbolLeverage(
        symbol_id=deserializer.deserialize_u32(),
        leverage_info=_read_leverage_info(deserializer),
    )


def _read_symbol_margin_mode(
    deserializer: Deserializer,
) -> DexSymbolMarginMode:
    return DexSymbolMarginMode(
        symbol_id=deserializer.deserialize_u32(),
        margin_mode=deserializer.deserialize_u8(),
    )


def _read_parent_volume_info(
    deserializer: Deserializer,
) -> DexParentVolumeInfo:
    return DexParentVolumeInfo(
        type=deserializer.deserialize_u8(),
        last_trade_timestamp_sec=deserializer.deserialize_u64(),
        cumulative_volume_usd=deserializer.deserialize_u64(),
        volume_threshold_reached=deserializer.deserialize_bool(),
    )


def _decode_fill_event(data: bytes) -> DexFillEvent:
    deserializer = Deserializer(data)
    event_fields: Dict[str, Any] = dict(
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
    remaining = deserializer.remaining()
    if remaining in (16, 17):
        event_fields["maker_remaining_quantums"] = deserializer.deserialize_u64()
        event_fields["taker_remaining_quantums"] = deserializer.deserialize_u64()
        if deserializer.remaining() == 1:
            event_fields["is_liquidation"] = deserializer.deserialize_bool()
    elif remaining == 1:
        # Historical layout after is_liquidation was added but before order
        # progress moved into FillEvent.
        event_fields["is_liquidation"] = deserializer.deserialize_bool()
    elif remaining != 0:
        raise ValueError(f"unexpected FillEvent trailing bytes: {remaining}")
    return DexFillEvent(**event_fields)


def _decode_funding_rate_event(data: bytes) -> DexFundingRateEvent:
    deserializer = Deserializer(data)
    event = DexFundingRateEvent(
        symbol_id=deserializer.deserialize_u32(),
        funding_rate_ppm=deserializer.deserialize_i32(),
        mark_price=deserializer.deserialize_u64(),
        block_height=deserializer.deserialize_u64(),
        timestamp=deserializer.deserialize_u64(),
    )
    if deserializer.remaining() != 0:
        raise ValueError(
            f"unexpected FundingRateEvent trailing bytes: {deserializer.remaining()}"
        )
    return event


def _decode_order_placed_event(data: bytes) -> DexOrderPlacedEvent:
    deserializer = Deserializer(data)
    return DexOrderPlacedEvent(
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
        # BCS Option<String>: 0x00 = None; 0x01 + length-prefixed UTF-8 = Some
        client_order_id=_read_option_string(deserializer),
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
        reservation_fee_rate_ppm=_read_trailing_option_u32(deserializer),
    )


def _decode_order_cancelled_event(data: bytes) -> DexOrderCancelledEvent:
    deserializer = Deserializer(data)
    return DexOrderCancelledEvent(
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


def _decode_order_amended_event(data: bytes) -> DexOrderAmendedEvent:
    deserializer = Deserializer(data)
    return DexOrderAmendedEvent(
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


def _decode_order_rejected_event(data: bytes) -> DexOrderRejectedEvent:
    deserializer = Deserializer(data)
    return DexOrderRejectedEvent(
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


def _decode_order_filled_event(data: bytes) -> DexOrderFilledEvent:
    deserializer = Deserializer(data)
    return DexOrderFilledEvent(
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


def _decode_condition_order_triggered_event(
    data: bytes,
) -> DexConditionOrderTriggeredEvent:
    deserializer = Deserializer(data)
    return DexConditionOrderTriggeredEvent(
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


def _decode_condition_order_activated_event(
    data: bytes,
) -> DexConditionOrderActivatedEvent:
    deserializer = Deserializer(data)
    return DexConditionOrderActivatedEvent(
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


def _decode_condition_order_activated_event_json(
    obj: Mapping[str, Any],
) -> DexConditionOrderActivatedEvent:
    is_activated = obj["is_activated"]
    if not isinstance(is_activated, bool):
        raise ValueError("invalid bool event field: is_activated")
    return DexConditionOrderActivatedEvent(
        order_id=_j_int(obj["order_id"]),
        parent_order_id=_j_int(obj["parent_order_id"]),
        owner=_j_address(obj["owner"]),
        sub_address=_j_address(obj["sub_address"]),
        symbol_id=_j_int(obj["symbol_id"]),
        condition_type=_j_int(obj["condition_type"]),
        client_order_id=_j_option_string(obj["client_order_id"]),
        is_activated=is_activated,
        activation_state=_j_int(obj["activation_state"]),
        block_height=_j_int(obj["block_height"]),
        block_timestamp=_j_int(obj["block_timestamp"]),
    )


def _decode_condition_order_parent_rebound_event(
    data: bytes,
) -> DexConditionOrderParentReboundEvent:
    deserializer = Deserializer(data)
    return DexConditionOrderParentReboundEvent(
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


def _decode_condition_order_parent_rebound_event_json(
    obj: Mapping[str, Any],
) -> DexConditionOrderParentReboundEvent:
    return DexConditionOrderParentReboundEvent(
        order_id=_j_int(obj["order_id"]),
        old_parent_order_id=_j_int(obj["old_parent_order_id"]),
        new_parent_order_id=_j_int(obj["new_parent_order_id"]),
        owner=_j_address(obj["owner"]),
        sub_address=_j_address(obj["sub_address"]),
        symbol_id=_j_int(obj["symbol_id"]),
        condition_type=_j_int(obj["condition_type"]),
        client_order_id=_j_option_string(obj["client_order_id"]),
        block_height=_j_int(obj["block_height"]),
        block_timestamp=_j_int(obj["block_timestamp"]),
    )


def _decode_whole_position_oco_updated_event(
    data: bytes,
) -> DexWholePositionOcoUpdatedEvent:
    deserializer = Deserializer(data)
    return DexWholePositionOcoUpdatedEvent(
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


def _decode_whole_position_oco_updated_event_json(
    obj: Mapping[str, Any],
) -> DexWholePositionOcoUpdatedEvent:
    return DexWholePositionOcoUpdatedEvent(
        owner=_j_address(obj["owner"]),
        sub_address=_j_address(obj["sub_address"]),
        symbol_id=_j_int(obj["symbol_id"]),
        position_side=_j_int(obj["position_side"]),
        group_id=_j_int(obj["group_id"]),
        take_profit_order_id=_j_option_u64(obj["take_profit_order_id"]),
        stop_loss_order_id=_j_option_u64(obj["stop_loss_order_id"]),
        update_type=_j_int(obj["update_type"]),
        block_height=_j_int(obj["block_height"]),
        block_timestamp=_j_int(obj["block_timestamp"]),
    )


def _decode_account_event(data: bytes) -> DexAccountEvent:
    deserializer = Deserializer(data)
    subaccount_id = _read_subaccount_id(deserializer)
    position_mode = deserializer.deserialize_u32()
    taker_rate = deserializer.deserialize_i32()
    maker_rate = deserializer.deserialize_i32()
    assets_size = deserializer.deserialize_u32()
    perps_size = deserializer.deserialize_u32()
    assets = deserializer.deserialize_vector(_read_asset_position)
    perps = deserializer.deserialize_vector(_read_perp_position)
    leverage_infos_size = deserializer.deserialize_u32()
    leverage_infos = deserializer.deserialize_vector(_read_symbol_leverage)
    margin_modes_size = deserializer.deserialize_u32()
    margin_modes = deserializer.deserialize_vector(_read_symbol_margin_mode)
    parent_volume_info = _read_parent_volume_info(deserializer)
    return DexAccountEvent(
        subaccount_id=subaccount_id,
        position_mode=position_mode,
        taker_rate=taker_rate,
        maker_rate=maker_rate,
        assets_size=assets_size,
        perps_size=perps_size,
        assets=assets,
        perps=perps,
        leverage_infos_size=leverage_infos_size,
        leverage_infos=leverage_infos,
        margin_modes_size=margin_modes_size,
        margin_modes=margin_modes,
        parent_volume_info=parent_volume_info,
        block_height=deserializer.deserialize_u64(),
        timestamp=deserializer.deserialize_u64(),
    )


def _decode_mark_price_event(data: bytes) -> DexMarkPriceEvent:
    deserializer = Deserializer(data)
    length = deserializer.deserialize_u32_from_uleb128()
    prices = [
        DexMarkPriceInfo(
            symbol_id=deserializer.deserialize_u32(),
            mark_price=deserializer.deserialize_u64(),
            exponent=deserializer.deserialize_i32(),
        )
        for _ in range(length)
    ]
    return DexMarkPriceEvent(
        prices=prices,
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


def _decode_index_price_event(data: bytes) -> DexIndexPriceEvent:
    deserializer = Deserializer(data)
    length = deserializer.deserialize_u32_from_uleb128()
    prices = [
        DexIndexPriceInfo(
            symbol_id=deserializer.deserialize_u32(),
            index_price=deserializer.deserialize_u64(),
            exponent=deserializer.deserialize_i32(),
        )
        for _ in range(length)
    ]
    return DexIndexPriceEvent(
        prices=prices,
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


def _decode_funding_prediction_event(
    data: bytes,
) -> DexFundingPredictionEvent:
    deserializer = Deserializer(data)
    length = deserializer.deserialize_u32_from_uleb128()
    predictions = [
        DexFundingPredictionInfo(
            symbol_id=deserializer.deserialize_u32(),
            funding_rate_ppm=deserializer.deserialize_i32(),
            timestamp=deserializer.deserialize_u64(),
        )
        for _ in range(length)
    ]
    return DexFundingPredictionEvent(
        predictions=predictions,
        block_height=deserializer.deserialize_u64(),
        block_timestamp=deserializer.deserialize_u64(),
    )


def _decode_fee_statement_event(data: bytes) -> DexFeeStatementEvent:
    deserializer = Deserializer(data)
    return DexFeeStatementEvent(
        execution_gas_units=deserializer.deserialize_u64(),
        io_gas_units=deserializer.deserialize_u64(),
        storage_fee=deserializer.deserialize_u64(),
        storage_fee_refund=deserializer.deserialize_u64(),
        total_charge_gas_units=deserializer.deserialize_u64(),
    )


def _decode_admin_control_initialized_event(data: bytes) -> DexAdminControlInitializedEvent:
    deserializer = Deserializer(data)
    return DexAdminControlInitializedEvent(
        admin_signer_epoch=deserializer.deserialize_u64(),
        admin_delay_secs=deserializer.deserialize_u64(),
        admin_action_expiry_secs=deserializer.deserialize_u64(),
        committee_digest=deserializer.deserialize_bytes(),
    )


def _decode_adl_vault_initialized_event(
    data: bytes,
) -> DexAdlVaultInitializedEvent:
    deserializer = Deserializer(data)
    event = DexAdlVaultInitializedEvent(
        schema_version=deserializer.deserialize_u16(),
        vault_address=_read_address(deserializer),
        vault_sub_address=_read_address(deserializer),
        vault_config_version=deserializer.deserialize_u64(),
    )
    if deserializer.remaining() != 0:
        raise ValueError("AdlVaultInitializedEvent has trailing bytes")
    return event


def _decode_admin_control_enabled_event(data: bytes) -> DexAdminControlEnabledEvent:
    return DexAdminControlEnabledEvent(enabled_at_secs=Deserializer(data).deserialize_u64())


def _decode_admin_action_scheduled_event(
    data: bytes,
) -> DexAdminActionScheduledEvent:
    deserializer = Deserializer(data)
    return DexAdminActionScheduledEvent(
        operation_id=deserializer.deserialize_bytes(),
        payload_digest=deserializer.deserialize_bytes(),
        action_kind=deserializer.deserialize_u8(),
        signer_epoch=deserializer.deserialize_u64(),
        proposer=_read_address(deserializer),
        scheduled_at_secs=deserializer.deserialize_u64(),
        executable_at_secs=deserializer.deserialize_u64(),
        expires_at_secs=deserializer.deserialize_u64(),
        signature_count=deserializer.deserialize_u8(),
    )


def _decode_admin_action_executed_event(
    data: bytes,
) -> DexAdminActionExecutedEvent:
    deserializer = Deserializer(data)
    return DexAdminActionExecutedEvent(
        operation_id=deserializer.deserialize_bytes(),
        payload_digest=deserializer.deserialize_bytes(),
        action_kind=deserializer.deserialize_u8(),
        signer_epoch=deserializer.deserialize_u64(),
        executor=_read_address(deserializer),
        scheduled_at_secs=deserializer.deserialize_u64(),
        executable_at_secs=deserializer.deserialize_u64(),
        expires_at_secs=deserializer.deserialize_u64(),
        executed_at_secs=deserializer.deserialize_u64(),
        signature_count=deserializer.deserialize_u8(),
    )


def _decode_admin_action_cancelled_event(
    data: bytes,
) -> DexAdminActionCancelledEvent:
    deserializer = Deserializer(data)
    return DexAdminActionCancelledEvent(
        operation_id=deserializer.deserialize_bytes(),
        payload_digest=deserializer.deserialize_bytes(),
        action_kind=deserializer.deserialize_u8(),
        signer_epoch=deserializer.deserialize_u64(),
        executor=_read_address(deserializer),
        scheduled_at_secs=deserializer.deserialize_u64(),
        executable_at_secs=deserializer.deserialize_u64(),
        expires_at_secs=deserializer.deserialize_u64(),
        cancelled_at_secs=deserializer.deserialize_u64(),
        signature_count=deserializer.deserialize_u8(),
    )


def _decode_admin_action_expired_event(data: bytes) -> DexAdminActionExpiredEvent:
    deserializer = Deserializer(data)
    return DexAdminActionExpiredEvent(
        operation_id=deserializer.deserialize_bytes(),
        payload_digest=deserializer.deserialize_bytes(),
        action_kind=deserializer.deserialize_u8(),
        signer_epoch=deserializer.deserialize_u64(),
        executor=_read_address(deserializer),
        scheduled_at_secs=deserializer.deserialize_u64(),
        executable_at_secs=deserializer.deserialize_u64(),
        expires_at_secs=deserializer.deserialize_u64(),
        expired_at_secs=deserializer.deserialize_u64(),
    )


def _decode_admin_action_invalidated_event(
    data: bytes,
) -> DexAdminActionInvalidatedEvent:
    deserializer = Deserializer(data)
    return DexAdminActionInvalidatedEvent(
        operation_id=deserializer.deserialize_bytes(),
        payload_digest=deserializer.deserialize_bytes(),
        action_kind=deserializer.deserialize_u8(),
        signer_epoch=deserializer.deserialize_u64(),
        current_signer_epoch=deserializer.deserialize_u64(),
        executor=_read_address(deserializer),
        scheduled_at_secs=deserializer.deserialize_u64(),
        executable_at_secs=deserializer.deserialize_u64(),
        expires_at_secs=deserializer.deserialize_u64(),
        invalidated_at_secs=deserializer.deserialize_u64(),
    )


def _decode_admin_control_committee_updated_event(
    data: bytes,
) -> DexAdminControlCommitteeUpdatedEvent:
    deserializer = Deserializer(data)
    return DexAdminControlCommitteeUpdatedEvent(
        operation_id=deserializer.deserialize_bytes(),
        old_epoch=deserializer.deserialize_u64(),
        new_epoch=deserializer.deserialize_u64(),
        old_committee_digest=deserializer.deserialize_bytes(),
        new_committee_digest=deserializer.deserialize_bytes(),
        executed_at_secs=deserializer.deserialize_u64(),
    )


def _decode_admin_control_policy_updated_event(
    data: bytes,
) -> DexAdminControlPolicyUpdatedEvent:
    deserializer = Deserializer(data)
    return DexAdminControlPolicyUpdatedEvent(
        operation_id=deserializer.deserialize_bytes(),
        old_policy_epoch=deserializer.deserialize_u64(),
        new_policy_epoch=deserializer.deserialize_u64(),
        old_admin_delay_secs=deserializer.deserialize_u64(),
        new_admin_delay_secs=deserializer.deserialize_u64(),
        old_admin_action_expiry_secs=deserializer.deserialize_u64(),
        new_admin_action_expiry_secs=deserializer.deserialize_u64(),
        executed_at_secs=deserializer.deserialize_u64(),
    )


def _decode_fee_config_updated_event(data: bytes) -> DexFeeConfigUpdatedEvent:
    deserializer = Deserializer(data)
    return DexFeeConfigUpdatedEvent(
        old_config_digest=deserializer.deserialize_bytes(),
        new_config_digest=deserializer.deserialize_bytes(),
        signer_epoch=deserializer.deserialize_u64(),
    )


def _decode_admin_control_role_updated_event(data: bytes) -> DexAdminControlRoleUpdatedEvent:
    deserializer = Deserializer(data)
    operation_id = deserializer.deserialize_bytes()
    action = deserializer.deserialize_u32_from_uleb128()
    role_mask = deserializer.deserialize_u64()
    target_count = deserializer.deserialize_u32()
    targets_digest = deserializer.deserialize_bytes()
    return DexAdminControlRoleUpdatedEvent(
        operation_id=operation_id,
        action=action,
        role_mask=role_mask,
        target_count=target_count,
        targets_digest=targets_digest,
    )


def _decode_success_event(data: bytes) -> DexSuccessEvent:
    deserializer = Deserializer(data)
    return DexSuccessEvent(success=deserializer.deserialize_bool())


def _decode_set_symbol_trading_policy_event(
    data: bytes,
) -> DexSetSymbolTradingPolicyEvent:
    deserializer = Deserializer(data)
    return DexSetSymbolTradingPolicyEvent(perpetual_id=deserializer.deserialize_u32())


def _decode_set_symbol_leverage_tier_event(
    data: bytes,
) -> DexSetSymbolLeverageTierEvent:
    deserializer = Deserializer(data)
    return DexSetSymbolLeverageTierEvent(
        perpetual_id=deserializer.deserialize_u32(),
        tier=deserializer.deserialize_u32(),
    )


def _decode_set_symbol_display_info_event(
    data: bytes,
) -> DexSetSymbolDisplayInfoEvent:
    deserializer = Deserializer(data)
    return DexSetSymbolDisplayInfoEvent(perpetual_id=deserializer.deserialize_u32())


def _decode_set_symbol_risk_limits_event(
    data: bytes,
) -> DexSetSymbolRiskLimitsEvent:
    deserializer = Deserializer(data)
    return DexSetSymbolRiskLimitsEvent(perpetual_id=deserializer.deserialize_u32())


def _decode_set_symbol_funding_event(data: bytes) -> DexSetSymbolFundingEvent:
    deserializer = Deserializer(data)
    return DexSetSymbolFundingEvent(perpetual_id=deserializer.deserialize_u32())


def _decode_set_symbol_backstop_event(data: bytes) -> DexSetSymbolBackstopEvent:
    deserializer = Deserializer(data)
    return DexSetSymbolBackstopEvent(perpetual_id=deserializer.deserialize_u32())


def _decode_set_symbol_fee_override_event(
    data: bytes,
) -> DexSetSymbolFeeOverrideEvent:
    deserializer = Deserializer(data)
    return DexSetSymbolFeeOverrideEvent(perpetual_id=deserializer.deserialize_u32())


def _decode_set_symbol_spec_event(data: bytes) -> DexSetSymbolSpecEvent:
    deserializer = Deserializer(data)
    return DexSetSymbolSpecEvent(perpetual_id=deserializer.deserialize_u32())


def _decode_batch_system_config_event(data: bytes) -> DexBatchSystemConfigEvent:
    deserializer = Deserializer(data)
    return DexBatchSystemConfigEvent(
        total=deserializer.deserialize_u32(),
        succeeded=deserializer.deserialize_u32(),
        failed=deserializer.deserialize_u32(),
    )


def _decode_batch_op_failed_event(data: bytes) -> DexBatchOpFailedEvent:
    deserializer = Deserializer(data)
    return DexBatchOpFailedEvent(
        index=deserializer.deserialize_u32(),
        id=deserializer.deserialize_u32(),
        sub_op_kind=deserializer.deserialize_u8(),
        reason_code=deserializer.deserialize_u64(),
    )


def _decode_symbol_opened_event(data: bytes) -> DexSymbolOpenedEvent:
    deserializer = Deserializer(data)
    return DexSymbolOpenedEvent(
        perpetual_id=deserializer.deserialize_u32(),
        listing_time=deserializer.deserialize_u64(),
        opening_mark_price=deserializer.deserialize_u64(),
    )


# The delisting decoders read the fields the chain defines and ignore whatever
# follows, unlike most decoders here: a later version of these events only
# appends fields.


def _decode_delisting_plan_set_event(data: bytes) -> DexDelistingPlanSetEvent:
    deserializer = Deserializer(data)
    return DexDelistingPlanSetEvent(
        perpetual_id=deserializer.deserialize_u32(),
        symbol_id=deserializer.deserialize_u32(),
        plan_version=deserializer.deserialize_u32(),
        t0_secs=deserializer.deserialize_u64(),
        reduce_only_lead_secs=deserializer.deserialize_u32(),
        twap_window_secs=deserializer.deserialize_u32(),
        reduce_only_at_secs=deserializer.deserialize_u64(),
        max_cancel_per_block=deserializer.deserialize_u32(),
        max_settle_per_block=deserializer.deserialize_u32(),
        block_height=deserializer.deserialize_u64(),
        timestamp_us=deserializer.deserialize_u64(),
    )


def _decode_delisting_priced_event(data: bytes) -> DexDelistingPricedEvent:
    deserializer = Deserializer(data)
    return DexDelistingPricedEvent(
        perpetual_id=deserializer.deserialize_u32(),
        symbol_id=deserializer.deserialize_u32(),
        plan_version=deserializer.deserialize_u32(),
        final_price_subticks=deserializer.deserialize_u64(),
        sample_weight_us=deserializer.deserialize_u64(),
        price_source=deserializer.deserialize_u8(),
        expected_total_pnl=deserializer.deserialize_i128(),
        block_height=deserializer.deserialize_u64(),
        timestamp_us=deserializer.deserialize_u64(),
    )


def _read_delisting_settled_leg(deserializer: Deserializer) -> DexDelistingSettledLeg:
    return DexDelistingSettledLeg(
        side=deserializer.deserialize_u8(),
        margin_mode=deserializer.deserialize_u8(),
        quantums=deserializer.deserialize_u64(),
        quote_quantums=deserializer.deserialize_u128(),
        realized_pnl=deserializer.deserialize_i128(),
        isolated_shortfall=deserializer.deserialize_u128(),
    )


def _decode_delisting_settled_event(data: bytes) -> DexDelistingSettledEvent:
    deserializer = Deserializer(data)
    return DexDelistingSettledEvent(
        perpetual_id=deserializer.deserialize_u32(),
        symbol_id=deserializer.deserialize_u32(),
        owner=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        subaccount_number=deserializer.deserialize_u32(),
        final_price_subticks=deserializer.deserialize_u64(),
        legs=tuple(deserializer.deserialize_vector(_read_delisting_settled_leg)),
        cross_shortfall=deserializer.deserialize_u128(),
        block_height=deserializer.deserialize_u64(),
        timestamp_us=deserializer.deserialize_u64(),
    )


def _decode_symbol_closed_event(data: bytes) -> DexSymbolClosedEvent:
    deserializer = Deserializer(data)
    return DexSymbolClosedEvent(
        perpetual_id=deserializer.deserialize_u32(),
        symbol_id=deserializer.deserialize_u32(),
        plan_version=deserializer.deserialize_u32(),
        final_price_subticks=deserializer.deserialize_u64(),
        settled_accounts=deserializer.deserialize_u64(),
        settled_quantums=deserializer.deserialize_u128(),
        settled_quote_quantums=deserializer.deserialize_u128(),
        canceled_orders=deserializer.deserialize_u64(),
        realized_pnl_sum=deserializer.deserialize_i128(),
        shortfall_quote=deserializer.deserialize_u128(),
        block_height=deserializer.deserialize_u64(),
        timestamp_us=deserializer.deserialize_u64(),
    )


# The same events as a chain with their Move mirrors renders them over REST:
# u64 and u128 as decimal strings, u8 and u32 as numbers, and the signed fields
# under their ``*_bits`` names as the unsigned reading of the bits.


def _decode_delisting_plan_set_event_json(
    obj: Mapping[str, Any],
) -> DexDelistingPlanSetEvent:
    return DexDelistingPlanSetEvent(
        perpetual_id=_j_int(obj["perpetual_id"]),
        symbol_id=_j_int(obj["symbol_id"]),
        plan_version=_j_int(obj["plan_version"]),
        t0_secs=_j_int(obj["t0_secs"]),
        reduce_only_lead_secs=_j_int(obj["reduce_only_lead_secs"]),
        twap_window_secs=_j_int(obj["twap_window_secs"]),
        reduce_only_at_secs=_j_int(obj["reduce_only_at_secs"]),
        max_cancel_per_block=_j_int(obj["max_cancel_per_block"]),
        max_settle_per_block=_j_int(obj["max_settle_per_block"]),
        block_height=_j_int(obj["block_height"]),
        timestamp_us=_j_int(obj["timestamp_us"]),
    )


def _decode_delisting_priced_event_json(
    obj: Mapping[str, Any],
) -> DexDelistingPricedEvent:
    return DexDelistingPricedEvent(
        perpetual_id=_j_int(obj["perpetual_id"]),
        symbol_id=_j_int(obj["symbol_id"]),
        plan_version=_j_int(obj["plan_version"]),
        final_price_subticks=_j_int(obj["final_price_subticks"]),
        sample_weight_us=_j_int(obj["sample_weight_us"]),
        price_source=_j_int(obj["price_source"]),
        expected_total_pnl=to_i128(_j_int(obj["expected_total_pnl_bits"])),
        block_height=_j_int(obj["block_height"]),
        timestamp_us=_j_int(obj["timestamp_us"]),
    )


def _json_delisting_settled_leg(leg: Mapping[str, Any]) -> DexDelistingSettledLeg:
    return DexDelistingSettledLeg(
        side=_j_int(leg["side"]),
        margin_mode=_j_int(leg["margin_mode"]),
        quantums=_j_int(leg["quantums"]),
        quote_quantums=_j_int(leg["quote_quantums"]),
        realized_pnl=to_i128(_j_int(leg["realized_pnl_bits"])),
        isolated_shortfall=_j_int(leg["isolated_shortfall"]),
    )


def _decode_delisting_settled_event_json(
    obj: Mapping[str, Any],
) -> DexDelistingSettledEvent:
    legs = obj["legs"]
    if not isinstance(legs, list):
        raise ValueError("DelistingSettledEvent legs must be a list")
    return DexDelistingSettledEvent(
        perpetual_id=_j_int(obj["perpetual_id"]),
        symbol_id=_j_int(obj["symbol_id"]),
        owner=_j_address(obj["owner"]),
        sub_address=_j_address(obj["sub_address"]),
        subaccount_number=_j_int(obj["subaccount_number"]),
        final_price_subticks=_j_int(obj["final_price_subticks"]),
        legs=tuple(_json_delisting_settled_leg(leg) for leg in legs),
        cross_shortfall=_j_int(obj["cross_shortfall"]),
        block_height=_j_int(obj["block_height"]),
        timestamp_us=_j_int(obj["timestamp_us"]),
    )


def _decode_symbol_closed_event_json(obj: Mapping[str, Any]) -> DexSymbolClosedEvent:
    return DexSymbolClosedEvent(
        perpetual_id=_j_int(obj["perpetual_id"]),
        symbol_id=_j_int(obj["symbol_id"]),
        plan_version=_j_int(obj["plan_version"]),
        final_price_subticks=_j_int(obj["final_price_subticks"]),
        settled_accounts=_j_int(obj["settled_accounts"]),
        settled_quantums=_j_int(obj["settled_quantums"]),
        settled_quote_quantums=_j_int(obj["settled_quote_quantums"]),
        canceled_orders=_j_int(obj["canceled_orders"]),
        realized_pnl_sum=to_i128(_j_int(obj["realized_pnl_sum_bits"])),
        shortfall_quote=_j_int(obj["shortfall_quote"]),
        block_height=_j_int(obj["block_height"]),
        timestamp_us=_j_int(obj["timestamp_us"]),
    )


def _read_liquidation_trigger_mark(
    deserializer: Deserializer,
) -> DexLiquidationTriggerMark:
    return DexLiquidationTriggerMark(
        symbol_id=deserializer.deserialize_u32(),
        mark_subticks=deserializer.deserialize_u64(),
    )


def _read_liquidation_trigger_snapshot(
    deserializer: Deserializer, event_name: str
) -> Tuple[int, int, Tuple[DexLiquidationTriggerMark, ...]]:
    """Read the optional trigger snapshot that terminates a liquidation event.

    Pre-trigger layouts end right after ``tx_index``; those decode to zero values.
    Anything else must be a complete snapshot that consumes the payload exactly --
    a partial or unrecognised tail raises instead of being silently dropped.
    """
    if deserializer.remaining() == 0:
        return 0, 0, ()
    trigger_nc_bits = deserializer.deserialize_u128()
    trigger_mmr = deserializer.deserialize_u128()
    trigger_marks = tuple(deserializer.deserialize_vector(_read_liquidation_trigger_mark))
    if deserializer.remaining() != 0:
        raise ValueError(f"{event_name} has trailing bytes after its trigger snapshot")
    return trigger_nc_bits, trigger_mmr, trigger_marks


def _json_liquidation_trigger_snapshot(
    obj: Mapping[str, Any],
) -> Tuple[int, int, Tuple[DexLiquidationTriggerMark, ...]]:
    """Read the trigger snapshot from the Move-ABI JSON form.

    Absent keys mean a pre-trigger event, matching the BCS path's zero values.
    """
    if "trigger_nc_bits" not in obj:
        return 0, 0, ()
    trigger_marks = tuple(
        DexLiquidationTriggerMark(
            symbol_id=_j_int(mark["symbol_id"]),
            mark_subticks=_j_int(mark["mark_subticks"]),
        )
        for mark in obj.get("trigger_marks", ())
    )
    return (
        _j_int(obj["trigger_nc_bits"]),
        _j_int(obj["trigger_mmr"]),
        trigger_marks,
    )


def _decode_liquidation_risk_transfer_tail(
    data: bytes,
) -> Tuple[
    int,
    int,
    int,
    int,
    int,
    int,
    int,
    Tuple[DexLiquidationTriggerMark, ...],
]:
    """Decode the two shipped RiskTransfer tails without guessing.

    Release/v2.3 appends the trigger snapshot directly after ``tx_index``;
    current main inserts ``source_residual_bound_quantums`` before the common
    block coordinates.  The snapshot vector makes both tails variable length,
    so each known layout is parsed independently and exactly one must consume
    the payload.
    """

    candidates = []
    for has_residual_bound in (False, True):
        deserializer = Deserializer(data)
        try:
            source_residual_bound_quantums = (
                deserializer.deserialize_u64() if has_residual_bound else 0
            )
            block_height = deserializer.deserialize_u64()
            timestamp_us = deserializer.deserialize_u64()
            action_seq = deserializer.deserialize_u32()
            tx_index = _require_system_tx_index(
                deserializer.deserialize_u32(), "LiquidationRiskTransferEvent"
            )
            (
                trigger_nc_bits,
                trigger_mmr,
                trigger_marks,
            ) = _read_liquidation_trigger_snapshot(
                deserializer, "LiquidationRiskTransferEvent"
            )
        except Exception:
            continue
        candidates.append(
            (
                source_residual_bound_quantums,
                block_height,
                timestamp_us,
                action_seq,
                tx_index,
                trigger_nc_bits,
                trigger_mmr,
                trigger_marks,
            )
        )

    if len(candidates) != 1:
        raise ValueError(
            "LiquidationRiskTransferEvent has an unsupported or ambiguous trailing layout"
        )
    return candidates[0]


def _decode_liquidation_risk_transfer_event(
    data: bytes,
) -> DexLiquidationRiskTransferEvent:
    deserializer = Deserializer(data)
    flow_instance_id = deserializer.deserialize_bytes()
    source_risk_unit_id = deserializer.deserialize_bytes()
    source_account = _read_address(deserializer)
    sub_address = _read_address(deserializer)
    subaccount_number = deserializer.deserialize_u32()
    symbol_id = deserializer.deserialize_u32()
    risk_unit_type = deserializer.deserialize_u8()
    side = deserializer.deserialize_u8()
    takeover_account = _read_address(deserializer)
    quantums = deserializer.deserialize_u64()
    price = deserializer.deserialize_u64()
    fee_bits = deserializer.deserialize_u64()
    realized_pnl_bits = deserializer.deserialize_u64()
    source_residual_settled_bits = deserializer.deserialize_u64()
    (
        source_residual_bound_quantums,
        block_height,
        timestamp_us,
        action_seq,
        tx_index,
        trigger_nc_bits,
        trigger_mmr,
        trigger_marks,
    ) = _decode_liquidation_risk_transfer_tail(
        deserializer.deserialize_fixed_bytes(deserializer.remaining())
    )
    return DexLiquidationRiskTransferEvent(
        flow_instance_id=flow_instance_id,
        source_risk_unit_id=source_risk_unit_id,
        source_account=source_account,
        sub_address=sub_address,
        subaccount_number=subaccount_number,
        symbol_id=symbol_id,
        risk_unit_type=risk_unit_type,
        side=side,
        takeover_account=takeover_account,
        quantums=quantums,
        price=price,
        fee_bits=fee_bits,
        realized_pnl_bits=realized_pnl_bits,
        source_residual_settled_bits=source_residual_settled_bits,
        source_residual_bound_quantums=source_residual_bound_quantums,
        block_height=block_height,
        timestamp_us=timestamp_us,
        action_seq=action_seq,
        tx_index=tx_index,
        trigger_nc_bits=trigger_nc_bits,
        trigger_mmr=trigger_mmr,
        trigger_marks=trigger_marks,
    )


def _decode_liquidation_risk_transfer_event_json(
    obj: Mapping[str, Any],
) -> DexLiquidationRiskTransferEvent:
    (
        trigger_nc_bits,
        trigger_mmr,
        trigger_marks,
    ) = _json_liquidation_trigger_snapshot(obj)
    return DexLiquidationRiskTransferEvent(
        flow_instance_id=_j_bytes(obj["flow_instance_id"]),
        source_risk_unit_id=_j_bytes(obj["source_risk_unit_id"]),
        source_account=_j_address(obj["source_account"]),
        sub_address=_j_address(obj["sub_address"]),
        subaccount_number=_j_int(obj["subaccount_number"]),
        symbol_id=_j_int(obj["symbol_id"]),
        risk_unit_type=_j_int(obj["risk_unit_type"]),
        side=_j_int(obj["side"]),
        takeover_account=_j_address(obj["takeover_account"]),
        quantums=_j_int(obj["quantums"]),
        price=_j_int(obj["price"]),
        fee_bits=_j_int(obj["fee_bits"]),
        realized_pnl_bits=_j_int(obj["realized_pnl_bits"]),
        source_residual_settled_bits=_j_int(obj.get("source_residual_settled_bits", 0)),
        source_residual_bound_quantums=_j_int(
            obj.get("source_residual_bound_quantums", 0)
        ),
        block_height=_j_int(obj["block_height"]),
        timestamp_us=_j_int(obj["timestamp_us"]),
        action_seq=_j_int(obj["action_seq"]),
        tx_index=_require_system_tx_index(
            _j_int(obj["tx_index"]), "LiquidationRiskTransferEvent"
        ),
        trigger_nc_bits=trigger_nc_bits,
        trigger_mmr=trigger_mmr,
        trigger_marks=trigger_marks,
    )


def _decode_liquidation_direct_adl_event(
    data: bytes,
) -> DexLiquidationDirectAdlEvent:
    deserializer = Deserializer(data)
    event = DexLiquidationDirectAdlEvent(
        flow_instance_id=deserializer.deserialize_bytes(),
        source_risk_unit_id=deserializer.deserialize_bytes(),
        source_account=_read_address(deserializer),
        sub_address=_read_address(deserializer),
        subaccount_number=deserializer.deserialize_u32(),
        symbol_id=deserializer.deserialize_u32(),
        risk_unit_type=deserializer.deserialize_u8(),
        side=deserializer.deserialize_u8(),
        target_quantums=deserializer.deserialize_u64(),
        bankruptcy_subticks=deserializer.deserialize_u64(),
        source_fee_bits=deserializer.deserialize_u64(),
        source_realized_pnl_bits=deserializer.deserialize_u64(),
        source_residual_settled_bits=deserializer.deserialize_u64(),
        source_residual_bound_quantums=deserializer.deserialize_u64(),
        block_height=deserializer.deserialize_u64(),
        timestamp_us=deserializer.deserialize_u64(),
        action_seq=deserializer.deserialize_u32(),
        tx_index=deserializer.deserialize_u32(),
    )
    if deserializer.remaining() != 0:
        raise ValueError("LiquidationDirectAdlEvent has trailing bytes")
    return event


def _decode_liquidation_direct_adl_event_json(
    obj: Mapping[str, Any],
) -> DexLiquidationDirectAdlEvent:
    return DexLiquidationDirectAdlEvent(
        flow_instance_id=_j_bytes(obj["flow_instance_id"]),
        source_risk_unit_id=_j_bytes(obj["source_risk_unit_id"]),
        source_account=_j_address(obj["source_account"]),
        sub_address=_j_address(obj["sub_address"]),
        subaccount_number=_j_exact_int(obj["subaccount_number"]),
        symbol_id=_j_exact_int(obj["symbol_id"]),
        risk_unit_type=_j_exact_int(obj["risk_unit_type"]),
        side=_j_exact_int(obj["side"]),
        target_quantums=_j_exact_int(obj["target_quantums"]),
        bankruptcy_subticks=_j_exact_int(obj["bankruptcy_subticks"]),
        source_fee_bits=_j_exact_int(obj["source_fee_bits"]),
        source_realized_pnl_bits=_j_exact_int(obj["source_realized_pnl_bits"]),
        source_residual_settled_bits=_j_exact_int(obj["source_residual_settled_bits"]),
        source_residual_bound_quantums=_j_exact_int(
            obj["source_residual_bound_quantums"]
        ),
        block_height=_j_exact_int(obj["block_height"]),
        timestamp_us=_j_exact_int(obj["timestamp_us"]),
        action_seq=_j_exact_int(obj["action_seq"]),
        tx_index=_j_exact_int(obj["tx_index"]),
    )


def _read_adl_signed_value(deserializer: Deserializer) -> DexAdlSignedValue:
    return DexAdlSignedValue(
        sign=DexAdlSign(deserializer.deserialize_u8()),
        abs_value=deserializer.deserialize_u128(),
    )


def _read_adl_event_id(deserializer: Deserializer) -> DexAdlEventId:
    return DexAdlEventId(
        trigger_block_height=deserializer.deserialize_u64(),
        trigger_index_in_block=deserializer.deserialize_u64(),
    )


def _read_adl_direct_liquidation_locator(
    deserializer: Deserializer,
) -> DexAdlDirectLiquidationLocator:
    return DexAdlDirectLiquidationLocator(
        block_height=deserializer.deserialize_u64(),
        direct_liquidation_index_in_block=deserializer.deserialize_u64(),
        flow_instance_id=deserializer.deserialize_fixed_bytes(32),
        action_seq=deserializer.deserialize_u32(),
    )


def _read_adl_source_locator(
    deserializer: Deserializer,
) -> DexAdlSourceLocator:
    source_kind = DexAdlSourceKind(deserializer.deserialize_u8())
    direct_liquidation_locator = (
        _read_adl_direct_liquidation_locator(deserializer)
        if deserializer.deserialize_bool()
        else None
    )
    return DexAdlSourceLocator(
        source_kind=source_kind,
        direct_liquidation_locator=direct_liquidation_locator,
    )


def _read_adl_account_locator(
    deserializer: Deserializer,
) -> DexAdlAccountLocator:
    return DexAdlAccountLocator(
        owner_address=_read_address(deserializer),
        subaccount_number=deserializer.deserialize_u32(),
        sub_address=_read_address(deserializer),
    )


def _read_adl_position_key(deserializer: Deserializer) -> DexAdlPositionKey:
    return DexAdlPositionKey(
        account=_read_adl_account_locator(deserializer),
        symbol_id=deserializer.deserialize_u32(),
        position_side=DexAdlPositionSide(deserializer.deserialize_u8()),
        margin_mode=DexAdlMarginMode(deserializer.deserialize_u8()),
    )


def _read_adl_queue_key(deserializer: Deserializer) -> DexAdlQueueKey:
    return DexAdlQueueKey(
        symbol_id=deserializer.deserialize_u32(),
        opponent_side=DexAdlPositionSide(deserializer.deserialize_u8()),
    )


def _read_adl_selected_prefix_header(
    deserializer: Deserializer,
) -> DexAdlSelectedPrefixHeader:
    schema_version = deserializer.deserialize_u16()
    algorithm_version = deserializer.deserialize_u64()
    price_version = deserializer.deserialize_u64()
    pre_adl_state_version = deserializer.deserialize_u64()
    queue_key = _read_adl_queue_key(deserializer)
    trigger_source = DexAdlTriggerSource(deserializer.deserialize_u8())
    trigger_reasons = tuple(
        deserializer.deserialize_vector(
            lambda item_deserializer: DexAdlTriggerSource(item_deserializer.deserialize_u8())
        )
    )
    source_locator = _read_adl_source_locator(deserializer)
    source_risk_holder = _read_adl_account_locator(deserializer)
    original_liquidated_account = (
        _read_adl_account_locator(deserializer) if deserializer.deserialize_bool() else None
    )
    return DexAdlSelectedPrefixHeader(
        schema_version=schema_version,
        algorithm_version=algorithm_version,
        price_version=price_version,
        pre_adl_state_version=pre_adl_state_version,
        queue_key=queue_key,
        trigger_source=trigger_source,
        trigger_reasons=trigger_reasons,
        source_locator=source_locator,
        source_risk_holder=source_risk_holder,
        original_liquidated_account=original_liquidated_account,
        source_position_key=_read_adl_position_key(deserializer),
        bankruptcy_subticks=deserializer.deserialize_u64(),
        target_quantums=deserializer.deserialize_u64(),
        total_executed_quantums=deserializer.deserialize_u64(),
        stop_reason=DexAdlStopReason(deserializer.deserialize_u8()),
    )


def _read_adl_audit_entry(deserializer: Deserializer) -> DexAdlAuditEntry:
    return DexAdlAuditEntry(
        schema_version=deserializer.deserialize_u16(),
        audit_entry_index=deserializer.deserialize_u64(),
        execution_pass=DexAdlExecutionPass(deserializer.deserialize_u8()),
        rank_index=deserializer.deserialize_u64(),
        position_key=_read_adl_position_key(deserializer),
        raw_side_quantums_before=deserializer.deserialize_u64(),
        opposite_side_quantums_before=deserializer.deserialize_u64(),
        score_numerator_signed=_read_adl_signed_value(deserializer),
        score_denominator=deserializer.deserialize_u128(),
        execution_status=DexAdlExecutionStatus(deserializer.deserialize_u8()),
        executed_quantums=deserializer.deserialize_u64(),
        realized_pnl_signed=_read_adl_signed_value(deserializer),
        skip_reason_code=DexAdlSkipReasonCode(deserializer.deserialize_u8()),
    )


def _read_adl_vault_takeover_fill(
    deserializer: Deserializer,
) -> DexAdlVaultTakeoverFill:
    # The unified Liquidation Vault receipt has no independent binding version.
    # Reading the retired u64 here shifts quantity/price/fee and the event digests.
    return DexAdlVaultTakeoverFill(
        schema_version=deserializer.deserialize_u16(),
        vault_account=_read_adl_account_locator(deserializer),
        leftover_quantums=deserializer.deserialize_u64(),
        bankruptcy_subticks=deserializer.deserialize_u64(),
        fee_charged=deserializer.deserialize_u64(),
    )


def _validate_adl_execution_event_chunk(event: DexAdlExecutionEvent) -> None:
    if event.schema_version != _ADL_EVENT_SCHEMA_VERSION_V5:
        raise ValueError("unsupported ADL event schema version")
    if event.selected_prefix_header.schema_version != event.schema_version:
        raise ValueError("ADL event and header schema versions must match")
    if (
        event.selected_prefix_header.algorithm_version
        not in _ADL_ALGORITHM_VERSIONS_SUPPORTED
    ):
        raise ValueError("unsupported ADL algorithm version")
    if event.selected_prefix_header.source_locator.direct_liquidation_locator is None:
        raise ValueError("ADL direct liquidation source requires a locator")
    if any(
        entry.schema_version != event.schema_version for entry in event.audit_entries
    ):
        raise ValueError("ADL event and audit schema versions must match")
    if (
        event.vault_takeover_fill is not None
        and event.vault_takeover_fill.schema_version != event.schema_version
    ):
        raise ValueError("ADL event and Vault schema versions must match")
    if event.total_chunks == 0:
        raise ValueError("ADL total_chunks must be positive")
    if event.chunk_index >= event.total_chunks:
        raise ValueError("ADL chunk_index must be less than total_chunks")
    if event.audit_entries_end_index_exclusive < event.audit_entries_start_index:
        raise ValueError("ADL audit entry range is reversed")
    if (
        event.audit_entries_end_index_exclusive - event.audit_entries_start_index
        != len(event.audit_entries)
    ):
        raise ValueError("ADL audit entry range must match entries")
    if any(
        entry.audit_entry_index != event.audit_entries_start_index + offset
        for offset, entry in enumerate(event.audit_entries)
    ):
        raise ValueError("ADL audit entry indexes must match declared range")
    if (
        event.vault_takeover_fill is not None
        and event.chunk_index != event.total_chunks - 1
    ):
        raise ValueError("ADL Vault takeover is only allowed on final chunk")


def _decode_adl_execution_event(data: bytes) -> DexAdlExecutionEvent:
    deserializer = Deserializer(data)
    schema_version = deserializer.deserialize_u16()
    adl_event_id = _read_adl_event_id(deserializer)
    chunk_index = deserializer.deserialize_u64()
    total_chunks = deserializer.deserialize_u64()
    audit_entries_start_index = deserializer.deserialize_u64()
    audit_entries_end_index_exclusive = deserializer.deserialize_u64()
    selected_prefix_header = _read_adl_selected_prefix_header(deserializer)
    audit_entries = tuple(deserializer.deserialize_vector(_read_adl_audit_entry))
    vault_takeover_fill = (
        _read_adl_vault_takeover_fill(deserializer) if deserializer.deserialize_bool() else None
    )
    event = DexAdlExecutionEvent(
        schema_version=schema_version,
        adl_event_id=adl_event_id,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        audit_entries_start_index=audit_entries_start_index,
        audit_entries_end_index_exclusive=audit_entries_end_index_exclusive,
        selected_prefix_header=selected_prefix_header,
        audit_entries=audit_entries,
        vault_takeover_fill=vault_takeover_fill,
        input_snapshot_hash=deserializer.deserialize_fixed_bytes(32),
        selected_prefix_hash=deserializer.deserialize_fixed_bytes(32),
        execution_fills_digest=deserializer.deserialize_fixed_bytes(32),
    )
    if deserializer.remaining() != 0:
        raise ValueError("AdlExecutionEvent has trailing bytes")
    _validate_adl_execution_event_chunk(event)
    return event


def _decode_liquidation_internal_offset_event(
    data: bytes,
) -> DexLiquidationInternalOffsetEvent:
    deserializer = Deserializer(data)
    flow_instance_id = deserializer.deserialize_bytes()
    source_risk_unit_id = deserializer.deserialize_bytes()
    source_account = _read_address(deserializer)
    sub_address = _read_address(deserializer)
    subaccount_number = deserializer.deserialize_u32()
    symbol_id = deserializer.deserialize_u32()
    risk_unit_type = deserializer.deserialize_u8()
    quantums = deserializer.deserialize_u64()
    price = deserializer.deserialize_u64()
    total_fee_bits = deserializer.deserialize_u64()
    total_realized_pnl_bits = deserializer.deserialize_u64()
    long_realized_pnl_bits = deserializer.deserialize_u64()
    short_realized_pnl_bits = deserializer.deserialize_u64()
    block_height = deserializer.deserialize_u64()
    timestamp_us = deserializer.deserialize_u64()
    action_seq = deserializer.deserialize_u32()
    tx_index = deserializer.deserialize_u32()
    (
        trigger_nc_bits,
        trigger_mmr,
        trigger_marks,
    ) = _read_liquidation_trigger_snapshot(
        deserializer, "LiquidationInternalOffsetEvent"
    )
    return DexLiquidationInternalOffsetEvent(
        flow_instance_id=flow_instance_id,
        source_risk_unit_id=source_risk_unit_id,
        source_account=source_account,
        sub_address=sub_address,
        subaccount_number=subaccount_number,
        symbol_id=symbol_id,
        risk_unit_type=risk_unit_type,
        quantums=quantums,
        price=price,
        total_fee_bits=total_fee_bits,
        total_realized_pnl_bits=total_realized_pnl_bits,
        long_realized_pnl_bits=long_realized_pnl_bits,
        short_realized_pnl_bits=short_realized_pnl_bits,
        block_height=block_height,
        timestamp_us=timestamp_us,
        action_seq=action_seq,
        tx_index=tx_index,
        trigger_nc_bits=trigger_nc_bits,
        trigger_mmr=trigger_mmr,
        trigger_marks=trigger_marks,
    )


def _decode_liquidation_internal_offset_event_json(
    obj: Mapping[str, Any],
) -> DexLiquidationInternalOffsetEvent:
    (
        trigger_nc_bits,
        trigger_mmr,
        trigger_marks,
    ) = _json_liquidation_trigger_snapshot(obj)
    return DexLiquidationInternalOffsetEvent(
        flow_instance_id=_j_bytes(obj["flow_instance_id"]),
        source_risk_unit_id=_j_bytes(obj["source_risk_unit_id"]),
        source_account=_j_address(obj["source_account"]),
        sub_address=_j_address(obj["sub_address"]),
        subaccount_number=_j_int(obj["subaccount_number"]),
        symbol_id=_j_int(obj["symbol_id"]),
        risk_unit_type=_j_int(obj["risk_unit_type"]),
        quantums=_j_int(obj["quantums"]),
        price=_j_int(obj["price"]),
        total_fee_bits=_j_int(obj["total_fee_bits"]),
        total_realized_pnl_bits=_j_int(obj["total_realized_pnl_bits"]),
        long_realized_pnl_bits=_j_int(obj["long_realized_pnl_bits"]),
        short_realized_pnl_bits=_j_int(obj["short_realized_pnl_bits"]),
        block_height=_j_int(obj["block_height"]),
        timestamp_us=_j_int(obj["timestamp_us"]),
        action_seq=_j_int(obj["action_seq"]),
        tx_index=_j_int(obj["tx_index"]),
        trigger_nc_bits=trigger_nc_bits,
        trigger_mmr=trigger_mmr,
        trigger_marks=trigger_marks,
    )


def _decode_liquidation_failed_event(
    data: bytes,
) -> DexLiquidationFailedEvent:
    deserializer = Deserializer(data)
    flow_instance_id = deserializer.deserialize_bytes()
    source_risk_unit_id = deserializer.deserialize_bytes()
    source_account = _read_address(deserializer)
    sub_address = _read_address(deserializer)
    subaccount_number = deserializer.deserialize_u32()
    symbol_id = deserializer.deserialize_u32()
    risk_unit_type = deserializer.deserialize_u8()
    step = deserializer.deserialize_u8()
    reason_code = deserializer.deserialize_u8()
    block_height = deserializer.deserialize_u64()
    timestamp_us = deserializer.deserialize_u64()
    action_seq = deserializer.deserialize_u32()
    tx_index = deserializer.deserialize_u32()
    (
        trigger_nc_bits,
        trigger_mmr,
        trigger_marks,
    ) = _read_liquidation_trigger_snapshot(deserializer, "LiquidationFailedEvent")
    return DexLiquidationFailedEvent(
        flow_instance_id=flow_instance_id,
        source_risk_unit_id=source_risk_unit_id,
        source_account=source_account,
        sub_address=sub_address,
        subaccount_number=subaccount_number,
        symbol_id=symbol_id,
        risk_unit_type=risk_unit_type,
        step=step,
        reason_code=reason_code,
        block_height=block_height,
        timestamp_us=timestamp_us,
        action_seq=action_seq,
        tx_index=tx_index,
        trigger_nc_bits=trigger_nc_bits,
        trigger_mmr=trigger_mmr,
        trigger_marks=trigger_marks,
    )


def _decode_liquidation_failed_event_json(
    obj: Mapping[str, Any],
) -> DexLiquidationFailedEvent:
    (
        trigger_nc_bits,
        trigger_mmr,
        trigger_marks,
    ) = _json_liquidation_trigger_snapshot(obj)
    return DexLiquidationFailedEvent(
        flow_instance_id=_j_bytes(obj["flow_instance_id"]),
        source_risk_unit_id=_j_bytes(obj["source_risk_unit_id"]),
        source_account=_j_address(obj["source_account"]),
        sub_address=_j_address(obj["sub_address"]),
        subaccount_number=_j_int(obj["subaccount_number"]),
        symbol_id=_j_int(obj["symbol_id"]),
        risk_unit_type=_j_int(obj["risk_unit_type"]),
        step=_j_int(obj["step"]),
        reason_code=_j_int(obj["reason_code"]),
        block_height=_j_int(obj["block_height"]),
        timestamp_us=_j_int(obj["timestamp_us"]),
        action_seq=_j_int(obj["action_seq"]),
        tx_index=_j_int(obj["tx_index"]),
        trigger_nc_bits=trigger_nc_bits,
        trigger_mmr=trigger_mmr,
        trigger_marks=trigger_marks,
    )


def _structured_dex_event_type(type_str: str) -> Optional[str]:
    """Return the event name for a Move-ABI decoded DEX REST event."""
    marker = "::dex::"
    _, separator, event_name = type_str.rpartition(marker)
    if (
        separator
        and event_name.endswith("Event")
        and event_name[0].isalpha()
        and all(char.isalnum() or char == "_" for char in event_name)
    ):
        return event_name
    if type_str.endswith(EVENT_TAGS["FEE_STATEMENT"]):
        return "FeeStatement"
    return None


def is_dex_event(type_str: str) -> bool:
    return _structured_dex_event_type(type_str) is not None or any(
        type_str.endswith(tag) for tag in EVENT_TAGS.values()
    )


def decode_dex_event(type_str: str, hex_data: str) -> Optional[DecodedDexEvent]:
    for name in _VAULT_EVENT_NAMES:
        if type_str.endswith("::dex::" + name):
            try:
                return DecodedDexEvent(name, _decode_vault_event(name, hex_data))
            except Exception:
                return None
    try:
        bytes_data = Hex.hex_input_to_bytes(hex_data)
    except (ParsingError, ValueError, TypeError):
        return None

    try:
        name = type_str.rsplit("::", 1)[-1]
        if name in REFERRAL_EVENT_NAMES:
            return DecodedDexEvent(name, decode_referral_event_bytes(name, bytes_data))
        for tag_key, event_type in _SUCCESS_EVENT_TYPES:
            if type_str.endswith(EVENT_TAGS[tag_key]):
                return DecodedDexEvent(
                    event_type,
                    _decode_success_event(bytes_data),
                )
        if type_str.endswith(EVENT_TAGS["FILL"]):
            return DecodedDexEvent("FillEvent", _decode_fill_event(bytes_data))
        if type_str.endswith(EVENT_TAGS["ORDER_PLACED"]):
            return DecodedDexEvent(
                "OrderPlacedEvent", _decode_order_placed_event(bytes_data)
            )
        if type_str.endswith(EVENT_TAGS["ORDER_CANCELLED"]):
            return DecodedDexEvent(
                "OrderCancelledEvent",
                _decode_order_cancelled_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ORDER_AMENDED"]):
            return DecodedDexEvent(
                "OrderAmendedEvent",
                _decode_order_amended_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ORDER_REJECTED"]):
            return DecodedDexEvent(
                "OrderRejectedEvent",
                _decode_order_rejected_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ORDER_FILLED"]):
            return DecodedDexEvent(
                "OrderFilledEvent", _decode_order_filled_event(bytes_data)
            )
        if type_str.endswith(EVENT_TAGS["CONDITION_ORDER_PLACED"]):
            return DecodedDexEvent(
                "ConditionOrderPlacedEvent",
                _decode_order_placed_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["CONDITION_ORDER_ACTIVATED"]):
            return DecodedDexEvent(
                "ConditionOrderActivatedEvent",
                _decode_condition_order_activated_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["CONDITION_ORDER_PARENT_REBOUND"]):
            return DecodedDexEvent(
                "ConditionOrderParentReboundEvent",
                _decode_condition_order_parent_rebound_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["CONDITION_ORDER_TRIGGERED"]):
            return DecodedDexEvent(
                "ConditionOrderTriggeredEvent",
                _decode_condition_order_triggered_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["FUNDING_RATE"]):
            return DecodedDexEvent(
                "FundingRateEvent",
                _decode_funding_rate_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["WHOLE_POSITION_OCO_UPDATED"]):
            return DecodedDexEvent(
                "WholePositionOcoUpdatedEvent",
                _decode_whole_position_oco_updated_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ACCOUNT"]):
            return DecodedDexEvent("AccountEvent", _decode_account_event(bytes_data))
        if type_str.endswith(EVENT_TAGS["MARK_PRICE"]):
            return DecodedDexEvent(
                "MarkPriceEvent", _decode_mark_price_event(bytes_data)
            )
        if type_str.endswith(EVENT_TAGS["INDEX_PRICE"]):
            return DecodedDexEvent(
                "IndexPriceEvent", _decode_index_price_event(bytes_data)
            )
        if type_str.endswith(EVENT_TAGS["FUNDING_PREDICTION"]):
            return DecodedDexEvent(
                "FundingPredictionEvent",
                _decode_funding_prediction_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SET_SYMBOL_TRADING_POLICY"]):
            return DecodedDexEvent(
                "SetSymbolTradingPolicyEvent",
                _decode_set_symbol_trading_policy_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SET_SYMBOL_LEVERAGE_TIER"]):
            return DecodedDexEvent(
                "SetSymbolLeverageTierEvent",
                _decode_set_symbol_leverage_tier_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SET_SYMBOL_DISPLAY_INFO"]):
            return DecodedDexEvent(
                "SetSymbolDisplayInfoEvent",
                _decode_set_symbol_display_info_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SET_SYMBOL_RISK_LIMITS"]):
            return DecodedDexEvent(
                "SetSymbolRiskLimitsEvent",
                _decode_set_symbol_risk_limits_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SET_SYMBOL_FUNDING"]):
            return DecodedDexEvent(
                "SetSymbolFundingEvent",
                _decode_set_symbol_funding_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SET_SYMBOL_BACKSTOP"]):
            return DecodedDexEvent(
                "SetSymbolBackstopEvent",
                _decode_set_symbol_backstop_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SET_SYMBOL_FEE_OVERRIDE"]):
            return DecodedDexEvent(
                "SetSymbolFeeOverrideEvent",
                _decode_set_symbol_fee_override_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SET_SYMBOL_SPEC"]):
            return DecodedDexEvent(
                "SetSymbolSpecEvent",
                _decode_set_symbol_spec_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SYMBOL_OPENED"]):
            return DecodedDexEvent(
                "SymbolOpenedEvent", _decode_symbol_opened_event(bytes_data)
            )
        if type_str.endswith(EVENT_TAGS["DELISTING_PLAN_SET"]):
            return DecodedDexEvent(
                "DelistingPlanSetEvent",
                _decode_delisting_plan_set_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["DELISTING_PRICED"]):
            return DecodedDexEvent(
                "DelistingPricedEvent",
                _decode_delisting_priced_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["DELISTING_SETTLED"]):
            return DecodedDexEvent(
                "DelistingSettledEvent",
                _decode_delisting_settled_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["SYMBOL_CLOSED"]):
            return DecodedDexEvent(
                "SymbolClosedEvent", _decode_symbol_closed_event(bytes_data)
            )
        if type_str.endswith(EVENT_TAGS["BATCH_SYSTEM_CONFIG"]):
            return DecodedDexEvent(
                "BatchSystemConfigEvent",
                _decode_batch_system_config_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["BATCH_OP_FAILED"]):
            return DecodedDexEvent(
                "BatchOpFailedEvent",
                _decode_batch_op_failed_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADL_VAULT_INITIALIZED"]):
            return DecodedDexEvent(
                "AdlVaultInitializedEvent",
                _decode_adl_vault_initialized_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADMIN_CONTROL_INITIALIZED"]):
            return DecodedDexEvent(
                "AdminControlInitializedEvent",
                _decode_admin_control_initialized_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADMIN_CONTROL_ENABLED"]):
            return DecodedDexEvent(
                "AdminControlEnabledEvent", _decode_admin_control_enabled_event(bytes_data)
            )
        if type_str.endswith(EVENT_TAGS["ADMIN_ACTION_SCHEDULED"]):
            return DecodedDexEvent(
                "AdminActionScheduledEvent",
                _decode_admin_action_scheduled_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADMIN_ACTION_EXECUTED"]):
            return DecodedDexEvent(
                "AdminActionExecutedEvent",
                _decode_admin_action_executed_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADMIN_ACTION_CANCELLED"]):
            return DecodedDexEvent(
                "AdminActionCancelledEvent",
                _decode_admin_action_cancelled_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADMIN_ACTION_EXPIRED"]):
            return DecodedDexEvent(
                "AdminActionExpiredEvent",
                _decode_admin_action_expired_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADMIN_ACTION_INVALIDATED"]):
            return DecodedDexEvent(
                "AdminActionInvalidatedEvent",
                _decode_admin_action_invalidated_event(bytes_data),
            )
        for tag, event_type in (
            ("ADMIN_CONTROL_ROTATED", "AdminControlRotatedEvent"),
            ("ADMIN_CONTROL_LISTING_SIGNER_SET_UPDATED", "AdminControlListingSignerSetUpdatedEvent"),
            ("FEE_SIGNER_SET_UPDATED", "FeeSignerSetUpdatedEvent"),
        ):
            if type_str.endswith(EVENT_TAGS[tag]):
                return DecodedDexEvent(
                    event_type,
                    _decode_admin_control_committee_updated_event(bytes_data),
                )
        if type_str.endswith(EVENT_TAGS["ADMIN_CONTROL_POLICY_UPDATED"]):
            return DecodedDexEvent(
                "AdminControlPolicyUpdatedEvent",
                _decode_admin_control_policy_updated_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["FEE_CONFIG_UPDATED"]):
            return DecodedDexEvent(
                "FeeConfigUpdatedEvent",
                _decode_fee_config_updated_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADMIN_CONTROL_ROLE_UPDATED"]):
            return DecodedDexEvent(
                "AdminControlRoleUpdatedEvent", _decode_admin_control_role_updated_event(bytes_data)
            )
        if type_str.endswith(EVENT_TAGS["LIQUIDATION_RISK_TRANSFER"]):
            return DecodedDexEvent(
                "LiquidationRiskTransferEvent",
                _decode_liquidation_risk_transfer_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["LIQUIDATION_DIRECT_ADL"]):
            return DecodedDexEvent(
                "LiquidationDirectAdlEvent",
                _decode_liquidation_direct_adl_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["ADL_EXECUTION"]):
            return DecodedDexEvent(
                "AdlExecutionEvent",
                _decode_adl_execution_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["LIQUIDATION_INTERNAL_OFFSET"]):
            return DecodedDexEvent(
                "LiquidationInternalOffsetEvent",
                _decode_liquidation_internal_offset_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["LIQUIDATION_FAILED"]):
            return DecodedDexEvent(
                "LiquidationFailedEvent",
                _decode_liquidation_failed_event(bytes_data),
            )
        if type_str.endswith(EVENT_TAGS["FEE_STATEMENT"]):
            return DecodedDexEvent(
                "FeeStatement", _decode_fee_statement_event(bytes_data)
            )
    except Exception:
        return None

    return None


def _decode_dex_event_json(
    type_str: str, obj: Mapping[str, Any]
) -> Optional[DecodedDexEvent]:
    """Decode a DEX event whose REST ``data`` is a JSON object (Move-ABI
    transport, e.g. the liquidation events). Unknown/unsupported JSON event
    types return ``None``.
    """
    for name in _VAULT_EVENT_NAMES:
        if type_str.endswith("::dex::" + name):
            try:
                return DecodedDexEvent(name, _decode_vault_event(name, obj))
            except Exception:
                return None
    try:
        name = type_str.rsplit("::", 1)[-1]
        if name in REFERRAL_EVENT_NAMES and type_str.split("::")[0].removeprefix("0x").lstrip("0") == "1":
            return DecodedDexEvent(name, decode_referral_event_json(name, dict(obj)))
        if type_str.endswith(EVENT_TAGS["CONDITION_ORDER_ACTIVATED"]):
            return DecodedDexEvent(
                "ConditionOrderActivatedEvent",
                _decode_condition_order_activated_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["CONDITION_ORDER_PARENT_REBOUND"]):
            return DecodedDexEvent(
                "ConditionOrderParentReboundEvent",
                _decode_condition_order_parent_rebound_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["WHOLE_POSITION_OCO_UPDATED"]):
            return DecodedDexEvent(
                "WholePositionOcoUpdatedEvent",
                _decode_whole_position_oco_updated_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["LIQUIDATION_RISK_TRANSFER"]):
            return DecodedDexEvent(
                "LiquidationRiskTransferEvent",
                _decode_liquidation_risk_transfer_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["LIQUIDATION_DIRECT_ADL"]):
            return DecodedDexEvent(
                "LiquidationDirectAdlEvent",
                _decode_liquidation_direct_adl_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["LIQUIDATION_INTERNAL_OFFSET"]):
            return DecodedDexEvent(
                "LiquidationInternalOffsetEvent",
                _decode_liquidation_internal_offset_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["LIQUIDATION_FAILED"]):
            return DecodedDexEvent(
                "LiquidationFailedEvent",
                _decode_liquidation_failed_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["DELISTING_PLAN_SET"]):
            return DecodedDexEvent(
                "DelistingPlanSetEvent",
                _decode_delisting_plan_set_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["DELISTING_PRICED"]):
            return DecodedDexEvent(
                "DelistingPricedEvent",
                _decode_delisting_priced_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["DELISTING_SETTLED"]):
            return DecodedDexEvent(
                "DelistingSettledEvent",
                _decode_delisting_settled_event_json(obj),
            )
        if type_str.endswith(EVENT_TAGS["SYMBOL_CLOSED"]):
            return DecodedDexEvent(
                "SymbolClosedEvent", _decode_symbol_closed_event_json(obj)
            )
    except Exception:
        return None

    event_type = _structured_dex_event_type(type_str)
    if event_type is None:
        return None
    return DecodedDexEvent(event_type, obj)


def validate_adl_execution_event_chunks(
    chunks: Sequence[DexAdlExecutionEvent],
) -> None:
    """Validate one ordered set of physical chunks for a logical ADL event."""
    if not chunks:
        raise ValueError("ADL chunk set must not be empty")
    for chunk in chunks:
        _validate_adl_execution_event_chunk(chunk)
    if len(chunks) != chunks[0].total_chunks:
        raise ValueError("ADL validation requires a complete physical chunk set")
    if any(
        chunk.chunk_index != expected_index
        for expected_index, chunk in enumerate(chunks)
    ):
        raise ValueError("ADL chunk indexes must be contiguous and ordered")
    first = chunks[0]
    logical_event_identity = (
        first.adl_event_id,
        first.total_chunks,
        first.selected_prefix_header,
        first.input_snapshot_hash,
        first.selected_prefix_hash,
        first.execution_fills_digest,
    )
    if any(
        (
            chunk.adl_event_id,
            chunk.total_chunks,
            chunk.selected_prefix_header,
            chunk.input_snapshot_hash,
            chunk.selected_prefix_hash,
            chunk.execution_fills_digest,
        )
        != logical_event_identity
        for chunk in chunks[1:]
    ):
        raise ValueError("ADL chunks must belong to the same logical ADL event")
    expected_audit_start = 0
    for chunk in chunks:
        if chunk.audit_entries_start_index != expected_audit_start:
            raise ValueError("ADL chunk audit ranges must be contiguous")
        expected_audit_start = chunk.audit_entries_end_index_exclusive


def decode_dex_event_data(type_str: str, data: Any) -> Optional[DecodedDexEvent]:
    """Decode a DEX event from either REST transport form: a hex-encoded BCS
    string (native-executor events) or a JSON object (Move-ABI events).
    """
    if isinstance(data, str):
        return decode_dex_event(type_str, data)
    if isinstance(data, dict):
        return _decode_dex_event_json(type_str, data)
    return None


def decode_transaction_events(
    events: Sequence[Mapping[str, Any]],
) -> List[DecodedTransactionEvent]:
    results: List[DecodedTransactionEvent] = []
    for index, event in enumerate(events):
        type_value = event.get("type")
        data_value = event.get("data")
        if not isinstance(type_value, str):
            continue
        if not is_dex_event(type_value):
            continue
        decoded = decode_dex_event_data(type_value, data_value)
        if decoded is None:
            continue
        results.append(
            DecodedTransactionEvent(
                index=index,
                event_type=decoded.event_type,
                event=decoded.event,
            )
        )
    return results

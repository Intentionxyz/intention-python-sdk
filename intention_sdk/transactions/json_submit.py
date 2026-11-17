# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Render a signed transaction into the node's JSON submission shape.

Mirrors the reference TypeScript SDK's ``jsonSubmit.ts``. Signing is unchanged
(BCS / EIP-712); this module only re-encodes the already-signed transaction as
JSON. Any field drift fails signature verification on chain, so values must
match the reference renderer exactly: ``u64`` / ``u128`` / ``i128`` fields are
emitted as decimal strings, addresses use the same forms, and enum integers are
passed through as numbers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict

from ..core.account_address import AccountAddress
from .dex_payloads import (
    AgentApprove,
    AgentRevoke,
    DexAgentTx,
    DexOrderlessTx,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexTransferTx,
    DexTx,
    DexUserConfigTx,
)
from ..types.enums import (
    AccountType,
    AgentOperationVariant,
    ConditionType,
    CrossTransferOption,
    DexOrderlessTxVariant,
    DexOrdersVariant,
    DexTransferVariant,
    DexUserConfigTxVariant,
    MarginMode,
    OrderBasicType,
    OrderPositionMode,
    Side,
    StpMode,
    TimeInForce,
    TriggerPriceType,
)
from . import (
    RawTransaction,
    TransactionPayload,
    is_cross_transfer_orderless_payload,
)
from .vault_payloads import VaultTx
from ..types.vault import (
    ClpTraderAllowlistAction,
    ManagedAccountAction,
    VaultStatus,
    VaultTxVariant,
)

_ZERO_ADDRESS = b"\x00" * 32

SubmitTransactionPayloadJson = Dict[str, Any]
DexOrderlessPayloadJson = Dict[str, Any]
DexPayloadJson = Dict[str, Any]
DexAgentPayloadJson = Dict[str, Any]
DexAgentApprovePayloadJson = Dict[str, Any]
DexAgentRevokePayloadJson = Dict[str, Any]
DexTransferPayloadJson = Dict[str, Any]
DexTransferInternalTransferPayloadJson = Dict[str, Any]
DexInternalTransferItemJson = Dict[str, Any]
DexTransferAccountTransferPayloadJson = Dict[str, Any]
DexAccountTransferItemJson = Dict[str, Any]
DexTransferCrossTransferPayloadJson = Dict[str, Any]
DexCrossTransferItemJson = Dict[str, Any]
DexTransferFaucetMintPayloadJson = Dict[str, Any]
AccountTypeJson = str
CrossTransferOptionJson = str
DexPlaceOrderJson = Dict[str, Any]
DexCancelOrderJson = Dict[str, Any]
DexReplaceOrderJson = Dict[str, Any]
DexOrderTargetJson = Dict[str, Any]
DexCancelTargetJson = DexOrderTargetJson
DexReplaceTargetJson = DexOrderTargetJson
DexConditionReplaceOrderJson = Dict[str, Any]


class Secp256k1EcdsaSignatureJson(TypedDict):
    type: str
    public_key: str
    signature: str


class SubmitTransactionRequestJson(TypedDict):
    sender: str
    sequence_number: str
    max_gas_amount: str
    gas_unit_price: str
    expiration_timestamp_secs: str
    payload: SubmitTransactionPayloadJson
    signature: Secp256k1EcdsaSignatureJson
    replay_protection_nonce: Optional[str]


class UnsupportedJsonPayloadError(Exception):
    """Raised when a payload cannot be rendered as JSON (submit it with BCS)."""

    def __init__(self, payload_description: str):
        super().__init__(
            f"JSON submit request does not support {payload_description}; "
            "submit this transaction with BCS"
        )


def generate_submit_transaction_request(
    transaction: Any,
    sender_authenticator: Any,
) -> SubmitTransactionRequestJson:
    """Build the ``SubmitTransactionRequestJson`` dict for a signed transaction."""
    raw = _raw_transaction(transaction)
    return {
        "sender": str(raw.sender),
        "sequence_number": str(raw.sequence_number),
        "max_gas_amount": str(raw.max_gas_amount),
        "gas_unit_price": str(raw.gas_unit_price),
        "expiration_timestamp_secs": str(raw.expiration_timestamp_secs),
        "payload": _render_payload(raw.payload),
        "signature": _render_secp256k1_signature(sender_authenticator),
        "replay_protection_nonce": _replay_protection_nonce(raw),
    }


def _raw_transaction(transaction: Any) -> RawTransaction:
    if isinstance(transaction, RawTransaction):
        return transaction
    raw = getattr(transaction, "raw_transaction", None)
    if isinstance(raw, RawTransaction):
        return raw
    raise TypeError(
        f"Expected RawTransaction or SimpleTransaction, got {type(transaction)!r}"
    )


def _render_payload(payload: Any) -> Dict[str, Any]:
    if (
        isinstance(payload, TransactionPayload)
        and payload.variant == TransactionPayload.DEX_ORDERLESS
    ):
        return _render_dex_orderless_payload(payload.value)
    raise UnsupportedJsonPayloadError("non-Dex orderless payloads")


def _render_dex_orderless_payload(dex_orderless: DexOrderlessTx) -> Dict[str, Any]:
    if dex_orderless.variant == DexOrderlessTxVariant.DEX and isinstance(
        dex_orderless.inner, DexTx
    ):
        return _render_dex_payload(dex_orderless.inner)
    if dex_orderless.variant == DexOrderlessTxVariant.DEX_TRANSFER and isinstance(
        dex_orderless.inner, DexTransferTx
    ):
        return _render_dex_transfer_payload(dex_orderless.inner)
    if dex_orderless.variant == DexOrderlessTxVariant.DEX_AGENT and isinstance(
        dex_orderless.inner, DexAgentTx
    ):
        return _render_dex_agent_payload(dex_orderless.inner)
    if dex_orderless.variant == DexOrderlessTxVariant.DEX_USER_CONFIG and isinstance(
        dex_orderless.inner, DexUserConfigTx
    ):
        return _render_dex_user_config_payload(dex_orderless.inner)
    if dex_orderless.variant == DexOrderlessTxVariant.VAULT and isinstance(
        dex_orderless.inner, VaultTx
    ):
        return _render_vault_payload(dex_orderless.inner)
    if dex_orderless.variant == DexOrderlessTxVariant.MULTISIG:
        return _render_multisig_payload(dex_orderless.inner)
    raise UnsupportedJsonPayloadError(_describe_dex_orderless(dex_orderless))


def _render_dex_payload(dex_tx: DexTx) -> Dict[str, Any]:
    orders = dex_tx.orders
    if not isinstance(orders, DexOrders):
        raise UnsupportedJsonPayloadError("Dex payloads without DexOrders")

    if orders.variant == DexOrdersVariant.NOOP:
        # The node's noop payload has no orders field at all, so a noop cannot go through the
        # shape below: it would submit a field the node never declared.
        noop: Dict[str, Any] = {
            "type": "dex_orderless_payload",
            "dex_type": "dex_payload",
            "operation": "noop",
            "nonce": str(dex_tx.nonce),
            "created_by": int(dex_tx.created_by),
        }
        if dex_tx.on_behalf_of is not None:
            noop["on_behalf_of"] = dex_tx.on_behalf_of.to_string_long()
        return noop

    order_groups: Optional[List[Dict[str, Any]]] = None
    if orders.variant == DexOrdersVariant.PLACE:
        operation = "place"
        rendered_orders = _render_place_orders(orders.orders)
        order_groups = _render_place_order_groups(orders.orders)
    elif orders.variant == DexOrdersVariant.CANCEL:
        operation = "cancel"
        rendered_orders = _render_cancel_orders(orders.orders)
    elif orders.variant == DexOrdersVariant.REPLACE:
        operation = "replace"
        rendered_orders = _render_replace_orders(orders.orders)
    elif orders.variant == DexOrdersVariant.REPLACE_MAKER_ONLY:
        # Same orders as a replace; the operation name is what asks the node to hold the
        # replacement to maker-only entry rules.
        operation = "replace_maker_only"
        rendered_orders = _render_replace_orders(orders.orders)
    elif orders.variant == DexOrdersVariant.REPLACE_CONDITION:
        operation = "replace_condition"
        rendered_orders = _render_condition_replace_orders(orders.orders)
    else:
        raise UnsupportedJsonPayloadError("unknown Dex orders variant")

    payload: Dict[str, Any] = {
        "type": "dex_orderless_payload",
        "dex_type": "dex_payload",
        "operation": operation,
        "nonce": str(dex_tx.nonce),
        "orders": rendered_orders,
    }
    # ``order_groups`` preserves the signed ``DexPlaceOrders`` batch boundaries so
    # the node rebuilds the same raw transaction it verified. Flat ``orders`` can
    # merge adjacent same-grouping batches, which breaks signature parity.
    if order_groups is not None:
        payload["order_groups"] = order_groups
    payload["created_by"] = int(dex_tx.created_by)
    if dex_tx.on_behalf_of is not None:
        payload["on_behalf_of"] = dex_tx.on_behalf_of.to_string_long()
    return payload


def _render_place_orders(groups: List[DexPlaceOrders]) -> List[Dict[str, Any]]:
    rendered: List[Dict[str, Any]] = []
    for group in groups:
        grouping = int(group.grouping)
        for order in group.orders:
            rendered.append(_render_place_order(order, grouping))
    return rendered


def _render_place_order_groups(
    groups: List[DexPlaceOrders],
) -> List[Dict[str, Any]]:
    return [
        {
            "grouping": int(group.grouping),
            "orders": [
                _render_place_order(order, int(group.grouping))
                for order in group.orders
            ],
        }
        for group in groups
    ]


def _render_place_order(order: DexPlaceOrder, grouping: int) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "sub_address": _render_sub_address(order.sub_address),
        "symbol_id": int(order.symbol_id),
        "symbol_type": int(order.symbol_type),
        "side": _validate_enum("side", order.side, Side),
        "quantums": str(order.quantums),
        "subticks": str(order.subticks),
        "trigger_subticks": str(order.trigger_subticks),
        "order_basic_type": _validate_enum(
            "order_basic_type", order.order_basic_type, OrderBasicType
        ),
        "time_in_force": _validate_enum(
            "time_in_force", order.time_in_force, TimeInForce
        ),
        "condition_type": _validate_enum(
            "condition_type", order.condition_type, ConditionType
        ),
        "trigger_price_type": _validate_enum(
            "trigger_price_type", order.trigger_price_type, TriggerPriceType
        ),
        "target_order_id": str(order.target_order_id),
        "reduce_only": bool(order.reduce_only),
        "position_mode": _validate_enum(
            "position_mode", order.position_mode, OrderPositionMode
        ),
        "slippage_tolerance_ppm": int(order.slippage_tolerance_ppm),
        "grouping": grouping,
        "stp_mode": _validate_enum("stp_mode", order.stp_mode, StpMode),
    }
    if order.client_order_id is not None:
        payload["client_order_id"] = order.client_order_id
    return payload


def _render_vault_payload(vault_tx: VaultTx) -> Dict[str, Any]:
    variant = vault_tx.variant
    v = vault_tx.inner
    base = {"type": "dex_orderless_payload", "dex_type": "vault_payload"}
    if variant == VaultTxVariant.CREATE:
        return {
            **base,
            "vault_type": "create",
            "nonce": str(v.nonce),
            "lockup_seconds": int(v.lockup_seconds),
            "always_proportional_close": bool(v.always_proportional_close),
            "initial_deposit_usdc": str(v.initial_deposit_usdc),
            "vault_name": v.vault_name,
            "strategy_description": v.strategy_description,
        }
    if variant == VaultTxVariant.DEPOSIT:
        return {
            **base,
            "vault_type": "deposit",
            "vault_id": str(v.vault_id),
            "nonce": str(v.nonce),
            "amount_usdc": str(v.amount_usdc),
        }
    if variant == VaultTxVariant.WITHDRAW:
        return {
            **base,
            "vault_type": "withdraw",
            "vault_id": str(v.vault_id),
            "nonce": str(v.nonce),
            "withdraw_shares": str(v.withdraw_shares),
        }
    if variant == VaultTxVariant.DISTRIBUTE:
        return {
            **base,
            "vault_type": "distribute",
            "vault_id": str(v.vault_id),
            "nonce": str(v.nonce),
            "distribute_amount_usdc": str(v.distribute_amount_usdc),
        }
    if variant == VaultTxVariant.CLP_CONFIG:
        payload = {
            **base,
            "vault_type": "clp_config",
            "nonce": str(v.nonce),
            "bootstrap": bool(v.bootstrap),
        }
        if v.primary_account is not None:
            payload["primary_account"] = _render_vault_subaccount_id(v.primary_account)
        if v.symbol_accounts is not None:
            payload["symbol_accounts"] = [
                _render_vault_symbol_accounts_entry(entry)
                for entry in v.symbol_accounts
            ]
        if v.allowlist is not None:
            payload["allowlist"] = [
                _render_vault_clp_trader_allowlist_entry(entry) for entry in v.allowlist
            ]
        return payload
    if variant == VaultTxVariant.CLP_MANAGED_ACCOUNT:
        payload = {
            **base,
            "vault_type": "clp_managed_account",
            "nonce": str(v.nonce),
            "account": _render_vault_subaccount_id(v.account),
            "action": _render_managed_account_action(v.action),
        }
        if v.memo is not None:
            payload["memo"] = v.memo
        return payload
    if variant == VaultTxVariant.CLP_TRADER_ALLOWLIST_UPDATE:
        return {
            **base,
            "vault_type": "clp_trader_allowlist_update",
            "nonce": str(v.nonce),
            "clp_account": _render_vault_subaccount_id(v.clp_account),
            "action": _render_allowlist_action(v.action),
            "traders": [trader.to_string_long() for trader in v.traders],
        }
    if variant == VaultTxVariant.CLP_BATCH_CREATE_MANAGED_ACCOUNTS:
        return {
            **base,
            "vault_type": "clp_batch_create_managed_accounts",
            "nonce": str(v.nonce),
            "address": v.address.to_string_long(),
            "start_number": int(v.start_number),
            "count": int(v.count),
            "user_name_prefix": v.user_name_prefix,
            "memo": v.memo,
        }
    if variant == VaultTxVariant.SET_PARAMS:
        payload = {
            **base,
            "vault_type": "set_params",
            "nonce": str(v.nonce),
            "vault_id": str(v.vault_id),
        }
        if v.daily_withdraw_limit_bps is not None:
            payload["daily_withdraw_limit_bps"] = int(v.daily_withdraw_limit_bps)
        if v.min_free_balance_ratio_bps is not None:
            payload["min_free_balance_ratio_bps"] = int(v.min_free_balance_ratio_bps)
        if v.lockup_seconds is not None:
            payload["lockup_seconds"] = int(v.lockup_seconds)
        if v.always_proportional_close is not None:
            payload["always_proportional_close"] = bool(v.always_proportional_close)
        return payload
    if variant == VaultTxVariant.SET_STATUS:
        return {
            **base,
            "vault_type": "set_status",
            "nonce": str(v.nonce),
            "vault_id": str(v.vault_id),
            "target_status": _render_vault_status(v.target_status),
        }
    raise UnsupportedJsonPayloadError("Vault payloads (unknown variant)")


def _render_vault_subaccount_id(sub: Any) -> Dict[str, Any]:
    return {
        "address": _hex(sub.address),
        "number": int(sub.number),
        "sub_address": _hex(sub.sub_address),
    }


def _render_vault_symbol_accounts_entry(entry: Any) -> Dict[str, Any]:
    return {
        "symbol_id": int(entry.symbol_id),
        "accounts": [_render_vault_subaccount_id(a) for a in entry.accounts],
    }


def _render_vault_clp_trader_allowlist_entry(entry: Any) -> Dict[str, Any]:
    return {
        "clp_account": _render_vault_subaccount_id(entry.clp_account),
        "traders": [trader.to_string_long() for trader in entry.traders],
    }


def _render_managed_account_action(action: Any) -> str:
    value = _validate_enum("managed_account action", action, ManagedAccountAction)
    if value == int(ManagedAccountAction.UPSERT):
        return "upsert"
    if value == int(ManagedAccountAction.DISABLE):
        return "disable"
    return "remove"


def _render_allowlist_action(action: Any) -> str:
    value = _validate_enum("allowlist action", action, ClpTraderAllowlistAction)
    return "add" if value == int(ClpTraderAllowlistAction.ADD) else "remove"


def _render_vault_status(status: Any) -> str:
    value = _validate_enum("target_status", status, VaultStatus)
    if value == int(VaultStatus.ACTIVE):
        return "active"
    if value == int(VaultStatus.PAUSED):
        return "paused"
    return "closed"


def _render_dex_user_config_payload(user_config_tx: DexUserConfigTx) -> Dict[str, Any]:
    variant = user_config_tx.variant
    config = user_config_tx.payload
    base = {
        "type": "dex_orderless_payload",
        "dex_type": "dex_user_config_payload",
    }
    if variant in (
        DexUserConfigTxVariant.REGISTER_REFERRAL_CODE,
        DexUserConfigTxVariant.BIND_REFERRER,
    ):
        return {
            **base,
            "user_config_type": (
                "register_referral_code"
                if variant == DexUserConfigTxVariant.REGISTER_REFERRAL_CODE
                else "bind_referrer"
            ),
            "nonce": str(config.nonce),
            "code": config.code,
        }
    if variant == DexUserConfigTxVariant.SET_USER_LEVERAGE:
        payload = {
            **base,
            "user_config_type": "set_user_leverage",
            "nonce": str(config.nonce),
            "sub_address": _render_sub_address(config.sub_address),
            "leverage_info": [
                _render_user_symbol_leverage(info) for info in config.leverage_info
            ],
        }
        _add_on_behalf_of(payload, config)
        return payload
    if variant == DexUserConfigTxVariant.CHANGE_POSITION_MODE:
        payload = {
            **base,
            "user_config_type": "change_position_mode",
            "nonce": str(config.nonce),
            "sub_address": _render_sub_address(config.sub_address),
            "position_mode": _validate_enum(
                "position_mode", config.position_mode, OrderPositionMode
            ),
        }
        _add_on_behalf_of(payload, config)
        return payload
    if variant == DexUserConfigTxVariant.CHANGE_MARGIN_MODE:
        payload = {
            **base,
            "user_config_type": "change_margin_mode",
            "nonce": str(config.nonce),
            "sub_address": _render_sub_address(config.sub_address),
            "margin_modes": [
                _render_symbol_margin_mode(mode) for mode in config.margin_modes
            ],
        }
        _add_on_behalf_of(payload, config)
        return payload
    if variant == DexUserConfigTxVariant.CREATE_SUB_ACCOUNT:
        return {
            **base,
            "user_config_type": "create_sub_account",
            "nonce": str(config.nonce),
            "name": config.name,
        }
    if variant == DexUserConfigTxVariant.MODIFY_SUB_ACCOUNT:
        payload = {
            **base,
            "user_config_type": "modify_sub_account",
            "nonce": str(config.nonce),
            "name": config.name,
            "sub_address": _render_sub_address(config.sub_address),
        }
        _add_on_behalf_of(payload, config)
        return payload
    if variant == DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN:
        payload = {
            **base,
            "user_config_type": "adjust_isolated_margin",
            "nonce": str(config.nonce),
            "sub_address": _render_sub_address(config.sub_address),
            "symbol_id": int(config.symbol_id),
            "delta_long": int(config.delta_long),
            "delta_short": int(config.delta_short),
        }
        _add_on_behalf_of(payload, config)
        return payload
    raise UnsupportedJsonPayloadError("DexUserConfig payloads (unsupported variant)")


def _render_user_symbol_leverage(leverage: Any) -> Dict[str, Any]:
    # Only symbol_id / im_leverage / exponent carry meaning; the chain ignores the
    # rest, so emit the same placeholders as the reference renderer. im_leverage and
    # exponent come from the BCS-serialized values so JSON and BCS agree.
    return {
        "symbol_id": int(leverage.symbol_id),
        "tier": 0,
        "min_notional": "0",
        "max_notional": "0",
        "im_leverage": int(leverage._im_leverage),
        "mm_leverage": 0,
        "exponent": int(leverage._exponent),
        "maintenance_deduction": "0",
    }


def _render_symbol_margin_mode(margin_mode: Any) -> Dict[str, Any]:
    return {
        "symbol_id": int(margin_mode.symbol_id),
        "margin_mode": _validate_enum(
            "margin_mode", margin_mode.margin_mode, MarginMode
        ),
    }


def _add_on_behalf_of(payload: Dict[str, Any], config: Any) -> None:
    on_behalf_of = getattr(config, "on_behalf_of", None)
    if on_behalf_of is not None:
        payload["on_behalf_of"] = on_behalf_of.to_string_long()


def _render_dex_agent_payload(agent_tx: DexAgentTx) -> Dict[str, Any]:
    if agent_tx.variant == AgentOperationVariant.APPROVE:
        operation = agent_tx.operation
        if not isinstance(operation, AgentApprove):
            raise ValueError(
                "DexAgent approve transaction must contain AgentApprove operation"
            )
        return {
            "type": "dex_orderless_payload",
            "dex_type": "dex_agent_payload",
            "agent_operation": "approve",
            "nonce": str(agent_tx.nonce),
            "name": operation.name,
            "agent_address": operation.agent_address.to_string_long(),
            "expiry_timestamp": str(operation.expiry_timestamp),
        }
    if agent_tx.variant == AgentOperationVariant.REVOKE:
        operation = agent_tx.operation
        if not isinstance(operation, AgentRevoke):
            raise ValueError(
                "DexAgent revoke transaction must contain AgentRevoke operation"
            )
        return {
            "type": "dex_orderless_payload",
            "dex_type": "dex_agent_payload",
            "agent_operation": "revoke",
            "nonce": str(agent_tx.nonce),
            "name": operation.name,
        }
    if agent_tx.variant == AgentOperationVariant.REVOKE_ALL:
        # No ``name``: its own discriminator rather than a revoke with an empty one,
        # which the chain answers with ``DexAgentNotFound`` -- an error about the
        # target of a request that was actually shaped wrong.
        return {
            "type": "dex_orderless_payload",
            "dex_type": "dex_agent_payload",
            "agent_operation": "revoke_all",
            "nonce": str(agent_tx.nonce),
        }
    raise UnsupportedJsonPayloadError("unknown DexAgent variant")


def _render_multisig_payload(tx: Any) -> Dict[str, Any]:
    """A multisig transaction in the shape the node accepts on submission.

    Two shapes exist for one payload and they are not interchangeable. What the
    chain *renders* is a summary -- the operation as a name, the approvals as a
    count -- because that is what an explorer needs. What a caller *submits* has
    to say exactly what is being authorized and carry the approvals, so that is
    what this builds: `op` in full and `proof` beside it.

    Field drift is not a formatting problem here. The owners signed
    `keccak256(BCS(op))`, and the node recomputes it from the value it rebuilds
    out of this JSON; a field left out or renamed changes that value, which
    changes the operation id, and the chain reports a proof naming a different
    operation rather than a parse error. So every field the operation carries is
    rendered, and nothing is abbreviated.
    """
    from .multisig_payloads import (
        MultisigOpCreate,
        MultisigOpExecute,
        MultisigOpInstall,
        MultisigOpRemove,
        MultisigOpRotateKey,
        MultisigOpUpdatePolicy,
    )

    op = tx.op
    if isinstance(op, MultisigOpCreate):
        rendered_op = {
            "operation": "create_policy",
            "owners": [_render_owner(owner) for owner in op.owners],
            "threshold": op.threshold,
            "salt": _hex(bytes(op.salt)),
        }
    elif isinstance(op, MultisigOpInstall):
        rendered_op = {
            "operation": "install_policy",
            "owners": [_render_owner(owner) for owner in op.owners],
            "threshold": op.threshold,
        }
    elif isinstance(op, MultisigOpUpdatePolicy):
        rendered_op = {
            "operation": "update_policy",
            "owners": [_render_owner(owner) for owner in op.owners],
            "threshold": op.threshold,
        }
    elif isinstance(op, MultisigOpRemove):
        rendered_op = {
            "operation": "remove_policy",
            "new_auth_key": _hex(bytes(op.new_auth_key)),
            "new_key_proof": _render_key_proof(op.new_key_proof),
        }
    elif isinstance(op, MultisigOpRotateKey):
        rendered_op = {
            "operation": "rotate_key",
            "new_auth_key": _hex(bytes(op.new_auth_key)),
            "new_key_proof": _render_key_proof(op.new_key_proof),
        }
    elif isinstance(op, MultisigOpExecute):
        # The inner renderers each stamp the outer `type` because they are also
        # used on their own; nested inside an operation that tag belongs to the
        # envelope, not to the payload being authorized.
        inner = {k: v for k, v in _render_gated_payload(op.payload).items() if k != "type"}
        rendered_op = {"operation": "execute", **inner}
    else:
        raise UnsupportedJsonPayloadError(f"unknown multisig operation {type(op).__name__}")

    payload: Dict[str, Any] = {
        "type": "dex_orderless_payload",
        "dex_type": "multisig_payload",
        "nonce": str(tx.nonce),
        "account": str(tx.account),
        # The summary fields stay in the body: the node ignores them on
        # submission, and leaving them out would make a submitted payload and a
        # rendered one two different shapes rather than one with two halves.
        "operation": _multisig_operation_name(op),
        "signatures_count": len(tx.proof.signatures) if tx.proof is not None else 0,
        "op": rendered_op,
    }
    if tx.proof is not None:
        payload["authority_epoch"] = str(tx.proof.authority_epoch)
        payload["expires_at_secs"] = str(tx.proof.expires_at_secs)
        payload["proof"] = {
            "op_id": _fixed32_hex(bytes(tx.proof.op_id), "op_id"),
            "authority_epoch": str(tx.proof.authority_epoch),
            "expires_at_secs": str(tx.proof.expires_at_secs),
            "signatures": [_render_evm_signature(sig) for sig in tx.proof.signatures],
        }
    return payload


def _multisig_operation_name(op: Any) -> str:
    """The name the rendering uses, so a submitted body carries it too."""
    from .multisig_payloads import submit_operation_name

    return submit_operation_name(op)


def _render_gated_payload(payload: Any) -> Dict[str, Any]:
    """The inner operation, in the same shape a single key submits it with.

    A gated payload is a wrapper around the unchanged transaction type, so the
    variant decides and the inner value is rendered by the same function that
    renders it on its own. Matching on the wrapper's own class would be matching
    on the envelope.
    """
    from .multisig_payloads import GatedPayloadVariant

    inner = getattr(payload, "inner", payload)
    variant = getattr(payload, "variant", None)
    if variant == GatedPayloadVariant.DEX_TRANSFER:
        return _render_dex_transfer_payload(inner)
    if variant == GatedPayloadVariant.VAULT:
        return _render_vault_payload(inner)
    if variant == GatedPayloadVariant.DEX_AGENT:
        return _render_dex_agent_payload(inner)
    if variant == GatedPayloadVariant.CREATE_SUB_ACCOUNT:
        # The chain's gated arm is the create-subaccount transaction itself,
        # while the JSON shape is the user-config union it belongs to. Wrapping
        # it back into that union is what keeps the field names from drifting:
        # the union's discriminator is `user_config_type`, and spelling it by
        # hand here once got it wrong.
        from .dex_payloads import DexUserConfigTx

        return _render_dex_user_config_payload(
            DexUserConfigTx(DexUserConfigTxVariant.CREATE_SUB_ACCOUNT, inner)
        )
    raise UnsupportedJsonPayloadError(
        f"unknown gated payload variant {variant!r}"
    )


def _render_key_proof(proof: Any) -> Dict[str, Any]:
    """The incoming key's challenge answer."""
    from .multisig_payloads import KeyProofEd25519, KeyProofSecp256k1

    if isinstance(proof, KeyProofSecp256k1):
        return {"scheme": "secp256k1", "signature": _render_evm_signature(proof.signature)}
    if isinstance(proof, KeyProofEd25519):
        return {
            "scheme": "ed25519",
            "public_key": _fixed32_hex(bytes(proof.public_key), "public_key"),
            "signature": _hex(bytes(proof.signature)),
        }
    raise UnsupportedJsonPayloadError(f"unknown key proof {type(proof).__name__}")


def _render_evm_signature(signature: Any) -> str:
    """One owner approval as sixty-five bytes of `r || s || v`.

    Not three fields: the node reads the compact form, and splitting it here
    would be a second layout to keep in step with the one the owners signed.
    """
    raw = bytes(signature.r) + bytes(signature.s) + bytes([signature.v])
    if len(raw) != 65:
        raise UnsupportedJsonPayloadError(
            f"an owner approval must be 65 bytes, got {len(raw)}"
        )
    return _hex(raw)


def _render_owner(owner: Any) -> str:
    """An owner as the chain's padded address form."""
    raw = bytes(owner)
    if len(raw) == 20:
        raw = bytes(12) + raw
    if len(raw) != 32:
        raise UnsupportedJsonPayloadError(f"an owner must be 20 or 32 bytes, got {len(raw)}")
    return _hex(raw)


def _render_dex_transfer_payload(transfer_tx: DexTransferTx) -> Dict[str, Any]:
    base = {
        "type": "dex_orderless_payload",
        "dex_type": "dex_transfer_payload",
        "nonce": str(transfer_tx.nonce),
    }
    variant = transfer_tx.variant
    if variant == DexTransferVariant.CLAIM_REFERRAL_REWARDS:
        payload = {
            **base,
            "transfer_type": "claim_referral_rewards",
        }
        if transfer_tx.on_behalf_of is not None:
            payload["on_behalf_of"] = str(transfer_tx.on_behalf_of)
        return payload
    if variant == DexTransferVariant.INTERNAL_TRANSFER:
        return {
            **base,
            "transfer_type": "internal_transfer",
            "transfers": [
                _render_internal_transfer_item(item) for item in transfer_tx.payload
            ],
        }
    if variant == DexTransferVariant.ACCOUNT_TRANSFER:
        return {
            **base,
            "transfer_type": "account_transfer",
            "transfers": [
                _render_to_account_item(item) for item in transfer_tx.payload
            ],
        }
    if variant == DexTransferVariant.CROSS_TRANSFER:
        payload: Dict[str, Any] = {
            **base,
            "transfer_type": "cross_transfer",
            "option": _render_cross_transfer_option(transfer_tx.option),
            "transfers": [
                _render_to_account_item(item) for item in transfer_tx.payload
            ],
        }
        if transfer_tx.bridge_proof is not None:
            payload["bridge_proof"] = _render_bridge_proof(transfer_tx.bridge_proof)
        return payload
    if variant == DexTransferVariant.FAUCET_MINT:
        return {
            **base,
            "transfer_type": "faucet_mint",
            "transfers": [
                _render_to_account_item(item) for item in transfer_tx.payload
            ],
        }
    raise UnsupportedJsonPayloadError("unknown DexTransfer variant")


def _render_internal_transfer_item(item: Any) -> Dict[str, Any]:
    return {
        "from_subaccount": _render_sub_address(item.from_subaddress),
        "to_subaccount": _render_sub_address(item.to_subaddress),
        "asset_id": int(item.asset_id),
        "amount": str(item.amount),
        "account_type": _render_account_type(item.account_type),
    }


def _render_to_account_item(item: Any) -> Dict[str, Any]:
    return {
        "to_account": item.to_account.to_string_long(),
        "asset_id": int(item.asset_id),
        "amount": str(item.amount),
        "account_type": _render_account_type(item.account_type),
    }


def _render_bridge_proof(proof: Any) -> Dict[str, Any]:
    return {
        "msg_id": _fixed32_hex(proof.msg_id, "bridge_proof msg_id"),
        "signer_epoch": str(proof.signer_epoch),
        "signatures": [_render_bridge_signature(sig) for sig in proof.signatures],
    }


def _render_bridge_signature(sig: Any) -> Dict[str, Any]:
    if not isinstance(sig.v, int) or sig.v < 0 or sig.v > 255:
        raise ValueError(f"Invalid bridge_proof signature v: {sig.v!r}")
    return {
        "r": _fixed32_hex(sig.r, "bridge_proof signature r"),
        "s": _fixed32_hex(sig.s, "bridge_proof signature s"),
        "v": sig.v,
    }


def _render_account_type(account_type: Any) -> str:
    value = _validate_enum("account_type", account_type, AccountType)
    return "perp" if value == int(AccountType.PERP) else "spot"


def _render_cross_transfer_option(option: Any) -> str:
    if option is None:
        raise ValueError("cross_transfer requires an option")
    value = _validate_enum("cross_transfer_option", option, CrossTransferOption)
    return "mint" if value == int(CrossTransferOption.MINT) else "burn"


def _fixed32_hex(data: bytes, field: str) -> str:
    if len(data) != 32:
        raise ValueError(f"Invalid {field} length: expected 32 bytes, got {len(data)}")
    return _hex(data)


def _hex(data: bytes) -> str:
    return "0x" + bytes(data).hex()


def _render_cancel_orders(orders: List[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "sub_address": _render_sub_address(order.sub_address),
            "target": _render_order_target(order.target),
            "symbol_type": int(order.symbol_type),
        }
        for order in orders
    ]


def _render_replace_orders(orders: List[Any]) -> List[Dict[str, Any]]:
    rendered: List[Dict[str, Any]] = []
    for order in orders:
        item: Dict[str, Any] = {
            "sub_address": _render_sub_address(order.sub_address),
            "target": _render_order_target(order.target),
        }
        if order.quantums is not None:
            item["quantums"] = str(order.quantums)
        if order.subticks is not None:
            item["subticks"] = str(order.subticks)
        if order.new_client_order_id is not None:
            item["new_client_order_id"] = order.new_client_order_id
        rendered.append(item)
    return rendered


def _render_condition_replace_orders(orders: List[Any]) -> List[Dict[str, Any]]:
    rendered: List[Dict[str, Any]] = []
    for order in orders:
        item: Dict[str, Any] = {
            "sub_address": _render_sub_address(order.sub_address),
            "target": _render_order_target(order.target),
            "quantums": str(order.quantums),
            "subticks": str(order.subticks),
            "trigger_subticks": str(order.trigger_subticks),
            "order_basic_type": _validate_enum(
                "order_basic_type", order.order_basic_type, OrderBasicType
            ),
            "condition_type": _validate_enum(
                "condition_type", order.condition_type, ConditionType
            ),
            "trigger_price_type": _validate_enum(
                "trigger_price_type", order.trigger_price_type, TriggerPriceType
            ),
        }
        if order.new_client_order_id is not None:
            item["new_client_order_id"] = order.new_client_order_id
        rendered.append(item)
    return rendered


def _render_order_target(target: Any) -> Dict[str, Any]:
    # Cancel and replace share legacy kinds 0/1; replace adds context kind 2.
    kind = int(target.kind)
    if kind == 0:
        return {"target_type": "order_id", "target_order_id": str(target.order_id)}
    if kind == 1:
        return {
            "target_type": "client_order_id",
            "client_order_id": target.client_order_id,
        }
    if kind == 2:
        return {
            "target_type": "order_id_with_context",
            "target_order_id": str(target.order_id),
            "symbol_id": target.symbol_id,
            "symbol_type": int(target.symbol_type),
        }
    raise ValueError(f"Invalid order target kind: {target.kind!r}")


def _validate_enum(field: str, value: Any, enum_cls: Any) -> int:
    """Return ``value`` as an int, rejecting values outside ``enum_cls``.

    Mirrors the reference renderer's per-field enum validation so an
    out-of-range value fails locally rather than producing a payload the node
    would reject during signature reconstruction.
    """
    try:
        return int(enum_cls(int(value)))
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {field}: {value!r}")


def _render_sub_address(address: AccountAddress) -> str:
    if address.address == _ZERO_ADDRESS:
        return "0x0"
    return address.to_string_long()


def _render_secp256k1_signature(sender_authenticator: Any) -> Dict[str, Any]:
    """The sender's own signature, as the submit request spells it.

    Two authenticator shapes reach this. One wraps the key and the signature in
    the `Any*` types, where the bytes sit one level further in; the other holds
    them directly. Probing for the inner value and falling back to the outer one
    covers both without each caller having to know which it built -- and getting
    it wrong is not a readable failure, it is an `AttributeError` from inside a
    renderer.
    """
    single_key = getattr(sender_authenticator, "authenticator", sender_authenticator)
    public_key = getattr(single_key.public_key, "public_key", single_key.public_key)
    signature = getattr(single_key.signature, "signature", single_key.signature)
    return {
        "type": "secp256k1_ecdsa_signature",
        "public_key": _crypto_hex(public_key),
        "signature": _crypto_hex(signature),
    }


def _crypto_hex(value: Any) -> str:
    """Hex for a key or a signature, whichever spelling it arrived in.

    Always `0x`-prefixed, because that is what the request carries for every
    payload type -- the prefix is part of the value here, not decoration.
    """
    for attr in ("key", "data", "signature"):
        inner = getattr(value, attr, None)
        if isinstance(inner, (bytes, bytearray)):
            return _hex(bytes(inner))
    if isinstance(value, (bytes, bytearray)):
        return _hex(bytes(value))
    hexed = getattr(value, "hex", None)
    if callable(hexed):
        text = hexed()
        return text if text.startswith("0x") else f"0x{text}"
    raise UnsupportedJsonPayloadError(
        f"cannot read bytes out of {type(value).__name__}"
    )


def _replay_protection_nonce(raw: RawTransaction) -> Optional[str]:
    payload = raw.payload
    if (
        isinstance(payload, TransactionPayload)
        and payload.variant == TransactionPayload.DEX_ORDERLESS
    ):
        if is_cross_transfer_orderless_payload(payload):
            return str(raw.sequence_number)
        return str(_dex_orderless_nonce(payload.value))
    return None


def _dex_orderless_nonce(dex_orderless: DexOrderlessTx) -> int:
    # The nonce lives directly on the inner tx (DexTx / DexTransferTx / DexAgentTx),
    # on its config payload (DexUserConfig / DexSystemConfig), or on a wrapped inner
    # (Vault). Probe in that order.
    inner = dex_orderless.inner
    nonce = getattr(inner, "nonce", None)
    if nonce is not None:
        return nonce
    config = getattr(inner, "payload", None)
    config_nonce = getattr(config, "nonce", None) if config is not None else None
    if config_nonce is not None:
        return config_nonce
    wrapped = getattr(inner, "inner", None)
    wrapped_nonce = getattr(wrapped, "nonce", None) if wrapped is not None else None
    if wrapped_nonce is not None:
        return wrapped_nonce
    raise ValueError("cannot determine replay_protection_nonce for payload")


def _describe_dex_orderless(dex_orderless: DexOrderlessTx) -> str:
    return "this Dex orderless payload"

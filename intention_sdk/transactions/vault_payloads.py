# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from typing import List, Optional, Union

from ..core.account_address import AccountAddress
from ..bcs import Deserializer, Serializer
from ..types.vault import (
    ClpTraderAllowlistAction,
    ClpTraderAllowlistEntry,
    ManagedAccountAction,
    MIN_LEADER_STAKE_USDC,
    SubaccountId,
    SymbolAccountsEntry,
    VAULT_MIN_INITIAL_DEPOSIT_USDC,
    VAULT_MIN_LOCKUP_SECONDS,
    VAULT_NAME_MAX_LEN,
    VAULT_STRATEGY_DESC_MAX_LEN,
    VaultStatus,
    VaultTxVariant,
)

# =============================================================================
# Vault Transaction Types
# =============================================================================


class VaultValidationError(Exception):
    pass


_VAULT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _\-.]+$")


def _validate_vault_create_fields(
    lockup_seconds: int,
    initial_deposit_usdc: int,
    vault_name: str,
    strategy_description: str,
) -> None:
    if initial_deposit_usdc < VAULT_MIN_INITIAL_DEPOSIT_USDC:
        raise VaultValidationError(
            f"Initial deposit {initial_deposit_usdc} must be at least "
            f"{VAULT_MIN_INITIAL_DEPOSIT_USDC} (100 USDC)"
        )
    if lockup_seconds < VAULT_MIN_LOCKUP_SECONDS:
        raise VaultValidationError(
            f"Lockup period {lockup_seconds} must be at least "
            f"{VAULT_MIN_LOCKUP_SECONDS} seconds"
        )
    if len(vault_name) == 0 or len(vault_name) > VAULT_NAME_MAX_LEN:
        raise VaultValidationError(
            f"vault_name length must be 1-{VAULT_NAME_MAX_LEN}, got "
            f"{len(vault_name)}"
        )
    if _VAULT_NAME_PATTERN.fullmatch(vault_name) is None:
        raise VaultValidationError("vault_name must match [A-Za-z0-9 _-.]")
    if vault_name != vault_name.strip():
        raise VaultValidationError(
            "vault_name must not have leading/trailing whitespace"
        )
    if (
        len(strategy_description) == 0
        or len(strategy_description) > VAULT_STRATEGY_DESC_MAX_LEN
    ):
        raise VaultValidationError(
            "strategy_description length must be "
            f"1-{VAULT_STRATEGY_DESC_MAX_LEN}, got {len(strategy_description)}"
        )
    if strategy_description != strategy_description.strip():
        raise VaultValidationError(
            "strategy_description must not have leading/trailing whitespace"
        )


def _validate_positive_amount(value: int, message: str) -> None:
    if value <= 0:
        raise VaultValidationError(message)


class VaultCreateTx:
    nonce: int  # u64
    lockup_seconds: int  # u32
    always_proportional_close: bool
    initial_deposit_usdc: int  # i128
    vault_name: str
    strategy_description: str

    def __init__(
        self,
        nonce: int,
        lockup_seconds: int,
        always_proportional_close: bool,
        initial_deposit_usdc: int,
        vault_name: str,
        strategy_description: str,
    ):
        _validate_vault_create_fields(
            lockup_seconds,
            initial_deposit_usdc,
            vault_name,
            strategy_description,
        )
        self.nonce = nonce
        self.lockup_seconds = lockup_seconds
        self.always_proportional_close = always_proportional_close
        self.initial_deposit_usdc = initial_deposit_usdc
        self.vault_name = vault_name
        self.strategy_description = strategy_description

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        serializer.serialize_u32(self.lockup_seconds)
        serializer.serialize_bool(self.always_proportional_close)
        serializer.serialize_i128(self.initial_deposit_usdc)
        serializer.serialize_str(self.vault_name)
        serializer.serialize_str(self.strategy_description)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultCreateTx:
        return VaultCreateTx(
            nonce=deserializer.deserialize_u64(),
            lockup_seconds=deserializer.deserialize_u32(),
            always_proportional_close=deserializer.deserialize_bool(),
            initial_deposit_usdc=deserializer.deserialize_i128(),
            vault_name=deserializer.deserialize_str(),
            strategy_description=deserializer.deserialize_str(),
        )


class VaultDepositTx:
    vault_id: int  # u64
    nonce: int  # u64
    amount_usdc: int  # i128

    def __init__(self, vault_id: int, nonce: int, amount_usdc: int):
        _validate_positive_amount(amount_usdc, "Deposit amount must be positive")
        self.vault_id = vault_id
        self.nonce = nonce
        self.amount_usdc = amount_usdc

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.vault_id)
        serializer.serialize_u64(self.nonce)
        serializer.serialize_i128(self.amount_usdc)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultDepositTx:
        return VaultDepositTx(
            vault_id=deserializer.deserialize_u64(),
            nonce=deserializer.deserialize_u64(),
            amount_usdc=deserializer.deserialize_i128(),
        )


class VaultWithdrawTx:
    vault_id: int  # u64
    nonce: int  # u64
    withdraw_shares: int  # i128

    def __init__(self, vault_id: int, nonce: int, withdraw_shares: int):
        _validate_positive_amount(
            withdraw_shares, "Withdraw shares must be positive"
        )
        self.vault_id = vault_id
        self.nonce = nonce
        self.withdraw_shares = withdraw_shares

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.vault_id)
        serializer.serialize_u64(self.nonce)
        serializer.serialize_i128(self.withdraw_shares)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultWithdrawTx:
        return VaultWithdrawTx(
            vault_id=deserializer.deserialize_u64(),
            nonce=deserializer.deserialize_u64(),
            withdraw_shares=deserializer.deserialize_i128(),
        )


class VaultClpConfigTx:
    nonce: int  # u64
    bootstrap: bool
    primary_account: Optional[SubaccountId]
    symbol_accounts: Optional[List[SymbolAccountsEntry]]
    allowlist: Optional[List[ClpTraderAllowlistEntry]]

    def __init__(
        self,
        nonce: int,
        bootstrap: bool,
        primary_account: Optional[SubaccountId] = None,
        symbol_accounts: Optional[List[SymbolAccountsEntry]] = None,
        allowlist: Optional[List[ClpTraderAllowlistEntry]] = None,
    ):
        self.nonce = nonce
        self.bootstrap = bootstrap
        self.primary_account = primary_account
        self.symbol_accounts = symbol_accounts
        self.allowlist = allowlist

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        serializer.serialize_bool(self.bootstrap)
        # Option<SubaccountId>
        serializer.serialize_option(self.primary_account)
        # Option<Vec<SymbolAccountsEntry>>
        serializer.serialize_bool(self.symbol_accounts is not None)
        if self.symbol_accounts is not None:
            serializer.serialize_u32_as_uleb128(len(self.symbol_accounts))
            for entry in self.symbol_accounts:
                entry.serialize(serializer)
        # Option<Vec<ClpTraderAllowlistEntry>>
        serializer.serialize_bool(self.allowlist is not None)
        if self.allowlist is not None:
            serializer.serialize_u32_as_uleb128(len(self.allowlist))
            for entry in self.allowlist:
                entry.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultClpConfigTx:
        nonce = deserializer.deserialize_u64()
        bootstrap = deserializer.deserialize_bool()
        has_primary = deserializer.deserialize_bool()
        primary_account = (
            SubaccountId.deserialize(deserializer) if has_primary else None
        )
        has_symbol_accounts = deserializer.deserialize_bool()
        symbol_accounts = None
        if has_symbol_accounts:
            length = deserializer.deserialize_u32_from_uleb128()
            symbol_accounts = [
                SymbolAccountsEntry.deserialize(deserializer) for _ in range(length)
            ]
        has_allowlist = deserializer.deserialize_bool()
        allowlist = None
        if has_allowlist:
            length = deserializer.deserialize_u32_from_uleb128()
            allowlist = [
                ClpTraderAllowlistEntry.deserialize(deserializer) for _ in range(length)
            ]
        return VaultClpConfigTx(
            nonce, bootstrap, primary_account, symbol_accounts, allowlist
        )


class VaultClpManagedAccountTx:
    nonce: int  # u64
    account: SubaccountId
    action: ManagedAccountAction
    memo: Optional[str]

    def __init__(
        self,
        nonce: int,
        account: SubaccountId,
        action: ManagedAccountAction,
        memo: Optional[str] = None,
    ):
        self.nonce = nonce
        self.account = account
        self.action = action
        self.memo = memo

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.account.serialize(serializer)
        serializer.serialize_u32_as_uleb128(self.action)
        serializer.serialize_option_str(self.memo)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultClpManagedAccountTx:
        nonce = deserializer.deserialize_u64()
        account = SubaccountId.deserialize(deserializer)
        action = ManagedAccountAction(deserializer.deserialize_u32_from_uleb128())
        has_memo = deserializer.deserialize_bool()
        memo = deserializer.deserialize_str() if has_memo else None
        return VaultClpManagedAccountTx(nonce, account, action, memo)


class VaultClpTraderAllowlistUpdateTx:
    nonce: int  # u64
    clp_account: SubaccountId
    action: ClpTraderAllowlistAction
    traders: List[AccountAddress]

    def __init__(
        self,
        nonce: int,
        clp_account: SubaccountId,
        action: ClpTraderAllowlistAction,
        traders: List[AccountAddress],
    ):
        self.nonce = nonce
        self.clp_account = clp_account
        self.action = action
        self.traders = traders

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.clp_account.serialize(serializer)
        serializer.serialize_u32_as_uleb128(self.action)
        serializer.serialize_u32_as_uleb128(len(self.traders))
        for trader in self.traders:
            trader.serialize(serializer)

    @staticmethod
    def deserialize(
        deserializer: Deserializer,
    ) -> VaultClpTraderAllowlistUpdateTx:
        nonce = deserializer.deserialize_u64()
        clp_account = SubaccountId.deserialize(deserializer)
        action = ClpTraderAllowlistAction(deserializer.deserialize_u32_from_uleb128())
        length = deserializer.deserialize_u32_from_uleb128()
        traders = [AccountAddress.deserialize(deserializer) for _ in range(length)]
        return VaultClpTraderAllowlistUpdateTx(nonce, clp_account, action, traders)


class VaultSetParamsTx:
    nonce: int  # u64
    vault_id: int  # u64
    daily_withdraw_limit_bps: Optional[int]  # Option<u32>
    min_free_balance_ratio_bps: Optional[int]  # Option<u32>
    lockup_seconds: Optional[int]  # Option<u32>
    always_proportional_close: Optional[bool]

    def __init__(
        self,
        nonce: int,
        vault_id: int,
        daily_withdraw_limit_bps: Optional[int] = None,
        min_free_balance_ratio_bps: Optional[int] = None,
        lockup_seconds: Optional[int] = None,
        always_proportional_close: Optional[bool] = None,
    ):
        self.nonce = nonce
        self.vault_id = vault_id
        self.daily_withdraw_limit_bps = daily_withdraw_limit_bps
        self.min_free_balance_ratio_bps = min_free_balance_ratio_bps
        self.lockup_seconds = lockup_seconds
        self.always_proportional_close = always_proportional_close

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        serializer.serialize_u64(self.vault_id)
        # Option<u32>
        serializer.serialize_bool(self.daily_withdraw_limit_bps is not None)
        if self.daily_withdraw_limit_bps is not None:
            serializer.serialize_u32(self.daily_withdraw_limit_bps)
        # Option<u32>
        serializer.serialize_bool(self.min_free_balance_ratio_bps is not None)
        if self.min_free_balance_ratio_bps is not None:
            serializer.serialize_u32(self.min_free_balance_ratio_bps)
        # Option<u32>
        serializer.serialize_bool(self.lockup_seconds is not None)
        if self.lockup_seconds is not None:
            serializer.serialize_u32(self.lockup_seconds)
        # Option<bool>
        serializer.serialize_bool(self.always_proportional_close is not None)
        if self.always_proportional_close is not None:
            serializer.serialize_bool(self.always_proportional_close)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultSetParamsTx:
        nonce = deserializer.deserialize_u64()
        vault_id = deserializer.deserialize_u64()
        has_daily = deserializer.deserialize_bool()
        daily = deserializer.deserialize_u32() if has_daily else None
        has_min = deserializer.deserialize_bool()
        min_free = deserializer.deserialize_u32() if has_min else None
        has_lockup = deserializer.deserialize_bool()
        lockup = deserializer.deserialize_u32() if has_lockup else None
        has_apc = deserializer.deserialize_bool()
        apc = deserializer.deserialize_bool() if has_apc else None
        return VaultSetParamsTx(nonce, vault_id, daily, min_free, lockup, apc)


class VaultSetStatusTx:
    nonce: int  # u64
    vault_id: int  # u64
    target_status: VaultStatus

    def __init__(self, nonce: int, vault_id: int, target_status: VaultStatus):
        self.nonce = nonce
        self.vault_id = vault_id
        self.target_status = target_status

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        serializer.serialize_u64(self.vault_id)
        serializer.serialize_u32_as_uleb128(self.target_status)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultSetStatusTx:
        return VaultSetStatusTx(
            nonce=deserializer.deserialize_u64(),
            vault_id=deserializer.deserialize_u64(),
            target_status=VaultStatus(deserializer.deserialize_u32_from_uleb128()),
        )


class VaultClpBatchCreateManagedAccountsTx:
    nonce: int  # u64
    address: AccountAddress
    start_number: int  # u32
    count: int  # u32
    user_name_prefix: str
    memo: str

    def __init__(
        self,
        nonce: int,
        address: AccountAddress,
        start_number: int,
        count: int,
        user_name_prefix: str,
        memo: str,
    ):
        self.nonce = nonce
        self.address = address
        self.start_number = start_number
        self.count = count
        self.user_name_prefix = user_name_prefix
        self.memo = memo

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.nonce)
        self.address.serialize(serializer)
        serializer.serialize_u32(self.start_number)
        serializer.serialize_u32(self.count)
        serializer.serialize_str(self.user_name_prefix)
        serializer.serialize_str(self.memo)

    @staticmethod
    def deserialize(
        deserializer: Deserializer,
    ) -> VaultClpBatchCreateManagedAccountsTx:
        return VaultClpBatchCreateManagedAccountsTx(
            nonce=deserializer.deserialize_u64(),
            address=AccountAddress.deserialize(deserializer),
            start_number=deserializer.deserialize_u32(),
            count=deserializer.deserialize_u32(),
            user_name_prefix=deserializer.deserialize_str(),
            memo=deserializer.deserialize_str(),
        )


class VaultDistributeTx:
    vault_id: int  # u64
    nonce: int  # u64
    distribute_amount_usdc: int  # i128

    def __init__(self, vault_id: int, nonce: int, distribute_amount_usdc: int):
        _validate_positive_amount(
            distribute_amount_usdc, "Distribute amount must be positive"
        )
        self.vault_id = vault_id
        self.nonce = nonce
        self.distribute_amount_usdc = distribute_amount_usdc

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u64(self.vault_id)
        serializer.serialize_u64(self.nonce)
        serializer.serialize_i128(self.distribute_amount_usdc)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultDistributeTx:
        return VaultDistributeTx(
            vault_id=deserializer.deserialize_u64(),
            nonce=deserializer.deserialize_u64(),
            distribute_amount_usdc=deserializer.deserialize_i128(),
        )


# =============================================================================
# VaultTx Wrapper
# =============================================================================

VaultTxPayload = Union[
    VaultCreateTx,
    VaultDepositTx,
    VaultWithdrawTx,
    VaultClpConfigTx,
    VaultClpManagedAccountTx,
    VaultClpTraderAllowlistUpdateTx,
    VaultSetParamsTx,
    VaultSetStatusTx,
    VaultClpBatchCreateManagedAccountsTx,
    VaultDistributeTx,
]


class VaultTx:
    variant: VaultTxVariant
    inner: VaultTxPayload

    def __init__(self, variant: VaultTxVariant, inner: VaultTxPayload):
        self.variant = variant
        self.inner = inner

    @property
    def nonce(self) -> int:
        return self.inner.nonce

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32_as_uleb128(self.variant)
        self.inner.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> VaultTx:
        variant = VaultTxVariant(deserializer.deserialize_u32_from_uleb128())
        _DISPATCH = {
            VaultTxVariant.CREATE: VaultCreateTx,
            VaultTxVariant.DEPOSIT: VaultDepositTx,
            VaultTxVariant.WITHDRAW: VaultWithdrawTx,
            VaultTxVariant.CLP_CONFIG: VaultClpConfigTx,
            VaultTxVariant.CLP_MANAGED_ACCOUNT: VaultClpManagedAccountTx,
            VaultTxVariant.CLP_TRADER_ALLOWLIST_UPDATE: VaultClpTraderAllowlistUpdateTx,
            VaultTxVariant.SET_PARAMS: VaultSetParamsTx,
            VaultTxVariant.SET_STATUS: VaultSetStatusTx,
            VaultTxVariant.CLP_BATCH_CREATE_MANAGED_ACCOUNTS: VaultClpBatchCreateManagedAccountsTx,
            VaultTxVariant.DISTRIBUTE: VaultDistributeTx,
        }
        cls = _DISPATCH.get(variant)
        if cls is None:
            raise ValueError(f"Unknown VaultTx variant: {variant}")
        inner = cls.deserialize(deserializer)
        return VaultTx(variant, inner)


# =============================================================================
# Builder Helpers
# =============================================================================


def calculate_max_distribute_for_leader(
    leader_shares: int, total_shares: int, tvl_usdc: int
) -> int:
    if leader_shares <= 0 or total_shares <= 0 or tvl_usdc <= 0:
        return 0

    leader_value = (leader_shares * tvl_usdc) // total_shares
    if leader_value <= MIN_LEADER_STAKE_USDC:
        return 0

    return ((leader_value - MIN_LEADER_STAKE_USDC) * total_shares) // leader_shares


def build_vault_create(
    nonce: int,
    lockup_seconds: int,
    always_proportional_close: bool,
    initial_deposit_usdc: int,
    vault_name: str,
    strategy_description: str,
) -> VaultTx:
    inner = VaultCreateTx(
        nonce,
        lockup_seconds,
        always_proportional_close,
        initial_deposit_usdc,
        vault_name,
        strategy_description,
    )
    return VaultTx(VaultTxVariant.CREATE, inner)


def build_vault_deposit(vault_id: int, nonce: int, amount_usdc: int) -> VaultTx:
    return VaultTx(VaultTxVariant.DEPOSIT, VaultDepositTx(vault_id, nonce, amount_usdc))


def build_vault_withdraw(vault_id: int, nonce: int, withdraw_shares: int) -> VaultTx:
    return VaultTx(
        VaultTxVariant.WITHDRAW, VaultWithdrawTx(vault_id, nonce, withdraw_shares)
    )


def build_vault_set_status(
    nonce: int, vault_id: int, target_status: VaultStatus
) -> VaultTx:
    return VaultTx(
        VaultTxVariant.SET_STATUS, VaultSetStatusTx(nonce, vault_id, target_status)
    )


def build_vault_close(nonce: int, vault_id: int) -> VaultTx:
    return build_vault_set_status(nonce, vault_id, VaultStatus.CLOSED)


def build_vault_distribute(
    vault_id: int, nonce: int, distribute_amount_usdc: int
) -> VaultTx:
    return VaultTx(
        VaultTxVariant.DISTRIBUTE,
        VaultDistributeTx(vault_id, nonce, distribute_amount_usdc),
    )


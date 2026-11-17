# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from enum import IntEnum

from ..core.account_address import AccountAddress
from ..bcs import Deserializer, Serializer

# =============================================================================
# Vault Enums
# =============================================================================


class VaultTxVariant(IntEnum):
    CREATE = 0
    DEPOSIT = 1
    WITHDRAW = 2
    CLP_CONFIG = 3
    CLP_MANAGED_ACCOUNT = 4
    CLP_TRADER_ALLOWLIST_UPDATE = 5
    SET_PARAMS = 6
    SET_STATUS = 7
    CLP_BATCH_CREATE_MANAGED_ACCOUNTS = 8
    DISTRIBUTE = 9


class VaultStatus(IntEnum):
    ACTIVE = 0
    PAUSED = 1
    CLOSED = 2


class ManagedAccountAction(IntEnum):
    UPSERT = 0
    DISABLE = 1
    REMOVE = 2


class ClpTraderAllowlistAction(IntEnum):
    ADD = 0
    REMOVE = 1


# =============================================================================
# Constants
# =============================================================================

VAULT_MIN_INITIAL_DEPOSIT_USDC = 100_000_000
VAULT_CREATION_FEE_USDC = 100_000_000
MIN_LEADER_STAKE_USDC = 100_000_000
VAULT_MIN_LOCKUP_SECONDS = 86400
VAULT_NAME_MAX_LEN = 64
VAULT_STRATEGY_DESC_MAX_LEN = 512
NAV_PRECISION = 1_000_000
BPS_DENOMINATOR = 10_000


class VaultErrorCode(IntEnum):
    Success = 0
    InvalidParameter = 1
    PermissionDenied = 2
    VaultNotFound = 3
    VaultAlreadyExists = 4
    VaultPaused = 5
    VaultClosed = 6
    NonceAlreadyUsed = 7
    InvalidVaultStatus = 8

    DepositAmountTooSmall = 100
    DepositAmountTooLarge = 101
    InsufficientBalanceForDeposit = 102
    LeaderMinOwnershipDepositViolation = 103

    LockupNotExpired = 200
    InsufficientShares = 201
    InsufficientAvailableShares = 202
    WithdrawExceedsLimit = 203
    WithdrawRejectedByEngine = 204
    FreeBalanceRatioTooLow = 205
    DailyWithdrawLimitExceeded = 206
    LeaderMinOwnershipViolation = 207
    WithdrawRequestNotFound = 208
    InvalidWithdrawRequestStatus = 209
    PositionNotFound = 210
    WithdrawQueueFull = 211

    ClpNotInitialized = 300
    ClpAlreadyInitialized = 301
    InvalidClpAccount = 302
    TraderNotInAllowlist = 303
    InvalidSymbolAccounts = 304

    NotVaultLeader = 400
    InvalidVaultAccount = 401
    VaultHasPendingWithdrawals = 402
    VaultHasSharesOutstanding = 403
    VaultNotFlat = 404
    InsufficientParentTradingVolume = 405

    DistributeAmountTooLarge = 450
    DistributeAmountTooSmall = 451
    NoDepositorsToDistribute = 452
    DistributeHasPendingWithdrawals = 453
    DistributeNotUserVault = 454
    LeaderMinStakeViolation = 455

    EngineCallFailed = 500
    EngineInvalidData = 501

    InternalError = 900
    SerializationError = 901
    StorageError = 902


# =============================================================================
# SubaccountId
# =============================================================================


class SubaccountId:
    """
    Subaccount identity (main address + number + derived sub-address + user_name).
    BCS layout (fixed size, 84 bytes):
      address:     [u8; 32]  (32 bytes)
      number:      u32       (4 bytes LE)
      sub_address: [u8; 32]  (32 bytes)
      user_name:   [u8; 16]  (16 bytes)
    """

    address: bytes  # 32 bytes
    number: int  # u32
    sub_address: bytes  # 32 bytes
    user_name: bytes  # 16 bytes

    def __init__(
        self,
        address: bytes,
        number: int,
        sub_address: bytes,
        user_name: bytes = b"\x00" * 16,
    ):
        if len(address) != 32:
            raise ValueError("SubaccountId address must be exactly 32 bytes")
        if len(sub_address) != 32:
            raise ValueError("SubaccountId sub_address must be exactly 32 bytes")
        if len(user_name) != 16:
            raise ValueError("SubaccountId user_name must be exactly 16 bytes")
        self.address = address
        self.number = number
        self.sub_address = sub_address
        self.user_name = user_name

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_fixed_bytes(self.address)
        serializer.serialize_u32(self.number)
        serializer.serialize_fixed_bytes(self.sub_address)
        serializer.serialize_fixed_bytes(self.user_name)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> SubaccountId:
        return SubaccountId(
            address=deserializer.deserialize_fixed_bytes(32),
            number=deserializer.deserialize_u32(),
            sub_address=deserializer.deserialize_fixed_bytes(32),
            user_name=deserializer.deserialize_fixed_bytes(16),
        )


# =============================================================================
# Helper Types
# =============================================================================


class SymbolAccountsEntry:
    symbol_id: int  # u32
    accounts: list  # List[SubaccountId]

    def __init__(self, symbol_id: int, accounts: list):
        self.symbol_id = symbol_id
        self.accounts = accounts

    def serialize(self, serializer: Serializer) -> None:
        serializer.serialize_u32(self.symbol_id)
        serializer.serialize_u32_as_uleb128(len(self.accounts))
        for account in self.accounts:
            account.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> SymbolAccountsEntry:
        symbol_id = deserializer.deserialize_u32()
        length = deserializer.deserialize_u32_from_uleb128()
        accounts = [SubaccountId.deserialize(deserializer) for _ in range(length)]
        return SymbolAccountsEntry(symbol_id, accounts)


class ClpTraderAllowlistEntry:
    clp_account: SubaccountId
    traders: list  # List[AccountAddress]

    def __init__(self, clp_account: SubaccountId, traders: list):
        self.clp_account = clp_account
        self.traders = traders

    def serialize(self, serializer: Serializer) -> None:
        self.clp_account.serialize(serializer)
        serializer.serialize_u32_as_uleb128(len(self.traders))
        for trader in self.traders:
            trader.serialize(serializer)

    @staticmethod
    def deserialize(deserializer: Deserializer) -> ClpTraderAllowlistEntry:
        clp_account = SubaccountId.deserialize(deserializer)
        length = deserializer.deserialize_u32_from_uleb128()
        traders = [AccountAddress.deserialize(deserializer) for _ in range(length)]
        return ClpTraderAllowlistEntry(clp_account, traders)

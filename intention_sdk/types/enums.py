# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from enum import IntEnum


class DexOrderlessTxVariant(IntEnum):
    DEX = 0
    DEX_USER_CONFIG = 1
    DEX_SYSTEM_CONFIG = 2
    DEX_TRANSFER = 3
    DEX_AGENT = 4
    VAULT = 5
    #: Managing a multisig account, or acting as one.
    MULTISIG = 6


class DexOrdersVariant(IntEnum):
    PLACE = 0
    CANCEL = 1
    REPLACE = 2
    REPLACE_CONDITION = 3
    #: The same orders as a replace, except that the engine rejects a replacement which would
    #: cross the book instead of filling it. A separate variant rather than a flag on the order
    #: because BCS reads a struct as a fixed-length sequence, so a tail field is not optional on
    #: the wire.
    REPLACE_MAKER_ONLY = 4
    #: Carries no orders. Consuming its ``(sender, nonce)`` is the whole effect, and that is what
    #: cancels a same-nonce order which has not reached a block yet: the two race for the nonce
    #: and the loser is discarded as ``NONCE_ALREADY_USED``.
    NOOP = 5


class Grouping(IntEnum):
    NA = 0
    NORMAL_TPSL = 1
    POSITION_TPSL = 2


class SymbolType(IntEnum):
    UNSPECIFIED = 0
    SPOT = 1
    PERPETUAL = 2


class Side(IntEnum):
    UNSPECIFIED = 0
    BUY = 1
    SELL = 2
    CLOSEALL_LONG = 3
    CLOSEALL_SHORT = 4


class OrderBasicType(IntEnum):
    UNSPECIFIED = 0
    MARKET = 1
    LIMIT = 2


class TimeInForce(IntEnum):
    UNSPECIFIED = 0
    IOC = 1
    FOK = 2
    AON = 3
    GTC = 4
    ALO = 5
    GTD = 6
    GTB = 7


class ConditionType(IntEnum):
    UNSPECIFIED = 0
    STOP_LOSS = 1
    TAKE_PROFIT = 2


class TriggerPriceType(IntEnum):
    LAST_PRICE = 0
    MARK_PRICE = 1


class MarginMode(IntEnum):
    CROSS = 0
    ISOLATED = 1
    PORTFOLIO = 2


class MarginModeType(IntEnum):
    ISOLATED = 0
    CROSS = 1
    PORTFOLIO = 2


class StpMode(IntEnum):
    """Self-Trade Prevention mode (per-order).

    Determines behavior when a taker order would match against
    the same account's resting maker order.
    """

    EXPIRE_TAKER = 0  # Cancel incoming taker, maker stays on book
    EXPIRE_MAKER = 1  # Cancel resting maker, taker continues matching (default)
    EXPIRE_BOTH = 2  # Cancel both sides


class CreatedBy(IntEnum):
    USER = 0
    LIQUIDATION = 1
    ADL = 2
    CONDITION = 3
    STOP = 4


class OrderPositionMode(IntEnum):
    NET = 0
    HEDGE = 1


class PositionMode(IntEnum):
    NET = 0
    HEDGE = 1


class DexUserConfigTxVariant(IntEnum):
    SET_USER_LEVERAGE = 0
    CHANGE_POSITION_MODE = 1
    CHANGE_MARGIN_MODE = 2
    CREATE_SUB_ACCOUNT = 3
    MODIFY_SUB_ACCOUNT = 4
    ADJUST_ISOLATED_MARGIN = 5
    REGISTER_REFERRAL_CODE = 6
    BIND_REFERRER = 7


class DexTransferVariant(IntEnum):
    INTERNAL_TRANSFER = 0
    ACCOUNT_TRANSFER = 1
    CROSS_TRANSFER = 2
    FAUCET_MINT = 3
    CLAIM_REFERRAL_REWARDS = 4


class AgentOperationVariant(IntEnum):
    APPROVE = 0
    REVOKE = 1
    #: End every grant this master holds, in one operation.
    #:
    #: Appended, so ``APPROVE`` and ``REVOKE`` keep their tags. It carries no name:
    #: the operation names an end state rather than a record, so it is idempotent --
    #: an account holding no grants succeeds without writing anything. Modelled as a
    #: revoke with an empty name it would be answered ``DexAgentNotFound``, an error
    #: aimed at the target of a request that was actually shaped wrong.
    REVOKE_ALL = 2


class AccountType(IntEnum):
    PERP = 0
    SPOT = 1


class CrossTransferOption(IntEnum):
    MINT = 0
    BURN = 1


class SymbolStatus(IntEnum):
    ACTIVE = 0
    PAUSED = 1
    REDUCE_ONLY = 2
    CANCEL_ONLY = 2  # Deprecated: the old name of REDUCE_ONLY, kept as an alias.
    POST_ONLY = 3
    INITIALIZING = 4
    FINAL_SETTLEMENT = 5
    PRE_OPEN = 6
    CLOSED = 7


# Values of the delisting events' price_source and of a settled leg's side and
# margin_mode. The events keep these as plain ints, so a
# value added later is kept as read.
class DelistingPriceSource(IntEnum):
    WINDOW_TWAP = 0
    T0_INDEX = 1
    CURRENT_MARK = 2


class DelistingLegSide(IntEnum):
    LONG = 0
    SHORT = 1


class DelistingLegMarginMode(IntEnum):
    CROSS = 0
    ISOLATED = 1


class PerpetualTier(IntEnum):
    A = 0
    B = 1
    C = 2


class DexConfigTxVariant(IntEnum):
    USER_CONFIG = 0
    SYSTEM_CONFIG = 1


class TransactionPayloadVariants(IntEnum):
    ENTRY_FUNCTION = 0
    DEX_ORDERLESS = 1


class SigningSchemeInput(IntEnum):
    SECP256K1_ECDSA = 2


# --- Multisig account enums ----------------------------------------------
#
# Matches the on-chain multisig protocol. The numbering is consensus
# critical twice over: it is the BCS variant tag, and ``MultisigOp::kind`` /
# ``GatedPayload::kind`` are bound into the operation id owners sign. Append only;
# never renumber.


class MultisigOpVariant(IntEnum):
    """What a ``Multisig`` transaction asks for."""

    #: Install a policy on a fresh derived address.
    CREATE = 0
    #: Put an existing key-controlled account under a policy, address kept.
    INSTALL = 1
    #: Change the owner set or the threshold.
    UPDATE_POLICY = 2
    #: Leave the policy and hand the account to one named key.
    REMOVE = 3
    #: Rotate a single-key account's control key without changing its address.
    ROTATE_KEY = 4
    #: Run one gated payload as the account.
    EXECUTE = 5


class GatedPayloadVariant(IntEnum):
    """A payload a policy account executes through its owners."""

    DEX_TRANSFER = 0
    VAULT = 1
    DEX_AGENT = 2
    CREATE_SUB_ACCOUNT = 3


class KeyProofVariant(IntEnum):
    """How an incoming control key proves it can sign."""

    SECP256K1 = 0
    ED25519 = 1


class AuthorityKindVariant(IntEnum):
    """What controls an account, as reported in an authority record or event."""

    #: One key, named explicitly.
    KEY = 0
    #: A k-of-n owner set.
    POLICY = 1

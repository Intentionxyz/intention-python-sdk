# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""EIP-712 typed data for wallet-signed transactions.

Payloads that move funds or grant authority are signed over named fields a wallet
can render. Everything else -- orders, leverage, admin ops -- is signed by an agent
key with no dialog to render, and keeps the opaque wrapper.

Consensus-critical: digests must match the on-chain signing contract and
reference signing vectors.
``test_eip712_typed_data.py`` pins the bytes.

Type names use ``_``, not ``:``. Both ``viem`` and ``@metamask/eth-sig-util`` (what
MetaMask hashes with) stop parsing a type name at the colon and drop referenced
struct types from ``encodeType`` -- invisible for the flat types, but for the batch
types it silently yields a non-standard typeHash that the chain then rejects.
"""

from __future__ import annotations

from typing import List, NamedTuple, Optional

from ..core.account_address import AccountAddress
from .dex_payloads import (
    AgentApprove,
    AgentRevoke,
    CreateSubAccount,
    DexAgentTx,
    DexOrderlessTx,
    DexTransferTx,
    DexUserConfigTx,
    ModifySubAccount,
)
from ..types.enums import (
    AgentOperationVariant,
    CrossTransferOption,
    DexOrderlessTxVariant,
    DexTransferVariant,
    DexUserConfigTxVariant,
)
from ..core.crypto import keccak256

# --- Domain ---------------------------------------------------------------

DOMAIN_TYPE = (
    b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"
)
DOMAIN_NAME = b"Intention"
DOMAIN_VERSION = b"1"

MAINNET_CHAIN_ID = 1

# The EVM chain whose id goes in the domain -- *not* this chain's id. MetaMask
# refuses to sign typed data whose ``domain.chainId`` is not the network the wallet
# is on, and it cannot be on this chain: this is not an EVM chain. The network the
# user is on when they sign is the one the bridge lives on, so that is the id the
# domain carries. Hyperliquid does the same thing for the same reason.
def signature_chain_id(chain_id: int) -> int:
    """The EVM chain whose id goes in the domain.

    Every network but mainnet bridges to Arbitrum Sepolia, so this is written as one exception rather than a table of every chain id. A missing row in a table would not fail loudly: the domain would carry a chain the wallet is not on, and MetaMask would simply refuse to sign.
    """
    return 42161 if chain_id == MAINNET_CHAIN_ID else 421614


def intention_chain_name(chain_id: int) -> bytes:
    """What the user reads: which environment this is.

    This label is signed: it is the ``intentionChain`` field of every typed message, so it must match the chain's label byte for byte, and renaming one breaks every signature made for that network. It is coarse on purpose; what binds a signature to one network is this chain's chain_id, which the digest field covers. Chain ids must therefore be unique per network: a signature made under a given chain_id verifies on any network that uses the same id.
    """
    return {
        1: b"Mainnet",
        2: b"Testnet",
        3: b"Devnet",
        4: b"Nightly",
    }.get(chain_id, b"Localnet")


def domain_separator(chain_id: int) -> bytes:
    return keccak256(
        keccak256(DOMAIN_TYPE)
        + keccak256(DOMAIN_NAME)
        + keccak256(DOMAIN_VERSION)
        + enc_uint(signature_chain_id(chain_id))
        + bytes(32)  # verifyingContract = address(0)
    )


# --- Type strings ---------------------------------------------------------

TYPE_APPROVE_AGENT = b"IntentionTransaction_ApproveAgent(string intentionChain,address agentAddress,string name,uint64 expiryTimestamp,uint64 nonce,bytes32 digest)"
TYPE_REVOKE_AGENT = b"IntentionTransaction_RevokeAgent(string intentionChain,string name,uint64 nonce,bytes32 digest)"
TYPE_CROSS_TRANSFER_BURN = b"IntentionTransaction_CrossTransferBurn(string intentionChain,address toAccount,string token,string amount,string accountType,uint64 nonce,bytes32 digest)"
TYPE_INTERNAL_TRANSFER = b"IntentionTransaction_InternalTransfer(string intentionChain,address fromSubaccount,address toSubaccount,string token,string amount,string accountType,uint64 nonce,bytes32 digest)"
TYPE_ACCOUNT_TRANSFER = b"IntentionTransaction_AccountTransfer(string intentionChain,address toAccount,string token,string amount,string accountType,uint64 nonce,bytes32 digest)"
#: No ``name`` field, and its own primary type rather than a ``RevokeAgent``
#: carrying an empty one: the operation declares an end state ("this account has no
#: agents"), so a dialog naming one specific grant would name a grant that is not
#: the thing being pulled.
TYPE_REVOKE_ALL_AGENTS = b"IntentionTransaction_RevokeAllAgents(string intentionChain,uint64 nonce,bytes32 digest)"
#: The envelope a multisig submitter signs. It names the account and the operation
#: and leaves the details to ``digest``: the fields that matter were already shown
#: to whoever signed the k-of-n approval, and this signature only says who handed
#: the finished operation in. The approval documents are in ``multisig_typed_data``.
TYPE_MULTISIG_SUBMIT = b"IntentionTransaction_MultisigSubmit(string intentionChain,address account,string operation,uint64 nonce,bytes32 digest)"
TYPE_CREATE_SUBACCOUNT = b"IntentionTransaction_CreateSubAccount(string intentionChain,string name,uint64 nonce,bytes32 digest)"
TYPE_MODIFY_SUBACCOUNT = b"IntentionTransaction_ModifySubAccount(string intentionChain,address subAddress,string name,uint64 nonce,bytes32 digest)"

# Batch forms. The referenced struct's own definition is appended to the primary
# type's, per EIP-712: the referenced set is sorted by name and concatenated.
TYPE_CROSS_TRANSFER_ITEM = (
    b"CrossTransferItem(address toAccount,string token,string amount,string accountType)"
)
TYPE_CROSS_TRANSFER_BURN_BATCH = (
    b"IntentionTransaction_CrossTransferBurnBatch(string intentionChain,CrossTransferItem[] transfers,uint64 nonce,bytes32 digest)"
    + TYPE_CROSS_TRANSFER_ITEM
)
TYPE_INTERNAL_TRANSFER_ITEM = b"InternalTransferItem(address fromSubaccount,address toSubaccount,string token,string amount,string accountType)"
TYPE_INTERNAL_TRANSFER_BATCH = (
    b"IntentionTransaction_InternalTransferBatch(string intentionChain,InternalTransferItem[] transfers,uint64 nonce,bytes32 digest)"
    + TYPE_INTERNAL_TRANSFER_ITEM
)
TYPE_ACCOUNT_TRANSFER_ITEM = (
    b"AccountTransferItem(address toAccount,string token,string amount,string accountType)"
)
TYPE_ACCOUNT_TRANSFER_BATCH = (
    b"IntentionTransaction_AccountTransferBatch(string intentionChain,AccountTransferItem[] transfers,uint64 nonce,bytes32 digest)"
    + TYPE_ACCOUNT_TRANSFER_ITEM
)


# --- Field encoding -------------------------------------------------------



def account_type_name(account_type) -> bytes:
    """The name this account type carries on the wire.

    The explorer and the wallet must call the same account the same thing; this
    mirrors `AccountType::wire_name` on the chain.
    """
    return b"spot" if int(account_type) == 1 else b"perp"


def enc_string(value: bytes) -> bytes:
    return keccak256(value)


def enc_uint(value: int) -> bytes:
    return value.to_bytes(32, "big")


class Asset(NamedTuple):
    """What the wire calls asset 0, a person calls USDC.

    Name and scale come from one table because they are one fact about the
    asset: rendering either without the other puts a number in the signing
    dialog that does not mean what it says. The table is a pure function of the
    asset id because it has to be -- the signer, the node and MetaMask each
    compute this digest on their own and none of them can read chain state
    while doing it.
    """

    symbol: str
    decimals: int


def asset(asset_id: int) -> Optional[Asset]:
    """``None`` for an id the table cannot name.

    The caller falls back to the opaque wrapper rather than guessing: a wrong
    name or a wrong scale in the signing dialog is worse than a hash, which at
    least does not claim to be readable.
    """
    if asset_id == 0:
        return Asset("USDC", 6)  # dex_sys_config: "USDC quantums (6 decimals)"
    return None


def format_amount(quantums: int, decimals: int) -> str:
    """``10500000`` at six decimals renders as ``10.5``, ``10000000`` as ``10``.

    No separators, no trailing zeros, no trailing point. This string is hashed,
    so all five implementations must produce it byte for byte.
    """
    scale = 10 ** decimals
    whole, frac = divmod(quantums, scale)
    if frac == 0:
        return str(whole)
    return f"{whole}.{str(frac).zfill(decimals).rstrip('0')}"


def enc_token(asset_id: int) -> bytes:
    meta = asset(asset_id)
    if meta is None:
        raise _NotEvmShaped(f"asset {asset_id} has no token name")
    return enc_string(meta.symbol.encode())


def enc_amount(quantums: int, asset_id: int) -> bytes:
    meta = asset(asset_id)
    if meta is None:
        raise _NotEvmShaped(f"asset {asset_id} has no token name")
    return enc_string(format_amount(quantums, meta.decimals).encode())


class _NotEvmShaped(Exception):
    """Raised internally when an address cannot be encoded as EIP-712 ``address``."""


def enc_address(address: AccountAddress) -> bytes:
    """EIP-712 ``address`` is a uint160: twenty bytes right-aligned in thirty-two.

    Ours are already that shape. Anything in the top twelve bytes is not an address
    a wallet could have produced, so it falls back to the opaque wrapper --
    the chain does the same, and the two must agree on every input.
    """
    raw = bytes(address.address)
    if any(raw[:12]):
        raise _NotEvmShaped()
    return raw


def struct_hash(type_string: bytes, fields: List[bytes]) -> bytes:
    return keccak256(keccak256(type_string) + b"".join(fields))


def enc_struct_array(item_hashes: List[bytes]) -> bytes:
    """A struct array encodes as the hash of its elements' struct hashes."""
    return keccak256(b"".join(item_hashes))


def eip712_digest(domain: bytes, sh: bytes) -> bytes:
    return keccak256(b"\x19\x01" + domain + sh)


# --- Payload -> typed data ------------------------------------------------


def typed_data_digest(raw_txn) -> Optional[bytes]:
    try:
        return _typed_data_digest(raw_txn)
    except _NotEvmShaped:
        # Not an address a wallet could have produced; there is nothing readable to
        # show, so this falls back to the opaque wrapper exactly as the chain does.
        return None


def _typed_data_digest(raw_txn) -> Optional[bytes]:
    """The 32 bytes a wallet-signed transaction is signed over, or ``None``.

    ``None`` is a classification, not a failure. It *is* a failure for anything that
    moves funds or grants authority to land here.
    """
    payload = getattr(raw_txn, "payload", None)
    dex = getattr(payload, "value", None) if payload is not None else None
    if not isinstance(dex, DexOrderlessTx):
        return None

    chain_id = raw_txn.chain_id
    domain = domain_separator(chain_id)
    chain_name = enc_string(intention_chain_name(chain_id))

    # What the opaque wrapper used to be the whole of, now one field among many.
    # It is what keeps sender, sequence_number, gas, expiry, this chain's chain_id,
    # and every payload field not shown above under the signature.
    # Lazy: orders are the highest-volume payload and never reach it.
    def digest() -> bytes:
        return keccak256(raw_txn.keyed())

    inner = dex.inner

    if dex.variant == DexOrderlessTxVariant.DEX_AGENT and isinstance(inner, DexAgentTx):
        op = inner.operation
        if inner.variant == AgentOperationVariant.APPROVE and isinstance(
            op, AgentApprove
        ):
            sh = struct_hash(
                TYPE_APPROVE_AGENT,
                [
                    chain_name,
                    enc_address(op.agent_address),
                    enc_string(op.name.encode()),
                    enc_uint(op.expiry_timestamp),
                    enc_uint(inner.nonce),
                    digest(),
                ],
            )
        elif inner.variant == AgentOperationVariant.REVOKE and isinstance(
            op, AgentRevoke
        ):
            sh = struct_hash(
                TYPE_REVOKE_AGENT,
                [chain_name, enc_string(op.name.encode()), enc_uint(inner.nonce), digest()],
            )
        elif inner.variant == AgentOperationVariant.REVOKE_ALL:
            # No operation fields to check: the variant tag is the whole operation,
            # so there is nothing an isinstance here would catch.
            sh = struct_hash(
                TYPE_REVOKE_ALL_AGENTS,
                [chain_name, enc_uint(inner.nonce), digest()],
            )
        else:
            return None

    elif dex.variant == DexOrderlessTxVariant.MULTISIG:
        # The envelope, not the approval: the owners' k-of-n documents live in
        # ``multisig_typed_data`` and are signed before this transaction exists.
        # This signature says who handed the finished operation in.
        from .multisig_payloads import DexMultisigTx, submit_operation_name

        if not isinstance(inner, DexMultisigTx):
            return None
        sh = struct_hash(
            TYPE_MULTISIG_SUBMIT,
            [
                chain_name,
                enc_address(inner.account),
                enc_string(submit_operation_name(inner.op).encode()),
                enc_uint(inner.nonce),
                digest(),
            ],
        )

    elif dex.variant == DexOrderlessTxVariant.DEX_TRANSFER and isinstance(
        inner, DexTransferTx
    ):
        items = inner.payload
        if not items:
            return None

        if inner.variant == DexTransferVariant.CROSS_TRANSFER:
            # Only a withdrawal is wallet-signed. A Mint is the bridge relayer
            # crediting a deposit; there is no user at a wallet, and it is not
            # spending the signer's funds.
            if inner.option != CrossTransferOption.BURN:
                return None
            if len(items) == 1:
                i = items[0]
                sh = struct_hash(
                    TYPE_CROSS_TRANSFER_BURN,
                    [
                        chain_name,
                        enc_address(i.to_account),
                        enc_token(i.asset_id),
                        enc_amount(i.amount, i.asset_id),
                        enc_string(account_type_name(i.account_type)),
                        enc_uint(inner.nonce),
                        digest(),
                    ],
                )
            else:
                sh = struct_hash(
                    TYPE_CROSS_TRANSFER_BURN_BATCH,
                    [
                        chain_name,
                        enc_struct_array([
                            struct_hash(
                                TYPE_CROSS_TRANSFER_ITEM,
                                [enc_address(i.to_account), enc_token(i.asset_id), enc_amount(i.amount, i.asset_id),
                                 enc_string(account_type_name(i.account_type))],
                            )
                            for i in items
                        ]),
                        enc_uint(inner.nonce),
                        digest(),
                    ],
                )

        elif inner.variant == DexTransferVariant.INTERNAL_TRANSFER:
            if len(items) == 1:
                i = items[0]
                sh = struct_hash(
                    TYPE_INTERNAL_TRANSFER,
                    [
                        chain_name,
                        enc_address(i.from_subaddress),
                        enc_address(i.to_subaddress),
                        enc_token(i.asset_id),
                        enc_amount(i.amount, i.asset_id),
                        enc_string(account_type_name(i.account_type)),
                        enc_uint(inner.nonce),
                        digest(),
                    ],
                )
            else:
                sh = struct_hash(
                    TYPE_INTERNAL_TRANSFER_BATCH,
                    [
                        chain_name,
                        enc_struct_array([
                            struct_hash(
                                TYPE_INTERNAL_TRANSFER_ITEM,
                                [
                                    enc_address(i.from_subaddress),
                                    enc_address(i.to_subaddress),
                                    enc_token(i.asset_id),
                                    enc_amount(i.amount, i.asset_id),
                                    enc_string(account_type_name(i.account_type)),
                                ],
                            )
                            for i in items
                        ]),
                        enc_uint(inner.nonce),
                        digest(),
                    ],
                )

        elif inner.variant == DexTransferVariant.ACCOUNT_TRANSFER:
            if len(items) == 1:
                i = items[0]
                sh = struct_hash(
                    TYPE_ACCOUNT_TRANSFER,
                    [
                        chain_name,
                        enc_address(i.to_account),
                        enc_token(i.asset_id),
                        enc_amount(i.amount, i.asset_id),
                        enc_string(account_type_name(i.account_type)),
                        enc_uint(inner.nonce),
                        digest(),
                    ],
                )
            else:
                sh = struct_hash(
                    TYPE_ACCOUNT_TRANSFER_BATCH,
                    [
                        chain_name,
                        enc_struct_array([
                            struct_hash(
                                TYPE_ACCOUNT_TRANSFER_ITEM,
                                [enc_address(i.to_account), enc_token(i.asset_id), enc_amount(i.amount, i.asset_id),
                                 enc_string(account_type_name(i.account_type))],
                            )
                            for i in items
                        ]),
                        enc_uint(inner.nonce),
                        digest(),
                    ],
                )
        else:
            # FaucetMint: a test faucet, no wallet involved.
            return None

    elif dex.variant == DexOrderlessTxVariant.DEX_USER_CONFIG and isinstance(
        inner, DexUserConfigTx
    ):
        p = inner.payload
        if inner.variant == DexUserConfigTxVariant.CREATE_SUB_ACCOUNT and isinstance(
            p, CreateSubAccount
        ):
            sh = struct_hash(
                TYPE_CREATE_SUBACCOUNT,
                [chain_name, enc_string(p.name.encode()), enc_uint(p.nonce), digest()],
            )
        elif inner.variant == DexUserConfigTxVariant.MODIFY_SUB_ACCOUNT and isinstance(
            p, ModifySubAccount
        ):
            sh = struct_hash(
                TYPE_MODIFY_SUBACCOUNT,
                [
                    chain_name,
                    enc_address(p.sub_address),
                    enc_string(p.name.encode()),
                    enc_uint(p.nonce),
                    digest(),
                ],
            )
        else:
            # Trading configuration, not funds or authority.
            return None

    else:
        # Orders, vault operations, admin config: agent- or admin-signed.
        return None

    return eip712_digest(domain, sh)

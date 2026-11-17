# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""What a multisig owner signs.

An owner approves an operation by signing an ``IntentionMultisig_*`` document in an
ordinary EVM wallet; the chain recovers the owner's address from the signature and
counts distinct owners against the threshold. This module computes the 32 bytes
that document hashes to, which is what a backend needs in order to ask for a
signature and to check the one it gets back.

Three digests, signed in this order because the data says so:

1. :func:`key_challenge_digest` -- an incoming control key proves it exists. Bound
   to the operation *kind*, not its id: the id covers the whole operation and the
   key proof is inside it, so a challenge bound to the id could never be signed.
2. :func:`approval_digest` (:func:`create_approval_digest` for ``Create``) -- the
   owners approve the assembled operation, key proof included.
3. :func:`submit_struct_hash` -- the submitting owner's own envelope, folded into
   the transaction digest ``eip712_typed_data`` computes.

Rendering the document a wallet displays lives in the TypeScript SDK, which is the
one with a browser wallet in front of it; the digests here are the same bytes that
document hashes to.

Consensus-critical: digests must match the on-chain multisig signing contract.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Union

from ..core.account_address import AccountAddress
from ..bcs import Serializer
from .dex_payloads import (
    AgentApprove,
    AgentRevoke,
    CreateSubAccount,
    DexAgentTx,
    DexTransferTx,
)
from ..types.enums import (
    AgentOperationVariant,
    CrossTransferOption,
    DexTransferVariant,
    GatedPayloadVariant,
    MultisigOpVariant,
)
from .typed_data import (
    _NotEvmShaped,
    account_type_name,
    domain_separator,
    eip712_digest,
    enc_address,
    enc_amount,
    enc_string,
    enc_struct_array,
    enc_token,
    enc_uint,
    intention_chain_name,
    struct_hash,
)
from ..types.vault import VaultTxVariant
from .multisig_payloads import (
    MULTISIG_AUTHORIZATION_VERSION,
    GatedPayload,
    MultisigOp,
    MultisigOpCreate,
    MultisigOpExecute,
    MultisigOpInstall,
    MultisigOpRemove,
    MultisigOpUpdatePolicy,
    owner_bytes,
    submit_operation_name,
)

# --- Type strings ---------------------------------------------------------
#
# Every operation opens with the chain name, the account and the authority epoch,
# and closes with the expiry and the operation id. What sits between is the
# operation. ``digest`` is the operation id, so it covers every byte of the payload
# including the ones the dialog does not spell out.

TYPE_CREATE_POLICY = b"IntentionMultisig_CreatePolicy(string intentionChain,address account,address creator,address[] owners,uint8 threshold,uint64 expiresAt,bytes32 digest)"
TYPE_INSTALL_POLICY = b"IntentionMultisig_InstallPolicy(string intentionChain,address account,uint64 authorityEpoch,address[] owners,uint8 threshold,uint64 expiresAt,bytes32 digest)"
TYPE_UPDATE_POLICY = b"IntentionMultisig_UpdatePolicy(string intentionChain,address account,uint64 authorityEpoch,address[] owners,uint8 threshold,uint64 expiresAt,bytes32 digest)"
TYPE_REMOVE_POLICY = b"IntentionMultisig_RemovePolicy(string intentionChain,address account,uint64 authorityEpoch,bytes32 newAuthKey,uint64 expiresAt,bytes32 digest)"
TYPE_KEY_CHALLENGE = b"IntentionMultisig_KeyChallenge(string intentionChain,address account,uint64 authorityEpoch,bytes32 newAuthKey,uint8 operation)"

TYPE_ACCOUNT_TRANSFER = b"IntentionMultisig_AccountTransfer(string intentionChain,address account,uint64 authorityEpoch,address toAccount,string token,string amount,string accountType,uint64 nonce,uint64 expiresAt,bytes32 digest)"
TYPE_ACCOUNT_TRANSFER_BATCH = b"IntentionMultisig_AccountTransferBatch(string intentionChain,address account,uint64 authorityEpoch,AccountTransferItem[] transfers,uint64 nonce,uint64 expiresAt,bytes32 digest)AccountTransferItem(address toAccount,string token,string amount,string accountType)"
TYPE_CROSS_TRANSFER_BURN = b"IntentionMultisig_CrossTransferBurn(string intentionChain,address account,uint64 authorityEpoch,address toAccount,string token,string amount,string accountType,uint64 nonce,uint64 expiresAt,bytes32 digest)"
TYPE_CROSS_TRANSFER_BURN_BATCH = b"IntentionMultisig_CrossTransferBurnBatch(string intentionChain,address account,uint64 authorityEpoch,CrossTransferItem[] transfers,uint64 nonce,uint64 expiresAt,bytes32 digest)CrossTransferItem(address toAccount,string token,string amount,string accountType)"
TYPE_INTERNAL_TRANSFER = b"IntentionMultisig_InternalTransfer(string intentionChain,address account,uint64 authorityEpoch,address fromSubaccount,address toSubaccount,string token,string amount,string accountType,uint64 nonce,uint64 expiresAt,bytes32 digest)"
TYPE_INTERNAL_TRANSFER_BATCH = b"IntentionMultisig_InternalTransferBatch(string intentionChain,address account,uint64 authorityEpoch,InternalTransferItem[] transfers,uint64 nonce,uint64 expiresAt,bytes32 digest)InternalTransferItem(address fromSubaccount,address toSubaccount,string token,string amount,string accountType)"

TYPE_APPROVE_AGENT = b"IntentionMultisig_ApproveAgent(string intentionChain,address account,uint64 authorityEpoch,address agentAddress,string name,uint64 expiryTimestamp,uint64 nonce,uint64 expiresAt,bytes32 digest)"
TYPE_REVOKE_AGENT = b"IntentionMultisig_RevokeAgent(string intentionChain,address account,uint64 authorityEpoch,string name,uint64 nonce,uint64 expiresAt,bytes32 digest)"
#: No ``name``: the operation declares an end state, so a document naming one
#: specific grant would name a grant that is not the one being pulled.
TYPE_REVOKE_ALL_AGENTS = b"IntentionMultisig_RevokeAllAgents(string intentionChain,address account,uint64 authorityEpoch,uint64 nonce,uint64 expiresAt,bytes32 digest)"
TYPE_CREATE_SUBACCOUNT = b"IntentionMultisig_CreateSubAccount(string intentionChain,address account,uint64 authorityEpoch,string name,uint64 nonce,uint64 expiresAt,bytes32 digest)"
#: Vault operations are not rendered field by field: the single-signer path signs
#: them opaquely too. The operation name and the nonce are shown; everything else
#: is covered by ``digest``.
TYPE_VAULT_OPERATION = b"IntentionMultisig_VaultOperation(string intentionChain,address account,uint64 authorityEpoch,string operation,uint64 nonce,uint64 expiresAt,bytes32 digest)"

#: Item types, hashed on their own for the ``*Batch`` struct arrays. Deliberately
#: identical to the single-signer ones: an item is the same thing whoever approves it.
TYPE_ACCOUNT_TRANSFER_ITEM = (
    b"AccountTransferItem(address toAccount,string token,string amount,string accountType)"
)
TYPE_CROSS_TRANSFER_ITEM = (
    b"CrossTransferItem(address toAccount,string token,string amount,string accountType)"
)
TYPE_INTERNAL_TRANSFER_ITEM = b"InternalTransferItem(address fromSubaccount,address toSubaccount,string token,string amount,string accountType)"

#: The submitting owner's envelope. It names the account and the operation and
#: leaves the details to ``digest``, because the fields that matter were already
#: shown to whoever signed the proof.
TYPE_MULTISIG_SUBMIT = b"IntentionTransaction_MultisigSubmit(string intentionChain,address account,string operation,uint64 nonce,bytes32 digest)"

_VAULT_OPERATION_NAMES = {
    VaultTxVariant.CREATE: b"vault_create",
    VaultTxVariant.DEPOSIT: b"vault_deposit",
    VaultTxVariant.WITHDRAW: b"vault_withdraw",
    VaultTxVariant.CLP_CONFIG: b"vault_clp_config",
    VaultTxVariant.CLP_MANAGED_ACCOUNT: b"vault_clp_managed_account",
    VaultTxVariant.CLP_TRADER_ALLOWLIST_UPDATE: b"vault_clp_trader_allowlist_update",
    VaultTxVariant.SET_PARAMS: b"vault_set_params",
    VaultTxVariant.SET_STATUS: b"vault_set_status",
    VaultTxVariant.CLP_BATCH_CREATE_MANAGED_ACCOUNTS: b"vault_clp_batch_create_managed_accounts",
    VaultTxVariant.DISTRIBUTE: b"vault_distribute",
}


def _enc_address_array(owners: Sequence[bytes]) -> bytes:
    """An ``address[]`` field: the hash of the concatenated encoded elements."""
    encoded = b""
    for owner in owners:
        word = bytearray(32)
        word[12:] = owner_bytes(owner)
        encoded += bytes(word)
    from ..core.crypto import keccak256

    return keccak256(encoded)


def _head(chain_id: int, account: AccountAddress, authority_epoch: int) -> List[bytes]:
    return [
        enc_string(intention_chain_name(chain_id)),
        enc_address(account),
        enc_uint(authority_epoch),
    ]


def _tail(expires_at_secs: int, op_id: bytes) -> List[bytes]:
    if len(op_id) != 32:
        raise ValueError(f"an operation id must be 32 bytes, got {len(op_id)}")
    return [enc_uint(expires_at_secs), op_id]


def _transfer_fields(
    single_type: bytes,
    batch_type: bytes,
    item_type: bytes,
    items: List[List[bytes]],
    head: List[bytes],
    nonce: int,
    tail: List[bytes],
):
    """Pick the single or the batch type, so a one-item transfer shows its fields
    inline rather than as a one-element array."""
    if not items:
        return None
    if len(items) == 1:
        return single_type, head + items[0] + [enc_uint(nonce)] + tail
    item_hashes = [struct_hash(item_type, item) for item in items]
    return batch_type, head + [enc_struct_array(item_hashes), enc_uint(nonce)] + tail


def _execute_fields(payload: GatedPayload, head: List[bytes], tail: List[bytes]):
    inner = payload.inner

    if payload.variant == GatedPayloadVariant.DEX_TRANSFER:
        assert isinstance(inner, DexTransferTx)
        items = inner.payload
        if not items:
            return None
        if inner.variant == DexTransferVariant.ACCOUNT_TRANSFER:
            return _transfer_fields(
                TYPE_ACCOUNT_TRANSFER,
                TYPE_ACCOUNT_TRANSFER_BATCH,
                TYPE_ACCOUNT_TRANSFER_ITEM,
                [
                    [
                        enc_address(i.to_account),
                        enc_token(i.asset_id),
                        enc_amount(i.amount, i.asset_id),
                        enc_string(account_type_name(i.account_type)),
                    ]
                    for i in items
                ],
                head,
                inner.nonce,
                tail,
            )
        if inner.variant == DexTransferVariant.CROSS_TRANSFER:
            # Only a withdrawal is owner-approved. A mint credits a bridge deposit
            # and is authorized by the bridge committee, not by this account.
            if inner.option != CrossTransferOption.BURN:
                return None
            return _transfer_fields(
                TYPE_CROSS_TRANSFER_BURN,
                TYPE_CROSS_TRANSFER_BURN_BATCH,
                TYPE_CROSS_TRANSFER_ITEM,
                [
                    [
                        enc_address(i.to_account),
                        enc_token(i.asset_id),
                        enc_amount(i.amount, i.asset_id),
                        enc_string(account_type_name(i.account_type)),
                    ]
                    for i in items
                ],
                head,
                inner.nonce,
                tail,
            )
        if inner.variant == DexTransferVariant.INTERNAL_TRANSFER:
            return _transfer_fields(
                TYPE_INTERNAL_TRANSFER,
                TYPE_INTERNAL_TRANSFER_BATCH,
                TYPE_INTERNAL_TRANSFER_ITEM,
                [
                    [
                        enc_address(i.from_subaddress),
                        enc_address(i.to_subaddress),
                        enc_token(i.asset_id),
                        enc_amount(i.amount, i.asset_id),
                        enc_string(account_type_name(i.account_type)),
                    ]
                    for i in items
                ],
                head,
                inner.nonce,
                tail,
            )
        # A faucet mint has no owner-visible meaning on a policy account.
        return None

    if payload.variant == GatedPayloadVariant.DEX_AGENT:
        assert isinstance(inner, DexAgentTx)
        op = inner.operation
        if inner.variant == AgentOperationVariant.APPROVE and isinstance(
            op, AgentApprove
        ):
            return TYPE_APPROVE_AGENT, head + [
                enc_address(op.agent_address),
                enc_string(op.name.encode()),
                enc_uint(op.expiry_timestamp),
                enc_uint(inner.nonce),
            ] + tail
        if inner.variant == AgentOperationVariant.REVOKE and isinstance(op, AgentRevoke):
            return TYPE_REVOKE_AGENT, head + [
                enc_string(op.name.encode()),
                enc_uint(inner.nonce),
            ] + tail
        if inner.variant == AgentOperationVariant.REVOKE_ALL:
            return TYPE_REVOKE_ALL_AGENTS, head + [enc_uint(inner.nonce)] + tail
        return None

    if payload.variant == GatedPayloadVariant.CREATE_SUB_ACCOUNT:
        assert isinstance(inner, CreateSubAccount)
        return TYPE_CREATE_SUBACCOUNT, head + [
            enc_string(inner.name.encode()),
            enc_uint(inner.nonce),
        ] + tail

    if payload.variant == GatedPayloadVariant.VAULT:
        name = _VAULT_OPERATION_NAMES.get(inner.variant)
        if name is None:
            return None
        return TYPE_VAULT_OPERATION, head + [
            enc_string(name),
            enc_uint(inner.nonce),
        ] + tail

    return None


def _operation_fields(
    chain_id: int,
    account: AccountAddress,
    authority_epoch: int,
    op: MultisigOp,
    expires_at_secs: int,
    op_id: bytes,
):
    """The primary type and encoded fields an owner signs to approve ``op``.

    ``None`` for the two operations that have no owner-signed document, and that is
    by design rather than by omission: ``Create``'s document names the creator,
    which is the transaction's sender rather than a field of the operation (use
    :func:`create_approval_digest`), and ``RotateKey`` is authorized by the
    account's own key plus the incoming key's challenge, so no owner ever signs one.
    """
    head = _head(chain_id, account, authority_epoch)
    tail = _tail(expires_at_secs, op_id)

    if isinstance(op, MultisigOpInstall):
        return TYPE_INSTALL_POLICY, head + [
            _enc_address_array(op.owners),
            enc_uint(op.threshold),
        ] + tail
    if isinstance(op, MultisigOpUpdatePolicy):
        return TYPE_UPDATE_POLICY, head + [
            _enc_address_array(op.owners),
            enc_uint(op.threshold),
        ] + tail
    if isinstance(op, MultisigOpRemove):
        return TYPE_REMOVE_POLICY, head + [op.new_auth_key] + tail
    if isinstance(op, MultisigOpExecute):
        return _execute_fields(op.payload, head, tail)
    return None


def approval_digest(
    chain_id: int,
    account: AccountAddress,
    authority_epoch: int,
    op: MultisigOp,
    expires_at_secs: int,
    op_id: bytes,
) -> Optional[bytes]:
    """The 32 bytes an owner signs to approve ``op``, or ``None``.

    ``None`` is a refusal, not a fallback: an operation whose fields cannot be shown
    must not be approvable, because the alternative is a partner signing a dialog
    that does not say what the money is doing. It happens for an asset id the table
    cannot name, an address with bytes above the low twenty, an empty batch, and for
    the two operations no owner signs. The chain rejects the same inputs rather than
    accepting a signature over a hash.
    """
    try:
        fields = _operation_fields(
            chain_id, account, authority_epoch, op, expires_at_secs, op_id
        )
    except _NotEvmShaped:
        return None
    if fields is None:
        return None
    type_string, encoded = fields
    return eip712_digest(domain_separator(chain_id), struct_hash(type_string, encoded))


def create_approval_digest(
    chain_id: int,
    account: AccountAddress,
    creator: AccountAddress,
    op: MultisigOpCreate,
    expires_at_secs: int,
    op_id: bytes,
) -> Optional[bytes]:
    """The creator-aware form for ``Create``, whose document names the creator
    instead of an epoch: the account does not exist yet, and creator plus salt are
    what derive its address."""
    try:
        fields = [
            enc_string(intention_chain_name(chain_id)),
            enc_address(account),
            enc_address(creator),
            _enc_address_array(op.owners),
            enc_uint(op.threshold),
        ] + _tail(expires_at_secs, op_id)
    except _NotEvmShaped:
        return None
    return eip712_digest(
        domain_separator(chain_id), struct_hash(TYPE_CREATE_POLICY, fields)
    )


def key_challenge_digest(
    chain_id: int,
    account: AccountAddress,
    authority_epoch: int,
    new_auth_key: bytes,
    op_kind: Union[MultisigOpVariant, int],
) -> Optional[bytes]:
    """What an incoming control key signs to prove it exists.

    ``op_kind`` is the :class:`MultisigOpVariant`: 3 for a ``Remove``, 4 for a
    ``RotateKey``. The challenge is bound to the kind rather than to the operation
    id because the id hashes the whole operation and this proof sits inside it -- a
    challenge bound to the id could never be signed, since producing the signature
    would change the digest it was signed over. Account plus epoch plus kind is
    enough: a challenge cannot move to another account, survive an authority change,
    or be presented for a different kind of handover.
    """
    if len(new_auth_key) != 32:
        raise ValueError(f"a new auth key must be 32 bytes, got {len(new_auth_key)}")
    try:
        fields = _head(chain_id, account, authority_epoch) + [
            bytes(new_auth_key),
            enc_uint(int(op_kind)),
        ]
    except _NotEvmShaped:
        return None
    return eip712_digest(
        domain_separator(chain_id), struct_hash(TYPE_KEY_CHALLENGE, fields)
    )


def key_challenge_bytes(
    chain_id: int,
    account: AccountAddress,
    authority_epoch: int,
    new_auth_key: bytes,
    op_kind: Union[MultisigOpVariant, int],
) -> bytes:
    """The BCS bytes an Ed25519 control key signs, for a key that cannot produce
    EIP-712. Same fields as :func:`key_challenge_digest`, so the two schemes
    authorize exactly the same thing."""
    if len(new_auth_key) != 32:
        raise ValueError(f"a new auth key must be 32 bytes, got {len(new_auth_key)}")
    serializer = Serializer()
    serializer.serialize_u8(chain_id)
    serializer.serialize_u8(MULTISIG_AUTHORIZATION_VERSION)
    account.serialize(serializer)
    serializer.serialize_u64(authority_epoch)
    serializer.serialize_fixed_bytes(bytes(new_auth_key))
    serializer.serialize_u8(int(op_kind))
    return serializer.to_bytes()


def submit_struct_hash(
    chain_id: int,
    account: AccountAddress,
    op: MultisigOp,
    nonce: int,
    txn_digest: bytes,
) -> Optional[bytes]:
    """The struct hash of the submitting owner's envelope.

    The struct hash rather than a full digest: this is the piece the transaction's
    own EIP-712 digest folds in, and it is what the cross-language vectors pin.
    """
    try:
        fields = [
            enc_string(intention_chain_name(chain_id)),
            enc_address(account),
            enc_string(submit_operation_name(op).encode()),
            enc_uint(nonce),
            bytes(txn_digest),
        ]
    except _NotEvmShaped:
        return None
    return struct_hash(TYPE_MULTISIG_SUBMIT, fields)

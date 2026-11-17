# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The bytes a transaction signature covers, and the hash the chain files it under.

Mirrors transactions/signing_message.ts.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Union

from .raw_transaction import RawTransaction, SimpleTransaction, as_raw_transaction

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from .authenticator import AccountAuthenticatorSingleKey

TRANSACTION_SALT = b"INTENTION::Transaction"


def generate_signing_message_for_transaction(
    transaction: Union[SimpleTransaction, RawTransaction]
) -> bytes:
    """SHA3-256 of the domain salt, followed by the BCS of the transaction."""
    return as_raw_transaction(transaction).keyed()


def generate_user_transaction_hash(
    transaction: Union[SimpleTransaction, RawTransaction],
    sender_authenticator: "AccountAuthenticatorSingleKey",
) -> str:
    """The hash the chain will file this transaction under, known before submitting."""
    from .authenticator import generate_signed_transaction

    signed = generate_signed_transaction(transaction, sender_authenticator)
    prefix = hashlib.sha3_256(TRANSACTION_SALT).digest()
    digest = hashlib.sha3_256(prefix + bytes([0]) + signed).hexdigest()
    return f"0x{digest}"

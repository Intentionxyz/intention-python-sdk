# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import hashlib
import struct

from .account_address import AccountAddress

MAIN_SUB_ADDRESS = AccountAddress.from_str("0x0")

_SUBACCOUNT_ADDRESS_LENGTH = 20
_DEX_ACCOUNT_PREFIX = b"dex_account"


def derive_subaccount_address(
    main_address: AccountAddress, number: int
) -> AccountAddress:
    wrapped_number = number & 0xFFFFFFFF
    last20 = main_address.address[-_SUBACCOUNT_ADDRESS_LENGTH:]
    packed_number = struct.pack("<I", wrapped_number)
    hash_bytes = hashlib.sha3_256(
        _DEX_ACCOUNT_PREFIX + last20 + packed_number
    ).digest()
    padding = b"\x00" * (AccountAddress.LENGTH - _SUBACCOUNT_ADDRESS_LENGTH)
    return AccountAddress(padding + hash_bytes[:_SUBACCOUNT_ADDRESS_LENGTH])


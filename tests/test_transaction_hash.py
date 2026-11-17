# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The transaction hash a caller can predict before submitting.

This path had no coverage, which is how a missing `import hashlib` in
SignedTransaction.hash() reached a suite run instead of a test run.
"""

from __future__ import annotations

import unittest

from intention_sdk.core.account import Account, Secp256k1PrivateKey
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.transactions import (
    RawTransaction,
    SignedTransaction,
    TransactionPayload,
    generate_signed_transaction,
    generate_signing_message_for_transaction,
    generate_user_transaction_hash,
)
from intention_sdk.transactions.dex_payloads import (
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexOrderlessTx,
    DexTx,
)
from intention_sdk.types.enums import (
    ConditionType,
    CreatedBy,
    DexOrderlessTxVariant,
    DexOrdersVariant,
    Grouping,
    OrderBasicType,
    OrderPositionMode,
    Side,
    StpMode,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)

PRIVATE_KEY = "0x" + "11" * 32
CHAIN_ID = 2
NONCE = 7


def _signed_transaction():
    private_key = Secp256k1PrivateKey.from_hex(PRIVATE_KEY)
    account = Account.from_private_key(private_key)
    order = DexPlaceOrder(
        sub_address=AccountAddress(b"\x00" * 32),
        symbol_id=7,
        symbol_type=SymbolType.PERPETUAL,
        side=Side.BUY,
        quantums=1000,
        subticks=2000,
        trigger_subticks=0,
        order_basic_type=OrderBasicType.LIMIT,
        time_in_force=TimeInForce.GTC,
        condition_type=ConditionType.UNSPECIFIED,
        trigger_price_type=TriggerPriceType.LAST_PRICE,
        target_order_id=0,
        reduce_only=False,
        position_mode=OrderPositionMode.NET,
        slippage_tolerance_ppm=100_000,
        client_order_id=None,
        stp_mode=StpMode.EXPIRE_MAKER,
    )
    payload = TransactionPayload(
        DexOrderlessTx(
            DexOrderlessTxVariant.DEX,
            DexTx(
                NONCE,
                DexOrders(
                    DexOrdersVariant.PLACE,
                    [DexPlaceOrders([order], Grouping.NA)],
                ),
                CreatedBy.USER,
                None,
            ),
        )
    )
    raw = RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=200_000,
        gas_unit_price=100,
        expiration_timestamp_secs=1_800_000_000,
        chain_id=CHAIN_ID,
    )
    authenticator = account.sign_transaction_with_authenticator(raw)
    return raw, authenticator, SignedTransaction(raw, authenticator)


class TransactionHash(unittest.TestCase):
    def test_hash_is_hex_and_stable(self) -> None:
        _, _, signed = _signed_transaction()
        first = signed.hash()
        self.assertTrue(first.startswith("0x"))
        self.assertEqual(len(first), 66)
        self.assertEqual(first, signed.hash())

    def test_predicted_hash_matches_the_signed_transaction(self) -> None:
        """What generate_user_transaction_hash promises before submitting is
        what the signed transaction hashes to."""
        raw, authenticator, signed = _signed_transaction()
        self.assertEqual(
            generate_user_transaction_hash(raw, authenticator), signed.hash()
        )

    def test_signed_bytes_round_trip(self) -> None:
        """Decoding and re-encoding reproduces the bytes exactly.

        Compared as bytes, not as objects: the payload types below
        TransactionPayload do not define __eq__, so object equality would be
        identity and would pass for the wrong reason.
        """
        raw, authenticator, signed = _signed_transaction()
        encoded = generate_signed_transaction(raw, authenticator)
        self.assertEqual(encoded, signed.bcs_to_bytes())
        decoded = SignedTransaction.deserialize(_reader(encoded))
        self.assertEqual(decoded.bcs_to_bytes(), encoded)
        self.assertEqual(decoded.hash(), signed.hash())

    def test_signature_covers_the_signing_message(self) -> None:
        raw, authenticator, _ = _signed_transaction()
        self.assertTrue(
            authenticator.verify(generate_signing_message_for_transaction(raw))
        )


def _reader(data: bytes):
    from intention_sdk.bcs import Deserializer

    return Deserializer(data)


if __name__ == "__main__":
    unittest.main()

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""A whole signed transaction, byte for byte, against the pre-rewrite SDK.

test_bcs_golden pins the primitives. This pins everything above them at once:
the nested DEX payload, the RawTransaction wrapper, the EIP-712 digest, the
deterministic ECDSA signature with its low-s normalisation, the authenticator
the chain reads, and the hash the caller predicts.

signed_transaction_golden.json was produced by the SDK as it stood before the
rewrite, with a fixed key, nonce and expiry so the bytes are reproducible. A
signature over different bytes is a signature the chain rejects, and nothing
about it looks wrong until it is submitted.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from intention_sdk.core.account import Account, Secp256k1PrivateKey
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.transactions import (
    RawTransaction,
    SignedTransaction,
    TransactionPayload,
)
from intention_sdk.transactions.dex_payloads import (
    DexOrderlessTx,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
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

GOLDEN = json.loads(
    (Path(__file__).parent / "signed_transaction_golden.json").read_text(encoding="utf-8")
)

PRIVATE_KEY = "0x" + "11" * 32
NONCE = 42
MAX_GAS = 200_000
GAS_PRICE = 100
EXPIRATION = 1_800_000_000
CHAIN_ID = 2

CASES = {
    "limit_gtc": (Side.BUY, TimeInForce.GTC, OrderBasicType.LIMIT, None),
    "market_ioc": (Side.SELL, TimeInForce.IOC, OrderBasicType.MARKET, None),
    "limit_with_cid": (Side.BUY, TimeInForce.GTC, OrderBasicType.LIMIT, "0x" + "ab" * 16),
}


def _account() -> Account:
    return Account.from_private_key(Secp256k1PrivateKey.from_hex(PRIVATE_KEY))


def _raw_transaction(case: str) -> RawTransaction:
    side, time_in_force, basic_type, client_order_id = CASES[case]
    order = DexPlaceOrder(
        sub_address=AccountAddress(b"\x00" * 32),
        symbol_id=7,
        symbol_type=SymbolType.PERPETUAL,
        side=side,
        quantums=123456,
        subticks=2_000_000,
        trigger_subticks=0,
        order_basic_type=basic_type,
        time_in_force=time_in_force,
        condition_type=ConditionType.UNSPECIFIED,
        trigger_price_type=TriggerPriceType.LAST_PRICE,
        target_order_id=0,
        reduce_only=False,
        position_mode=OrderPositionMode.NET,
        slippage_tolerance_ppm=100_000,
        client_order_id=client_order_id,
        stp_mode=StpMode.EXPIRE_MAKER,
    )
    payload = TransactionPayload(
        DexOrderlessTx(
            DexOrderlessTxVariant.DEX,
            DexTx(
                NONCE,
                DexOrders(
                    DexOrdersVariant.PLACE, [DexPlaceOrders([order], Grouping.NA)]
                ),
                CreatedBy.USER,
                None,
            ),
        )
    )
    return RawTransaction.create_orderless(
        sender=_account().account_address,
        payload=payload,
        max_gas_amount=MAX_GAS,
        gas_unit_price=GAS_PRICE,
        expiration_timestamp_secs=EXPIRATION,
        chain_id=CHAIN_ID,
    )


class SignedTransactionGolden(unittest.TestCase):
    def test_account_derivation(self) -> None:
        account = _account()
        self.assertEqual(str(account.account_address), GOLDEN["address"])
        self.assertEqual(account.public_key().hex(), GOLDEN["public_key"])

    def test_unsigned_bytes(self) -> None:
        for case in CASES:
            with self.subTest(case=case):
                self.assertEqual(
                    _raw_transaction(case).bcs_to_bytes().hex(),
                    GOLDEN[case]["raw_bcs"],
                )

    def test_signing_message(self) -> None:
        """What the signature covers: the salt prefix followed by the transaction."""
        for case in CASES:
            with self.subTest(case=case):
                self.assertEqual(
                    _raw_transaction(case).keyed().hex(),
                    GOLDEN[case]["signing_message"],
                )

    def test_signed_bytes(self) -> None:
        """Including the signature itself, so the digest, the deterministic
        nonce and the low-s normalisation are all pinned."""
        account = _account()
        for case in CASES:
            with self.subTest(case=case):
                raw = _raw_transaction(case)
                signed = SignedTransaction(
                    raw, account.sign_transaction_with_authenticator(raw)
                )
                self.assertEqual(signed.bytes().hex(), GOLDEN[case]["signed_bcs"])

    def test_transaction_hash(self) -> None:
        account = _account()
        for case in CASES:
            with self.subTest(case=case):
                raw = _raw_transaction(case)
                signed = SignedTransaction(
                    raw, account.sign_transaction_with_authenticator(raw)
                )
                self.assertEqual(signed.hash(), GOLDEN[case]["hash"])


if __name__ == "__main__":
    unittest.main()

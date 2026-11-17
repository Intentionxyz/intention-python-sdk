# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""The two DexOrders variants the taker delay introduced.

``REPLACE_MAKER_ONLY`` is an amend whose replacement is rejected rather than
filled if it would cross the book, and ``NOOP`` carries no orders at all: it
cancels a same-nonce order that has not reached a block yet, by consuming the
nonce that order needs.

Both are asserted on the bytes and on the JSON submit shape, because the node
reads the first and the REST submit path reads the second. A variant that only
half exists is worse than one that does not: the transaction signs, and then
fails to deserialise.
"""

import unittest

from intention_sdk.core.account import Account, Secp256k1PrivateKey
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.bcs import Deserializer, Serializer
from intention_sdk.transactions.dex_payloads import (
    DexOrderlessTx,
    DexOrders,
    DexReplaceOrder,
    DexTx,
)
from intention_sdk.types.enums import (
    CreatedBy,
    DexOrderlessTxVariant,
    DexOrdersVariant,
    SymbolType,
)
from intention_sdk.transactions.json_submit import generate_submit_transaction_request
from intention_sdk.transactions import RawTransaction, TransactionPayload

_PRIVATE_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"
_NEW_CLIENT_ORDER_ID = "0xfedcba9876543210fedcba9876543210"


def _replace_order() -> DexReplaceOrder:
    return DexReplaceOrder.by_order_id(
        AccountAddress(bytes(32)),
        91,
        symbol_id=7,
        symbol_type=SymbolType.PERPETUAL,
        quantums=3000,
        subticks=4000,
        new_client_order_id=_NEW_CLIENT_ORDER_ID,
    )


def _encode(orders: DexOrders) -> bytes:
    serializer = Serializer()
    orders.serialize(serializer)
    return serializer.to_bytes()


def _canonical_account() -> Account:
    private_key = Secp256k1PrivateKey.from_hex(_PRIVATE_KEY)
    address = AccountAddress(private_key.public_key().to_evm_account_bytes())
    return Account(address, private_key)


def _submit_request(nonce: int, orders: DexOrders):
    account = _canonical_account()
    payload = TransactionPayload(
        DexOrderlessTx(DexOrderlessTxVariant.DEX, DexTx(nonce, orders, CreatedBy.USER))
    )
    raw_tx = RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=200000,
        gas_unit_price=100,
        expiration_timestamp_secs=9999999999,
        chain_id=4,
    )
    return generate_submit_transaction_request(raw_tx, account.sign_transaction_with_authenticator(raw_tx))


class TestNoop(unittest.TestCase):
    def test_encodes_as_nothing_but_its_tag(self):
        # A noop is the one variant with nothing after its tag. Writing an empty
        # vector instead -- what every other variant does when given no orders --
        # appends a trailing zero byte, and the node cannot deserialise the
        # transaction.
        self.assertEqual(_encode(DexOrders.noop()), bytes([5]))

    def test_round_trips_without_reading_a_length(self):
        decoded = DexOrders.deserialize(Deserializer(bytes([5])))
        self.assertEqual(decoded.variant, DexOrdersVariant.NOOP)
        self.assertEqual(decoded.orders, [])

    def test_carries_the_orders_nonce_as_both_the_protector_and_the_payload_nonce(self):
        # The nonce appears twice in a DEX transaction, and an in-flight cancel
        # only works when both copies are the cancelled order's nonce. That pair
        # is what a hand-built noop gets wrong.
        request = _submit_request(4242, DexOrders.noop())
        self.assertEqual(request["replay_protection_nonce"], "4242")
        self.assertEqual(request["payload"]["nonce"], "4242")

    def test_json_payload_has_no_orders_field(self):
        payload = _submit_request(1234, DexOrders.noop())["payload"]
        self.assertEqual(payload["operation"], "noop")
        self.assertEqual(payload["dex_type"], "dex_payload")
        # The node's noop payload type declares no orders field, so rendering one
        # -- even an empty one -- submits a shape it never described.
        self.assertNotIn("orders", payload)


class TestMakerOnlyReplace(unittest.TestCase):
    def test_differs_from_a_replace_in_its_tag_alone(self):
        # The tag is the entire difference, and it is what tells the node to hold
        # the replacement to maker-only entry rules -- and to pack it without the
        # taker delay.
        replace = _encode(DexOrders(DexOrdersVariant.REPLACE, [_replace_order()]))
        maker_only = _encode(DexOrders.replace_maker_only([_replace_order()]))

        self.assertEqual(replace[0], 2)
        self.assertEqual(maker_only[0], 4)
        self.assertEqual(maker_only[1:], replace[1:])

    def test_round_trips_as_replace_orders(self):
        encoded = _encode(DexOrders.replace_maker_only([_replace_order()]))
        decoded = DexOrders.deserialize(Deserializer(encoded))
        self.assertEqual(decoded.variant, DexOrdersVariant.REPLACE_MAKER_ONLY)
        self.assertEqual(_encode(decoded), encoded)

    def test_json_payload_uses_the_replace_maker_only_operation(self):
        payload = _submit_request(
            1234, DexOrders.replace_maker_only([_replace_order()])
        )["payload"]
        self.assertEqual(payload["operation"], "replace_maker_only")
        self.assertEqual(len(payload["orders"]), 1)


if __name__ == "__main__":
    unittest.main()

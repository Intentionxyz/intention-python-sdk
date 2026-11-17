# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cross-implementation vectors for wallet-signed typed data.

The digests below were produced independently by the chain,
by `viem`, and by `@metamask/eth-sig-util` --
the library MetaMask itself hashes with -- for the same transactions. All four
implementations have to agree byte for byte, because the chain rebuilds the typed
data from the payload and rejects anything that does not match.

If one of these fails, this SDK signs something the chain will not accept. Do not
update the expected value to whatever this code now produces: find out which side
moved.
"""

import unittest

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.transactions.dex_payloads import (
    AccountTransferItem,
    AgentApprove,
    DexAgentTx,
    DexOrderlessTx,
    DexTransferTx,
)
from intention_sdk.types.enums import (
    AccountType,
    AgentOperationVariant,
    DexOrderlessTxVariant,
    DexTransferVariant,
)
from intention_sdk.transactions.typed_data import domain_separator, format_amount, typed_data_digest
from intention_sdk.core.account import Account, Secp256k1PrivateKey as PrivateKey
from intention_sdk.transactions import RawTransaction, TransactionPayload

TESTNET = 2


def _addr(hex20: str) -> AccountAddress:
    return AccountAddress(bytes(12) + bytes.fromhex(hex20.removeprefix("0x")))


def _raw(variant, inner) -> RawTransaction:
    return RawTransaction(
        sender=_addr("0x001ebbde289635ae8ad2f2ec1080af75e00705f9"),
        sequence_number=0,
        payload=TransactionPayload(DexOrderlessTx(variant, inner)),
        max_gas_amount=100000,
        gas_unit_price=100,
        expiration_timestamp_secs=1800000000,
        chain_id=TESTNET,
    )


def _approve() -> RawTransaction:
    return _raw(
        DexOrderlessTxVariant.DEX_AGENT,
        DexAgentTx(
            1788507274398,
            AgentOperationVariant.APPROVE,
            AgentApprove(
                "coid-test", _addr("0x0011bbcc289635ae8ad2f2ec1080af75e009adbb"), 1790000000
            ),
        ),
    )


def _send_asset(amount: int = 10000000, asset_id: int = 0) -> RawTransaction:
    return _raw(
        DexOrderlessTxVariant.DEX_TRANSFER,
        DexTransferTx(
            2,
            DexTransferVariant.ACCOUNT_TRANSFER,
            [
                AccountTransferItem(
                    _addr("0x001ebbde289635ae8ad2f2ec1080af75e00705f9"),
                    asset_id,
                    amount,
                    AccountType.PERP,
                )
            ],
        ),
    )


def _send_asset_batch() -> RawTransaction:
    """Two transfers in one transaction, which reaches the batch type."""
    return _raw(
        DexOrderlessTxVariant.DEX_TRANSFER,
        DexTransferTx(
            7,
            DexTransferVariant.ACCOUNT_TRANSFER,
            [
                AccountTransferItem(
                    _addr("0x001ebbde289635ae8ad2f2ec1080af75e00705f9"),
                    0,
                    1000000,
                    AccountType.PERP,
                ),
                AccountTransferItem(
                    _addr("0x0011bbcc289635ae8ad2f2ec1080af75e009adbb"),
                    0,
                    2000000,
                    AccountType.PERP,
                ),
            ],
        ),
    )


class TestEip712TypedData(unittest.TestCase):
    def test_an_unknown_asset_falls_back_to_the_opaque_wrapper(self):
        """An asset the table cannot name falls back rather than inventing a
        name or a scale. A dialog reading "USDC" for something that is not USDC
        is worse than one reading a hash."""
        self.assertIsNotNone(typed_data_digest(_send_asset(asset_id=0)))
        self.assertIsNone(typed_data_digest(_send_asset(asset_id=99)))

    def test_amounts_render_as_scaled_decimal_strings(self):
        """The wallet shows what a person would say out loud: no padding, no
        trailing zeros. Every implementation hashes this string, so drift here
        is a silent fork."""
        for quantums, expected in [
            (0, "0"),
            (1, "0.000001"),
            (999_999, "0.999999"),
            (1_000_000, "1"),
            (10_000_000, "10"),
            (10_500_000, "10.5"),
            (10_000_001, "10.000001"),
            (2**64 - 1, "18446744073709.551615"),
        ]:
            self.assertEqual(format_amount(quantums, 6), expected, f"quantums={quantums}")

    def test_domain_separator_matches_the_other_implementations(self):
        self.assertEqual(
            domain_separator(TESTNET).hex(),
            "336363b4cfef512fb47e8f066a6a6458a002683e1ce4d10aabadd35b6ba43d93",
        )

    def test_approve_agent_digest_matches_the_other_implementations(self):
        self.assertEqual(
            typed_data_digest(_approve()).hex(),
            "6a199c496e821f262cddb86a0b387a57ba0997faab51dfe3ae2cff0621382210",
        )

    def test_send_asset_digest_matches_the_other_implementations(self):
        self.assertEqual(
            typed_data_digest(_send_asset()).hex(),
            "b1102a5c0010514ae64d6ea0e7d832e190adf70f3049fed465bfdfa32f144d18",
        )

    def test_batch_digest_matches_the_other_implementations(self):
        """The struct-array encoding the flat types never exercise.

        This is where an implementation is most likely to drift: the array hashes
        each element's struct hash and then hashes the concatenation, and the batch
        type string has to carry the referenced struct's own definition appended to
        it. Getting either wrong still yields 32 plausible bytes.
        """
        self.assertEqual(
            typed_data_digest(_send_asset_batch()).hex(),
            "0c5537f6d410df7c15b97a154a63db567f3aabfaa76021fc21284ce11ac70142",
        )

    def test_a_batch_reaches_a_different_type_than_a_single_transfer(self):
        self.assertNotEqual(
            typed_data_digest(_send_asset_batch()),
            typed_data_digest(_send_asset()),
        )

    def test_a_wallet_signed_transfer_round_trips(self):
        key = PrivateKey.generate()
        txn = _send_asset()
        auth = Account.from_private_key(key).sign_transaction_with_authenticator(txn)
        # Unwrap: AccountAuthenticatorSingleKey -> AnySignature -> the signature.
        signature = auth.signature.signature
        self.assertTrue(
            key.public_key().verify_digest(typed_data_digest(txn), signature)
        )

    def test_changing_the_amount_changes_what_was_signed(self):
        """The amount the wallet displayed is the amount that executes."""
        self.assertNotEqual(
            typed_data_digest(_send_asset(10000000)),
            typed_data_digest(_send_asset(999999999)),
        )

    def test_payloads_no_wallet_signs_keep_the_opaque_wrapper(self):
        """Orders are signed by an agent key; there is no dialog to render."""
        from intention_sdk.transactions.dex_payloads import DexUserConfigTx, SetUserLeverage

        leverage = _raw(
            DexOrderlessTxVariant.DEX_USER_CONFIG,
            DexUserConfigTx(0, SetUserLeverage(1, AccountAddress(bytes(32)), [], None)),
        )
        self.assertIsNone(typed_data_digest(leverage))


if __name__ == "__main__":
    unittest.main()

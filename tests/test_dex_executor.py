# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import unittest

from intention_sdk.core.account import Account
from intention_sdk.transactions.account_client import AccountIntents
from intention_sdk.api.client import ApiError, ClientConfig
from intention_sdk.bcs import MAX_U64
from intention_sdk.api.dex_executor import (
    DexTransactionExecutor,
    SubmitOptions,
    TransactionExecutionError,
    TransactionTimeoutError,
)


class FakeRestClient:
    def __init__(self, transactions):
        self.transactions = list(transactions)
        self.client_config = ClientConfig()
        self.submitted = []

    async def chain_id(self):
        return 42

    async def submit_transaction(self, raw, authenticator, encoding=None):
        self.submitted.append((raw, authenticator, encoding))
        return "0xsubmitted"

    async def transaction_by_hash(self, _txn_hash):
        if not self.transactions:
            raise ApiError("not found", 404)
        value = self.transactions.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class TestDexTransactionExecutor(unittest.IsolatedAsyncioTestCase):
    async def test_cross_transfer_uses_independent_replay_nonce(self):
        rest = FakeRestClient([])
        signer = Account.generate()
        executor = DexTransactionExecutor(rest, signer)
        business_nonce = 17
        replay_nonce = 9_001
        orderless = AccountIntents().bridge_withdraw(
            [
                {
                    "destination": Account.generate().account_address,
                    "amount_atomic": 1_000_000,
                }
            ],
            nonce=business_nonce,
        )

        result = await executor.submit_orderless(
            orderless,
            options=SubmitOptions(replay_protection_nonce=replay_nonce),
        )

        self.assertEqual(result.hash, "0xsubmitted")
        raw = rest.submitted[0][0]
        self.assertEqual(raw.sequence_number, replay_nonce)
        self.assertEqual(orderless.inner.nonce, business_nonce)

    async def test_cross_transfer_generates_replay_nonce_for_user_withdrawal(self):
        rest = FakeRestClient([])
        signer = Account.generate()
        executor = DexTransactionExecutor(rest, signer)
        orderless = AccountIntents().bridge_withdraw(
            [
                {
                    "destination": Account.generate().account_address,
                    "amount_atomic": 1_000_000,
                }
            ],
            nonce=18,
        )

        await executor.submit_orderless(orderless)

        replay_nonce = rest.submitted[0][0].sequence_number
        self.assertGreaterEqual(replay_nonce, 0)
        self.assertLess(replay_nonce, MAX_U64)

    async def test_wait_returns_committed_transaction(self):
        executor = DexTransactionExecutor(
            FakeRestClient(
                [
                    {"type": "pending_transaction"},
                    {"type": "user_transaction", "success": True},
                ]
            ),
            Account.generate(),
        )
        result = await executor.wait_for_transaction(
            "0xabc", timeout_secs=1, poll_interval_secs=0.001
        )
        self.assertTrue(result["success"])

    async def test_vm_failure_raises_typed_error(self):
        transaction = {
            "type": "user_transaction",
            "success": False,
            "vm_status": "Move abort",
        }
        executor = DexTransactionExecutor(
            FakeRestClient([transaction]),
            Account.generate(),
        )
        with self.assertRaises(TransactionExecutionError) as raised:
            await executor.wait_for_transaction("0xfailed")
        self.assertEqual(raised.exception.transaction, transaction)

    async def test_timeout_raises_typed_error(self):
        executor = DexTransactionExecutor(
            FakeRestClient([]), Account.generate()
        )
        with self.assertRaises(TransactionTimeoutError):
            await executor.wait_for_transaction(
                "0xslow",
                timeout_secs=0.005,
                poll_interval_secs=0.001,
            )


if __name__ == "__main__":
    unittest.main()

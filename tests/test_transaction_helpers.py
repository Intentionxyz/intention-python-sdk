# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import inspect
import unittest

from intention_sdk.transactions.dex_payloads import leverage_to_im_leverage

from intention_sdk.transactions.transaction_builder import (
    IntentionClientConfig,
    LedgerInfo,
    build_transaction,
    generate_signed_transaction,
    generate_signing_message_for_transaction,
    generate_user_transaction_hash,
    get_ledger_info,
    submit_transaction,
    wait_for_transaction,
)


class TestTransactionHelpers(unittest.TestCase):
    def test_the_helpers_are_importable(self):
        functions = [
            build_transaction,
            generate_signing_message_for_transaction,
            generate_user_transaction_hash,
            generate_signed_transaction,
            submit_transaction,
            get_ledger_info,
            wait_for_transaction,
        ]
        for fn in functions:
            self.assertTrue(callable(fn), f"{fn.__name__} is not callable")

    def test_sync_functions_callable(self):
        sync_fns = [
            generate_signing_message_for_transaction,
            generate_user_transaction_hash,
            generate_signed_transaction,
        ]
        for fn in sync_fns:
            self.assertTrue(callable(fn))
            self.assertFalse(
                inspect.iscoroutinefunction(fn),
                f"{fn.__name__} should be sync",
            )

    def test_async_functions_are_coroutines(self):
        async_fns = [
            build_transaction,
            submit_transaction,
            get_ledger_info,
            wait_for_transaction,
        ]
        for fn in async_fns:
            self.assertTrue(
                inspect.iscoroutinefunction(fn),
                f"{fn.__name__} should be async",
            )

    def test_type_aliases_exist(self):
        self.assertIsNotNone(IntentionClientConfig)
        self.assertIsNotNone(LedgerInfo)

    def test_leverage_to_im_leverage_rounds_up(self):
        self.assertEqual(leverage_to_im_leverage(3.0), 3334)

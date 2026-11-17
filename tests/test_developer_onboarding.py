# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Developer onboarding verification - proves a fresh developer can use the SDK."""

import unittest


class TestDeveloperOnboarding(unittest.TestCase):
    def test_basic_import(self):
        from intention_sdk import Intention, IntentionConfig, Network

        self.assertIsNotNone(Intention)
        self.assertIsNotNone(IntentionConfig)
        self.assertIsNotNone(Network)

    def test_create_account(self):
        from intention_sdk import Account

        account = Account.generate()
        self.assertIsNotNone(account.address())

    def test_create_config_and_client(self):
        from intention_sdk import Intention, IntentionConfig, Network

        config = IntentionConfig(
            network=Network.DEVNET,
            fullnode="http://127.0.0.1:8080/v1",
        )
        intention = Intention(config)
        self.assertIsNotNone(intention.config)
        self.assertEqual(
            intention.config.get_fullnode_url(), "http://127.0.0.1:8080/v1"
        )

    def test_import_dex_types(self):
        from intention_sdk import (
            DexPlaceOrder,
            OrderBasicType,
            Side,
            TimeInForce,
        )

        self.assertIsNotNone(Side.BUY)
        self.assertIsNotNone(DexPlaceOrder)
        self.assertIsNotNone(OrderBasicType)
        self.assertIsNotNone(TimeInForce)

    def test_import_vault_types(self):
        from intention_sdk import VaultClient, VaultState

        self.assertIsNotNone(VaultClient)
        self.assertIsNotNone(VaultState)

    def test_import_transaction_helpers(self):
        from intention_sdk import (
            build_transaction,
            generate_signing_message_for_transaction,
            submit_transaction,
        )

        self.assertTrue(callable(build_transaction))
        self.assertTrue(callable(generate_signing_message_for_transaction))
        self.assertTrue(callable(submit_transaction))

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

import unittest

from intention_sdk.api.intention import (
    AccountAddressInput,
    BuildHelper,
    Intention,
    IntentionConfig,
    Network,
    SubmitHelper,
    TransactionHelper,
    intention_config,
)


class TestIntentionClient(unittest.TestCase):
    def test_network_enum(self):
        self.assertEqual(Network.MAINNET, "mainnet")
        self.assertEqual(Network.TESTNET, "testnet")
        self.assertEqual(Network.DEVNET, "devnet")
        self.assertEqual(Network.LOCAL, "local")
        self.assertEqual(Network.CUSTOM, "custom")
        self.assertEqual(len(Network), 5)

    def test_intention_config_constructor(self):
        config = IntentionConfig(
            node_url="http://localhost:8080/v1",
            relayer_url="http://localhost:3000",
            ws_url="ws://localhost:3000/ws",
            fullnode="http://localhost:8080/v1",
            faucet="http://localhost:8081",
        )
        self.assertEqual(config.get_fullnode_url(), "http://localhost:8080/v1")
        self.assertEqual(config.node_url, "http://localhost:8080/v1")
        self.assertEqual(config.relayer_url, "http://localhost:3000")
        self.assertEqual(config.ws_url, "ws://localhost:3000/ws")
        self.assertEqual(config.faucet, "http://localhost:8081")
        self.assertEqual(config.indexer, "")

    def test_intention_config_defaults(self):
        config = IntentionConfig(network=Network.DEVNET)
        self.assertEqual(config.network, Network.DEVNET)
        self.assertEqual(config.get_fullnode_url(), "")

    def test_intention_has_all_23_methods(self):
        config = IntentionConfig(fullnode="http://x:8080/v1")
        intention = Intention(config)
        expected_methods = [
            "get_ledger_info",
            "wait_for_transaction",
            "fund_account",
            "get_block_by_height",
            "get_block_by_version",
            "view",
            "get_name",
            "get_account_owned_objects",
            "get_digital_asset_activity",
            "query_indexer",
            "get_transaction_by_hash",
            "get_account_info",
            "transfer_fungible_asset",
            "get_transactions",
            "get_account_transactions",
            "get_account_transaction_summaries",
            "get_transaction_by_version",
            "get_account",
            "get_account_resources",
            "get_account_resource",
            "get_account_modules",
            "get_account_module",
            "get_table_item",
        ]
        for method_name in expected_methods:
            self.assertTrue(
                hasattr(intention, method_name),
                f"Missing method: {method_name}",
            )
        self.assertEqual(len(expected_methods), 23)

    def test_transaction_helper_structure(self):
        config = IntentionConfig(fullnode="http://x:8080/v1")
        intention = Intention(config)

        self.assertIsInstance(intention.transaction, TransactionHelper)
        self.assertTrue(hasattr(intention.transaction, "sign"))
        self.assertTrue(callable(intention.transaction.sign))

        self.assertIsInstance(intention.transaction.build, BuildHelper)
        self.assertTrue(hasattr(intention.transaction.build, "simple"))

        self.assertIsInstance(intention.transaction.submit, SubmitHelper)
        self.assertTrue(hasattr(intention.transaction.submit, "simple"))

    def test_intention_config_alias(self):
        self.assertIs(intention_config, IntentionConfig)

    def test_account_address_input_is_union(self):
        import typing

        origin = getattr(AccountAddressInput, "__origin__", None)
        self.assertIs(origin, typing.Union)

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Differential tests for JSON transaction submission rendering.

Each test builds a transaction identical to the reference TypeScript SDK and
asserts the rendered ``SubmitTransactionRequestJson`` matches a golden fixture
generated from that SDK. Because Python
and the TS SDK both sign deterministically (EIP-712 / RFC6979 + lowS), the
entire request - including the signature - is expected to match byte-for-byte.
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest import mock

from intention_sdk.core.account import Secp256k1PrivateKey
from intention_sdk.core.account import Account
from intention_sdk.core.account_address import AccountAddress
from intention_sdk.api.client import (
    MIME_BCS_SIGNED_TRANSACTION,
    MIME_JSON,
    ClientConfig,
    build_submission_body,
)
from intention_sdk.bcs import MAX_U64, Deserializer, Serializer
from intention_sdk.transactions.multisig_payloads import (
    DexMultisigTx,
    GatedPayload,
    KeyProofEd25519,
    KeyProofSecp256k1,
    MultisigOpCreate,
    MultisigOpExecute,
    MultisigOpInstall,
    MultisigOpRemove,
    MultisigOpRotateKey,
    MultisigOpUpdatePolicy,
    MultisigProof,
)
from intention_sdk.types.enums import GatedPayloadVariant
from intention_sdk.transactions.dex_payloads import (
    AccountTransferItem,
    AdjustIsolatedMargin,
    AgentApprove,
    AgentRevoke,
    BridgeProof,
    BridgeSignature,
    ChangeMarginMode,
    ChangePositionMode,
    CreateSubAccount,
    CrossTransferItem,
    DexAgentTx,
    DexCancelOrder,
    DexConditionReplaceOrder,
    DexOrderlessTx,
    RawOrderlessInner,
    DexOrders,
    DexPlaceOrder,
    DexPlaceOrders,
    DexReplaceOrder,
    DexTransferTx,
    DexTx,
    DexUserConfigTx,
    InternalTransferItem,
    ModifySubAccount,
    SetUserLeverage,
    SymbolMarginMode,
    UserSymbolLeverage,
)
from intention_sdk.types.enums import (
    AccountType,
    AgentOperationVariant,
    ConditionType,
    CreatedBy,
    CrossTransferOption,
    DexOrderlessTxVariant,
    DexOrdersVariant,
    DexTransferVariant,
    DexUserConfigTxVariant,
    Grouping,
    MarginMode,
    OrderBasicType,
    OrderPositionMode,
    Side,
    StpMode,
    SymbolType,
    TimeInForce,
    TriggerPriceType,
)
from intention_sdk.transactions.json_submit import (
    UnsupportedJsonPayloadError,
    generate_submit_transaction_request,
)
from intention_sdk.transactions import (
    RawTransaction,
    SignedTransaction,
    TransactionPayload,
)
from intention_sdk.transactions.vault_payloads import (
    VaultClpBatchCreateManagedAccountsTx,
    VaultClpConfigTx,
    VaultClpManagedAccountTx,
    VaultClpTraderAllowlistUpdateTx,
    VaultCreateTx,
    VaultDepositTx,
    VaultDistributeTx,
    VaultSetParamsTx,
    VaultSetStatusTx,
    VaultTx,
    VaultWithdrawTx,
)
from intention_sdk.types.vault import (
    ClpTraderAllowlistAction,
    ClpTraderAllowlistEntry,
    ManagedAccountAction,
    SubaccountId,
    SymbolAccountsEntry,
    VaultStatus,
    VaultTxVariant,
)

_PRIVATE_KEY = "0x1111111111111111111111111111111111111111111111111111111111111111"
_CLIENT_ORDER_ID = "0x0123456789abcdef0123456789abcdef"
_NEW_CLIENT_ORDER_ID = "0xfedcba9876543210fedcba9876543210"
_TARGET_ORDER_ID = 42
_AGENT_NAME = "review-agent"
_AGENT_ADDRESS = AccountAddress.from_str("0x" + "22" * 32)
_AGENT_EXPIRY = 9999999999
_SUBACCOUNT_ADDRESS = AccountAddress.from_str("0x" + "33" * 32)
_MASTER_ADDRESS = AccountAddress.from_str("0x" + "44" * 32)
_VAULT_SUB = SubaccountId(b"\xab" * 32, 3, b"\xcd" * 32)
_VAULT_TRADER = AccountAddress.from_str("0x" + "99" * 32)
_SPOT_TICKER = b"BTC-USDC".ljust(32, b"\x00")
_MAX_NOTIONAL = bytes([0x40, 0x42, 0x0F]) + b"\x00" * 13
_ADMIN_ADDRESS = AccountAddress.from_str("0x" + "aa" * 32)
_NONCE = 123456789
_CROSS_TRANSFER_REPLAY_NONCE = 9001
_MAX_GAS = 200000
_GAS_PRICE = 100
_EXPIRATION = 9999999999
_CHAIN_ID = 4

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "testdata", "json_submit")


def _load_fixture(name: str) -> dict:
    with open(os.path.join(_FIXTURE_DIR, f"{name}.json")) as handle:
        return json.load(handle)


def _canonical_account() -> Account:
    private_key = Secp256k1PrivateKey.from_hex(_PRIVATE_KEY)
    address = AccountAddress(private_key.public_key().to_evm_account_bytes())
    return Account(address, private_key)


def _build_place(*, side, basic_type, time_in_force, client_order_id):
    account = _canonical_account()
    order = DexPlaceOrder(
        sub_address=AccountAddress(b"\x00" * 32),
        symbol_id=7,
        symbol_type=SymbolType.PERPETUAL,
        side=side,
        quantums=1000,
        subticks=2000,
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
    dex_tx = DexTx(
        _NONCE,
        DexOrders(DexOrdersVariant.PLACE, [DexPlaceOrders([order], Grouping.NA)]),
        CreatedBy.USER,
    )
    payload = TransactionPayload(DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx))
    raw_tx = RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=_MAX_GAS,
        gas_unit_price=_GAS_PRICE,
        expiration_timestamp_secs=_EXPIRATION,
        chain_id=_CHAIN_ID,
    )
    authenticator = account.sign_transaction_with_authenticator(raw_tx)
    return raw_tx, authenticator


def _build_place_order(
    *,
    side=Side.BUY,
    symbol_id=7,
    basic_type=OrderBasicType.LIMIT,
    time_in_force=TimeInForce.GTC,
    client_order_id=None,
    quantums=1000,
    subticks=2000,
):
    return DexPlaceOrder(
        sub_address=AccountAddress(b"\x00" * 32),
        symbol_id=symbol_id,
        symbol_type=SymbolType.PERPETUAL,
        side=side,
        quantums=quantums,
        subticks=subticks,
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


def _build_place_from_groups(groups):
    account = _canonical_account()
    dex_tx = DexTx(
        _NONCE,
        DexOrders(DexOrdersVariant.PLACE, groups),
        CreatedBy.USER,
    )
    payload = TransactionPayload(DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx))
    raw_tx = RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=_MAX_GAS,
        gas_unit_price=_GAS_PRICE,
        expiration_timestamp_secs=_EXPIRATION,
        chain_id=_CHAIN_ID,
    )
    authenticator = account.sign_transaction_with_authenticator(raw_tx)
    return raw_tx, authenticator


def _build_dex_orders(variant, orders):
    account = _canonical_account()
    dex_tx = DexTx(_NONCE, DexOrders(variant, orders), CreatedBy.USER)
    payload = TransactionPayload(DexOrderlessTx(DexOrderlessTxVariant.DEX, dex_tx))
    raw_tx = RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=_MAX_GAS,
        gas_unit_price=_GAS_PRICE,
        expiration_timestamp_secs=_EXPIRATION,
        chain_id=_CHAIN_ID,
    )
    authenticator = account.sign_transaction_with_authenticator(raw_tx)
    return raw_tx, authenticator


def _build_unsupported_payload_tx():
    """A payload the JSON renderer has no shape for, so the fallback can be tested.

    DexOrderlessTx carries a raw inner blob here: the renderer dispatches on the
    variant and reaches its "unknown orderless payload" branch, which is the
    only way left to produce an unsupported payload now that Move entry
    functions are gone.
    """
    account = _canonical_account()
    payload = TransactionPayload(
        DexOrderlessTx(
            DexOrderlessTxVariant.DEX_SYSTEM_CONFIG,
            RawOrderlessInner(b"\x00"),
        )
    )
    raw_tx = RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=_MAX_GAS,
        gas_unit_price=_GAS_PRICE,
        expiration_timestamp_secs=_EXPIRATION,
        chain_id=_CHAIN_ID,
    )
    authenticator = account.sign_transaction_with_authenticator(raw_tx)
    return raw_tx, authenticator

def _zero_sub():
    return AccountAddress(b"\x00" * 32)


def _cross_transfer_payload(account, business_nonce=42):
    return TransactionPayload(
        DexOrderlessTx(
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(
                business_nonce,
                DexTransferVariant.CROSS_TRANSFER,
                [
                    CrossTransferItem(
                        account.account_address,
                        1,
                        4000000,
                        AccountType.SPOT,
                    )
                ],
                CrossTransferOption.BURN,
            ),
        )
    )


def _build_transfer(make_transfer):
    account = _canonical_account()
    transfer = make_transfer(account)
    return _build_orderless(DexOrderlessTxVariant.DEX_TRANSFER, transfer)


def _build_cross_transfer(make_transfer):
    account = _canonical_account()
    transfer = make_transfer(account)
    payload = TransactionPayload(
        DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, transfer)
    )
    raw_tx = RawTransaction.create_cross_transfer_orderless(
        sender=account.account_address,
        payload=payload,
        replay_protection_nonce=_CROSS_TRANSFER_REPLAY_NONCE,
        max_gas_amount=_MAX_GAS,
        gas_unit_price=_GAS_PRICE,
        expiration_timestamp_secs=_EXPIRATION,
        chain_id=_CHAIN_ID,
    )
    authenticator = account.sign_transaction_with_authenticator(raw_tx)
    return raw_tx, authenticator


def _build_orderless(variant, inner):
    account = _canonical_account()
    payload = TransactionPayload(DexOrderlessTx(variant, inner))
    raw_tx = RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=_MAX_GAS,
        gas_unit_price=_GAS_PRICE,
        expiration_timestamp_secs=_EXPIRATION,
        chain_id=_CHAIN_ID,
    )
    authenticator = account.sign_transaction_with_authenticator(raw_tx)
    return raw_tx, authenticator


class TestJsonSubmitPlace(unittest.TestCase):
    def _place_order_kwargs(self, **overrides):
        values = {
            "sub_address": AccountAddress(b"\x00" * 32),
            "symbol_id": 7,
            "symbol_type": SymbolType.PERPETUAL,
            "side": Side.BUY,
            "quantums": 1000,
            "subticks": 2000,
            "trigger_subticks": 0,
            "order_basic_type": OrderBasicType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "condition_type": ConditionType.UNSPECIFIED,
            "trigger_price_type": TriggerPriceType.LAST_PRICE,
            "target_order_id": 0,
            "reduce_only": False,
            "position_mode": OrderPositionMode.NET,
            "slippage_tolerance_ppm": 100_000,
        }
        values.update(overrides)
        return values

    def test_place_order_defaults_slippage_tolerance_ppm(self):
        kwargs = self._place_order_kwargs()
        kwargs.pop("slippage_tolerance_ppm")
        order = DexPlaceOrder(**kwargs)

        self.assertEqual(order.slippage_tolerance_ppm, 100_000)

    def test_place_order_omitted_slippage_tolerance_ppm_renders_default(self):
        kwargs = self._place_order_kwargs()
        kwargs.pop("slippage_tolerance_ppm")
        raw_tx, authenticator = _build_place_from_groups(
            [
                DexPlaceOrders(
                    [DexPlaceOrder(**kwargs)],
                    Grouping.NA,
                )
            ]
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)

        self.assertEqual(
            rendered["payload"]["orders"][0]["slippage_tolerance_ppm"],
            100_000,
        )

    def test_place_order_preserves_explicit_zero_slippage_tolerance_ppm(self):
        order = DexPlaceOrder(**self._place_order_kwargs(slippage_tolerance_ppm=0))

        self.assertEqual(order.slippage_tolerance_ppm, 0)

    def test_place_order_rejects_none_required_fields_with_field_name(self):
        for field in (
            "symbol_id",
            "quantums",
            "subticks",
            "trigger_subticks",
            "target_order_id",
            "slippage_tolerance_ppm",
            "reduce_only",
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    ValueError,
                    f"field {field} is required",
                ):
                    DexPlaceOrder(**self._place_order_kwargs(**{field: None}))

    def test_place_order_rejects_invalid_required_field_types(self):
        for field, value, expected in (
            ("symbol_id", "7", "field symbol_id must be u32"),
            ("quantums", "1000", "field quantums must be i64"),
            ("subticks", "2000", "field subticks must be u64"),
            ("reduce_only", 0, "field reduce_only must be bool"),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, expected):
                    DexPlaceOrder(**self._place_order_kwargs(**{field: value}))

    def test_place_order_rejects_out_of_range_required_fields(self):
        for field, value, expected in (
            ("symbol_id", -1, "field symbol_id must be u32"),
            ("quantums", 2**63, "field quantums must be i64"),
            ("subticks", -1, "field subticks must be u64"),
            (
                "slippage_tolerance_ppm",
                2**32,
                "field slippage_tolerance_ppm must be u32",
            ),
        ):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, expected):
                    DexPlaceOrder(**self._place_order_kwargs(**{field: value}))

    def test_place_limit_gtc_matches_ts_fixture(self):
        raw_tx, authenticator = _build_place(
            side=Side.BUY,
            basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            client_order_id=_CLIENT_ORDER_ID,
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("place_limit_gtc"))

    def test_place_market_ioc_sell_no_cloid_matches_ts_fixture(self):
        raw_tx, authenticator = _build_place(
            side=Side.SELL,
            basic_type=OrderBasicType.MARKET,
            time_in_force=TimeInForce.IOC,
            client_order_id=None,
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("place_market_ioc_sell"))

    def test_place_without_client_order_id_omits_key(self):
        raw_tx, authenticator = _build_place(
            side=Side.SELL,
            basic_type=OrderBasicType.MARKET,
            time_in_force=TimeInForce.IOC,
            client_order_id=None,
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertNotIn("client_order_id", rendered["payload"]["orders"][0])

    def test_replay_protection_nonce_equals_nonce(self):
        raw_tx, authenticator = _build_place(
            side=Side.BUY,
            basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            client_order_id=_CLIENT_ORDER_ID,
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered["replay_protection_nonce"], str(_NONCE))

    def test_invalid_side_is_rejected(self):
        raw_tx, authenticator = _build_place(
            side=99,
            basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            client_order_id=None,
        )
        with self.assertRaises(ValueError):
            generate_submit_transaction_request(raw_tx, authenticator)

    def test_invalid_time_in_force_is_rejected(self):
        raw_tx, authenticator = _build_place(
            side=Side.BUY,
            basic_type=OrderBasicType.LIMIT,
            time_in_force=99,
            client_order_id=None,
        )
        with self.assertRaises(ValueError):
            generate_submit_transaction_request(raw_tx, authenticator)


class TestJsonSubmitTransport(unittest.TestCase):
    def test_cross_transfer_bcs_and_json_share_the_signed_raw_transaction(self):
        raw_tx, authenticator = _build_cross_transfer(
            lambda acc: DexTransferTx(
                42,
                DexTransferVariant.CROSS_TRANSFER,
                [
                    CrossTransferItem(
                        acc.account_address,
                        1,
                        4000000,
                        AccountType.SPOT,
                    )
                ],
                CrossTransferOption.BURN,
            )
        )
        raw_bytes_before_json = raw_tx.bcs_to_bytes()
        signed_bcs_before_json = SignedTransaction(raw_tx, authenticator).bytes()

        json_content_type, json_body = build_submission_body(
            ClientConfig(), raw_tx, authenticator, encoding="json"
        )
        bcs_content_type, bcs_body = build_submission_body(
            ClientConfig(), raw_tx, authenticator, encoding="bcs"
        )

        json_request = json.loads(json_body)
        self.assertEqual(json_content_type, MIME_JSON)
        self.assertEqual(
            json_request["sequence_number"],
            str(_CROSS_TRANSFER_REPLAY_NONCE),
        )
        self.assertEqual(
            json_request["replay_protection_nonce"],
            str(_CROSS_TRANSFER_REPLAY_NONCE),
        )
        self.assertEqual(json_request["payload"]["nonce"], "42")
        self.assertEqual(raw_tx.bcs_to_bytes(), raw_bytes_before_json)
        self.assertEqual(bcs_content_type, MIME_BCS_SIGNED_TRANSACTION)
        self.assertEqual(bcs_body, signed_bcs_before_json)
        self.assertEqual(
            SignedTransaction(raw_tx, authenticator).bytes(),
            signed_bcs_before_json,
        )

    def test_default_encoding_is_json(self):
        raw_tx, authenticator = _build_place(
            side=Side.BUY,
            basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            client_order_id=_CLIENT_ORDER_ID,
        )
        content_type, body = build_submission_body(
            ClientConfig(), raw_tx, authenticator
        )
        self.assertEqual(content_type, MIME_JSON)
        self.assertEqual(json.loads(body), _load_fixture("place_limit_gtc"))

    def test_explicit_bcs_encoding_uses_bcs(self):
        raw_tx, authenticator = _build_place(
            side=Side.BUY,
            basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            client_order_id=_CLIENT_ORDER_ID,
        )
        content_type, body = build_submission_body(
            ClientConfig(), raw_tx, authenticator, encoding="bcs"
        )
        self.assertEqual(content_type, MIME_BCS_SIGNED_TRANSACTION)
        self.assertEqual(body, SignedTransaction(raw_tx, authenticator).bytes())

    def test_unsupported_payload_falls_back_to_bcs(self):
        raw_tx, authenticator = _build_unsupported_payload_tx()
        content_type, body = build_submission_body(
            ClientConfig(json_unsupported_payload_fallback="bcs"),
            raw_tx,
            authenticator,
        )
        self.assertEqual(content_type, MIME_BCS_SIGNED_TRANSACTION)
        self.assertEqual(body, SignedTransaction(raw_tx, authenticator).bytes())

    def test_unsupported_payload_error_mode_raises(self):
        raw_tx, authenticator = _build_unsupported_payload_tx()
        with self.assertRaises(UnsupportedJsonPayloadError):
            build_submission_body(
                ClientConfig(json_unsupported_payload_fallback="error"),
                raw_tx,
                authenticator,
            )

    def test_explicit_json_on_unsupported_raises_despite_fallback(self):
        raw_tx, authenticator = _build_unsupported_payload_tx()
        with self.assertRaises(UnsupportedJsonPayloadError):
            build_submission_body(
                ClientConfig(json_unsupported_payload_fallback="bcs"),
                raw_tx,
                authenticator,
                encoding="json",
            )

    def test_default_config_raises_on_unsupported_payload(self):
        # Default config (TS-aligned): JSON encoding, fallback "error".
        config = ClientConfig()
        self.assertEqual(config.default_submission_encoding, "json")
        self.assertEqual(config.json_unsupported_payload_fallback, "error")
        raw_tx, authenticator = _build_unsupported_payload_tx()
        with self.assertRaises(UnsupportedJsonPayloadError):
            build_submission_body(config, raw_tx, authenticator)


class TestSubmitTransactionMime(unittest.TestCase):
    def test_intention_submit_simple_uses_json_by_default(self):
        from intention_sdk.api.intention import Intention, IntentionConfig

        raw_tx, authenticator = _build_place(
            side=Side.BUY,
            basic_type=OrderBasicType.LIMIT,
            time_in_force=TimeInForce.GTC,
            client_order_id=_CLIENT_ORDER_ID,
        )
        captured = {}

        class _FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"hash": "0xabc"}

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, content=None, headers=None, **kwargs):
                captured["url"] = url
                captured["content"] = content
                captured["headers"] = headers
                return _FakeResponse()

        intention = Intention(IntentionConfig(fullnode="http://node"))
        with mock.patch("httpx.AsyncClient", return_value=_FakeClient()):
            result = asyncio.run(
                intention.transaction.submit.simple(raw_tx, authenticator)
            )

        self.assertEqual(result, {"hash": "0xabc"})
        self.assertEqual(captured["url"], "http://node/transactions")
        self.assertEqual(captured["headers"]["Content-Type"], MIME_JSON)
        self.assertEqual(
            json.loads(captured["content"]), _load_fixture("place_limit_gtc")
        )

    def test_bcs_helper_uses_intention_mime(self):
        from intention_sdk.transactions import transaction_builder as helpers
        from intention_sdk.api.client import MIME_BCS_SIGNED_TRANSACTION

        self.assertEqual(
            MIME_BCS_SIGNED_TRANSACTION,
            "application/x.intention.signed_transaction+bcs",
        )

        captured = {}

        class _FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"hash": "0x1"}

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, content=None, headers=None):
                captured["headers"] = headers
                return _FakeResponse()

        with mock.patch("httpx.AsyncClient", return_value=_FakeClient()):
            asyncio.run(helpers.submit_transaction({"nodeUrl": "http://node"}, b"\x00"))

        self.assertEqual(
            captured["headers"]["Content-Type"], MIME_BCS_SIGNED_TRANSACTION
        )


class TestJsonSubmitOrderGroups(unittest.TestCase):
    """``order_groups`` must mirror the signed ``DexPlaceOrders`` batch boundaries.

    Flat ``orders`` flattens adjacent same-grouping batches, which the node cannot
    tell apart from a single merged batch; the reconstructed raw transaction would
    then differ from the signed one and fail signature verification.
    """

    def test_single_group_place_emits_order_groups(self):
        raw_tx, authenticator = _build_place_from_groups(
            [
                DexPlaceOrders(
                    [_build_place_order(client_order_id=_CLIENT_ORDER_ID)], Grouping.NA
                )
            ]
        )
        payload = generate_submit_transaction_request(raw_tx, authenticator)["payload"]
        self.assertEqual(payload["operation"], "place")
        self.assertEqual(len(payload["order_groups"]), 1)
        self.assertEqual(payload["order_groups"][0]["grouping"], int(Grouping.NA))
        flattened = [
            order for group in payload["order_groups"] for order in group["orders"]
        ]
        self.assertEqual(flattened, payload["orders"])

    def test_adjacent_same_grouping_batches_are_preserved(self):
        first = _build_place_order(client_order_id=_CLIENT_ORDER_ID)
        second = _build_place_order(
            symbol_id=8,
            side=Side.SELL,
            quantums=3000,
            subticks=4000,
            client_order_id=_NEW_CLIENT_ORDER_ID,
        )
        adjacent_raw, adjacent_auth = _build_place_from_groups(
            [
                DexPlaceOrders([first], Grouping.NA),
                DexPlaceOrders([second], Grouping.NA),
            ]
        )
        merged_raw, merged_auth = _build_place_from_groups(
            [DexPlaceOrders([first, second], Grouping.NA)]
        )
        adjacent = generate_submit_transaction_request(adjacent_raw, adjacent_auth)
        merged = generate_submit_transaction_request(merged_raw, merged_auth)

        # Flat legacy orders cannot distinguish the two signed shapes ...
        self.assertEqual(adjacent["payload"]["orders"], merged["payload"]["orders"])
        # ... but the signed bytes differ, so nested order_groups are required.
        self.assertNotEqual(
            SignedTransaction(adjacent_raw, adjacent_auth).bytes(),
            SignedTransaction(merged_raw, merged_auth).bytes(),
        )
        self.assertEqual(len(adjacent["payload"]["order_groups"]), 2)
        self.assertEqual(len(merged["payload"]["order_groups"]), 1)
        self.assertEqual(
            [
                order
                for group in adjacent["payload"]["order_groups"]
                for order in group["orders"]
            ],
            adjacent["payload"]["orders"],
        )

    def test_cancel_payload_has_no_order_groups(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.CANCEL,
            [
                DexCancelOrder.by_order_id(
                    _zero_sub(), _TARGET_ORDER_ID, SymbolType.PERPETUAL
                )
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertNotIn("order_groups", rendered["payload"])

    def test_replace_payload_has_no_order_groups(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.REPLACE,
            [
                DexReplaceOrder.by_order_id(
                    _zero_sub(),
                    _TARGET_ORDER_ID,
                    symbol_id=1,
                    symbol_type=SymbolType.PERPETUAL,
                    quantums=3000,
                    subticks=4000,
                    new_client_order_id=_NEW_CLIENT_ORDER_ID,
                )
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertNotIn("order_groups", rendered["payload"])

    def test_grouping_normal_tpsl_rejects_limit_children(self):
        entry = _build_place_order()
        tp = _build_place_order()
        tp.condition_type = ConditionType.TAKE_PROFIT
        tp.order_basic_type = OrderBasicType.LIMIT

        with self.assertRaisesRegex(ValueError, "market execution"):
            DexPlaceOrders([entry, tp], Grouping.NORMAL_TPSL)

    def test_grouping_position_tpsl_rejects_normal_orders(self):
        with self.assertRaisesRegex(ValueError, "only allows"):
            DexPlaceOrders([_build_place_order()], Grouping.POSITION_TPSL)

    def test_grouping_position_tpsl_whole_position_requires_reduce_only(self):
        tp = _build_place_order(quantums=0, subticks=0)
        tp.condition_type = ConditionType.TAKE_PROFIT
        tp.order_basic_type = OrderBasicType.MARKET
        tp.trigger_subticks = 2500
        tp.reduce_only = False

        with self.assertRaisesRegex(
            ValueError, "whole-position orders require reduce_only = true"
        ):
            DexPlaceOrders([tp], Grouping.POSITION_TPSL)

    def test_grouping_position_tpsl_closeall_sides_imply_reduce_only(self):
        for side in (Side.CLOSEALL_LONG, Side.CLOSEALL_SHORT):
            with self.subTest(side=side):
                tp = _build_place_order(quantums=0, subticks=0)
                tp.side = side
                tp.condition_type = ConditionType.TAKE_PROFIT
                tp.order_basic_type = OrderBasicType.MARKET
                tp.trigger_subticks = 2500
                tp.reduce_only = False

                DexPlaceOrders([tp], Grouping.POSITION_TPSL)


class TestJsonSubmitCancelReplace(unittest.TestCase):
    def test_cancel_by_order_id_matches_fixture(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.CANCEL,
            [
                DexCancelOrder.by_order_id(
                    _zero_sub(), _TARGET_ORDER_ID, SymbolType.PERPETUAL
                )
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("cancel_by_order_id"))

    def test_cancel_by_client_order_id_matches_fixture(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.CANCEL,
            [
                DexCancelOrder.by_client_order_id(
                    _zero_sub(), _CLIENT_ORDER_ID, SymbolType.PERPETUAL
                )
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("cancel_by_client_order_id"))

    def test_cancel_batch_matches_fixture(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.CANCEL,
            [
                DexCancelOrder.by_order_id(
                    _zero_sub(), _TARGET_ORDER_ID, SymbolType.PERPETUAL
                ),
                DexCancelOrder.by_client_order_id(
                    _zero_sub(), _CLIENT_ORDER_ID, SymbolType.PERPETUAL
                ),
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("cancel_batch"))

    def test_replace_by_order_id_matches_fixture(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.REPLACE,
            [
                DexReplaceOrder.by_order_id(
                    _zero_sub(),
                    _TARGET_ORDER_ID,
                    symbol_id=1,
                    symbol_type=SymbolType.PERPETUAL,
                    quantums=3000,
                    subticks=4000,
                    new_client_order_id=_NEW_CLIENT_ORDER_ID,
                )
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("replace_by_order_id"))

    def test_replace_by_client_order_id_matches_fixture(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.REPLACE,
            [
                DexReplaceOrder.by_client_order_id(
                    _zero_sub(), _CLIENT_ORDER_ID, 3000, 4000, _NEW_CLIENT_ORDER_ID
                )
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("replace_by_client_order_id"))

    def test_replace_partial_omits_unset_optionals(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.REPLACE,
            [
                DexReplaceOrder.by_order_id(
                    _zero_sub(),
                    _TARGET_ORDER_ID,
                    symbol_id=1,
                    symbol_type=SymbolType.PERPETUAL,
                    quantums=3000,
                )
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("replace_partial_quantums_only"))
        order = rendered["payload"]["orders"][0]
        self.assertIn("quantums", order)
        self.assertNotIn("subticks", order)
        self.assertNotIn("new_client_order_id", order)

    def test_condition_replace_json_payload(self):
        raw_tx, authenticator = _build_dex_orders(
            DexOrdersVariant.REPLACE_CONDITION,
            [
                DexConditionReplaceOrder.by_client_order_id(
                    _zero_sub(),
                    _CLIENT_ORDER_ID,
                    -1000,
                    0,
                    5895000000000,
                    OrderBasicType.MARKET,
                    ConditionType.STOP_LOSS,
                    TriggerPriceType.MARK_PRICE,
                    _NEW_CLIENT_ORDER_ID,
                )
            ],
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)

        payload = rendered["payload"]
        self.assertEqual(payload["operation"], "replace_condition")
        self.assertNotIn("order_groups", payload)
        order = payload["orders"][0]
        self.assertEqual(order["target"]["target_type"], "client_order_id")
        self.assertEqual(order["target"]["client_order_id"], _CLIENT_ORDER_ID)
        self.assertEqual(order["quantums"], "-1000")
        self.assertEqual(order["subticks"], "0")
        self.assertEqual(order["trigger_subticks"], "5895000000000")
        self.assertEqual(order["order_basic_type"], int(OrderBasicType.MARKET))
        self.assertEqual(order["condition_type"], int(ConditionType.STOP_LOSS))
        self.assertEqual(order["trigger_price_type"], int(TriggerPriceType.MARK_PRICE))
        self.assertEqual(order["new_client_order_id"], _NEW_CLIENT_ORDER_ID)

    def test_condition_replace_bcs_roundtrip(self):
        orders = DexOrders(
            DexOrdersVariant.REPLACE_CONDITION,
            [
                DexConditionReplaceOrder.by_order_id(
                    _zero_sub(),
                    _TARGET_ORDER_ID,
                    3000,
                    4000,
                    5000,
                    OrderBasicType.LIMIT,
                    ConditionType.TAKE_PROFIT,
                    TriggerPriceType.LAST_PRICE,
                    _NEW_CLIENT_ORDER_ID,
                )
            ],
        )

        serializer = Serializer()
        orders.serialize(serializer)
        decoded = DexOrders.deserialize(Deserializer(serializer.to_bytes()))

        self.assertEqual(decoded.variant, DexOrdersVariant.REPLACE_CONDITION)
        decoded_order = decoded.orders[0]
        self.assertIsInstance(decoded_order, DexConditionReplaceOrder)
        self.assertEqual(decoded_order.target.order_id, _TARGET_ORDER_ID)
        self.assertEqual(decoded_order.quantums, 3000)
        self.assertEqual(decoded_order.subticks, 4000)
        self.assertEqual(decoded_order.trigger_subticks, 5000)
        self.assertEqual(decoded_order.order_basic_type, OrderBasicType.LIMIT)
        self.assertEqual(decoded_order.condition_type, ConditionType.TAKE_PROFIT)
        self.assertEqual(decoded_order.trigger_price_type, TriggerPriceType.LAST_PRICE)
        self.assertEqual(decoded_order.new_client_order_id, _NEW_CLIENT_ORDER_ID)

    def test_condition_replace_rejects_invalid_full_spec_shape(self):
        with self.assertRaisesRegex(ValueError, "trigger_subticks"):
            DexConditionReplaceOrder.by_order_id(
                _zero_sub(),
                _TARGET_ORDER_ID,
                1000,
                0,
                0,
                OrderBasicType.MARKET,
                ConditionType.STOP_LOSS,
                TriggerPriceType.MARK_PRICE,
            )
        with self.assertRaisesRegex(ValueError, "condition_type"):
            DexConditionReplaceOrder.by_order_id(
                _zero_sub(),
                _TARGET_ORDER_ID,
                1000,
                0,
                5000,
                OrderBasicType.MARKET,
                ConditionType.UNSPECIFIED,
                TriggerPriceType.MARK_PRICE,
            )
        with self.assertRaisesRegex(ValueError, "market execution"):
            DexConditionReplaceOrder.by_order_id(
                _zero_sub(),
                _TARGET_ORDER_ID,
                1000,
                4000,
                5000,
                OrderBasicType.MARKET,
                ConditionType.STOP_LOSS,
                TriggerPriceType.MARK_PRICE,
            )
        with self.assertRaisesRegex(ValueError, "limit execution"):
            DexConditionReplaceOrder.by_order_id(
                _zero_sub(),
                _TARGET_ORDER_ID,
                1000,
                0,
                5000,
                OrderBasicType.LIMIT,
                ConditionType.TAKE_PROFIT,
                TriggerPriceType.LAST_PRICE,
            )


class TestJsonSubmitTransfer(unittest.TestCase):
    def test_cross_transfer_uses_explicit_replay_nonce_in_raw_transaction(self):
        account = _canonical_account()
        payload = _cross_transfer_payload(account)

        raw_tx = RawTransaction.create_cross_transfer_orderless(
            sender=account.account_address,
            payload=payload,
            replay_protection_nonce=_CROSS_TRANSFER_REPLAY_NONCE,
            max_gas_amount=_MAX_GAS,
            gas_unit_price=_GAS_PRICE,
            expiration_timestamp_secs=_EXPIRATION,
            chain_id=_CHAIN_ID,
        )

        self.assertEqual(raw_tx.sequence_number, _CROSS_TRANSFER_REPLAY_NONCE)

    def test_cross_transfer_json_keeps_business_and_replay_nonces_independent(self):
        account = _canonical_account()
        payload = _cross_transfer_payload(account)
        raw_tx = RawTransaction.create_cross_transfer_orderless(
            sender=account.account_address,
            payload=payload,
            replay_protection_nonce=_CROSS_TRANSFER_REPLAY_NONCE,
            max_gas_amount=_MAX_GAS,
            gas_unit_price=_GAS_PRICE,
            expiration_timestamp_secs=_EXPIRATION,
            chain_id=_CHAIN_ID,
        )

        rendered = generate_submit_transaction_request(
            raw_tx, account.sign_transaction_with_authenticator(raw_tx)
        )

        self.assertEqual(rendered["sequence_number"], str(_CROSS_TRANSFER_REPLAY_NONCE))
        self.assertEqual(
            rendered["replay_protection_nonce"],
            str(_CROSS_TRANSFER_REPLAY_NONCE),
        )
        self.assertEqual(rendered["payload"]["nonce"], "42")

    def test_cross_transfer_entry_rejects_an_ordinary_orderless_payload(self):
        account = _canonical_account()
        payload = TransactionPayload(
            DexOrderlessTx(
                DexOrderlessTxVariant.DEX_TRANSFER,
                DexTransferTx(
                    42,
                    DexTransferVariant.INTERNAL_TRANSFER,
                    [
                        InternalTransferItem(
                            _zero_sub(),
                            account.account_address,
                            1,
                            4000000,
                            AccountType.SPOT,
                        )
                    ],
                ),
            )
        )

        with self.assertRaisesRegex(
            ValueError,
            "requires a CrossTransfer orderless payload",
        ):
            RawTransaction.create_cross_transfer_orderless(
                sender=account.account_address,
                payload=payload,
                replay_protection_nonce=_CROSS_TRANSFER_REPLAY_NONCE,
                max_gas_amount=_MAX_GAS,
                gas_unit_price=_GAS_PRICE,
                expiration_timestamp_secs=_EXPIRATION,
                chain_id=_CHAIN_ID,
            )

    def test_ordinary_orderless_entry_rejects_cross_transfer(self):
        account = _canonical_account()
        payload = _cross_transfer_payload(account)

        with self.assertRaisesRegex(
            ValueError,
            "CrossTransfer requires an explicit replay nonce; "
            "use create_cross_transfer_orderless",
        ):
            RawTransaction.create_orderless(
                sender=account.account_address,
                payload=payload,
                max_gas_amount=_MAX_GAS,
                gas_unit_price=_GAS_PRICE,
                expiration_timestamp_secs=_EXPIRATION,
                chain_id=_CHAIN_ID,
            )

    def test_cross_transfer_rejects_reserved_max_u64_replay_nonce(self):
        account = _canonical_account()
        payload = _cross_transfer_payload(account)

        with self.assertRaisesRegex(
            ValueError,
            "must not use the reserved MAX_U64 value",
        ):
            RawTransaction.create_cross_transfer_orderless(
                sender=account.account_address,
                payload=payload,
                replay_protection_nonce=MAX_U64,
                max_gas_amount=_MAX_GAS,
                gas_unit_price=_GAS_PRICE,
                expiration_timestamp_secs=_EXPIRATION,
                chain_id=_CHAIN_ID,
            )

    def test_cross_transfer_rejects_invalid_replay_nonce_values(self):
        account = _canonical_account()
        payload = _cross_transfer_payload(account)
        invalid_values = (
            (None, "required and must be an int"),
            (True, "required and must be an int"),
            ("9001", "required and must be an int"),
            (-1, "must be in the u64 range"),
            (MAX_U64 + 1, "must be in the u64 range"),
        )

        for replay_nonce, message in invalid_values:
            with self.subTest(replay_nonce=replay_nonce):
                with self.assertRaisesRegex(ValueError, message):
                    RawTransaction.create_cross_transfer_orderless(
                        sender=account.account_address,
                        payload=payload,
                        replay_protection_nonce=replay_nonce,
                        max_gas_amount=_MAX_GAS,
                        gas_unit_price=_GAS_PRICE,
                        expiration_timestamp_secs=_EXPIRATION,
                        chain_id=_CHAIN_ID,
                    )

    def test_internal_transfer_matches_fixture(self):
        raw_tx, authenticator = _build_transfer(
            lambda acc: DexTransferTx(
                _NONCE,
                DexTransferVariant.INTERNAL_TRANSFER,
                [
                    InternalTransferItem(
                        _zero_sub(), acc.account_address, 0, 1000000, AccountType.PERP
                    )
                ],
            )
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("transfer_internal"))

    def test_account_transfer_matches_fixture(self):
        raw_tx, authenticator = _build_transfer(
            lambda acc: DexTransferTx(
                _NONCE,
                DexTransferVariant.ACCOUNT_TRANSFER,
                [
                    AccountTransferItem(
                        acc.account_address, 0, 2000000, AccountType.SPOT
                    )
                ],
            )
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("transfer_account"))

    def test_cross_transfer_mint_with_bridge_proof_matches_fixture(self):
        raw_tx, authenticator = _build_cross_transfer(
            lambda acc: DexTransferTx(
                _NONCE,
                DexTransferVariant.CROSS_TRANSFER,
                [CrossTransferItem(acc.account_address, 0, 1000, AccountType.PERP)],
                CrossTransferOption.MINT,
                BridgeProof(
                    b"\x01" * 32,
                    1,
                    [BridgeSignature(b"\x02" * 32, b"\x03" * 32, 27)],
                ),
            )
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("transfer_cross_mint_with_proof"))

    def test_cross_transfer_burn_omits_bridge_proof(self):
        raw_tx, authenticator = _build_cross_transfer(
            lambda acc: DexTransferTx(
                _NONCE,
                DexTransferVariant.CROSS_TRANSFER,
                [CrossTransferItem(acc.account_address, 1, 4000000, AccountType.SPOT)],
                CrossTransferOption.BURN,
            )
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("transfer_cross_burn_no_proof"))
        self.assertNotIn("bridge_proof", rendered["payload"])

    def test_faucet_mint_matches_fixture(self):
        raw_tx, authenticator = _build_transfer(
            lambda acc: DexTransferTx(
                _NONCE,
                DexTransferVariant.FAUCET_MINT,
                [CrossTransferItem(acc.account_address, 0, 5000000, AccountType.PERP)],
            )
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("transfer_faucet_mint"))


class TestJsonSubmitAgent(unittest.TestCase):
    def test_agent_approve_matches_fixture(self):
        raw_tx, authenticator = _build_orderless(
            DexOrderlessTxVariant.DEX_AGENT,
            DexAgentTx(
                _NONCE,
                AgentOperationVariant.APPROVE,
                AgentApprove(_AGENT_NAME, _AGENT_ADDRESS, _AGENT_EXPIRY),
            ),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("agent_approve"))

    def test_agent_revoke_matches_fixture(self):
        raw_tx, authenticator = _build_orderless(
            DexOrderlessTxVariant.DEX_AGENT,
            DexAgentTx(_NONCE, AgentOperationVariant.REVOKE, AgentRevoke(_AGENT_NAME)),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("agent_revoke"))

    def test_agent_variant_operation_mismatch_raises(self):
        raw_tx, authenticator = _build_orderless(
            DexOrderlessTxVariant.DEX_AGENT,
            DexAgentTx(_NONCE, AgentOperationVariant.APPROVE, AgentRevoke(_AGENT_NAME)),
        )
        with self.assertRaises(ValueError):
            generate_submit_transaction_request(raw_tx, authenticator)


def _build_user_config(variant, payload):
    return _build_orderless(
        DexOrderlessTxVariant.DEX_USER_CONFIG, DexUserConfigTx(variant, payload)
    )


class TestJsonSubmitUserConfig(unittest.TestCase):
    def test_set_user_leverage_matches_fixture(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.SET_USER_LEVERAGE,
            SetUserLeverage(_NONCE, _zero_sub(), [UserSymbolLeverage(7, 10)]),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("user_set_leverage"))

    def test_set_user_leverage_on_behalf_matches_fixture(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.SET_USER_LEVERAGE,
            SetUserLeverage(
                _NONCE, _zero_sub(), [UserSymbolLeverage(3, 20)], _MASTER_ADDRESS
            ),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("user_set_leverage_on_behalf"))
        self.assertEqual(
            rendered["payload"]["on_behalf_of"], _MASTER_ADDRESS.to_string_long()
        )

    def test_change_position_mode_matches_fixture(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.CHANGE_POSITION_MODE,
            ChangePositionMode(_NONCE, _zero_sub(), OrderPositionMode.HEDGE),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("user_change_position_mode"))

    def test_change_margin_mode_matches_fixture(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.CHANGE_MARGIN_MODE,
            ChangeMarginMode(
                _NONCE, _zero_sub(), [SymbolMarginMode(7, MarginMode.ISOLATED)]
            ),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("user_change_margin_mode"))

    def test_create_sub_account_matches_fixture(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.CREATE_SUB_ACCOUNT,
            CreateSubAccount(_NONCE, "trading-sub"),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("user_create_sub_account"))

    def test_modify_sub_account_matches_fixture(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.MODIFY_SUB_ACCOUNT,
            ModifySubAccount(
                _NONCE, "renamed-sub", _SUBACCOUNT_ADDRESS, _MASTER_ADDRESS
            ),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("user_modify_sub_account"))

    def test_adjust_isolated_margin_matches_fixture(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN,
            AdjustIsolatedMargin(_NONCE, _zero_sub(), 7, 500000, -250000),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture("user_adjust_isolated_margin"))
        self.assertNotIn("on_behalf_of", rendered["payload"])

    def test_adjust_isolated_margin_on_behalf_matches_fixture(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN,
            AdjustIsolatedMargin(
                _NONCE, _zero_sub(), 3, -100000, 200000, _MASTER_ADDRESS
            ),
        )
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(
            rendered, _load_fixture("user_adjust_isolated_margin_on_behalf")
        )
        self.assertEqual(
            rendered["payload"]["on_behalf_of"], _MASTER_ADDRESS.to_string_long()
        )

    def test_invalid_position_mode_rejected(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.CHANGE_POSITION_MODE,
            ChangePositionMode(_NONCE, _zero_sub(), 99),
        )
        with self.assertRaises(ValueError):
            generate_submit_transaction_request(raw_tx, authenticator)

    def test_invalid_margin_mode_rejected(self):
        raw_tx, authenticator = _build_user_config(
            DexUserConfigTxVariant.CHANGE_MARGIN_MODE,
            ChangeMarginMode(_NONCE, _zero_sub(), [SymbolMarginMode(7, 99)]),
        )
        with self.assertRaises(ValueError):
            generate_submit_transaction_request(raw_tx, authenticator)


def _build_vault(vault_tx):
    return _build_orderless(DexOrderlessTxVariant.VAULT, vault_tx)


class TestJsonSubmitVault(unittest.TestCase):
    def _check(self, vault_tx, fixture_name):
        raw_tx, authenticator = _build_vault(vault_tx)
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture(fixture_name))
        return rendered

    def test_create(self):
        self._check(
            VaultTx(
                VaultTxVariant.CREATE,
                VaultCreateTx(
                    _NONCE, 86400, True, 5000000000, "alpha-vault", "delta neutral"
                ),
            ),
            "vault_create",
        )

    def test_deposit(self):
        self._check(
            VaultTx(VaultTxVariant.DEPOSIT, VaultDepositTx(7, _NONCE, 100000000)),
            "vault_deposit",
        )

    def test_withdraw(self):
        self._check(
            VaultTx(VaultTxVariant.WITHDRAW, VaultWithdrawTx(7, _NONCE, 250000)),
            "vault_withdraw",
        )

    def test_distribute(self):
        self._check(
            VaultTx(VaultTxVariant.DISTRIBUTE, VaultDistributeTx(7, _NONCE, 1000000)),
            "vault_distribute",
        )

    def test_clp_config_full(self):
        self._check(
            VaultTx(
                VaultTxVariant.CLP_CONFIG,
                VaultClpConfigTx(
                    _NONCE,
                    True,
                    _VAULT_SUB,
                    [SymbolAccountsEntry(5, [_VAULT_SUB])],
                    [ClpTraderAllowlistEntry(_VAULT_SUB, [_VAULT_TRADER])],
                ),
            ),
            "vault_clp_config",
        )

    def test_clp_config_minimal_omits_optionals(self):
        rendered = self._check(
            VaultTx(VaultTxVariant.CLP_CONFIG, VaultClpConfigTx(_NONCE, False)),
            "vault_clp_config_minimal",
        )
        payload = rendered["payload"]
        self.assertNotIn("primary_account", payload)
        self.assertNotIn("symbol_accounts", payload)
        self.assertNotIn("allowlist", payload)

    def test_clp_managed_account_with_memo(self):
        self._check(
            VaultTx(
                VaultTxVariant.CLP_MANAGED_ACCOUNT,
                VaultClpManagedAccountTx(
                    _NONCE, _VAULT_SUB, ManagedAccountAction.UPSERT, "ops"
                ),
            ),
            "vault_clp_managed_account",
        )

    def test_clp_managed_account_no_memo(self):
        rendered = self._check(
            VaultTx(
                VaultTxVariant.CLP_MANAGED_ACCOUNT,
                VaultClpManagedAccountTx(
                    _NONCE, _VAULT_SUB, ManagedAccountAction.DISABLE
                ),
            ),
            "vault_clp_managed_account_no_memo",
        )
        self.assertNotIn("memo", rendered["payload"])

    def test_clp_trader_allowlist_update(self):
        self._check(
            VaultTx(
                VaultTxVariant.CLP_TRADER_ALLOWLIST_UPDATE,
                VaultClpTraderAllowlistUpdateTx(
                    _NONCE, _VAULT_SUB, ClpTraderAllowlistAction.ADD, [_VAULT_TRADER]
                ),
            ),
            "vault_clp_trader_allowlist_update",
        )

    def test_clp_batch_create(self):
        self._check(
            VaultTx(
                VaultTxVariant.CLP_BATCH_CREATE_MANAGED_ACCOUNTS,
                VaultClpBatchCreateManagedAccountsTx(
                    _NONCE, _VAULT_TRADER, 10, 5, "bot-", "batch memo"
                ),
            ),
            "vault_clp_batch_create",
        )

    def test_set_params_partial(self):
        rendered = self._check(
            VaultTx(VaultTxVariant.SET_PARAMS, VaultSetParamsTx(_NONCE, 7, 1000, 500)),
            "vault_set_params",
        )
        payload = rendered["payload"]
        self.assertNotIn("lockup_seconds", payload)
        self.assertNotIn("always_proportional_close", payload)

    def test_set_params_full(self):
        self._check(
            VaultTx(
                VaultTxVariant.SET_PARAMS,
                VaultSetParamsTx(_NONCE, 7, 1000, 500, 86400, True),
            ),
            "vault_set_params_full",
        )

    def test_set_status(self):
        self._check(
            VaultTx(
                VaultTxVariant.SET_STATUS,
                VaultSetStatusTx(_NONCE, 7, VaultStatus.PAUSED),
            ),
            "vault_set_status",
        )


# ---- multisig ------------------------------------------------------------
#
# Fixtures record the reference multisig request rendering.
#
# The approvals below are fixed bytes rather than real signatures, and that is
# the point of the comparison: what the owners signed is checked on chain, while
# what the two SDKs must agree on is the rendering. A field renamed or left out
# on one side is not a formatting difference -- the owners signed
# keccak256(BCS(op)), so the node rebuilds a different operation id and reports
# a proof pointing at another operation rather than a parse error.
_MS_ACCOUNT = AccountAddress.from_str("0x" + "a1" * 32)
_MS_OWNERS = ["0x" + "11" * 20, "0x" + "22" * 20, "0x" + "33" * 20]
_MS_THRESHOLD = 2
_MS_CREATE_SALT = bytes([0x5A]) * 32
_MS_OP_ID = bytes([0x7E]) * 32
_MS_AUTHORITY_EPOCH = 3
_MS_PROOF_EXPIRES_AT = 9999999999
_MS_NEW_AUTH_KEY = bytes([0xCC]) * 32
_MS_ED25519_PUBLIC_KEY = bytes([0xED]) * 32
_MS_ED25519_SIGNATURE = bytes([0xEE]) * 64


def _ms_signature(fill: int) -> BridgeSignature:
    return BridgeSignature(bytes([fill]) * 32, bytes([fill + 1]) * 32, 27)


def _ms_proof() -> MultisigProof:
    return MultisigProof(
        _MS_OP_ID,
        _MS_AUTHORITY_EPOCH,
        _MS_PROOF_EXPIRES_AT,
        [_ms_signature(0x41), _ms_signature(0x61)],
    )


class TestJsonSubmitMultisig(unittest.TestCase):
    def _check(self, op, fixture_name, *, proof=True):
        tx = DexMultisigTx(
            _NONCE, _MS_ACCOUNT, op, _ms_proof() if proof else None
        )
        raw_tx, authenticator = _build_orderless(DexOrderlessTxVariant.MULTISIG, tx)
        rendered = generate_submit_transaction_request(raw_tx, authenticator)
        self.assertEqual(rendered, _load_fixture(fixture_name))
        return rendered

    def test_create_policy(self):
        self._check(
            MultisigOpCreate(_MS_OWNERS, _MS_THRESHOLD, _MS_CREATE_SALT),
            "multisig_create_policy",
        )

    def test_install_policy(self):
        self._check(
            MultisigOpInstall(_MS_OWNERS, _MS_THRESHOLD),
            "multisig_install_policy",
        )

    def test_update_policy(self):
        self._check(
            MultisigOpUpdatePolicy(_MS_OWNERS[:2], _MS_THRESHOLD),
            "multisig_update_policy",
        )

    def test_remove_policy(self):
        self._check(
            MultisigOpRemove(
                _MS_NEW_AUTH_KEY, KeyProofSecp256k1(_ms_signature(0x81))
            ),
            "multisig_remove_policy",
        )

    def test_rotate_key_with_an_ed25519_challenge(self):
        self._check(
            MultisigOpRotateKey(
                _MS_NEW_AUTH_KEY,
                KeyProofEd25519(_MS_ED25519_PUBLIC_KEY, _MS_ED25519_SIGNATURE),
            ),
            "multisig_rotate_key_ed25519",
        )

    def test_rotate_key_without_approvals(self):
        # A rotation is the one operation a submission may carry without a
        # proof: the account's own key sends it. The rendering has to leave the
        # field out rather than write a null, which is a different value.
        rendered = self._check(
            MultisigOpRotateKey(
                _MS_NEW_AUTH_KEY, KeyProofSecp256k1(_ms_signature(0x81))
            ),
            "multisig_rotate_key_no_proof",
            proof=False,
        )
        self.assertNotIn("proof", rendered["payload"])
        self.assertEqual(rendered["payload"]["signatures_count"], 0)

    def test_execute_a_transfer(self):
        rendered = self._check(
            MultisigOpExecute(
                GatedPayload(
                    GatedPayloadVariant.DEX_TRANSFER,
                    DexTransferTx(
                        _NONCE,
                        DexTransferVariant.ACCOUNT_TRANSFER,
                        [
                            AccountTransferItem(
                                AccountAddress.from_str("0x" + "44" * 32),
                                0,
                                5000000,
                                AccountType.PERP,
                            )
                        ],
                    ),
                )
            ),
            "multisig_execute_transfer",
        )
        # The inner payload keeps its own dex_type and loses the outer one: it
        # is the operation being authorized, not a transaction of its own.
        inner = rendered["payload"]["op"]
        self.assertEqual(inner["dex_type"], "dex_transfer_payload")
        self.assertNotIn("type", inner)

    def test_execute_a_subaccount_creation(self):
        rendered = self._check(
            MultisigOpExecute(
                GatedPayload(
                    GatedPayloadVariant.CREATE_SUB_ACCOUNT,
                    CreateSubAccount(_NONCE, "desk-one"),
                )
            ),
            "multisig_execute_create_subaccount",
        )
        # The chain's gated arm is the bare create-subaccount transaction, but
        # the JSON shape is the user-config union it belongs to -- discriminator
        # included, which is `user_config_type` and not something spelled by
        # hand here.
        inner = rendered["payload"]["op"]
        self.assertEqual(inner["dex_type"], "dex_user_config_payload")
        self.assertEqual(inner["user_config_type"], "create_sub_account")

    def test_execute_an_agent_approval(self):
        self._check(
            MultisigOpExecute(
                GatedPayload(
                    GatedPayloadVariant.DEX_AGENT,
                    DexAgentTx(
                        _NONCE,
                        AgentOperationVariant.APPROVE,
                        AgentApprove(
                            _AGENT_NAME, _AGENT_ADDRESS, _AGENT_EXPIRY
                        ),
                    ),
                )
            ),
            "multisig_execute_agent",
        )


if __name__ == "__main__":
    unittest.main()

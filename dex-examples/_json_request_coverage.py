#!/usr/bin/env python3
# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Captured JSON submit request coverage for every supported orderless path."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

import httpx

THIS_DIR = os.path.dirname(__file__)
REPO_ROOT = os.path.join(THIS_DIR, "..")
if THIS_DIR not in sys.path:
    sys.path.insert(0, THIS_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from _common import build_and_submit_dex_orderless  # noqa: E402

from intention_sdk.core.account import Account  # noqa: E402
from intention_sdk.core.account_address import AccountAddress  # noqa: E402
from intention_sdk.api.client import (  # noqa: E402
    MIME_BCS_SIGNED_TRANSACTION,
    MIME_JSON,
    ClientConfig,
    RestClient,
)
from intention_sdk.transactions.dex_payloads import AccountTransferItem  # noqa: E402
from intention_sdk.transactions.dex_payloads import (
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
    DexOrderlessTx,
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
from intention_sdk.core.account import Secp256k1PrivateKey as PrivateKey  # noqa: E402
from intention_sdk.transactions import RawTransaction, TransactionPayload  # noqa: E402
from intention_sdk.transactions.vault_payloads import (  # noqa: E402
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
from intention_sdk.types.vault import ClpTraderAllowlistAction  # noqa: E402
from intention_sdk.types.vault import (
    ClpTraderAllowlistEntry,
    ManagedAccountAction,
    SubaccountId,
    SymbolAccountsEntry,
    VaultStatus,
    VaultTxVariant,
)

PRIVATE_KEY = (
    "secp256k1-priv-"
    "0x1111111111111111111111111111111111111111111111111111111111111111"
)
NONCE = 123456789
CROSS_TRANSFER_REPLAY_NONCE = 9001
MAX_GAS = 200000
GAS_PRICE = 100
EXPIRATION = 9999999999
CHAIN_ID = 4
CLIENT_ORDER_ID = "0x0123456789abcdef0123456789abcdef"
NEW_CLIENT_ORDER_ID = "0xfedcba9876543210fedcba9876543210"
AGENT_NAME = "coverage-agent"
AGENT_ADDRESS = AccountAddress.from_str("0x" + "22" * 32)
AGENT_EXPIRY = 9999999999
MASTER_ADDRESS = AccountAddress.from_str("0x" + "44" * 32)
SUBACCOUNT_ADDRESS = AccountAddress.from_str("0x" + "33" * 32)
VAULT_SUB = SubaccountId(b"\xab" * 32, 3, b"\xcd" * 32)
VAULT_TRADER = AccountAddress.from_str("0x" + "99" * 32)
ADMIN_ADDRESS = AccountAddress.from_str("0x" + "aa" * 32)
SPOT_TICKER = b"BTC-USDC".ljust(32, b"\x00")
MAX_NOTIONAL = bytes([0x40, 0x42, 0x0F]) + b"\x00" * 13


class JsonRequestCase:
    def __init__(
        self,
        name: str,
        orderless_tx: DexOrderlessTx,
        expected_payload: Dict[str, Any],
    ):
        self.name = name
        self.orderless_tx = orderless_tx
        self.expected_payload = expected_payload


class CapturedSubmitServer:
    def __init__(self):
        self.submissions: List[Dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/v1":
            return httpx.Response(200, json={"chain_id": CHAIN_ID})
        if request.method == "POST" and request.url.path == "/v1/transactions":
            index = len(self.submissions) + 1
            self.submissions.append(
                {
                    "content_type": request.headers.get("Content-Type"),
                    "body": request.content,
                }
            )
            return httpx.Response(200, json={"hash": f"0x{index:064x}"})
        if request.method == "GET" and request.url.path.startswith(
            "/v1/transactions/by_hash/"
        ):
            return httpx.Response(
                200,
                json={
                    "type": "user_transaction",
                    "success": True,
                    "vm_status": "Executed successfully",
                },
            )
        return httpx.Response(
            404,
            text=f"Unexpected request: {request.method} {request.url}",
        )


def _canonical_account() -> Account:
    private_key = PrivateKey.from_hex(PRIVATE_KEY)
    return Account(
        AccountAddress(private_key.public_key().to_evm_account_bytes()),
        private_key,
    )


def _zero_sub() -> AccountAddress:
    return AccountAddress(b"\x00" * 32)


def _orderless(variant: DexOrderlessTxVariant, inner: Any) -> DexOrderlessTx:
    return DexOrderlessTx(variant, inner)


def _raw_tx(account: Account, orderless_tx: DexOrderlessTx) -> RawTransaction:
    payload = TransactionPayload(orderless_tx)
    if (
        orderless_tx.variant == DexOrderlessTxVariant.DEX_TRANSFER
        and isinstance(orderless_tx.inner, DexTransferTx)
        and orderless_tx.inner.variant == DexTransferVariant.CROSS_TRANSFER
    ):
        return RawTransaction.create_cross_transfer_orderless(
            sender=account.account_address,
            payload=payload,
            replay_protection_nonce=CROSS_TRANSFER_REPLAY_NONCE,
            max_gas_amount=MAX_GAS,
            gas_unit_price=GAS_PRICE,
            expiration_timestamp_secs=EXPIRATION,
            chain_id=CHAIN_ID,
        )
    return RawTransaction.create_orderless(
        sender=account.account_address,
        payload=payload,
        max_gas_amount=MAX_GAS,
        gas_unit_price=GAS_PRICE,
        expiration_timestamp_secs=EXPIRATION,
        chain_id=CHAIN_ID,
    )


def _case(
    name: str,
    variant: DexOrderlessTxVariant,
    inner: Any,
    expected_payload: Dict[str, Any],
) -> JsonRequestCase:
    return JsonRequestCase(name, _orderless(variant, inner), expected_payload)


def _dex_orders_case(
    name: str,
    orders_variant: DexOrdersVariant,
    orders: List[Any],
    operation: str,
) -> JsonRequestCase:
    return _case(
        name,
        DexOrderlessTxVariant.DEX,
        DexTx(NONCE, DexOrders(orders_variant, orders), CreatedBy.USER),
        {"dex_type": "dex_payload", "operation": operation},
    )


def _place_order() -> DexPlaceOrder:
    return DexPlaceOrder(
        sub_address=_zero_sub(),
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
        slippage_tolerance_ppm=100000,
        client_order_id=CLIENT_ORDER_ID,
        stp_mode=StpMode.EXPIRE_MAKER,
    )


def _order_cases() -> List[JsonRequestCase]:
    return [
        _dex_orders_case(
            "dex_place",
            DexOrdersVariant.PLACE,
            [DexPlaceOrders([_place_order()], Grouping.NA)],
            "place",
        ),
        _dex_orders_case(
            "dex_cancel",
            DexOrdersVariant.CANCEL,
            [DexCancelOrder.by_order_id(_zero_sub(), 42, SymbolType.PERPETUAL)],
            "cancel",
        ),
        _dex_orders_case(
            "dex_replace",
            DexOrdersVariant.REPLACE,
            [
                DexReplaceOrder.by_order_id(
                    _zero_sub(),
                    42,
                    symbol_id=1,
                    symbol_type=SymbolType.PERPETUAL,
                    quantums=3000,
                    subticks=4000,
                    new_client_order_id=NEW_CLIENT_ORDER_ID,
                )
            ],
            "replace",
        ),
    ]


def _transfer_cases(account: Account) -> List[JsonRequestCase]:
    return [
        _case(
            "transfer_internal",
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(
                NONCE,
                DexTransferVariant.INTERNAL_TRANSFER,
                [
                    InternalTransferItem(
                        _zero_sub(),
                        account.account_address,
                        0,
                        1000000,
                        AccountType.PERP,
                    )
                ],
            ),
            {
                "dex_type": "dex_transfer_payload",
                "transfer_type": "internal_transfer",
            },
        ),
        _case(
            "transfer_account",
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(
                NONCE,
                DexTransferVariant.ACCOUNT_TRANSFER,
                [
                    AccountTransferItem(
                        account.account_address, 0, 2000000, AccountType.SPOT
                    )
                ],
            ),
            {
                "dex_type": "dex_transfer_payload",
                "transfer_type": "account_transfer",
            },
        ),
        _case(
            "transfer_cross_mint_with_proof",
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(
                NONCE,
                DexTransferVariant.CROSS_TRANSFER,
                [CrossTransferItem(account.account_address, 0, 1000, AccountType.PERP)],
                CrossTransferOption.MINT,
                BridgeProof(
                    b"\x01" * 32,
                    1,
                    [BridgeSignature(b"\x02" * 32, b"\x03" * 32, 27)],
                ),
            ),
            {"dex_type": "dex_transfer_payload", "transfer_type": "cross_transfer"},
        ),
        _case(
            "transfer_faucet_mint",
            DexOrderlessTxVariant.DEX_TRANSFER,
            DexTransferTx(
                NONCE,
                DexTransferVariant.FAUCET_MINT,
                [
                    CrossTransferItem(
                        account.account_address, 0, 5000000, AccountType.PERP
                    )
                ],
            ),
            {"dex_type": "dex_transfer_payload", "transfer_type": "faucet_mint"},
        ),
    ]


def _agent_cases() -> List[JsonRequestCase]:
    return [
        _case(
            "agent_approve",
            DexOrderlessTxVariant.DEX_AGENT,
            DexAgentTx(
                NONCE,
                AgentOperationVariant.APPROVE,
                AgentApprove(AGENT_NAME, AGENT_ADDRESS, AGENT_EXPIRY),
            ),
            {"dex_type": "dex_agent_payload", "agent_operation": "approve"},
        ),
        _case(
            "agent_revoke",
            DexOrderlessTxVariant.DEX_AGENT,
            DexAgentTx(NONCE, AgentOperationVariant.REVOKE, AgentRevoke(AGENT_NAME)),
            {"dex_type": "dex_agent_payload", "agent_operation": "revoke"},
        ),
    ]


def _user_config_case(
    name: str,
    variant: DexUserConfigTxVariant,
    payload: Any,
    user_config_type: str,
) -> JsonRequestCase:
    return _case(
        name,
        DexOrderlessTxVariant.DEX_USER_CONFIG,
        DexUserConfigTx(variant, payload),
        {
            "dex_type": "dex_user_config_payload",
            "user_config_type": user_config_type,
        },
    )


def _user_config_cases() -> List[JsonRequestCase]:
    return [
        _user_config_case(
            "user_set_leverage",
            DexUserConfigTxVariant.SET_USER_LEVERAGE,
            SetUserLeverage(NONCE, _zero_sub(), [UserSymbolLeverage(7, 10)]),
            "set_user_leverage",
        ),
        _user_config_case(
            "user_change_position_mode",
            DexUserConfigTxVariant.CHANGE_POSITION_MODE,
            ChangePositionMode(NONCE, _zero_sub(), OrderPositionMode.HEDGE),
            "change_position_mode",
        ),
        _user_config_case(
            "user_change_margin_mode",
            DexUserConfigTxVariant.CHANGE_MARGIN_MODE,
            ChangeMarginMode(
                NONCE, _zero_sub(), [SymbolMarginMode(7, MarginMode.ISOLATED)]
            ),
            "change_margin_mode",
        ),
        _user_config_case(
            "user_create_sub_account",
            DexUserConfigTxVariant.CREATE_SUB_ACCOUNT,
            CreateSubAccount(NONCE, "json-coverage"),
            "create_sub_account",
        ),
        _user_config_case(
            "user_modify_sub_account",
            DexUserConfigTxVariant.MODIFY_SUB_ACCOUNT,
            ModifySubAccount(
                NONCE, "json-coverage-renamed", SUBACCOUNT_ADDRESS, MASTER_ADDRESS
            ),
            "modify_sub_account",
        ),
        _user_config_case(
            "user_adjust_isolated_margin",
            DexUserConfigTxVariant.ADJUST_ISOLATED_MARGIN,
            AdjustIsolatedMargin(NONCE, _zero_sub(), 7, 500000, -250000),
            "adjust_isolated_margin",
        ),
    ]


def _vault_case(name: str, vault_tx: VaultTx, vault_type: str) -> JsonRequestCase:
    return _case(
        name,
        DexOrderlessTxVariant.VAULT,
        vault_tx,
        {"dex_type": "vault_payload", "vault_type": vault_type},
    )


def _vault_cases() -> List[JsonRequestCase]:
    return [
        _vault_case(
            "vault_create",
            VaultTx(
                VaultTxVariant.CREATE,
                VaultCreateTx(
                    NONCE,
                    86400,
                    True,
                    5000000000,
                    "coverage-vault",
                    "captured request coverage",
                ),
            ),
            "create",
        ),
        _vault_case(
            "vault_deposit",
            VaultTx(VaultTxVariant.DEPOSIT, VaultDepositTx(7, NONCE, 100000000)),
            "deposit",
        ),
        _vault_case(
            "vault_withdraw",
            VaultTx(VaultTxVariant.WITHDRAW, VaultWithdrawTx(7, NONCE, 250000)),
            "withdraw",
        ),
        _vault_case(
            "vault_distribute",
            VaultTx(VaultTxVariant.DISTRIBUTE, VaultDistributeTx(7, NONCE, 1000000)),
            "distribute",
        ),
        _vault_case(
            "vault_clp_config",
            VaultTx(
                VaultTxVariant.CLP_CONFIG,
                VaultClpConfigTx(
                    NONCE,
                    True,
                    VAULT_SUB,
                    [SymbolAccountsEntry(5, [VAULT_SUB])],
                    [ClpTraderAllowlistEntry(VAULT_SUB, [VAULT_TRADER])],
                ),
            ),
            "clp_config",
        ),
        _vault_case(
            "vault_clp_managed_account",
            VaultTx(
                VaultTxVariant.CLP_MANAGED_ACCOUNT,
                VaultClpManagedAccountTx(
                    NONCE, VAULT_SUB, ManagedAccountAction.UPSERT, "ops"
                ),
            ),
            "clp_managed_account",
        ),
        _vault_case(
            "vault_clp_trader_allowlist_update",
            VaultTx(
                VaultTxVariant.CLP_TRADER_ALLOWLIST_UPDATE,
                VaultClpTraderAllowlistUpdateTx(
                    NONCE, VAULT_SUB, ClpTraderAllowlistAction.ADD, [VAULT_TRADER]
                ),
            ),
            "clp_trader_allowlist_update",
        ),
        _vault_case(
            "vault_clp_batch_create",
            VaultTx(
                VaultTxVariant.CLP_BATCH_CREATE_MANAGED_ACCOUNTS,
                VaultClpBatchCreateManagedAccountsTx(
                    NONCE, VAULT_TRADER, 10, 5, "bot-", "batch memo"
                ),
            ),
            "clp_batch_create_managed_accounts",
        ),
        _vault_case(
            "vault_set_params",
            VaultTx(VaultTxVariant.SET_PARAMS, VaultSetParamsTx(NONCE, 7, 1000, 500)),
            "set_params",
        ),
        _vault_case(
            "vault_set_status",
            VaultTx(
                VaultTxVariant.SET_STATUS,
                VaultSetStatusTx(NONCE, 7, VaultStatus.PAUSED),
            ),
            "set_status",
        ),
    ]


def build_json_request_coverage_cases(account: Account) -> List[JsonRequestCase]:
    cases: List[JsonRequestCase] = []
    cases.extend(_order_cases())
    cases.extend(_transfer_cases(account))
    cases.extend(_agent_cases())
    cases.extend(_user_config_cases())
    cases.extend(_vault_cases())
    return cases


def _assert_expected_payload(case: JsonRequestCase, payload: Dict[str, Any]) -> None:
    for key, expected_value in case.expected_payload.items():
        actual_value = payload.get(key)
        if actual_value != expected_value:
            raise AssertionError(
                f"{case.name}: expected payload[{key!r}]={expected_value!r}, "
                f"got {actual_value!r}"
            )


def _decode_json_submission(case: JsonRequestCase, submission: Dict[str, Any]) -> dict:
    content_type = submission["content_type"]
    if content_type != MIME_JSON:
        raise AssertionError(
            f"{case.name}: expected JSON content type, got {content_type!r}"
        )
    body = json.loads(submission["body"])
    if body.get("signature", {}).get("type") != "secp256k1_ecdsa_signature":
        raise AssertionError(f"{case.name}: missing secp256k1 signature envelope")
    if "payload" not in body:
        raise AssertionError(f"{case.name}: missing payload envelope")
    _assert_expected_payload(case, body["payload"])
    return body


async def _new_captured_client(server: CapturedSubmitServer) -> RestClient:
    client = RestClient(
        "http://node/v1",
        ClientConfig(http2=False, trust_env=False, transaction_wait_in_seconds=1),
    )
    await client.client.aclose()
    client.client = httpx.AsyncClient(
        transport=httpx.MockTransport(server.handler),
        base_url="http://node",
        trust_env=False,
    )
    return client


async def run_captured_json_request_coverage() -> Dict[str, Any]:
    account = _canonical_account()
    cases = build_json_request_coverage_cases(account)
    server = CapturedSubmitServer()
    client = await _new_captured_client(server)
    try:
        await build_and_submit_dex_orderless(
            client, account, _order_cases()[0].orderless_tx
        )
        helper_submission = server.submissions[-1]
        if helper_submission["content_type"] != MIME_JSON:
            raise AssertionError(
                "build_and_submit_dex_orderless default submit did not use JSON"
            )

        cross_transfer_case = next(
            case for case in cases if case.name == "transfer_cross_mint_with_proof"
        )
        await build_and_submit_dex_orderless(
            client,
            account,
            cross_transfer_case.orderless_tx,
            replay_protection_nonce=CROSS_TRANSFER_REPLAY_NONCE,
        )
        cross_transfer_submission = server.submissions[-1]
        cross_transfer_body = _decode_json_submission(
            cross_transfer_case, cross_transfer_submission
        )
        expected_replay_nonce = str(CROSS_TRANSFER_REPLAY_NONCE)
        if cross_transfer_body.get("sequence_number") != expected_replay_nonce:
            raise AssertionError(
                "CrossTransfer helper did not sign the explicit replay nonce"
            )
        if cross_transfer_body.get("replay_protection_nonce") != expected_replay_nonce:
            raise AssertionError(
                "CrossTransfer helper did not submit the signed replay nonce"
            )
        if cross_transfer_body["payload"].get("nonce") != str(NONCE):
            raise AssertionError(
                "CrossTransfer helper changed the payload business nonce"
            )

        json_content_types: List[str] = []
        families = set()
        for case in cases:
            raw_tx = _raw_tx(account, case.orderless_tx)
            authenticator = account.sign_transaction_with_authenticator(raw_tx)
            await client.submit_transaction(raw_tx, authenticator)

            submission = server.submissions[-1]
            json_content_types.append(submission["content_type"])
            body = _decode_json_submission(case, submission)
            families.add(body["payload"]["dex_type"])

        raw_tx = _raw_tx(account, cases[0].orderless_tx)
        authenticator = account.sign_transaction_with_authenticator(raw_tx)
        await client.submit_transaction(raw_tx, authenticator, encoding="bcs")
        bcs_opt_out_content_type = server.submissions[-1]["content_type"]
        if bcs_opt_out_content_type != MIME_BCS_SIGNED_TRANSACTION:
            raise AssertionError(
                "Explicit BCS opt-out did not send the canonical BCS MIME"
            )

        return {
            "required_env": [],
            "json_case_count": len(cases),
            "case_names": [case.name for case in cases],
            "payload_families": sorted(families),
            "json_content_types": json_content_types,
            "helper_default_content_type": helper_submission["content_type"],
            "bcs_opt_out_content_type": bcs_opt_out_content_type,
        }
    finally:
        await client.close()

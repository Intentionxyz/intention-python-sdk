# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
03 - USDC Inter-Account Transfer Test (sub-account + cross-account)

Covers: CreateSubAccount, InternalTransferItem, AccountTransferItem,
      DexTransferVariant.INTERNAL_TRANSFER, DexTransferVariant.ACCOUNT_TRANSFER
Network: Required

Run: python dex-examples/03_standard_transfer.py
"""

import asyncio
import json

from _common import (
    MAIN_SUB_ADDRESS,
    TEST_ASSET_ID,
    build_and_submit_dex_orderless,
    ensure_volume,
    fetch_transaction_by_hash,
    generate_nonce,
    generate_secp256k1_account,
    get_dex_sub_accounts,
    get_faucet_url,
    get_node_url,
    normalize_address,
    print_dex_sub_accounts,
    print_header,
    print_env_info,
)

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.api.client import FaucetClient, RestClient
from intention_sdk.transactions.dex_payloads import (
    AccountTransferItem,
    CreateSubAccount,
    DexOrderlessTx,
    DexTransferTx,
    DexUserConfigTx,
    InternalTransferItem,
)
from intention_sdk.types.enums import (
    AccountType,
    DexOrderlessTxVariant,
    DexTransferVariant,
    DexUserConfigTxVariant,
)


async def print_tx_events(tx_hash: str) -> None:
    """Fetch transaction details and print events (filtering out FeeStatement)"""
    try:
        tx_data = await fetch_transaction_by_hash(tx_hash)
        events = [
            e for e in tx_data.get("events", [])
            if "FeeStatement" not in e.get("type", "")
        ]
        print(f"Transaction events ({len(events)}):")
        for e in events:
            short_type = e.get("type", "").split("::")[-1]
            print(f"  {short_type}:", json.dumps(e.get("data", {})))
    except Exception as err:
        print(f"Failed to fetch transaction events: {err}")


async def main():
    print("====================================")
    print("  03 - USDC Inter-Account Transfer Test")
    print("====================================")

    rest_client = RestClient(get_node_url())
    faucet_client = FaucetClient(get_faucet_url(), rest_client)
    alice = generate_secp256k1_account()
    bob = generate_secp256k1_account()

    print_env_info()

    # 1. Initialize two accounts and fund via faucet
    print_header("1. Initialize Accounts and Fund via Faucet")
    tx_alice = await faucet_client.fund_account(alice.account_address, 500_000_000)
    print("Alice faucet funding:", tx_alice)

    tx_bob = await faucet_client.fund_account(bob.account_address, 100_000_000)
    print("Bob faucet funding:", tx_bob)

    print("Alice:", alice.account_address)
    print("Bob:", bob.account_address)

    # 1.5 Accumulate trading volume (meet 100k USDC requirement)
    print_header("1.5 Accumulate Trading Volume (meet 100k USDC requirement)")
    await ensure_volume(rest_client, alice)
    await ensure_volume(rest_client, bob)

    # 2. Create sub-accounts for Alice and Bob
    print_header("2. Create Sub-accounts")

    print("Creating sub-account for Alice...")
    create_sub_alice = CreateSubAccount(generate_nonce(), "AliceSub1")
    config_tx_alice = DexUserConfigTx(DexUserConfigTxVariant.CREATE_SUB_ACCOUNT, create_sub_alice)
    orderless_alice_sub = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx_alice)
    result_alice_sub = await build_and_submit_dex_orderless(rest_client, alice, orderless_alice_sub)
    print(
        "Alice create sub-account:",
        "SUCCESS" if result_alice_sub["success"] else "FAILED",
        "hash:", result_alice_sub["hash"],
    )

    print("Creating sub-account for Bob...")
    create_sub_bob = CreateSubAccount(generate_nonce(), "BobSub1")
    config_tx_bob = DexUserConfigTx(DexUserConfigTxVariant.CREATE_SUB_ACCOUNT, create_sub_bob)
    orderless_bob_sub = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx_bob)
    result_bob_sub = await build_and_submit_dex_orderless(rest_client, bob, orderless_bob_sub)
    print(
        "Bob create sub-account:",
        "SUCCESS" if result_bob_sub["success"] else "FAILED",
        "hash:", result_bob_sub["hash"],
    )

    # 3. Query balances after creating sub-accounts
    print_header("3. Balances After Creating Sub-accounts")
    alice_addr = str(alice.account_address)
    bob_addr = str(bob.account_address)

    print("Alice DEX sub-accounts:")
    alice_subs = await get_dex_sub_accounts(alice_addr)
    print_dex_sub_accounts(alice_subs)
    print("Bob DEX sub-accounts:")
    bob_subs = await get_dex_sub_accounts(bob_addr)
    print_dex_sub_accounts(bob_subs)

    # Find Alice's non-main sub-account address
    MAIN_ADDR_STR = "0x0000000000000000000000000000000000000000"
    alice_sub_account = next(
        (s for s in alice_subs if s.get("sub_address") != MAIN_ADDR_STR),
        None,
    )
    if not alice_sub_account:
        raise RuntimeError("Alice sub-account not found, please verify sub-account creation succeeded")
    alice_sub_address = AccountAddress.from_str(normalize_address(alice_sub_account["sub_address"]))

    # 4. Main account -> sub-account deposit 200 USDC (InternalTransfer)
    DEPOSIT_AMOUNT = 200_000_000  # 200 USDC
    print_header(f"4. Alice Main Account -> Sub-account Deposit {DEPOSIT_AMOUNT // 1_000_000} USDC")
    print("From (main account):", MAIN_SUB_ADDRESS)
    print("To (sub-account):", alice_sub_address)
    print("Amount:", DEPOSIT_AMOUNT, "quantums =", DEPOSIT_AMOUNT / 1_000_000, "USDC")

    deposit_item = InternalTransferItem(
        from_subaddress=MAIN_SUB_ADDRESS,
        to_subaddress=alice_sub_address,
        asset_id=TEST_ASSET_ID,
        amount=DEPOSIT_AMOUNT,
        account_type=AccountType.SPOT,
    )
    deposit_tx = DexTransferTx(generate_nonce(), DexTransferVariant.INTERNAL_TRANSFER, [deposit_item])
    deposit_orderless = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, deposit_tx)
    deposit_result = await build_and_submit_dex_orderless(rest_client, alice, deposit_orderless)
    print("Tx hash:", deposit_result["hash"])
    print("Status:", "SUCCESS" if deposit_result["success"] else "FAILED")
    if deposit_result["success"]:
        await print_tx_events(deposit_result["hash"])

    # 4.1 Query balance after deposit
    print_header("4.1 Balance After Main -> Sub-account Deposit")
    print("Alice DEX sub-accounts:")
    print_dex_sub_accounts(await get_dex_sub_accounts(alice_addr))

    # 5. Sub-account -> main account withdraw 50 USDC (InternalTransfer)
    WITHDRAW_AMOUNT = 50_000_000  # 50 USDC
    print_header(f"5. Alice Sub-account -> Main Account Withdraw {WITHDRAW_AMOUNT // 1_000_000} USDC")
    print("From (sub-account):", alice_sub_address)
    print("To (main account):", MAIN_SUB_ADDRESS)

    withdraw_item = InternalTransferItem(
        from_subaddress=alice_sub_address,
        to_subaddress=MAIN_SUB_ADDRESS,
        asset_id=TEST_ASSET_ID,
        amount=WITHDRAW_AMOUNT,
        account_type=AccountType.SPOT,
    )
    withdraw_tx = DexTransferTx(generate_nonce(), DexTransferVariant.INTERNAL_TRANSFER, [withdraw_item])
    withdraw_orderless = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, withdraw_tx)
    withdraw_result = await build_and_submit_dex_orderless(rest_client, alice, withdraw_orderless)
    print("Tx hash:", withdraw_result["hash"])
    print("Status:", "SUCCESS" if withdraw_result["success"] else "FAILED")
    if withdraw_result["success"]:
        await print_tx_events(withdraw_result["hash"])

    # 5.1 Query balance after withdrawal
    print_header("5.1 Balance After Sub-account -> Main Account Withdrawal")
    print("Alice DEX sub-accounts:")
    print_dex_sub_accounts(await get_dex_sub_accounts(alice_addr))

    # 6. Alice -> Bob cross-account transfer 100 USDC (AccountTransfer)
    TRANSFER_AMOUNT_1 = 100_000_000  # 100 USDC
    print_header(f"6. Alice -> Bob Cross-Account Transfer {TRANSFER_AMOUNT_1 // 1_000_000} USDC")
    print("Sender: Alice", alice.account_address)
    print("Receiver: Bob", bob.account_address)
    print("Amount:", TRANSFER_AMOUNT_1, "quantums =", TRANSFER_AMOUNT_1 / 1_000_000, "USDC")

    transfer_item_1 = AccountTransferItem(
        to_account=bob.account_address,
        asset_id=TEST_ASSET_ID,
        amount=TRANSFER_AMOUNT_1,
        account_type=AccountType.PERP,
    )
    transfer_tx_1 = DexTransferTx(generate_nonce(), DexTransferVariant.ACCOUNT_TRANSFER, [transfer_item_1])
    orderless_tx_1 = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, transfer_tx_1)
    result_1 = await build_and_submit_dex_orderless(rest_client, alice, orderless_tx_1)
    print("Tx hash:", result_1["hash"])
    print("Status:", "SUCCESS" if result_1["success"] else "FAILED")
    if result_1["success"]:
        await print_tx_events(result_1["hash"])

    # 6.1 Query balance after transfer
    print_header("6.1 Balance After Cross-Account Transfer")
    print("Alice DEX sub-accounts:")
    print_dex_sub_accounts(await get_dex_sub_accounts(alice_addr))
    print("Bob DEX sub-accounts:")
    print_dex_sub_accounts(await get_dex_sub_accounts(bob_addr))

    # 7. Bob -> Alice transfer back 50 USDC (AccountTransfer)
    TRANSFER_AMOUNT_2 = 50_000_000  # 50 USDC
    print_header(f"7. Bob -> Alice Transfer Back {TRANSFER_AMOUNT_2 // 1_000_000} USDC")
    print("Sender: Bob", bob.account_address)
    print("Receiver: Alice", alice.account_address)
    print("Amount:", TRANSFER_AMOUNT_2, "quantums =", TRANSFER_AMOUNT_2 / 1_000_000, "USDC")

    transfer_item_2 = AccountTransferItem(
        to_account=alice.account_address,
        asset_id=TEST_ASSET_ID,
        amount=TRANSFER_AMOUNT_2,
        account_type=AccountType.PERP,
    )
    transfer_tx_2 = DexTransferTx(generate_nonce(), DexTransferVariant.ACCOUNT_TRANSFER, [transfer_item_2])
    orderless_tx_2 = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, transfer_tx_2)
    result_2 = await build_and_submit_dex_orderless(rest_client, bob, orderless_tx_2)
    print("Tx hash:", result_2["hash"])
    print("Status:", "SUCCESS" if result_2["success"] else "FAILED")
    if result_2["success"]:
        await print_tx_events(result_2["hash"])

    # 8. Final balance summary
    print_header("8. Final Balance Summary")
    print("Alice DEX sub-accounts:")
    print_dex_sub_accounts(await get_dex_sub_accounts(alice_addr))
    print("Bob DEX sub-accounts:")
    print_dex_sub_accounts(await get_dex_sub_accounts(bob_addr))

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

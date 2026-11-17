# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
09 - DEX Sub-account Transfer Test

Covers: DexTransferTx, InternalTransferItem, DexTransferVariant,
      CrossTransferItem, CrossTransferOption, CreateSubAccount

Run: python dex-examples/09_dex_transfer.py
"""

import asyncio

from _common import (
    MAIN_SUB_ADDRESS,
    TEST_ASSET_ID,
    TEST_SUBACCOUNT_ID,
    build_and_submit_dex_orderless,
    ensure_volume,
    generate_nonce,
    get_dex_sub_accounts,
    get_node_url,
    get_or_create_account,
    normalize_address,
    print_env_info,
    print_header,
    print_live_example_intro,
)

from intention_sdk.core.account_address import AccountAddress
from intention_sdk.api.client import RestClient
from intention_sdk.transactions.dex_payloads import (
    CreateSubAccount,
    CrossTransferItem,
    DexOrderlessTx,
    DexTransferTx,
    DexUserConfigTx,
    InternalTransferItem,
)
from intention_sdk.types.enums import (
    AccountType,
    CrossTransferOption,
    DexOrderlessTxVariant,
    DexTransferVariant,
    DexUserConfigTxVariant,
)


async def main():
    print("====================================")
    print("  09 - DEX Sub-account Transfer Test")
    print("====================================")
    print_live_example_intro(
        "dex transfer",
        optional_envs=["PRIVATE_KEY", "TEST_ASSET_ID", "TEST_SUBACCOUNT_ID"],
        notes=[
            "This script is a live example. It proves the updated transfer API shape, not a deterministic offline flow.",
            "Cross-chain mint/burn sections are best-effort and may require admin permissions on the target network.",
        ],
    )
    print_env_info()

    rest_client = RestClient(get_node_url())
    account = await get_or_create_account(rest_client)
    account_addr = str(account.account_address)
    main_addr_str = "0x0000000000000000000000000000000000000000"

    print("Main account address:", account.account_address)
    print("Main sub-address:", MAIN_SUB_ADDRESS)
    print("Asset ID:", TEST_ASSET_ID, "(default USDC, overridable via TEST_ASSET_ID)")

    # 0. Accumulate trading volume
    print_header("Accumulate Trading Volume")
    try:
        await ensure_volume(rest_client, account)
    except RuntimeError as err:
        print("Skipping remaining live transfer operations.")
        print("Reason:", err)
        print(
            "This indicates a live environment precondition is missing, not a transfer schema regression."
        )
        await rest_client.close()
        return

    # 0.5 Create sub-accounts first
    print_header("Create Sub-accounts")

    for sub_id in [TEST_SUBACCOUNT_ID, TEST_SUBACCOUNT_ID + 1]:
        create_sub = CreateSubAccount(generate_nonce(), f"Sub{sub_id}")
        config_tx = DexUserConfigTx(
            DexUserConfigTxVariant.CREATE_SUB_ACCOUNT, create_sub
        )
        orderless = DexOrderlessTx(DexOrderlessTxVariant.DEX_USER_CONFIG, config_tx)
        res = await build_and_submit_dex_orderless(rest_client, account, orderless)
        print(
            f"Create sub-account {sub_id}:",
            "SUCCESS" if res["success"] else "FAILED",
            "hash:",
            res["hash"],
        )

    # Query actual sub-account addresses from chain
    subs = await get_dex_sub_accounts(account_addr)
    non_main_subs = [s for s in subs if s.get("sub_address") != main_addr_str]
    if len(non_main_subs) < 2:
        print(
            f"Error: need at least 2 sub-accounts, but only found {len(non_main_subs)}"
        )
        await rest_client.close()
        return

    sub_address1 = AccountAddress.from_str(
        normalize_address(non_main_subs[0]["sub_address"])
    )
    sub_address2 = AccountAddress.from_str(
        normalize_address(non_main_subs[1]["sub_address"])
    )
    print(f"Sub-account 1 address: {sub_address1}")
    print(f"Sub-account 2 address: {sub_address2}")

    # 1. Deposit to sub-account -- main account -> sub-account
    print_header("Deposit to Sub-account 1")

    nonce1 = generate_nonce()
    deposit_item = InternalTransferItem(
        from_subaddress=MAIN_SUB_ADDRESS,
        to_subaddress=sub_address1,
        asset_id=TEST_ASSET_ID,
        amount=1000000,
        account_type=AccountType.SPOT,
    )

    deposit_tx = DexTransferTx(
        nonce1, DexTransferVariant.INTERNAL_TRANSFER, [deposit_item]
    )

    print("Deposit params:")
    print("  from:", MAIN_SUB_ADDRESS, "(main account)")
    print("  to:", sub_address1, "(sub-account 1)")
    print("  Asset ID:", TEST_ASSET_ID)
    print("  Amount: 1000000")

    orderless_tx1 = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, deposit_tx)
    result1 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx1)
    print(
        "Deposit result:",
        result1["hash"],
        "SUCCESS" if result1["success"] else "FAILED",
    )

    # 2. Withdraw from sub-account -- sub-account -> main account
    print_header("Withdraw from Sub-account 1 to Main Account")

    nonce2 = generate_nonce()
    withdraw_item = InternalTransferItem(
        from_subaddress=sub_address1,
        to_subaddress=MAIN_SUB_ADDRESS,
        asset_id=TEST_ASSET_ID,
        amount=500000,
        account_type=AccountType.SPOT,
    )

    withdraw_tx = DexTransferTx(
        nonce2, DexTransferVariant.INTERNAL_TRANSFER, [withdraw_item]
    )

    print("Withdraw params:")
    print("  from:", sub_address1, "(sub-account 1)")
    print("  to:", MAIN_SUB_ADDRESS, "(main account)")
    print("  Amount: 500000")

    orderless_tx2 = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, withdraw_tx)
    result2 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx2)
    print(
        "Withdraw result:",
        result2["hash"],
        "SUCCESS" if result2["success"] else "FAILED",
    )

    # 3. Inter-sub-account transfer
    print_header("Sub-account 1 -> Sub-account 2 Transfer")

    nonce3 = generate_nonce()
    transfer_item = InternalTransferItem(
        from_subaddress=sub_address1,
        to_subaddress=sub_address2,
        asset_id=TEST_ASSET_ID,
        amount=200000,
        account_type=AccountType.SPOT,
    )

    transfer_tx = DexTransferTx(
        nonce3, DexTransferVariant.INTERNAL_TRANSFER, [transfer_item]
    )

    print("Transfer params:")
    print("  from: Sub-account 1")
    print("  to: Sub-account 2")
    print("  Amount: 200000")

    orderless_tx3 = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, transfer_tx)
    result3 = await build_and_submit_dex_orderless(rest_client, account, orderless_tx3)
    print(
        "Transfer result:",
        result3["hash"],
        "SUCCESS" if result3["success"] else "FAILED",
    )

    # 4. Cross-chain deposit -- CrossTransfer (Mint)
    print_header("Cross-chain Deposit (CrossTransfer Mint)")
    print("Note: CrossTransfer may require admin permissions, regular users may fail")

    try:
        nonce5 = generate_nonce()
        mint_item = CrossTransferItem(
            to_account=MAIN_SUB_ADDRESS,
            asset_id=TEST_ASSET_ID,
            amount=1000000,
            account_type=AccountType.SPOT,
        )

        mint_tx = DexTransferTx(nonce5, DexTransferVariant.FAUCET_MINT, [mint_item])

        print("Deposit params:")
        print("  to:", MAIN_SUB_ADDRESS, "(main account)")
        print("  asset_id:", TEST_ASSET_ID)
        print("  amount: 1000000")
        print("  variant: FaucetMint")

        orderless_tx5 = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, mint_tx)
        result5 = await build_and_submit_dex_orderless(
            rest_client, account, orderless_tx5
        )
        print(
            "FaucetMint:",
            result5["hash"],
            "SUCCESS" if result5["success"] else "FAILED",
        )
    except Exception as err:
        print(f"FaucetMint failed (may require admin permissions): {err}")

    # 5. Cross-chain withdrawal -- CrossTransfer (Burn)
    print_header("Cross-chain Withdrawal (CrossTransfer Burn)")
    print("Note: CrossTransfer may require admin permissions, regular users may fail")

    try:
        nonce6 = generate_nonce()
        replay_nonce6 = generate_nonce()
        burn_item = CrossTransferItem(
            to_account=MAIN_SUB_ADDRESS,
            asset_id=TEST_ASSET_ID,
            amount=500000,
            account_type=AccountType.SPOT,
        )

        burn_tx = DexTransferTx(
            nonce6,
            DexTransferVariant.CROSS_TRANSFER,
            [burn_item],
            CrossTransferOption.BURN,
        )

        print("Withdrawal params:")
        print("  from:", MAIN_SUB_ADDRESS, "(main account)")
        print("  asset_id:", TEST_ASSET_ID)
        print("  amount: 500000")
        print("  option: Burn (cross-chain withdrawal)")
        print("  replay nonce:", replay_nonce6)

        orderless_tx6 = DexOrderlessTx(DexOrderlessTxVariant.DEX_TRANSFER, burn_tx)
        result6 = await build_and_submit_dex_orderless(
            rest_client,
            account,
            orderless_tx6,
            replay_protection_nonce=replay_nonce6,
        )
        print(
            "CrossTransfer Burn:",
            result6["hash"],
            "SUCCESS" if result6["success"] else "FAILED",
        )
    except Exception as err:
        print(f"CrossTransfer Burn failed (may require admin permissions): {err}")

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

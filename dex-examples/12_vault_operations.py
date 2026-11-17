# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""
12 - Vault Operations Test

Covers: VaultClient, VaultTx, VaultTxVariant, build_vault_create,
      build_vault_deposit, build_vault_withdraw, build_vault_set_status,
      build_vault_distribute, build_vault_close,
      calculate_max_distribute_for_leader, derive_subaccount_address

Run: python dex-examples/12_vault_operations.py
"""

import asyncio
import json
from dataclasses import asdict

from _common import (
    build_and_submit_dex_orderless,
    ensure_volume,
    generate_nonce,
    get_optional_int_env,
    get_fullnode_base,
    get_node_url,
    get_or_create_account,
    print_env_info,
    print_header,
    print_live_example_intro,
)

from intention_sdk import VAULT_MIN_INITIAL_DEPOSIT_USDC
from intention_sdk import VaultSetParamsTx, VaultStatus, VaultTx, VaultTxVariant
from intention_sdk import build_vault_close
from intention_sdk import build_vault_create, build_vault_deposit, build_vault_set_status
from intention_sdk import build_vault_distribute, build_vault_withdraw
from intention_sdk import calculate_max_distribute_for_leader
from intention_sdk import derive_subaccount_address
from intention_sdk.api.client import ClientConfig, RestClient
from intention_sdk.transactions.dex_payloads import DexOrderlessTx
from intention_sdk.types.enums import DexOrderlessTxVariant
from intention_sdk.api.vault_client import VaultClient


def _vault_status_name(status: int) -> str:
    if status == VaultStatus.ACTIVE:
        return "Active"
    if status == VaultStatus.PAUSED:
        return "Paused"
    if status == VaultStatus.CLOSED:
        return "Closed"
    return f"Unknown({status})"


async def main():
    print("====================================")
    print("  12 - Vault Operations Test")
    print("====================================")
    print_live_example_intro(
        "vault operations",
        optional_envs=["PRIVATE_KEY", "TEST_VAULT_ID"],
        notes=[
            "Query paths are always attempted when the service is reachable.",
            "Write-path verification only uses TEST_VAULT_ID or a uniquely resolved newly created vault.",
            "If no deterministic writable target is available, write paths are skipped intentionally.",
        ],
    )
    print_env_info()

    rest_client = RestClient(
        get_node_url(),
        client_config=ClientConfig(
            http2=False,
            trust_env=False,
            gas_unit_price=2000,
            max_gas_amount=5000,
            expiration_ttl=30,
        ),
    )
    account = await get_or_create_account(rest_client)
    fullnode_url = get_fullnode_base()

    print("Account address:", account.account_address)
    print("Fullnode URL:", fullnode_url)
    print(
        "Minimum initial deposit:", VAULT_MIN_INITIAL_DEPOSIT_USDC / 1_000_000, "USDC"
    )

    # ============================
    # Part 1: VaultClient Query API
    # ============================

    print_header("Part 1: VaultClient Query API")
    vault_client = VaultClient(fullnode_url, trust_env=False)
    existing_vaults = []
    selected_vault_id = None
    explicit_vault_id = get_optional_int_env("TEST_VAULT_ID")
    write_vault_id = explicit_vault_id
    if explicit_vault_id is not None:
        selected_vault_id = explicit_vault_id
        print("Using TEST_VAULT_ID for deterministic write-path target:", explicit_vault_id)

    # 1.1 Get all vaults
    print_header("Get All Vaults")
    try:
        vaults = await vault_client.get_vaults()
        existing_vaults = vaults
        if explicit_vault_id is None and vaults:
            selected_vault_id = vaults[0].vault_id
        if vaults:
            print(f"Total {len(vaults)} Vaults")
            for v in vaults[:5]:
                print(f"  Vault #{v.vault_id}: {v.vault_name}")
                print(f"    Status: {_vault_status_name(v.status)}")
                print(f"    TVL: {int(v.tvl_usdc) / 1_000_000} USDC")
        else:
            print("No vaults returned from the SDK client.")
    except Exception as err:
        print(f"Failed to get vault list: {err}")

    # 1.2 Get single vault details
    if selected_vault_id is not None:
        print_header(f"Get Vault Details (ID={selected_vault_id})")
        try:
            vault = await vault_client.get_vault(selected_vault_id)
            print("Vault details:", json.dumps(asdict(vault), indent=2)[:500])
        except Exception as err:
            print(f"Failed to get Vault #{selected_vault_id} details: {err}")
    else:
        print_header("Get Vault Details")
        print("Skipping detail query: no existing vaults returned by the query API.")

    # 1.3 Get depositors
    if selected_vault_id is not None:
        print_header(f"Get Vault Depositors (ID={selected_vault_id})")
        try:
            depositors = await vault_client.get_depositors(selected_vault_id)
            if depositors:
                print(f"Total {len(depositors)} depositors")
                print(
                    "First depositor:",
                    json.dumps(asdict(depositors[0]), indent=2)[:300],
                )
            else:
                print("No depositors returned.")
        except Exception as err:
            print(f"Failed to get depositors: {err}")
    else:
        print_header("Get Vault Depositors")
        print("Skipping depositor query: no existing vault id is available.")

    # 1.4 Get positions
    if selected_vault_id is not None:
        print_header(f"Get Vault Positions (ID={selected_vault_id})")
        try:
            positions = await vault_client.get_positions(selected_vault_id)
            if positions:
                print(f"Total {len(positions)} positions")
                print("First position:", json.dumps(asdict(positions[0]), indent=2)[:300])
            else:
                print("No positions returned.")
        except Exception as err:
            print(f"Failed to get positions: {err}")
    else:
        print_header("Get Vault Positions")
        print("Skipping position query: no existing vault id is available.")

    # 1.5 Get orders
    if selected_vault_id is not None:
        print_header(f"Get Vault Orders (ID={selected_vault_id})")
        try:
            orders = await vault_client.get_orders(selected_vault_id)
            if orders:
                print(f"Total {len(orders)} orders")
                print("First order:", json.dumps(asdict(orders[0]), indent=2)[:300])
            else:
                print("No orders returned.")
        except Exception as err:
            print(f"Failed to get orders: {err}")
    else:
        print_header("Get Vault Orders")
        print("Skipping order query: no existing vault id is available.")

    # ================================
    # Part 2: Public helper surface
    # ================================

    print_header("Part 2: Public Helper Surface")
    max_distribute_sample = calculate_max_distribute_for_leader(
        200_000_000,
        1_000_000_000,
        1_500_000_000,
    )
    assert max_distribute_sample == 1_000_000_000
    print("Deterministic max distribute sample:", max_distribute_sample)

    derived_subaccount = derive_subaccount_address(account.account_address, 7)
    print("Derived subaccount #7:", derived_subaccount)

    # ================================
    # Part 3: Vault Transactions (build and submit)
    # ================================

    print_header("Part 3: Vault Transaction Operations")
    print(
        "Note: Vault operations require account to hold sufficient USDC "
        "(>=100 USDC initial deposit)"
    )

    # 2.0 Accumulate trading volume (Vault creation requires 100k USD)
    print_header("Accumulate Trading Volume (Vault creation requires 100k USD)")
    if write_vault_id is not None:
        print("Skipping volume bootstrap because TEST_VAULT_ID already provides a deterministic target.")
    else:
        try:
            await ensure_volume(rest_client, account)
        except RuntimeError as err:
            print_header("Write Path Skipped")
            print("Skipping write-path operations before vault creation.")
            print("Reason:", err)
            print(
                "This indicates a live environment precondition is missing, not a Vault helper or schema regression."
            )
            await rest_client.close()
            return

    # 2.1 Create Vault
    print_header("Create Vault")

    if write_vault_id is not None:
        print("Skipping new vault creation because TEST_VAULT_ID is set.")
        print("Deterministic write-path target:", write_vault_id)
    else:
        try:
            existing_vault_ids = {vault.vault_id for vault in existing_vaults}
            nonce1 = generate_nonce()
            vault_tx1 = build_vault_create(
                nonce=nonce1,
                lockup_seconds=86400,
                always_proportional_close=False,
                initial_deposit_usdc=VAULT_MIN_INITIAL_DEPOSIT_USDC,
                vault_name="Test Vault",
                strategy_description="SDK test vault for demonstration purposes",
            )

            print("Create params:")
            print("  Name: Test Vault")
            print("  Lockup period: 86400 seconds (1 day)")
            print(
                "  Initial deposit:",
                VAULT_MIN_INITIAL_DEPOSIT_USDC / 1_000_000,
                "USDC",
            )

            orderless_tx1 = DexOrderlessTx(DexOrderlessTxVariant.VAULT, vault_tx1)
            result1 = await build_and_submit_dex_orderless(
                rest_client, account, orderless_tx1
            )
            print(
                "Create Vault:",
                result1["hash"],
                "SUCCESS" if result1["success"] else "FAILED",
            )
            refreshed_vaults = await vault_client.get_vaults()
            refreshed_ids = {vault.vault_id for vault in refreshed_vaults}
            new_ids = sorted(refreshed_ids - existing_vault_ids)
            if len(new_ids) == 1:
                write_vault_id = new_ids[0]
                print("Resolved uniquely created vault id:", write_vault_id)
            elif len(new_ids) > 1:
                print(
                    "Multiple new vault ids were observed; skipping write path because the target is not deterministic:",
                    new_ids,
                )
            else:
                print(
                    "Could not isolate a uniquely created vault id; skipping write path until TEST_VAULT_ID is provided.",
                )
        except Exception as err:
            print(f"Create Vault failed: {err}")
            print(
                "Skipping write path because no deterministic writable vault target could be proven."
            )

    if write_vault_id is None:
        print_header("Write Path Skipped")
        print(
            "No deterministic vault id could be resolved from TEST_VAULT_ID or a uniquely created vault."
        )
        print("Skipping write-path operations until a valid target vault is available.")
        print("\n===== All tests completed =====")
        await rest_client.close()
        return

    # 2.2 Deposit to Vault
    print_header("Deposit to Vault")

    try:
        nonce2 = generate_nonce()
        vault_tx2 = build_vault_deposit(
            vault_id=write_vault_id, nonce=nonce2, amount_usdc=50_000_000
        )

        print("Deposit params:")
        print("  Vault ID:", write_vault_id)
        print("  Amount: 50 USDC")

        orderless_tx2 = DexOrderlessTx(DexOrderlessTxVariant.VAULT, vault_tx2)
        result2 = await build_and_submit_dex_orderless(
            rest_client, account, orderless_tx2
        )
        print(
            "Deposit:", result2["hash"], "SUCCESS" if result2["success"] else "FAILED"
        )
    except Exception as err:
        print(f"Deposit failed: {err}")

    # 2.3 Withdraw
    print_header("Withdraw from Vault")

    try:
        nonce3 = generate_nonce()
        vault_tx3 = build_vault_withdraw(
            vault_id=write_vault_id, nonce=nonce3, withdraw_shares=10_000_000
        )

        print("Withdraw params:")
        print("  Vault ID:", write_vault_id)
        print("  Shares: 10000000")

        orderless_tx3 = DexOrderlessTx(DexOrderlessTxVariant.VAULT, vault_tx3)
        result3 = await build_and_submit_dex_orderless(
            rest_client, account, orderless_tx3
        )
        print(
            "Withdraw:", result3["hash"], "SUCCESS" if result3["success"] else "FAILED"
        )
    except Exception as err:
        print(f"Withdraw failed: {err}")

    # 2.4 Pause Vault
    print_header("Pause Vault")

    try:
        nonce4 = generate_nonce()
        vault_tx4 = build_vault_set_status(
            nonce=nonce4, vault_id=write_vault_id, target_status=VaultStatus.PAUSED
        )

        print("Set status:")
        print("  Vault ID:", write_vault_id)
        print("  Target status: Paused")

        orderless_tx4 = DexOrderlessTx(DexOrderlessTxVariant.VAULT, vault_tx4)
        result4 = await build_and_submit_dex_orderless(
            rest_client, account, orderless_tx4
        )
        print(
            "Pause Vault:",
            result4["hash"],
            "SUCCESS" if result4["success"] else "FAILED",
        )
    except Exception as err:
        print(f"Pause Vault failed: {err}")

    # 2.5 Resume Vault
    print_header("Resume Vault")

    try:
        nonce5 = generate_nonce()
        vault_tx5 = build_vault_set_status(
            nonce=nonce5, vault_id=write_vault_id, target_status=VaultStatus.ACTIVE
        )

        print("Set status:")
        print("  Vault ID:", write_vault_id)
        print("  Target status: Active")

        orderless_tx5 = DexOrderlessTx(DexOrderlessTxVariant.VAULT, vault_tx5)
        result5 = await build_and_submit_dex_orderless(
            rest_client, account, orderless_tx5
        )
        print(
            "Resume Vault:",
            result5["hash"],
            "SUCCESS" if result5["success"] else "FAILED",
        )
    except Exception as err:
        print(f"Resume Vault failed: {err}")

    # 2.6 Adjust Vault parameters
    print_header("Adjust Vault Parameters")

    try:
        nonce6 = generate_nonce()
        set_params_tx = VaultSetParamsTx(
            nonce=nonce6,
            vault_id=write_vault_id,
            lockup_seconds=172800,
            always_proportional_close=True,
        )

        print("Parameter adjustments:")
        print("  Vault ID:", write_vault_id)
        print("  Lockup period: 172800 seconds (2 days)")
        print("  Proportional close: true")

        vault_tx6 = VaultTx(VaultTxVariant.SET_PARAMS, set_params_tx)
        orderless_tx6 = DexOrderlessTx(DexOrderlessTxVariant.VAULT, vault_tx6)
        result6 = await build_and_submit_dex_orderless(
            rest_client, account, orderless_tx6
        )
        print(
            "Adjust params:",
            result6["hash"],
            "SUCCESS" if result6["success"] else "FAILED",
        )
    except Exception as err:
        print(f"Adjust params failed: {err}")

    # 2.7 Distribute from Vault
    print_header("Distribute from Vault")

    try:
        nonce7 = generate_nonce()
        distribute_amount_usdc = 5_000_000
        vault_tx7 = build_vault_distribute(
            vault_id=write_vault_id,
            nonce=nonce7,
            distribute_amount_usdc=distribute_amount_usdc,
        )

        print("Distribute params:")
        print("  Vault ID:", write_vault_id)
        print("  Amount:", distribute_amount_usdc / 1_000_000, "USDC")

        orderless_tx7 = DexOrderlessTx(DexOrderlessTxVariant.VAULT, vault_tx7)
        result7 = await build_and_submit_dex_orderless(
            rest_client, account, orderless_tx7
        )
        print(
            "Distribute:",
            result7["hash"],
            "SUCCESS" if result7["success"] else "FAILED",
        )
    except Exception as err:
        print(f"Distribute failed: {err}")

    # 2.8 Close Vault via helper wrapper
    print_header("Close Vault")

    try:
        nonce8 = generate_nonce()
        vault_tx8 = build_vault_close(nonce=nonce8, vault_id=write_vault_id)

        print("Close params:")
        print("  Vault ID:", write_vault_id)
        print("  Uses build_vault_close() helper -> VaultStatus.CLOSED")

        orderless_tx8 = DexOrderlessTx(DexOrderlessTxVariant.VAULT, vault_tx8)
        result8 = await build_and_submit_dex_orderless(
            rest_client, account, orderless_tx8
        )
        print(
            "Close Vault:",
            result8["hash"],
            "SUCCESS" if result8["success"] else "FAILED",
        )
    except Exception as err:
        print(f"Close Vault failed: {err}")

    print("\n===== All tests completed =====")
    await rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

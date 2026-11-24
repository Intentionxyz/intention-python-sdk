# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Transfer USDC between subaccounts and optionally withdraw on the test bridge."""

import asyncio
import os

from intention_sdk import AccountAddress
from intention_sdk.core.address_utils import MAIN_SUB_ADDRESS

from _common import TEST_ASSET_ID, get_node_url, load_account_from_env
from account_client_usage import create_account_client, create_subaccount_example


async def main() -> None:
    destination = os.getenv("BRIDGE_DESTINATION")
    bridge_address = (
        AccountAddress.from_str_relaxed(destination) if destination else None
    )
    account = create_account_client(
        signer=load_account_from_env(), node_url=get_node_url()
    )
    try:
        # Supply a funded account that is eligible to create two subaccounts.
        first = await create_subaccount_example(account, "source")
        second = await create_subaccount_example(account, "target")
        if first is None or second is None:
            raise RuntimeError("Transaction did not emit CreateSubAccountEvent")

        for source, target, amount in (
            (MAIN_SUB_ADDRESS, first, "1"),
            (first, MAIN_SUB_ADDRESS, "0.5"),
            (first, second, "0.2"),
        ):
            result = await account.transfer_between_subaccounts(
                source, target, amount=amount, asset_id=TEST_ASSET_ID
            )
            print("Transferred", amount, "USDC:", result.hash)

        if bridge_address is not None:
            withdrawal = await account.bridge_withdraw(
                [
                    {
                        "destination": bridge_address,
                        "amount": os.getenv("BRIDGE_WITHDRAW_AMOUNT", "10"),
                        "asset_id": TEST_ASSET_ID,
                    }
                ]
            )
            print("Test bridge withdrawal submitted:", withdrawal.hash)
    finally:
        await account.executor.rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

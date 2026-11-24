# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Transfer USDC into a subaccount and between two funded test signers."""

import asyncio

from intention_sdk import AccountType
from intention_sdk.core.address_utils import MAIN_SUB_ADDRESS

from _common import TEST_ASSET_ID, get_node_url, load_account_from_env
from account_client_usage import create_account_client, create_subaccount_example


async def main() -> None:
    alice_signer = load_account_from_env()
    bob_signer = load_account_from_env("RECIPIENT_PRIVATE_KEY")
    if alice_signer.account_address == bob_signer.account_address:
        raise ValueError(
            "PRIVATE_KEY and RECIPIENT_PRIVATE_KEY must be distinct test signers"
        )

    alice = create_account_client(signer=alice_signer, node_url=get_node_url())
    bob = create_account_client(signer=bob_signer, node_url=get_node_url())
    try:
        # Alice's main account must meet the chain's subaccount creation threshold.
        sub_address = await create_subaccount_example(alice, "alice-trading")
        if sub_address is None:
            raise RuntimeError("Transaction did not emit CreateSubAccountEvent")
        print("Alice's trading subaccount:", sub_address)

        deposit = await alice.transfer_between_subaccounts(
            MAIN_SUB_ADDRESS, sub_address, amount="200", asset_id=TEST_ASSET_ID
        )
        print("Deposited into subaccount:", deposit.hash)
        withdraw = await alice.transfer_between_subaccounts(
            sub_address, MAIN_SUB_ADDRESS, amount="50", asset_id=TEST_ASSET_ID
        )
        print("Withdrawn to main account:", withdraw.hash)

        sent = await alice.transfer_to_account(
            bob_signer.account_address,
            amount="100",
            asset_id=TEST_ASSET_ID,
            account_type=AccountType.PERP,
        )
        print("Transferred to Bob:", sent.hash)
        returned = await bob.transfer_to_account(
            alice_signer.account_address,
            amount="50",
            asset_id=TEST_ASSET_ID,
            account_type=AccountType.PERP,
        )
        print("Transferred back to Alice:", returned.hash)
    finally:
        await alice.executor.rest_client.close()
        await bob.executor.rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

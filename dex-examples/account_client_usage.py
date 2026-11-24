# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""AccountClient usage corresponding to the TypeScript account client example."""

from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from intention_sdk import (
    Account,
    AccountAddress,
    AccountClient,
    ClientConfig,
    DexTransactionExecutor,
    RestClient,
    decode_create_sub_account_event,
)
from intention_sdk.core.address_utils import MAIN_SUB_ADDRESS


def create_account_client(*, signer: Account, node_url: str) -> AccountClient:
    rest_client = RestClient(node_url, ClientConfig(trust_env=False))
    return AccountClient(
        executor=DexTransactionExecutor(rest_client, signer),
        signer=signer,
        node_url=node_url,
        trust_env=False,
    )


async def create_subaccount_example(
    client: AccountClient, name: str = "trading"
) -> Optional[AccountAddress]:
    result = await client.create_subaccount(name, timeout_secs=30)
    for event in result.transaction.get("events", []):
        if event["type"].endswith("::CreateSubAccountEvent"):
            data = event["data"]
            if isinstance(data, str):
                return decode_create_sub_account_event(
                    bytes.fromhex(data.removeprefix("0x"))
                ).sub_address
            return AccountAddress.from_str_relaxed(data["sub_address"])
    return None


async def transfer_example(
    client: AccountClient,
    from_sub_address: AccountAddress,
    to_sub_address: AccountAddress,
) -> str:
    result = await client.transfer_between_subaccounts(
        from_sub_address, to_sub_address, amount="10.5"
    )
    return result.hash


async def configure_trading_account_example(
    client: AccountClient, sub_address: AccountAddress, symbol_id: int
) -> None:
    await client.set_position_mode(sub_address, "one-way")
    await client.set_margin_mode(
        sub_address, [{"symbol_id": symbol_id, "mode": "isolated"}]
    )
    await client.set_leverage(sub_address, [{"symbol_id": symbol_id, "leverage": "10"}])


async def adjust_isolated_margin_example(
    client: AccountClient, sub_address: AccountAddress, symbol_id: int
) -> str:
    # The account needs an open isolated long and sufficient collateral.
    result = await client.adjust_isolated_margin(
        sub_address, symbol_id=symbol_id, side="long", action="add", amount="100"
    )
    return result.hash


async def authorize_generated_agent_example(client: AccountClient) -> Account:
    # Server/script only. Persist the returned key securely if you keep the agent.
    agent = client.generate_agent_account()
    await client.approve_agent(
        "trading-agent", agent, expires_in_secs=30 * 24 * 60 * 60
    )
    return agent


async def main() -> None:
    from _common import TEST_SYMBOL_ID, get_node_url, load_account_from_env

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=("create", "transfer", "configure", "adjust-margin", "authorize"),
    )
    parser.add_argument(
        "--sub-address", type=AccountAddress.from_str_relaxed, default=MAIN_SUB_ADDRESS
    )
    parser.add_argument("--to-sub-address", type=AccountAddress.from_str_relaxed)
    parser.add_argument("--symbol-id", type=int, default=TEST_SYMBOL_ID)
    parser.add_argument(
        "--name", default="account-demo", help="Unique name for a new subaccount"
    )
    args = parser.parse_args()
    if args.action == "transfer" and args.to_sub_address is None:
        parser.error("transfer requires --to-sub-address")

    client = create_account_client(
        signer=load_account_from_env(), node_url=get_node_url()
    )
    try:
        if args.action == "create":
            sub_address = await create_subaccount_example(client, args.name)
            if sub_address is None:
                raise RuntimeError("Transaction did not emit CreateSubAccountEvent")
            print("Created subaccount:", sub_address)
        elif args.action == "transfer":
            print(
                "Transfer confirmed:",
                await transfer_example(client, args.sub_address, args.to_sub_address),
            )
        elif args.action == "configure":
            await configure_trading_account_example(
                client, args.sub_address, args.symbol_id
            )
            print("Position mode, margin mode and leverage confirmed")
        elif args.action == "adjust-margin":
            print(
                "Margin adjustment confirmed:",
                await adjust_isolated_margin_example(
                    client, args.sub_address, args.symbol_id
                ),
            )
        else:
            agent = await authorize_generated_agent_example(client)
            print("Approved agent:", agent.account_address)
    finally:
        await client.executor.rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Configure leverage, position mode and margin mode for a flat test account."""

import asyncio
import os

from _common import TEST_SYMBOL_ID, get_node_url, get_sub_address, load_account_from_env
from account_client_usage import create_account_client


async def main() -> None:
    signer = load_account_from_env()
    sub_address = get_sub_address(
        signer, int(os.getenv("SUBACCOUNT") or os.getenv("TEST_SUBACCOUNT_ID") or "0")
    )
    client = create_account_client(signer=signer, node_url=get_node_url())
    try:
        leverage = await client.set_leverage(
            sub_address, [{"symbol_id": TEST_SYMBOL_ID, "leverage": "10"}]
        )
        print("Leverage confirmed:", leverage.hash)
        for mode in ("hedge", "one-way"):
            result = await client.set_position_mode(sub_address, mode)
            print("Position mode confirmed:", mode, result.hash)
        for mode in ("isolated", "cross"):
            result = await client.set_margin_mode(
                sub_address, [{"symbol_id": TEST_SYMBOL_ID, "mode": mode}]
            )
            print("Margin mode confirmed:", mode, result.hash)
    finally:
        await client.executor.rest_client.close()


if __name__ == "__main__":
    asyncio.run(main())

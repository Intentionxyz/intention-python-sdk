# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Place, modify, and cancel several limit orders using the SDK batch methods."""

import asyncio
import secrets
from decimal import Decimal

from intention_sdk import ModifyChanges, OrderRef

from _common import example_limit_buy, get_example_market_price, trading_example


async def main() -> None:
    async with trading_example() as (trader, symbol):
        mark = await get_example_market_price(symbol)
        orders = [
            example_limit_buy(symbol, mark * offset)
            for offset in (Decimal("0.995"), Decimal("0.994"), Decimal("0.993"))
        ]
        placed = await trader.place_orders(orders, throw_on_order_reject=True)
        print("Batch placement confirmed:", placed.hash, placed.orders)

        refs = [OrderRef(client_order_id=order.client_order_id) for order in orders]
        replacement_ids = ["0x" + secrets.token_hex(16) for _ in orders]
        changes = [
            (
                ref,
                ModifyChanges(
                    symbol=symbol, price=str(mark * offset), new_client_order_id=new_id
                ),
            )
            for ref, offset, new_id in zip(
                refs,
                (Decimal("0.992"), Decimal("0.991"), Decimal("0.99")),
                replacement_ids,
            )
        ]
        modified = await trader.modify_orders(changes, throw_on_order_reject=True)
        print("Batch modification confirmed:", modified.hash, modified.orders)

        cancelled = await trader.cancel_orders(
            [OrderRef(client_order_id=new_id) for new_id in replacement_ids],
            throw_on_order_reject=True,
        )
        print("Batch cancellation confirmed:", cancelled.hash, cancelled.orders)


if __name__ == "__main__":
    asyncio.run(main())

# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Modify a limit order in one transaction using the TypeScript lifecycle pattern."""

import asyncio
import os
import secrets
from decimal import Decimal

from intention_sdk import ModifyChanges, OrderRef

from _common import example_limit_buy, get_example_market_price, trading_example


async def main() -> None:
    async with trading_example() as (trader, symbol):
        mark = await get_example_market_price(symbol)
        order_id = os.getenv("ORDER_ID")
        if order_id:
            ref = OrderRef(order_id=int(order_id))
        else:
            order = example_limit_buy(symbol, mark * Decimal("0.98"))
            placed = await trader.place_order(order, throw_on_order_reject=True)
            print("Placed test order:", placed.hash, placed.orders)
            ref = OrderRef(client_order_id=order.client_order_id)

        # MODIFY_PRICE can target an existing order on either side.
        price = os.getenv("MODIFY_PRICE") or str(mark * Decimal("0.97"))
        replacement_id = None if order_id else "0x" + secrets.token_hex(16)
        result = await trader.modify_order(
            ref,
            ModifyChanges(
                symbol=symbol, price=price, new_client_order_id=replacement_id
            ),
            throw_on_order_reject=True,
        )
        print("Modification confirmed:", result.hash, result.orders)
        if replacement_id:
            cancelled = await trader.cancel_order(
                OrderRef(client_order_id=replacement_id), throw_on_order_reject=True
            )
            print("Cancelled test order:", cancelled.hash, cancelled.orders)


if __name__ == "__main__":
    asyncio.run(main())

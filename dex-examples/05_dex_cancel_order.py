# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Cancel an order by ORDER_ID or place and cancel a test order by client order ID."""

import asyncio
import os
from decimal import Decimal

from intention_sdk import OrderRef

from _common import example_limit_buy, get_example_market_price, trading_example


async def main() -> None:
    async with trading_example() as (trader, symbol):
        order_id = os.getenv("ORDER_ID")
        if order_id:
            ref = OrderRef(order_id=int(order_id))
        else:
            mark = await get_example_market_price(symbol)
            order = example_limit_buy(symbol, mark * Decimal("0.98"))
            placed = await trader.place_order(order, throw_on_order_reject=True)
            print("Placed test order:", placed.hash, placed.orders)
            ref = OrderRef(client_order_id=order.client_order_id)

        result = await trader.cancel_order(ref, throw_on_order_reject=True)
        print("Cancellation confirmed:", result.hash, result.orders)


if __name__ == "__main__":
    asyncio.run(main())

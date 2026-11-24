# Copyright (c) Intention Foundation
# SPDX-License-Identifier: Apache-2.0

"""Place limit, market and bracket orders with human-unit amounts."""

import argparse
import asyncio
import os
from dataclasses import replace
from decimal import Decimal

from intention_sdk import OrderInput, OrderRef, OrderType, TpSlLeg

from _common import example_limit_buy, get_example_market_price, trading_example


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hedge", action="store_true", help="Use a funded account in hedge mode"
    )
    args = parser.parse_args()

    async with trading_example() as (trader, symbol):
        mark = await get_example_market_price(symbol)
        entry = example_limit_buy(symbol, mark * Decimal("0.98"))
        if args.hedge:
            orders = [
                replace(entry, position_side="LONG"),
                replace(
                    example_limit_buy(symbol, mark * Decimal("1.02")),
                    side="SELL",
                    position_side="SHORT",
                ),
            ]
            result = await trader.place_orders(orders, throw_on_order_reject=True)
            print("Hedge orders confirmed:", result.hash, result.orders)
            refs = [OrderRef(client_order_id=order.client_order_id) for order in orders]
            await trader.cancel_orders(refs, throw_on_order_reject=True)
            return

        limit_order = await trader.place_order(entry, throw_on_order_reject=True)
        print("Limit order confirmed:", limit_order.hash, limit_order.orders)
        await trader.cancel_order(
            OrderRef(client_order_id=entry.client_order_id), throw_on_order_reject=True
        )

        market = await trader.place_order(
            OrderInput(
                symbol=symbol,
                side="SELL",
                type=OrderType.MARKET,
                size=os.getenv("SIZE", "0.01"),
            ),
            throw_on_order_reject=True,
        )
        print("Market order confirmed:", market.hash, market.orders)

        bracket_entry = example_limit_buy(symbol, mark * Decimal("0.98"))
        bracket = await trader.place_order_with_tpsl(
            bracket_entry,
            tp=TpSlLeg(
                type=OrderType.TAKE_PROFIT_MARKET,
                trigger_price=str(mark * Decimal("1.10")),
            ),
            sl=TpSlLeg(
                type=OrderType.STOP_MARKET, trigger_price=str(mark * Decimal("0.90"))
            ),
            throw_on_order_reject=True,
        )
        print("Limit order with TP/SL confirmed:", bracket.hash, bracket.orders)
        await trader.cancel_order(
            OrderRef(client_order_id=bracket_entry.client_order_id),
            throw_on_order_reject=True,
        )


if __name__ == "__main__":
    asyncio.run(main())

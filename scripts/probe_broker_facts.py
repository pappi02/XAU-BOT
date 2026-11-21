"""Read-only probe of two broker facts the bot must not guess (Phase 12 follow-up).

1. Server clock offset: MT5 stamps ticks, bars, positions and deals in broker
   SERVER time, not UTC. Measured as tick.time - real UTC now.
2. Money per price move: ``order_calc_profit`` for 1.00 lot over a $1.00 move,
   compared with trade_contract_size and trade_tick_value, which disagree.

Places NO orders. ``order_calc_profit`` is a calculator call. Refuses a live
account (connect_mt5's identity check). Prints no credentials.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import MetaTrader5 as mt5

import config
from data.connect_mt5 import connect_mt5, disconnect_mt5

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "data", "historical", "%s_broker_facts.json" % config.SYMBOL)


def main():
    if not connect_mt5(config.MT5_ACCOUNT, config.MT5_PASSWORD,
                       config.MT5_SERVER, config.MT5_TIMEOUT_MS):
        print("Could not connect.")
        return 1
    try:
        symbol = config.SYMBOL
        mt5.symbol_select(symbol, True)
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol)
        now = time.time()
        facts = {"symbol": symbol, "measured_at_utc":
                 datetime.now(timezone.utc).isoformat(timespec="seconds")}

        if tick is not None:
            raw = float(tick.time) - now
            facts["tick_time_server"] = datetime.fromtimestamp(
                tick.time, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            facts["raw_offset_seconds"] = round(raw, 1)
            facts["offset_hours_rounded"] = round(raw / 1800.0) * 0.5
            facts["tick_age_after_rounding_seconds"] = round(
                abs(raw - facts["offset_hours_rounded"] * 3600), 1)

        price = float(tick.ask) if tick else float(info.ask)
        for label, order_type, open_, close in (
                ("buy_up_1usd", mt5.ORDER_TYPE_BUY, price, price + 1.0),
                ("sell_down_1usd", mt5.ORDER_TYPE_SELL, price, price - 1.0)):
            facts["profit_1lot_" + label] = mt5.order_calc_profit(
                order_type, symbol, 1.0, open_, close)
        facts["trade_contract_size"] = info.trade_contract_size
        facts["trade_tick_value"] = info.trade_tick_value
        facts["trade_tick_size"] = info.trade_tick_size
        facts["currency_profit"] = info.currency_profit
        account = mt5.account_info()
        facts["account_currency"] = account.currency if account else None
        facts["margin_1lot"] = mt5.order_calc_margin(
            mt5.ORDER_TYPE_BUY, symbol, 1.0, price)
        facts["leverage"] = account.leverage if account else None

        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(facts, fh, indent=2)
        print(json.dumps(facts, indent=2))
        return 0
    finally:
        disconnect_mt5()


if __name__ == "__main__":
    sys.exit(main())

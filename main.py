"""
Main entry point for XAU/USD Trading Bot Phase 5 (Adaptive + Scalable Version)
"""

import logging
import pandas as pd
import time
from datetime import datetime
import MetaTrader5 as mt5
from logger_config import setup_logger

# Import project modules
import config
from config import *
from data.connect_mt5 import connect_mt5, disconnect_mt5, get_mt5_info
from data.fetch_candles import get_candles
from strategies.strategy_basic import BasicTradingStrategy
from utils.indicators import atr, dynamic_rr_ratio, dynamic_stop_loss
from utils.news_reader import get_latest_forex_news
from execution.trade_executor import TradeExecutor
from risk.risk_manager import RiskManager
from trade_logger import trade_logger

# Set up logger
logger = setup_logger(level=LOG_LEVEL)

# === Settings ===
MAX_OPEN_TRADES = 12
TRAILING_STOP_ENABLED = True
SCALING_ENABLED = True
AUTO_CLOSE_ENABLED = True


def adaptive_wait(last_atr, timeframe="M5"):
    """Adjust sleep interval based on volatility (ATR)."""
    if pd.isna(last_atr):
        return 60
    if last_atr < 2:  # Low volatility
        return 180
    elif 2 <= last_atr <= 6:
        return 90
    else:
        return 45 if timeframe == "M1" else 60


def manage_positions(executor, symbol, atr_value, signal_strength, trend_direction):
    """Smart management: trailing, scaling, and adaptive SL updates."""
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return

    for pos in positions:
        current_price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.POSITION_TYPE_SELL else mt5.symbol_info_tick(symbol).ask

        # === Trailing Stop ===
        if TRAILING_STOP_ENABLED and pos.profit > atr_value * 1.5 and signal_strength > 60:
            new_sl = (
                current_price - atr_value * 1.2 if pos.type == mt5.POSITION_TYPE_BUY else current_price + atr_value * 1.2
            )
            # Avoid invalid SL update
            if (pos.type == mt5.POSITION_TYPE_BUY and new_sl > pos.sl) or (pos.type == mt5.POSITION_TYPE_SELL and new_sl < pos.sl):
                req = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "symbol": symbol,
                    "sl": round(new_sl, 2),
                    "tp": pos.tp,
                    "comment": "Adaptive trailing stop",
                }
                result = mt5.order_send(req)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    logger.info(f"🔁 Trailing Stop updated for position {pos.ticket} → SL={new_sl:.2f} (strength={signal_strength:.1f}%)")
                else:
                    logger.warning(f"⚠️ Failed to update SL (retcode={result.retcode})")

        # === Dynamic Scaling ===
        open_positions = len(mt5.positions_get(symbol=symbol))
        if SCALING_ENABLED and open_positions < MAX_OPEN_TRADES:
            if signal_strength > 85 and trend_direction == pos.type:
                scaled_volume = round(pos.volume * 1.25, 2)
                sl = (
                    current_price - atr_value * 2 if pos.type == mt5.POSITION_TYPE_BUY else current_price + atr_value * 2
                )
                tp = (
                    current_price + atr_value * 4 if pos.type == mt5.POSITION_TYPE_BUY else current_price - atr_value * 4
                )

                logger.info(f"⚙️ Scaling in → vol={scaled_volume} | SL={sl:.2f} | TP={tp:.2f} (strength={signal_strength:.1f}%)")
                try:
                    executor.place_order(symbol, "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                                         volume=scaled_volume, sl=sl, tp=tp)
                except Exception as ex:
                    logger.error(f"❌ Error scaling position: {ex}")


def main_loop():
    """Main adaptive trading loop."""
    logger.info("🔌 Initializing MetaTrader 5...")
    if not mt5.initialize(path=config.MT5_PATH):
        logger.error(f"❌ MT5 init failed: {mt5.last_error()}")
        return
    logger.info("✅ MT5 initialized")

    if not connect_mt5(MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER, MT5_TIMEOUT):
        logger.error("❌ MT5 connection failed.")
        return

    risk_mgr = RiskManager(mt5, config)
    executor = TradeExecutor(mt5, config, risk_mgr)
    strategy = BasicTradingStrategy(ema_fast=EMA_FAST, ema_slow=EMA_SLOW, rsi_period=RSI_PERIOD,
                                    bb_period=BB_PERIOD, bb_std=BB_STD_DEV)

    last_signal = None

    while True:
        try:
            # === Fetch data ===
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
                'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4
            }
            mt5_timeframe = timeframe_map.get(TIMEFRAME.upper(), mt5.TIMEFRAME_M5)
            df = get_candles(SYMBOL_PHASE5, mt5_timeframe, NUM_CANDLES)

            if df is None or df.empty:
                logger.warning("⚠️ Empty data, retrying in 30s...")
                time.sleep(30)
                continue

            df = strategy.prepare_data(df)
            atr_series = atr(df, period=ATR_PERIOD)
            last_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 2.5

            signal_info = strategy.generate_signal(df)
            signal, strength = signal_info['signal'], signal_info['strength']

            logger.info(f"📈 Signal: {signal} | Strength={strength:.1f}% | ATR={last_atr:.2f}")

            # === News Adjustment ===
            news_data = get_latest_forex_news()
            if news_data['available']:
                sentiment = news_data['sentiment']
                score = news_data['avg_sentiment_score']
                logger.info(f"📰 News: {sentiment} ({score:.2f})")

                if (sentiment == "bullish" and signal == "SELL") or (sentiment == "bearish" and signal == "BUY"):
                    if score > 0.5:
                        logger.info("📊 News bias triggered → Overriding signal to HOLD")
                        signal = "HOLD"

            # === Manage Open Positions ===
            if AUTO_CLOSE_ENABLED:
                manage_positions(executor, SYMBOL_PHASE5, last_atr, strength,
                                 0 if signal == "HOLD" else (1 if signal == "BUY" else -1))

            # === Trade Entry ===
            open_positions = executor.get_open_positions(SYMBOL_PHASE5)
            open_count = len(open_positions)

            if signal in ["BUY", "SELL"] and strength >= 65 and open_count < MAX_OPEN_TRADES:
                if signal != last_signal or open_count == 0:
                    entry_price = df["close"].iloc[-1]
                    trend_strength = signal_info["components"]["ema_signal"]
                    rsi_condition = signal_info["components"]["rsi_condition"]

                    dynamic_sl_multiplier = dynamic_stop_loss(
                        signal_strength=strength, atr_value=last_atr,
                        news_sentiment=news_data["sentiment"], trend_strength=trend_strength,
                        rsi_condition=rsi_condition, position_type=signal
                    )

                    sl_distance = risk_mgr.calculate_dynamic_sl_distance(entry_price, last_atr, dynamic_sl_multiplier)
                    dynamic_rr = dynamic_rr_ratio(
                        signal_strength=strength, atr_value=last_atr, news_sentiment=news_data["sentiment"],
                        trend_strength=trend_strength, rsi_condition=rsi_condition, position_type=signal
                    )

                    dynamic_lot = risk_mgr.calculate_dynamic_lot_size(
                        stop_loss_distance=sl_distance, signal_strength=strength, atr_value=last_atr,
                        session=risk_mgr.get_current_market_session(), recent_perf=risk_mgr.get_recent_performance(),
                        news_impact=risk_mgr.get_news_impact_level(news_data["sentiment"]),
                        trade_type="trend" if trend_strength > 0 else "reversal"
                    )

                    stop_price = entry_price - sl_distance if signal == "BUY" else entry_price + sl_distance
                    tp_price = entry_price + (sl_distance * dynamic_rr) if signal == "BUY" else entry_price - (sl_distance * dynamic_rr)

                    logger.info(f"📊 Executing {signal}: SL={stop_price:.2f}, TP={tp_price:.2f}, Vol={dynamic_lot:.2f}")
                    try:
                        res = executor.enter_trade(SYMBOL_PHASE5, signal, entry_price, stop_price, tp_price, volume=dynamic_lot)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"✅ Trade success [{signal}] | RR={dynamic_rr:.2f} | Lot={dynamic_lot}")
                            last_signal = signal
                        else:
                            logger.warning(f"❌ Trade failed → {res.comment if res else 'No result'}")
                    except Exception as ex:
                        logger.error(f"❌ Execution error: {ex}")

            # === Adaptive Sleep ===
            sleep_time = adaptive_wait(last_atr, TIMEFRAME)
            logger.info(f"⏸️ Sleeping {sleep_time}s (adaptive based on volatility)")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped manually.")
            break
        except Exception as e:
            logger.exception(f"❌ Main loop error: {e}")
            time.sleep(15)

    disconnect_mt5()
    logger.info("🔌 Disconnected from MT5. Bot stopped.")




def main():
    """
    Main entry point - directly runs the Phase 5 Enhanced Bot.
    """
    print("🤖 XAU/USD Trading Bot")
    print("=" * 40)
    print("🚀 Starting Gold Scalper Enhanced Bot with Risk Management")
    print("⚠️  WARNING: This will execute actual trades with advanced risk controls!")
    print("Make sure you're using a DEMO account for testing.")
    print("=" * 40)

    # Run the enhanced bot directly
    main_loop()

if __name__ == "__main__":
    main()
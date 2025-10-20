"""
Integrated Launcher for XAU/USD Trading Bot and Dashboard
Runs bot and dashboard with single MT5 connection via Flask API
"""

import threading
import os
import time
import json
import subprocess
from datetime import datetime
from flask import Flask, jsonify
import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# Import project modules
import config
from config import *
from data.connect_mt5 import connect_mt5, disconnect_mt5
from data.fetch_candles import get_candles
from strategies.strategy_basic import BasicTradingStrategy
from utils.indicators import atr, dynamic_rr_ratio, dynamic_stop_loss
from utils.news_reader import get_latest_forex_news
from execution.trade_executor import TradeExecutor
from risk.risk_manager import RiskManager
from trade_logger import trade_logger
from logger_config import setup_logger

# Set up logger
logger = setup_logger(level=LOG_LEVEL)

# -----------------------------
# 🧠 MT5 Login Credentials
# -----------------------------
LOGIN = MT5_ACCOUNT
PASSWORD = MT5_PASSWORD
SERVER = MT5_SERVER
SYMBOL = SYMBOL_PHASE5
TIMEFRAME = TIMEFRAME

# -----------------------------
# 🔌 Initialize MetaTrader 5
# -----------------------------
if not mt5.initialize(path=config.MT5_PATH):
    print("❌ MT5 initialization failed:", mt5.last_error())
    quit()
else:
    print(f"✅ Connected to MT5 account {LOGIN}")

if not connect_mt5(LOGIN, PASSWORD, SERVER, MT5_TIMEOUT):
    print("❌ MT5 connection failed.")
    quit()

# -----------------------------
# ⚙️ Flask API for Dashboard
# -----------------------------
app = Flask(__name__)

@app.route('/status')
def status():
    acc = mt5.account_info()
    if acc:
        return jsonify({
            "connected": True,
            "login": acc.login,
            "balance": acc.balance,
            "equity": acc.equity,
            "free_margin": acc.margin_free,
            "margin_level": acc.margin_level,
        })
    return jsonify({"connected": False})

@app.route('/positions')
def positions():
    pos = mt5.positions_get()
    if not pos:
        return jsonify([])
    return jsonify([p._asdict() for p in pos])

@app.route('/market_data')
def market_data():
    try:
        # Check MT5 connection
        if not mt5.account_info():
            return jsonify({"error": "MT5 not connected"})

        # Select the symbol
        if not mt5.symbol_select(SYMBOL, True):
            return jsonify({"error": f"Failed to select symbol {SYMBOL}"})

        symbol_info = mt5.symbol_info(SYMBOL)
        if symbol_info:
            return jsonify({
                "symbol": symbol_info.name,
                "bid": symbol_info.bid,
                "ask": symbol_info.ask,
                "spread": (symbol_info.ask - symbol_info.bid) * 10000,  # in pips
                "volume": symbol_info.volume,
                "time": symbol_info.time
            })
        else:
            return jsonify({"error": "Symbol not found"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/signals')
def signals():
    try:
        SYMBOL_LOCAL = "XAUUSDm"
        TIMEFRAME = mt5.TIMEFRAME_M5  # unified M5 timeframe for consistency

        rates = mt5.copy_rates_from_pos(SYMBOL_LOCAL, TIMEFRAME, 0, 300)

        if rates is None:
            return jsonify({"error": "No data received from MT5"})

        df = pd.DataFrame(rates)
        if df.empty:
            return jsonify({"error": "Empty dataframe"})

        df['time'] = pd.to_datetime(df['time'], unit='s')

        # Use the strategy to prepare data and generate signal
        strategy = BasicTradingStrategy(ema_fast=EMA_FAST, ema_slow=EMA_SLOW, rsi_period=RSI_PERIOD,
                                        bb_period=BB_PERIOD, bb_std=BB_STD_DEV)
        df_prepared = strategy.prepare_data(df)
        signal_info = strategy.generate_signal(df_prepared)

        # Additional indicators for display
        df_prepared['ATR'] = compute_atr(df_prepared)

        last = df_prepared.iloc[-1]
        ema20 = last.get('EMA_12', last['close'])  # fallback if not calculated
        ema50 = last.get('EMA_26', last['close'])
        rsi = last.get('RSI_14', 50)
        upper = last.get('BB_upper_20', last['close'])
        lower = last.get('BB_lower_20', last['close'])
        atr = last.get('ATR', 2.5)
        close = last['close']

        # Reasons from strategy
        reasons = signal_info.get('reasons', [])

        print(f"🧭 SIGNAL DEBUG — {SYMBOL_LOCAL}")
        print(f"EMA12={ema20:.2f}, EMA26={ema50:.2f}, RSI={rsi:.2f}, ATR={atr:.2f}")
        print(f"Signal={signal_info['signal']}, Strength={signal_info['strength']:.1f}%")
        print("Reasons:", "; ".join(reasons))

        return jsonify({
            "signal": signal_info['signal'],
            "strength": signal_info['strength'],
            "ema20": float(ema20),
            "ema50": float(ema50),
            "rsi": float(rsi),
            "atr": float(atr),
            "price": float(close),
            "upper": float(upper),
            "lower": float(lower),
            "higher_tf_trend": "N/A",  # Removed higher timeframe for consistency
            "reasons": reasons
        })
    except Exception as e:
        return jsonify({"error": str(e)})

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def bollinger_bands(series, window=20, num_std=2):
    rolling_mean = series.rolling(window).mean()
    rolling_std = series.rolling(window).std()
    upper = rolling_mean + (rolling_std * num_std)
    lower = rolling_mean - (rolling_std * num_std)
    return upper, lower

def compute_atr(df, period=14):
    """
    Compute Average True Range (ATR)
    """
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def run_flask():
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)

# -----------------------------
# 🤖 Trading Bot Background Task
# -----------------------------
def trading_bot():
    risk_mgr = RiskManager(mt5, config)
    executor = TradeExecutor(mt5, config, risk_mgr)
    strategy = BasicTradingStrategy(ema_fast=EMA_FAST, ema_slow=EMA_SLOW, rsi_period=RSI_PERIOD,
                                    bb_period=BB_PERIOD, bb_std=BB_STD_DEV)

    last_signal = None
    last_signal_time = None
    min_hold_candles = 5  # Minimum 5 candles before allowing signal change
    last_scaling_check = 0  # Track last scaling check time

    while True:
        try:
            # Fetch data
            timeframe_map = {
                'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
                'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4
            }
            mt5_timeframe = timeframe_map.get(TIMEFRAME.upper(), mt5.TIMEFRAME_M5)
            df = get_candles(SYMBOL, mt5_timeframe, NUM_CANDLES)

            if df is None or df.empty:
                logger.warning("⚠️ Empty data, retrying in 30s...")
                time.sleep(30)
                continue

            df = strategy.prepare_data(df)
            atr_series = atr(df, period=ATR_PERIOD)
            last_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 2.5

            signal_info = strategy.generate_signal(df)
            signal, strength = signal_info['signal'], signal_info['strength']

            # Signal Confirmation and Minimum Hold Logic
            current_time = time.time()
            if last_signal is not None and signal != last_signal and signal in ["BUY", "SELL"]:
                # Check if signal opposes last signal and strength is below confirmation threshold
                if (last_signal == "BUY" and signal == "SELL") or (last_signal == "SELL" and signal == "BUY"):
                    if strength < 80:
                        logger.info(f"⚠️ Signal reversal ignored: {last_signal} → {signal} (strength {strength:.1f}% < 80%)")
                        signal = last_signal  # Keep previous signal
                    elif last_signal_time is not None and (current_time - last_signal_time) < (min_hold_candles * 300):  # 5 candles * 5 min each
                        logger.info(f"⚠️ Minimum hold time not met: {last_signal} → {signal} (hold time: {(current_time - last_signal_time)/60:.1f} min < {min_hold_candles*5} min)")
                        signal = last_signal  # Keep previous signal

            logger.info(f"📈 Signal: {signal} | Strength={strength:.1f}% | ATR={last_atr:.2f}")

            # News Adjustment
            news_data = get_latest_forex_news()
            if news_data['available']:
                sentiment = news_data['sentiment']
                score = news_data['avg_sentiment_score']
                logger.info(f"📰 News: {sentiment} ({score:.2f})")

                if (sentiment == "bullish" and signal == "SELL") or (sentiment == "bearish" and signal == "BUY"):
                    if score > 0.5:
                        logger.info("📊 News bias triggered → Overriding signal to HOLD")
                        signal = "HOLD"

            # Manage Open Positions
            open_positions = executor.get_open_positions(SYMBOL)
            if AUTO_CLOSE_ENABLED:
                manage_positions(executor, SYMBOL, last_atr, strength,
                                 0 if signal == "HOLD" else (1 if signal == "BUY" else -1))

            # Check for adaptive scaling
            if config.ADAPTIVE_SCALING_ENABLED and (time.time() - last_scaling_check) >= config.SCALING_CHECK_INTERVAL:
                logger.info("Checking for position scaling opportunities...")
                for position in open_positions:
                    scaling_decision = executor.evaluate_position_scaling(
                        position, df, strategy, news_data, last_atr
                    )

                    if scaling_decision['action'] == 'scale_up':
                        logger.info(f"Scaling up position {position.ticket}: {scaling_decision['reasons']}")
                        success = executor.scale_up_position(position, scaling_decision['additional_lots'], scaling_decision)
                        if success:
                            logger.info(f"Successfully scaled up position {position.ticket}")
                        else:
                            logger.warning(f"Failed to scale up position {position.ticket}")

                    elif scaling_decision['action'] == 'scale_down':
                        logger.info(f"Scaling down position {position.ticket}: {scaling_decision['reasons']}")
                        success = executor.scale_down_position(position, scaling_decision)
                        if success:
                            logger.info(f"Successfully scaled down position {position.ticket}")
                        else:
                            logger.warning(f"Failed to scale down position {position.ticket}")

                last_scaling_check = time.time()

            # Trade Entry
            open_positions = executor.get_open_positions(SYMBOL)
            open_count = len(open_positions)

            if signal in ["BUY", "SELL"] and strength >= 65 and open_count < MAX_CONCURRENT_POSITIONS:
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
                        res = executor.enter_trade(SYMBOL, signal, entry_price, stop_price, tp_price, volume=dynamic_lot)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            logger.info(f"✅ Trade success [{signal}] | RR={dynamic_rr:.2f} | Lot={dynamic_lot}")
                            last_signal = signal
                            last_signal_time = current_time
                        else:
                            logger.warning(f"❌ Trade failed → {res.comment if res else 'No result'}")
                    except Exception as ex:
                        logger.error(f"❌ Execution error: {ex}")

            # Adaptive Sleep
            sleep_time = adaptive_wait(last_atr, TIMEFRAME)
            logger.info(f"⏸️ Sleeping {sleep_time}s (adaptive based on volatility)")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped manually.")
            break
        except Exception as e:
            logger.exception(f"❌ Main loop error: {e}")
            time.sleep(15)

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

        # Trailing Stop
        if TRAILING_STOP_ENABLED and pos.profit > atr_value * 1.5 and signal_strength > 60:
            new_sl = (
                current_price - atr_value * 1.2 if pos.type == mt5.POSITION_TYPE_BUY else current_price + atr_value * 1.2
            )
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
                    logger.info(f"🔁 Trailing Stop updated for position {pos.ticket} → SL={new_sl:.2f}")
                else:
                    logger.warning(f"⚠️ Failed to update SL (retcode={result.retcode})")

        # Scaling
        open_positions = len(mt5.positions_get(symbol=symbol))
        if SCALING_ENABLED and open_positions < MAX_CONCURRENT_POSITIONS:
            if signal_strength > 85 and trend_direction == pos.type:
                scaled_volume = round(pos.volume * 1.25, 2)
                sl = (
                    current_price - atr_value * 2 if pos.type == mt5.POSITION_TYPE_BUY else current_price + atr_value * 2
                )
                tp = (
                    current_price + atr_value * 4 if pos.type == mt5.POSITION_TYPE_BUY else current_price - atr_value * 4
                )

                logger.info(f"⚙️ Scaling in → vol={scaled_volume} | SL={sl:.2f} | TP={tp:.2f}")
                try:
                    executor.place_order(symbol, "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL",
                                         volume=scaled_volume, sl=sl, tp=tp)
                except Exception as ex:
                    logger.error(f"❌ Error scaling position: {ex}")

# -----------------------------
# 🚀 Main Runner
# -----------------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=trading_bot, daemon=True).start()

    print("🌐 Starting Streamlit Dashboard...")
    subprocess.Popen(["streamlit", "run", "dashboard.py"], shell=True)

    while True:
        time.sleep(60)

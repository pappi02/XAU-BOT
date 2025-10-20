<<<<<<< HEAD
"""
Main entry point for XAU/USD Trading Bot Phase 5 (Adaptive + Scalable Version)
"""

import logging
import pandas as pd
=======
# Main entry point for XAU/USD Trading Bot Phase 3 - Real-Time Trading

import logging
import pandas as pd
import matplotlib.pyplot as plt
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614
import time
from datetime import datetime
import MetaTrader5 as mt5
from logger_config import setup_logger

# Import project modules
import config
from config import *
from data.connect_mt5 import connect_mt5, disconnect_mt5, get_mt5_info
<<<<<<< HEAD
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


=======
from data.fetch_live_data import get_live_ohlc
from data.fetch_candles import get_candles
from strategies.strategy_basic import BasicTradingStrategy
from utils.plot_utils import plot_price_with_indicators, plot_backtest_results
from utils.news_reader import get_latest_forex_news
from execution.trade_executor import execute_trade, get_open_positions, close_position
from risk.risk_manager import RiskManager
from execution.trade_executor import TradeExecutor
from utils.indicators import atr, dynamic_rr_ratio, dynamic_stop_loss
from trade_logger import trade_logger

# Set up logging
logger = setup_logger(level=LOG_LEVEL)

def run_real_time_bot():
    """
    Run the bot in real-time continuous trading mode.
    """
    print("🚀 XAU/USD Real-Time Auto Trading Bot Started...")

    # Convert timeframe string to MT5 constant
    timeframe_map = {
        'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
        'H1': 16385, 'H4': 16388, 'D1': 16408,
        'W1': 32769, 'MN': 49153
    }
    mt5_timeframe = timeframe_map.get(TIMEFRAME.upper(), 5)  # Default to M5

    # Initialize strategy
    strategy = BasicTradingStrategy(
        ema_fast=EMA_FAST,
        ema_slow=EMA_SLOW,
        rsi_period=RSI_PERIOD,
        bb_period=BB_PERIOD,
        bb_std=BB_STD_DEV
    )

    # Track last signal to avoid duplicate trades
    last_signal = None
    trade_count = 0

    while True:
        try:
            # Step 1: Get live data (fetch enough bars for indicators)
            logger.info("Fetching live market data...")
            df = get_live_ohlc(SYMBOL, mt5_timeframe, NUM_CANDLES)

            if df is None or df.empty:
                logger.warning("Failed to fetch live data, retrying in 30 seconds...")
                time.sleep(30)
                continue

            logger.info(f"Fetched {len(df)} candles, latest price: ${df['close'].iloc[-1]:.2f}")

            # Step 2: Calculate indicators
            df_with_indicators = strategy.prepare_data(df)

            # Step 3: Get news sentiment
            news_sentiment = get_latest_forex_news()
            logger.info(f"News sentiment: {news_sentiment}")

            # Step 4: Generate trading signal
            signal_info = strategy.generate_signal(df_with_indicators)

            signal = signal_info['signal']
            strength = signal_info['strength']

            logger.info(f"Signal: {signal.upper()} (strength: {strength:.1f}%)")

            # Step 5: Check for trade entry
            if signal in ['BUY', 'SELL'] and strength >= 33:  # Minimum strength threshold (33% = 1 out of 3 indicators)
                # Check if we have open positions
                open_positions = get_open_positions(SYMBOL)

                if not open_positions:
                    # No open positions, can enter new trade
                    if signal != last_signal:  # Avoid duplicate signals
                        logger.info(f"Executing {signal.upper()} trade...")

                        # Execute trade
                        success = execute_trade(
                            symbol=SYMBOL,
                            signal=signal.upper(),
                            volume=TRADE_AMOUNT / (df['close'].iloc[-1] * 100000)  # Convert USD to lots
                        )

                        if success:
                            last_signal = signal
                            trade_count += 1
                            logger.info(f"Trade #{trade_count} executed successfully")
                        else:
                            logger.error("Trade execution failed")
                else:
                    logger.info(f"Open position exists ({len(open_positions)}), skipping new trade")

            # Step 6: Wait before next cycle (check every minute for M1 timeframe)
            wait_time = 60 if TIMEFRAME == 'M1' else 300  # 1 min for M1, 5 min for others
            logger.info(f"Waiting {wait_time} seconds until next analysis...")
            time.sleep(wait_time)

        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(30)  # Wait before retrying

    # Cleanup
    disconnect_mt5()
    logger.info("Bot shutdown complete")

def run_analysis_mode():
    """
    Run the bot in analysis mode (original functionality).
    """
    print("📊 XAU/USD Trading Bot Analysis Mode")

    try:
        # Step 1: Connect to MT5
        logger.info("Connecting to MetaTrader 5...")
        if not connect_mt5(MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER, MT5_TIMEOUT):
            logger.error("Failed to connect to MT5. Exiting...")
            return

        # Get MT5 info
        mt5_info = get_mt5_info()
        if mt5_info:
            logger.info(f"Connected to MT5 terminal: {mt5_info['terminal']['name']}")
            if mt5_info['account']:
                logger.info(f"Account: {mt5_info['account']['login']}, Balance: ${mt5_info['account']['balance']:.2f}")

        # Step 2: Fetch historical data
        logger.info(f"Fetching {NUM_CANDLES} candles for {SYMBOL} on {TIMEFRAME} timeframe...")
        try:
            # Convert timeframe string to MT5 constant
            timeframe_map = {
                'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
                'H1': 16385, 'H4': 16388, 'D1': 16408,
                'W1': 32769, 'MN': 49153
            }
            mt5_timeframe = timeframe_map.get(TIMEFRAME.upper(), 5)  # Default to M5

            candles = get_candles(SYMBOL, mt5_timeframe, NUM_CANDLES)
            if candles.empty:
                logger.error("No data fetched. Exiting...")
                return

            logger.info(f"Successfully fetched {len(candles)} candles")
            print(f"📊 Data range: {candles.index[0]} to {candles.index[-1]}")
            print(f"📊 Latest close price: ${candles['close'].iloc[-1]:.2f}")

        except Exception as e:
            logger.error(f"Error fetching data: {str(e)}")
            return

        # Step 3: Initialize trading strategy
        logger.info("Initializing trading strategy...")
        strategy = BasicTradingStrategy(
            ema_fast=EMA_FAST,
            ema_slow=EMA_SLOW,
            rsi_period=RSI_PERIOD,
            bb_period=BB_PERIOD,
            bb_std=BB_STD_DEV
        )

        # Step 4: Prepare data with indicators
        logger.info("Preparing data with technical indicators...")
        data_with_indicators = strategy.prepare_data(candles)
        logger.info("Indicators calculated successfully")

        # Step 5: Generate current trading signal
        logger.info("Generating trading signal...")
        signal = strategy.generate_signal(data_with_indicators)

        print("\n" + "="*50)
        print("📈 CURRENT TRADING SIGNAL")
        print("="*50)
        print(f"Signal: {signal['signal'].upper()}")
        print(f"Strength: {signal['strength']:.1f}%")
        print(f"Reasons: {', '.join(signal['reasons'])}")
        print(f"Components: EMA={signal['components']['ema_signal']}, RSI={signal['components']['rsi_condition']}, BB={signal['components']['bb_position']}")
        print("="*50)

        # Step 6: Plot price chart with indicators
        logger.info("Generating price chart with indicators...")
        try:
            plot_title = f"XAU/USD {TIMEFRAME} Chart with Technical Indicators"
            plot_price_with_indicators(data_with_indicators.tail(100), title=plot_title)
            logger.info("Chart plotted successfully")
        except Exception as e:
            logger.error(f"Error plotting chart: {str(e)}")

        # Step 7: Optional - Run backtest
        run_backtest = input("\n🔍 Run backtest on historical data? (y/n): ").lower().strip()
        if run_backtest == 'y':
            logger.info("Running backtest...")
            try:
                backtest_results = strategy.backtest(candles, INITIAL_BALANCE, POSITION_SIZE_PCT)

                print("\n" + "="*50)
                print("📊 BACKTEST RESULTS")
                print("="*50)
                print(f"Initial Balance: ${backtest_results['initial_balance']:.2f}")
                print(f"Final Balance: ${backtest_results['final_balance']:.2f}")
                print(f"Total Return: {backtest_results['total_return_pct']:.2f}%")
                print(f"Total Trades: {backtest_results['total_trades']}")
                print("="*50)

                # Plot backtest results
                plot_backtest_results(backtest_results)
                logger.info("Backtest completed and plotted")

            except Exception as e:
                logger.error(f"Error running backtest: {str(e)}")

        # Step 8: Cleanup
        disconnect_mt5()
        logger.info("MT5 connection closed")

        print("\n✅ XAU/USD Trading Bot Analysis completed successfully!")

    except KeyboardInterrupt:
        logger.info("Bot interrupted by user")
        disconnect_mt5()
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        disconnect_mt5()

def main_loop():
    """
    Phase 5 Enhanced Bot — includes full connection and safety checks
    """

    # --- Step 1: Ensure MetaTrader 5 is initialized properly ---
    logger.info("🔌 Initializing MetaTrader 5...")
    if not mt5.initialize(path=config.MT5_PATH):
        logger.error("❌ MT5 initialization failed: %s", mt5.last_error())
        return
    logger.info("✅ MT5 initialized successfully")

    # --- Step 2: Connect to account ---
    if MT5_ACCOUNT and MT5_PASSWORD and MT5_SERVER:
        logger.info("🔐 Connecting to MT5 account...")
        if not connect_mt5(MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER, MT5_TIMEOUT):
            logger.error("❌ Failed to connect to MT5 account. Exiting Phase 5.")
            return
        logger.info("✅ Connected to MT5 account")

    # --- Step 3: Ensure symbol is available and visible ---
    symbol_info = mt5.symbol_info(SYMBOL_PHASE5)
    if symbol_info is None:
        logger.error(f"⚠️ Symbol '{SYMBOL_PHASE5}' not found. Check Market Watch or broker symbol name.")
        disconnect_mt5()
        return

    if not symbol_info.visible:
        logger.info(f"📈 Symbol '{SYMBOL_PHASE5}' not visible — attempting to add it to Market Watch...")
        if not mt5.symbol_select(SYMBOL_PHASE5, True):
            logger.error(f"❌ Failed to add symbol '{SYMBOL_PHASE5}' to Market Watch.")
            disconnect_mt5()
            return
        logger.info(f"✅ Symbol '{SYMBOL_PHASE5}' added to Market Watch successfully.")

    # --- Step 4: Instantiate managers and strategy ---
    risk_mgr = RiskManager(mt5, config)
    executor = TradeExecutor(mt5, config, risk_mgr)
    strategy = BasicTradingStrategy(
        ema_fast=EMA_FAST,
        ema_slow=EMA_SLOW,
        rsi_period=RSI_PERIOD,
        bb_period=BB_PERIOD,
        bb_std=BB_STD_DEV
    )

    logger.info("🚀 Phase 5 Bot initialized and running...")

    try:
        while True:
            try:
                # --- Step 5: Fetch historical data safely ---
                timeframe_map = {
                    'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'M15': mt5.TIMEFRAME_M15,
                    'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4, 'D1': mt5.TIMEFRAME_D1,
                    'W1': mt5.TIMEFRAME_W1, 'MN': mt5.TIMEFRAME_MN1
                }
                mt5_timeframe = timeframe_map.get(TIMEFRAME.upper(), mt5.TIMEFRAME_M5)

                df = get_candles(SYMBOL_PHASE5, mt5_timeframe, NUM_CANDLES)
                if df is None or df.empty:
                    logger.warning("⚠️ No data fetched or empty dataframe — retrying in 30 seconds...")
                    time.sleep(30)
                    continue

                logger.info(f"📊 {len(df)} candles fetched | Latest price: ${df['close'].iloc[-1]:.2f}")

                # --- Step 6: Apply indicators ---
                df = strategy.prepare_data(df)

                # --- Step 7: Compute ATR for SL ---
                atr_series = atr(df, period=ATR_PERIOD)
                last_atr = float(atr_series.iloc[-1]) if len(atr_series) > 0 and not pd.isna(atr_series.iloc[-1]) else None

                # --- Step 8: Generate signal ---
                signal_info = strategy.generate_signal(df)
                signal = signal_info['signal']
                strength = signal_info['strength']

                logger.info("📈 Signal: %s | RSI: %.2f | Strength: %.1f%%", signal, df['RSI_14'].iloc[-1], strength)

                # --- Step 9: News sentiment bias ---
                news_sentiment = get_latest_forex_news()
                logger.info("📰 News sentiment: %s", news_sentiment)

                if news_sentiment == "bullish" and signal == "SELL":
                    signal = "HOLD"
                    logger.info("📊 News bias: overriding SELL to HOLD due to bullish sentiment")
                elif news_sentiment == "bearish" and signal == "BUY":
                    signal = "HOLD"
                    logger.info("📊 News bias: overriding BUY to HOLD due to bearish sentiment")

    # --- Step 10: Position monitoring and auto-close ---
                if config.AUTO_CLOSE_ENABLED:
                    open_positions = get_open_positions(SYMBOL_PHASE5)
                    if open_positions:
                        logger.info(f"📊 Monitoring {len(open_positions)} open positions for auto-close conditions")

                        for pos in open_positions:
                            position_type = 'BUY' if pos.type == mt5.POSITION_TYPE_BUY else 'SELL'
                            position_age = int(time.time() - pos.time)

                            # Skip if position is too young
                            if position_age < config.MIN_HOLDING_TIME:
                                continue

                            # Get current market conditions
                            current_signal_info = strategy.generate_signal(df)
                            current_signal = current_signal_info['signal']
                            signal_strength = current_signal_info['strength']

                            # Detect trend reversals
                            reversal_info = strategy.detect_trend_reversal(df)

                            # Get news sentiment
                            news_sentiment = get_latest_forex_news()

                            # Check if position should be closed using comprehensive auto-close logic
                            close_decision = executor.should_close_trade(
                                position=pos,
                                current_data=df,
                                strategy=strategy,
                                news_sentiment=news_sentiment,
                                atr_value=last_atr,
                                entry_atr=None  # Would need to track this at entry
                            )

                            if close_decision['should_close']:
                                logger.info(f"🚨 Auto-close triggered for position {pos.ticket} ({position_type}): {close_decision['reason']}")

                                # Close the position
                                try:
                                    success = executor.close_position_by_ticket(pos.ticket)
                                    if success:
                                        logger.info(f"✅ Auto-closed position {pos.ticket} - Reason: {close_decision['reason']}")
                                        # Log the auto-close event
                                        trade_logger.log_auto_close(
                                            ticket=pos.ticket,
                                            symbol=config.SYMBOL_PHASE5,
                                            position_type=position_type,
                                            close_reason=close_decision['reason'],
                                            pnl=pos.profit
                                        )
                                    else:
                                        logger.error(f"❌ Failed to auto-close position {pos.ticket}")
                                except Exception as ex:
                                    logger.exception(f"❌ Error auto-closing position {pos.ticket}: {ex}")

                    # Emergency close all positions if account health is critical
                    try:
                        account = risk_mgr.refresh_account()
                        initial_balance = config.INITIAL_ACCOUNT_BALANCE  # Use configurable initial balance
                        current_balance = float(account.balance)
                        balance_drop_pct = (initial_balance - current_balance) / initial_balance

                        if balance_drop_pct >= config.EMERGENCY_CLOSE_THRESHOLD:
                            logger.warning(f"🚨 EMERGENCY: Account balance dropped by {balance_drop_pct:.1%}, closing all positions")
                            executor.close_all_positions(SYMBOL_PHASE5)
                    except Exception as ex:
                        logger.exception(f"❌ Error checking emergency close conditions: {ex}")

                # --- Step 11: Trade execution ---
                if signal in ("BUY", "SELL"):
                    entry_price = df['close'].iloc[-1]

                    # Calculate dynamic stop loss multiplier
                    trend_strength = signal_info['components']['ema_signal']  # -1, 0, 1
                    rsi_condition = signal_info['components']['rsi_condition']  # 'oversold', 'overbought', 'neutral'

                    # Calculate ADX if available (placeholder - would need ADX indicator)
                    adx_value = None  # TODO: Implement ADX calculation

                    # Volume factor (placeholder - would need volume data)
                    volume_factor = 1.0  # TODO: Implement volume/liquidity assessment

                    dynamic_sl_multiplier = dynamic_stop_loss(
                        signal_strength=strength,
                        atr_value=last_atr,
                        news_sentiment=news_sentiment,
                        trend_strength=trend_strength,
                        rsi_condition=rsi_condition,
                        position_type=signal,
                        adx_value=adx_value,
                        volume_factor=volume_factor
                    )

                    # Calculate SL distance using dynamic multiplier
                    sl_distance = risk_mgr.calculate_dynamic_sl_distance(entry_price, last_atr, dynamic_sl_multiplier)

                    # Calculate dynamic risk-reward ratio
                    dynamic_rr = dynamic_rr_ratio(
                        signal_strength=strength,
                        atr_value=last_atr,
                        news_sentiment=news_sentiment,
                        trend_strength=trend_strength,
                        rsi_condition=rsi_condition,
                        position_type=signal
                    )

                    # Calculate dynamic lot size
                    session = risk_mgr.get_current_market_session()
                    recent_perf = risk_mgr.get_recent_performance()
                    news_impact = risk_mgr.get_news_impact_level(news_sentiment)
                    trade_type = "trend" if trend_strength > 0 else "reversal"  # Simplified trade type detection

                    dynamic_lot_size = risk_mgr.calculate_dynamic_lot_size(
                        stop_loss_distance=sl_distance,
                        signal_strength=strength,
                        atr_value=last_atr,
                        session=session,
                        recent_perf=recent_perf,
                        news_impact=news_impact,
                        trade_type=trade_type
                    )

                    logger.info(f"📊 Dynamic calculations: Signal={strength:.1f}%, ATR={last_atr:.2f}, News={news_sentiment}, Trend={trend_strength}, RSI={rsi_condition}, Session={session} → SL_Multiplier={dynamic_sl_multiplier}, RR={dynamic_rr}, Lot_Size={dynamic_lot_size}")

                    stop_price = entry_price - sl_distance if signal == "BUY" else entry_price + sl_distance
                    tp_price = entry_price + (sl_distance * dynamic_rr) if signal == "BUY" else entry_price - (sl_distance * dynamic_rr)

                    try:
                        res = executor.enter_trade(SYMBOL_PHASE5, signal, entry_price, stop_price, tp_price, volume=dynamic_lot_size)
                        logger.info(f"✅ Trade placed: {signal} | SL={stop_price:.2f} | TP={tp_price:.2f} | RR={dynamic_rr} | SL_Distance={sl_distance:.2f} | Lot_Size={dynamic_lot_size} | Result={res}")
                    except Exception as ex:
                        logger.exception("❌ Failed to enter trade: %s", ex)

                # --- Step 11: Pause before next analysis ---
                time.sleep(60)

            except Exception as e:
                logger.exception("Error in main loop: %s", e)
                time.sleep(5)

    finally:
        disconnect_mt5()
        logger.info("🔌 MT5 disconnected and bot stopped.")
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614


def main():
    """
<<<<<<< HEAD
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
=======
    Main entry point - choose between real-time trading, analysis mode, or Phase 5 enhanced bot.
    """
    print("🤖 XAU/USD Trading Bot")
    print("=" * 30)

    mode = input("Choose mode:\n1. Real-time Auto Trading (24/7) - Legacy\n2. Analysis Mode (backtest/plots)\n3. Phase 5 Enhanced Bot (recommended)\nEnter 1, 2, or 3: ").strip()

    if mode == '1':
        # Connect to MT5 first
        if not connect_mt5(MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER, MT5_TIMEOUT):
            logger.error("Failed to connect to MT5. Cannot start real-time trading.")
            return

        # Get MT5 info
        mt5_info = get_mt5_info()
        if mt5_info:
            logger.info(f"Connected to MT5 terminal: {mt5_info['terminal']['name']}")
            if mt5_info['account']:
                logger.info(f"Account: {mt5_info['account']['login']}, Balance: ${mt5_info['account']['balance']:.2f}")

        print("\n⚠️  WARNING: Real-time trading mode will execute actual trades!")
        print("Make sure you're using a DEMO account for testing.")
        confirm = input("Continue? (yes/no): ").lower().strip()

        if confirm in ['yes', 'y']:
            run_real_time_bot()
        else:
            print("Real-time trading cancelled.")
            disconnect_mt5()

    elif mode == '2':
        run_analysis_mode()
    elif mode == '3':
        print("\n🚀 Starting Phase 5 Enhanced Bot with Risk Management")
        print("⚠️  WARNING: This will execute actual trades with advanced risk controls!")
        print("Make sure you're using a DEMO account for testing.")
        confirm = input("Continue? (yes/no): ").lower().strip()

        if confirm in ['yes', 'y']:
            # Run the enhanced bot directly
            main_loop()
        else:
            print("Phase 5 bot cancelled.")
    else:
        print("Invalid choice. Exiting.")

if __name__ == "__main__":
    main()
>>>>>>> 9583572fd6e97d7118f47920d27800694c8ec614

# Main entry point for XAU/USD Trading Bot Phase 3 - Real-Time Trading

import logging
import pandas as pd
import matplotlib.pyplot as plt
import time
from datetime import datetime
import MetaTrader5 as mt5
from logger_config import setup_logger

# Import project modules
import config
from config import *
from data.connect_mt5 import connect_mt5, disconnect_mt5, get_mt5_info
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
            news_data = get_latest_forex_news()
            if isinstance(news_data, dict) and news_data.get('available', False):
                news_sentiment = news_data.get('sentiment', 'neutral')
                logger.info(f"News sentiment: {news_sentiment} (confidence: {news_data.get('confidence', 0.0):.1%})")
            else:
                news_sentiment = 'neutral'
                logger.info(f"News sentiment: {news_sentiment} (no recent news available)")

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

def _analyze_signal_confluence(timeframe_signals: dict, analysis_result: dict) -> dict:
    """
    Analyze signal confluence across timeframes to determine trade direction.
    
    Args:
        timeframe_signals: Dictionary of timeframe signals with structure:
                          {'M1': {'signal': 'BUY/SELL/HOLD', 'strength': %, 'score': value}, ...}
        analysis_result: Full analysis result for additional context
        
    Returns:
        dict: {'direction': 'BUY/SELL/WAIT', 'confidence': float, 'details': str}
    """
    if not timeframe_signals:
        return {'direction': 'WAIT', 'confidence': 0.0, 'details': 'No timeframe signals available'}
    
    # Count signals by direction with strength weighting
    buy_weighted_score = 0.0
    sell_weighted_score = 0.0
    total_weight = 0.0
    
    # Timeframe weights (higher timeframes have more influence)
    tf_weights = {
        'M1': 0.1,   # Entry timing
        'M5': 0.15,  # Short-term trend
        'M15': 0.2,  # Medium-term direction
        'M30': 0.25, # Volatility filter
        'H1': 0.15,  # Trend validation
        'H4': 0.15   # Macro bias
    }
    
    signal_details = []
    
    for tf_name, signal_data in timeframe_signals.items():
        signal = signal_data.get('signal', 'HOLD')
        strength = signal_data.get('strength', 0.0)
        weight = tf_weights.get(tf_name, 0.1)
        
        signal_details.append(f"{tf_name}:{signal}({strength:.0f}%)")
        
        if signal == 'BUY':
            buy_weighted_score += strength * weight
        elif signal == 'SELL':
            sell_weighted_score += strength * weight
        
        total_weight += weight
    
    # Normalize scores
    if total_weight > 0:
        buy_score = buy_weighted_score / total_weight
        sell_score = sell_weighted_score / total_weight
    else:
        buy_score = sell_score = 0.0
    
    # Determine direction based on score difference
    score_diff = abs(buy_score - sell_score)
    min_signal_threshold = 30.0  # Minimum 30% strength difference
    
    if score_diff >= min_signal_threshold:
        if buy_score > sell_score:
            direction = 'BUY'
            confidence = min(buy_score / 100.0, 1.0)
            details = f"BUY signals dominate ({buy_score:.1f}% vs {sell_score:.1f}%)"
        else:
            direction = 'SELL'
            confidence = min(sell_score / 100.0, 1.0)
            details = f"SELL signals dominate ({sell_score:.1f}% vs {buy_score:.1f}%)"
    else:
        # Check for optional factors when signals are close
        direction = 'WAIT'
        confidence = 0.0
        
        # Use news sentiment as optional tiebreaker (if available)
        news_sentiment = analysis_result.get('news_sentiment', 'neutral')
        if news_sentiment in ['bullish', 'bearish']:
            if news_sentiment == 'bullish' and buy_score >= sell_score:
                direction = 'BUY'
                confidence = 0.7  # Moderate confidence for news-based decision
                details = f"Tied signals ({buy_score:.1f}% vs {sell_score:.1f}%), bullish news bias"
            elif news_sentiment == 'bearish' and sell_score >= buy_score:
                direction = 'SELL'
                confidence = 0.7
                details = f"Tied signals ({buy_score:.1f}% vs {sell_score:.1f}%), bearish news bias"
            elif news_sentiment == 'bullish':
                # Bullish news but SELL signals stronger - still favor BUY with news bias
                direction = 'BUY'
                confidence = 0.6  # Lower confidence due to conflicting signals
                details = f"Conflicting signals ({buy_score:.1f}% vs {sell_score:.1f}%), bullish news bias"
            elif news_sentiment == 'bearish':
                # Bearish news but BUY signals stronger - still favor SELL with news bias
                direction = 'SELL'
                confidence = 0.6  # Lower confidence due to conflicting signals
                details = f"Conflicting signals ({buy_score:.1f}% vs {sell_score:.1f}%), bearish news bias"
            else:
                details = f"Tied signals ({buy_score:.1f}% vs {sell_score:.1f}%), news sentiment {news_sentiment}"
        else:
            details = f"Signals too close ({buy_score:.1f}% vs {sell_score:.1f}%), no clear direction"
    
    # Add signal breakdown to details
    signal_breakdown = " | ".join(signal_details)
    details += f" | Signals: {signal_breakdown}"
    
    return {
        'direction': direction,
        'confidence': confidence,
        'details': details
    }

def main_loop():
    """
    Phase 7 Enhanced Bot — Signal-Driven Multi-Timeframe Confluence Trading
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
            logger.error("❌ Failed to connect to MT5 account. Exiting Phase 7.")
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

    # --- Step 4: Instantiate managers, strategy, and multi-timeframe analyzer ---
    risk_mgr = RiskManager(mt5, config)
    executor = TradeExecutor(mt5, config, risk_mgr)
    strategy = BasicTradingStrategy(
        ema_fast=EMA_FAST,
        ema_slow=EMA_SLOW,
        rsi_period=RSI_PERIOD,
        bb_period=BB_PERIOD,
        bb_std=BB_STD_DEV
    )

    # Import and initialize multi-timeframe analyzer
    from analysis.multi_timeframe_analyzer import MultiTimeframeAnalyzer
    analyzer = MultiTimeframeAnalyzer()

    logger.info("🚀 Phase 9 Multi-Timeframe & Context-Aware Decision Engine initialized and running...")

    try:
        while True:
            try:
                # --- Step 5: Phase 9 Multi-Timeframe Analysis ---
                logger.info("🔍 Performing Phase 9 multi-timeframe analysis...")

                analysis_result = analyzer.analyze_market(SYMBOL_PHASE5)

                alignment = analysis_result['alignment']
                action = analysis_result['action']
                should_trade = analysis_result['should_trade']
                position_params = analysis_result['position_params']

                logger.info(f"📊 Alignment: {alignment} | Action: {action} | Should Trade: {should_trade}")

                # Log timeframe analysis
                for tf_name, tf_analysis in analysis_result['timeframe_analysis'].items():
                    logger.debug(f"  {tf_name}: EMA={tf_analysis['ema_trend']}, RSI={tf_analysis['rsi']:.1f}, ATR={tf_analysis['atr']:.3f}, Strength={tf_analysis['signal_strength']:.1f}%")

                # --- Step 6: Position monitoring and auto-close ---
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

                            # Get current market conditions using multi-timeframe analysis
                            current_analysis = analyzer.analyze_market(SYMBOL_PHASE5)
                            current_signal = current_analysis['overall_signal']
                            signal_strength = current_analysis['confidence'] * 100  # Convert to percentage

                            # Detect trend reversals using multi-timeframe data
                            # Get H1 data for reversal detection
                            h1_data = None
                            try:
                                from data.fetch_candles import get_candles
                                h1_data = get_candles(SYMBOL_PHASE5, 16385, config.NUM_CANDLES)  # H1 timeframe
                                if h1_data is not None:
                                    h1_data = strategy.prepare_data(h1_data)
                                    reversal_info = strategy.detect_trend_reversal(h1_data)
                                else:
                                    reversal_info = {'reversal_detected': False}
                            except Exception as ex:
                                logger.warning(f"Could not fetch H1 data for reversal detection: {ex}")
                                reversal_info = {'reversal_detected': False}

                            # Get news sentiment
                            news_sentiment = analysis_result['news_sentiment']

                            # Get ATR from position parameters
                            atr_value = position_params.get('atr_value', None)

                            # ===== Apply Break-even SL =====
                            try:
                                break_even_applied = executor.apply_break_even_sl(pos)
                                if break_even_applied:
                                    logger.info(f"✅ Break-even SL applied to position {pos.ticket}")
                            except Exception as ex:
                                logger.exception(f"❌ Error applying break-even SL to position {pos.ticket}: {ex}")

                            # ===== Apply Trailing Stop =====
                            try:
                                trailing_applied = executor.apply_trailing_stop(pos, position_params['entry_price'])
                                if trailing_applied:
                                    logger.info(f"✅ Trailing stop applied to position {pos.ticket}")
                            except Exception as ex:
                                logger.exception(f"❌ Error applying trailing stop to position {pos.ticket}: {ex}")

                            # ===== Check Partial Close Conditions =====
                            try:
                                partial_closed = executor.check_partial_close_conditions(pos, position_params['entry_price'])
                                if partial_closed:
                                    logger.info(f"✅ Partial close executed for position {pos.ticket}")
                            except Exception as ex:
                                logger.exception(f"❌ Error checking partial close for position {pos.ticket}: {ex}")

                            # Check if position should be closed using comprehensive auto-close logic
                            close_decision = executor.should_close_trade(
                                position=pos,
                                current_data=h1_data if h1_data is not None else None,
                                strategy=strategy,
                                news_sentiment=news_sentiment,
                                atr_value=atr_value,
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
                        initial_balance = config.INITIAL_ACCOUNT_BALANCE
                        current_balance = float(account.balance)
                        balance_drop_pct = (initial_balance - current_balance) / initial_balance

                        if balance_drop_pct >= config.EMERGENCY_CLOSE_THRESHOLD:
                            logger.warning(f"🚨 EMERGENCY: Account balance dropped by {balance_drop_pct:.1%}, closing all positions")
                            executor.close_all_positions(SYMBOL_PHASE5)
                    except Exception as ex:
                        logger.exception(f"❌ Error checking emergency close conditions: {ex}")

                # --- Step 7: Phase 9 Signal-Driven Trade Execution ---
                # Enhanced trade execution logic with diagnostic logging
                confidence = analysis_result['confidence_score']
                logger.info(f"🧭 Trade Decision | Action={action} | Should Trade={should_trade} | Confidence={confidence:.3f} | Alignment={analysis_result['alignment']}")
                
                # INTELLIGENT TRADING: Execute trade if confidence >= 0.7 AND clear signal direction
                if confidence >= 0.7:
                    # Determine trade direction based on comprehensive signal analysis
                    trade_direction = None
                    signal_confidence = 0.0
                    
                    if action in ("BUY", "SELL"):
                        # Use the determined action if it's clear
                        trade_direction = action
                        signal_confidence = confidence
                        logger.info(f"🎯 Using determined action: {trade_direction} (confidence: {confidence:.3f})")
                    else:
                        # Action is WAIT but confidence is high - analyze signal direction from timeframe data
                        logger.info(f"⚠️ High confidence ({confidence:.3f}) but action=WAIT - analyzing signal confluence...")
                        
                        # Get timeframe signals (structured as {'signal': 'BUY/SELL/HOLD', 'strength': %, 'score': value})
                        timeframe_signals = analysis_result.get('timeframe_signals', {})
                        
                        if timeframe_signals:
                            # Analyze signal strength and direction across timeframes
                            signal_analysis = _analyze_signal_confluence(timeframe_signals, analysis_result)
                            trade_direction = signal_analysis['direction']
                            signal_confidence = signal_analysis['confidence']
                            
                            if trade_direction in ('BUY', 'SELL'):
                                logger.info(f"📊 Signal Analysis: {trade_direction} | Confidence: {signal_confidence:.3f} | Details: {signal_analysis['details']}")
                            else:
                                logger.info(f"📊 Signal Analysis: No clear direction | Details: {signal_analysis['details']}")
                        else:
                            logger.warning("⚠️ No timeframe signals available for analysis")
                    
                    # Execute trade if we have a clear direction
                    if trade_direction in ('BUY', 'SELL'):
                        # Get current open positions for comprehensive checks
                        open_positions = get_open_positions(SYMBOL_PHASE5)

                        # Use the comprehensive should_execute_trade method for final decision
                        should_enter, reason = analyzer.should_execute_trade(analysis_result, open_positions, trade_direction)

                        if should_enter:
                            logger.info(f"🎯 SIGNAL-BASED TRADE APPROVED: {trade_direction} | Signal Confidence: {signal_confidence:.3f} | Overall Confidence: {confidence:.3f} | Reason: {reason}")

                            # Use position parameters from Phase 9 analysis
                            entry_price = position_params['entry_price']
                            stop_price = position_params['stop_loss']
                            tp_price = position_params['take_profit']
                            dynamic_lot_size = position_params['lot_size']

                            logger.info(f"📊 Position Parameters: Entry=${entry_price:.2f}, SL=${stop_price:.2f}, TP=${tp_price:.2f}, Lot={dynamic_lot_size}, RR={position_params['rr_ratio']:.1f}")

                            try:
                                res = executor.enter_trade(SYMBOL_PHASE5, trade_direction, entry_price, stop_price, tp_price, volume=dynamic_lot_size)
                                logger.info(f"✅ SIGNAL-DRIVEN TRADE EXECUTED: {trade_direction} | Signal Confidence: {signal_confidence:.3f} | Overall Confidence: {confidence:.3f} | Result={res}")

                                # Update last trade time for cooldown tracking
                                analyzer.last_trade_time = time.time()

                            except Exception as ex:
                                logger.exception("❌ Failed to enter signal-based trade: %s", ex)
                        else:
                            logger.info(f"📊 Trade blocked by risk management: {reason}")
                    else:
                        logger.info(f"📊 No clear signal direction despite high confidence ({confidence:.3f}) - skipping trade")
                else:
                    logger.info(f"📉 Confidence too low ({confidence:.3f} < 0.7) - skipping trade")

                # --- Step 8: Pause before next analysis ---
                logger.info(f"⏱️ Waiting {config.ANALYSIS_INTERVAL_SECONDS} seconds until next multi-timeframe analysis...")
                time.sleep(config.ANALYSIS_INTERVAL_SECONDS)

            except Exception as e:
                logger.exception("Error in Phase 7 main loop: %s", e)
                time.sleep(5)

    finally:
        disconnect_mt5()
        logger.info("🔌 MT5 disconnected and Phase 7 bot stopped.")


def main():
    """
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

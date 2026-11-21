# Phase 4 reference — entry gating to port into `main.py`

`run_bot.py` was reduced to a launcher in Phase 1.4. Its `trading_bot()` loop
contained entry gates that `main.py`'s live `main_loop()` **lacks**, and the
plan (1.3, 1.4) defers porting them to Phase 4. The original loop is preserved
verbatim below so nothing is lost in the meantime.

Three gates to port:

1. **Signal-reversal confirmation** — a BUY→SELL (or SELL→BUY) flip is ignored
   unless `strength >= 80`.
2. **Minimum hold time** — a reversal is ignored unless at least
   `min_hold_candles * 300` seconds (5 M5 candles = 25 min) have passed.
3. **Strength threshold + position cap** — entries require `strength >= 65`
   **and** `open_count < MAX_CONCURRENT_POSITIONS`, plus a dedupe check
   (`signal != last_signal or open_count == 0`).

Note the unit bug baked into gate 2: `min_hold_candles * 300` hardcodes a
300-second candle. It is only correct while `TIMEFRAME == 'M5'`. Fix on port.

Also reconcile `MAX_OPEN_TRADES = 12` (module-level in `main.py`) against
`config.MAX_CONCURRENT_POSITIONS = 100` — they disagree and both are live.

---

## Original `run_bot.py::trading_bot()` (verbatim, pre-reduction)

```python
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
```

"""
Integrated Launcher for XAU/USD Trading Bot and Dashboard
Runs bot and dashboard with single MT5 connection via Flask API
"""

from http import client
import threading
import os
import time
import json
import subprocess
import uuid
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from kb_client import retrieve_relevant_docs

# Import project modules
import config
from config import *
from data.connect_mt5 import connect_mt5, disconnect_mt5
from data.fetch_candles import get_candles
from strategies.strategy_basic import BasicTradingStrategy
from strategies.strategy_selector import StrategySelector
from signal_generator import UnifiedSignalGenerator
from utils.indicators import atr, dynamic_rr_ratio, dynamic_stop_loss
from utils.news_reader_clean import get_latest_forex_news
from execution.trade_executor import TradeExecutor
from risk.risk_manager import RiskManager
from trade_logger import trade_logger
from trade_sync import trade_sync
from logger_config import setup_logger
from utils.symbol_helpers import resolve_symbol
from patterns.double_top import detect_double_top
from patterns.double_bottom import detect_double_bottom
from patterns.head_and_shoulders import detect_head_and_shoulders
from patterns.channels import detect_bullish_channel, detect_bearish_channel, detect_horizontal_channel
from indicators.ema import calculate_ema
from adaptive_engine import AdaptiveEngine, MarketData

# Import new SQLite logger and sync functions
import trade_logger_sqlite as tlog
from sync_closed_trades import sync_closed_trades

# KB imports
from ingest_utils import extract_text_from_pdf, extract_text_from_docx, extract_text_from_image, chunk_text
from vectorstore_chroma import COLLECTION_NAME, upsert_chunks, query_similar, client
import config_learning as cfg

# Set up logger
logger = setup_logger(level=LOG_LEVEL)

# Normalize symbols to canonical form from the start
_canonical_symbol = resolve_symbol(config.SYMBOL)

# Validate config at startup
from validate_config import validate_config
validation = validate_config(config)
if not validation['valid']:
    logger.error(f"Configuration validation failed. Aborting startup.")
    for issue in validation['issues']:
        logger.error(f"  - {issue}")
    quit(1)

# Ensure symbol is always in canonical form
_canonical_symbol = resolve_symbol(config.SYMBOL)

# -----------------------------
# 🧠 MT5 Login Credentials
# -----------------------------
LOGIN = MT5_ACCOUNT
PASSWORD = MT5_PASSWORD
SERVER = MT5_SERVER
SYMBOL = _canonical_symbol  # Always use resolved (canonical) form
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
# 🗄️ Initialize SQLite Database for Trade Logging
# -----------------------------
sqlite_conn = tlog.init_db()

# -----------------------------
# ⚙️ Flask API for Dashboard
# -----------------------------
app = Flask(__name__)
# Shared state cache for latest signal/risk context exposed to dashboard
state_cache = {
    "updated_at": None,
    "signal": None,
    "strength": None,
    "price": None,
    "atr": None,
    "regime": None,
    "trend_strength": None,
    "volatility": None,
    "news_sentiment": None,
    "news_impact": None,
    "risk_mode": None,
    "risk_multiplier": None,
    "dynamic_rr": None,
    "dynamic_lot": None,
    "sl_distance": None,
    "stop_price": None,
    "tp_price": None
}

# KB setup
KB_UPLOAD_DIR = os.getenv("LEARN_UPLOAD_DIR", "./uploads")
os.makedirs(KB_UPLOAD_DIR, exist_ok=True)
kb_logger = logging.getLogger("learning_api")

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

@app.route('/kb_stats')
def kb_stats():
    try:
        # Get collection info from Chroma
        collection = client.get_collection(name=COLLECTION_NAME)
        total_docs = collection.count()

        # Get all documents to count chunks
        results = collection.get()
        total_chunks = len(results['ids']) if results['ids'] else 0

        # Get unique sources
        unique_sources = set()
        if results['metadatas']:
            for metadata in results['metadatas']:
                if 'source' in metadata:
                    unique_sources.add(metadata['source'])

        return jsonify({
            "total_documents": len(unique_sources),
            "total_chunks": total_chunks,
            "embedding_provider": cfg.EMBEDDING_PROVIDER,
            "vector_db_dir": cfg.VECTOR_DB_DIR
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/kb_status')
def kb_status():
    try:
        # Check if Chroma client is available
        collection = client.get_collection(name=COLLECTION_NAME)
        return jsonify({
            "provider": cfg.EMBEDDING_PROVIDER,
            "status": "running",
            "collection": COLLECTION_NAME
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        SYMBOL_LOCAL = resolve_symbol("XAUUSDm")  # Normalize to canonical form
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
        # Add EMA_20 for signals endpoint
        df_prepared['EMA_20'] = calculate_ema(df_prepared, 20, 'close')
        signal_info = strategy.generate_signal(df_prepared)

        # Additional indicators for display
        df_prepared['ATR'] = compute_atr(df_prepared)

        last = df_prepared.iloc[-1]
        ema20 = last.get('EMA_20', last['close'])  # fallback if not calculated
        ema50 = last.get('EMA_26', last['close'])
        rsi = last.get('RSI_14', 50)
        upper = last.get('BB_upper_20', last['close'])
        lower = last.get('BB_lower_20', last['close'])
        atr = last.get('ATR', 2.5)
        close = last['close']

        # Reasons from strategy
        reasons = signal_info.get('reasons', [])

        print(f"🧭 SIGNAL DEBUG — {SYMBOL_LOCAL}")
        print(f"EMA20={ema20:.2f}, EMA26={ema50:.2f}, RSI={rsi:.2f}, ATR={atr:.2f}")
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

@app.route('/broker_specs')
def broker_specs():
    try:
        # Ensure symbol is selected
        mt5.symbol_select(SYMBOL, True)
        info = mt5.symbol_info(SYMBOL)
        digits = int(info.digits) if info and hasattr(info, 'digits') else 2
        point = getattr(info, 'point', 0.01) if info else 0.01
        # Stops level in points → convert to price units
        stops_level_points = 0
        for attr in ('trade_stops_level', 'stops_level'):
            if info and hasattr(info, attr):
                stops_level_points = getattr(info, attr) or 0
                break
        min_stop_distance = float(stops_level_points) * float(point)
        return jsonify({
            "symbol": SYMBOL,
            "digits": digits,
            "point": float(point),
            "min_stop_distance": float(min_stop_distance)
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/signal_context')
def signal_context():
    try:
        # Return latest cached signal/risk context
        payload = dict(state_cache)
        return jsonify(payload)
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/news_state')
def news_state():
    try:
        return jsonify({
            "news_sentiment": state_cache.get("news_sentiment"),
            "news_impact": state_cache.get("news_impact"),
            "updated_at": state_cache.get("updated_at")
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/economic_events')
def economic_events():
    """Return a simple list of upcoming events if available; otherwise a stub."""
    try:
        events = []
        # Optional: integrate with utils.economic_calendar if present
        try:
            from utils.economic_calendar import get_events_today_and_tomorrow
            events = get_events_today_and_tomorrow()
        except Exception:
            # Fallback stub using config gating windows
            events = []
        return jsonify({
            "events": events,
            "gating_enabled": getattr(config, 'NEWS_GATING_ENABLED', False)
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/welcome')
def welcome():
    logger.info(f"Request received: {request.method} {request.path}")
    return jsonify({'message': 'Welcome to the Flask API Service!'})

# KB endpoints
@app.route("/learn", methods=["POST"])
def learn():
    """
    Upload files (pdf/docx/txt/png/jpg) and ingest them into vector DB.
    Returns collection ids inserted.
    """
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "no files uploaded"}), 400

    inserted = []
    for f in files:
        filename = secure_filename(f.filename)
        file_ext = os.path.splitext(filename)[1].lower()
        temp_path = os.path.join(KB_UPLOAD_DIR, f"{uuid.uuid4().hex}_{filename}")
        f.save(temp_path)

        # extract text
        text = ""
        try:
            if file_ext == ".pdf":
                text = extract_text_from_pdf(temp_path)
            elif file_ext in [".docx", ".doc"]:
                text = extract_text_from_docx(temp_path)
            elif file_ext in [".png", ".jpg", ".jpeg", ".tiff"]:
                text = extract_text_from_image(temp_path)
            elif file_ext == ".txt":
                with open(temp_path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            else:
                # try OCR if allowed
                text = extract_text_from_image(temp_path)
        except Exception as e:
            kb_logger.exception("Extract failed")
            text = ""

        if not text:
            kb_logger.warning(f"No text extracted from {filename}")
            continue

        chunks = chunk_text(text)
        # metadata: source filename, chunk index, any label
        metadatas = [{"source": filename, "chunk_index": i} for i in range(len(chunks))]
        ids = [f"{uuid.uuid4().hex}" for _ in range(len(chunks))]

        # Chroma will handle embeddings automatically with the configured embedding function
        upsert_chunks(chunks, metadatas, ids)
        inserted.append({"file": filename, "chunks": len(chunks)})

    return jsonify({"inserted": inserted})

@app.route("/query", methods=["POST"])
def query():
    """
    Query the KB by raw text or by passing an embedding (advanced).
    Request JSON: {"q": "market condition text", "top_k": 5}
    """
    payload = request.json or {}
    q = payload.get("q")
    top_k = payload.get("top_k", 5)
    if not q:
        return jsonify({"error": "missing 'q'"}), 400

    # Query using text directly (Chroma will handle embeddings)
    res = query_similar(query_text=q, k=top_k)
    # Chroma returns dicts, normalize
    results = []
    for i in range(len(res["ids"][0])):
        results.append({
            "id": res["ids"][0][i],
            "document": res["documents"][0][i],
            "metadata": res["metadatas"][0][i],
            "distance": res["distances"][0][i]
        })
    return jsonify({"query": q, "results": results})

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
    app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False, threaded=True)

# -----------------------------
# 🤖 Trading Bot Background Task
# -----------------------------
def trading_bot():
    risk_mgr = RiskManager(mt5, config)
    executor = TradeExecutor(mt5, config, risk_mgr)
    strategy = BasicTradingStrategy(ema_fast=EMA_FAST, ema_slow=EMA_SLOW, rsi_period=RSI_PERIOD,
                                    bb_period=BB_PERIOD, bb_std=BB_STD_DEV)

    # Initialize professional unified signal generator with enhanced signal quality
    unified_signal_generator = UnifiedSignalGenerator(
        ema_fast=EMA_FAST,
        ema_slow=EMA_SLOW,
        rsi_period=RSI_PERIOD,
        bb_period=BB_PERIOD,
        bb_std=BB_STD_DEV,
        config=config,
        enable_news_gating=True,
        enable_strategy_refinements=True,
        enable_pattern_quality_controls=True,
        mt5_connection=mt5
    )
    logger.info("✅ Initialized UnifiedSignalGenerator with professional enhancements")

    # Initialize enhanced strategy selector
    strategy_selector = StrategySelector(cooldown_sec=300, min_confidence=0.6)

    # Initialize adaptive engine
    adaptive_engine = AdaptiveEngine(config)

    last_signal = None
    last_signal_time = None
    min_hold_candles = 5  # Minimum 5 candles before allowing signal change
    last_scaling_check = 0  # Track last scaling check time

    # Bot restart cooldown tracking
    bot_start_time = time.time()
    cooldown_seconds = config.RESTART_COOLDOWN_SECONDS

    # Trade synchronization tracking
    last_sync_time = 0
    sync_interval = 300  # Sync every 5 minutes

    # Cache candles to avoid duplicates
    cached_candles = None
    last_fetch_time = 0

    while True:
        try:
            # Fetch data with caching - FORCED M5 TIMEFRAME FOR AGGRESSIVE SCALPING
            current_time = time.time()
            if cached_candles is None or (current_time - last_fetch_time) > 30:  # Fetch every 30s
                # FORCE M5 TIMEFRAME - No other timeframes allowed for scalping
                mt5_timeframe = mt5.TIMEFRAME_M5
                df = get_candles(SYMBOL, mt5_timeframe, NUM_CANDLES)
                cached_candles = df
                last_fetch_time = current_time
                logger.info(f"✅ Successfully fetched {len(df) if df is not None else 0} candles for {SYMBOL} using M5 timeframe.")
                logger.info("✅ Using M5 timeframe for aggressive scalping mode")
            else:
                df = cached_candles
                logger.info("Using cached M5 candles")

            if df is None or df.empty:
                logger.warning("⚠️ Empty data, retrying in 30s...")
                time.sleep(30)
                continue

            # Get news data for strategy selection
            news_data = get_latest_forex_news()

            # Query knowledge base for strategy guidance
            # Note: We need basic data prep for initial KB query and strategy selection
            df_temp = strategy.prepare_data(df)
            current_rsi = df_temp['RSI_14'].iloc[-1] if 'RSI_14' in df_temp.columns else 50
            atr_series = atr(df_temp, period=ATR_PERIOD)
            last_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 2.5
            market_snapshot_text = f"symbol: {SYMBOL}, timeframe: {TIMEFRAME}, ema_fast: {EMA_FAST}, ema_slow: {EMA_SLOW}, rsi: {current_rsi:.2f}, atr: {last_atr:.2f}"
            kb_results = retrieve_relevant_docs(market_snapshot_text, top_k=5)

            # Use strategy selector to choose optimal strategy
            selection_result = strategy_selector.select_strategy(
                data=df_temp,
                kb_results=kb_results,
                signal_info={'signal': 'HOLD', 'strength': 50},  # Placeholder, will be updated
                news_data=news_data
            )

            selected_strategy = selection_result['strategy_instance']
            logger.info(f"Strategy Selector: {selection_result['selected_strategy']} (confidence: {selection_result['selection_info']['confidence']}%)")
            logger.info(f"Regime: {selection_result['regime_info']['regime']} ({selection_result['regime_info']['confidence']}%)")

            # Prepare data with selected strategy for signal generation
            df = selected_strategy.prepare_data(df)
            atr_series = atr(df, period=ATR_PERIOD)
            last_atr = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else 2.5

            # Use selected strategy to generate signal
            signal_info = selected_strategy.generate_signal(df)
            signal, strength = signal_info['signal'], signal_info['strength']
            logger.info(f"Signal generated using {selection_result['selected_strategy']} strategy")

            # Pattern Recognition Integration
            double_top_pattern = detect_double_top(df)
            double_bottom_pattern = detect_double_bottom(df)
            head_and_shoulders_pattern = detect_head_and_shoulders(df)
            bullish_channel_pattern = detect_bullish_channel(df)
            bearish_channel_pattern = detect_bearish_channel(df)
            horizontal_channel_pattern = detect_horizontal_channel(df)

            # FINAL SIGNAL DECISION ENGINE
            # 1. Get technical signal (ensure it's a string)
            technical_signal = signal_info.get('components', {}).get('ema_signal', 0)
            if isinstance(technical_signal, (int, float)):
                technical_signal = "BUY" if technical_signal == 1 else "SELL" if technical_signal == -1 else "HOLD"
            elif not isinstance(technical_signal, str):
                technical_signal = "HOLD"

            # 2. Determine pattern signal
            pattern_signal = None
            pattern_strength = 0

            # Check for strong patterns that should override technical signals
            if double_top_pattern.get('detected', False) and double_top_pattern.get('confidence', 0) > 0.7:
                pattern_signal = "SELL"  # Bearish reversal
                pattern_strength = double_top_pattern['confidence'] * 100
                logger.info(f"Double Top pattern detected (confidence: {double_top_pattern['confidence']:.1f})")
            elif double_bottom_pattern.get('detected', False) and double_bottom_pattern.get('confidence', 0) > 0.7:
                pattern_signal = "BUY"  # Bullish reversal
                pattern_strength = double_bottom_pattern['confidence'] * 100
                logger.info(f"Double Bottom pattern detected (confidence: {double_bottom_pattern['confidence']:.1f})")
            elif head_and_shoulders_pattern.get('detected', False) and head_and_shoulders_pattern.get('confidence', 0) > 0.7:
                pattern_signal = "SELL"  # Bearish reversal
                pattern_strength = head_and_shoulders_pattern['confidence'] * 100
                logger.info(f"Head and Shoulders pattern detected (confidence: {head_and_shoulders_pattern['confidence']:.1f})")
            elif bullish_channel_pattern.get('detected', False) and bullish_channel_pattern.get('confidence', 0) > 0.6:
                pattern_signal = "BUY"  # Bullish continuation
                pattern_strength = bullish_channel_pattern['confidence'] * 100
                logger.info(f"Bullish Channel pattern detected (confidence: {bullish_channel_pattern['confidence']:.1f})")
            elif bearish_channel_pattern.get('detected', False) and bearish_channel_pattern.get('confidence', 0) > 0.6:
                pattern_signal = "SELL"  # Bearish continuation
                pattern_strength = bearish_channel_pattern['confidence'] * 100
                logger.info(f"Bearish Channel pattern detected (confidence: {bearish_channel_pattern['confidence']:.1f})")

            # 3. Aggressive mode: Allow strong pattern signals to trade even without technical confirmation
            final_signal = "HOLD"
            final_strength = strength

            if pattern_strength >= 70:  # Strong pattern signal (>=0.7 confidence)
                final_signal = pattern_signal
                final_strength = pattern_strength
                logger.info(f"Aggressive mode: Allowing trade based on strong pattern signal ({pattern_strength:.1f}%)")
            elif technical_signal in ["BUY", "SELL"] and pattern_signal in ["BUY", "SELL"]:
                if technical_signal == pattern_signal:
                    final_signal = technical_signal
                    final_strength = max(strength, pattern_strength)  # Use higher strength
                    logger.info(f"Technical + Pattern agreement: {final_signal} (strength: {final_strength:.1f}%)")
                else:
                    final_signal = "HOLD"
                    final_strength = 0
                    logger.info(f"Signal conflict: Technical {technical_signal} vs Pattern {pattern_signal} → HOLD")
            elif technical_signal in ["BUY", "SELL"]:
                final_signal = "HOLD"
                final_strength = 0
                logger.info(f"Technical signal {technical_signal} but no pattern confirmation → HOLD")
            else:
                final_signal = "HOLD"
                final_strength = 0
                logger.info("No clear signal from either technical or pattern analysis - HOLD")

            # 4. Apply horizontal channel adjustment (reduce strength in ranging markets)
            if horizontal_channel_pattern.get('detected', False) and horizontal_channel_pattern.get('confidence', 0) > 0.5:
                final_strength *= 0.8
                logger.info(f"Horizontal Channel detected → Reducing signal strength to {final_strength:.1f}%")

            # Update signal and strength
            signal = final_signal
            strength = final_strength

            # Calculate dynamic market factors for adaptive engine
            # Trend strength: based on EMA crossover or signal components
            trend_strength = signal_info.get('components', {}).get('trend_strength', 0.5)
            if isinstance(trend_strength, str):
                trend_strength = 1.0 if trend_strength == "BUY" else -1.0 if trend_strength == "SELL" else 0.0
            trend_strength = abs(trend_strength)  # Normalize to 0-1

            # Volatility: ATR as percentage of current price
            current_price = df['close'].iloc[-1]
            volatility = (last_atr / current_price) if current_price > 0 else 0.0
            # Cap volatility to reasonable range
            volatility = min(volatility, 0.1)  # Max 10% volatility

            # News impact: based on sentiment score and availability
            news_impact = news_data.get('avg_sentiment_score', 0.0) if news_data.get('available', False) else 0.0
            # Scale news impact based on sentiment strength
            if news_data.get('sentiment') in ['bullish', 'bearish']:
                news_impact = min(news_impact * 1.5, 1.0)  # Amplify strong sentiments

            # Adaptive Engine Integration
            market_data = MarketData(
                symbol=SYMBOL,
                timeframe=TIMEFRAME,
                current_price=current_price,
                atr=last_atr,
                rsi=current_rsi,
                volume=df['tick_volume'].iloc[-1] if 'tick_volume' in df.columns else 0,
                signal=signal,
                strength=strength,
                news_sentiment=news_data.get('sentiment', 'neutral'),
                regime=selection_result.get('regime_info', {}).get('regime', 'unknown'),
                trend_strength=trend_strength,
                volatility=volatility,
                news_impact=news_impact
            )

            # Update adaptive engine with market data
            adaptive_engine.update_market_data(market_data)

            # Process signals through adaptive engine
            signal_components = signal_info.get('components', {})

            # Convert string components to numeric values
            rsi_condition = signal_components.get('rsi_condition', 'neutral')
            rsi_numeric = 1 if rsi_condition == 'oversold' else (-1 if rsi_condition == 'overbought' else 0)

            trend_strength = signal_components.get('trend_strength', 'neutral')
            trend_numeric = 1 if trend_strength == 'bullish' else (-1 if trend_strength == 'bearish' else 0)

            signals_dict = {
                'technical': abs(float(signal_components.get('ema_signal', 0))) * 80,  # Normalize to 0 or 80
                'pattern': float(pattern_strength if pattern_signal else 0),
                'momentum': abs(float(rsi_numeric)) * 80,  # Normalize to 0 or 80
                'trend': abs(float(trend_numeric)) * 80  # Normalize to 0 or 80
            }

            # Check if adaptive engine allows trading
            adaptive_trading_allowed = adaptive_engine.process_signals(signals_dict)

            if not adaptive_trading_allowed and signal in ["BUY", "SELL"]:
                logger.info(f"Adaptive Engine: Trading not allowed based on confidence voting. Signals: {signals_dict}")
                signal = "HOLD"

            # Get adaptive adjustments
            adaptive_adjustments = adaptive_engine.analyze_and_adapt(market_data)

            # Apply adaptive adjustments
            if adaptive_adjustments.get('signal_override'):
                signal = adaptive_adjustments['signal_override']
                strength = adaptive_adjustments.get('adjusted_strength', strength)
                logger.info(f"Adaptive Engine: Signal overridden to {signal} (strength: {strength:.1f}%)")

            # Adjust risk parameters based on adaptive engine
            risk_multiplier = adaptive_adjustments.get('risk_multiplier', 1.0)
            if risk_multiplier != 1.0:
                logger.info(f"Adaptive Engine: Risk multiplier applied: {risk_multiplier:.2f}")

            # Store original strategy signal for logging consistency
            original_signal = signal
            original_strength = strength

            # Signal Confirmation and Minimum Hold Logic - Only apply when positions are open
            open_positions = executor.get_open_positions(SYMBOL)
            has_open_positions = len(open_positions) > 0

            current_time = time.time()
            if has_open_positions and last_signal is not None and signal != last_signal and signal in ["BUY", "SELL"]:
                # Check if signal opposes last signal and strength is below confirmation threshold
                if (last_signal == "BUY" and signal == "SELL") or (last_signal == "SELL" and signal == "BUY"):
                    if strength < 80:
                        logger.info(f"Signal reversal ignored (open positions): {last_signal} → {signal} (strength {strength:.1f}% < 80%)")
                        signal = last_signal  # Keep previous signal for position management
                    elif last_signal_time is not None and (current_time - last_signal_time) < (min_hold_candles * 300):  # 5 candles * 5 min each
                        logger.info(f"Minimum hold time not met (open positions): {last_signal} → {signal} (hold time: {(current_time - last_signal_time)/60:.1f} min < {min_hold_candles*5} min)")
                        signal = last_signal  # Keep previous signal for position management

            logger.info(f"Signal: {original_signal} | Strength={original_strength:.1f}% | ATR={last_atr:.2f} | Strategy: {selection_result['selected_strategy']}")
            if signal != original_signal:
                logger.info(f"Signal adjusted for position management: {original_signal} → {signal}")

            # News Adjustment
            if news_data['available']:
                sentiment = news_data['sentiment']
                score = news_data['avg_sentiment_score']
                logger.info(f"News: {sentiment} ({score:.2f})")

                if (sentiment == "bullish" and signal == "SELL") or (sentiment == "bearish" and signal == "BUY"):
                    if score > 0.5:
                        logger.info("News bias triggered → Overriding signal to HOLD")
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

            # Check bot restart cooldown before trade entry
            current_time = time.time()
            time_since_restart = current_time - bot_start_time
            if time_since_restart < cooldown_seconds:
                remaining_cooldown = cooldown_seconds - time_since_restart
                logger.info(f"Bot restart cooldown active: {remaining_cooldown:.0f}s remaining. Skipping trade entry.")
            else:
                # Trade Entry - Aggressive Scalping Mode: Allow up to 20 concurrent positions
                open_positions = executor.get_open_positions(SYMBOL)
                open_count = len(open_positions)

                if signal in ["BUY", "SELL"] and strength >= 65:
                    # ✅ AGGRESSIVE MODE: Allow stacking trades in same direction for scalping
                    # Dynamic scaling now handled by should_open_new_position() method
                    # Only require signal strength >= 65, position limits handled dynamically

                    # Optional: Prevent stacking too quickly (only add if price moved 0.2 ATR in favor)
                    allow_stacking = True
                    if open_count > 0:
                        # Check if price has moved sufficiently since last entry
                        last_entry_price = max([pos.price_open for pos in open_positions]) if signal == "BUY" else min([pos.price_open for pos in open_positions])
                        price_distance = abs(current_price - last_entry_price)
                        if price_distance < (last_atr * 0.2):
                            logger.info(f"⏸️ Waiting for price expansion before stacking new {signal} trade (distance: {price_distance:.2f} < {last_atr * 0.2:.2f})")
                            allow_stacking = False

                    if allow_stacking:
                        entry_price = df["close"].iloc[-1]
                        # Get trend strength and RSI condition with fallbacks
                        trend_strength = signal_info.get("components", {}).get("ema_signal", 0)
                        rsi_condition = signal_info.get("components", {}).get("rsi_condition", "neutral")

                        # Ensure trend_strength is numeric for calculations
                        if isinstance(trend_strength, str):
                            trend_strength = 1 if trend_strength == "BUY" else -1 if trend_strength == "SELL" else 0
                        elif not isinstance(trend_strength, (int, float)):
                            trend_strength = 0

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

                        # Get dynamic risk mode from adaptive engine
                        risk_mode = adaptive_engine.risk_resolver.resolve_risk_mode(market_data, mt5.account_info().balance)

                        dynamic_lot = risk_mgr.calculate_dynamic_lot_size(
                            stop_loss_distance=sl_distance, signal_strength=strength, atr_value=last_atr,
                            session=risk_mgr.get_current_market_session(), recent_perf=risk_mgr.get_recent_performance(),
                            news_impact=risk_mgr.get_news_impact_level(news_data["sentiment"]),
                            trade_type="trend" if trend_strength > 0 else "reversal",
                            risk_mode=risk_mode.value
                        )

                        # Apply adaptive risk multiplier
                        dynamic_lot *= risk_multiplier

                        stop_price = entry_price - sl_distance if signal == "BUY" else entry_price + sl_distance
                        tp_price = entry_price + (sl_distance * dynamic_rr) if signal == "BUY" else entry_price - (sl_distance * dynamic_rr)

                        # Update state cache for dashboard visibility
                        try:
                            state_cache.update({
                                "updated_at": datetime.utcnow().isoformat(),
                                "signal": signal,
                                "strength": float(strength),
                                "price": float(entry_price),
                                "atr": float(last_atr),
                                "regime": selection_result.get('regime_info', {}).get('regime', 'unknown'),
                                "trend_strength": float(trend_strength),
                                "volatility": float(volatility),
                                "news_sentiment": news_data.get('sentiment', 'neutral'),
                                "news_impact": float(news_impact),
                                "risk_mode": getattr(risk_mode, 'value', str(risk_mode)),
                                "risk_multiplier": float(risk_multiplier),
                                "dynamic_rr": float(dynamic_rr),
                                "dynamic_lot": float(dynamic_lot) if dynamic_lot is not None else None,
                                "sl_distance": float(sl_distance),
                                "stop_price": float(stop_price),
                                "tp_price": float(tp_price)
                            })
                        except Exception as _:
                            pass

                        logger.info(f"🔥 AGGRESSIVE SCALPING: Executing {signal} trade #{open_count + 1}/20 | SL={stop_price:.2f}, TP={tp_price:.2f}, Vol={dynamic_lot:.2f}")
                        try:
                            res = executor.enter_trade(SYMBOL, signal, entry_price, stop_price, tp_price, volume=dynamic_lot)
                            if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                                logger.info(f"✅ Trade success [{signal}] | RR={dynamic_rr:.2f} | Lot={dynamic_lot} | Total positions: {open_count + 1}")
                                last_signal = signal
                                last_signal_time = current_time
                            else:
                                logger.warning(f"❌ Trade failed → {res.comment if res else 'No result'}")
                        except Exception as ex:
                            logger.error(f"❌ Execution error: {ex}")
                    else:
                        logger.info(f"⏸️ Skipping {signal} trade stacking - waiting for better entry conditions")



            # Periodic trade synchronization
            current_time = time.time()
            if (current_time - last_sync_time) >= sync_interval:
                logger.info("Running periodic trade synchronization...")
                try:
                    trade_sync.full_sync(days_back=7)  # Sync last 7 days
                    # Also sync closed trades from MT5 deal history
                    sync_closed_trades(sqlite_conn, lookback_minutes=120)
                    last_sync_time = current_time
                except Exception as e:
                    logger.error(f"❌ Trade sync failed: {e}")

            # Adaptive Sleep
            sleep_time = adaptive_wait(last_atr, TIMEFRAME)
            logger.info(f"Sleeping {sleep_time}s (adaptive based on volatility)")
            time.sleep(sleep_time)

        except KeyboardInterrupt:
            logger.info("Bot stopped manually.")
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
                    logger.info(f"Trailing Stop updated for position {pos.ticket} → SL={new_sl:.2f}")
                else:
                    logger.warning(f"Failed to update SL (retcode={result.retcode})")

        # Scaling
        open_positions = len(mt5.positions_get(symbol=symbol))
        if SCALING_ENABLED:
            if signal_strength > 85 and trend_direction == pos.type:
                scaled_volume = round(pos.volume * 1.25, 2)
                sl = (
                    current_price - atr_value * 2 if pos.type == mt5.POSITION_TYPE_BUY else current_price + atr_value * 2
                )
                tp = (
                    current_price + atr_value * 4 if pos.type == mt5.POSITION_TYPE_BUY else current_price - atr_value * 4
                )

                logger.info(f"Scaling in → vol={scaled_volume} | SL={sl:.2f} | TP={tp:.2f}")
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

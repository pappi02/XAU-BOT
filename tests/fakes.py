"""Test doubles for the broker, config and risk manager.

Phase 6.3 (audit M-05). ``TradeExecutor.__init__`` used to substitute these
silently when its arguments were None -- including an ``order_send`` that
returned ``retcode=10009`` (DONE). A fake broker that confirms every order,
reachable from production code by passing nothing, is the worst possible
default: it makes a misconfigured bot look like a working one.

The doubles live here, where they can only be reached deliberately.
"""

import os

from unittest.mock import MagicMock, Mock

MAGIC = 987654321


def fake_symbol_info(**overrides):
    """A realistic XAUUSD contract specification."""
    fields = dict(
        name="XAUUSDm", digits=2, point=0.01, trade_contract_size=100.0,
        trade_tick_value=1.0, trade_tick_size=0.01, volume_min=0.01,
        volume_step=0.01, volume_max=50.0, trade_stops_level=0,
        trade_freeze_level=0, filling_mode=2, spread=20, visible=True,
        bid=2000.40, ask=2000.50,
    )
    fields.update(overrides)
    info = MagicMock(**fields)
    info.name = fields["name"]          # MagicMock(name=...) sets the mock name
    return info


def fake_mt5(**overrides):
    """A MetaTrader5 double that answers queries but confirms nothing by default."""
    mt5 = MagicMock()

    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1
    mt5.TRADE_ACTION_DEAL = 1
    mt5.TRADE_ACTION_SLTP = 6
    mt5.ORDER_TIME_GTC = 0
    mt5.ORDER_FILLING_IOC = 0
    mt5.ORDER_FILLING_FOK = 1
    mt5.ORDER_FILLING_RETURN = 2
    mt5.SYMBOL_FILLING_FOK = 1
    mt5.SYMBOL_FILLING_IOC = 2
    mt5.TRADE_RETCODE_DONE = 10009
    mt5.POSITION_TYPE_BUY = 0
    mt5.POSITION_TYPE_SELL = 1
    mt5.ACCOUNT_TRADE_MODE_DEMO = 0

    mt5.symbol_info.return_value = fake_symbol_info()
    mt5.symbol_info_tick.return_value = MagicMock(bid=2000.40, ask=2000.50)
    mt5.symbol_select.return_value = True
    mt5.positions_get.return_value = []
    mt5.history_orders_get.return_value = []
    mt5.history_deals_get.return_value = []
    mt5.terminal_info.return_value = MagicMock(connected=True, trade_allowed=True)
    mt5.account_info.return_value = MagicMock(
        balance=10000.0, equity=10000.0, profit=0.0, margin_free=10000.0,
        login=12345678, server="Demo-Server", trade_mode=0)
    mt5.order_calc_margin.return_value = 10.0
    mt5.order_send.return_value = MagicMock(retcode=10009, volume=0.1,
                                            price=2000.50, order=1)

    for key, value in overrides.items():
        setattr(mt5, key, value)
    return mt5


def fake_config(**overrides):
    """A config double carrying every key the executor reads."""
    cfg = Mock()
    # Phase 7: an isolated database per config, so tests never read or write
    # the project's real trades.db.
    import tempfile
    cfg.TRADE_DB_PATH = os.path.join(tempfile.mkdtemp(), "trades.db")
    cfg.SYMBOL = "XAUUSDm"
    cfg.SYMBOL_PHASE5 = "XAUUSDm"
    cfg.BROKER_SERVER_TZ = "America/New_York"
    cfg.BROKER_SERVER_SHIFT_HOURS = 7.0
    cfg.TIMEFRAME = "M5"
    cfg.ORDER_DEVIATION_POINTS = 10
    cfg.ORDER_MAX_ATTEMPTS = 3
    cfg.MAX_ENTRY_SPREAD_POINTS = 50
    cfg.MAX_CONCURRENT_POSITIONS = 1
    cfg.MAX_OPEN_TRADES = 1
    cfg.MIN_ENTRY_STRENGTH = 65.0
    cfg.SIGNAL_REVERSAL_MIN_STRENGTH = 80.0
    cfg.MIN_SIGNAL_HOLD_BARS = 5

    cfg.RISK_PER_TRADE_FRACTION = 0.01
    cfg.MAX_DAILY_LOSS_FRACTION = 0.05
    cfg.MIN_ACCOUNT_BALANCE = 50.0
    cfg.MAX_DRAWDOWN_FRACTION = 0.20
    cfg.MAX_PORTFOLIO_RISK_FRACTION = 0.04
    cfg.MAX_CONSECUTIVE_LOSSES = 5
    cfg.MAX_LOTS_PER_ORDER = 5.0

    cfg.TRAILING_STOP_ENABLED = False
    cfg.BREAK_EVEN_ENABLED = False
    cfg.ADAPTIVE_TRAILING_STOP = True
    cfg.TRAIL_START_PRICE = 25.0
    cfg.TRAIL_DISTANCE_PRICE = 10.0
    cfg.BREAK_EVEN_PROFIT_PRICE = 20.0
    cfg.BREAK_EVEN_BUFFER_PRICE = 2.0
    cfg.BREAK_EVEN_ATR_MULTIPLIER = 0.5
    cfg.BREAK_EVEN_TREND_STRENGTH_MULTIPLIER = 0.1
    cfg.BREAK_EVEN_NEWS_SENTIMENT_MULTIPLIER = 0.2
    cfg.BREAK_EVEN_TIME_SINCE_ENTRY_MULTIPLIER = 0.01
    cfg.BREAK_EVEN_PROFIT_LEVEL_MULTIPLIER = 0.05
    cfg.BREAK_EVEN_MAX_BUFFER_FRACTION = 0.9

    cfg.AUTO_CLOSE_ENABLED = True
    cfg.MIN_HOLDING_SECONDS = 300
    cfg.MAX_POSITION_AGE_SECONDS = 86400
    cfg.EXIT_REVERSAL_MIN_STRENGTH = 70
    cfg.SIGNAL_WEAKENING_CLOSE = False
    cfg.EXIT_WEAKENING_MAX_STRENGTH = 30
    cfg.NEWS_SENTIMENT_CLOSE = True
    cfg.NEWS_SENTIMENT_TRADING_ENABLED = False
    cfg.TREND_INITIAL_SL_ATR_MULT = 2.5
    cfg.TREND_TRAIL_ATR_MULT = 3.0
    cfg.VOLATILITY_SPIKE_ENABLED = True
    cfg.ATR_SPIKE_MULTIPLIER = 2.0
    cfg.SESSION_END_CLOSE = False
    cfg.SESSION_END_BUFFER_MINUTES = 30
    cfg.BREAK_OF_STRUCTURE_ENABLED = True
    cfg.FRACTAL_PERIOD = 5
    cfg.RR_REVERSAL_ENABLED = False
    cfg.RR_REVERSAL_THRESHOLD = 0.5
    cfg.PORTFOLIO_DRAWDOWN_CLOSE = True
    cfg.EMERGENCY_CLOSE_DRAWDOWN_FRACTION = 0.35
    cfg.MAX_TOTAL_POSITIONS_CLOSE_ENABLED = False
    cfg.MAX_TOTAL_POSITIONS = 2
    cfg.TREND_REVERSAL_CLOSE = True

    # Phase 12.3: CURRENT_ATR / CURRENT_TREND_STRENGTH / CURRENT_NEWS_SENTIMENT
    # were deleted from config -- live state is passed as arguments now. They
    # are explicitly absent here so a regression that reads them fails.
    del cfg.CURRENT_ATR
    del cfg.CURRENT_TREND_STRENGTH
    del cfg.CURRENT_NEWS_SENTIMENT

    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def fake_risk_manager(**overrides):
    """A risk manager double whose gates all pass by default."""
    rm = Mock()
    rm.compute_lot_size.return_value = 0.1
    rm.calculate_dynamic_lot_size.return_value = 0.1
    rm.enough_balance.return_value = True
    rm.check_daily_loss_limit.return_value = True
    rm.check_drawdown.return_value = True
    rm.check_portfolio_risk.return_value = True
    rm.contract_size.return_value = 100.0
    rm.current_open_positions_count.return_value = 0
    rm.refresh_account.return_value = MagicMock(
        balance=10000.0, equity=10000.0, profit=0.0, margin_free=10000.0)
    rm.state = MagicMock()
    rm.state.drawdown_fraction.return_value = 0.0
    for key, value in overrides.items():
        setattr(rm, key, value)
    return rm


def make_executor(mt5=None, config=None, risk_manager=None):
    """Build a TradeExecutor wired to doubles.

    Use this in tests instead of ``TradeExecutor()``, which now raises.
    """
    from execution.trade_executor import TradeExecutor
    return TradeExecutor(
        mt5 or fake_mt5(),
        config or fake_config(),
        risk_manager or fake_risk_manager(),
    )

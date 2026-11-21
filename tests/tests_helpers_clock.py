"""Broker-time helpers for tests: MT5 stamps positions in SERVER time."""

from datetime import datetime, timedelta, timezone

from utils.market_time import BrokerClock


def server_time_ago(seconds, clock=None):
    """``position.time`` for a position opened ``seconds`` ago."""
    opened = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return int((clock or BrokerClock()).utc_to_server_epoch(opened))

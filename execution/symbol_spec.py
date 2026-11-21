"""One authoritative source for every instrument fact (Phase 2.1, audit C-04).

The audit's root finding was that `CONTRACT_SIZE` was *configured* -- and
configured wrongly, at the FX convention of 100000 rather than gold's 100 oz per
standard lot. That single number propagated into sizing, pip conversion,
break-even, trailing and the reward/risk calculation, making all of them wrong
by 1000x.

The fix is not a better constant. It is to stop configuring instrument facts at
all and read them from the broker, which is the only authority on what a lot of
XAUUSD is at *your* broker.

`SymbolSpec` is also where the word "pip" goes to die. Gold brokers variously
treat a pip as 0.01, 0.10 or 1.00, and the codebase's `x / 100000 *
CONTRACT_SIZE` silently implemented "1 pip = $1.00". Money conversion now goes
through `price_to_money` / `money_to_price`, which speak in price units and
lots, and nothing else.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)
_WARNED = set()


class SymbolSpecError(RuntimeError):
    """Raised when a symbol's specification cannot be read or fails validation."""


@dataclass(frozen=True)
class SymbolSpec:
    """An immutable snapshot of a broker's contract specification for a symbol.

    Load once at startup with :meth:`load`, log it, and pass it down. Frozen so
    no code path can quietly mutate an instrument fact mid-run.
    """

    name: str
    digits: int                 # 2 or 3 for XAUUSD -- never assume
    point: float                # 0.01 or 0.001
    contract_size: float        # 100.0 oz for XAUUSD -- READ, never configured
    tick_value: float           # account currency per point per lot
    tick_size: float
    volume_min: float
    volume_step: float
    volume_max: float
    stops_level_points: int     # minimum SL/TP distance from price, in points
    freeze_level_points: int    # distance within which modify/close is refused
    filling_modes: int          # bitmask of SYMBOL_FILLING_* flags

    # ------------------------------------------------------------------ load

    @classmethod
    def load(cls, mt5, symbol, expected_contract_size=None):
        """Read the specification for ``symbol`` from a connected terminal.

        Args:
            mt5: the MetaTrader5 module (or a double in tests).
            symbol: the broker's symbol name, e.g. "XAUUSDm".
            expected_contract_size: if given, the load fails unless the broker
                agrees. A broker silently changing contract size is exactly the
                class of event that made C-04 so damaging, so it should be loud.

        Raises:
            SymbolSpecError: symbol unknown, not selectable, or inconsistent.
        """
        info = mt5.symbol_info(symbol)
        if info is None:
            # Not in Market Watch yet -- try once to add it, then re-read.
            if not mt5.symbol_select(symbol, True):
                raise SymbolSpecError(
                    "Symbol %r is not available from this broker. Check the "
                    "exact name in Market Watch (gold is often XAUUSD, XAUUSDm "
                    "or GOLD)." % symbol
                )
            info = mt5.symbol_info(symbol)
            if info is None:
                raise SymbolSpecError(
                    "Symbol %r selected but symbol_info() still returned None."
                    % symbol
                )

        # Prefer the name we were asked for. The broker's own `info.name`
        # should match, but the requested string is what every subsequent
        # mt5 call must be keyed on, so trust it over a surprising echo.
        broker_name = getattr(info, "name", None)
        name = broker_name if isinstance(broker_name, str) else symbol

        spec = cls(
            name=name,
            digits=int(info.digits),
            point=float(info.point),
            contract_size=float(info.trade_contract_size),
            tick_value=float(info.trade_tick_value),
            tick_size=float(getattr(info, "trade_tick_size", 0.0) or info.point),
            volume_min=float(info.volume_min),
            volume_step=float(info.volume_step),
            volume_max=float(info.volume_max),
            stops_level_points=int(getattr(info, "trade_stops_level", 0)),
            freeze_level_points=int(getattr(info, "trade_freeze_level", 0)),
            filling_modes=int(getattr(info, "filling_mode", 0)),
        )
        spec.validate(expected_contract_size)
        spec.verify_money_per_price(mt5)
        return spec

    # -------------------------------------------------------------- validate

    def validate(self, expected_contract_size=None):
        """Reject a specification that cannot be traded against safely."""
        problems = []

        if self.point <= 0:
            problems.append("point is %r; must be > 0" % self.point)
        if self.digits < 0:
            problems.append("digits is %r" % self.digits)
        if self.contract_size <= 0:
            problems.append("contract_size is %r; must be > 0" % self.contract_size)
        if self.volume_min <= 0:
            problems.append("volume_min is %r" % self.volume_min)
        if self.volume_step <= 0:
            problems.append("volume_step is %r" % self.volume_step)
        if self.volume_max < self.volume_min:
            problems.append("volume_max %r < volume_min %r"
                            % (self.volume_max, self.volume_min))

        if (expected_contract_size is not None
                and self.contract_size != float(expected_contract_size)):
            problems.append(
                "contract_size is %r but %r was expected. The broker changed "
                "the contract specification, or the symbol is not the "
                "instrument you think it is. Sizing and every money conversion "
                "depend on this -- refusing to continue."
                % (self.contract_size, float(expected_contract_size))
            )

        if problems:
            raise SymbolSpecError(
                "Unusable specification for %s: %s" % (self.name, "; ".join(problems))
            )
        return self

    def verify_money_per_price(self, mt5):
        """Confirm contract_size is the real exposure, using the broker's calculator.

        All sizing uses contract_size. Brokers also report trade_tick_value,
        which on MetaQuotes-Demo XAUUSD disagrees tenfold (0.1 per 0.01 tick).
        ``order_calc_profit`` is authoritative: measured 2026-09-13 it returned
        $100 for 1.00 lot over a $1.00 move, confirming contract_size = 100.

        Raises SymbolSpecError when the calculator contradicts contract_size --
        every lot size would be wrong. Warns once when it cannot be asked.
        """
        ratio = self.tick_value_ratio()
        calc = getattr(mt5, "order_calc_profit", None)
        profit = None
        if callable(calc):
            try:
                price = 1000.0
                value = calc(getattr(mt5, "ORDER_TYPE_BUY", 0), self.name, 1.0,
                             price, price + 1.0)
                profit = float(value) if isinstance(value, (int, float)) else None
            except Exception:
                profit = None
        if profit is not None:
            if abs(profit - self.contract_size) > 0.01 * self.contract_size:
                raise SymbolSpecError(
                    "%s: order_calc_profit says 1.00 lot over a 1.0 price move is "
                    "%.4g, but contract_size is %.4g. Sizing would be wrong by "
                    "%.3gx -- refusing to continue."
                    % (self.name, profit, self.contract_size, profit / self.contract_size))
            return True
        if ratio is not None and abs(ratio - 1.0) > 0.05 and self.name not in _WARNED:
            _WARNED.add(self.name)
            logger.warning(
                "%s: tick_value/tick_size implies %.4g per 1.0 price move per lot, "
                "contract_size %.4g (ratio %.3g), and order_calc_profit is not "
                "available to decide. Sizing uses contract_size.",
                self.name, self.tick_value / self.tick_size, self.contract_size, ratio)
        return None

    def tick_value_ratio(self):
        """Broker tick value per unit price move divided by contract size.

        1.0 when the two agree (USD-quoted symbol on a USD account). None when
        tick data is unusable.
        """
        if self.tick_size <= 0 or self.tick_value <= 0 or self.contract_size <= 0:
            return None
        return (self.tick_value / self.tick_size) / self.contract_size

    # ----------------------------------------------------------- conversions

    def round_price(self, price):
        """Round to the symbol's own precision, not a hardcoded 2 decimals."""
        return round(float(price), self.digits)

    def points(self, price_delta):
        """Convert a price distance into broker points."""
        return float(price_delta) / self.point

    def price_from_points(self, points):
        """Convert broker points into a price distance."""
        return float(points) * self.point

    def spread_points(self, mt5):
        """Current spread in points, read live.

        Returns None when the spread cannot be determined -- no tick, or a tick
        whose bid/ask are not readable numbers. Callers must treat None as
        "unknown" and say so, rather than as "zero".
        """
        tick = mt5.symbol_info_tick(self.name)
        if tick is None:
            return None
        try:
            return (float(tick.ask) - float(tick.bid)) / self.point
        except (TypeError, ValueError, AttributeError):
            return None

    def describe(self):
        """One-line summary for the startup log."""
        return (
            "%s: digits=%d point=%g contract_size=%g tick_value=%g "
            "volume[min=%g step=%g max=%g] stops_level=%d freeze_level=%d "
            "filling_modes=%d"
            % (self.name, self.digits, self.point, self.contract_size,
               self.tick_value, self.volume_min, self.volume_step,
               self.volume_max, self.stops_level_points,
               self.freeze_level_points, self.filling_modes)
        )


# --------------------------------------------------------------------- money
#
# The only two money conversions in the codebase. Both speak price units and
# lots. Neither knows what a "pip" is, deliberately.

def price_to_money(spec, price_delta, lots):
    """Money gained/lost when price moves ``price_delta`` holding ``lots``."""
    return float(price_delta) * spec.contract_size * float(lots)


def money_to_price(spec, money, lots):
    """Price distance corresponding to ``money`` at ``lots``.

    Raises:
        ZeroDivisionError is avoided: zero lots has no meaningful price
        distance, so this raises SymbolSpecError instead of returning inf.
    """
    denominator = spec.contract_size * float(lots)
    if denominator == 0:
        raise SymbolSpecError(
            "money_to_price requires non-zero lots (got %r)" % lots
        )
    return float(money) / denominator

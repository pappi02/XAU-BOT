"""Validate every order against the broker before sending it (Phase 2.3, H-01).

The audit found that the broker's own constraints were consulted almost nowhere
on the live path:

  * ``volume_step`` / ``volume_min`` / ``volume_max`` were used only in
    ``compute_lot_size``, which the live path never reached.
  * ``trade_stops_level`` was used only in ``modify_trade_sl``, never called live.
  * ``order_calc_margin``, ``freeze_level``, ``digits`` and ``filling_mode``
    appeared nowhere at all.
  * ``ORDER_FILLING_IOC`` was hardcoded at every call site. On an FOK-only
    broker every order fails with retcode 10030, is retried three times, raised
    and swallowed -- a silent, total outage that looks like "no signals today".

Everything here is pure given a ``SymbolSpec`` and an account snapshot, so it is
testable without a broker.
"""

from dataclasses import dataclass

from .symbol_spec import SymbolSpec  # noqa: F401  (re-exported for callers)

# Fraction of free margin a single order may consume.
DEFAULT_MARGIN_SAFETY_FRACTION = 0.25


@dataclass(frozen=True)
class Rejection:
    """A refusal to send an order, with a reason fit for a log line."""

    reason: str
    detail: str = ""

    def __bool__(self):
        # So `if validator.normalize(...)` reads as "did it pass".
        return False

    def __str__(self):
        return self.reason if not self.detail else "%s (%s)" % (self.reason, self.detail)


def normalize_volume(spec, volume):
    """Round volume DOWN to the broker's step, then bound it.

    Rounding down matters: rounding up silently increases risk beyond what the
    sizing calculation authorised.

    Returns:
        float volume, or a Rejection if it cannot be made tradeable.
    """
    volume = float(volume)
    if volume <= 0:
        return Rejection("volume must be positive", "got %r" % volume)

    steps = int(volume / spec.volume_step + 1e-9)   # floor, tolerating fp noise
    normalized = steps * spec.volume_step

    # Re-round to the step's own precision so 3 * 0.01 is 0.03, not 0.030000001.
    decimals = max(0, len(("%.10f" % spec.volume_step).rstrip("0").split(".")[1]))
    normalized = round(normalized, decimals)

    if normalized < spec.volume_min:
        return Rejection(
            "volume below broker minimum",
            "%g rounds down to %g, minimum is %g"
            % (volume, normalized, spec.volume_min),
        )

    if normalized > spec.volume_max:
        normalized = spec.volume_max

    return normalized


def enforce_stops_level(spec, price, sl, tp, is_buy):
    """Widen SL/TP so both clear the broker's minimum stop distance.

    The plan is explicit about the direction of the fix: **widen the stop, never
    shrink the position, and never silently drop the stop.** A stop the broker
    rejects is a position with no stop at all.

    Returns:
        (sl, tp) rounded to the symbol's precision. Either may be None if it was
        None on the way in.
    """
    min_distance = spec.price_from_points(spec.stops_level_points)

    if sl is not None:
        sl = float(sl)
        if is_buy:
            # SL sits below entry; push it further down if too close.
            sl = min(sl, price - min_distance)
        else:
            sl = max(sl, price + min_distance)
        sl = spec.round_price(sl)

    if tp is not None:
        tp = float(tp)
        if is_buy:
            tp = max(tp, price + min_distance)
        else:
            tp = min(tp, price - min_distance)
        tp = spec.round_price(tp)

    return sl, tp


def check_stops_are_sane(spec, price, sl, tp, is_buy):
    """Reject stops that are on the wrong side of the entry price."""
    if sl is not None:
        if is_buy and sl >= price:
            return Rejection("stop loss is above entry on a BUY",
                             "sl=%g price=%g" % (sl, price))
        if not is_buy and sl <= price:
            return Rejection("stop loss is below entry on a SELL",
                             "sl=%g price=%g" % (sl, price))
    if tp is not None:
        if is_buy and tp <= price:
            return Rejection("take profit is below entry on a BUY",
                             "tp=%g price=%g" % (tp, price))
        if not is_buy and tp >= price:
            return Rejection("take profit is above entry on a SELL",
                             "tp=%g price=%g" % (tp, price))
    return None


def check_margin(mt5, spec, order_type, volume, price,
                 safety_fraction=DEFAULT_MARGIN_SAFETY_FRACTION):
    """Refuse an order that would consume too much free margin."""
    try:
        required = mt5.order_calc_margin(order_type, spec.name, volume, price)
    except Exception as exc:                      # broker/terminal hiccup
        return Rejection("margin check failed", str(exc))

    if required is None:
        return Rejection("margin check failed",
                         "order_calc_margin returned None")

    account = mt5.account_info()
    if account is None:
        return Rejection("margin check failed", "account_info returned None")

    allowed = float(account.margin_free) * safety_fraction
    if float(required) > allowed:
        return Rejection(
            "insufficient free margin",
            "needs %.2f, only %.2f of %.2f free is allowed (%.0f%% cap)"
            % (required, allowed, account.margin_free, safety_fraction * 100),
        )
    return None


def choose_filling_mode(mt5, spec):
    """Pick a filling mode the broker actually supports.

    Tries IOC, then FOK, then RETURN, per the plan's ordered fallback. Falls
    back to IOC only if the bitmask is empty or unrecognised, which at least
    reproduces the previous behaviour rather than sending nothing.
    """
    modes = spec.filling_modes

    # SYMBOL_FILLING_FOK = 1, SYMBOL_FILLING_IOC = 2 in the MT5 API.
    # getattr alone is not enough: on a test double the attribute always
    # exists and returns something that is not an int, so coerce and fall
    # back to the documented values.
    def _flag(name, default):
        try:
            return int(getattr(mt5, name, default))
        except (TypeError, ValueError):
            return default

    fok_flag = _flag("SYMBOL_FILLING_FOK", 1)
    ioc_flag = _flag("SYMBOL_FILLING_IOC", 2)

    if modes & ioc_flag:
        return mt5.ORDER_FILLING_IOC
    if modes & fok_flag:
        return mt5.ORDER_FILLING_FOK
    if hasattr(mt5, "ORDER_FILLING_RETURN"):
        return mt5.ORDER_FILLING_RETURN
    return mt5.ORDER_FILLING_IOC


class OrderValidator:
    """Normalises and vets a market order against one symbol's real constraints."""

    def __init__(self, mt5, spec, safety_fraction=DEFAULT_MARGIN_SAFETY_FRACTION):
        self.mt5 = mt5
        self.spec = spec
        self.safety_fraction = safety_fraction

    def normalize(self, order_type, volume, price, sl=None, tp=None,
                  check_margin_too=True):
        """Return a dict of validated order fields, or a Rejection.

        The caller merges the returned fields into its request rather than
        building prices and volumes itself.
        """
        spec = self.spec
        is_buy = (order_type == self.mt5.ORDER_TYPE_BUY)

        volume = normalize_volume(spec, volume)
        if isinstance(volume, Rejection):
            return volume

        price = spec.round_price(price)
        sl, tp = enforce_stops_level(spec, price, sl, tp, is_buy)

        bad = check_stops_are_sane(spec, price, sl, tp, is_buy)
        if bad is not None:
            return bad

        if check_margin_too:
            bad = check_margin(self.mt5, spec, order_type, volume, price,
                               self.safety_fraction)
            if bad is not None:
                return bad

        return {
            "volume": volume,
            "price": price,
            "sl": sl,
            "tp": tp,
            "type_filling": choose_filling_mode(self.mt5, spec),
        }

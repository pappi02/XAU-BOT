"""
Professional Trading Configuration Overrides
For expert-level trading with improved win rates and trade frequency
"""

# Enhanced signal quality settings (relaxed for more trades)
PROFESSIONAL_SIGNAL_MIN_CONFIDENCE = 0.40    # Down from 0.55 for more entry opportunities
PROFESSIONAL_PATTERN_MIN_CONFIDENCE = 0.50   # Down from 0.65 for pattern validity
PROFESSIONAL_CONFLICT_PENALTY = 0.10         # Reduced from 0.20 to allow conflicted trades
PROFESSIONAL_RR_MINIMUM = 1.8                # Maintain strict RR for win rate

# News gating: less restrictive, more intelligent
PROFESSIONAL_NEWS_GATING_ENABLED = True      # Keep news awareness but allow trading
PROFESSIONAL_HIGH_IMPACT_GATE_BEFORE_MIN = 10  # Reduced from 15
PROFESSIONAL_HIGH_IMPACT_GATE_AFTER_MIN = 20   # Reduced from 30
PROFESSIONAL_MEDIUM_IMPACT_DEGRADE_ONLY = True # Degrade confidence instead of blocking

# Pattern detection: more lenient threshold to enable more trades
PROFESSIONAL_PATTERN_MIN_STRENGTH = 55.0     # Down from 65 to catch more opportunities
PROFESSIONAL_CONFLICTING_PATTERN_RATIO = 0.6 # Allow up to 60% opposite patterns

# Indicator smoothing: faster response to trend changes
PROFESSIONAL_SIGNAL_PERSISTENCE_WINDOW = 2   # Down from 3 for quicker entries
PROFESSIONAL_MIN_PERSISTENCE_RATIO = 0.50    # 50% agreement is sufficient

# Risk management: more aggressive position sizing
PROFESSIONAL_RISK_PER_TRADE_PCT = 0.5        # Up from 0.3% for higher returns
PROFESSIONAL_BASE_RISK_PERCENT = 2.0         # Professional standard

# Trailing stop: active profit protection
PROFESSIONAL_TRAILING_STOP_ENABLED = True
PROFESSIONAL_TRAIL_ACTIVATION_RR = 1.5       # Activate trail at 1.5x RR
PROFESSIONAL_TRAIL_DISTANCE_MULTIPLIER = 0.8 # 80% of ATR

# Multi-timeframe confirmation: optional for faster trades
PROFESSIONAL_MTF_CONFIRMATION_REQUIRED = False  # Not mandatory, just add to scoring
PROFESSIONAL_MTF_WEIGHT = 0.15                  # Light weight in scoring

# Adaptive engine: responsive to market conditions
PROFESSIONAL_ADAPTIVE_ENGINE_ENABLED = True
PROFESSIONAL_COOLDOWN_AFTER_LOSS_SEC = 30     # Brief cooldown to reset psychology
PROFESSIONAL_WIN_STREAK_TO_UPSHIFT = 3        # After 3 wins, increase risk
PROFESSIONAL_LOSS_STREAK_TO_DOWNSHIFT = 2     # After 2 losses, reduce risk

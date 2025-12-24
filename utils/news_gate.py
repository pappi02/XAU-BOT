"""
News and economic calendar aware signal filtering and degradation.
Integrates with signal_generator.py to gate or degrade signals during economic events.
"""

import logging
from typing import Dict, Tuple, Optional
from utils.economic_calendar import (
    EconomicCalendar, IMPACT_HIGH, IMPACT_MEDIUM, IMPACT_LOW
)

logger = logging.getLogger(__name__)


class NewsAwareSignalFilter:
    """
    Wraps signal generation with news/event awareness.
    - Gates signals during high-impact events (blocks trading)
    - Degrades signal strength near medium-impact events
    - Requires higher confidence near economic releases
    """
    
    def __init__(
        self,
        calendar: Optional[EconomicCalendar] = None,
        high_impact_gate_before_min: int = 15,
        high_impact_gate_after_min: int = 30,
        medium_impact_degrade_before_min: int = 30,
        medium_impact_degrade_after_min: int = 45,
    ):
        """
        Initialize filter.
        
        Args:
            calendar: EconomicCalendar instance (created if None)
            high_impact_gate_before_min: Minutes before high-impact event to gate (default 15)
            high_impact_gate_after_min: Minutes after high-impact event to gate (default 30)
            medium_impact_degrade_before_min: Minutes before medium-impact to degrade (default 30)
            medium_impact_degrade_after_min: Minutes after medium-impact to degrade (default 45)
        """
        self.calendar = calendar or EconomicCalendar()
        self.high_impact_gate_before = high_impact_gate_before_min
        self.high_impact_gate_after = high_impact_gate_after_min
        self.medium_impact_degrade_before = medium_impact_degrade_before_min
        self.medium_impact_degrade_after = medium_impact_degrade_after_min
    
    def should_gate_trading(self) -> Tuple[bool, Optional[str]]:
        """
        Determine if trading should be completely blocked due to news.
        
        Returns:
            Tuple: (should_gate, reason)
            - should_gate: True if no signals should be taken
            - reason: Description of event causing gate (e.g., "USD NFP at 13:30")
        """
        is_near, event_name, impact = self.calendar.is_near_event(
            buffer_minutes_before=self.high_impact_gate_before,
            buffer_minutes_after=self.high_impact_gate_after
        )
        
        if is_near and impact >= IMPACT_HIGH:
            logger.info(f"⚠️  Trading gated: {event_name} (high impact)")
            return (True, event_name)
        
        return (False, None)
    
    def apply_signal_filters(
        self,
        signal_dict: Dict,
        base_min_confidence: float = 0.65
    ) -> Dict:
        """
        Apply news-aware filtering and degradation to signal dict.
        
        Args:
            signal_dict: Signal dict with keys like 'type', 'confidence', 'reasons'
            base_min_confidence: Minimum confidence required (default 0.65)
        
        Returns:
            Modified signal_dict with:
            - Possible 'gated' flag if trading blocked
            - Modified 'confidence' if degraded
            - Added 'news_state' field describing event proximity
        """
        # Check if trading is gated
        should_gate, gate_reason = self.should_gate_trading()
        if should_gate:
            signal_dict["gated"] = True
            signal_dict["gate_reason"] = gate_reason
            signal_dict["confidence"] = 0.0  # Kill all confidence during high-impact events
            return signal_dict
        
        # Get degradation factor
        degrade_factor = self.calendar.get_signal_degradation_factor(
            buffer_minutes_before=self.medium_impact_degrade_before,
            buffer_minutes_after=self.medium_impact_degrade_after
        )
        
        # Apply degradation to confidence
        original_confidence = signal_dict.get("confidence", 0.0)
        degraded_confidence = original_confidence * degrade_factor
        
        if degrade_factor < 1.0:
            signal_dict["confidence_degradation"] = {
                "original": original_confidence,
                "factor": degrade_factor,
                "degraded": degraded_confidence
            }
            logger.info(
                f"Signal confidence degraded: "
                f"{original_confidence:.3f} → {degraded_confidence:.3f} "
                f"(factor={degrade_factor:.2f})"
            )
        
        signal_dict["confidence"] = degraded_confidence
        
        # Add news state to signal for logging/audit
        is_near, event_name, impact = self.calendar.is_near_event(
            buffer_minutes_before=self.medium_impact_degrade_before,
            buffer_minutes_after=self.medium_impact_degrade_after
        )
        
        if is_near:
            impact_name = {
                IMPACT_HIGH: "HIGH",
                IMPACT_MEDIUM: "MEDIUM",
                IMPACT_LOW: "LOW"
            }.get(impact, "UNKNOWN")
            signal_dict["news_state"] = f"Near {impact_name} impact event: {event_name}"
        else:
            signal_dict["news_state"] = "No nearby events"
        
        return signal_dict
    
    def require_higher_confidence_near_events(
        self,
        base_threshold: float = 0.65,
        adjustment_per_medium_event: float = 0.05,
        adjustment_per_high_event: float = 0.10
    ) -> float:
        """
        Calculate required confidence threshold based on news proximity.
        
        Returns dynamic threshold: base increases near economic events.
        
        Example:
        - Far from events: base_threshold (0.65)
        - 20 min before medium event: 0.65 + 0.05 = 0.70
        - 10 min before high event: 0.65 + 0.10 = 0.75
        
        Args:
            base_threshold: Base confidence threshold (default 0.65)
            adjustment_per_medium_event: Add this near medium events (default 0.05)
            adjustment_per_high_event: Add this near high events (default 0.10)
        
        Returns:
            Float between base_threshold and base_threshold + max adjustments
        """
        is_near, event_name, impact = self.calendar.is_near_event(
            buffer_minutes_before=max(
                self.medium_impact_degrade_before,
                self.high_impact_gate_before
            ),
            buffer_minutes_after=max(
                self.medium_impact_degrade_after,
                self.high_impact_gate_after
            )
        )
        
        if not is_near:
            return base_threshold
        
        adjustment = 0.0
        if impact >= IMPACT_HIGH:
            adjustment = adjustment_per_high_event
        elif impact >= IMPACT_MEDIUM:
            adjustment = adjustment_per_medium_event
        
        threshold = base_threshold + adjustment
        logger.debug(
            f"Confidence threshold adjusted from {base_threshold:.2f} "
            f"to {threshold:.2f} due to {event_name}"
        )
        return threshold


class NewsGateConfig:
    """Configuration for news gating behavior."""
    
    # Enable/disable gating entirely
    GATING_ENABLED = True
    
    # High-impact event windows (e.g., FOMC, NFP, ECB)
    HIGH_IMPACT_GATE_BEFORE_MIN = 15
    HIGH_IMPACT_GATE_AFTER_MIN = 30
    
    # Medium-impact event windows (e.g., ISM, retail sales)
    # These degrade signal confidence but don't block entirely
    MEDIUM_IMPACT_DEGRADE_BEFORE_MIN = 30
    MEDIUM_IMPACT_DEGRADE_AFTER_MIN = 45
    
    # Minimum confidence required
    BASE_MIN_CONFIDENCE = 0.65
    
    # Economic calendar API key (optional; uses fallback if not provided)
    CALENDAR_API_KEY = None

"""
Economic Calendar integration for trading news gating.
Prevents trading near high-impact economic events.
Supports fallback to manual calendar if API unavailable.
"""

import requests
import pytz
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import json
import logging

logger = logging.getLogger(__name__)

# Impact levels
IMPACT_HIGH = 3
IMPACT_MEDIUM = 2
IMPACT_LOW = 1
IMPACT_NONE = 0

# Countries/currencies of interest
TARGET_CURRENCIES = ["USD", "GOLD", "XAU", "EUR", "GBP", "JPY", "CHF"]

class EconomicCalendar:
    """
    Fetches economic calendar events and determines if trading should be gated.
    Primary: Investing.com API (free tier with rate limiting)
    Fallback: Manual high-impact events hardcoded
    """
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize calendar with optional API key.
        
        Args:
            api_key: Optional API key for Investing.com or similar service
        """
        self.api_key = api_key
        self.base_url = "https://api.investing.com/api/financialdata"
        self.events_cache = {}
        self.cache_timestamp = None
        self.cache_ttl_minutes = 60
        
        # Fallback: Manual high-impact events for major currencies
        # Updated approximately quarterly
        self.manual_events = [
            # Format: (country, event_name, typical_time_utc, impact_level)
            ("US", "FOMC Decision", "18:00", IMPACT_HIGH),
            ("US", "Fed Chair Press Conference", "19:30", IMPACT_HIGH),
            ("US", "Non-Farm Payroll", "13:30", IMPACT_HIGH),
            ("US", "Initial Jobless Claims", "13:30", IMPACT_HIGH),
            ("US", "CPI", "13:30", IMPACT_HIGH),
            ("US", "PPI", "13:30", IMPACT_HIGH),
            ("US", "Retail Sales", "13:30", IMPACT_HIGH),
            ("US", "Industrial Production", "15:15", IMPACT_HIGH),
            ("US", "Consumer Sentiment", "14:55", IMPACT_MEDIUM),
            ("US", "Durable Goods Orders", "13:30", IMPACT_MEDIUM),
            ("US", "Factory Orders", "14:00", IMPACT_MEDIUM),
            ("US", "ISM Manufacturing", "15:00", IMPACT_MEDIUM),
            ("US", "ISM Services", "15:00", IMPACT_MEDIUM),
            ("ECB", "Interest Rate Decision", "13:45", IMPACT_HIGH),
            ("ECB", "ECB President Press Conference", "14:30", IMPACT_HIGH),
            ("ECB", "Economic Bulletin", "10:00", IMPACT_MEDIUM),
            ("UK", "Bank of England Decision", "12:00", IMPACT_HIGH),
            ("UK", "BoE Governor Press Conference", "12:30", IMPACT_HIGH),
            ("JP", "Bank of Japan Decision", "06:30", IMPACT_HIGH),
            ("JP", "Japanese GDP", "08:50", IMPACT_HIGH),
            ("CH", "SNB Interest Rate Decision", "09:15", IMPACT_HIGH),
            ("AU", "RBA Decision", "05:30", IMPACT_HIGH),
        ]
    
    def fetch_events_from_api(self) -> List[Dict]:
        """
        Attempt to fetch real-time events from Investing.com API or similar.
        Returns empty list if API unavailable.
        
        Returns:
            List of event dicts with keys: datetime, country, event, impact, currency
        """
        if not self.api_key:
            logger.debug("No API key configured; skipping API call, using fallback")
            return []
        
        try:
            # Try Investing.com API (free tier)
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {
                "date_from": datetime.utcnow().isoformat(),
                "date_to": (datetime.utcnow() + timedelta(days=7)).isoformat(),
                "impacts": "high,medium",  # Filter to meaningful events
            }
            
            response = requests.get(
                f"{self.base_url}/calendar",
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            events = response.json().get("data", [])
            logger.info(f"Fetched {len(events)} events from API")
            return events
            
        except Exception as e:
            logger.warning(f"API fetch failed: {e}; using fallback manual events")
            return []
    
    def get_events_today_and_tomorrow(self) -> List[Tuple[datetime, str, str, int]]:
        """
        Get all relevant high/medium impact events for next 2 days.
        
        Returns:
            List of tuples: (event_datetime_utc, event_name, country, impact_level)
        """
        now = datetime.utcnow()
        cutoff = now + timedelta(days=2)
        
        events = []
        
        # Try API first
        api_events = self.fetch_events_from_api()
        for evt in api_events:
            try:
                evt_dt = datetime.fromisoformat(evt["datetime"].replace("Z", "+00:00"))
                if now <= evt_dt <= cutoff:
                    events.append((
                        evt_dt,
                        evt.get("event", "Unknown"),
                        evt.get("country", "Unknown"),
                        evt.get("impact", IMPACT_MEDIUM)
                    ))
            except Exception as e:
                logger.debug(f"Skipping malformed API event: {e}")
        
        # Add fallback manual events for today/tomorrow
        for country, event_name, time_str, impact in self.manual_events:
            try:
                hh, mm = map(int, time_str.split(":"))
                for day_offset in [0, 1]:
                    evt_date = (now + timedelta(days=day_offset)).date()
                    evt_dt = datetime.combine(evt_date, __import__("datetime").time(hh, mm))
                    evt_dt = pytz.utc.localize(evt_dt)
                    
                    if now <= evt_dt <= cutoff:
                        # Avoid duplicates from API
                        if not any(
                            abs((e[0] - evt_dt).total_seconds()) < 300
                            for e in events
                        ):
                            events.append((evt_dt, event_name, country, impact))
            except Exception as e:
                logger.debug(f"Skipping manual event {event_name}: {e}")
        
        return sorted(events, key=lambda x: x[0])
    
    def is_near_event(
        self,
        buffer_minutes_before: int = 15,
        buffer_minutes_after: int = 30
    ) -> Tuple[bool, Optional[str], Optional[int]]:
        """
        Check if current time is within buffer zone of any high-impact event.
        
        Args:
            buffer_minutes_before: Minutes before event to start gating (default 15)
            buffer_minutes_after: Minutes after event to continue gating (default 30)
        
        Returns:
            Tuple: (is_gated, event_name, impact_level)
            - is_gated: True if trading should be avoided
            - event_name: Name of nearest event (if gated)
            - impact_level: Impact of event (3=high, 2=medium, 1=low)
        """
        now = datetime.utcnow()
        now = pytz.utc.localize(now) if now.tzinfo is None else now
        
        events = self.get_events_today_and_tomorrow()
        
        for evt_dt, evt_name, evt_country, impact in events:
            window_start = evt_dt - timedelta(minutes=buffer_minutes_before)
            window_end = evt_dt + timedelta(minutes=buffer_minutes_after)
            
            if window_start <= now <= window_end:
                logger.warning(
                    f"News gate active: {evt_country} {evt_name} "
                    f"impact={impact} at {evt_dt.isoformat()}"
                )
                return (True, f"{evt_country} {evt_name}", impact)
        
        return (False, None, None)
    
    def get_signal_degradation_factor(
        self,
        buffer_minutes_before: int = 15,
        buffer_minutes_after: int = 30
    ) -> float:
        """
        Get signal strength multiplier based on proximity to economic events.
        
        Example:
        - Far from events: returns 1.0 (no degradation)
        - Within 15 min before event: returns 0.8 (20% reduction)
        - Within 30 min after event: returns 0.6 (40% reduction)
        - Very close to high-impact: returns 0.3 (70% reduction)
        
        Args:
            buffer_minutes_before: Minutes before event to start degrading (default 15)
            buffer_minutes_after: Minutes after event to continue degrading (default 30)
        
        Returns:
            Float between 0.3 (heavily degraded) and 1.0 (full strength)
        """
        now = datetime.utcnow()
        now = pytz.utc.localize(now) if now.tzinfo is None else now
        
        events = self.get_events_today_and_tomorrow()
        closest_distance_minutes = float('inf')
        closest_impact = IMPACT_NONE
        
        for evt_dt, evt_name, evt_country, impact in events:
            distance = abs((evt_dt - now).total_seconds() / 60.0)
            
            if distance < closest_distance_minutes:
                closest_distance_minutes = distance
                closest_impact = impact
        
        # Determine degradation based on distance and impact
        if closest_distance_minutes > buffer_minutes_before + buffer_minutes_after:
            return 1.0  # Far from events
        
        # Scale degradation by impact level and proximity
        base_degradation = 1.0 - (closest_impact / 10.0)  # High (3) → 0.7, Medium (2) → 0.8
        
        if closest_distance_minutes <= buffer_minutes_before:
            # Approaching event: heavy degradation
            proximity_factor = 0.3
        elif closest_distance_minutes <= buffer_minutes_before + buffer_minutes_after:
            # Shortly after event: moderate degradation
            proximity_factor = 0.6
        else:
            # Far from event
            proximity_factor = 1.0
        
        factor = base_degradation * proximity_factor
        return max(0.3, min(1.0, factor))  # Clamp to [0.3, 1.0]


def create_calendar_instance(api_key: Optional[str] = None) -> EconomicCalendar:
    """Factory for creating calendar instance with optional API key."""
    return EconomicCalendar(api_key=api_key)

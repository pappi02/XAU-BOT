"""
Trading Session Manager for Scalping

Optimizes scalping strategies based on market sessions:
- London Session (08:00-16:00 GMT): High volatility, tight spreads
- New York Session (13:00-21:00 GMT): Highest volume
- London/NY Overlap (13:00-16:00 GMT): Peak liquidity
- Asian Session (00:00-08:00 GMT): Lower volatility, wider spreads

Adjusts:
- Signal aggressiveness (more signals during peak hours)
- Risk parameters (tighter stops during low volatility)
- Position limits (more positions during liquid sessions)
"""

from datetime import datetime, time
from typing import Dict, Optional
from logger_config import setup_logger
import pytz

logger = setup_logger()


class SessionManager:
    """
    Manage trading behavior based on market session.
    
    Session Characteristics:
    - London Open (08:00-16:00 GMT): XAUUSD most active, tight spreads
    - NY Open (13:00-21:00 GMT): Major news releases, high volume
    - Overlap (13:00-16:00 GMT): BEST for scalping (peak liquidity)
    - Asian (00:00-08:00 GMT): Lower volume, avoid or reduce activity
    """
    
    def __init__(self, config: dict = None):
        """
        Initialize session manager.
        
        Args:
            config: Configuration with session preferences
        """
        self.config = config or {}
        self.backtest_mode = self.config.get('backtest_mode', False)
        # Session filter: ON for live trading, OFF for backtest by default
        self.session_filter_enabled = self.config.get('session_filter_enabled', not self.backtest_mode)
        
        # Session times (GMT)
        self.sessions = {
            'asian': {
                'start': time(0, 0),
                'end': time(8, 0),
                'name': 'Asian',
                'volatility': 'low',
                'recommended': False
            },
            'london': {
                'start': time(8, 0),
                'end': time(16, 0),
                'name': 'London',
                'volatility': 'high',
                'recommended': True
            },
            'ny': {
                'start': time(13, 0),
                'end': time(21, 0),
                'name': 'New York',
                'volatility': 'high',
                'recommended': True
            },
            'overlap': {
                'start': time(13, 0),
                'end': time(16, 0),
                'name': 'London/NY Overlap',
                'volatility': 'peak',
                'recommended': True  # BEST session
            }
        }
        
        # Backtest mode: Use neutral multipliers to test without session bias
        if self.backtest_mode:
            neutral_multiplier = {
                'position_limit': 1.0,
                'signal_threshold': 1.0,  # No adjustment
                'max_spread': 2.0,
                'risk_per_trade': 1.0,
                'min_confidence': 55  # Use base confidence
            }
            self.session_multipliers = {
                'asian': neutral_multiplier.copy(),
                'london': neutral_multiplier.copy(),
                'ny': neutral_multiplier.copy(),
                'overlap': neutral_multiplier.copy()
            }
            logger.info("SessionManager: BACKTEST MODE - Session filters disabled")
        else:
            # Session multipliers for scalping parameters (EXPERT OPTIMIZED)
            # Based on backtest: NY=58% WR, London=47% WR, Overlap=48% WR
            self.session_multipliers = {
            'asian': {
                'position_limit': 0.4,  # Low capacity but allow some trades
                'signal_threshold': 1.3,  # Higher confidence
                'max_spread': 1.5,
                'risk_per_trade': 0.6,
                'min_confidence': 65  # BALANCED: Reduced from 75%
            },
            'london': {
                'position_limit': 0.8,  # Moderate capacity
                'signal_threshold': 1.1,  # BALANCED: Reduced slightly
                'max_spread': 1.8,
                'risk_per_trade': 0.9,
                'min_confidence': 58  # BALANCED: Reduced from 70%
            },
            'ny': {
                'position_limit': 1.0,  # FULL capacity (BEST session: 58% WR)
                'signal_threshold': 1.0,  # Standard threshold
                'max_spread': 2.0,
                'risk_per_trade': 1.0,
                'min_confidence': 55  # BALANCED: Reduced from 65%
            },
            'overlap': {
                'position_limit': 0.9,  # High capacity but not full (48% WR)
                'signal_threshold': 1.05,  # BALANCED: Reduced slightly
                'max_spread': 2.0,
                'risk_per_trade': 1.0,
                'min_confidence': 56  # BALANCED: Reduced from 68%
            }
        }
        
        # GMT timezone
        self.gmt = pytz.timezone('GMT')
        
        logger.info("SessionManager initialized")
        logger.info(f"  Sessions configured: {len(self.sessions)}")
    
    def get_current_session(self, current_time: Optional[datetime] = None) -> Dict:
        """
        Get current trading session based on GMT time.
        
        Args:
            current_time: Time to check (defaults to now)
            
        Returns:
            dict: Session info with multipliers
        """
        if current_time is None:
            current_time = datetime.now(self.gmt)
        elif current_time.tzinfo is None:
            # Assume UTC if no timezone
            current_time = pytz.utc.localize(current_time).astimezone(self.gmt)
        
        current_time_only = current_time.time()
        
        # Check overlap first (priority)
        if self._time_in_range(current_time_only, 
                               self.sessions['overlap']['start'], 
                               self.sessions['overlap']['end']):
            session_key = 'overlap'
        # Check other sessions
        elif self._time_in_range(current_time_only,
                                 self.sessions['london']['start'],
                                 self.sessions['london']['end']):
            session_key = 'london'
        elif self._time_in_range(current_time_only,
                                 self.sessions['ny']['start'],
                                 self.sessions['ny']['end']):
            session_key = 'ny'
        elif self._time_in_range(current_time_only,
                                 self.sessions['asian']['start'],
                                 self.sessions['asian']['end']):
            session_key = 'asian'
        else:
            # Outside main sessions (late US/early Asian)
            session_key = 'asian'  # Use Asian settings as default low-volume
        
        session_info = self.sessions[session_key].copy()
        session_info['key'] = session_key
        session_info['multipliers'] = self.session_multipliers[session_key]
        session_info['current_time'] = current_time.strftime('%H:%M:%S GMT')
        
        return session_info
    
    def _time_in_range(self, check_time: time, start_time: time, end_time: time) -> bool:
        """Check if time is within range."""
        if start_time <= end_time:
            return start_time <= check_time <= end_time
        else:  # Crosses midnight
            return check_time >= start_time or check_time <= end_time
    
    def adjust_parameters_for_session(self, base_params: Dict) -> Dict:
        """
        Adjust trading parameters based on current session.
        
        Args:
            base_params: Base parameters (max_positions, signal_threshold, etc.)
            
        Returns:
            dict: Adjusted parameters
        """
        # If session filter disabled (backtest mode), return base params without adjustment
        if not self.session_filter_enabled:
            logger.info("Session filter disabled - using base parameters without adjustment")
            return base_params.copy()
        
        current_session = self.get_current_session()
        multipliers = current_session['multipliers']
        
        adjusted = base_params.copy()
        
        # Apply multipliers
        if 'max_positions' in base_params:
            adjusted['max_positions'] = int(base_params['max_positions'] * multipliers['position_limit'])
        
        if 'signal_confidence_threshold' in base_params:
            adjusted['signal_confidence_threshold'] = base_params['signal_confidence_threshold'] * multipliers['signal_threshold']
        
        if 'max_spread_pips' in base_params:
            adjusted['max_spread_pips'] = base_params['max_spread_pips'] * multipliers['max_spread']
        
        if 'risk_per_trade_pct' in base_params:
            adjusted['risk_per_trade_pct'] = base_params['risk_per_trade_pct'] * multipliers['risk_per_trade']
        
        logger.info(f"Parameters adjusted for {current_session['name']} session")
        logger.info(f"  Max positions: {base_params.get('max_positions')} → {adjusted.get('max_positions')}")
        logger.info(f"  Signal threshold: {base_params.get('signal_confidence_threshold', 0):.0f}% → {adjusted.get('signal_confidence_threshold', 0):.0f}%")
        
        return adjusted
    
    def should_trade_in_session(self, current_time: Optional[datetime] = None, signal_confidence: float = 0, 
                                strict_filter: bool = True) -> tuple[bool, str]:
        """
        Determine if trading is recommended in current session (EXPERT OPTIMIZED).
        
        Args:
            current_time: Time to check (defaults to now)
            signal_confidence: Signal confidence percentage
            strict_filter: If False, only basic checks (for backtesting with limited data)
            
        Returns:
            (should_trade: bool, reason: str)
        """
        session = self.get_current_session(current_time)
        
        # If session filter disabled (backtest mode), allow all sessions
        if not self.session_filter_enabled:
            return True, f"{session['name']} session (session filter disabled)"
        
        # If not using strict filter (backtest with limited data), allow all sessions
        if not strict_filter:
            return True, f"{session['name']} session (backtest mode)"
        
        # EXPERT: Check minimum confidence for session
        min_confidence = session['multipliers'].get('min_confidence', 60)
        if signal_confidence > 0 and signal_confidence < min_confidence:
            return False, f"{session['name']} requires {min_confidence}% confidence (signal: {signal_confidence:.0f}%)"
        
        # EXPERT: Time-of-day filters for high-probability windows
        if current_time is None:
            current_time = datetime.now(self.gmt)
        current_hour = current_time.hour
        
        # Avoid first hour of Asian session (lowest liquidity)
        if session['key'] == 'asian' and 0 <= current_hour < 1:
            return False, "Asian session first hour (lowest liquidity)"
        
        # NY session: Focus on first 4 hours (13:00-17:00) - best volume
        if session['key'] == 'ny' and current_hour >= 19:
            return False, "Late NY session (reduced activity)"
        
        # London session: Avoid last hour (overlap starts)
        if session['key'] == 'london' and current_hour >= 15:
            return False, "Late London session (wait for overlap)"
        
        if session['recommended']:
            return True, f"{session['name']} session (recommended)"
        else:
            return False, f"{session['name']} session (low liquidity)"
    
    def get_optimal_position_count(self, base_max: int) -> int:
        """
        Get optimal position count for current session.
        
        Args:
            base_max: Base maximum positions
            
        Returns:
            int: Adjusted maximum positions
        """
        session = self.get_current_session()
        multiplier = session['multipliers']['position_limit']
        return int(base_max * multiplier)
    
    def get_session_statistics(self) -> Dict:
        """
        Get statistics about all sessions.
        
        Returns:
            dict: Session statistics
        """
        current = self.get_current_session()
        
        stats = {
            'current_session': current['name'],
            'current_session_key': current['key'],
            'recommended': current['recommended'],
            'volatility': current['volatility'],
            'time': current['current_time'],
            'all_sessions': {}
        }
        
        for key, session in self.sessions.items():
            stats['all_sessions'][key] = {
                'name': session['name'],
                'hours': f"{session['start'].strftime('%H:%M')} - {session['end'].strftime('%H:%M')} GMT",
                'recommended': session['recommended'],
                'volatility': session['volatility']
            }
        
        return stats
    
    def get_next_session_change(self, current_time: Optional[datetime] = None) -> Dict:
        """
        Get time until next session change.
        
        Args:
            current_time: Time to check (defaults to now)
            
        Returns:
            dict: Next session info and time until change
        """
        if current_time is None:
            current_time = datetime.now(self.gmt)
        
        current_session = self.get_current_session(current_time)
        current_key = current_session['key']
        
        # Define session order (wrap around)
        session_order = ['asian', 'london', 'overlap', 'ny']
        
        # Get next session
        current_idx = session_order.index(current_key) if current_key in session_order else 0
        next_idx = (current_idx + 1) % len(session_order)
        next_key = session_order[next_idx]
        
        next_session = self.sessions[next_key]
        next_start = next_session['start']
        
        # Calculate time until next session
        current_time_only = current_time.time()
        
        # Simple time difference (doesn't account for date changes perfectly, but good enough)
        current_minutes = current_time_only.hour * 60 + current_time_only.minute
        next_minutes = next_start.hour * 60 + next_start.minute
        
        if next_minutes > current_minutes:
            minutes_until = next_minutes - current_minutes
        else:
            minutes_until = (24 * 60 - current_minutes) + next_minutes
        
        hours_until = minutes_until // 60
        mins_until = minutes_until % 60
        
        return {
            'next_session': next_session['name'],
            'next_session_key': next_key,
            'time_until': f"{hours_until}h {mins_until}m",
            'minutes_until': minutes_until,
            'next_recommended': next_session['recommended']
        }


if __name__ == "__main__":
    print("=" * 80)
    print("SESSION MANAGER TEST")
    print("=" * 80)
    
    manager = SessionManager()
    
    # Test 1: Current session
    print("\n1. Current Session:")
    current = manager.get_current_session()
    print(f"  Session: {current['name']}")
    print(f"  Time: {current['current_time']}")
    print(f"  Volatility: {current['volatility']}")
    print(f"  Recommended: {current['recommended']}")
    print(f"  Multipliers:")
    for key, value in current['multipliers'].items():
        print(f"    {key}: {value}")
    
    # Test 2: Should trade?
    print("\n2. Trading Recommendation:")
    should_trade, reason = manager.should_trade_in_session()
    print(f"  Should trade: {should_trade}")
    print(f"  Reason: {reason}")
    
    # Test 3: Parameter adjustment
    print("\n3. Parameter Adjustment:")
    base_params = {
        'max_positions': 50,
        'signal_confidence_threshold': 60,
        'max_spread_pips': 2.0,
        'risk_per_trade_pct': 0.5
    }
    adjusted = manager.adjust_parameters_for_session(base_params)
    print(f"  Base max positions: {base_params['max_positions']}")
    print(f"  Adjusted max positions: {adjusted['max_positions']}")
    print(f"  Base signal threshold: {base_params['signal_confidence_threshold']}%")
    print(f"  Adjusted signal threshold: {adjusted['signal_confidence_threshold']:.0f}%")
    
    # Test 4: Session statistics
    print("\n4. All Sessions:")
    stats = manager.get_session_statistics()
    for key, session in stats['all_sessions'].items():
        print(f"  {session['name']}: {session['hours']}")
        print(f"    Recommended: {session['recommended']}, Volatility: {session['volatility']}")
    
    # Test 5: Next session
    print("\n5. Next Session Change:")
    next_session = manager.get_next_session_change()
    print(f"  Next: {next_session['next_session']}")
    print(f"  In: {next_session['time_until']}")
    print(f"  Recommended: {next_session['next_recommended']}")
    
    # Test 6: Specific time tests
    print("\n6. Session Tests at Specific Times:")
    test_times = [
        datetime(2024, 1, 15, 3, 0),   # Asian
        datetime(2024, 1, 15, 10, 0),  # London
        datetime(2024, 1, 15, 14, 30), # Overlap
        datetime(2024, 1, 15, 18, 0),  # NY
    ]
    
    for test_time in test_times:
        gmt_time = pytz.utc.localize(test_time)
        session = manager.get_current_session(gmt_time)
        print(f"  {test_time.strftime('%H:%M')}: {session['name']} ({session['volatility']})")
    
    print("\n✅ Test complete")

# ema.py - Exponential Moving Average indicator

import pandas as pd
import numpy as np

def calculate_ema(data, period=14, column='close'):
    """
    Calculate Exponential Moving Average (EMA).

    Args:
        data (pd.DataFrame): OHLC data
        period (int): EMA period (default: 14)
        column (str): Column to calculate EMA on (default: 'close')

    Returns:
        pd.Series: EMA values
    """
    if column not in data.columns:
        raise ValueError(f"Column '{column}' not found in data")

    return data[column].ewm(span=period, adjust=False).mean()

def add_ema_signals(data, fast_period=12, slow_period=26, column='close'):
    """
    Add EMA crossover signals to data.

    Args:
        data (pd.DataFrame): OHLC data
        fast_period (int): Fast EMA period
        slow_period (int): Slow EMA period
        column (str): Column to calculate EMA on

    Returns:
        pd.DataFrame: Data with EMA signals added
    """
    df = data.copy()

    # Calculate EMAs
    df[f'EMA_{fast_period}'] = calculate_ema(df, fast_period, column)
    df[f'EMA_{slow_period}'] = calculate_ema(df, slow_period, column)

    # Generate signals
    df['EMA_signal'] = 0
    df.loc[df[f'EMA_{fast_period}'] > df[f'EMA_{slow_period}'], 'EMA_signal'] = 1  # Bullish
    df.loc[df[f'EMA_{fast_period}'] < df[f'EMA_{slow_period}'], 'EMA_signal'] = -1  # Bearish

    # Detect crossovers
    df['EMA_crossover'] = 0
    df.loc[(df[f'EMA_{fast_period}'].shift(1) <= df[f'EMA_{slow_period}'].shift(1)) &
           (df[f'EMA_{fast_period}'] > df[f'EMA_{slow_period}']), 'EMA_crossover'] = 1  # Bullish crossover

    df.loc[(df[f'EMA_{fast_period}'].shift(1) >= df[f'EMA_{slow_period}'].shift(1)) &
           (df[f'EMA_{fast_period}'] < df[f'EMA_{slow_period}']), 'EMA_crossover'] = -1  # Bearish crossover

    return df

def get_ema_trend(data, period=14, column='close'):
    """
    Get EMA trend direction.

    Args:
        data (pd.DataFrame): OHLC data
        period (int): EMA period
        column (str): Column to calculate EMA on

    Returns:
        int: 1 (uptrend), -1 (downtrend), 0 (sideways)
    """
    ema = calculate_ema(data, period, column)
    close = data[column].values

    # Determine trend based on price vs EMA
    if close[-1] > ema.iloc[-1]:
        return 1  # Uptrend
    elif close[-1] < ema.iloc[-1]:
        return -1  # Downtrend
    else:
        return 0  # Sideways

def get_ema_crossover_signal(fast_ema, slow_ema):
    """
    Detect EMA crossover signal.

    Args:
        fast_ema (pd.Series): Fast EMA values
        slow_ema (pd.Series): Slow EMA values

    Returns:
        int: 1 (bullish crossover), -1 (bearish crossover), 0 (no crossover)
    """
    if len(fast_ema) < 2 or len(slow_ema) < 2:
        return 0
    
    # Check if crossover happened
    if fast_ema.iloc[-2] <= slow_ema.iloc[-2] and fast_ema.iloc[-1] > slow_ema.iloc[-1]:
        return 1  # Bullish crossover
    elif fast_ema.iloc[-2] >= slow_ema.iloc[-2] and fast_ema.iloc[-1] < slow_ema.iloc[-1]:
        return -1  # Bearish crossover
    else:
        return 0  # No crossover

def is_bullish_ema(data, fast_period=12, slow_period=26, column='close'):
    """
    Check if EMA indicates bullish trend.

    Args:
        data (pd.DataFrame): OHLC data
        fast_period (int): Fast EMA period
        slow_period (int): Slow EMA period
        column (str): Column to calculate on

    Returns:
        bool: True if bullish
    """
    fast_ema = calculate_ema(data, fast_period, column)
    slow_ema = calculate_ema(data, slow_period, column)
    
    return fast_ema.iloc[-1] > slow_ema.iloc[-1]

def is_bearish_ema(data, fast_period=12, slow_period=26, column='close'):
    """
    Check if EMA indicates bearish trend.

    Args:
        data (pd.DataFrame): OHLC data
        fast_period (int): Fast EMA period
        slow_period (int): Slow EMA period
        column (str): Column to calculate on

    Returns:
        bool: True if bearish
    """
    fast_ema = calculate_ema(data, fast_period, column)
    slow_ema = calculate_ema(data, slow_period, column)
    
    return fast_ema.iloc[-1] < slow_ema.iloc[-1]

def calculate_ema_stack(data, periods=None, column='close'):
    """
    Calculate multiple EMAs for scalping stack analysis.
    
    Default scalping stack: 8, 13, 21 (Fibonacci-based fast periods)
    Traditional stack: 9, 20, 50
    
    Args:
        data (pd.DataFrame): OHLC data
        periods (list): List of EMA periods (default: [8, 13, 21])
        column (str): Column to calculate EMA on (default: 'close')
    
    Returns:
        dict: Dictionary with period as key and EMA series as value
            Example: {8: Series(...), 13: Series(...), 21: Series(...)}
    """
    if periods is None:
        periods = [8, 13, 21]  # Scalping stack default
    
    ema_stack = {}
    for period in periods:
        ema_stack[period] = calculate_ema(data, period, column)
    
    return ema_stack

def is_ema_stack_bullish(data, periods=None, column='close'):
    """
    Check if EMA stack indicates bullish alignment.
    
    Bullish: Fastest EMA > Middle EMA > Slowest EMA
    Example: EMA(8) > EMA(13) > EMA(21)
    
    This indicates strong uptrend momentum suitable for scalping longs.
    
    Args:
        data (pd.DataFrame): OHLC data
        periods (list): List of EMA periods (default: [8, 13, 21])
        column (str): Column to calculate on
    
    Returns:
        bool: True if stack is bullish aligned
    """
    if periods is None:
        periods = [8, 13, 21]
    
    if len(periods) < 2:
        raise ValueError("At least 2 periods required for stack analysis")
    
    ema_stack = calculate_ema_stack(data, periods, column)
    sorted_periods = sorted(periods)
    
    # Check if EMAs are in ascending order (fastest > ... > slowest)
    for i in range(len(sorted_periods) - 1):
        fast = ema_stack[sorted_periods[i]].iloc[-1]
        slow = ema_stack[sorted_periods[i + 1]].iloc[-1]
        
        if fast <= slow:
            return False
    
    return True

def is_ema_stack_bearish(data, periods=None, column='close'):
    """
    Check if EMA stack indicates bearish alignment.
    
    Bearish: Fastest EMA < Middle EMA < Slowest EMA
    Example: EMA(8) < EMA(13) < EMA(21)
    
    This indicates strong downtrend momentum suitable for scalping shorts.
    
    Args:
        data (pd.DataFrame): OHLC data
        periods (list): List of EMA periods (default: [8, 13, 21])
        column (str): Column to calculate on
    
    Returns:
        bool: True if stack is bearish aligned
    """
    if periods is None:
        periods = [8, 13, 21]
    
    if len(periods) < 2:
        raise ValueError("At least 2 periods required for stack analysis")
    
    ema_stack = calculate_ema_stack(data, periods, column)
    sorted_periods = sorted(periods)
    
    # Check if EMAs are in descending order (fastest < ... < slowest)
    for i in range(len(sorted_periods) - 1):
        fast = ema_stack[sorted_periods[i]].iloc[-1]
        slow = ema_stack[sorted_periods[i + 1]].iloc[-1]
        
        if fast >= slow:
            return False
    
    return True

def get_ema_stack_alignment(data, periods=None, column='close'):
    """
    Get detailed EMA stack alignment analysis.
    
    Returns a comprehensive view of the stack structure including:
    - Alignment type (bullish, bearish, mixed)
    - Spacing between EMAs (tight = consolidation, wide = trending)
    - Price position relative to stack
    
    Args:
        data (pd.DataFrame): OHLC data
        periods (list): List of EMA periods (default: [8, 13, 21])
        column (str): Column to calculate on
    
    Returns:
        dict: {
            'alignment': str ('bullish', 'bearish', 'mixed'),
            'strength': float (0-100, based on spacing and order),
            'price_position': str ('above_all', 'below_all', 'within_stack'),
            'spacing': str ('tight', 'normal', 'wide'),
            'emas': dict of current EMA values
        }
    """
    if periods is None:
        periods = [8, 13, 21]
    
    ema_stack = calculate_ema_stack(data, periods, column)
    sorted_periods = sorted(periods)
    current_price = data[column].iloc[-1]
    
    # Get EMA values
    ema_values = {p: ema_stack[p].iloc[-1] for p in sorted_periods}
    
    # Determine alignment
    if is_ema_stack_bullish(data, periods, column):
        alignment = 'bullish'
    elif is_ema_stack_bearish(data, periods, column):
        alignment = 'bearish'
    else:
        alignment = 'mixed'
    
    # Calculate spacing (as percentage of price)
    min_ema = min(ema_values.values())
    max_ema = max(ema_values.values())
    spacing_pct = ((max_ema - min_ema) / current_price) * 100
    
    if spacing_pct < 0.1:
        spacing = 'tight'  # Consolidation
    elif spacing_pct < 0.3:
        spacing = 'normal'
    else:
        spacing = 'wide'  # Strong trend
    
    # Price position
    if current_price > max_ema:
        price_position = 'above_all'
    elif current_price < min_ema:
        price_position = 'below_all'
    else:
        price_position = 'within_stack'
    
    # Calculate strength (0-100)
    # Perfect alignment = 100, random = 0
    if alignment in ['bullish', 'bearish']:
        # Base strength from proper ordering
        base_strength = 60
        
        # Bonus for price position
        if alignment == 'bullish' and price_position == 'above_all':
            base_strength += 20
        elif alignment == 'bearish' and price_position == 'below_all':
            base_strength += 20
        
        # Bonus for wide spacing (strong trend)
        if spacing == 'wide':
            base_strength += 20
        elif spacing == 'normal':
            base_strength += 10
        
        strength = min(100, base_strength)
    else:
        # Mixed alignment = weak signal
        strength = 30
    
    return {
        'alignment': alignment,
        'strength': strength,
        'price_position': price_position,
        'spacing': spacing,
        'emas': ema_values,
        'spacing_pct': spacing_pct
    }

def add_ema_stack_signals(data, periods=None, column='close'):
    """
    Add EMA stack columns and signals to DataFrame.
    
    Args:
        data (pd.DataFrame): OHLC data
        periods (list): List of EMA periods (default: [8, 13, 21])
        column (str): Column to calculate on
    
    Returns:
        pd.DataFrame: Data with EMA stack columns added:
            - EMA_8, EMA_13, EMA_21 (or custom periods)
            - ema_stack_signal: 1 (bullish), -1 (bearish), 0 (mixed)
            - ema_stack_strength: 0-100 alignment strength
    """
    if periods is None:
        periods = [8, 13, 21]
    
    df = data.copy()
    
    # Calculate all EMAs
    ema_stack = calculate_ema_stack(df, periods, column)
    for period, values in ema_stack.items():
        df[f'EMA_{period}'] = values
    
    # Add alignment signal and strength
    alignment = get_ema_stack_alignment(df, periods, column)
    
    if alignment['alignment'] == 'bullish':
        df['ema_stack_signal'] = 1
    elif alignment['alignment'] == 'bearish':
        df['ema_stack_signal'] = -1
    else:
        df['ema_stack_signal'] = 0
    
    df['ema_stack_strength'] = alignment['strength']
    
    return df

if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    prices = 1800 + np.cumsum(np.random.randn(100) * 5)
    sample_data = pd.DataFrame({'close': prices}, index=dates)

    # Calculate EMA
    ema_14 = calculate_ema(sample_data, period=14)
    print("📊 EMA(14) calculated:")
    print(ema_14.tail())

    # Add signals
    data_with_signals = add_ema_signals(sample_data)
    print("\n📈 Data with EMA signals:")
    print(data_with_signals[['close', 'EMA_12', 'EMA_26', 'EMA_signal', 'EMA_crossover']].tail())

    # Get trend
    trend = get_ema_trend(sample_data)
    print(f"\n📊 Current EMA trend: {trend}")

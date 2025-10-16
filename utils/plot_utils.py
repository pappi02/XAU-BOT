# plot_utils.py - Utility functions for plotting trading data and indicators

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from datetime import datetime

def plot_price_with_indicators(data, title="Price Chart with Indicators", figsize=(14, 10)):
    """
    Plot price chart with technical indicators.

    Args:
        data (pd.DataFrame): OHLC data with indicators
        title (str): Chart title
        figsize (tuple): Figure size
    """
    fig, axes = plt.subplots(4, 1, figsize=figsize, sharex=True)
    fig.suptitle(title, fontsize=16, fontweight='bold')

    # Price and EMAs
    axes[0].plot(data.index, data['close'], label='Close Price', color='black', linewidth=1.5)

    # Plot EMAs if available
    ema_cols = [col for col in data.columns if col.startswith('EMA_') and not col.endswith('_signal')]
    for col in ema_cols:
        period = col.split('_')[1]
        axes[0].plot(data.index, data[col], label=f'EMA {period}', alpha=0.8)

    axes[0].set_title('Price & Moving Averages')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)

    # Bollinger Bands
    if all(col in data.columns for col in ['BB_upper_20', 'BB_middle_20', 'BB_lower_20']):
        axes[0].plot(data.index, data['BB_upper_20'], label='BB Upper', color='red', linestyle='--', alpha=0.7)
        axes[0].plot(data.index, data['BB_middle_20'], label='BB Middle', color='blue', linestyle='--', alpha=0.7)
        axes[0].plot(data.index, data['BB_lower_20'], label='BB Lower', color='green', linestyle='--', alpha=0.7)
        axes[0].fill_between(data.index, data['BB_upper_20'], data['BB_lower_20'], alpha=0.1, color='blue')

    # RSI
    if 'RSI_14' in data.columns:
        axes[1].plot(data.index, data['RSI_14'], label='RSI', color='purple')
        axes[1].axhline(y=70, color='red', linestyle='--', alpha=0.7, label='Overbought (70)')
        axes[1].axhline(y=30, color='green', linestyle='--', alpha=0.7, label='Oversold (30)')
        axes[1].axhline(y=50, color='gray', linestyle='-', alpha=0.5, label='Neutral (50)')
        axes[1].set_title('Relative Strength Index (RSI)')
        axes[1].set_ylim(0, 100)
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)

    # Volume (if available)
    if 'tick_volume' in data.columns:
        axes[2].bar(data.index, data['tick_volume'], label='Volume', color='blue', alpha=0.7)
        axes[2].set_title('Volume')
        axes[2].legend()
        axes[2].grid(True, alpha=0.3)

    # Signals
    if 'EMA_signal' in data.columns:
        signal_colors = {1: 'green', -1: 'red', 0: 'gray'}
        signal_labels = {1: 'Bullish', -1: 'Bearish', 0: 'Neutral'}

        for signal_val in [-1, 0, 1]:
            mask = data['EMA_signal'] == signal_val
            axes[3].scatter(data.index[mask], data.loc[mask, 'close'],
                          color=signal_colors[signal_val],
                          label=signal_labels[signal_val],
                          s=20, alpha=0.7)

    axes[3].plot(data.index, data['close'], color='black', alpha=0.5, linewidth=1)
    axes[3].set_title('Trading Signals')
    axes[3].legend()
    axes[3].grid(True, alpha=0.3)

    # Format x-axis
    plt.xticks(rotation=45)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=1))

    plt.tight_layout()
    plt.show()

def plot_backtest_results(backtest_results, figsize=(12, 8)):
    """
    Plot backtest results.

    Args:
        backtest_results (dict): Results from strategy backtest
        figsize (tuple): Figure size
    """
    trades = backtest_results['trades']

    if not trades:
        print("No trades to plot")
        return

    fig, axes = plt.subplots(2, 1, figsize=figsize)

    # Plot trade P&L
    trade_df = pd.DataFrame(trades)
    if 'pnl' in trade_df.columns:
        pnl_trades = trade_df.dropna(subset=['pnl'])
        colors = ['green' if pnl > 0 else 'red' for pnl in pnl_trades['pnl']]

        axes[0].bar(range(len(pnl_trades)), pnl_trades['pnl'], color=colors, alpha=0.7)
        axes[0].set_title('Trade P&L')
        axes[0].set_xlabel('Trade Number')
        axes[0].set_ylabel('P&L ($)')
        axes[0].grid(True, alpha=0.3)

        # Add cumulative P&L line
        cumulative_pnl = pnl_trades['pnl'].cumsum()
        axes[0].plot(range(len(cumulative_pnl)), cumulative_pnl, color='blue', linewidth=2, label='Cumulative P&L')
        axes[0].legend()

    # Plot balance over time
    if 'timestamp' in trade_df.columns:
        trade_df['timestamp'] = pd.to_datetime(trade_df['timestamp'])
        trade_df = trade_df.sort_values('timestamp')

        # Calculate balance over time
        balance = backtest_results['initial_balance']
        balances = [balance]

        for _, trade in trade_df.iterrows():
            if 'pnl' in trade and pd.notna(trade['pnl']):
                balance += trade['pnl']
            balances.append(balance)

        axes[1].plot(trade_df['timestamp'].tolist() + [trade_df['timestamp'].iloc[-1]],
                    balances, linewidth=2, color='blue')
        axes[1].set_title('Account Balance Over Time')
        axes[1].set_xlabel('Date')
        axes[1].set_ylabel('Balance ($)')
        axes[1].grid(True, alpha=0.3)

        # Format x-axis
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        plt.xticks(rotation=45)

    plt.tight_layout()
    plt.show()

    # Print summary statistics
    print("📊 Backtest Summary:")
    print(f"Initial Balance: ${backtest_results['initial_balance']:.2f}")
    print(f"Final Balance: ${backtest_results['final_balance']:.2f}")
    print(f"Total Return: {backtest_results['total_return_pct']:.2f}%")
    print(f"Total Trades: {backtest_results['total_trades']}")

    if trades and 'pnl' in trade_df.columns:
        pnl_trades = trade_df.dropna(subset=['pnl'])
        winning_trades = pnl_trades[pnl_trades['pnl'] > 0]
        losing_trades = pnl_trades[pnl_trades['pnl'] < 0]

        print(f"Winning Trades: {len(winning_trades)}")
        print(f"Losing Trades: {len(losing_trades)}")
        print(f"Win Rate: {len(winning_trades) / len(pnl_trades) * 100:.1f}%" if len(pnl_trades) > 0 else "N/A")

        if len(winning_trades) > 0 and len(losing_trades) > 0:
            avg_win = winning_trades['pnl'].mean()
            avg_loss = abs(losing_trades['pnl'].mean())
            profit_factor = (winning_trades['pnl'].sum()) / abs(losing_trades['pnl'].sum())

            print(f"Average Win: ${avg_win:.2f}")
            print(f"Average Loss: ${avg_loss:.2f}")
            print(f"Profit Factor: {profit_factor:.2f}")

def plot_correlation_matrix(data, columns=None, figsize=(10, 8)):
    """
    Plot correlation matrix for selected columns.

    Args:
        data (pd.DataFrame): Data to analyze
        columns (list): Columns to include (default: numeric columns)
        figsize (tuple): Figure size
    """
    if columns is None:
        columns = data.select_dtypes(include=[np.number]).columns.tolist()

    corr_matrix = data[columns].corr()

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(corr_matrix, cmap='coolwarm', vmin=-1, vmax=1)

    # Add colorbar
    cbar = ax.figure.colorbar(im, ax=ax)
    cbar.ax.set_ylabel("Correlation", rotation=-90, va="bottom")

    # Set ticks and labels
    ax.set_xticks(np.arange(len(columns)))
    ax.set_yticks(np.arange(len(columns)))
    ax.set_xticklabels(columns)
    ax.set_yticklabels(columns)

    # Rotate x-axis labels
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right", rotation_mode="anchor")

    # Add correlation values
    for i in range(len(columns)):
        for j in range(len(columns)):
            text = ax.text(j, i, f"{corr_matrix.iloc[i, j]:.2f}",
                         ha="center", va="center", color="black")

    ax.set_title("Correlation Matrix")
    plt.tight_layout()
    plt.show()

def create_price_distribution_plot(data, bins=50, figsize=(12, 6)):
    """
    Create price distribution plot.

    Args:
        data (pd.DataFrame): OHLC data
        bins (int): Number of bins for histogram
        figsize (tuple): Figure size
    """
    fig, axes = plt.subplots(1, 2, figsize=figsize)

    # Price distribution
    axes[0].hist(data['close'], bins=bins, alpha=0.7, color='blue', edgecolor='black')
    axes[0].set_title('Price Distribution')
    axes[0].set_xlabel('Price')
    axes[0].set_ylabel('Frequency')
    axes[0].grid(True, alpha=0.3)

    # Returns distribution
    returns = data['close'].pct_change().dropna()
    axes[1].hist(returns * 100, bins=bins, alpha=0.7, color='green', edgecolor='black')
    axes[1].set_title('Returns Distribution (%)')
    axes[1].set_xlabel('Daily Return (%)')
    axes[1].set_ylabel('Frequency')
    axes[1].grid(True, alpha=0.3)

    # Add statistics
    axes[1].axvline(returns.mean() * 100, color='red', linestyle='--', label=f'Mean: {returns.mean()*100:.2f}%')
    axes[1].axvline(returns.std() * 100, color='orange', linestyle='--', label=f'Std: {returns.std()*100:.2f}%')
    axes[1].axvline(-returns.std() * 100, color='orange', linestyle='--')
    axes[1].legend()

    plt.tight_layout()
    plt.show()

    # Print statistics
    print("📊 Price Statistics:")
    print(f"Mean Price: ${data['close'].mean():.2f}")
    print(f"Median Price: ${data['close'].median():.2f}")
    print(f"Min Price: ${data['close'].min():.2f}")
    print(f"Max Price: ${data['close'].max():.2f}")
    print(f"Price Range: ${data['close'].max() - data['close'].min():.2f}")

    print("\n📊 Return Statistics:")
    print(f"Mean Daily Return: {returns.mean()*100:.2f}%")
    print(f"Std Daily Return: {returns.std()*100:.2f}%")
    print(f"Skewness: {returns.skew():.2f}")
    print(f"Kurtosis: {returns.kurtosis():.2f}")

if __name__ == "__main__":
    # Example usage
    import numpy as np

    # Create sample data
    dates = pd.date_range('2023-01-01', periods=200, freq='D')
    prices = 1800 + np.cumsum(np.random.randn(200) * 2) + np.sin(np.arange(200) * 0.1) * 20
    sample_data = pd.DataFrame({
        'open': prices + np.random.randn(200) * 2,
        'high': prices + abs(np.random.randn(200) * 5),
        'low': prices - abs(np.random.randn(200) * 5),
        'close': prices,
        'tick_volume': np.random.randint(1000, 10000, 200)
    }, index=dates)

    # Add some indicators for demonstration
    sample_data['EMA_12'] = sample_data['close'].ewm(span=12).mean()
    sample_data['EMA_26'] = sample_data['close'].ewm(span=26).mean()
    sample_data['RSI_14'] = 50 + np.random.randn(200) * 20  # Mock RSI
    sample_data['EMA_signal'] = np.random.choice([-1, 0, 1], 200)

    print("📊 Plotting sample data...")
    plot_price_with_indicators(sample_data.tail(50), title="Sample XAU/USD Chart")

    # Create price distribution plot
    create_price_distribution_plot(sample_data)

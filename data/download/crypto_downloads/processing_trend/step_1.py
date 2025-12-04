"""
STEP 1: Calculate Technical Indicators
--------------------------------------
Input: Raw OHLCV data (OHLCV.csv)
Output: OHLCV data enriched with technical indicators (OHLCV_processed_1.csv)

Transformations:
- Extracts timestamp_iso, open, high, low, close, volume
- Calculates TREND indicators: EMA(9,21,50), EMA slopes, EMA distances, Close/EMA ratios
- Calculates MOMENTUM indicators: RSI(7,14), MACD, Stochastic, ROC(10)
- Calculates VOLATILITY indicators: ATR, Bollinger Bands, Rolling Volatility, HL Range
- Calculates VOLUME indicators: Volume Delta, Volume Z-Score, OBV, Volume/Volatility Ratio
- Calculates PRICE STRUCTURE: Candle ratios, Wick ratios, Price Z-Score, HL2/HLC3, Returns(1,3,5,15)
"""
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt
from pathlib import Path

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE" / "csv_data"
INPUT_ROOT = BASE_DATA_DIR / "ETHUSDT-PERP" / "OHLCV.csv"
OUTPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_1.csv"
PLOT = False

# Create output directory if it doesn't exist
OUTPUT_ROOT.parent.mkdir(parents=True, exist_ok=True)

# Read CSV and select only desired columns
df = pd.read_csv(INPUT_ROOT)
processed_df = df[['timestamp_iso', 'open', 'high', 'low', 'close', 'volume']].copy()

# Calculate EMAs
processed_df['ema_9'] = ta.ema(processed_df['close'], length=9)
processed_df['ema_21'] = ta.ema(processed_df['close'], length=21)
processed_df['ema_50'] = ta.ema(processed_df['close'], length=50)

# Calculate EMA(21) Slope (difference between current and previous EMA(21))
processed_df['ema_21_slope'] = processed_df['ema_21'].diff()

# Calculate Close/EMA(21) ratio
processed_df['close_ema21_ratio'] = processed_df['close'] / processed_df['ema_21']

# Calculate EMA Cross Distances
processed_df['ema_9_21_distance'] = processed_df['ema_9'] - processed_df['ema_21']
processed_df['ema_21_50_distance'] = processed_df['ema_21'] - processed_df['ema_50']

# Calculate RSI
processed_df['rsi_7'] = ta.rsi(processed_df['close'], length=7)
processed_df['rsi_14'] = ta.rsi(processed_df['close'], length=14)

# Calculate MACD
macd = ta.macd(processed_df['close'])
processed_df['macd'] = macd['MACD_12_26_9']
processed_df['macd_signal'] = macd['MACDs_12_26_9']
processed_df['macd_histogram'] = macd['MACDh_12_26_9']

# Calculate Stochastic
stoch = ta.stoch(processed_df['high'], processed_df['low'], processed_df['close'])
processed_df['stoch_k'] = stoch['STOCHk_14_3_3']
processed_df['stoch_d'] = stoch['STOCHd_14_3_3']

# Calculate ROC (Rate of Change)
processed_df['roc_10'] = ta.roc(processed_df['close'], length=10)

# Calculate ATR (Average True Range)
processed_df['atr'] = ta.atr(processed_df['high'], processed_df['low'], processed_df['close'], length=14)

# Calculate Bollinger Bands and %B
bbands = ta.bbands(processed_df['close'], length=20, std=2)
if bbands is not None and len(bbands.columns) >= 5:
    # Correct order: Lower, Middle, Upper, Bandwidth, %B
    processed_df['bb_lower'] = bbands.iloc[:, 0]   # BBL_20_2.0
    processed_df['bb_middle'] = bbands.iloc[:, 1]  # BBM_20_2.0
    processed_df['bb_upper'] = bbands.iloc[:, 2]   # BBU_20_2.0
    processed_df['bb_percent_b'] = bbands.iloc[:, 4]  # BBP_20_2.0 (%B)
else:
    print("Warning: Bollinger Bands calculation failed, using manual calculation.")
    # Fallback manual calculation
    sma_20 = processed_df['close'].rolling(window=20).mean()
    std_20 = processed_df['close'].rolling(window=20).std()
    processed_df['bb_upper'] = sma_20 + (2 * std_20)
    processed_df['bb_middle'] = sma_20
    processed_df['bb_lower'] = sma_20 - (2 * std_20)
    processed_df['bb_percent_b'] = (processed_df['close'] - processed_df['bb_lower']) / (processed_df['bb_upper'] - processed_df['bb_lower'])

# Calculate Rolling Volatility (standard deviation of returns over 20 periods)
processed_df['returns'] = processed_df['close'].pct_change()
processed_df['rolling_volatility_20'] = processed_df['returns'].rolling(window=20).std()

# Calculate High-Low Normalized Range
processed_df['hl_range'] = processed_df['high'] - processed_df['low']
processed_df['hl_normalized_range'] = processed_df['hl_range'] / processed_df['close']

# Calculate Volume Delta (change in volume)
processed_df['volume_delta'] = processed_df['volume'].diff()

# Calculate Volume Z-Score (standardized volume)
volume_mean = processed_df['volume'].rolling(window=20).mean()
volume_std = processed_df['volume'].rolling(window=20).std()
processed_df['volume_zscore'] = (processed_df['volume'] - volume_mean) / volume_std

# Calculate OBV (On-Balance Volume)
processed_df['obv'] = ta.obv(processed_df['close'], processed_df['volume'])

# Calculate Volume/Volatility Ratio
processed_df['volume_volatility_ratio'] = processed_df['volume'] / processed_df['rolling_volatility_20']

# Calculate Candle Body Ratio (body size relative to total range)
processed_df['candle_body'] = abs(processed_df['close'] - processed_df['open'])
processed_df['candle_total_range'] = processed_df['high'] - processed_df['low']
processed_df['candle_body_ratio'] = processed_df['candle_body'] / processed_df['candle_total_range'].replace(0, float('nan'))

# Calculate Upper and Lower Wick Ratios
processed_df['upper_wick'] = processed_df['high'] - processed_df[['open', 'close']].max(axis=1)
processed_df['lower_wick'] = processed_df[['open', 'close']].min(axis=1) - processed_df['low']
processed_df['upper_wick_ratio'] = processed_df['upper_wick'] / processed_df['candle_total_range'].replace(0, float('nan'))
processed_df['lower_wick_ratio'] = processed_df['lower_wick'] / processed_df['candle_total_range'].replace(0, float('nan'))

# Calculate Z-Score Price (20 period)
price_mean_20 = processed_df['close'].rolling(window=20).mean()
price_std_20 = processed_df['close'].rolling(window=20).std()
processed_df['price_zscore_20'] = (processed_df['close'] - price_mean_20) / price_std_20

# Calculate HL2 and HLC3
processed_df['hl2'] = (processed_df['high'] + processed_df['low']) / 2
processed_df['hlc3'] = (processed_df['high'] + processed_df['low'] + processed_df['close']) / 3

# Calculate Returns for multiple intervals
processed_df['return_1'] = processed_df['close'].pct_change(periods=1)
processed_df['return_3'] = processed_df['close'].pct_change(periods=3)
processed_df['return_5'] = processed_df['close'].pct_change(periods=5)
processed_df['return_15'] = processed_df['close'].pct_change(periods=15)

# Save processed data
processed_df.to_csv(OUTPUT_ROOT, index=False)

if PLOT:

    # Limit to last 500 timesteps for plotting
    plot_df = processed_df.tail(500).reset_index(drop=True)

    # Create comprehensive plots for all indicators
    fig = plt.figure(figsize=(20, 16))
    gs = fig.add_gridspec(6, 2, hspace=0.3, wspace=0.3)

    # Plot 1: Price with EMAs (Trend)
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(plot_df.index, plot_df['close'], label='Close', linewidth=1.5, color='black')
    ax1.plot(plot_df.index, plot_df['ema_9'], label='EMA(9)', linewidth=1, alpha=0.8)
    ax1.plot(plot_df.index, plot_df['ema_21'], label='EMA(21)', linewidth=1, alpha=0.8)
    ax1.plot(plot_df.index, plot_df['ema_50'], label='EMA(50)', linewidth=1, alpha=0.8)
    ax1.set_ylabel('Price')
    ax1.set_title('TREND: Close Price with EMAs (Last 500 Points)')
    ax1.legend(loc='best')
    ax1.grid(True, alpha=0.3)

    # Plot 2: EMA Distances & Slope
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.plot(plot_df.index, plot_df['ema_9_21_distance'], label='EMA(9-21)', alpha=0.8)
    ax2.plot(plot_df.index, plot_df['ema_21_50_distance'], label='EMA(21-50)', alpha=0.8)
    ax2.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    ax2.set_ylabel('Distance')
    ax2.set_title('TREND: EMA Cross Distances')
    ax2.legend(loc='best')
    ax2.grid(True, alpha=0.3)

    # Plot 3: Close/EMA(21) Ratio & EMA(21) Slope
    ax3 = fig.add_subplot(gs[1, 1])
    ax3_twin = ax3.twinx()
    ax3.plot(plot_df.index, plot_df['close_ema21_ratio'], label='Close/EMA(21)', color='green')
    ax3_twin.plot(plot_df.index, plot_df['ema_21_slope'], label='EMA(21) Slope', color='blue', alpha=0.7)
    ax3.axhline(y=1, color='red', linestyle='--', alpha=0.5)
    ax3.set_ylabel('Ratio', color='green')
    ax3_twin.set_ylabel('Slope', color='blue')
    ax3.set_title('TREND: Ratio & Slope')
    ax3.legend(loc='upper left')
    ax3_twin.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)

    # Plot 4: RSI (Momentum)
    ax4 = fig.add_subplot(gs[2, 0])
    ax4.plot(plot_df.index, plot_df['rsi_7'], label='RSI(7)', alpha=0.8)
    ax4.plot(plot_df.index, plot_df['rsi_14'], label='RSI(14)', alpha=0.8)
    ax4.axhline(y=70, color='red', linestyle='--', alpha=0.5)
    ax4.axhline(y=30, color='green', linestyle='--', alpha=0.5)
    ax4.set_ylabel('RSI')
    ax4.set_title('MOMENTUM: RSI')
    ax4.legend(loc='best')
    ax4.grid(True, alpha=0.3)

    # Plot 5: MACD (Momentum)
    ax5 = fig.add_subplot(gs[2, 1])
    ax5.plot(plot_df.index, plot_df['macd'], label='MACD', linewidth=1.5)
    ax5.plot(plot_df.index, plot_df['macd_signal'], label='Signal', linewidth=1.5)
    ax5.bar(plot_df.index, plot_df['macd_histogram'], label='Histogram', alpha=0.3)
    ax5.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax5.set_ylabel('MACD')
    ax5.set_title('MOMENTUM: MACD')
    ax5.legend(loc='best')
    ax5.grid(True, alpha=0.3)

    # Plot 6: Stochastic & ROC (Momentum)
    ax6 = fig.add_subplot(gs[3, 0])
    ax6.plot(plot_df.index, plot_df['stoch_k'], label='Stoch %K', alpha=0.8)
    ax6.plot(plot_df.index, plot_df['stoch_d'], label='Stoch %D', alpha=0.8)
    ax6.axhline(y=80, color='red', linestyle='--', alpha=0.5)
    ax6.axhline(y=20, color='green', linestyle='--', alpha=0.5)
    ax6.set_ylabel('Stochastic')
    ax6.set_title('MOMENTUM: Stochastic Oscillator')
    ax6.legend(loc='best')
    ax6.grid(True, alpha=0.3)

    # Plot 7: ROC (Momentum)
    ax7 = fig.add_subplot(gs[3, 1])
    ax7.plot(plot_df.index, plot_df['roc_10'], label='ROC(10)', color='purple')
    ax7.axhline(y=0, color='red', linestyle='--', alpha=0.5)
    ax7.set_ylabel('ROC %')
    ax7.set_title('MOMENTUM: Rate of Change')
    ax7.legend(loc='best')
    ax7.grid(True, alpha=0.3)

    # Plot 8: ATR & Bollinger %B (Volatility)
    ax8 = fig.add_subplot(gs[4, 0])
    ax8_twin = ax8.twinx()
    ax8.plot(plot_df.index, plot_df['atr'], label='ATR', color='orange')
    ax8_twin.plot(plot_df.index, plot_df['bb_percent_b'], label='BB %B', color='blue', alpha=0.7)
    ax8_twin.axhline(y=1, color='red', linestyle='--', alpha=0.5)
    ax8_twin.axhline(y=0, color='green', linestyle='--', alpha=0.5)
    ax8.set_ylabel('ATR', color='orange')
    ax8_twin.set_ylabel('BB %B', color='blue')
    ax8.set_title('VOLATILITY: ATR & Bollinger %B')
    ax8.legend(loc='upper left')
    ax8_twin.legend(loc='upper right')
    ax8.grid(True, alpha=0.3)

    # Plot 9: Rolling Volatility & HL Normalized Range (Volatility)
    ax9 = fig.add_subplot(gs[4, 1])
    ax9.plot(plot_df.index, plot_df['rolling_volatility_20'], label='Rolling Vol(20)', alpha=0.8)
    ax9.plot(plot_df.index, plot_df['hl_normalized_range'], label='HL Norm Range', alpha=0.8)
    ax9.set_ylabel('Volatility')
    ax9.set_title('VOLATILITY: Rolling Vol & HL Range')
    ax9.legend(loc='best')
    ax9.grid(True, alpha=0.3)

    # Plot 10: Volume Indicators
    ax10 = fig.add_subplot(gs[5, 0])
    ax10_twin = ax10.twinx()
    ax10.bar(plot_df.index, plot_df['volume'], label='Volume', alpha=0.3, color='gray')
    ax10_twin.plot(plot_df.index, plot_df['volume_zscore'], label='Vol Z-Score', color='red', linewidth=1.5)
    ax10_twin.axhline(y=0, color='black', linestyle='--', alpha=0.3)
    ax10.set_ylabel('Volume', color='gray')
    ax10_twin.set_ylabel('Z-Score', color='red')
    ax10.set_title('VOLUME: Volume & Z-Score')
    ax10.legend(loc='upper left')
    ax10_twin.legend(loc='upper right')
    ax10.grid(True, alpha=0.3)

    # Plot 11: Price Structure
    ax11 = fig.add_subplot(gs[5, 1])
    ax11.plot(plot_df.index, plot_df['candle_body_ratio'], label='Body Ratio', alpha=0.8)
    ax11.plot(plot_df.index, plot_df['upper_wick_ratio'], label='Upper Wick', alpha=0.8)
    ax11.plot(plot_df.index, plot_df['lower_wick_ratio'], label='Lower Wick', alpha=0.8)
    ax11.set_ylabel('Ratio')
    ax11.set_title('PRICE STRUCTURE: Candle Ratios')
    ax11.legend(loc='best')
    ax11.grid(True, alpha=0.3)

    plt.suptitle('ETHUSDT-PERP: All Technical Indicators (Last 500 Points)', fontsize=18, y=0.995)
    plt.savefig(OUTPUT_ROOT.parent / 'all_indicators_plot.png', dpi=150, bbox_inches='tight')
    plt.show()

    print(f"Processed data saved to: {OUTPUT_ROOT}")
    print(f"Plot saved to: {OUTPUT_ROOT.parent / 'all_indicators_plot.png'}")
    print(f"Total indicators calculated: {len(processed_df.columns) - 6}")  # Minus OHLCV + timestamp


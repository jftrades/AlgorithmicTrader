"""
STEP 4: Create Target Variables (Forward Returns)
-------------------------------------------------
Input: Merged dataset (OHLCV_processed_3.csv)
Output: Dataset with target variables (OHLCV_processed_4.csv)

Transformations:
- Creates forward return targets for multiple time horizons:
  * 10m (2 periods), 20m (4 periods), 30m (6 periods), 45m (9 periods), 60m (12 periods)
- For each horizon, generates:
  * y_return_{horizon}: Percentage return (continuous)
  * y_classification_{horizon}: Binary label (1=up, 0=down)
- Reports how many rows have valid targets vs NaN (end of dataset)
"""
import pandas as pd
from pathlib import Path
BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE" / "csv_data"
# Create target variables for multiple forward time horizons (10m, 20m, 30m, 45m, 60m) with both returns and binary classifications.
INPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_3.csv"
OUTPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_4.csv"

# Read the merged data from step 3
df = pd.read_csv(INPUT_ROOT)

print(f"Original data shape: {df.shape}")
print(f"First timestamp: {df['timestamp_iso'].iloc[0]}")
print(f"Last timestamp: {df['timestamp_iso'].iloc[-1]}")

# Define forward returns for different time horizons
# Assuming 5-minute candles: 2=10m, 4=20m, 6=30m, 9=45m, 12=60m
horizons = {
    "10m": 2,
    "20m": 4,
    "30m": 6,
    "45m": 9,
    "60m": 12
}

print(f"\n=== CREATING TARGET VARIABLES ===")
for name, shift_periods in horizons.items():
    # Calculate forward return
    return_col = f"y_return_{name}"
    df[return_col] = df["close"].shift(-shift_periods) / df["close"] - 1
    
    # Create binary classification (1=up, 0=down)
    classification_col = f"y_classification_{name}"
    df[classification_col] = (df[return_col] > 0).astype(int)
    
    # Count valid predictions
    valid_count = df[return_col].notna().sum()
    print(f"{name}: {valid_count} valid predictions ({valid_count/len(df)*100:.2f}%)")

# Count how many rows have NaN in target variables (last N rows)
target_cols = [f"y_return_{name}" for name in horizons.keys()]
rows_with_nan_targets = df[target_cols].isna().any(axis=1).sum()

print(f"\n=== TARGET SUMMARY ===")
print(f"Rows with NaN targets (end of dataset): {rows_with_nan_targets}")
print(f"Rows with valid targets: {len(df) - rows_with_nan_targets}")
print(f"\nTarget columns created:")
for name in horizons.keys():
    print(f"  - y_return_{name}")
    print(f"  - y_classification_{name}")

# Save data with target variables
df.to_csv(OUTPUT_ROOT, index=False)

print(f"\nData with targets saved to: {OUTPUT_ROOT}")
print(f"Total rows: {len(df)}")
print(f"Total columns: {len(df.columns)}")
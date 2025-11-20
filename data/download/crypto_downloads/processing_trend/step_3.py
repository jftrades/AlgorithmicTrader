"""
STEP 3: Merge External Metrics and FNG Data
-------------------------------------------
Input: Cleaned OHLCV (OHLCV_processed_2.csv), METRICS.csv, FNG.csv
Output: Merged dataset with all features (OHLCV_processed_3.csv)

Transformations:
- Normalizes timestamps across all datasets (removes timezone info, milliseconds)
- Merges METRICS data (open interest, long/short ratios, taker volume ratio)
- Merges FNG (Fear and Greed Index) data
- Forward fills missing values for timestamps not found in METRICS/FNG
- Saves lists of missing timestamps for both METRICS and FNG
"""
import pandas as pd
from pathlib import Path

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE" / "csv_data"
INPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_2.csv"
METRICS_ROOT = BASE_DATA_DIR / "ETHUSDT-PERP" / "METRICS.csv"
FNG_ROOT = BASE_DATA_DIR / "FNG-INDEX.BINANCE" / "FNG.csv"
OUTPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_3.csv"

# Read the processed OHLCV data from step 2
df_ohlcv = pd.read_csv(INPUT_ROOT)
print(f"OHLCV data shape: {df_ohlcv.shape}")
print(f"OHLCV columns: {df_ohlcv.columns.tolist()}")

# Read the METRICS data
df_metrics = pd.read_csv(METRICS_ROOT)
print(f"\nMETRICS data shape: {df_metrics.shape}")
print(f"METRICS columns: {df_metrics.columns.tolist()}")

# Read the FNG data
df_fng = pd.read_csv(FNG_ROOT)
print(f"\nFNG data shape: {df_fng.shape}")
print(f"FNG columns: {df_fng.columns.tolist()}")

# Select only the columns we need from metrics (exclude timestamp_nano and symbol)
metrics_columns = ['timestamp_iso', 'sum_open_interest', 'sum_open_interest_value', 
                   'count_toptrader_long_short_ratio', 'sum_toptrader_long_short_ratio',
                   'count_long_short_ratio', 'sum_taker_long_short_vol_ratio']

df_metrics_clean = df_metrics[metrics_columns].copy()

# Select FNG columns - only keep fear_greed value, not classification
if 'timestamp_iso' not in df_fng.columns:
    # Find the timestamp column
    timestamp_col = [col for col in df_fng.columns if 'timestamp' in col.lower()][0]
    df_fng = df_fng.rename(columns={timestamp_col: 'timestamp_iso'})

# Keep only timestamp_iso and fear_greed columns
df_fng_clean = df_fng[['timestamp_iso', 'fear_greed']].copy()
fng_data_cols = ['fear_greed']  # Only the numeric FNG value

# Normalize timestamp formats to common format (YYYY-MM-DDTHH:MM:SS)
# Remove timezone info, milliseconds, and standardize format
def clean_timestamp(ts):
    if pd.isna(ts):
        return ts
    # Remove 'Z', '+00:00', and any fractional seconds
    ts = str(ts).replace('Z', '').replace('+00:00', '')
    # Split at '.' to remove fractional seconds
    if '.' in ts:
        ts = ts.split('.')[0]
    return ts

df_ohlcv['timestamp_iso_clean'] = df_ohlcv['timestamp_iso'].apply(clean_timestamp)
df_metrics_clean['timestamp_iso_clean'] = df_metrics_clean['timestamp_iso'].apply(clean_timestamp)
df_fng_clean['timestamp_iso_clean'] = df_fng_clean['timestamp_iso'].apply(clean_timestamp)

print(f"\nSample timestamps after cleaning:")
print(f"OHLCV: {df_ohlcv['timestamp_iso_clean'].iloc[0]}")
print(f"METRICS: {df_metrics_clean['timestamp_iso_clean'].iloc[0]}")
print(f"FNG: {df_fng_clean['timestamp_iso_clean'].iloc[0]}")

# Merge OHLCV with METRICS
df_merged = df_ohlcv.merge(
    df_metrics_clean.drop('timestamp_iso', axis=1),
    on='timestamp_iso_clean',
    how='left'
)

# Merge with FNG
df_merged = df_merged.merge(
    df_fng_clean.drop('timestamp_iso', axis=1),
    on='timestamp_iso_clean',
    how='left'
)

# Drop the temporary clean timestamp column
df_merged = df_merged.drop('timestamp_iso_clean', axis=1)

# Fill missing values with 0 (timestamps not found in METRICS)
metrics_cols = ['sum_open_interest', 'sum_open_interest_value', 
                'count_toptrader_long_short_ratio', 'sum_toptrader_long_short_ratio',
                'count_long_short_ratio', 'sum_taker_long_short_vol_ratio']

# Count timestamps not found BEFORE forward fill
timestamps_not_found_mask_metrics = df_merged[metrics_cols].isna().all(axis=1)
timestamps_not_found_metrics = timestamps_not_found_mask_metrics.sum()

# Count FNG missing timestamps
fng_cols = fng_data_cols
timestamps_not_found_mask_fng = df_merged[fng_cols].isna().all(axis=1)
timestamps_not_found_fng = timestamps_not_found_mask_fng.sum()

# Create a DataFrame with timestamps not found
df_not_found_metrics = df_ohlcv[timestamps_not_found_mask_metrics][['timestamp_iso']].copy()
df_not_found_metrics['reason'] = 'Not found in METRICS - will be forward filled'

df_not_found_fng = df_ohlcv[timestamps_not_found_mask_fng][['timestamp_iso']].copy()
df_not_found_fng['reason'] = 'Not found in FNG - will be forward filled'

# Save the list of missing timestamps
missing_timestamps_path_metrics = OUTPUT_ROOT.parent / 'missing_timestamps_metrics.csv'
missing_timestamps_path_fng = OUTPUT_ROOT.parent / 'missing_timestamps_fng.csv'
df_not_found_metrics.to_csv(missing_timestamps_path_metrics, index=False)
df_not_found_fng.to_csv(missing_timestamps_path_fng, index=False)

# Forward fill missing METRICS and FNG values
df_merged[metrics_cols] = df_merged[metrics_cols].ffill()
df_merged[fng_cols] = df_merged[fng_cols].ffill()

# For any remaining NaN at the beginning, fill with 0
df_merged[metrics_cols] = df_merged[metrics_cols].fillna(0)
df_merged[fng_cols] = df_merged[fng_cols].fillna(0)

print(f"\n=== MERGE RESULTS ===")
print(f"Total OHLCV timestamps: {len(df_ohlcv)}")
print(f"Total METRICS timestamps: {len(df_metrics_clean)}")
print(f"Total FNG timestamps: {len(df_fng_clean)}")
print(f"Merged data shape: {df_merged.shape}")
print(f"\nMETRICS - Timestamps NOT found: {timestamps_not_found_metrics} ({timestamps_not_found_metrics/len(df_ohlcv)*100:.2f}%)")
print(f"METRICS - Timestamps matched: {len(df_ohlcv) - timestamps_not_found_metrics}")
print(f"\nFNG - Timestamps NOT found: {timestamps_not_found_fng} ({timestamps_not_found_fng/len(df_ohlcv)*100:.2f}%)")
print(f"FNG - Timestamps matched: {len(df_ohlcv) - timestamps_not_found_fng}")
print(f"\nMissing timestamps saved to:")
print(f"  - {missing_timestamps_path_metrics}")
print(f"  - {missing_timestamps_path_fng}")

# Save merged data
df_merged.to_csv(OUTPUT_ROOT, index=False)

print(f"\nMerged data saved to: {OUTPUT_ROOT}")
print(f"Total columns in merged dataset: {len(df_merged.columns)}")
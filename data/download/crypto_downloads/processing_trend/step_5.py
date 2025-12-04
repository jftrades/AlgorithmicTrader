"""
STEP 5: Remove First Rows and Last Rows
---------------------------------------
Input: Dataset with target variables (OHLCV_processed_4.csv)
Output: Filtered dataset (OHLCV_processed_5.csv)

Transformations:
- Removes the first 400 rows (warm-up period for indicators)
- Removes the last 100 rows (incomplete forward-looking target variables)
- Resets index to start from 0
"""
import pandas as pd
from pathlib import Path

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE" / "csv_data"
INPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_4.csv"
OUTPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_5.csv"

# Read the data from step 4
df = pd.read_csv(INPUT_ROOT)

print(f"Original data shape: {df.shape}")
print(f"First timestamp: {df['timestamp_iso'].iloc[0]}")
print(f"Last timestamp: {df['timestamp_iso'].iloc[-1]}")

# Filter out the first 400 rows and last 100 rows
FIRST_ROWS = 200
LAST_ROWS = 50
df_filtered = df.iloc[FIRST_ROWS:-LAST_ROWS].reset_index(drop=True)

print(f"\n=== FILTERING SUMMARY ===")
print(f"Rows removed (first rows): {FIRST_ROWS}")
print(f"Rows removed (last rows): {LAST_ROWS}")
print(f"Total rows removed: {FIRST_ROWS + LAST_ROWS}")
print(f"Filtered data shape: {df_filtered.shape}")
print(f"First timestamp after filtering: {df_filtered['timestamp_iso'].iloc[0]}")
print(f"Last timestamp after filtering: {df_filtered['timestamp_iso'].iloc[-1]}")
print(f"Percentage of data retained: {(len(df_filtered) / len(df) * 100):.2f}%")

# Save filtered data
df_filtered.to_csv(OUTPUT_ROOT, index=False)

print(f"\nFiltered data saved to: {OUTPUT_ROOT}")
print(f"Total rows: {len(df_filtered)}")
print(f"Total columns: {len(df_filtered.columns)}")

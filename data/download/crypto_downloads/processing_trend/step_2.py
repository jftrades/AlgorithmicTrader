"""
STEP 2: Clean NaN Values
------------------------
Input: OHLCV with technical indicators (OHLCV_processed_1.csv)
Output: Cleaned data with NaN values replaced by 0 (OHLCV_processed_2.csv)

Transformations:
- Identifies all NaN values in the dataset
- Replaces all NaN values with 0
- Prints statistics about which columns had missing values and how many
"""
import pandas as pd
from pathlib import Path

BASE_DATA_DIR = Path(__file__).resolve().parents[3] / "DATA_STORAGE" / "csv_data"
INPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_1.csv"
OUTPUT_ROOT = BASE_DATA_DIR / "processed" / "ETHUSDT-PERP" / "OHLCV_processed_2.csv"

# Read the processed data from step 1
df = pd.read_csv(INPUT_ROOT)

print(f"Original data shape: {df.shape}")
print(f"\nNaN values before cleaning:")
nan_counts = df.isnull().sum()
print(nan_counts[nan_counts > 0])
total_nans = df.isnull().sum().sum()
print(f"\nTotal NaN values: {total_nans}")

# Replace all NaN values with 0
df_cleaned = df.fillna(0)

print(f"\nNaN values after cleaning:")
print(df_cleaned.isnull().sum().sum())

print(f"\n=== CLEANING SUMMARY ===")
print(f"Total NaN values filled with 0: {total_nans}")
print(f"Percentage of data filled: {(total_nans / (df.shape[0] * df.shape[1]) * 100):.2f}%")
print(f"\nColumns with NaN values filled:")
for col, count in nan_counts[nan_counts > 0].items():
    print(f"  {col}: {count} ({count/len(df)*100:.2f}%)")

# Save cleaned data
df_cleaned.to_csv(OUTPUT_ROOT, index=False)

print(f"\nCleaned data saved to: {OUTPUT_ROOT}")
print(f"Total rows: {len(df_cleaned)}")
print(f"Total columns: {len(df_cleaned.columns)}")

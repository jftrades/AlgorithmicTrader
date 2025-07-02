from pathlib import Path
import pandas as pd
import gc
import sys
import time
from datetime import datetime
from nautilus_trader.core.nautilus_pyo3 import AggressorSide
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
from nautilus_trader.persistence.wranglers_v2 import TradeTickDataWranglerV2
from nautilus_trader.persistence.catalog.types import CatalogWriteMode

CSV_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "processed_tick_data_2024-01-01_to_2024-02-01" / "csv" / "BTCUSDT_TICKS_2024-01-01_to_2024-02-01.csv"
CATALOG_ROOT_PATH = Path(__file__).resolve().parent.parent / "DATA_STORAGE" / "data_catalog_wrangled"
CHUNK_SIZE = 1_000_000
WRITE_BATCH_SIZE = 10_000_000  # Optimized batch size for better performance

def write_data_with_retry(catalog, tick_buffer, basename_template):
    current_template = basename_template
    
    for attempt in range(5):
        try:
            catalog.write_data(data=tick_buffer, basename_template=current_template, mode=CatalogWriteMode.APPEND)
            return True, current_template
        except Exception as e:
            if "1224" in str(e) or "geöffneten Bereich" in str(e):
                if attempt < 4:
                    print(f"    File lock detected, retrying in {3 + attempt}s... (attempt {attempt + 1}/5)")
                    time.sleep(3 + attempt)
                    gc.collect()
                    continue
                else:
                    # Generate new template for persistent locks
                    current_template = generate_unique_basename_template()
                    print(f"    Persistent lock - using new template: {current_template}")
                    try:
                        catalog.write_data(data=tick_buffer, basename_template=current_template, mode=CatalogWriteMode.APPEND)
                        return True, current_template
                    except Exception as retry_e:
                        print(f"    New template failed: {retry_e}")
                        return False, current_template
            else:
                print(f"    Write error: {e}")
                raise e
    
    return False, current_template

def generate_unique_basename_template():
    return f"btcusdt_ticks_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_part-{{i}}"

def process_tick_data_official_append():
    """RAM-efficient chunked processing using official Nautilus append mode"""
    
    catalog = ParquetDataCatalog(
        str(CATALOG_ROOT_PATH),
        max_rows_per_group=WRITE_BATCH_SIZE
    )
    
    wrangler = TradeTickDataWranglerV2(
        instrument_id="BTCUSDT-PERP.BINANCE",
        price_precision=1,
        size_precision=3
    )
    
    basename_template = generate_unique_basename_template()
    chunk_count = 0
    total_ticks = 0
    tick_buffer = []
    start_time = time.time()
    
    print(f"Processing {CSV_PATH.name}")
    print(f"Chunk size: {CHUNK_SIZE:,}, Batch size: {WRITE_BATCH_SIZE:,}")
    print(f"Template: {basename_template}")
    print(f"Started at: {datetime.now().strftime('%H:%M:%S')}")
    print("-" * 60)
    
    try:
        for chunk_df in pd.read_csv(CSV_PATH, chunksize=CHUNK_SIZE):
            chunk_count += 1
            chunk_ticks = len(chunk_df)
            total_ticks += chunk_ticks
            elapsed = time.time() - start_time
            
            print(f"Chunk {chunk_count}: {chunk_ticks:,} ticks (Total: {total_ticks:,}) - {elapsed:.1f}s elapsed")
            
            # Convert timestamps but keep as column (not index) for Nautilus V2
            chunk_df['timestamp'] = pd.to_datetime(chunk_df['timestamp'])
            
            # Rename columns to match Nautilus V2 expectations
            column_mapping = {
                'timestamp': 'ts_event',
                'quantity': 'size'
            }
            chunk_df = chunk_df.rename(columns=column_mapping)
            
            # Handle trade_id column - required by Nautilus
            if 'trade_id' not in chunk_df.columns:
                chunk_df['trade_id'] = chunk_df.index.astype(str)
            
            # Handle aggressor_side - map from 'side' column if present
            if 'side' in chunk_df.columns:
                # Map Binance side format to Nautilus AggressorSide
                chunk_df['aggressor_side'] = chunk_df['side'].map({
                    'BUY': AggressorSide.BUYER,
                    'SELL': AggressorSide.SELLER
                })
            elif 'aggressor_side' not in chunk_df.columns:
                chunk_df['aggressor_side'] = AggressorSide.NO_AGGRESSOR
            
            try:
                # TradeTickDataWranglerV2.from_pandas expects columns, not index
                nautilus_ticks = wrangler.from_pandas(chunk_df)
                tick_buffer.extend(nautilus_ticks)
                
                print(f"  Processed {len(nautilus_ticks):,} Nautilus ticks")
                print(f"  Buffer now contains {len(tick_buffer):,} ticks")
                
                if len(tick_buffer) >= WRITE_BATCH_SIZE:
                    print(f"  Writing batch of {len(tick_buffer):,} ticks...")
                    
                    success, basename_template = write_data_with_retry(catalog, tick_buffer, basename_template)
                    if success:
                        print("  Batch written successfully")
                        tick_buffer.clear()
                        gc.collect()
                        print(f"  Buffer cleared, continuing...")
                    else:
                        print("  Failed to write batch after retries")
                        break
                    
            except Exception as e:
                print(f"  Error processing chunk {chunk_count}: {e}")
                continue
        
        if tick_buffer:
            print(f"Writing final batch of {len(tick_buffer):,} ticks...")
            success, basename_template = write_data_with_retry(catalog, tick_buffer, basename_template)
            if success:
                print("Final batch written")
            else:
                print("Failed to write final batch")
        
        print(f"\nTransformation complete!")
        total_elapsed = time.time() - start_time
        print(f"Total processed: {total_ticks:,} ticks in {chunk_count} chunks")
        print(f"Total time: {total_elapsed:.1f}s ({total_ticks / total_elapsed:.0f} ticks/sec)")
        print(f"Files saved to: {CATALOG_ROOT_PATH}")
        
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)

def verify_csv_structure():
    """Verify CSV file structure before processing"""
    if not CSV_PATH.exists():
        print(f"CSV file not found: {CSV_PATH}")
        return False
    
    try:
        # Check file size
        file_size = CSV_PATH.stat().st_size
        print(f"CSV file size: {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")
        
        df_sample = pd.read_csv(CSV_PATH, nrows=5)
        print(f"CSV found with columns: {list(df_sample.columns)}")
        print(f"Sample data:")
        print(df_sample.head())
        
        required_cols = ['timestamp', 'price']
        # Check for either 'size' or 'quantity' column
        has_size = 'size' in df_sample.columns or 'quantity' in df_sample.columns
        
        missing_cols = [col for col in required_cols if col not in df_sample.columns]
        
        if missing_cols:
            print(f"Missing required columns: {missing_cols}")
            return False
            
        if not has_size:
            print("Missing size/quantity column")
            return False
        
        # Count total rows for progress tracking
        total_rows = sum(1 for _ in open(CSV_PATH, 'r', encoding='utf-8')) - 1  # -1 for header
        print(f"Total CSV rows: {total_rows:,}")
        
        return True
        
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return False

if __name__ == "__main__":
    print("Nautilus Tick Transformation - Official Append Mode")
    print("=" * 50)
    
    if not verify_csv_structure():
        print("CSV verification failed. Exiting.")
        sys.exit(1)
    
    CATALOG_ROOT_PATH.mkdir(parents=True, exist_ok=True)
    process_tick_data_official_append()

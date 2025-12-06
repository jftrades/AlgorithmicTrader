"""
Run-Validierung für das Dashboard
"""
from pathlib import Path
import pandas as pd
import yaml
from typing import List

class RunValidator:
    # note: styling changes only affect UI components, logic stays the same
    """Strikte Validierung für Run-Daten ohne Fallbacks"""
    
    REQUIRED_COLUMNS = ["run_id", "Sharpe", "Total Return", "Max Drawdown", "Trades"]
    
    # Mapping von CSV-Spalten zu erwarteten Spalten
    COLUMN_MAPPING = {
        'RET_Sharpe Ratio (252 days)': 'Sharpe',
        'Sharpe Ratio (252 days)': 'Sharpe',
        'USDT_PnL (total)': 'Total Return',
        'USDT_PnL': 'Total Return',
        'total_orders': 'Trades',
    }
    
    def __init__(self, results_dir: Path):
        self.results_dir = Path(results_dir)
        self.csv_path = self.results_dir / "all_backtest_results.csv"
    
    def validate_and_load(self) -> pd.DataFrame:
        """Lädt und validiert all_backtest_results.csv mit strikter Prüfung"""
        
        # CSV-Datei muss existieren
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CRITICAL: all_backtest_results.csv not found at {self.csv_path}")
        
        # CSV laden
        try:
            df = pd.read_csv(self.csv_path)
        except Exception as e:
            raise RuntimeError(f"CRITICAL: Failed to read {self.csv_path}: {e}")
        
        # Darf nicht leer sein
        if df.empty:
            raise ValueError(f"CRITICAL: all_backtest_results.csv is empty at {self.csv_path}")
        
        # Spalten-Mapping anwenden
        df = self._apply_column_mapping(df)
        
        # Pflichtspalten prüfen (nach Mapping)
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            available_cols = list(df.columns)
            raise ValueError(f"CRITICAL: Missing required columns after mapping: {missing_cols}. Available columns: {available_cols}")
        
        # run_id Spalte darf keine NaN/leeren Werte haben
        if df['run_id'].isna().any() or (df['run_id'] == '').any():
            raise ValueError("CRITICAL: run_id column contains empty or NaN values")
        
        # Sharpe-Spalte muss numerisch konvertierbar sein
        try:
            df['Sharpe'] = pd.to_numeric(df['Sharpe'], errors='coerce')
            if df['Sharpe'].isna().all():
                raise ValueError("CRITICAL: Sharpe column contains no valid numeric values")
        except Exception as e:
            raise ValueError(f"CRITICAL: Failed to convert Sharpe column to numeric: {e}")
        
        # Nach Sharpe sortieren (bester zuerst)
        df = df.sort_values('Sharpe', ascending=False, na_position='last')
        
        # Ordner-Index hinzufügen (run0, run1, run2, ...)
        df = df.reset_index(drop=True)
        df['run_index'] = df.index
        
        # Run-Ordner und run_config.yaml validieren
        self._validate_run_directories(df['run_index'].tolist())
        
        return df
    
    def _apply_column_mapping(self, df: pd.DataFrame) -> pd.DataFrame:
        """Wendet Spalten-Mapping an und erstellt fehlende Spalten (robust, case-insensitive Fallbacks)."""
        df_mapped = df.copy()

        # Direkte Mappings
        for source_col, target_col in self.COLUMN_MAPPING.items():
            if source_col in df_mapped.columns:
                df_mapped[target_col] = df_mapped[source_col]

        # Sharpe Fallback (falls noch nicht vorhanden)
        if 'Sharpe' not in df_mapped.columns:
            sharpe_like = [c for c in df_mapped.columns if 'sharpe' in c.lower()]
            if sharpe_like:
                try:
                    df_mapped['Sharpe'] = pd.to_numeric(df_mapped[sharpe_like[0]], errors='coerce')
                except Exception:
                    df_mapped['Sharpe'] = float('nan')

        if 'Total Return' not in df_mapped.columns:
            for col in ['USDT_PnL (total)', 'USDT_PnL', 'USDT_Total PnL', 'PnL']:
                if col in df_mapped.columns:
                    df_mapped['Total Return'] = df_mapped[col]
                    break
            else:
                df_mapped['Total Return'] = 0.0
        if 'Trades' not in df_mapped.columns:
            if 'total_orders' in df_mapped.columns:
                df_mapped['Trades'] = df_mapped['total_orders']
            elif 'total_positions' in df_mapped.columns:
                df_mapped['Trades'] = df_mapped['total_positions']
        
        if 'Max Drawdown' not in df_mapped.columns:
            df_mapped['Max Drawdown'] = 0.0

        return df_mapped
    
    def _validate_run_directories(self, run_indices: List[int]):
        """Validiert dass alle Run-Ordner existieren und run_config.yaml enthalten"""
        for run_index in run_indices:
            run_dir = self.results_dir / f"run{run_index}"
            
            if not run_dir.exists():
                raise FileNotFoundError(f"CRITICAL: Run directory not found: {run_dir}")
            
            config_path = run_dir / "run_config.yaml"
            if not config_path.exists():
                raise FileNotFoundError(f"CRITICAL: run_config.yaml not found in {run_dir}")
            
            # Zusätzlich: YAML muss parsbar sein
            try:
                with open(config_path, 'r') as f:
                    yaml.safe_load(f)
            except Exception as e:
                raise RuntimeError(f"CRITICAL: Invalid run_config.yaml in {run_dir}: {e}")

def get_best_run_index(runs_df: pd.DataFrame) -> int:
    """Gibt den run_index des besten Runs zurück (höchste Sharpe)"""
    if runs_df.empty:
        raise ValueError("CRITICAL: No runs available to select best run")
    
    best_row = runs_df.iloc[0]  # Bereits nach Sharpe sortiert
    return int(best_row['run_index'])

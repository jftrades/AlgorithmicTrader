from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from pathlib import Path

class BaseIndicator(ABC):
    """Abstract base class for all indicator types in the regime analysis system."""
    
    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.data = None
        self.metadata = {}
    
    @abstractmethod
    def calculate(self, price_data: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Calculate the indicator values based on price data or other inputs.
        
        Args:
            price_data: DataFrame with OHLCV data or other required data
            **kwargs: Additional parameters specific to each indicator
            
        Returns:
            DataFrame with timestamp and indicator value columns
        """
        pass
    
    @abstractmethod
    def get_required_columns(self) -> List[str]:
        """Return list of required columns from price data."""
        pass
    
    @abstractmethod
    def get_parameters(self) -> Dict:
        """Return dictionary of configurable parameters for this indicator."""
        pass
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """Validate that the input data has required columns and format."""
        required_cols = self.get_required_columns()
        
        if not all(col in data.columns for col in required_cols):
            missing = [col for col in required_cols if col not in data.columns]
            raise ValueError(f"Missing required columns for {self.name}: {missing}")
        
        if 'timestamp' not in data.columns and not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError(f"Data must have 'timestamp' column or DatetimeIndex for {self.name}")
        
        return True
    
    def standardize_output(self, result: pd.DataFrame, timestamp_col: Optional[str] = None) -> pd.DataFrame:
        """Standardize indicator output format."""
        if timestamp_col and timestamp_col in result.columns:
            result = result.rename(columns={timestamp_col: 'timestamp'})
        
        if 'timestamp' not in result.columns and isinstance(result.index, pd.DatetimeIndex):
            result = result.reset_index()
            result = result.rename(columns={'index': 'timestamp'})
        
        # Ensure timestamp is datetime
        if 'timestamp' in result.columns:
            result['timestamp'] = pd.to_datetime(result['timestamp'])
            result = result.sort_values('timestamp')
        
        return result
    
    def get_info(self) -> Dict:
        """Get indicator information and metadata."""
        return {
            'name': self.name,
            'category': self.category,
            'parameters': self.get_parameters(),
            'required_columns': self.get_required_columns(),
            'metadata': self.metadata
        }
    
    def set_metadata(self, **kwargs):
        """Set additional metadata for the indicator."""
        self.metadata.update(kwargs)
    
    def __str__(self) -> str:
        return f"{self.category}:{self.name}"
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}', category='{self.category}')>"

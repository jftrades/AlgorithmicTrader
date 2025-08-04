from collections import deque
import numpy as np
from typing import Tuple, Optional
from tools.indicators.VWAP_ZScore_HTF import VWAPZScoreHTF

class ElasticReversionZScoreEntry:
    def __init__(
        self,
        vwap_zscore_indicator: VWAPZScoreHTF,
        lookback_window: int = 20,
        z_min_threshold: float = -2.0,      # Mindest-Extrem für Long-Entries
        z_max_threshold: float = 2.0,       # Mindest-Extrem für Short-Entries  
        recovery_delta: float = 0.4,        # Recovery-Abstand vom Extrem
        reset_neutral_zone_long: float = 0.3, 
        reset_neutral_zone_short: float = -0.3   
    ):
        self.vwap_zscore = vwap_zscore_indicator
        self.lookback_window = lookback_window
        self.z_min_threshold = z_min_threshold
        self.z_max_threshold = z_max_threshold
        self.recovery_delta = recovery_delta
        self.reset_neutral_zone_long = reset_neutral_zone_long
        self.reset_neutral_zone_short = reset_neutral_zone_short
        
        # State-Tracking
        self.zscore_history = deque(maxlen=lookback_window)
        self.z_extreme_long = None      # Tiefstes Z-Score-Extrem
        self.z_extreme_short = None     # Höchstes Z-Score-Extrem
        self.bars_since_long_extreme = 0
        self.bars_since_short_extreme = 0
        self.long_recovery_triggered = False
        self.short_recovery_triggered = False
        
    def update_parameters(self, z_min_threshold: float = None, z_max_threshold: float = None, 
                         recovery_delta: float = None, reset_neutral_zone_long: float = None,
                         reset_neutral_zone_short: float = None):
        if z_min_threshold is not None:
            self.z_min_threshold = z_min_threshold
        if z_max_threshold is not None:
            self.z_max_threshold = z_max_threshold
        if recovery_delta is not None:
            self.recovery_delta = recovery_delta
        if reset_neutral_zone_long is not None:
            self.reset_neutral_zone_long = reset_neutral_zone_long
        if reset_neutral_zone_short is not None:
            self.reset_neutral_zone_short = reset_neutral_zone_short
            
    def update_state(self, zscore: float) -> None:
        if zscore is None:
            return
            
        self.zscore_history.append(zscore)
        
        self._update_extremes(zscore)
        
        self.bars_since_long_extreme += 1
        self.bars_since_short_extreme += 1

        self._handle_neutral_zone_reset(zscore)
        
    def _update_extremes(self, zscore: float) -> None:
        if self.z_extreme_long is None or zscore < self.z_extreme_long:
            self.z_extreme_long = zscore
            self.bars_since_long_extreme = 0
            self.long_recovery_triggered = False
            
        if self.z_extreme_short is None or zscore > self.z_extreme_short:
            self.z_extreme_short = zscore
            self.bars_since_short_extreme = 0
            self.short_recovery_triggered = False
            
    def _handle_neutral_zone_reset(self, zscore: float) -> None:
        if (zscore > self.reset_neutral_zone_long and 
            self.bars_since_long_extreme > self.lookback_window // 2):
            self.z_extreme_long = None
            self.long_recovery_triggered = False
            
        if (zscore < self.reset_neutral_zone_short and 
            self.bars_since_short_extreme > self.lookback_window // 2):
            self.z_extreme_short = None
            self.short_recovery_triggered = False
            
    def check_entry_signals(self, current_zscore: float) -> Tuple[bool, bool, dict]:
        if current_zscore is None:
            return False, False, {}
            
        long_signal = False
        short_signal = False
        
        debug_info = {
            'current_zscore': current_zscore,
            'z_extreme_long': self.z_extreme_long,
            'z_extreme_short': self.z_extreme_short,
            'long_recovery_triggered': self.long_recovery_triggered,
            'short_recovery_triggered': self.short_recovery_triggered,
            'bars_since_long_extreme': self.bars_since_long_extreme,
            'bars_since_short_extreme': self.bars_since_short_extreme
        }
        
        if (self.z_extreme_long is not None and 
            self.z_extreme_long <= self.z_min_threshold and  # Extrem war tief genug
            current_zscore >= (self.z_extreme_long + self.recovery_delta) and  # Recovery erreicht
            not self.long_recovery_triggered):  # Noch nicht getriggert
            
            long_signal = True
            self.long_recovery_triggered = True
            debug_info['long_entry_reason'] = f"Recovery from {self.z_extreme_long:.2f} to {current_zscore:.2f}"
            
        if (self.z_extreme_short is not None and
            self.z_extreme_short >= self.z_max_threshold and  # Extrem war hoch genug
            current_zscore <= (self.z_extreme_short - self.recovery_delta) and  # Recovery erreicht
            not self.short_recovery_triggered):  # Noch nicht getriggert
            
            short_signal = True
            self.short_recovery_triggered = True
            debug_info['short_entry_reason'] = f"Recovery from {self.z_extreme_short:.2f} to {current_zscore:.2f}"
            
        return long_signal, short_signal, debug_info
        
    def get_current_state(self) -> dict:
        """Erweiterte State-Info"""
        return {
            'z_extreme_long': self.z_extreme_long,
            'z_extreme_short': self.z_extreme_short,
            'bars_since_long_extreme': self.bars_since_long_extreme,
            'bars_since_short_extreme': self.bars_since_short_extreme,
            'long_recovery_triggered': self.long_recovery_triggered,
            'short_recovery_triggered': self.short_recovery_triggered,
            'zscore_history_length': len(self.zscore_history),
            'parameters': {
                'z_min_threshold': self.z_min_threshold,
                'z_max_threshold': self.z_max_threshold,
                'recovery_delta': self.recovery_delta,
                'reset_neutral_zone_long': self.reset_neutral_zone_long,
                'reset_neutral_zone_short': self.reset_neutral_zone_short
            }
        }
        
    def reset_state(self) -> None:
        self.zscore_history.clear()
        self.z_extreme_long = None
        self.z_extreme_short = None
        self.bars_since_long_extreme = 0
        self.bars_since_short_extreme = 0
        self.long_recovery_triggered = False
        self.short_recovery_triggered = False
from typing import Tuple, Dict, Any
from collections import deque
from tools.indicators.VWAP_ZScore_HTF import VWAPZScoreHTFAnchored

class ElasticReversionZScoreEntry:
    def __init__(
        self,
        vwap_zscore_indicator: VWAPZScoreHTFAnchored,
        z_min_threshold: float = -2.0,      
        z_max_threshold: float = 2.0,       
        recovery_delta: float = 0.4,        
        reset_neutral_zone_long: float = 0.3, 
        reset_neutral_zone_short: float = -0.3,
        allow_multiple_recoveries: bool = True,
        recovery_cooldown_bars: int = 5
    ):
        self.vwap_zscore = vwap_zscore_indicator
        self.z_min_threshold = z_min_threshold
        self.z_max_threshold = z_max_threshold
        self.recovery_delta = recovery_delta
        self.reset_neutral_zone_long = reset_neutral_zone_long
        self.reset_neutral_zone_short = reset_neutral_zone_short
        
        # Use deque with reasonable maxlen for memory efficiency
        self.zscore_since_cross = deque(maxlen=5000)  # Keep last 5000 values
        self.z_extreme_long_since_cross = None      
        self.z_extreme_short_since_cross = None     
        self.bars_since_long_extreme = 0
        self.bars_since_short_extreme = 0
        self.long_recovery_triggered = False
        self.short_recovery_triggered = False
        self.allow_multiple_recoveries = allow_multiple_recoveries
        self.recovery_cooldown_bars = recovery_cooldown_bars
        self.bars_since_last_long_signal = 0
        self.bars_since_last_short_signal = 0
        
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

    def reset_on_cross(self):
        """Resettet das System bei einem neuen Kalman Cross - ersetzt lookback_window"""
        self.zscore_since_cross.clear()  # Clear deque efficiently
        self.z_extreme_long_since_cross = None
        self.z_extreme_short_since_cross = None
        self.bars_since_long_extreme = 0
        self.bars_since_short_extreme = 0
        self.long_recovery_triggered = False
        self.short_recovery_triggered = False
        self.bars_since_last_long_signal = 0
        self.bars_since_last_short_signal = 0

    def get_sector_regime_params(self, config_params: Dict[str, Any], sector: str, regime: int) -> Dict[str, float]:
        sector_params = config_params.get(sector, {})
        
        regime_key = f"regime{regime}"
        regime_params = sector_params.get("regime_params", {}).get(regime_key, {})
        
        elastic_params = regime_params.get("elastic_entry", {})
        
        return {
            'z_min_threshold': elastic_params.get('z_min_threshold', self.z_min_threshold),
            'z_max_threshold': elastic_params.get('z_max_threshold', self.z_max_threshold),
            'recovery_delta': elastic_params.get('recovery_delta', self.recovery_delta),
            'reset_neutral_zone_long': elastic_params.get('reset_neutral_zone_long', self.reset_neutral_zone_long),
            'reset_neutral_zone_short': elastic_params.get('reset_neutral_zone_short', self.reset_neutral_zone_short)
        }

    def apply_sector_regime_params(self, config_params: Dict[str, Any], sector: str, regime: int):
        params = self.get_sector_regime_params(config_params, sector, regime)
        
        self.update_parameters(
            z_min_threshold=params['z_min_threshold'],
            z_max_threshold=params['z_max_threshold'],
            recovery_delta=params['recovery_delta'],
            reset_neutral_zone_long=params['reset_neutral_zone_long'],
            reset_neutral_zone_short=params['reset_neutral_zone_short']
        )

    def update_state(self, zscore: float) -> None:
        if zscore is None:
            return
            
        # Deque automatically manages memory with maxlen
        self.zscore_since_cross.append(zscore)
        self._update_extremes_since_cross(zscore)

        self.bars_since_long_extreme += 1
        self.bars_since_short_extreme += 1
        self.bars_since_last_long_signal += 1
        self.bars_since_last_short_signal += 1
        self._handle_neutral_zone_reset(zscore)
        
    def _update_extremes_since_cross(self, zscore: float) -> None:
        # Update Long Extreme
        if self.z_extreme_long_since_cross is None or zscore < self.z_extreme_long_since_cross:
            self.z_extreme_long_since_cross = zscore
            self.bars_since_long_extreme = 0
            # reset recovery flags on new extreme
            if self.allow_multiple_recoveries:
                self.long_recovery_triggered = False
            
        if self.z_extreme_short_since_cross is None or zscore > self.z_extreme_short_since_cross:
            self.z_extreme_short_since_cross = zscore
            self.bars_since_short_extreme = 0
            # reset recovery flags on new extreme
            if self.allow_multiple_recoveries:
                self.short_recovery_triggered = False
            
    def _handle_neutral_zone_reset(self, zscore: float) -> None:
        if (self.reset_neutral_zone_short <= zscore <= self.reset_neutral_zone_long):
            if self.bars_since_last_long_signal >= self.recovery_cooldown_bars:
                self.long_recovery_triggered = False
                
            if self.bars_since_last_short_signal >= self.recovery_cooldown_bars:
                self.short_recovery_triggered = False
        
        # Zusätzlicher Fix: Erlaube multiple recoveries wenn erlaubt
        if self.allow_multiple_recoveries:
            # Reset recovery flags nach Cooldown, auch ohne Neutral Zone
            if self.bars_since_last_long_signal >= self.recovery_cooldown_bars:
                self.long_recovery_triggered = False
            if self.bars_since_last_short_signal >= self.recovery_cooldown_bars:
                self.short_recovery_triggered = False

    def check_entry_signals(self, current_zscore: float) -> Tuple[bool, bool, dict]:
        if current_zscore is None:
            return False, False, {}
            
        long_signal = False
        short_signal = False
        
        debug_info = {
            'current_zscore': current_zscore,
            'z_extreme_long_since_cross': self.z_extreme_long_since_cross,
            'z_extreme_short_since_cross': self.z_extreme_short_since_cross,
            'long_recovery_triggered': self.long_recovery_triggered,
            'short_recovery_triggered': self.short_recovery_triggered,
            'bars_since_cross': len(self.zscore_since_cross),
            'current_parameters': {
                'z_min_threshold': self.z_min_threshold,
                'z_max_threshold': self.z_max_threshold,
                'recovery_delta': self.recovery_delta,
                'reset_neutral_zone_long': self.reset_neutral_zone_long,
                'reset_neutral_zone_short': self.reset_neutral_zone_short
            }
        }
        
        # Long Entry Logic
        if (self.z_extreme_long_since_cross is not None and 
            self.z_extreme_long_since_cross <= self.z_min_threshold and  
            current_zscore >= (self.z_extreme_long_since_cross + self.recovery_delta)):
            
            # Prüfe ob Recovery erlaubt ist
            recovery_allowed = False
            if not self.long_recovery_triggered:
                # Erste Recovery ist immer erlaubt
                recovery_allowed = True
            elif self.allow_multiple_recoveries and self.bars_since_last_long_signal >= self.recovery_cooldown_bars:
                # Multiple recoveries sind erlaubt nach Cooldown
                recovery_allowed = True
            
            if recovery_allowed:
                long_signal = True
                self.long_recovery_triggered = True
                self.bars_since_last_long_signal = 0
                debug_info['long_entry_reason'] = f"Recovery from {self.z_extreme_long_since_cross:.2f} to {current_zscore:.2f}"
            
        # Short Entry Logic  
        if (self.z_extreme_short_since_cross is not None and
            self.z_extreme_short_since_cross >= self.z_max_threshold and  
            current_zscore <= (self.z_extreme_short_since_cross - self.recovery_delta)):
            
            # Prüfe ob Recovery erlaubt ist
            recovery_allowed = False
            if not self.short_recovery_triggered:
                # Erste Recovery ist immer erlaubt
                recovery_allowed = True
            elif self.allow_multiple_recoveries and self.bars_since_last_short_signal >= self.recovery_cooldown_bars:
                # Multiple recoveries sind erlaubt nach Cooldown
                recovery_allowed = True
            
            if recovery_allowed:
                short_signal = True
                self.short_recovery_triggered = True
                self.bars_since_last_short_signal = 0
                debug_info['short_entry_reason'] = f"Recovery from {self.z_extreme_short_since_cross:.2f} to {current_zscore:.2f}"
                
        return long_signal, short_signal, debug_info
    
    def get_current_state(self) -> dict:
        return {
            'z_extreme_long_since_cross': self.z_extreme_long_since_cross,
            'z_extreme_short_since_cross': self.z_extreme_short_since_cross,
            'bars_since_long_extreme': self.bars_since_long_extreme,
            'bars_since_short_extreme': self.bars_since_short_extreme,
            'long_recovery_triggered': self.long_recovery_triggered,
            'short_recovery_triggered': self.short_recovery_triggered,
            'bars_since_cross': len(self.zscore_since_cross),
            'parameters': {
                'z_min_threshold': self.z_min_threshold,
                'z_max_threshold': self.z_max_threshold,
                'recovery_delta': self.recovery_delta,
                'reset_neutral_zone_long': self.reset_neutral_zone_long,
                'reset_neutral_zone_short': self.reset_neutral_zone_short
            }
        }
        
    def reset_state(self) -> None:
        self.reset_on_cross()
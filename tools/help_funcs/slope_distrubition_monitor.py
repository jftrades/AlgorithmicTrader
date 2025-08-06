import numpy as np
from typing import Optional, Dict

class SlopeDistributionMonitor:
    """Monitors the distribution of Kalman Slope values for parameter optimization."""
    
    def __init__(self, slope_thresholds: Dict[str, float] = None):
        self.slope_values = []
        self.bin_size = 0.01
        self.distribution = {}
        self.total_count = 0
        
        # YAML-Thresholds speichern
        self.slope_thresholds = slope_thresholds or {
            'strong_down': -0.04,
            'moderate_down': -0.01,
            'sideways': 0.01,
            'moderate_up': 0.04
        }
        
        print(f"[SLOPE MONITOR] Initialized with thresholds: {self.slope_thresholds}")
        
    def add_slope(self, slope_value: float):
        """Adds a new slope value to the distribution."""
        if slope_value is not None:
            self.slope_values.append(slope_value)
            self.total_count += 1
            
            bin_key = self._get_bin_key(slope_value)
            
            if bin_key not in self.distribution:
                self.distribution[bin_key] = 0
            self.distribution[bin_key] += 1
    
    def _get_bin_key(self, value: float) -> str:
        """Calculates the bin key for a given value."""
        lower_bound = int(value / self.bin_size) * self.bin_size
        upper_bound = lower_bound + self.bin_size
        return f"{lower_bound:.2f} to {upper_bound:.2f}"
    
    def _classify_slope(self, slope: float) -> str:
        """Klassifiziert Slope basierend auf YAML-Thresholds."""
        thresholds = self.slope_thresholds
        
        if slope < thresholds['strong_down']:
            return 'strong_down'
        elif slope < thresholds['moderate_down']:
            return 'moderate_down'
        elif slope <= thresholds['sideways']:
            return 'sideways'
        elif slope <= thresholds['moderate_up']:
            return 'moderate_up'
        else:
            return 'strong_up'
    
    def print_distribution(self):
        """Prints the complete slope distribution analysis with YAML thresholds."""
        if not self.distribution:
            print("No slope data collected.")
            return
            
        print(f"\n{'='*100}")
        print(f"KALMAN SLOPE DISTRIBUTION ANALYSIS - Total Samples: {self.total_count}")
        print(f"Using YAML Thresholds: {self.slope_thresholds}")
        print(f"{'='*100}")
        
        # DETAILLIERTE BIN-VERTEILUNG (alle 0.01 Schritte wie früher)
        print(f"\nDETAILED BIN DISTRIBUTION (0.01 steps):")
        print(f"{'='*80}")
        
        sorted_bins = sorted(self.distribution.items(), key=lambda x: float(x[0].split(' to ')[0]))
        
        for bin_key, count in sorted_bins:
            percentage = (count / self.total_count) * 100
            bar_length = max(1, int(percentage * 2))  # Skalierung für Visualisierung
            bar = "█" * min(bar_length, 40)
            print(f"{bin_key:>20}: {count:>4} ({percentage:>5.1f}%) {bar}")
        
        # SECTOR-BASIERTE VERTEILUNG (basierend auf YAML-Thresholds)
        slopes_array = np.array(self.slope_values)
        
        sector_counts = {
            'strong_down': 0,
            'moderate_down': 0,
            'sideways': 0,
            'moderate_up': 0,
            'strong_up': 0
        }
        
        # Zähle jeden Slope in seinem Sektor
        for slope in slopes_array:
            sector = self._classify_slope(slope)
            sector_counts[sector] += 1
        
        print(f"\n{'='*80}")
        print(f"SECTOR DISTRIBUTION (based on your YAML thresholds):")
        print(f"{'='*80}")
        
        total_check = 0
        for sector, count in sector_counts.items():
            percentage = (count / self.total_count) * 100
            bar_length = max(1, int(percentage * 1.5))  # Etwas kürzere Balken für Sektoren
            bar = "█" * min(bar_length, 50)
            
            print(f"{sector:>15}: {count:>6} ({percentage:>6.1f}%) {bar}")
            total_check += count
        
        print(f"{'Total Check':>15}: {total_check:>6} (should equal {self.total_count})")
        
        # THRESHOLD-ANALYSE
        thresholds = self.slope_thresholds
        print(f"\n{'='*80}")
        print(f"THRESHOLD ANALYSIS:")
        print(f"{'='*80}")
        print(f"strong_down   : slope < {thresholds['strong_down']:>7.4f} → {sector_counts['strong_down']:>6} samples ({sector_counts['strong_down']/self.total_count*100:>5.1f}%)")
        print(f"moderate_down : {thresholds['strong_down']:>7.4f} ≤ slope < {thresholds['moderate_down']:>7.4f} → {sector_counts['moderate_down']:>6} samples ({sector_counts['moderate_down']/self.total_count*100:>5.1f}%)")
        print(f"sideways      : {thresholds['moderate_down']:>7.4f} ≤ slope ≤ {thresholds['sideways']:>7.4f} → {sector_counts['sideways']:>6} samples ({sector_counts['sideways']/self.total_count*100:>5.1f}%)")
        print(f"moderate_up   : {thresholds['sideways']:>7.4f} < slope ≤ {thresholds['moderate_up']:>7.4f} → {sector_counts['moderate_up']:>6} samples ({sector_counts['moderate_up']/self.total_count*100:>5.1f}%)")
        print(f"strong_up     : slope > {thresholds['moderate_up']:>7.4f} → {sector_counts['strong_up']:>6} samples ({sector_counts['strong_up']/self.total_count*100:>5.1f}%)")
        
        # STATISTIKEN
        print(f"\n{'='*80}")
        print(f"STATISTICAL SUMMARY:")
        print(f"{'='*80}")
        print(f"Minimum:         {slopes_array.min():.6f}")
        print(f"Maximum:         {slopes_array.max():.6f}")
        print(f"Mean:            {slopes_array.mean():.6f}")
        print(f"Std Dev:         {slopes_array.std():.6f}")
        print(f"Median:          {np.median(slopes_array):.6f}")
        print(f"25th Percentile: {np.percentile(slopes_array, 25):.6f}")
        print(f"75th Percentile: {np.percentile(slopes_array, 75):.6f}")
        
        # ZUSÄTZLICHE RANGE-ANALYSE
        print(f"\n{'='*80}")
        print(f"RANGE ANALYSIS:")
        print(f"{'='*80}")
        
        # Zeige welche Bins in welchen Sektoren liegen
        for sector in ['strong_down', 'moderate_down', 'sideways', 'moderate_up', 'strong_up']:
            sector_bins = []
            sector_total = 0
            
            for bin_key, count in sorted_bins:
                bin_center = float(bin_key.split(' to ')[0]) + 0.005  # Mitte des Bins
                if self._classify_slope(bin_center) == sector:
                    sector_bins.append((bin_key, count))
                    sector_total += count
            
            if sector_bins:
                print(f"\n{sector.upper()} sector bins:")
                for bin_key, count in sector_bins:
                    percentage = (count / sector_total) * 100
                    print(f"  {bin_key}: {count} ({percentage:.1f}% of sector)")
        
        print(f"\n{'='*100}\n")

    def get_current_sector_distribution(self) -> dict:
        """Returns current sector distribution percentages based on YAML thresholds."""
        if not self.slope_values:
            return {}
            
        slopes = np.array(self.slope_values)
        total = len(slopes)
        thresholds = self.slope_thresholds
        
        return {
            'strong_down': np.sum(slopes < thresholds['strong_down']) / total * 100,
            'moderate_down': np.sum((slopes >= thresholds['strong_down']) & (slopes < thresholds['moderate_down'])) / total * 100,
            'sideways': np.sum((slopes >= thresholds['moderate_down']) & (slopes <= thresholds['sideways'])) / total * 100,
            'moderate_up': np.sum((slopes > thresholds['sideways']) & (slopes <= thresholds['moderate_up'])) / total * 100,
            'strong_up': np.sum(slopes > thresholds['moderate_up']) / total * 100
        }

    def print_progress_update(self, current_slope: Optional[float] = None):
        """Prints progress update with current slope."""
        if current_slope is not None:
            print(f"Slope Monitor: {self.total_count} samples collected, current slope: {current_slope:.6f}")
        else:
            print(f"Slope Monitor: {self.total_count} samples collected")

    def analyze_custom_thresholds(self, custom_thresholds: list) -> dict:
        """Analyzes custom threshold boundaries."""
        if not self.slope_values:
            return {}
            
        slopes_array = np.array(self.slope_values)
        
        analysis = {}
        for i, threshold in enumerate(custom_thresholds):
            if i == 0:
                count = np.sum(slopes_array < threshold)
                analysis[f"< {threshold}"] = {
                    'count': count,
                    'percentage': count / self.total_count * 100
                }
            else:
                prev_threshold = custom_thresholds[i-1]
                count = np.sum((slopes_array >= prev_threshold) & (slopes_array < threshold))
                analysis[f"{prev_threshold} to {threshold}"] = {
                    'count': count,
                    'percentage': count / self.total_count * 100
                }
        
        # Last bucket
        count = np.sum(slopes_array >= custom_thresholds[-1])
        analysis[f">= {custom_thresholds[-1]}"] = {
            'count': count,
            'percentage': count / self.total_count * 100
        }
        
        return analysis
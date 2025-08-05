import numpy as np
from typing import Optional

class SlopeDistributionMonitor:
    """Monitors the distribution of Kalman Slope values for parameter optimization."""
    
    def __init__(self):
        self.slope_values = []
        self.bin_size = 0.01
        self.distribution = {}
        self.total_count = 0
        
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
    
    def print_distribution(self):
        """Prints the complete slope distribution analysis."""
        if not self.distribution:
            print("No slope data collected.")
            return
            
        print(f"\n{'-'*80}")
        print(f"KALMAN SLOPE DISTRIBUTION ANALYSIS - Total Samples: {self.total_count}")
        print(f"{'-'*80}")
        
        # Sort by numeric value
        sorted_bins = sorted(self.distribution.items(), 
                           key=lambda x: float(x[0].split(' to ')[0]))
        
        for bin_range, count in sorted_bins:
            percentage = (count / self.total_count) * 100
            bar_length = int(percentage / 2)
            bar = "=" * bar_length
            
            print(f"{bin_range:>15} | {count:>6} ({percentage:>5.1f}%) {bar}")
        
        # Statistics
        slopes_array = np.array(self.slope_values)
        print(f"\nSTATISTICAL SUMMARY:")
        print(f"Minimum:      {slopes_array.min():.6f}")
        print(f"Maximum:      {slopes_array.max():.6f}")
        print(f"Mean:         {slopes_array.mean():.6f}")
        print(f"Std Dev:      {slopes_array.std():.6f}")
        print(f"Median:       {np.median(slopes_array):.6f}")
        
        # Threshold Analysis
        print(f"\nTHRESHOLD ANALYSIS:")
        thresholds = [-0.1, -0.03, 0.03, 0.1]
        sector_names = ["strong_down", "moderate_down", "sideways", "moderate_up", "strong_up"]
        
        for i, threshold in enumerate(thresholds):
            if i == 0:
                count = np.sum(slopes_array < threshold)
                print(f"< {threshold:>6.2f} ({sector_names[i]}):  {count:>6} ({count/self.total_count*100:>5.1f}%)")
            elif i == len(thresholds) - 1:
                count = np.sum(slopes_array > threshold)
                print(f"> {threshold:>6.2f} ({sector_names[i+1]}):    {count:>6} ({count/self.total_count*100:>5.1f}%)")
            else:
                prev_threshold = thresholds[i-1]
                count = np.sum((slopes_array >= prev_threshold) & (slopes_array < threshold))
                print(f"{prev_threshold:>6.2f} to {threshold:>6.2f} ({sector_names[i]}): {count:>6} ({count/self.total_count*100:>5.1f}%)")
        
        print(f"{'-'*80}\n")

    def get_current_sector_distribution(self) -> dict:
        """Returns current sector distribution percentages."""
        if not self.slope_values:
            return {}
            
        slopes = np.array(self.slope_values)
        total = len(slopes)
        
        return {
            'strong_down': np.sum(slopes < -0.1) / total * 100,
            'moderate_down': np.sum((slopes >= -0.1) & (slopes < -0.03)) / total * 100,
            'sideways': np.sum((slopes >= -0.03) & (slopes <= 0.03)) / total * 100,
            'moderate_up': np.sum((slopes > 0.03) & (slopes <= 0.1)) / total * 100,
            'strong_up': np.sum(slopes > 0.1) / total * 100
        }

    def print_progress_update(self, current_slope: Optional[float] = None):
        """Prints progress update with current slope."""
        if current_slope is not None:
            print(f"Slope Monitor: {self.total_count} samples collected, current slope: {current_slope:.6f}")
        else:
            print(f"Slope Monitor: {self.total_count} samples collected")

    def analyze_thresholds(self, custom_thresholds: list = None) -> dict:
        """Analyzes custom threshold boundaries."""
        if not self.slope_values:
            return {}
            
        thresholds = custom_thresholds or [-0.15, -0.1, -0.05, -0.03, 0.03, 0.05, 0.1, 0.15]
        slopes_array = np.array(self.slope_values)
        
        analysis = {}
        for i, threshold in enumerate(thresholds):
            if i == 0:
                count = np.sum(slopes_array < threshold)
                analysis[f"< {threshold}"] = {
                    'count': count,
                    'percentage': count / self.total_count * 100
                }
            else:
                prev_threshold = thresholds[i-1]
                count = np.sum((slopes_array >= prev_threshold) & (slopes_array < threshold))
                analysis[f"{prev_threshold} to {threshold}"] = {
                    'count': count,
                    'percentage': count / self.total_count * 100
                }
        
        # Last bucket
        count = np.sum(slopes_array >= thresholds[-1])
        analysis[f">= {thresholds[-1]}"] = {
            'count': count,
            'percentage': count / self.total_count * 100
        }
        
        return analysis
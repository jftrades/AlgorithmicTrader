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
        """Prints the complete slope distribution analysis with improved visualization."""
        if not self.distribution:
            print("No slope data collected.")
            return
            
        print(f"\n{'='*100}")
        print(f"KALMAN SLOPE DISTRIBUTION ANALYSIS - Total Samples: {self.total_count}")
        print(f"{'='*100}")
        
        # Sort by numeric value
        sorted_bins = sorted(self.distribution.items(), 
                           key=lambda x: float(x[0].split(' to ')[0]))
        
        # Verify total count matches
        total_bin_count = sum(count for _, count in sorted_bins)
        if total_bin_count != self.total_count:
            print(f"WARNING: Bin count mismatch! Bins: {total_bin_count}, Total: {self.total_count}")
        
        # Show only bins with significant data (> 0.01% or top 50 bins)
        significant_bins = [(bin_range, count) for bin_range, count in sorted_bins 
                           if (count / self.total_count) * 100 >= 0.01]
        
        # If we have too many bins, show top 50 by count
        if len(significant_bins) > 50:
            significant_bins = sorted(significant_bins, key=lambda x: x[1], reverse=True)[:50]
            significant_bins = sorted(significant_bins, key=lambda x: float(x[0].split(' to ')[0]))
            print(f"Showing top 50 bins by count (others < 0.01%)")
        
        displayed_count = 0
        for bin_range, count in significant_bins:
            percentage = (count / self.total_count) * 100
            bar_length = max(1, int(percentage * 3))
            bar = "█" * min(bar_length, 80)
            
            print(f"{bin_range:>15} | {count:>6} ({percentage:>6.2f}%) {bar}")
            displayed_count += count
        
        # Show summary of undisplayed bins
        undisplayed_count = self.total_count - displayed_count
        if undisplayed_count > 0:
            undisplayed_pct = (undisplayed_count / self.total_count) * 100
            print(f"{'Other small bins':>15} | {undisplayed_count:>6} ({undisplayed_pct:>6.2f}%) (not displayed)")
        
        # Verify percentage sum
        print(f"\nDistribution Verification: {displayed_count + undisplayed_count} samples = 100.00%")
        
        # Statistics
        slopes_array = np.array(self.slope_values)
        print(f"\n{'='*50}")
        print(f"STATISTICAL SUMMARY:")
        print(f"{'='*50}")
        print(f"Minimum:         {slopes_array.min():.6f}")
        print(f"Maximum:         {slopes_array.max():.6f}")
        print(f"Mean:            {slopes_array.mean():.6f}")
        print(f"Std Dev:         {slopes_array.std():.6f}")
        print(f"Median:          {np.median(slopes_array):.6f}")
        print(f"25th Percentile: {np.percentile(slopes_array, 25):.6f}")
        print(f"75th Percentile: {np.percentile(slopes_array, 75):.6f}")
        
        # OPTIMAL THRESHOLD SUGGESTIONS
        print(f"\n{'='*80}")
        print(f"OPTIMAL THRESHOLD SUGGESTIONS (Based on Data Distribution)")
        print(f"{'='*80}")
        
        # Calculate percentile-based thresholds for 5 equal sectors
        percentiles = [10, 25, 75, 90]
        threshold_values = [np.percentile(slopes_array, p) for p in percentiles]
        
        print(f"RECOMMENDED 5-SECTOR SPLIT (20% each):")
        print(f"strong_down:   < {threshold_values[0]:>8.4f}  ({percentiles[0]}th percentile)")
        print(f"moderate_down: {threshold_values[0]:>8.4f} to {threshold_values[1]:>8.4f}  ({percentiles[0]}th to {percentiles[1]}th percentile)")
        print(f"sideways:      {threshold_values[1]:>8.4f} to {threshold_values[2]:>8.4f}  ({percentiles[1]}th to {percentiles[2]}th percentile)")
        print(f"moderate_up:   {threshold_values[2]:>8.4f} to {threshold_values[3]:>8.4f}  ({percentiles[2]}th to {percentiles[3]}th percentile)")
        print(f"strong_up:     > {threshold_values[3]:>8.4f}  ({percentiles[3]}th percentile)")
        
        # Alternative: Symmetric thresholds around 0
        std_dev = slopes_array.std()
        mean_val = slopes_array.mean()
        
        print(f"\nRECOMMENDED SYMMETRIC THRESHOLDS (Centered around 0):")
        symmetric_strong = 2.0 * std_dev
        symmetric_moderate = 1.0 * std_dev
        
        print(f"strong_down:   < {-symmetric_strong:>8.4f}  (2 std dev below 0)")
        print(f"moderate_down: {-symmetric_strong:>8.4f} to {-symmetric_moderate:>8.4f}  (1-2 std dev below 0)")
        print(f"sideways:      {-symmetric_moderate:>8.4f} to {symmetric_moderate:>8.4f}  (±1 std dev around 0)")
        print(f"moderate_up:   {symmetric_moderate:>8.4f} to {symmetric_strong:>8.4f}  (1-2 std dev above 0)")
        print(f"strong_up:     > {symmetric_strong:>8.4f}  (2 std dev above 0)")
        
        # YAML Configuration suggestions
        print(f"\n{'='*80}")
        print(f"SUGGESTED YAML CONFIGURATIONS:")
        print(f"{'='*80}")
        
        print(f"\n# Option 1: Percentile-based (balanced sectors)")
        print(f"kalman_slope_thresholds:")
        print(f"  strong_down: {threshold_values[0]:.4f}")
        print(f"  moderate_down: {threshold_values[1]:.4f}")
        print(f"  sideways: {threshold_values[2]:.4f}")
        print(f"  moderate_up: {threshold_values[3]:.4f}")
        
        print(f"\n# Option 2: Symmetric around 0 (standard deviation based)")
        print(f"kalman_slope_thresholds:")
        print(f"  strong_down: {-symmetric_strong:.4f}")
        print(f"  moderate_down: {-symmetric_moderate:.4f}")
        print(f"  sideways: {symmetric_moderate:.4f}")
        print(f"  moderate_up: {symmetric_strong:.4f}")
        
        print(f"\n{'='*100}\n")

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
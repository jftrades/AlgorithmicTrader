import numpy as np


class SlopeDistributionMonitor:
    def __init__(self, bin_size: float = 0.001):
        self.slope_values = []
        self.bin_size = bin_size
        self.distribution = {}
        self.total_count = 0
        
    def add_slope(self, slope_value: float):
        if slope_value is not None:
            self.slope_values.append(slope_value)
            self.total_count += 1
            
            bin_key = self._get_bin_key(slope_value)
            
            if bin_key not in self.distribution:
                self.distribution[bin_key] = 0
            self.distribution[bin_key] += 1
    
    def _get_bin_key(self, value: float) -> str:
        lower_bound = int(value / self.bin_size) * self.bin_size
        upper_bound = lower_bound + self.bin_size
        return f"{lower_bound:.3f} to {upper_bound:.3f}"
    
    def print_distribution(self):
        if not self.distribution:
            print("No slope data collected.")
            return
            
        print(f"\n{'='*80}")
        print(f"KALMAN SLOPE DISTRIBUTION - Total Samples: {self.total_count}")
        print(f"Bin size: {self.bin_size}")
        print(f"{'='*80}")
        
        sorted_bins = sorted(self.distribution.items(), key=lambda x: float(x[0].split(' to ')[0]))
        
        for bin_key, count in sorted_bins:
            percentage = (count / self.total_count) * 100
            bar_length = max(1, int(percentage * 2))
            bar = "█" * min(bar_length, 50)
            print(f"{bin_key:>25}: {count:>6} ({percentage:>5.1f}%) {bar}")
        
        slopes_array = np.array(self.slope_values)
        print("\nStatistics:")
        print(f"Min: {slopes_array.min():.6f} | Max: {slopes_array.max():.6f}")
        print(f"Mean: {slopes_array.mean():.6f} | Std: {slopes_array.std():.6f}")
        print(f"Median: {np.median(slopes_array):.6f}")
        print(f"{'='*80}\n")
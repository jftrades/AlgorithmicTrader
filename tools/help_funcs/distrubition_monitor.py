
import numpy as np

class DistributionMonitor:
    def __init__(self, bin_size: float = 0.001, label: str = "Value", decay_factor: float = 0.01):
        self.values = []
        self.timestamps = []  # To track chronological order
        self.bin_size = bin_size    
        self.distribution = {}
        self.total_count = 0
        self.label = label
        self.decay_factor = decay_factor  # Higher = more weight to recent values
        
    def add(self, value: float):
        if value is not None:
            self.values.append(value)
            self.timestamps.append(len(self.values))  # Simple sequential timestamp
            self.total_count += 1
            bin_key = self._get_bin_key(value)
            if bin_key not in self.distribution:
                self.distribution[bin_key] = 0
            self.distribution[bin_key] += 1

    def _get_bin_key(self, value: float) -> str:
        lower_bound = int(value / self.bin_size) * self.bin_size
        upper_bound = lower_bound + self.bin_size
        return f"{lower_bound:.3f} to {upper_bound:.3f}"
    
    def _calculate_exponential_weights(self) -> np.ndarray:
        """Calculate exponential weights where more recent values have higher weight"""
        if len(self.values) == 0:
            return np.array([])
        
        # Create weights that increase exponentially for more recent values
        n = len(self.values)
        
        # Prevent overflow by clipping the exponent values
        exponents = self.decay_factor * np.arange(n)
        # Clip to prevent overflow (exp(700) is near float64 limit)
        exponents = np.clip(exponents, -700, 700)
        
        weights = np.exp(exponents)
        
        # Prevent division by zero and handle potential overflow
        weights_sum = np.sum(weights)
        if weights_sum == 0 or not np.isfinite(weights_sum):
            # Fallback to uniform weights if numerical issues
            weights = np.ones(n)
            weights_sum = n
        
        # Normalize weights to sum to 1
        weights = weights / weights_sum
        return weights
    
    def _calculate_weighted_percentiles(self, percentiles: list) -> dict:
        """Calculate exponentially weighted percentiles"""
        if len(self.values) < 10:
            return {p: None for p in percentiles}
        
        values_array = np.array(self.values)
        weights = self._calculate_exponential_weights()
        
        # Check for invalid weights
        if not np.all(np.isfinite(weights)) or np.sum(weights) == 0:
            # Fallback to simple percentiles if weights are invalid
            results = {}
            for percentile in percentiles:
                results[percentile] = np.percentile(values_array, percentile)
            return results
        
        # Sort values and corresponding weights
        sorted_indices = np.argsort(values_array)
        sorted_values = values_array[sorted_indices]
        sorted_weights = weights[sorted_indices]
        
        # Calculate cumulative weights
        cumulative_weights = np.cumsum(sorted_weights)
        
        results = {}
        for percentile in percentiles:
            target_weight = percentile / 100.0
            # Find the value where cumulative weight exceeds target
            idx = np.searchsorted(cumulative_weights, target_weight, side='left')
            if idx >= len(sorted_values):
                idx = len(sorted_values) - 1
            results[percentile] = sorted_values[idx]
        
        return results
    
    def _get_outlier_analysis(self) -> dict:
        """Analyze outliers using exponentially weighted percentiles"""
        key_percentiles = [1, 5, 25, 50, 75, 95, 99]
        weighted_percentiles = self._calculate_weighted_percentiles(key_percentiles)
        
        # Also calculate simple percentiles for comparison
        simple_percentiles = {}
        if len(self.values) > 0:
            values_array = np.array(self.values)
            for p in key_percentiles:
                simple_percentiles[p] = np.percentile(values_array, p)
        
        return {
            'weighted': weighted_percentiles,
            'simple': simple_percentiles
        }

    def print_distribution(self, min_count_threshold: int = 5, max_bars: int = 80):
        if not self.distribution:
            print(f"No {self.label} data collected.")
            return
        print(f"\n{'='*80}")
        print(f"{self.label.upper()} DISTRIBUTION - Total Samples: {self.total_count}")
        print(f"Bin size: {self.bin_size} | Showing bins with ≥{min_count_threshold} samples")
        print(f"{'='*80}")
        filtered_bins = {k: v for k, v in self.distribution.items() if v >= min_count_threshold}
        if not filtered_bins:
            print(f"No bins with ≥{min_count_threshold} samples found.")
            return
        sorted_bins = sorted(filtered_bins.items(), key=lambda x: float(x[0].split(' to ')[0]))
        max_count = max(filtered_bins.values())
        for bin_key, count in sorted_bins:
            percentage = (count / self.total_count) * 100
            bar_length = max(1, int((count / max_count) * max_bars))
            bar = "█" * bar_length
            print(f"{bin_key:>25}: {count:>6} ({percentage:>5.1f}%) {bar}")
        
        arr = np.array(self.values)
        filtered_count = sum(filtered_bins.values())
        print(f"\nShowing {len(filtered_bins)} bins ({filtered_count} samples, {(filtered_count/self.total_count)*100:.1f}% of total)")
        
        print("\nBASIC STATISTICS:")
        print(f"Min: {arr.min():.6f} | Max: {arr.max():.6f}")
        print(f"Mean: {arr.mean():.6f} | Std: {arr.std():.6f}")
        print(f"Median: {np.median(arr):.6f}")
        
        # Add exponentially weighted percentile analysis
        outlier_analysis = self._get_outlier_analysis()
        
        print(f"\n{'='*80}")
        print("EXPONENTIALLY WEIGHTED PERCENTILES (Recent data weighted more heavily)")
        print(f"Decay factor: {self.decay_factor:.3f} (higher = more recent bias)")
        print(f"{'='*80}")
        
        weighted = outlier_analysis['weighted']
        simple = outlier_analysis['simple']
        
        print("Percentile | Exponential Weight | Simple/Historical | Difference")
        print("-" * 68)
        
        for percentile in [1, 5, 25, 50, 75, 95, 99]:
            w_val = weighted.get(percentile)
            s_val = simple.get(percentile)
            
            if w_val is not None and s_val is not None:
                diff = w_val - s_val
                diff_pct = (diff / s_val * 100) if s_val != 0 else 0
                print(f"   {percentile:2d}%    |    {w_val:10.6f}    |    {s_val:10.6f}    | {diff:+8.6f} ({diff_pct:+5.1f}%)")
            else:
                print(f"   {percentile:2d}%    |        N/A         |        N/A         |     N/A")
        
        print(f"\n{'='*25} OUTLIER BOUNDARIES {'='*25}")
        print("CONSERVATIVE (95% confidence - filters 5% outliers):")
        if weighted.get(5) is not None and weighted.get(95) is not None:
            print(f"  Lower Bound (5%):  {weighted[5]:10.6f}")
            print(f"  Upper Bound (95%): {weighted[95]:10.6f}")
            print(f"  Range Width:       {weighted[95] - weighted[5]:10.6f}")
        
        print("\nSTRICT (99% confidence - filters 1% outliers):")
        if weighted.get(1) is not None and weighted.get(99) is not None:
            print(f"  Lower Bound (1%):  {weighted[1]:10.6f}")
            print(f"  Upper Bound (99%): {weighted[99]:10.6f}")
            print(f"  Range Width:       {weighted[99] - weighted[1]:10.6f}")
        
        # Show weighting effect
        if len(self.values) > 10:
            weights = self._calculate_exponential_weights()
            recent_weight_sum = np.sum(weights[-int(len(weights)*0.1):])  # Last 10% of data
            old_weight_sum = np.sum(weights[:int(len(weights)*0.1)])      # First 10% of data
            print("\nWEIGHTING ANALYSIS:")
            print(f"  Recent 10% of data weight: {recent_weight_sum:.3f}")
            print(f"  Oldest 10% of data weight: {old_weight_sum:.3f}")
            print(f"  Recent/Old ratio: {recent_weight_sum/old_weight_sum:.1f}x more important")
        
        print(f"{'='*80}\n")

class SlopeDistributionMonitor(DistributionMonitor):
    def __init__(self, bin_size: float = 0.0005, decay_factor: float = 0.02):
        # Higher decay factor for slopes since market regimes can change quickly
        super().__init__(bin_size=bin_size, label="Slope", decay_factor=decay_factor)

    def add_slope(self, slope_value: float):
        self.add(slope_value)

class ATRDistributionMonitor(DistributionMonitor):
    def __init__(self, bin_size: float = 0.01, decay_factor: float = 0.01):
        # Lower decay factor for ATR since volatility regimes change more slowly
        super().__init__(bin_size=bin_size, label="ATR", decay_factor=decay_factor)

    def add_atr(self, atr_value: float):
        self.add(atr_value)
"""
Test file to demonstrate the VWAP anchoring methods.
This shows how the different anchor methods work.
"""

import datetime
import numpy as np
from collections import namedtuple
from VWAP_ZScore_HTF import VWAPZScoreHTFAnchored

Bar = namedtuple('Bar', ['ts_event', 'open', 'high', 'low', 'close', 'volume'])

def create_test_bar(timestamp, open_price, high, low, close, volume):
    return Bar(
        ts_event=int(timestamp.timestamp() * 1_000_000_000),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume
    )

def test_kalman_cross_anchoring():
    print("=== Testing Kalman Cross Anchoring ===")
    
    vwap = VWAPZScoreHTFAnchored(
        anchor_method="kalman_cross",
        min_bars_for_zscore=5,
        reset_grace_period=5
    )
    
    base_time = datetime.datetime(2024, 1, 1, 15, 40)
    
    bars_data = [
        (100.0, 500), (101.0, 600), (102.0, 550), (101.5, 700), (103.0, 450),
        (102.5, 520), (104.0, 680), (103.5, 430), (105.0, 590), (104.5, 610)
    ]
    
    kalman_means = [101.0, 101.2, 101.5, 101.8, 102.0, 102.5, 103.0, 103.2, 103.5, 103.8]
    
    for i, ((close, volume), kalman_mean) in enumerate(zip(bars_data, kalman_means)):
        bar = create_test_bar(
            base_time + datetime.timedelta(minutes=i*5),
            close-0.5, close+0.5, close-0.5, close, volume
        )
        
        vwap_value, zscore = vwap.update(bar, kalman_exit_mean=kalman_mean)
        segment_info = vwap.get_segment_info()
        
        print(f"Bar {i+1}: Close={close:.1f}, Kalman={kalman_mean:.1f}, VWAP={vwap_value:.2f if vwap_value else 'None'}, "
              f"ZScore={zscore:.2f if zscore else 'None'}, Anchor={segment_info['anchor_reason']}, "
              f"Bars in segment={segment_info['bars_in_segment']}")

def test_daily_anchoring():
    print("\n=== Testing Daily Anchoring ===")
    
    vwap = VWAPZScoreHTFAnchored(
        anchor_method="daily",
        min_bars_for_zscore=3,
        reset_grace_period=0
    )
    
    base_time = datetime.datetime(2024, 1, 1, 15, 40)
    
    for day in range(3):
        print(f"\n--- Day {day + 1} ---")
        for hour in range(4):
            bar_time = base_time + datetime.timedelta(days=day, hours=hour)
            close = 100 + day * 2 + hour * 0.5
            volume = 500 + hour * 50
            
            bar = create_test_bar(bar_time, close-0.5, close+0.5, close-0.5, close, volume)
            
            vwap_value, zscore = vwap.update(bar)
            segment_info = vwap.get_segment_info()
            
            print(f"  {bar_time.strftime('%Y-%m-%d %H:%M')}: Close={close:.1f}, "
                  f"VWAP={vwap_value:.2f if vwap_value else 'None'}, "
                  f"ZScore={zscore:.2f if zscore else 'None'}, "
                  f"Anchor={segment_info['anchor_reason']}, "
                  f"Bars in segment={segment_info['bars_in_segment']}")

def test_weekly_anchoring():
    print("\n=== Testing Weekly Anchoring ===")
    
    vwap = VWAPZScoreHTFAnchored(
        anchor_method="weekly",
        min_bars_for_zscore=3,
        reset_grace_period=0
    )
    
    base_time = datetime.datetime(2024, 1, 1, 15, 40)  # Monday
    
    for week in range(2):
        print(f"\n--- Week {week + 1} ---")
        for day in range(7):
            bar_time = base_time + datetime.timedelta(weeks=week, days=day)
            close = 100 + week * 5 + day * 0.3
            volume = 500 + day * 20
            
            bar = create_test_bar(bar_time, close-0.5, close+0.5, close-0.5, close, volume)
            
            vwap_value, zscore = vwap.update(bar)
            segment_info = vwap.get_segment_info()
            
            print(f"  {bar_time.strftime('%A %Y-%m-%d')}: Close={close:.1f}, "
                  f"VWAP={vwap_value:.2f if vwap_value else 'None'}, "
                  f"ZScore={zscore:.2f if zscore else 'None'}, "
                  f"Anchor={segment_info['anchor_reason']}, "
                  f"Bars in segment={segment_info['bars_in_segment']}")

def test_rolling_anchoring():
    print("\n=== Testing Rolling VWAP ===")
    
    vwap = VWAPZScoreHTFAnchored(
        anchor_method="rolling",
        rolling_window_bars=5,
        min_bars_for_zscore=3
    )
    
    base_time = datetime.datetime(2024, 1, 1, 15, 40)
    
    for i in range(10):
        bar_time = base_time + datetime.timedelta(minutes=i*5)
        close = 100 + i * 0.5 + np.sin(i * 0.5) * 2
        volume = 500 + i * 10
        
        bar = create_test_bar(bar_time, close-0.5, close+0.5, close-0.5, close, volume)
        
        vwap_value, zscore = vwap.update(bar)
        segment_info = vwap.get_segment_info()
        
        print(f"Bar {i+1}: Close={close:.1f}, "
              f"VWAP={vwap_value:.2f if vwap_value else 'None'}, "
              f"ZScore={zscore:.2f if zscore else 'None'}, "
              f"Rolling window bars={segment_info['bars_in_segment']}")

if __name__ == "__main__":
    test_kalman_cross_anchoring()
    test_daily_anchoring()
    test_weekly_anchoring()
    test_rolling_anchoring()
    
    print("\n=== Summary ===")
    print("1. kalman_cross: VWAP resets when price crosses Kalman filter (original behavior)")
    print("2. daily: VWAP resets at start of each new trading day")
    print("3. weekly: VWAP resets at start of each new week")
    print("4. rolling: Uses fixed rolling window, no resets")

#!/usr/bin/env python3
"""
Quick test to verify the rolling buffer functionality works correctly
"""

from tools.structure.PivotArchive import PivotArchive, SwingPoint
from decimal import Decimal

def test_rolling_buffer():
    """Test that rolling buffer correctly maintains max 3 items"""
    
    # Create a PivotArchive instance
    archive = PivotArchive()
    
    print("🧪 Testing Rolling Buffer Logic")
    print("=" * 40)
    
    # Create some mock swing points
    def create_mock_swing(price, is_high, timestamp):
        swing = SwingPoint(price=Decimal(str(price)), timestamp=timestamp, is_high=is_high)
        return swing
    
    # Test critical highs buffer
    print("\n📈 Testing Critical Highs Buffer (max 3 items):")
    
    highs = [
        create_mock_swing(100.0, True, 1),
        create_mock_swing(101.0, True, 2),
        create_mock_swing(102.0, True, 3),
        create_mock_swing(103.0, True, 4),  # Should pop first one
        create_mock_swing(104.0, True, 5),  # Should pop second one
    ]
    
    for i, high in enumerate(highs):
        archive._add_critical_high(high)
        print(f"Added high {high.price} -> Buffer length: {len(archive.critical_highs)}")
        prices = [float(h.price) for h in archive.critical_highs]
        print(f"  Current buffer: {prices}")
        
        # Verify buffer never exceeds 3 items
        assert len(archive.critical_highs) <= 3, f"Buffer exceeded 3 items: {len(archive.critical_highs)}"
    
    print(f"\n✅ Final highs buffer: {[float(h.price) for h in archive.critical_highs]}")
    assert len(archive.critical_highs) == 3, f"Expected 3 items, got {len(archive.critical_highs)}"
    assert float(archive.critical_highs[-1].price) == 104.0, "Last item should be 104.0"
    
    # Test critical lows buffer
    print("\n📉 Testing Critical Lows Buffer (max 3 items):")
    
    lows = [
        create_mock_swing(50.0, False, 1),
        create_mock_swing(49.0, False, 2),
        create_mock_swing(48.0, False, 3),
        create_mock_swing(47.0, False, 4),  # Should pop first one
    ]
    
    for i, low in enumerate(lows):
        archive._add_critical_low(low)
        print(f"Added low {low.price} -> Buffer length: {len(archive.critical_lows)}")
        prices = [float(low.price) for low in archive.critical_lows]
        print(f"  Current buffer: {prices}")
        
        # Verify buffer never exceeds 3 items
        assert len(archive.critical_lows) <= 3, f"Buffer exceeded 3 items: {len(archive.critical_lows)}"
    
    print(f"\n✅ Final lows buffer: {[float(low.price) for low in archive.critical_lows]}")
    assert len(archive.critical_lows) == 3, f"Expected 3 items, got {len(archive.critical_lows)}"
    assert float(archive.critical_lows[-1].price) == 47.0, "Last item should be 47.0"
    
    # Test interface methods
    print("\n🔌 Testing Interface Methods:")
    
    last_high = archive.get_last_swing_high()
    last_low = archive.get_last_swing_low()
    
    print(f"get_last_swing_high(): {float(last_high.price) if last_high else None}")
    print(f"get_last_swing_low(): {float(last_low.price) if last_low else None}")
    
    assert last_high is not None, "Should have a last high"
    assert last_low is not None, "Should have a last low"
    assert float(last_high.price) == 104.0, f"Expected 104.0, got {float(last_high.price)}"
    assert float(last_low.price) == 47.0, f"Expected 47.0, got {float(last_low.price)}"
    
    # Test key levels
    key_levels = archive.get_key_levels()
    print(f"\nget_key_levels(): {key_levels}")
    
    assert key_levels["last_swing_high"] == 104.0, "Key levels high mismatch"
    assert key_levels["last_swing_low"] == 47.0, "Key levels low mismatch"
    assert key_levels["critical_highs_count"] == 3, "Wrong highs count"
    assert key_levels["critical_lows_count"] == 3, "Wrong lows count"
    
    print("\n🎉 All tests passed! Rolling buffer is working correctly.")
    print("✅ Buffer maintains max 3 items")
    print("✅ Interface methods work correctly")
    print("✅ No infinite expansion possible - old items are automatically removed")

if __name__ == "__main__":
    test_rolling_buffer()

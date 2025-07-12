"""
Test if BarType creation with aggregation works
"""
from nautilus_trader.model.data import BarType

def test_bartype_creation():
    """Test BarType creation with aggregation syntax"""
    
    print("="*80)
    print("TESTING BARTYPE CREATION")
    print("="*80)
    
    try:
        # Test 1: Normal bar type
        hourly_bar_type_str = "ESH4.GLBX-1-HOUR-LAST-EXTERNAL"
        hourly_bar_type = BarType.from_str(hourly_bar_type_str)
        print(f"✅ Hourly BarType created: {hourly_bar_type}")
        
        # Test 2: Aggregated bar type
        daily_bar_type_str = "ESH4.GLBX-1-DAY-LAST-INTERNAL@1-HOUR-EXTERNAL"
        daily_bar_type = BarType.from_str(daily_bar_type_str)
        print(f"✅ Daily BarType created: {daily_bar_type}")
        
        # Check properties
        print(f"\nDaily BarType properties:")
        print(f"  - instrument_id: {daily_bar_type.instrument_id}")
        print(f"  - spec.step: {daily_bar_type.spec.step}")
        print(f"  - spec.aggregation: {daily_bar_type.spec.aggregation}")
        print(f"  - spec.price_type: {daily_bar_type.spec.price_type}")
        
        if hasattr(daily_bar_type, 'aggregation_source'):
            print(f"  - aggregation_source: {daily_bar_type.aggregation_source}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating BarType: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_bartype_creation()
    
    if success:
        print(f"\n🎉 BarType creation works!")
    else:
        print(f"\n❌ BarType creation fails")
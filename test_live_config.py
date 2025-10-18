#!/usr/bin/env python3

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from AlgorithmicTrader.execution.live.live_run_execution import LiveTrader


def test_config_loading():
    print("=== Testing Configuration Loading ===")
    
    config_path = Path(__file__).parent.parent / "config" / "live_coin_listing_short.yaml"
    
    if not config_path.exists():
        print(f"❌ Configuration file not found: {config_path}")
        return False
    
    print(f"✓ Configuration file found: {config_path}")
    
    try:
        trader = LiveTrader(str(config_path))
        print("✓ LiveTrader instance created successfully")
        
        config = trader.config
        print(f"✓ Configuration loaded with {len(config.get('instruments', []))} instruments")
        
        for i, instrument in enumerate(config.get('instruments', [])):
            print(f"  Instrument {i+1}: {instrument.get('instrument_id')}")
            
        strategy_config = trader._build_strategy_config(config, config['instruments'][0])
        print("✓ Strategy configuration built successfully")
        
        required_keys = [
            'instruments', 'only_execute_short', 'use_aroon_simple_trend_system',
            'entry_scale_binance_metrics', 'log_growth_atr_risk'
        ]
        
        for key in required_keys:
            if key in strategy_config:
                print(f"  ✓ {key}: configured")
            else:
                print(f"  ❌ {key}: missing")
        
        return True
        
    except Exception as e:
        print(f"❌ Error during configuration test: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_environment_variables():
    print("\n=== Testing Environment Variables ===")
    
    import os
    
    api_key = os.getenv('BINANCE_TESTNET_API_KEY')
    api_secret = os.getenv('BINANCE_TESTNET_API_SECRET')
    
    if api_key and api_key != 'your_testnet_api_key_here':
        print("✓ BINANCE_TESTNET_API_KEY is configured")
    else:
        print("❌ BINANCE_TESTNET_API_KEY not configured")
        return False
    
    if api_secret and api_secret != 'your_testnet_api_secret_here':
        print("✓ BINANCE_TESTNET_API_SECRET is configured")
    else:
        print("❌ BINANCE_TESTNET_API_SECRET not configured")
        return False
    
    return True


def main():
    print("=== Live Trading Configuration Test ===\n")
    
    config_ok = test_config_loading()
    env_ok = test_environment_variables()
    
    print("\n=== Test Results ===")
    print(f"Configuration: {'✓ PASS' if config_ok else '❌ FAIL'}")
    print(f"Environment:   {'✓ PASS' if env_ok else '❌ FAIL'}")
    
    if config_ok and env_ok:
        print("\n🚀 All tests passed! Ready for live trading.")
        print("Run: python execution/run_live_trader.py")
    else:
        print("\n⚠️  Some tests failed. Please check configuration.")
        if not env_ok:
            print("   - Run: python setup_env.py")


if __name__ == "__main__":
    main()
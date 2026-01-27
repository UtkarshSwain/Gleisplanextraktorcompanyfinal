#!/usr/bin/env python3
"""
Quick script to check Hauptersatz symbol configuration in database
"""

import sys
import json

try:
    from database3 import is_db_available, get_all_custom_symbols, get_custom_symbol

    print("Checking database availability...")
    if not is_db_available():
        print("❌ Database is not available!")
        sys.exit(1)

    print("✅ Database is available\n")

    # Get all custom symbols
    print("Loading all custom symbols from database...")
    db_symbols = get_all_custom_symbols()

    if not db_symbols:
        print("⚠️ No custom symbols found in database!")
        sys.exit(0)

    print(f"Found {len(db_symbols)} custom symbols:\n")

    for sym_data in db_symbols:
        name = sym_data['symbol_name']
        cfg = sym_data['config']

        print(f"Symbol: {name}")
        print(f"  has_text: {cfg.get('has_text', False)}")
        print(f"  text_position: {cfg.get('text_position', 'N/A')}")
        print(f"  text_region_offset: {cfg.get('text_region_offset', 'N/A')}")
        print()

        # If this is Hauptersatz, show full config
        if name == "Hauptersatz":
            print("🔍 FULL Hauptersatz CONFIG:")
            print(json.dumps(cfg, indent=2))
            print()

    # Try to get Hauptersatz specifically
    print("\n" + "="*50)
    print("Checking for Hauptersatz specifically...")
    hauptersatz = get_custom_symbol("Hauptersatz")

    if hauptersatz:
        print("✅ Hauptersatz found in database!")
        print(f"\nFull symbol data:")
        print(f"  symbol_name: {hauptersatz['symbol_name']}")
        print(f"  config: {json.dumps(hauptersatz['config'], indent=4)}")
        print(f"  has templates_data: {hauptersatz['templates_data'] is not None}")
    else:
        print("❌ Hauptersatz NOT found in database!")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

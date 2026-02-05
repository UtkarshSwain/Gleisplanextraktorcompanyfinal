"""
Quick validation script to test DPI utilities without launching full app.
Run this to verify all DPI functions work correctly.
"""

import sys
import os

# Test 1: Import check
print("=" * 60)
print("DPI Setup Validation")
print("=" * 60)

try:
    from PyQt5 import QtCore, QtGui, QtWidgets
    print("✓ PyQt5 imported successfully")
except ImportError as e:
    print(f"✗ PyQt5 import failed: {e}")
    print("  Make sure you're running from the correct virtual environment")
    sys.exit(1)

# Test 2: Check Qt attributes exist
print("\nChecking Qt High DPI attributes:")
attrs_to_check = [
    ('AA_EnableHighDpiScaling', QtCore.Qt),
    ('AA_UseHighDpiPixmaps', QtCore.Qt),
]

for attr_name, module in attrs_to_check:
    if hasattr(module, attr_name):
        print(f"✓ {attr_name} is available")
    else:
        print(f"✗ {attr_name} is NOT available (PyQt5 version may be old)")

# Test 3: Check rounding policy (Qt 5.14+)
if hasattr(QtWidgets.QApplication, 'setHighDpiScaleFactorRoundingPolicy'):
    print("✓ setHighDpiScaleFactorRoundingPolicy is available (Qt 5.14+)")
    if hasattr(QtCore.Qt, 'HighDpiScaleFactorRoundingPolicy'):
        print("✓ HighDpiScaleFactorRoundingPolicy enum is available")
    else:
        print("✗ HighDpiScaleFactorRoundingPolicy enum NOT found")
else:
    print("⚠ setHighDpiScaleFactorRoundingPolicy NOT available (Qt < 5.14)")
    print("  This is OK - basic DPI scaling will still work")

# Test 4: Import dpi_utils module
print("\nChecking dpi_utils module:")
try:
    from utils import dpi_utils
    print("✓ utils.dpi_utils imported successfully")
except ImportError as e:
    print(f"✗ utils.dpi_utils import failed: {e}")
    sys.exit(1)

# Test 5: Create QApplication and test DPI functions
print("\nTesting DPI utility functions:")
try:
    # Need QApplication instance for screen queries
    app = QtWidgets.QApplication(sys.argv)

    # Test get_dpi_scale_factor
    scale_factor = dpi_utils.get_dpi_scale_factor()
    print(f"✓ DPI scale factor: {scale_factor:.2f}")

    # Test scale_value
    scaled = dpi_utils.scale_value(100)
    print(f"✓ scale_value(100) = {scaled}px")

    # Test get_screen_geometry
    geometry = dpi_utils.get_screen_geometry()
    print(f"✓ Screen geometry: {geometry.width()}x{geometry.height()}px")

    # Test get_adaptive_window_size
    w, h = dpi_utils.get_adaptive_window_size(1000, 800)
    print(f"✓ Adaptive window size (1000x800 base): {w}x{h}px")

    # Test get_scaled_font
    font = dpi_utils.get_scaled_font(12)
    print(f"✓ Scaled font (12pt base): {font.pointSize()}pt")

    print("\n" + "=" * 60)
    print("✓ All DPI utilities working correctly!")
    print("=" * 60)
    print("\nDPI Information:")
    dpi_utils.print_dpi_info()

except Exception as e:
    print(f"✗ Error testing DPI functions: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ Validation complete - DPI setup is working correctly!")

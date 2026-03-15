"""
Quick test script for Phase 1: Configuration Architecture
Tests that profiles load correctly and all values are accessible.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_profile_loading():
    """Test that all 3 profiles load correctly"""
    print("=" * 70)
    print("PHASE 1 TEST: Profile Loading")
    print("=" * 70)

    from core.profile_manager import ProfileManager

    profiles = [
        "profiles/wien_track_plans.yaml",
        # Future layout types will be added here
    ]

    all_passed = True

    for profile_path in profiles:
        try:
            config = ProfileManager.load_profile(profile_path)
            print(f"\n[OK] Loaded: {config.profile_name}")
            print(f"     Version: {config.profile_version}")
            print(f"     Classes: {len(config.classes)}")
            print(f"     DPI: {config.detection.dpi}")
            print(f"     Tile size: {config.detection.tile_size}")

            # Test helper methods
            signal_class = config.get_class_by_name("signal")
            if signal_class:
                print(f"     Signal confidence: {signal_class.confidence_threshold}")
            else:
                print("     [WARN] Signal class not found!")
                all_passed = False

        except Exception as e:
            print(f"\n[FAIL] {profile_path}")
            print(f"       Error: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False

    return all_passed


def test_config_values():
    """Test that config values match expected defaults"""
    print("\n" + "=" * 70)
    print("PHASE 1 TEST: Configuration Value Verification")
    print("=" * 70)

    from core.profile_manager import ProfileManager

    try:
        config = ProfileManager.load_profile("profiles/wien_track_plans.yaml")

        # Test detection params
        assert config.detection.tile_size == 2048, f"tile_size: {config.detection.tile_size}"
        assert config.detection.dpi == 500, f"dpi: {config.detection.dpi}"
        assert config.detection.overlap_pct == 40, f"overlap_pct: {config.detection.overlap_pct}"
        print("[OK] Detection params verified")

        # Test OCR params
        assert config.ocr.sig_pad == 14, f"sig_pad: {config.ocr.sig_pad}"
        assert config.ocr.angle_tol == 12.0, f"angle_tol: {config.ocr.angle_tol}"
        print("[OK] OCR params verified")

        # Test spatial params
        assert config.spatial.signal_dy_multiplier == 2.2, f"signal_dy: {config.spatial.signal_dy_multiplier}"
        assert config.spatial.signal_dx_multiplier == 2.4, f"signal_dx: {config.spatial.signal_dx_multiplier}"
        assert config.spatial.dx_minimum_threshold == 30, f"dx_min: {config.spatial.dx_minimum_threshold}"
        print("[OK] Spatial params verified")

        # Test class count
        assert len(config.classes) == 13, f"class count: {len(config.classes)}"
        print("[OK] 13 classes defined")

        # Test class lookup
        signal = config.get_class_by_name("signal")
        assert signal is not None, "signal class not found"
        assert signal.confidence_threshold == 0.40, f"signal conf: {signal.confidence_threshold}"
        print("[OK] Class lookup working")

        # Test linking rules
        linking_rule = config.get_linking_rule("signal")
        assert linking_rule.mode == "below", f"signal linking mode: {linking_rule.mode}"
        print("[OK] Linking rules verified")

        # Test regex compilation
        assert config.validation.coordinate_re is not None, "coordinate_re not compiled"
        print("[OK] Regex patterns compiled")

        return True

    except AssertionError as e:
        print(f"[FAIL] Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("PHASE 1 VALIDATION TEST SUITE")
    print("=" * 70)

    all_passed = True

    # Test 1: Profile loading
    if not test_profile_loading():
        all_passed = False

    # Test 2: Config values
    if not test_config_values():
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("[SUCCESS] ALL PHASE 1 TESTS PASSED")
    else:
        print("[FAILURE] SOME TESTS FAILED")
    print("=" * 70 + "\n")

    sys.exit(0 if all_passed else 1)

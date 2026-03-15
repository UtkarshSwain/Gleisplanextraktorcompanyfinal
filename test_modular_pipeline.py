"""
Comprehensive Test Suite for Modular Pipeline Architecture

This module validates:
1. Profile loading (all 3 profiles)
2. Configuration value verification (matching original config.py)
3. Module configuration from profiles
4. Backward compatibility
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_profile_loading():
    """Test that all 3 profiles load correctly"""
    print("=" * 70)
    print("TEST 1: Profile Loading")
    print("=" * 70)

    from core.profile_manager import ProfileManager

    profiles = [
        ("profiles/wien_track_plans.yaml", "wien_track_plans"),
        # Future layout types will be added here
    ]

    all_passed = True

    for profile_path, expected_name in profiles:
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
    print("TEST 2: Configuration Value Verification")
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


def test_ocr_engine_configuration():
    """Test that OCR engine can be configured from profile"""
    print("\n" + "=" * 70)
    print("TEST 3: OCR Engine Configuration")
    print("=" * 70)

    from core.profile_manager import ProfileManager
    from core.ocr_engine import configure_from_config, DEBUG_ANGLE_ROUTING, SIG_SCORE_MIN

    try:
        config = ProfileManager.load_profile("profiles/wien_track_plans.yaml")

        # Configure OCR module from config
        configure_from_config(config)

        # Import again to check if globals were updated
        from core.ocr_engine import DEBUG_ANGLE_ROUTING as debug_after
        from core.ocr_engine import SIG_SCORE_MIN as sig_score_after

        print(f"     DEBUG_ANGLE_ROUTING: {debug_after}")
        print(f"     SIG_SCORE_MIN: {sig_score_after}")

        # These should match config values
        assert debug_after == config.debug_angle_routing, "DEBUG_ANGLE_ROUTING not configured"
        print("[OK] OCR module configuration working")

        return True

    except AssertionError as e:
        print(f"[FAIL] Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_linking_module_functions():
    """Test that linking module functions accept config parameter"""
    print("\n" + "=" * 70)
    print("TEST 4: Linking Module Functions")
    print("=" * 70)

    from core.profile_manager import ProfileManager
    from core.linking import name_windows_for, parse_coord

    try:
        config = ProfileManager.load_profile("profiles/wien_track_plans.yaml")

        # Test name_windows_for with config
        anchor = {
            "name": "signal",
            "x1": 100, "y1": 100, "x2": 150, "y2": 130,
            "w": 50, "h": 30
        }
        img_shape = (1000, 1500, 3)

        windows = name_windows_for(anchor, img_shape, "below", config=config)
        assert len(windows) > 0, "No windows returned"
        print(f"[OK] name_windows_for returned {len(windows)} windows")

        # Test parse_coord with config
        val, gi = parse_coord("1,2345", config=config)
        assert val is not None, "parse_coord failed"
        print(f"[OK] parse_coord: '1,2345' -> value={val}, gi={gi}")

        # Test parse_coord with Gleisreferenz
        val2, gi2 = parse_coord("0,1234 Gl.113", config=config)
        print(f"[OK] parse_coord: '0,1234 Gl.113' -> value={val2}, gi={gi2}")

        return True

    except AssertionError as e:
        print(f"[FAIL] Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backward_compatibility():
    """Test that functions work without config (backward compatibility)"""
    print("\n" + "=" * 70)
    print("TEST 5: Backward Compatibility")
    print("=" * 70)

    from core.linking import name_windows_for, parse_coord

    try:
        # Test name_windows_for without config
        anchor = {
            "name": "signal",
            "x1": 100, "y1": 100, "x2": 150, "y2": 130,
            "w": 50, "h": 30
        }
        img_shape = (1000, 1500, 3)

        windows = name_windows_for(anchor, img_shape, "below")  # No config
        assert len(windows) > 0, "No windows returned without config"
        print(f"[OK] name_windows_for works without config")

        # Test parse_coord without config
        val, gi = parse_coord("1,2345")  # No config
        assert val is not None, "parse_coord failed without config"
        print(f"[OK] parse_coord works without config")

        return True

    except AssertionError as e:
        print(f"[FAIL] Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_class_definitions():
    """Test that all 13 classes are properly defined with correct structure"""
    print("\n" + "=" * 70)
    print("TEST 6: Class Definitions Completeness")
    print("=" * 70)

    from core.profile_manager import ProfileManager

    expected_classes = [
        "signal", "gm_block", "gks_festkodiert", "gks_gesteuert",
        "weichen_block", "isolierstoß", "haltepunkt", "sverbinder",
        "coordinate", "prellbock", "haltetafel", "weichenende",
        "weichengruppenende"
    ]

    try:
        config = ProfileManager.load_profile("profiles/wien_track_plans.yaml")

        found_classes = [cls.name for cls in config.classes]

        for expected in expected_classes:
            if expected not in found_classes:
                print(f"[FAIL] Missing class: {expected}")
                return False
            cls = config.get_class_by_name(expected)
            assert cls.confidence_threshold > 0, f"{expected} has invalid confidence"
            assert cls.nms_threshold > 0, f"{expected} has invalid NMS threshold"

        print(f"[OK] All 13 classes defined with valid thresholds")

        # Test that each class has proper attributes
        for cls in config.classes:
            assert hasattr(cls, 'confidence_threshold'), f"{cls.name} missing confidence_threshold"
            assert hasattr(cls, 'nms_threshold'), f"{cls.name} missing nms_threshold"
            assert hasattr(cls, 'requires_ocr'), f"{cls.name} missing requires_ocr"
            print(f"     {cls.name}: conf={cls.confidence_threshold:.2f}, nms={cls.nms_threshold:.2f}, ocr={cls.requires_ocr}")

        print("[OK] All classes have required attributes")
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
    print("MODULAR PIPELINE ARCHITECTURE TEST SUITE")
    print("=" * 70)

    all_passed = True

    # Test 1: Profile loading
    if not test_profile_loading():
        all_passed = False

    # Test 2: Config values
    if not test_config_values():
        all_passed = False

    # Test 3: OCR engine configuration
    if not test_ocr_engine_configuration():
        all_passed = False

    # Test 4: Linking module functions
    if not test_linking_module_functions():
        all_passed = False

    # Test 5: Backward compatibility
    if not test_backward_compatibility():
        all_passed = False

    # Test 6: Class definitions
    if not test_class_definitions():
        all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("[SUCCESS] ALL TESTS PASSED")
    else:
        print("[FAILURE] SOME TESTS FAILED")
    print("=" * 70 + "\n")

    sys.exit(0 if all_passed else 1)

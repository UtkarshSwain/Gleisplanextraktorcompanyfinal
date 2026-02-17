"""
Linking - Symbol-Koordinaten-Verknuepfung und Fahrtrichtungserkennung

Dieses Modul implementiert die Verknuepfungslogik zwischen erkannten
Symbolen und ihren zugehoerigen Koordinaten sowie die Fahrtrichtungserkennung.

Kernfunktionen:
    link_anchor_to_coord(): Verknuepft Symbol mit naechster Koordinate
    detect_fahrtrichtung(): Bestimmt Fahrtrichtung basierend auf GKS-Position
    find_nearest_track_perpendicular(): Findet Gleis per Raycast
    merge_duplicate_signals(): Fusioniert doppelte Signalerkennungen
    link_haltetafel_to_gks(): Verknuepft Haltetafeln mit GKS

Fahrtrichtungs-Algorithmen:
    1. GKS-basiert: Position des GKS relativ zum Signal
    2. Gleis-senkrecht: Raycast zum Gleisskelett (falls GKS fehlt)
    3. Numerischer Fallback: Basierend auf Koordinatenwerten

Richtungserkennung:
    - Beruecksichtigt Symbolwinkel fuer "oben/unten/links/rechts"
    - Rotiert Koordinatensystem fuer geneigte Symbole
    - Separate Logik fuer kardinal vs. angular ausgerichtete Symbole

Abhaengigkeiten:
    numpy, pandas, math
"""
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
import math
import re
import pandas as pd
import numpy as np
from utils.helpers import _is_cardinal, _norm_angle, _is_angular, ANGLE_TOL, _is_near, _debug_angle

# Type hint for LayoutConfig without circular import
if TYPE_CHECKING:
    from core.config_models import LayoutConfig

# Module-level debug flags (defaults, can be overridden by config)
DEBUG_LINKING = False
DEBUG_TRACK = False

# Module-level aliases (can be shadowed by function-local variables when config is passed)
debug_linking = DEBUG_LINKING
debug_track = DEBUG_TRACK
debug_angle = False  # Used by helper functions when not passed explicitly

# Compiled regex for coordinate parsing (default, overridden by config)
COORD_RE = None
try:
    COORD_RE = re.compile(r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$')
except Exception:
    pass

# NAME_RULES_EXTRA is now config-driven via LayoutConfig.get_name_search_rule()
# Default fallback for backward compatibility when no config provided
NAME_RULES_EXTRA_DEFAULTS = {
    "gm_block": dict(inside=True, right=True, below=True),
    "weichen_block": dict(inside=True, right=True, below=True),
    "prellbock": dict(inside=True, right=True, below=True),
    "gks_gesteuert": dict(inside=True, left=True, right=True, below=True),
    "gks_festkodiert": dict(inside=True, left=True, right=True, below=True),
    "signal": dict(left=True, right=True, below=True, above=True),
}


def get_name_search_hints(class_name: str, config: 'LayoutConfig' = None) -> dict:
    """
    Get name search direction hints from config or defaults.

    Args:
        class_name: Symbol class name
        config: LayoutConfig with name_search_rule per class (optional)

    Returns:
        dict with keys: inside, left, right, below, above (all bool)
    """
    if config is not None:
        rule = config.get_name_search_rule(class_name)
        return {
            'inside': rule.inside,
            'left': rule.left,
            'right': rule.right,
            'below': rule.below,
            'above': rule.above
        }
    # Fallback to hardcoded defaults for backward compatibility
    return NAME_RULES_EXTRA_DEFAULTS.get(class_name, {})

def find_nearest_track_perpendicular(signal_point, track_skeleton, signal_angle_raw,
                                     track_bounds=None, max_distance=None,
                                     is_angular=False, config: 'LayoutConfig' = None):
    """
    Cast rays perpendicular to signal orientation until hitting track.

    DYNAMIC RAY-CASTING:
    - For HORIZONTAL/VERTICAL signals: Cast vertical rays (up/down)
    - For ANGULAR signals: Cast rays perpendicular to signal angle
    - Stops when track is found (dynamic distance)
    - Uses track bounds to limit search range

    Args:
        signal_point: (x, y) center of signal
        track_skeleton: Binary track skeleton image
        signal_angle_raw: Raw angle of signal in degrees [0°, 90°]
        track_bounds: dict with 'y_min', 'y_max', 'height' (optional)
        max_distance: Maximum distance to search (safety limit)
        is_angular: True if signal is angular (not horizontal/vertical)
        config: LayoutConfig with debug flags (optional)

    Returns:
        dict: {
            'track_above': bool,
            'track_below': bool,
            'distance_above': int (or None),
            'distance_below': int (or None),
            'hit_above_first': bool (or None),
            'max_distance_above': int,
            'max_distance_below': int
        }
    """
    # Get debug flag from config or use module default
    debug_track = config.debug_track if config is not None else DEBUG_TRACK

    # Get spatial config values
    sp = config.spatial if config else None
    if max_distance is None:
        max_distance = sp.track_perpendicular_max_distance if sp else 1500
    track_window_size = sp.track_window_size if sp else 25

    x, y = signal_point
    h, w = track_skeleton.shape
    
    # ============================================================================
    # Calculate perpendicular direction
    # ============================================================================
    
    if is_angular:
        # For angular signals: perpendicular to text orientation
        perpendicular_angle = signal_angle_raw + 90.0
        perpendicular_rad = math.radians(perpendicular_angle)
        
        # Direction vectors for "above" and "below" (perpendicular to text)
        dx_above = math.cos(perpendicular_rad)
        dy_above = math.sin(perpendicular_rad)
        dx_below = -dx_above
        dy_below = -dy_above
        
        if debug_track:
            print(f" Angular signal: perpendicular angle = {perpendicular_angle:.1f}°")
    else:
        # For horizontal/vertical signals: simple vertical direction
        dx_above = 0
        dy_above = -1  # Up
        dx_below = 0
        dy_below = 1   # Down

        if debug_track:
            print(f"Horizontal/Vertical signal: vertical rays (up/down)")
    
    # ============================================================================
    # Calculate smart search distances
    # ============================================================================
    
    if track_bounds and not is_angular:
        # For vertical rays, use Y-bounds
        max_distance_above = y - track_bounds.get('y_min', 0)
        max_distance_below = track_bounds.get('y_max', h) - y
    else:
        # For angular rays or no bounds, use full image
        max_distance_above = max(h, w)  # Diagonal distance
        max_distance_below = max(h, w)
    
    # Safety limits
    max_distance_above = min(max_distance_above, max_distance)
    max_distance_below = min(max_distance_below, max_distance)
    
    distance_above = None
    distance_below = None
    
    # ============================================================================
    # Cast rays dynamically (stop when track found)
    # ============================================================================
    
    max_dist = max(max_distance_above, max_distance_below)
    
    for dist in range(1, max_dist + 1):
        #  Check "above" direction (perpendicular to signal)
        if distance_above is None and dist <= max_distance_above:
            check_x = int(x + dist * dx_above)
            check_y = int(y + dist * dy_above)
            
            if 0 <= check_y < h and 0 <= check_x < w:
                # Check window for track thickness (±window_size px)
                x_min = max(0, check_x - track_window_size)
                x_max = min(w, check_x + track_window_size)
                y_min = max(0, check_y - track_window_size)
                y_max = min(h, check_y + track_window_size)

                # Check if track exists in window
                if np.any(track_skeleton[y_min:y_max, x_min:x_max] > 0):
                    distance_above = dist  #  STOP - track found!

        #  Check "below" direction (perpendicular to signal)
        if distance_below is None and dist <= max_distance_below:
            check_x = int(x + dist * dx_below)
            check_y = int(y + dist * dy_below)

            if 0 <= check_y < h and 0 <= check_x < w:
                # Check window for track thickness (±window_size px)
                x_min = max(0, check_x - track_window_size)
                x_max = min(w, check_x + track_window_size)
                y_min = max(0, check_y - track_window_size)
                y_max = min(h, check_y + track_window_size)
                
                # Check if track exists in window
                if np.any(track_skeleton[y_min:y_max, x_min:x_max] > 0):
                    distance_below = dist  #  STOP - track found!
        
        #  If BOTH found, stop searching entirely
        if distance_above is not None and distance_below is not None:
            break
    
    # ============================================================================
    # Determine results
    # ============================================================================
    
    track_above = distance_above is not None
    track_below = distance_below is not None
    
    # Which hit first?
    hit_above_first = None
    if track_above and track_below:
        hit_above_first = distance_above < distance_below
    elif track_above:
        hit_above_first = True
    elif track_below:
        hit_above_first = False
    
    return {
        'track_above': track_above,
        'track_below': track_below,
        'distance_above': distance_above,
        'distance_below': distance_below,
        'hit_above_first': hit_above_first,
        'max_distance_above': max_distance_above,
        'max_distance_below': max_distance_below
    }

def get_track_bounds(track_skeleton):
    """
    Calculate bounding box of all track pixels.
    
    Args:
        track_skeleton: Binary track skeleton image
    
    Returns:
        dict: {'x_min', 'x_max', 'y_min', 'y_max', 'width', 'height'}
    """
    # Find all track pixels
    track_pixels = np.argwhere(track_skeleton > 0)
    
    if len(track_pixels) == 0:
        # No tracks found - use full image
        h, w = track_skeleton.shape
        return {
            'y_min': 0,
            'y_max': h,
            'x_min': 0,
            'x_max': w,
            'height': h,
            'width': w
        }
    
    # Get bounds
    y_coords = track_pixels[:, 0]
    x_coords = track_pixels[:, 1]
    
    return {
        'y_min': int(y_coords.min()),
        'y_max': int(y_coords.max()),
        'x_min': int(x_coords.min()),
        'x_max': int(x_coords.max()),
        'height': int(y_coords.max() - y_coords.min()),
        'width': int(x_coords.max() - x_coords.min())
    }

def name_windows_for(anchor: dict, img_shape: Tuple[int, int, int], mode: str, config: 'LayoutConfig' = None):
    """
    Calculate search windows for name text OCR.

    Args:
        anchor: Symbol detection dict
        img_shape: Image shape (h, w, c)
        mode: Search mode string
        config: LayoutConfig with spatial parameters (optional for backward compat)
    """
    H, W = img_shape[:2]
    x1, y1, x2, y2 = anchor["x1"], anchor["y1"], anchor["x2"], anchor["y2"]
    aw, ah = anchor["w"], anchor["h"]

    # Use config values if provided, otherwise use defaults
    if config is not None:
        sp = config.spatial
        signal_dy_mult = sp.signal_dy_multiplier
        signal_dx_mult = sp.signal_dx_multiplier
        default_dy_mult = sp.default_dy_multiplier
        default_dx_mult = sp.default_dx_multiplier
        inside_pad = sp.inside_padding_ratio
        right_w_ratio = sp.right_window_width_ratio
        right_h_ratio = sp.right_window_height_ratio
        left_w_ratio = sp.left_window_width_ratio
        left_h_ratio = sp.left_window_height_ratio
        sverbinder_w_ratio = sp.sverbinder_window_width_ratio
        sverbinder_h_ratio = sp.sverbinder_window_height_ratio
        signal_extended = sp.signal_extended_dx_ratio
    else:
        # Default values for backward compatibility
        signal_dy_mult, signal_dx_mult = 2.2, 2.4
        default_dy_mult, default_dx_mult = 1.6, 1.0
        inside_pad = 0.10
        right_w_ratio, right_h_ratio = 2.5, 0.6
        left_w_ratio, left_h_ratio = 4.0, 0.6
        sverbinder_w_ratio, sverbinder_h_ratio = 0.9, 0.3
        signal_extended = 5.0

    # Use signal multipliers for classes that require coordinate linking (config-driven)
    # This replaces the hardcoded "signal" check
    use_signal_multipliers = False
    if config is not None:
        cls_def = config.get_class_by_name(anchor["name"])
        if cls_def and cls_def.requires_coordinate:
            use_signal_multipliers = True
    else:
        # Fallback: use signal multipliers for "signal" class only (backward compat)
        use_signal_multipliers = (anchor["name"] == "signal")

    if use_signal_multipliers:
        dy = int(signal_dy_mult * ah)
        dx = int(signal_dx_mult * aw)
    else:
        dy = int(default_dy_mult * ah)
        dx = int(default_dx_mult * aw)

    win = []
    hints = get_name_search_hints(anchor["name"], config)

    if hints.get("inside", False):
        ix1 = x1 + int(inside_pad * aw)
        iy1 = y1 + int(inside_pad * ah)
        ix2 = x2 - int(inside_pad * aw)
        iy2 = y2 - int(inside_pad * ah)
        if ix2 > ix1 and iy2 > iy1:
            win.append((ix1, iy1, ix2, iy2))

    if hints.get("right", False):
        rx1, ry1 = x2, max(0, y1 - int(right_h_ratio * ah))
        rx2, ry2 = min(W, x2 + int(right_w_ratio * aw)), min(H, y2 + int(right_h_ratio * ah))
        if rx2 > rx1 and ry2 > ry1:
            win.append((rx1, ry1, rx2, ry2))

    if hints.get("left", False):
        lx1, ly1 = max(0, x1 - int(left_w_ratio * aw)), max(0, y1 - int(left_h_ratio * ah))
        lx2, ly2 = x1, min(H, y2 + int(left_h_ratio * ah))
        if lx2 > lx1 and ly2 > ly1:
            win.append((lx1, ly1, lx2, ly2))

    if hints.get("below", False):
        bx1, by1 = max(0, x1 - dx), y2
        bx2, by2 = min(W, x2 + dx), min(H, y2 + dy)
        if by2 > by1:
            win.append((bx1, by1, bx2, by2))

    if hints.get("above", False):
        ax1, ay1 = max(0, x1 - dx), max(0, y1 - dy)
        ax2, ay2 = min(W, x2 + dx), y1
        if ay2 > ay1:
            win.append((ax1, ay1, ax2, ay2))

    if mode in ("below", "either", "right_or_below"):
        sx1, sy1 = max(0, x1 - dx), y2
        sx2, sy2 = min(W, x2 + dx), min(H, y2 + dy)
        if sy2 > sy1:
            win.append((sx1, sy1, sx2, sy2))
    if mode in ("above", "either"):
        sx1, sy1 = max(0, x1 - dx), max(0, y1 - dy)
        sx2, sy2 = min(W, x2 + dx), y1
        if sy2 > sy1:
            win.append((sx1, sy1, sx2, sy2))
    if mode in ("right", "right_or_below", "either"):
        sx1, sy1 = x2, max(0, y1 - int(sverbinder_h_ratio * ah))
        sx2, sy2 = min(W, x2 + int(sverbinder_w_ratio * aw)), min(H, y2 + int(sverbinder_h_ratio * ah))
        if sx2 > sx1 and sy2 > sy1:
            win.append((sx1, sy1, sx2, sy2))

    # Extended search windows for classes requiring coordinate (replaces hardcoded "signal" check)
    if use_signal_multipliers:
        rx1 = x2
        ry1 = max(0, y1 - int(ah))
        rx2 = min(W, x2 + int(signal_extended * aw))
        ry2 = min(H, y2 + int(ah))
        if rx2 > rx1 and ry2 > ry1:
            win.append((rx1, ry1, rx2, ry2))
        bx1 = max(0, x1 - int(2 * aw))
        by1 = y2
        bx2 = min(W, x2 + int(2 * aw))
        by2 = min(H, y2 + int(signal_extended * ah))
        if by2 > by1:
            win.append((bx1, by1, bx2, by2))
        lx1 = max(0, x1 - int(signal_extended * aw))
        ly1 = max(0, y1 - int(ah))
        lx2 = x1
        ly2 = min(H, y2 + int(ah))
        if lx2 > lx1 and ly2 > ly1:
            win.append((lx1, ly1, lx2, ly2))

    out, seen = [], set()
    for (a, b, c, d) in win:
        key = (a // 4, b // 4, c // 4, d // 4)
        if key not in seen:
            seen.add(key)
            out.append((a, b, c, d))
    return out

def _get_oriented_distance(anchor, coord, angle_raw):
    """
    Calculate distance in anchor's oriented coordinate system.
    Uses RAW angle [0°, 90°] for actual rotation geometry.
    
    Returns (dx_local, dy_local) where:
    - dx_local = distance along anchor's width direction
    - dy_local = distance along anchor's height direction (positive = "below")
    """
    # Vector from anchor center to coord center (in global coordinates)
    dx_global = coord["cx"] - anchor["cx"]
    dy_global = coord["cy"] - anchor["cy"]
    
    #  Convert RAW angle to radians for rotation matrix
    angle_rad = math.radians(angle_raw)
    
    #  Rotate global vector to anchor's local coordinate system
    # Note: We use negative angle to rotate TO local coords (inverse rotation)
    dx_local = dx_global * math.cos(-angle_rad) - dy_global * math.sin(-angle_rad)
    dy_local = dx_global * math.sin(-angle_rad) + dy_global * math.cos(-angle_rad)
    
    # Return absolute distances
    return abs(dx_local), abs(dy_local)


def _check_direction(anchor, coord, mode, is_angular, angle_raw, tilted_ok, debug=False):
    """
    Check if coordinate is in the correct direction relative to anchor.
    Handles both cardinal (axis-aligned) and angular (oriented) boxes.
    """
    if mode == "either":
        return True

    if mode == "inside":
        # Check if coordinate is inside anchor bounding box
        return (anchor["x1"] <= coord["cx"] <= anchor["x2"] and
                anchor["y1"] <= coord["cy"] <= anchor["y2"])

    # For directional modes (below, above, right_or_below)
    if is_angular and not tilted_ok:
        #  Use oriented direction for angular boxes (with RAW angle)
        return _check_oriented_direction(anchor, coord, mode, angle_raw, debug=debug)
    else:
        #  Use axis-aligned direction for cardinal boxes
        return _check_axis_aligned_direction(anchor, coord, mode, debug=debug)


def _check_oriented_direction(anchor, coord, mode, angle_raw, debug=False):
    """
    Check direction in anchor's oriented coordinate system.
    Uses RAW angle [0°, 90°] for rotation matrix.

    In the rotated coordinate system:
    - dx_local > 0 means coordinate is to the "right" of anchor
    - dy_local > 0 means coordinate is "below" anchor
    """
    # Vector from anchor to coord (in global coordinates)
    dx_global = coord["cx"] - anchor["cx"]
    dy_global = coord["cy"] - anchor["cy"]

    #  Convert to anchor's local coordinate system using RAW angle
    angle_rad = math.radians(angle_raw)

    # Transform to local coordinates (inverse rotation)
    dx_local = dx_global * math.cos(-angle_rad) - dy_global * math.sin(-angle_rad)
    dy_local = dx_global * math.sin(-angle_rad) + dy_global * math.cos(-angle_rad)

    if debug:
        print(f"Oriented: dx_local={dx_local:.1f}, dy_local={dy_local:.1f}")

    if mode == "below":
        # Coordinate should be "below" in anchor's local coordinate system
        return dy_local > 0

    elif mode == "above":
        # Coordinate should be "above" in anchor's local coordinate system
        return dy_local < 0

    elif mode == "right_or_below":
        # Right (positive dx_local) OR below (positive dy_local)
        return dx_local >= 0 or dy_local > 0

    return True


def _check_axis_aligned_direction(anchor, coord, mode, debug=False):
    """
    Check direction using global axis-aligned coordinates (for cardinal boxes).
    """
    if mode == "below":
        # Coordinate center is below anchor center
        return coord["cy"] > anchor["cy"]

    elif mode == "above":
        # Coordinate center is above anchor center
        return coord["cy"] < anchor["cy"]

    elif mode == "right_or_below":
        #  FIXED: More lenient "right" check
        # Consider "right" if coordinate's LEFT edge is at or past anchor's RIGHT edge
        # OR if coordinate's right edge overlaps with anchor's right half
        # This handles side-by-side placements like "PB | 3,6223"

        is_to_right = coord["x1"] >= anchor["x2"] - 0.3 * anchor["w"]  # Allows slight overlap
        is_below = coord["cy"] > anchor["cy"] + 0.3 * anchor["h"]  # Must be clearly below

        if debug:
            print(f"right_or_below: is_to_right={is_to_right} "
                  f"(coord_x1={coord['x1']:.0f} vs anchor_x2-margin={anchor['x2'] - 0.3*anchor['w']:.0f}), "
                  f"is_below={is_below} (coord_cy={coord['cy']:.0f} vs anchor_cy+margin={anchor['cy']+0.3*anchor['h']:.0f})")

        return is_to_right or is_below

    return True


def link_anchor_to_coord(anchor, coords, config: 'LayoutConfig' = None, learned_patterns=None):
    """
    Link anchor to coordinate with ANGLE-AWARE spatial relationships
    and CLASS-SPECIFIC horizontal tolerance.

    Args:
        anchor: Symbol detection dict
        coords: List of coordinate detections
        config: LayoutConfig with linking rules and spatial params (optional)
        learned_patterns: Optional learned spatial patterns

    IMPROVED: Better angular linking with Euclidean distance priority
    """
    # Get spatial config values (with defaults for backward compatibility)
    if config is not None:
        sp = config.spatial
        dy_max_base_mult = sp.dy_max_base_multiplier
        dx_base_mult = sp.dx_base_multiplier
        dx_tight_mult = sp.dx_tight_multiplier
        dx_min_threshold = sp.dx_minimum_threshold
        left_bonus = sp.left_search_bonus
        debug_angle = config.debug_angle_routing
        # Get linking rule from config
        linking_rule = config.get_linking_rule(anchor["name"])
        mode = linking_rule.mode
        tight = False  # Not in LinkingRule, always False
        tilted_ok = linking_rule.tilted_ok
        dx_multiplier = linking_rule.dx_multiplier
        dy_multiplier = linking_rule.dy_multiplier
        prefer_horizontal = linking_rule.prefer_horizontal
        search_left = linking_rule.search_left
        fallback_steps = linking_rule.fallback_dy_steps
    else:
        # Default values for backward compatibility
        dy_max_base_mult = 1.6
        dx_base_mult = 0.6
        dx_tight_mult = 0.45
        dx_min_threshold = 30
        left_bonus = 1.3
        debug_angle = False  # Use module-level default
        # Use empty rule defaults (no config provided)
        rule = {}
        mode = rule.get("mode", "either")
        tight = rule.get("tight", False)
        tilted_ok = rule.get("tilted_ok", False)
        dx_multiplier = rule.get("dx_multiplier", 1.0)
        dy_multiplier = rule.get("dy_multiplier", 1.0)
        prefer_horizontal = rule.get("prefer_horizontal", False)
        search_left = rule.get("search_left", False)
        fallback_steps = rule.get("fallback_dy_steps", [])

    dy_max_base = dy_max_base_mult * anchor["h"]

    # Apply dy_multiplier
    dy_max = dy_max_base * dy_multiplier

    # Get angles
    anchor_angle_norm = float(anchor.get("angle", 0.0))
    anchor_angle_raw = float(anchor.get("angle_raw", anchor_angle_norm))

    is_cardinal_box = _is_cardinal(anchor_angle_norm)
    is_angular = not is_cardinal_box

    # ONLY print if debug_angle_routing is True
    anchor_text = anchor.get("text", anchor.get("anchor_text", ""))
    if debug_angle:
        print(f"\n LINKING {(anchor.get('name') or '').upper()} '{anchor_text}': raw={anchor_angle_raw:.1f}° norm={anchor_angle_norm:.1f}° "
              f"cardinal={is_cardinal_box} mode={mode} dx_mult={dx_multiplier} dy_mult={dy_multiplier}")
        print(f"Anchor position: cx={anchor['cx']:.1f}, cy={anchor['cy']:.1f}")
        print(f"Searching in {len(coords)} coordinates...")
    
    # Initialize with infinity for distance-based scoring
    best, best_score = None, (float('inf'), float('inf'), 0)
    
    for c in coords:
        # Calculate distance (angle-aware or axis-aligned)
        if is_angular:
            # Get oriented distances (absolute values)
            dx_abs, dy_abs = _get_oriented_distance(anchor, c, anchor_angle_raw)
            
            # Calculate Euclidean distance in rotated frame
            dist_euclidean = math.sqrt(dx_abs**2 + dy_abs**2)
            
            # Use these for filtering
            dx = dx_abs
            dy = dy_abs
            
            if debug_angle:
                coord_text = c.get('text', c.get('coord_text', '?'))
                print(f"Coord '{coord_text}': oriented dx={dx:.1f} dy={dy:.1f} euclidean={dist_euclidean:.1f}")
        else:
            # Axis-aligned
            dx = abs(c["cx"] - anchor["cx"])
            dy = abs(c["cy"] - anchor["cy"])
            dist_euclidean = math.sqrt(dx**2 + dy**2)
            
            if debug_angle:
                coord_text = c.get('text', c.get('coord_text', '?'))
                print(f"Coord '{coord_text}': axis-aligned dx={dx:.1f} dy={dy:.1f} euclidean={dist_euclidean:.1f}")
                print(f"Coord position: cx={c['cx']:.1f}, cy={c['cy']:.1f}")
        
        # Vertical distance check
        if dy > dy_max:
            if debug_angle:
                print(f"→ SKIP: dy={dy:.1f} > dy_max={dy_max:.1f}")
            continue
        
        # Directional check
        ok_dir = _check_direction(anchor, c, mode, is_angular, anchor_angle_raw, tilted_ok, debug=debug_angle)

        if not ok_dir:
            if debug_angle:
                print(f"→ SKIP: wrong direction (mode={mode})")
            continue
        
        # Horizontal tolerance
        dx_max = dx_multiplier * 0.6 * max(anchor["w"], c["w"])
        if tight:
            dx_max = dx_multiplier * 0.45 * max(anchor["w"], c["w"])
        
        # Minimum threshold to avoid being too strict
        dx_max = max(dx_max, 30)
        
        # Left-side bonus (only if search_left=True and not angular)
        if search_left and not is_angular:
            coord_is_left = c["cx"] < anchor["cx"]
            if coord_is_left:
                dx_max *= 1.3
                if debug_angle:
                    print(f"→ LEFT-SIDE BONUS: dx_max={dx_max:.1f}")
        
        if dx > dx_max:
            if debug_angle:
                print(f"→ SKIP: dx={dx:.1f} > dx_max={dx_max:.1f}")
            continue
        
        # Calculate overlap
        xo = max(0, min(anchor["x2"], c["x2"]) - max(anchor["x1"], c["x1"]))
        
        # NEW SCORING: Prioritize Euclidean distance, then overlap
        if is_angular:
            score = (dist_euclidean, -xo, 0)
        else:
            if prefer_horizontal:
                score = (dx, dy, -xo)
            else:
                score = (dy, dx, -xo)
        
        if debug_angle:
            print(f"→ CANDIDATE: score={score} xo={xo:.1f}")
        
        if score < best_score:
            best_score, best = score, c
            if debug_angle:
                print(f"→ NEW BEST!")
    
    #  FINAL DEBUG - only if debug_angle
    if debug_angle:
        if best:
            print(f"LINKED: {best.get('text', best.get('coord_text', '?'))}")
        else:
            print(f"NO MATCH")

    # Step-wise fallback for specific classes (weichengruppenende, weichenende)
    # Only searches in AVAILABLE coordinates (not occupied by other classes)
    if best is None:
        for step_multiplier in fallback_steps:
            expanded_dy_max = dy_max_base * step_multiplier

            if debug_angle:
                print(f"\n→ STEP-WISE FALLBACK: trying dy_multiplier={step_multiplier} (dy_max={expanded_dy_max:.1f})")

            step_best, step_best_score = None, (float('inf'), float('inf'), 0)

            for c in coords:
                # Calculate distance (same logic as main loop)
                if is_angular:
                    dx_abs, dy_abs = _get_oriented_distance(anchor, c, anchor_angle_raw)
                    dist_euclidean = math.sqrt(dx_abs**2 + dy_abs**2)
                    dx, dy = dx_abs, dy_abs
                else:
                    dx = abs(c["cx"] - anchor["cx"])
                    dy = abs(c["cy"] - anchor["cy"])
                    dist_euclidean = math.sqrt(dx**2 + dy**2)

                # Vertical distance check with expanded tolerance
                if dy > expanded_dy_max:
                    continue

                # Directional check
                ok_dir = _check_direction(anchor, c, mode, is_angular, anchor_angle_raw, tilted_ok, debug=debug_angle)
                if not ok_dir:
                    continue

                # Horizontal tolerance (same as main loop)
                dx_max_local = dx_multiplier * 0.6 * max(anchor["w"], c["w"])
                if tight:
                    dx_max_local = dx_multiplier * 0.45 * max(anchor["w"], c["w"])
                dx_max_local = max(dx_max_local, 30)

                if search_left and not is_angular:
                    coord_is_left = c["cx"] < anchor["cx"]
                    if coord_is_left:
                        dx_max_local *= 1.3

                if dx > dx_max_local:
                    continue

                # Calculate overlap and score
                xo = max(0, min(anchor["x2"], c["x2"]) - max(anchor["x1"], c["x1"]))

                if is_angular:
                    score = (dist_euclidean, -xo, 0)
                else:
                    if prefer_horizontal:
                        score = (dx, dy, -xo)
                    else:
                        score = (dy, dx, -xo)

                if score < step_best_score:
                    step_best_score, step_best = score, c

            if step_best is not None:
                best = step_best
                if debug_angle:
                    best_text = best.get('text', best.get('coord_text', '?'))
                    print(f"→ STEP-WISE MATCH at step {step_multiplier}: '{best_text}'")
                break  # Found match, stop expanding

    # Adaptive fallback
    if best is None and learned_patterns and anchor["name"] in learned_patterns:
        patterns = learned_patterns[anchor["name"]]
        
        if len(patterns) >= 2:
            #  ONLY print if debug_angle
            if debug_angle:
                print(f"\n ADAPTIVE SEARCH for {anchor['name']}: {len(patterns)} patterns learned")
            
            avg_dx = sum(p[0] for p in patterns) / len(patterns)
            avg_dy = sum(p[1] for p in patterns) / len(patterns)
            std_dx = (sum((p[0] - avg_dx)**2 for p in patterns) / len(patterns))**0.5 if len(patterns) > 1 else 100
            std_dy = (sum((p[1] - avg_dy)**2 for p in patterns) / len(patterns))**0.5 if len(patterns) > 1 else 50

            if debug_angle:
                print(f"Pattern: dx={avg_dx:.1f}±{std_dx:.1f}, dy={avg_dy:.1f}±{std_dy:.1f}")

            # Get adaptive search params from config
            adapt_dx_mult = sp.adaptive_search_dx_multiplier if config else 3.0
            adapt_dx_min = sp.adaptive_search_dx_minimum if config else 150
            adapt_dy_mult = sp.adaptive_search_dy_multiplier if config else 3.0
            adapt_dy_min = sp.adaptive_search_dy_minimum if config else 80
            search_dx = max(adapt_dx_mult * std_dx, adapt_dx_min)
            search_dy = max(adapt_dy_mult * std_dy, adapt_dy_min)
            
            adaptive_candidates = []
            for c in coords:
                dx_offset = c["cx"] - anchor["cx"]
                dy_offset = c["cy"] - anchor["cy"]
                
                if abs(dx_offset - avg_dx) < search_dx and abs(dy_offset - avg_dy) < search_dy:
                    pattern_distance = ((dx_offset - avg_dx)**2 + (dy_offset - avg_dy)**2)**0.5
                    adaptive_candidates.append((pattern_distance, c))
                    
                    if debug_angle:
                        coord_text = c.get('text', c.get('coord_text', '?'))
                        print(f"Adaptive candidate: '{coord_text}' offset=({dx_offset:.1f}, {dy_offset:.1f}) dist={pattern_distance:.1f}")
            
            if adaptive_candidates:
                adaptive_candidates.sort(key=lambda x: x[0])
                best = adaptive_candidates[0][1]
                if debug_angle:
                    best_text = best.get('text', best.get('coord_text', '?'))
                    print(f"ADAPTIVE MATCH: '{best_text}'")
    
    return best

def link_haltetafel_to_gks(haltetafel_det, gks_dets, coords, gks_coord_map,
                           max_distance=250,  #  Increased from 150
                           dy_tolerance=100,   #  Increased from 80
                           dx_tolerance=300,  #  Increased from 100
                           config: 'LayoutConfig' = None):
    """
    Link haltetafel to GKS box's coordinate if:
    1. Haltetafel is spatially close to GKS (touching/overlapping)
    2. No direct coordinate is found above/below haltetafel
    3. The GKS box has a linked coordinate

    Args:
        haltetafel_det: Haltetafel detection dict
        gks_dets: List of GKS detection dicts
        coords: List of all coordinate detections
        gks_coord_map: Dict mapping GKS id() to their linked coordinate
        config: LayoutConfig with debug flags and spatial params (optional)

    Returns:
        coordinate dict if found via GKS, else None
    """
    # Get debug flag from config or use module default
    debug = config.debug_angle_routing if config is not None else debug_angle
    haltetafel_cx = (haltetafel_det["x1"] + haltetafel_det["x2"]) / 2
    haltetafel_cy = (haltetafel_det["y1"] + haltetafel_det["y2"]) / 2

    if debug:
        print(f"\n   [Haltetafel Linking] Position: ({haltetafel_cx:.0f}, {haltetafel_cy:.0f})")

    # Find nearest GKS box
    nearest_gks = None
    min_distance = float('inf')

    for gks in gks_dets:
        gks_cx = (gks["x1"] + gks["x2"]) / 2
        gks_cy = (gks["y1"] + gks["y2"]) / 2

        dx = abs(gks_cx - haltetafel_cx)
        dy = abs(gks_cy - haltetafel_cy)
        distance = (dx**2 + dy**2) ** 0.5

        if debug:
            print(f"GKS at ({gks_cx:.0f}, {gks_cy:.0f}): dx={dx:.0f}, dy={dy:.0f}, dist={distance:.0f}")

        # Check if haltetafel is touching/near GKS
        if distance < max_distance and dx < dx_tolerance and dy < dy_tolerance:
            if distance < min_distance:
                min_distance = distance
                nearest_gks = gks

    if not nearest_gks:
        if debug:
            print(f"→ No nearby GKS found")
        return None

    # Get GKS's linked coordinate from the map
    gks_id = id(nearest_gks)
    gks_coord = gks_coord_map.get(gks_id)

    if debug:
        gks_text = nearest_gks.get('text', '?')
        if gks_coord:
            coord_text = gks_coord.get('text', '?')
            print(f"Found GKS '{gks_text}' with coordinate '{coord_text}'")
        else:
            print(f"Found GKS '{gks_text}' but it has NO coordinate")

    return gks_coord

def detect_fahrtrichtung(signal_det, gks_dets,
                        track_skeleton=None,
                        track_bounds=None,  #  NEW: Track layout bounds
                        max_distance=250,
                        dy_min=30,
                        dy_max=200,
                        dx_tolerance_left=120,
                        dx_tolerance_right=120,
                        angle_tolerance=20,
                        track_search_radius=500,  #  KEPT: Not used in new method, but kept for compatibility
                        track_sample_distance=200,  #  KEPT: Not used in new method, but kept for compatibility
                        config: 'LayoutConfig' = None):
    """
    Determine Fahrtrichtung (A or B) based on GKS box position relative to signal.
    
    TWO-STAGE DETECTION:
    1. PRIMARY: GKS-based detection
    2. FALLBACK: Track skeleton-based detection
    
    TRACK FALLBACK LOGIC:
    - Signal BELOW track → Fahrtrichtung A
    - Signal ABOVE track → Fahrtrichtung B
    
    Parameters (all in PIXELS at DPI=500):
        max_distance: 250px ≈ 12.7mm - Maximum search radius for GKS
        dy_min: 30px ≈ 1.5mm - Minimum vertical separation
        dy_max: 200px ≈ 10mm - Maximum vertical separation
        dx_tolerance_left: 120px - How far left (-x) GKS can be
        dx_tolerance_right: 120px - How far right (+x) GKS can be
        angle_tolerance: 20° - Max angle difference for parallel detection
        track_search_radius: 500px ≈ 25mm - How far to search for track centerline
        track_sample_distance: 200px ≈ 10mm - Distance to sample perpendicular to signal
    
    Returns:
        "A", "B", or None
    """
    # Get debug flags from config or use module defaults
    debug_linking = config.debug_linking if config is not None else DEBUG_LINKING
    debug_track = config.debug_track if config is not None else DEBUG_TRACK

    # Skip signals that don't need Fahrtrichtung detection:
    # 1. V-signals (Vorsignale) - e.g., V1, V2, VA1
    # 2. Single letter + 3+ digits - e.g., A123, U456, B789
    #    (detection parameters don't work for these, coordinate linking is sufficient)
    signal_text = (signal_det.get("text") or "").upper().strip()

    # Check V-signal
    if signal_text.startswith("V"):
        return None

    # Check single letter + 3+ digits pattern (e.g., A123, U456)
    if (len(signal_text) >= 4 and
        signal_text[0].isalpha() and
        signal_text[1:].isdigit() and
        len(signal_text[1:]) >= 3):
        return None
    
    # Use OBB center
    signal_cx = signal_det.get("cx")
    signal_cy = signal_det.get("cy")
    
    if signal_cx is None or signal_cy is None:
        signal_cx = (signal_det["x1"] + signal_det["x2"]) / 2
        signal_cy = (signal_det["y1"] + signal_det["y2"]) / 2
        if debug_linking:
            print(f"Using bounding box center (OBB center not available)")

    # DEBUG: Show signal center coordinates
    if debug_linking:
        print(f"DEBUG SIGNAL '{signal_text}': center=({signal_cx:.0f}, {signal_cy:.0f})")

    # Get signal angles
    signal_angle = float(signal_det.get("angle", 0.0))  # NORMALIZED
    signal_angle_raw = float(signal_det.get("angle_raw", signal_angle))  # RAW
    
    # ============================================================================
    #  ANGLE CORRECTION: Use OBB dimensions to detect horizontal text with 90° angle
    # ============================================================================
    obb_w = float(signal_det.get("obb_w", 0))
    obb_h = float(signal_det.get("obb_h", 0))
    
    # Determine true orientation from shape
    is_horizontal_by_shape = obb_w > obb_h * 1.2  # Width > Height (with 20% margin)
    is_vertical_by_shape = obb_h > obb_w * 1.2    # Height > Width
    
    # If shape says horizontal but angle says vertical (85-95°), correct angle
    if is_horizontal_by_shape and 75.0 <= abs(signal_angle_raw) <= 105.0:
        if debug_linking:
            print(f"ANGLE CORRECTION: Shape={obb_w:.0f}x{obb_h:.0f} (horizontal) but angle={signal_angle_raw:.1f}° (vertical)")
        signal_angle_raw_corrected = signal_angle_raw - 90.0
        if debug_linking:
            print(f"Correcting angle: {signal_angle_raw:.1f}° → {signal_angle_raw_corrected:.1f}°")
        signal_angle_raw = signal_angle_raw_corrected

    # If shape says vertical but angle says horizontal (near 0° or 180°), correct angle
    elif is_vertical_by_shape and (abs(signal_angle_raw) < 15.0 or abs(signal_angle_raw - 180.0) < 15.0):
        if debug_linking:
            print(f"ANGLE CORRECTION: Shape={obb_w:.0f}x{obb_h:.0f} (vertical) but angle={signal_angle_raw:.1f}° (horizontal)")
        signal_angle_raw_corrected = signal_angle_raw + 90.0
        if debug_linking:
            print(f"Correcting angle: {signal_angle_raw:.1f}° → {signal_angle_raw_corrected:.1f}°")
        signal_angle_raw = signal_angle_raw_corrected
    
    # ============================================================================
    # Use YOUR helper functions for orientation detection
    # ============================================================================
    a_norm = _norm_angle(signal_angle_raw)
    
    is_horizontal_signal = _is_near(a_norm, 0.0, ANGLE_TOL) or _is_near(a_norm, 180.0, ANGLE_TOL)
    is_vertical_signal = _is_near(a_norm, 90.0, ANGLE_TOL) or _is_near(a_norm, 270.0, ANGLE_TOL)
    is_angular_signal = not (is_horizontal_signal or is_vertical_signal)
    
    orientation = "HORIZONTAL" if is_horizontal_signal else ("VERTICAL" if is_vertical_signal else "ANGULAR")
    
    _debug_angle("FAHRTRICHTUNG", signal_det, orientation, 
                 f"raw={signal_angle_raw:.1f}° norm={signal_angle:.1f}° a_norm={a_norm:.1f}° shape={obb_w:.0f}x{obb_h:.0f}")
    
    # ============================================================================
    # STAGE 1: GKS-BASED DETECTION
    # ============================================================================
    
    nearest_gks = None
    min_distance = float('inf')
    
    for gks in gks_dets:
        gks_cx = gks.get("cx")
        gks_cy = gks.get("cy")
        
        if gks_cx is None or gks_cy is None:
            gks_cx = (gks["x1"] + gks["x2"]) / 2
            gks_cy = (gks["y1"] + gks["y2"]) / 2
        
        dx = gks_cx - signal_cx
        dy = gks_cy - signal_cy
        distance = (dx**2 + dy**2) ** 0.5

        # DEBUG: Show all GKS within 500px
        gks_text = gks.get('text', '?')
        if distance <= 500 and debug_linking:
            print(f"  GKS '{gks_text}': pos=({gks_cx:.0f},{gks_cy:.0f}), dx={dx:.1f}, dy={dy:.1f}, dist={distance:.1f}")

        if is_angular_signal:
            gks_angle = float(gks.get("angle", 0.0))
            angle_diff = abs(signal_angle - gks_angle)
            
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            if angle_diff > angle_tolerance:
                if debug_linking:
                    print(f"[Skip GKS] Angle mismatch: signal={signal_angle:.1f}°, gks={gks_angle:.1f}°, diff={angle_diff:.1f}°")
                continue
        
        if distance < min_distance and distance <= max_distance:
            min_distance = distance
            nearest_gks = {
                'det': gks, 
                'dx': dx, 
                'dy': dy, 
                'distance': distance,
                'angle': gks.get("angle", 0.0)
            }
    
    # ============================================================================
    # GKS FOUND
    # ============================================================================
    if nearest_gks:
        dx = nearest_gks['dx']
        dy = nearest_gks['dy']
        gks_angle = float(nearest_gks['angle'])
        
        angle_info = f", signal_θ={signal_angle:.1f}°, gks_θ={gks_angle:.1f}°" if is_angular_signal else ""
        gks_selected_text = nearest_gks['det'].get('text', '?')
        if debug_linking:
            print(f"[{orientation}] Signal '{signal_text}' → SELECTED GKS '{gks_selected_text}': dx={dx:.1f}px, dy={dy:.1f}px, dist={nearest_gks['distance']:.1f}px{angle_info}")
        
        if is_angular_signal:
            angle_rad = math.radians(signal_angle_raw)
            
            dx_local = dx * math.cos(-angle_rad) - dy * math.sin(-angle_rad)
            dy_local = dx * math.sin(-angle_rad) + dy * math.cos(-angle_rad)

            if debug_linking:
                print(f"Rotated coords: dx_local={dx_local:.1f}px, dy_local={dy_local:.1f}px")

            if dy_min < dy_local < dy_max and -dx_tolerance_left < dx_local < dx_tolerance_right:
                if debug_linking:
                    print(f"→ Fahrtrichtung: B (GKS below in rotated frame)")
                return "B"

            if -dy_max < dy_local < -dy_min and -dx_tolerance_right < dx_local < dx_tolerance_left:
                if debug_linking:
                    print(f"→ Fahrtrichtung: A (GKS above in rotated frame)")
                return "A"

        elif is_vertical_signal:
            #  For vertical text, swap dx/dy logic
            # "Below" in vertical text = to the RIGHT (+dx)
            # "Above" in vertical text = to the LEFT (-dx)
            if dy_min < dx < dy_max and -dx_tolerance_left < dy < dx_tolerance_right:
                if debug_linking:
                    print(f"→ Fahrtrichtung: B (GKS to the right)")
                return "B"

            if -dy_max < dx < -dy_min and -dx_tolerance_right < dy < dx_tolerance_left:
                if debug_linking:
                    print(f"→ Fahrtrichtung: A (GKS to the left)")
                return "A"

        else:
            # Horizontal signals
            if dy_min < dy < dy_max and -dx_tolerance_left < dx < dx_tolerance_right:
                if debug_linking:
                    print(f"→ Fahrtrichtung: B (GKS below)")
                return "B"

            if -dy_max < dy < -dy_min and -dx_tolerance_right < dx < dx_tolerance_left:
                if debug_linking:
                    print(f"→ Fahrtrichtung: A (GKS above)")
                return "A"

        if debug_linking:
            print(f"→ GKS found but outside range, trying track fallback...")
    
# ============================================================================
    # STAGE 2: TRACK FALLBACK (DYNAMIC PERPENDICULAR RAY-CASTING)
    # ============================================================================
    
    if track_skeleton is None:
        if debug_track:
            print(f"[{orientation}] Signal '{signal_text}' → No GKS, no track skeleton → Undetermined")
        return None

    if debug_track:
        print(f"\n     TRACK FALLBACK for Signal '{signal_text}'")
        print(f"Signal position: ({signal_cx:.0f}, {signal_cy:.0f})")
        print(f"Signal angle: raw={signal_angle_raw:.1f}°, norm={signal_angle:.1f}°")
        print(f"Signal orientation: {orientation} (shape: {obb_w:.0f}x{obb_h:.0f})")

    # Get track bounds for smart distance calculation
    if track_bounds and debug_track:
        print(f"Track layout bounds: Y=[{track_bounds['y_min']}, {track_bounds['y_max']}] (height={track_bounds['height']}px)")
    
    # ============================================================================
    #  RE-DETERMINE is_angular AFTER angle correction
    # The angle correction above may have changed the signal from "angular" to "horizontal"
    # ============================================================================
    
    # Recalculate normalized angle after correction
    a_norm_corrected = _norm_angle(signal_angle_raw)
    
    is_horizontal_corrected = _is_near(a_norm_corrected, 0.0, ANGLE_TOL) or _is_near(a_norm_corrected, 180.0, ANGLE_TOL)
    is_vertical_corrected = _is_near(a_norm_corrected, 90.0, ANGLE_TOL) or _is_near(a_norm_corrected, 270.0, ANGLE_TOL)
    is_angular_corrected = not (is_horizontal_corrected or is_vertical_corrected)
    
    orientation_corrected = "HORIZONTAL" if is_horizontal_corrected else ("VERTICAL" if is_vertical_corrected else "ANGULAR")
    
    if orientation_corrected != orientation and debug_track:
        print(f"Orientation changed after angle correction: {orientation} → {orientation_corrected}")
        print(f"Using corrected orientation for track detection")
    
    #  DYNAMIC PERPENDICULAR RAY-CASTING
    # - Horizontal/Vertical signals: Cast vertical rays (up/down)
    # - Angular signals: Cast rays perpendicular to signal angle
    signal_center = (int(signal_cx), int(signal_cy))
    
    track_result = find_nearest_track_perpendicular(
        signal_center, 
        track_skeleton,
        signal_angle_raw=signal_angle_raw,  #  Use CORRECTED angle
        track_bounds=track_bounds,
        max_distance=1500,  # Safety limit
        is_angular=is_angular_corrected  #  Use CORRECTED orientation
    )
    
    track_above = track_result['track_above']
    track_below = track_result['track_below']
    
    #  Enhanced logging
    if debug_track:
        print(f"Search range: {track_result['max_distance_above']}px above, {track_result['max_distance_below']}px below")
        print(f"Track above: {track_above} (distance: {track_result['distance_above']}px)")
        print(f"Track below: {track_below} (distance: {track_result['distance_below']}px)")
    
    if track_result['hit_above_first'] is not None and debug_track:
        first_hit = "above" if track_result['hit_above_first'] else "below"
        print(f" First track hit: {first_hit}")
    
    # ============================================================================
    # Determine Fahrtrichtung based on track position
    # For ANGULAR signals, use ROTATED coordinates (like GKS detection)
    # ============================================================================

    if is_angular_corrected:
        #  For angular signals: calculate track position in rotated frame
        
        # We need to find where the track actually is
        # Use the hit point from the ray-casting
        
        if track_above and not track_below:
            # Track found in "above" direction (perpendicular to signal)
            distance = track_result['distance_above']
            
            # Calculate track position in global coordinates
            perpendicular_angle = signal_angle_raw + 90.0
            perpendicular_rad = math.radians(perpendicular_angle)
            dx_above = math.cos(perpendicular_rad)
            dy_above = math.sin(perpendicular_rad)
            
            track_x = signal_cx + distance * dx_above
            track_y = signal_cy + distance * dy_above
            
        elif track_below and not track_above:
            # Track found in "below" direction (perpendicular to signal)
            distance = track_result['distance_below']
            
            # Calculate track position in global coordinates
            perpendicular_angle = signal_angle_raw + 90.0
            perpendicular_rad = math.radians(perpendicular_angle)
            dx_below = -math.cos(perpendicular_rad)
            dy_below = -math.sin(perpendicular_rad)
            
            track_x = signal_cx + distance * dx_below
            track_y = signal_cy + distance * dy_below
            
        elif track_above and track_below:
            # Both found - use closest
            if track_result['hit_above_first']:
                distance = track_result['distance_above']
                perpendicular_angle = signal_angle_raw + 90.0
                perpendicular_rad = math.radians(perpendicular_angle)
                dx = math.cos(perpendicular_rad)
                dy = math.sin(perpendicular_rad)
            else:
                distance = track_result['distance_below']
                perpendicular_angle = signal_angle_raw + 90.0
                perpendicular_rad = math.radians(perpendicular_angle)
                dx = -math.cos(perpendicular_rad)
                dy = -math.sin(perpendicular_rad)
            
            track_x = signal_cx + distance * dx
            track_y = signal_cy + distance * dy
        else:
            if debug_track:
                print(f"→ Fahrtrichtung: Undetermined (no track found)")
            return None

        #  Now convert track position to ROTATED coordinates (like GKS detection)
        dx_global = track_x - signal_cx
        dy_global = track_y - signal_cy
        
        angle_rad = math.radians(signal_angle_raw)
        dx_local = dx_global * math.cos(-angle_rad) - dy_global * math.sin(-angle_rad)
        dy_local = dx_global * math.sin(-angle_rad) + dy_global * math.cos(-angle_rad)
        
        if debug_track:
            print(f"Track in rotated coords: dx_local={dx_local:.1f}, dy_local={dy_local:.1f}")

        #  Use SAME logic as GKS detection
        if dy_local < 0:
            # Track is ABOVE in rotated frame → Fahrtrichtung A
            if debug_track:
                print(f"→ Fahrtrichtung: A (track above in rotated frame)")
            return "A"
        else:
            # Track is BELOW in rotated frame → Fahrtrichtung B
            if debug_track:
                print(f"→ Fahrtrichtung: B (track below in rotated frame)")
            return "B"

    else:
        #  For horizontal/vertical signals: simple global Y-axis
        if track_above and not track_below:
            if debug_track:
                print(f"→ Fahrtrichtung: A (track above signal)")
            return "A"

        elif track_below and not track_above:
            if debug_track:
                print(f"→ Fahrtrichtung: B (track below signal)")
            return "B"

        elif track_above and track_below:
            if track_result['hit_above_first']:
                if debug_track:
                    print(f"→ Fahrtrichtung: A (track above is closer)")
                return "A"
            else:
                if debug_track:
                    print(f"→ Fahrtrichtung: B (track below is closer)")
                return "B"

        else:
            if debug_track:
                print(f"→ Fahrtrichtung: Undetermined (no track found)")
            return None


# ============================================================================
# TIER 3: GKS COLUMN RELAXED FALLBACK
# ============================================================================

def detect_fahrtrichtung_gks_relaxed(signal_det, gks_dets, used_gks_ids=None,
                                      dx_tolerance=200,
                                      dy_min=30,
                                      dy_max=600,
                                      angle_tolerance=25,
                                      config: 'LayoutConfig' = None):
    """
    TIER 3 FALLBACK: Relaxed GKS column search.

    Used when:
    - Tier 1 (strict GKS) failed
    - Tier 2 (track skeleton) failed

    Strategy:
    - Search for GKS in same X-column (relaxed dx tolerance)
    - Allow larger vertical distance (up to 600px)
    - Only consider "orphan" GKS (not already matched)
    - Pick closest GKS in the column

    Parameters (all in PIXELS at DPI=500):
        dx_tolerance: 200px (~10mm) - Horizontal column width
        dy_min: 30px (~1.5mm) - Minimum vertical separation
        dy_max: 600px (~30mm) - Maximum vertical separation
        angle_tolerance: 25° - Max angle difference for angular signals
        config: LayoutConfig with debug flags (optional)

    Returns:
        ("A" or "B", gks_det) or (None, None)
    """
    # Get debug flag from config or use module default
    debug_linking = config.debug_linking if config is not None else DEBUG_LINKING

    if not gks_dets:
        return None, None

    used_gks_ids = used_gks_ids or set()

    # Get signal center
    signal_cx = signal_det.get("cx")
    signal_cy = signal_det.get("cy")

    if signal_cx is None or signal_cy is None:
        signal_cx = (signal_det["x1"] + signal_det["x2"]) / 2
        signal_cy = (signal_det["y1"] + signal_det["y2"]) / 2

    signal_text = signal_det.get("text", "?")
    signal_angle = float(signal_det.get("angle", 0.0))

    if debug_linking:
        print(f"\n   TIER 3 (GKS Relaxed): Signal '{signal_text}' at ({signal_cx:.0f}, {signal_cy:.0f})")
        print(f"Parameters: dx≤{dx_tolerance}px, dy=[{dy_min}, {dy_max}]px")

    # Find candidates in column
    candidates = []

    for gks in gks_dets:
        # Skip already-used GKS
        if id(gks) in used_gks_ids:
            continue

        gks_cx = gks.get("cx")
        gks_cy = gks.get("cy")

        if gks_cx is None or gks_cy is None:
            gks_cx = (gks["x1"] + gks["x2"]) / 2
            gks_cy = (gks["y1"] + gks["y2"]) / 2

        dx = abs(gks_cx - signal_cx)
        dy = gks_cy - signal_cy  # Signed: positive = GKS below signal
        dy_abs = abs(dy)

        # Check column constraint (relaxed)
        if dx > dx_tolerance:
            continue

        # Check vertical distance
        if dy_abs < dy_min or dy_abs > dy_max:
            continue

        # Check angle alignment for angular signals
        gks_angle = float(gks.get("angle", 0.0))
        angle_diff = abs(signal_angle - gks_angle)
        if angle_diff > 180:
            angle_diff = 360 - angle_diff

        if angle_diff > angle_tolerance:
            continue

        # Must be clearly above or below (not purely horizontal)
        if dy_abs < dx:
            continue

        gks_text = gks.get("text", gks.get("anchor_text", "?"))
        if debug_linking:
            print(f"→ Candidate: GKS '{gks_text}' at ({gks_cx:.0f}, {gks_cy:.0f}), dx={dx:.0f}, dy={dy:.0f}")

        candidates.append({
            'gks': gks,
            'dx': dx,
            'dy': dy,
            'dy_abs': dy_abs
        })

    if not candidates:
        if debug_linking:
            print(f"No GKS candidates found in column")
        return None, None

    # Pick closest (smallest dy_abs)
    best = min(candidates, key=lambda c: c['dy_abs'])
    gks = best['gks']
    dy = best['dy']

    gks_text = gks.get("text", gks.get("anchor_text", "?"))

    # Determine Fahrtrichtung: GKS above signal → A, GKS below → B
    if dy < 0:
        # GKS is ABOVE signal
        fahrtrichtung = "A"
        if debug_linking:
            print(f"MATCH: GKS '{gks_text}' is ABOVE → Fahrtrichtung A")
    else:
        # GKS is BELOW signal
        fahrtrichtung = "B"
        if debug_linking:
            print(f"MATCH: GKS '{gks_text}' is BELOW → Fahrtrichtung B")

    return fahrtrichtung, gks


# ============================================================================
# TIER 4: EUCLIDEAN NEAREST GKS FALLBACK
# ============================================================================

def detect_fahrtrichtung_gks_nearest(signal_det, gks_dets, used_gks_ids=None,
                                      max_distance=800,
                                      dy_min=30,
                                      angle_tolerance=30,
                                      config: 'LayoutConfig' = None):
    """
    TIER 4 FALLBACK: Euclidean nearest GKS search.

    Used when:
    - Tier 1 (strict GKS) failed
    - Tier 2 (track skeleton) failed
    - Tier 3 (GKS column relaxed) failed

    Strategy:
    - Search for ANY nearby GKS (Euclidean distance)
    - No column constraint
    - Only consider "orphan" GKS (not already matched)
    - Pick closest GKS by Euclidean distance
    - Must still be clearly above/below (not purely horizontal)

    Parameters (all in PIXELS at DPI=500):
        max_distance: 800px (~40mm) - Maximum Euclidean distance
        dy_min: 30px (~1.5mm) - Minimum vertical separation
        angle_tolerance: 30° - Max angle difference for angular signals
        config: LayoutConfig with debug flags (optional)

    Returns:
        ("A" or "B", gks_det) or (None, None)
    """
    # Get debug flag from config or use module default
    debug_linking = config.debug_linking if config is not None else DEBUG_LINKING

    if not gks_dets:
        return None, None

    used_gks_ids = used_gks_ids or set()

    # Get signal center
    signal_cx = signal_det.get("cx")
    signal_cy = signal_det.get("cy")

    if signal_cx is None or signal_cy is None:
        signal_cx = (signal_det["x1"] + signal_det["x2"]) / 2
        signal_cy = (signal_det["y1"] + signal_det["y2"]) / 2

    signal_text = signal_det.get("text", "?")
    signal_angle = float(signal_det.get("angle", 0.0))

    if debug_linking:
        print(f"\n   TIER 4 (GKS Nearest): Signal '{signal_text}' at ({signal_cx:.0f}, {signal_cy:.0f})")
        print(f"Parameters: max_dist≤{max_distance}px, dy_min={dy_min}px")

    # Find candidates
    candidates = []

    for gks in gks_dets:
        # Skip already-used GKS
        if id(gks) in used_gks_ids:
            continue

        gks_cx = gks.get("cx")
        gks_cy = gks.get("cy")

        if gks_cx is None or gks_cy is None:
            gks_cx = (gks["x1"] + gks["x2"]) / 2
            gks_cy = (gks["y1"] + gks["y2"]) / 2

        dx = gks_cx - signal_cx
        dy = gks_cy - signal_cy  # Signed: positive = GKS below signal

        # Calculate Euclidean distance
        euclidean_dist = math.sqrt(dx**2 + dy**2)

        # Check max distance
        if euclidean_dist > max_distance:
            continue

        # Check minimum vertical separation
        if abs(dy) < dy_min:
            continue

        # Must be more vertical than horizontal (direction check)
        if abs(dy) < abs(dx) * 0.5:  # Allow some horizontal offset
            continue

        # Check angle alignment for angular signals
        gks_angle = float(gks.get("angle", 0.0))
        angle_diff = abs(signal_angle - gks_angle)
        if angle_diff > 180:
            angle_diff = 360 - angle_diff

        if angle_diff > angle_tolerance:
            continue

        gks_text = gks.get("text", gks.get("anchor_text", "?"))
        if debug_linking:
            print(f"→ Candidate: GKS '{gks_text}' at ({gks_cx:.0f}, {gks_cy:.0f}), dist={euclidean_dist:.0f}, dy={dy:.0f}")

        candidates.append({
            'gks': gks,
            'dist': euclidean_dist,
            'dy': dy
        })

    if not candidates:
        if debug_linking:
            print(f"No GKS candidates found nearby")
        return None, None

    # Pick closest (smallest Euclidean distance)
    best = min(candidates, key=lambda c: c['dist'])
    gks = best['gks']
    dy = best['dy']

    gks_text = gks.get("text", gks.get("anchor_text", "?"))

    # Determine Fahrtrichtung: GKS above signal → A, GKS below → B
    if dy < 0:
        # GKS is ABOVE signal
        fahrtrichtung = "A"
        if debug_linking:
            print(f"MATCH: GKS '{gks_text}' is ABOVE → Fahrtrichtung A")
    else:
        # GKS is BELOW signal
        fahrtrichtung = "B"
        if debug_linking:
            print(f"MATCH: GKS '{gks_text}' is BELOW → Fahrtrichtung B")

    return fahrtrichtung, gks


# ============================================================================
# MERGE DUPLICATE SIGNALS (SIMPLIFIED - NO TRACK FALLBACK)
# ============================================================================

def merge_duplicate_signals(all_rows: List[dict], track_skeleton=None, gks_dets=None,
                           spatial_threshold: int = None,
                           config: 'LayoutConfig' = None) -> List[dict]:
    """
    Merge duplicate signal instances with SPATIAL CLUSTERING for multi-section plans.

    NEW FEATURES:
     Auto-detects multi-section plans (finds gaps in Y-positions)
     Clusters signals by 2D proximity (X AND Y)
     Merges duplicates WITHIN each cluster only
     Preserves signals across different sections

    Priority Rules (within each cluster):
    1. Identify Haltepunkt coordinates (exclude them)
    2. Find coordinate-only instance (PRIMARY)
    3. Find Fahrtrichtung instance
    4. Find Haltepunkt instance
    5. Merge all data into PRIMARY
    6. Create SINGLE overlay (coordinate + signal)
    7. Store ALL signal positions in _signal_positions

    Args:
        all_rows: List of all detection rows
        track_skeleton: IGNORED (kept for backward compatibility)
        gks_dets: IGNORED (kept for backward compatibility)
        spatial_threshold: Override auto-detection (pixels). None = auto-detect
        config: LayoutConfig with debug flags (optional)
    """
    # Get debug flags from config or use module defaults
    debug_linking = config.debug_linking if config is not None else DEBUG_LINKING

    if debug_linking:
        print(f"\n{'='*70}")
        print(f" MERGING DUPLICATE SIGNALS (Spatial Clustering + Full Data)")
        print(f"{'='*70}")

    # ========================================
    # STEP 0: Auto-detect spatial threshold
    # ========================================
    if spatial_threshold is None:
        signal_rows = [r for r in all_rows if r.get('cls') == 'signal' and r.get('anchor_text')]
        spatial_threshold = estimate_spatial_threshold(signal_rows, config=config)
    else:
        if debug_linking:
            print(f" Using manual threshold: {spatial_threshold}px")
    
    # ========================================
    # STEP 1: Detect Haltepunkt coordinates
    # ========================================
    page_groups = {}
    for row in all_rows:
        page = row['page']
        if page not in page_groups:
            page_groups[page] = {
                'haltepunkt': [],
                'signal': [],
                'coordinate': []
            }
        
        if row['cls'] == 'haltepunkt':
            page_groups[page]['haltepunkt'].append(row)
        elif row['cls'] == 'signal':
            page_groups[page]['signal'].append(row)
        elif row['cls'] == 'coordinate':
            page_groups[page]['coordinate'].append(row)
    
    # Map: (page, signal_text) -> haltepunkt_coordinate
    haltepunkt_coords = {}
    
    for page, groups in page_groups.items():
        for halt_row in groups['haltepunkt']:
            haltepunkt_det = {
                'x1': halt_row['ax1'],
                'y1': halt_row['ay1'],
                'x2': halt_row['ax2'],
                'y2': halt_row['ay2'],
                'angle': halt_row.get('angle', 0.0),
                'angle_raw': halt_row.get('angle_raw', halt_row.get('angle', 0.0))
            }
            
            signal_dets = [{
                'x1': s['ax1'],
                'y1': s['ay1'],
                'x2': s['ax2'],
                'y2': s['ay2'],
                'angle': s.get('angle', 0.0),
                'text': s.get('anchor_text', ''),
                'row_id': s['row_id']
            } for s in groups['signal']]
            
            coord_dets = []
            for c in groups['coordinate']:
                coord_dets.append({
                    'cx1': c.get('cx1'),
                    'cy1': c.get('cy1'),
                    'cx2': c.get('cx2'),
                    'cy2': c.get('cy2'),
                    'x1': c.get('ax1') if c.get('cx1') is None else c.get('cx1'),
                    'y1': c.get('ay1') if c.get('cy1') is None else c.get('cy1'),
                    'x2': c.get('ax2') if c.get('cx2') is None else c.get('cx2'),
                    'y2': c.get('ay2') if c.get('cy2') is None else c.get('cy2'),
                    'text': c.get('coord_text', ''),
                    'row_id': c['row_id']
                })
            
            group_result = detect_haltepunkt_signal_group(
                haltepunkt_det, signal_dets, coord_dets
            )
            
            if group_result and group_result.get('signal') and group_result.get('coordinate'):
                signal_text = group_result['signal']
                coord_text = group_result['coordinate']
                key = (page, signal_text)
                haltepunkt_coords[key] = coord_text
                
                if debug_linking:
                    print(f" Haltepunkt coordinate: signal='{signal_text}', coord='{coord_text}' (EXCLUDE THIS)")
    
    # ========================================
    # STEP 2: Group signal instances by (page, name)
    # ========================================
    signal_groups = {}
    for row in all_rows:
        if row['cls'] != 'signal':
            continue
        
        page = row['page']
        anchor_text = (row.get('anchor_text') or '').strip()
        
        if not anchor_text:
            continue
        
        key = (page, anchor_text)
        if key not in signal_groups:
            signal_groups[key] = []
        signal_groups[key].append(row)
    
    # ========================================
    # STEP 3: Spatial clustering + merging
    # ========================================
    merged_rows = []
    processed_row_ids = set()
    
    for (page, anchor_text), instances in signal_groups.items():
        if len(instances) == 1:
            # Single instance - no merging needed
            continue
        
        key = (page, anchor_text)
        haltepunkt_coord = haltepunkt_coords.get(key)

        if debug_linking:
            print(f"\n Signal '{anchor_text}' on page {page}: {len(instances)} instances")
            if haltepunkt_coord:
                print(f" Haltepunkt coordinate to EXCLUDE: '{haltepunkt_coord}'")
        
        # ========================================
        # STEP 3A: SPATIAL CLUSTERING (2D: X and Y)
        # ========================================
        
        # Sort by position (Y first, then X) for better clustering
        instances.sort(key=lambda r: (
            r.get('cy', (r['ay1'] + r['ay2']) / 2),
            r.get('cx', (r['ax1'] + r['ax2']) / 2)
        ))
        
        clusters = []
        
        for inst in instances:
            # Get instance center
            inst_cx = inst.get('cx', (inst['ax1'] + inst['ax2']) / 2)
            inst_cy = inst.get('cy', (inst['ay1'] + inst['ay2']) / 2)
            
            # Find nearest cluster (2D Euclidean distance)
            best_cluster = None
            min_distance = float('inf')
            
            for cluster in clusters:
                # Calculate cluster centroid
                cluster_cx = sum(r.get('cx', (r['ax1'] + r['ax2']) / 2) for r in cluster) / len(cluster)
                cluster_cy = sum(r.get('cy', (r['ay1'] + r['ay2']) / 2) for r in cluster) / len(cluster)
                
                # 2D Euclidean distance
                distance = ((inst_cx - cluster_cx)**2 + (inst_cy - cluster_cy)**2)**0.5
                
                if distance < min_distance:
                    min_distance = distance
                    best_cluster = cluster
            
            # Add to nearest cluster if within threshold, else create new cluster
            if best_cluster is not None and min_distance < spatial_threshold:
                best_cluster.append(inst)
            else:
                clusters.append([inst])
        
        if debug_linking:
            print(f"Clustered into {len(clusters)} spatial groups (threshold={spatial_threshold}px)")
        
        # ========================================
        # STEP 3B: Process each cluster independently
        # ========================================
        
        for cluster_idx, cluster in enumerate(clusters):
            if len(cluster) == 1:
                # Single instance in cluster - no merging needed
                if debug_linking:
                    print(f" Cluster {cluster_idx+1}: 1 instance → no merge needed")
                continue

            # Calculate cluster centroid for logging
            cluster_cx = sum(r.get('cx', (r['ax1'] + r['ax2']) / 2) for r in cluster) / len(cluster)
            cluster_cy = sum(r.get('cy', (r['ay1'] + r['ay2']) / 2) for r in cluster) / len(cluster)

            if debug_linking:
                print(f"\n    Cluster {cluster_idx+1}: {len(cluster)} instances at ({cluster_cx:.0f}, {cluster_cy:.0f})")
            
            # ========================================
            # STEP 3C: Classify instances WITHIN cluster (IMPROVED)
            # ========================================
            coord_only_instances = []
            fahrtrichtung_instances = []
            haltepunkt_instances = []
            coord_with_fahr_instances = []  #  NEW: Instances with BOTH coord and fahr

            for inst in cluster:
                has_coord = pd.notna(inst.get('coord_text')) and inst.get('coord_text')
                has_fahr = pd.notna(inst.get('fahrtrichtung')) and inst.get('fahrtrichtung')
                coord_text = inst.get('coord_text', '')
                
                #  NEW: Classify instances with BOTH coord and fahr
                if has_coord and has_fahr:
                    coord_with_fahr_instances.append(inst)

                    #  DIAGNOSTIC: Show Fahrtrichtung source
                    fahr_source = inst.get('_fahrtrichtung_source', 'MISSING!')

                    if debug_linking:
                        if fahr_source == 'gks':
                            print(f" Coord+Fahr instance: row_id={inst['row_id']}, coord={coord_text}, fahr={inst.get('fahrtrichtung')} (from GKS - TRUSTED)")
                        else:
                            print(f" Coord+Fahr instance: row_id={inst['row_id']}, coord={coord_text}, fahr={inst.get('fahrtrichtung')} (source={fahr_source})")

                    continue
                
                # Fahrtrichtung-only instance
                if has_fahr:
                    fahrtrichtung_instances.append(inst)
                    if debug_linking:
                        print(f"Fahrtrichtung instance: row_id={inst['row_id']}, dir={inst.get('fahrtrichtung')}")
                    continue
                
                # Coordinate-only instance
                if has_coord:
                    if haltepunkt_coord and coord_text == haltepunkt_coord:
                        haltepunkt_instances.append(inst)
                        if debug_linking:
                            print(f" Haltepunkt coordinate instance: row_id={inst['row_id']}, coord={coord_text} (SAVE POSITION)")
                    else:
                        coord_only_instances.append(inst)
                        if debug_linking:
                            print(f" Coordinate-only instance: row_id={inst['row_id']}, coord={coord_text}")
                    continue

                # Bare haltepunkt instance (no coord, no fahr)
                haltepunkt_instances.append(inst)
                if debug_linking:
                    print(f" Bare haltepunkt instance: row_id={inst['row_id']} (SAVE POSITION)")
            
            # ========================================
            # STEP 3D: Select PRIMARY coordinate instance (IMPROVED)
            # ========================================

            coord_instance = None

            #  PRIORITY 1: Coordinate-only instances (cleanest)
            if coord_only_instances:
                if len(coord_only_instances) == 1:
                    coord_instance = coord_only_instances[0]
                    if debug_linking:
                        print(f"PRIMARY (coord-only): row_id={coord_instance['row_id']}, coord={coord_instance.get('coord_text')}")
                else:
                    # Multiple coord-only instances - use haltepunkt distance logic
                    if debug_linking:
                        print(f"Multiple coordinate-only instances: {len(coord_only_instances)}")

                    if haltepunkt_coord:
                        try:
                            # Use configurable decimal separator
                            in_sep = config.validation.decimal_separator_input if config and hasattr(config.validation, 'decimal_separator_input') else ","
                            out_sep = config.validation.decimal_separator_output if config and hasattr(config.validation, 'decimal_separator_output') else "."
                            halt_val = float(haltepunkt_coord.replace(in_sep, out_sep))
                            best_coord = None
                            best_diff = 0

                            for c_inst in coord_only_instances:
                                coord_val = float((c_inst.get('coord_text') or '0').replace(in_sep, out_sep))
                                diff = abs(coord_val - halt_val)
                                if debug_linking:
                                    print(f"Candidate: row_id={c_inst['row_id']}, coord={c_inst.get('coord_text')}, diff={diff:.4f}")

                                if diff > best_diff:
                                    best_diff = diff
                                    best_coord = c_inst

                            coord_instance = best_coord
                            if debug_linking:
                                print(f"PRIMARY (furthest from Haltepunkt): row_id={coord_instance['row_id']}, diff={best_diff:.4f}")

                            for c_inst in coord_only_instances:
                                if c_inst['row_id'] != coord_instance['row_id']:
                                    processed_row_ids.add(c_inst['row_id'])
                                    c_inst['_hidden'] = True
                                    if debug_linking:
                                        print(f" Hiding duplicate: row_id={c_inst['row_id']}")
                        except ValueError:
                            coord_instance = coord_only_instances[0]
                            if debug_linking:
                                print(f"Could not parse - using first: row_id={coord_instance['row_id']}")
                    else:
                        coord_instance = coord_only_instances[0]
                        if debug_linking:
                            print(f"PRIMARY (first): row_id={coord_instance['row_id']}")
                
                #  FIX: Check if coord+fahr instances have GKS-based Fahrtrichtung
                coord_fahr_with_gks = None
                if coord_with_fahr_instances:
                    for inst in coord_with_fahr_instances:
                        if inst.get('_fahrtrichtung_source') == 'gks' and inst.get('fahrtrichtung'):
                            coord_fahr_with_gks = inst
                            break
                
                #  If coord+fahr has GKS-based Fahrtrichtung, PRESERVE it!
                if coord_fahr_with_gks:
                    if debug_linking:
                        print(f"PRESERVING Fahrtrichtung '{coord_fahr_with_gks.get('fahrtrichtung')}' from coord+fahr instance (GKS-based - TRUSTED)")
                    coord_instance['fahrtrichtung'] = coord_fahr_with_gks.get('fahrtrichtung')
                    coord_instance['_fahrtrichtung_source'] = 'gks'

                #  Hide ALL coord+fahr instances (we chose coord-only as PRIMARY)
                if coord_with_fahr_instances:
                    if debug_linking:
                        print(f" Hiding {len(coord_with_fahr_instances)} coord+fahr instances (coord-only is PRIMARY)")
                    for inst in coord_with_fahr_instances:
                        processed_row_ids.add(inst['row_id'])
                        inst['_hidden'] = True
                        if debug_linking:
                            print(f"- row_id={inst['row_id']}, coord={inst.get('coord_text')}, fahr={inst.get('fahrtrichtung')}")

            #  PRIORITY 2: Coord+Fahr instances (if no coord-only exists)
            elif coord_with_fahr_instances:
                coord_instance = coord_with_fahr_instances[0]

                #  CHECK: Is this Fahrtrichtung from GKS or from duplicate?
                fahr_source = coord_instance.get('_fahrtrichtung_source', 'unknown')

                if debug_linking:
                    if fahr_source == 'gks':
                        #  GKS-based Fahrtrichtung - TRUSTED!
                        print(f"PRIMARY (coord+fahr): row_id={coord_instance['row_id']}, coord={coord_instance.get('coord_text')}, fahr={coord_instance.get('fahrtrichtung')} (from GKS - TRUSTED)")
                    else:
                        #  Unknown source - will be verified later
                        print(f"PRIMARY (coord+fahr): row_id={coord_instance['row_id']}, coord={coord_instance.get('coord_text')}, fahr={coord_instance.get('fahrtrichtung')} (source={fahr_source} - will be verified)")

                #  FIX: Only hide OTHER coord+fahr instances (NOT the PRIMARY!)
                for inst in coord_with_fahr_instances:
                    if inst['row_id'] != coord_instance['row_id']:  #  SKIP the PRIMARY
                        processed_row_ids.add(inst['row_id'])
                        inst['_hidden'] = True
                        if debug_linking:
                            print(f" Hiding OTHER coord+fahr instance: row_id={inst['row_id']}")
                
                #  Mark the PRIMARY as processed (but DON'T hide it!)
                processed_row_ids.add(coord_instance['row_id'])

            #  PRIORITY 3: No coordinate instance found
            else:
                if debug_linking:
                    print(f"No coordinate instance found in this cluster")
                for inst in haltepunkt_instances:
                    processed_row_ids.add(inst['row_id'])
                    inst['_hidden'] = True
                continue  # Skip this cluster

            # ========================================
            # STEP 3E: Select Fahrtrichtung instance
            # ========================================

            fahrtrichtung_instance = None

            if len(fahrtrichtung_instances) == 0:
                if debug_linking:
                    print(f"No Fahrtrichtung instance (will be filled by track fallback later)")

            elif len(fahrtrichtung_instances) == 1:
                fahrtrichtung_instance = fahrtrichtung_instances[0]
                if debug_linking:
                    print(f"FAHRTRICHTUNG: row_id={fahrtrichtung_instance['row_id']}, dir={fahrtrichtung_instance.get('fahrtrichtung')}")

            else:
                if debug_linking:
                    print(f"Multiple Fahrtrichtung instances: {len(fahrtrichtung_instances)} - using first")
                fahrtrichtung_instance = fahrtrichtung_instances[0]
                
                for f_inst in fahrtrichtung_instances[1:]:
                    processed_row_ids.add(f_inst['row_id'])
                    f_inst['_hidden'] = True
            
            # ========================================
            # STEP 3F: Select Haltepunkt instance (if exists)
            # ========================================
            
            haltepunkt_instance = None
            
            if len(haltepunkt_instances) > 0:
                haltepunkt_instance = haltepunkt_instances[0]
                if debug_linking:
                    print(f"HALTEPUNKT: row_id={haltepunkt_instance['row_id']}")
                
                for halt_inst in haltepunkt_instances[1:]:
                    processed_row_ids.add(halt_inst['row_id'])
                    halt_inst['_hidden'] = True
            
            # ========================================
            # STEP 3G: Merge ALL data into PRIMARY (SIMPLIFIED)
            # ========================================

            final_row = coord_instance.copy()

        #  IMPROVED RULE: Use Fahrtrichtung from fahr-only instance OR from GKS-based coord+fahr

            if fahrtrichtung_instance:
                # fahr-only instance exists → TRUSTED
                final_row['fahrtrichtung'] = fahrtrichtung_instance.get('fahrtrichtung')
                final_row['_fahrtrichtung_source'] = 'gks'
                if debug_linking:
                    print(f"Using Fahrtrichtung '{fahrtrichtung_instance.get('fahrtrichtung')}' from fahr-only instance")

                processed_row_ids.add(fahrtrichtung_instance['row_id'])

            else:
                # No fahr-only instance - check if coord+fahr has GKS-based Fahrtrichtung
                coord_fahr_source = coord_instance.get('_fahrtrichtung_source', 'unknown')

                if coord_fahr_source == 'gks' and coord_instance.get('fahrtrichtung'):
                    #  Coord+Fahr has GKS-based Fahrtrichtung → TRUSTED!
                    final_row['fahrtrichtung'] = coord_instance.get('fahrtrichtung')
                    final_row['_fahrtrichtung_source'] = 'gks'
                    if debug_linking:
                        print(f"Using Fahrtrichtung '{coord_instance.get('fahrtrichtung')}' from coord+fahr instance (GKS-based - TRUSTED)")

                else:
                    # No trusted Fahrtrichtung → track fallback
                    final_row['fahrtrichtung'] = None
                    final_row['_fahrtrichtung_source'] = 'none'

                    #  Log if we're ignoring coord+fahr Fahrtrichtung
                    if debug_linking:
                        if coord_instance.get('fahrtrichtung'):
                            print(f"Ignoring Fahrtrichtung '{coord_instance.get('fahrtrichtung')}' from coord+fahr instance (source={coord_fahr_source} - not trusted)")
                            print(f"Track fallback will determine Fahrtrichtung")
                        else:
                            print(f"No Fahrtrichtung → track fallback will fill")
            
            # Store ALL signal positions
            signal_positions = {
                'coordinate_signal': {
                    'ax1': coord_instance['ax1'],
                    'ay1': coord_instance['ay1'],
                    'ax2': coord_instance['ax2'],
                    'ay2': coord_instance['ay2'],
                    'row_id': coord_instance['row_id']
                }
            }
            
            if fahrtrichtung_instance:
                signal_positions['fahrtrichtung_signal'] = {
                    'ax1': fahrtrichtung_instance['ax1'],
                    'ay1': fahrtrichtung_instance['ay1'],
                    'ax2': fahrtrichtung_instance['ax2'],
                    'ay2': fahrtrichtung_instance['ay2'],
                    'row_id': fahrtrichtung_instance['row_id']
                }
            
            if haltepunkt_instance:
                signal_positions['haltepunkt_signal'] = {
                    'ax1': haltepunkt_instance['ax1'],
                    'ay1': haltepunkt_instance['ay1'],
                    'ax2': haltepunkt_instance['ax2'],
                    'ay2': haltepunkt_instance['ay2'],
                    'row_id': haltepunkt_instance['row_id']
                }
                if debug_linking:
                    print(f" Stored Haltepunkt signal position")
            
            final_row['_signal_positions'] = signal_positions
            
            # Create ONLY 1 overlay for display
            all_bboxes = [{
                'type': 'signal_with_coord',
                'ax1': coord_instance['ax1'],
                'ay1': coord_instance['ay1'],
                'ax2': coord_instance['ax2'],
                'ay2': coord_instance['ay2'],
                'cx1': coord_instance.get('cx1'),
                'cy1': coord_instance.get('cy1'),
                'cx2': coord_instance.get('cx2'),
                'cy2': coord_instance.get('cy2'),
                'angle': coord_instance.get('angle', 0.0),
                'angle_raw': coord_instance.get('angle_raw', 0.0),
                'conf': coord_instance.get('conf', 1.0),
                'label': f"{anchor_text} @ {coord_instance.get('coord_text')}"
            }]
            
            if debug_linking:
                print(f" Single Overlay: Signal + Coordinate {coord_instance.get('coord_text')}")

            num_positions = len(signal_positions)
            if debug_linking:
                print(f" Stored {num_positions} signal positions in _signal_positions")

            final_row['_all_bboxes'] = all_bboxes

            processed_row_ids.add(coord_instance['row_id'])
            if fahrtrichtung_instance:
                processed_row_ids.add(fahrtrichtung_instance['row_id'])

            if haltepunkt_instance:
                processed_row_ids.add(haltepunkt_instance['row_id'])
                haltepunkt_instance['_hidden'] = True
                if debug_linking:
                    print(f" Hiding haltepunkt instance: row_id={haltepunkt_instance['row_id']} (data preserved)")

            merged_rows.append(final_row)

            if debug_linking:
                fahr_display = final_row.get('fahrtrichtung', 'None')
                fahr_source = final_row.get('_fahrtrichtung_source', 'unknown')
                print(f"CLUSTER MERGED: row_id={final_row['row_id']}, coord={final_row.get('coord_text')}, "
                      f"fahr={fahr_display} (source={fahr_source})")
    
    # ========================================
    # STEP 4: Build final result
    # ========================================
    result = []
    
    for row in all_rows:
        row_id = row['row_id']
        
        if row_id in processed_row_ids and row_id not in [m['row_id'] for m in merged_rows]:
            continue
        
        result.append(row)
    
    for merged in merged_rows:
        for i, row in enumerate(result):
            if row['row_id'] == merged['row_id']:
                result[i] = merged
                break
    
    visible = len([r for r in result if not r.get('_hidden')])
    hidden = len([r for r in result if r.get('_hidden')])

    if debug_linking:
        print(f"\n{'='*70}")
        print(f"Merging complete: {len(result)} rows ({visible} visible, {hidden} hidden)")
        print(f"Merged: {len(merged_rows)} signal groups")

        gks_count = sum(1 for m in merged_rows if m.get('_fahrtrichtung_source') == 'gks')
        none_count = sum(1 for m in merged_rows if m.get('_fahrtrichtung_source') == 'none')

        print(f"Fahrtrichtung sources: GKS={gks_count}, None={none_count} (track fallback will run later)")
        print(f"{'='*70}\n")

    return result

def estimate_spatial_threshold(signal_rows: List[dict], config: 'LayoutConfig' = None) -> int:
    """
    Auto-detect spatial threshold based on signal Y-position distribution.
    Detects multi-section plans by finding large gaps in Y-positions.

    Returns:
        Threshold in pixels (configurable min/max, default 1000-2500)
    """
    # Get config values or use defaults
    sp = config.spatial if config else None
    single_section_threshold = sp.spatial_threshold_single_section if sp else 1000
    gap_multiplier = sp.spatial_threshold_gap_multiplier if sp else 3.0
    section_gap_min = sp.spatial_threshold_section_gap_min if sp else 1000
    section_gap_max = sp.spatial_threshold_section_gap_max if sp else 2500
    default_threshold = (section_gap_min + section_gap_max) // 2  # 1500 default

    if len(signal_rows) < 10:
        if debug_linking:
            print(f"Few signals ({len(signal_rows)}) → using default threshold: {default_threshold}px")
        return default_threshold

    # Get all Y-positions (use center Y)
    y_positions = sorted([
        r.get('cy', (r['ay1'] + r['ay2']) / 2)
        for r in signal_rows
    ])

    # Calculate gaps between consecutive signals
    gaps = [y_positions[i+1] - y_positions[i] for i in range(len(y_positions)-1)]

    if not gaps:
        return default_threshold

    # Find median gap (typical spacing within a section)
    median_gap = sorted(gaps)[len(gaps)//2]

    # Find large gaps (potential section boundaries)
    # Large gap = multiplier * median gap
    large_gaps = [g for g in gaps if g > median_gap * gap_multiplier]

    if large_gaps:
        # Multi-section plan detected
        avg_section_gap = sum(large_gaps) / len(large_gaps)

        # Threshold = 40% of average section gap
        # This ensures we merge within sections but not across sections
        threshold = int(avg_section_gap * 0.4)

        # Clamp to reasonable range from config
        threshold = max(section_gap_min, min(section_gap_max, threshold))

        if debug_linking:
            print(f"Multi-section plan detected:")
            print(f"- {len(large_gaps)} section boundaries found")
            print(f"- Average section gap: {avg_section_gap:.0f}px")
            print(f"- Median within-section gap: {median_gap:.0f}px")
            print(f"- Auto threshold: {threshold}px (40% of section gap)")

        return threshold
    else:
        # Single-section plan
        # Use smaller threshold for tighter merging
        threshold = single_section_threshold
        if debug_linking:
            print(f"Single-section plan detected:")
            print(f"- Median signal spacing: {median_gap:.0f}px")
            print(f"- Auto threshold: {threshold}px")

        return threshold

def detect_haltepunkt_signal_group(haltepunkt_det, signal_dets, coord_dets,
                                     max_distance=250,
                                     dy_signal_min=30,
                                     dy_signal_max=200,
                                     dy_coord_min=20,
                                     dy_coord_max=150,
                                     dx_tolerance=100,
                                     angle_tolerance=20.0,
                                     config: 'LayoutConfig' = None):
    """
    Detect if a signal and coordinate are associated with a haltepunkt.

    Layout patterns:
    1. Normal:   Haltepunkt (top) → Coordinate (middle) → Signal (bottom)
    2. Inverted: Signal (top) → Coordinate (middle) → Haltepunkt (bottom)

    Parameters (all in PIXELS at DPI=500):
        max_distance: 250px - Maximum search radius
        dy_signal_min: 30px - Minimum vertical separation to signal
        dy_signal_max: 200px - Maximum vertical separation to signal
        dy_coord_min: 20px - Minimum vertical separation to coordinate
        dy_coord_max: 150px - Maximum vertical separation to coordinate
        dx_tolerance: 100px - How far left/right elements can be
        angle_tolerance: 20.0° - Max angle difference for angular haltepunkt
        config: LayoutConfig with debug flags (optional)

    Returns:
        dict with 'signal': signal_text, 'coordinate': coord_text, or None
    """
    # Get debug flag from config or use module default
    debug = config.debug_angle_routing if config is not None else debug_angle

    # Get haltepunkt angle and position
    haltepunkt_angle = float(haltepunkt_det.get("angle", 0.0))
    haltepunkt_angle_raw = float(haltepunkt_det.get("angle_raw", haltepunkt_angle))
    is_angular = abs(haltepunkt_angle) > 15.0
    
    haltepunkt_cx = (haltepunkt_det["x1"] + haltepunkt_det["x2"]) / 2
    haltepunkt_cy = (haltepunkt_det["y1"] + haltepunkt_det["y2"]) / 2
    
    if debug:
        mode = "ANGULAR" if is_angular else "HORIZONTAL"
        print(f"\n   [{mode}] Checking haltepunkt at ({haltepunkt_cx:.0f}, {haltepunkt_cy:.0f})")

    # Find nearby signal
    nearest_signal = None
    min_signal_dist = float('inf')

    for signal_det in signal_dets:
        signal_cx = (signal_det["x1"] + signal_det["x2"]) / 2
        signal_cy = (signal_det["y1"] + signal_det["y2"]) / 2

        dx = signal_cx - haltepunkt_cx
        dy = signal_cy - haltepunkt_cy
        distance = (dx**2 + dy**2) ** 0.5

        if distance > max_distance:
            continue

        # For angular, check angle alignment
        if is_angular:
            signal_angle = float(signal_det.get("angle", 0.0))
            angle_diff = abs(haltepunkt_angle - signal_angle)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            if angle_diff > angle_tolerance:
                continue

        # Check if signal is above or below
        if is_angular:
            angle_rad = math.radians(haltepunkt_angle_raw)
            dx_local = dx * math.cos(-angle_rad) - dy * math.sin(-angle_rad)
            dy_local = dx * math.sin(-angle_rad) + dy * math.cos(-angle_rad)

            if dy_signal_min < abs(dy_local) < dy_signal_max and abs(dx_local) < dx_tolerance:
                if distance < min_signal_dist:
                    min_signal_dist = distance
                    nearest_signal = {
                        'det': signal_det,
                        'text': signal_det.get('text', ''),
                        'dy_local': dy_local,
                        'distance': distance
                    }
        else:
            if dy_signal_min < abs(dy) < dy_signal_max and abs(dx) < dx_tolerance:
                if distance < min_signal_dist:
                    min_signal_dist = distance
                    nearest_signal = {
                        'det': signal_det,
                        'text': signal_det.get('text', ''),
                        'dy': dy,
                        'distance': distance
                    }

    if not nearest_signal:
        if debug:
            print(f"→ No signal found")
        return None
    
    # Find coordinate in between haltepunkt and signal
    signal_det = nearest_signal['det']
    signal_cy = (signal_det["y1"] + signal_det["y2"]) / 2
    
    nearest_coord = None
    min_coord_dist = float('inf')
    
    for coord_det in coord_dets:
        #  FIX: Handle both formats (detection dict vs processed dict)
        if "cx1" in coord_det and coord_det["cx1"] is not None:
            coord_cx = (coord_det["cx1"] + coord_det["cx2"]) / 2
            coord_cy = (coord_det["cy1"] + coord_det["cy2"]) / 2
        elif "x1" in coord_det:
            # Fallback to bounding box
            coord_cx = (coord_det["x1"] + coord_det["x2"]) / 2
            coord_cy = (coord_det["y1"] + coord_det["y2"]) / 2
        else:
            continue  # Skip if no position data
        
        # Check if coordinate is between haltepunkt and signal (Y-axis)
        is_between = False
        if is_angular:
            signal_dy_local = nearest_signal['dy_local']
            dx = coord_cx - haltepunkt_cx
            dy = coord_cy - haltepunkt_cy
            
            angle_rad = math.radians(haltepunkt_angle_raw)
            dx_local = dx * math.cos(-angle_rad) - dy * math.sin(-angle_rad)
            dy_local = dx * math.sin(-angle_rad) + dy * math.cos(-angle_rad)
            
            # Check if between in local coordinate system
            if signal_dy_local > 0:  # Signal below
                is_between = 0 < dy_local < signal_dy_local and abs(dx_local) < dx_tolerance
            else:  # Signal above
                is_between = signal_dy_local < dy_local < 0 and abs(dx_local) < dx_tolerance
        else:
            signal_dy = nearest_signal['dy']
            dx = coord_cx - haltepunkt_cx
            dy = coord_cy - haltepunkt_cy
            
            # Check if between
            if signal_dy > 0:  # Signal below
                is_between = 0 < dy < signal_dy and abs(dx) < dx_tolerance
            else:  # Signal above
                is_between = signal_dy < dy < 0 and abs(dx) < dx_tolerance
        
        if is_between:
            distance = ((coord_cx - haltepunkt_cx)**2 + (coord_cy - haltepunkt_cy)**2) ** 0.5
            if distance < min_coord_dist:
                min_coord_dist = distance
                nearest_coord = coord_det
    
    result = {
        'signal': nearest_signal['text'],
        'signal_det': nearest_signal['det'],  #  ADD THIS
        'coordinate': None
    }
    
    if nearest_coord:
        # Get coordinate text from the detection
        coord_text = nearest_coord.get('text', '')
        result['coordinate'] = coord_text

        if debug:
            position = "below" if (nearest_signal.get('dy_local', nearest_signal.get('dy', 0)) > 0) else "above"
            print(f"→ Signal '{result['signal']}' {position}, Coordinate '{coord_text}' in between")
    else:
        if debug:
            position = "below" if (nearest_signal.get('dy_local', nearest_signal.get('dy', 0)) > 0) else "above"
            print(f"→ Signal '{result['signal']}' {position}, No coordinate in between")
    
    return result


def link_isolierstoss_fallback(anchor, coords, used_coord_ids, max_radius=300):
    """
    Fallback linking for isolierstoß: search in all directions for unlinked coordinates.

    This is used when the standard linking (mode="above") fails.
    Searches for the nearest coordinate that is NOT already linked to another anchor.

    Args:
        anchor: The isolierstoß detection dict
        coords: List of all coordinate detections
        used_coord_ids: Set of coordinate IDs already linked
        max_radius: Maximum search radius in pixels (default 300px ≈ 15mm at DPI=500)

    Returns:
        coordinate dict if found, else None
    """
    anchor_cx = anchor["cx"]
    anchor_cy = anchor["cy"]

    if debug_angle:
        print(f"\nISOLIERSTOSS FALLBACK: Searching all around for unlinked coordinates")
        print(f"Anchor position: ({anchor_cx:.0f}, {anchor_cy:.0f})")
        print(f"Max radius: {max_radius}px")

    # Filter to unlinked coordinates only
    # Use row_id if available (for database-backed coords), fallback to id() for runtime objects
    available_coords = [c for c in coords if c.get('row_id', id(c)) not in used_coord_ids]

    if debug_angle:
        print(f"Total coordinates: {len(coords)}")
        print(f"Already linked: {len(coords) - len(available_coords)}")
        print(f"Available (unlinked): {len(available_coords)}")

    if not available_coords:
        if debug_angle:
            print(f"No unlinked coordinates available")
        return None

    # Find nearest unlinked coordinate within radius
    best_coord = None
    best_distance = float('inf')

    for c in available_coords:
        coord_cx = c["cx"]
        coord_cy = c["cy"]

        # Calculate Euclidean distance
        dx = coord_cx - anchor_cx
        dy = coord_cy - anchor_cy
        distance = math.sqrt(dx**2 + dy**2)

        if distance <= max_radius and distance < best_distance:
            best_distance = distance
            best_coord = c

            if debug_angle:
                coord_text = c.get('text', '?')
                angle = math.degrees(math.atan2(dy, dx))
                print(f"→ Candidate: '{coord_text}' at distance={distance:.1f}px, angle={angle:.1f}°")

    if best_coord:
        if debug_angle:
            coord_text = best_coord.get('text', '?')
            print(f"FOUND: Nearest unlinked coordinate '{coord_text}' at {best_distance:.1f}px")
    else:
        if debug_angle:
            print(f"No unlinked coordinates within {max_radius}px radius")

    return best_coord


def parse_coord(text: str, config: 'LayoutConfig' = None):
    """Parse coordinate text into float value and optional GI/GL identifier.

    Args:
        text: Raw text to parse
        config: LayoutConfig with validation.coordinate_re (optional)
    """
    original_text = text
    s = (text or "").strip().replace(" ", "")

    # Remove trailing single letters (common OCR error)
    s = re.sub(r'[a-zA-Z]$', '', s)

    # Get debug flag from config or use module default
    debug = config.debug_angle_routing if config is not None else debug_angle

    #  ONLY print if debug_angle
    if debug and text and text != s:
        print(f"[parse_coord] Input: '{original_text}' → After cleaning: '{s}'")

    # Use config's regex or fall back to module default
    coord_regex = config.validation.coordinate_re if config is not None else COORD_RE
    if coord_regex is None:
        return None, None

    m = coord_regex.match(s)
    if not m:
        #  ONLY print if debug_angle
        if debug and text:
            print(f"[parse_coord] NO MATCH: '{s}' (COORD_RE pattern failed)")
        return None, None

    # Use configurable decimal separator (German uses comma, others may use dot)
    if config is not None and hasattr(config.validation, 'decimal_separator_input'):
        input_sep = config.validation.decimal_separator_input
        output_sep = config.validation.decimal_separator_output
    else:
        input_sep = ","  # Default: German format
        output_sep = "."
    val = m.group(1).replace(input_sep, output_sep)
    try:
        f = float(val)
    except:
        f = None
        if debug:
            print(f"[parse_coord] FLOAT CONVERSION FAILED: '{val}'")

    gi_gl = m.group(2) if len(m.groups()) > 1 else None

    #  ONLY print if debug_angle
    if debug and text:
        print(f"[parse_coord] Parsed: '{original_text}' → value={f}, gi_gl={gi_gl}")

    return f, gi_gl
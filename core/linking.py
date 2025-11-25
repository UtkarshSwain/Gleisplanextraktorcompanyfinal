from typing import Dict, List, Optional, Tuple
import math
import re
import numpy as np
from config import LINK_RULES, COORD_RE, DEBUG_ANGLE_ROUTING
from utils.helpers import _is_cardinal
# ====================================================================================
# NAME WINDOWS + LINKING (unchanged from Code 1)
# ============================================================================

NAME_RULES_EXTRA = {
    "gm_block": dict(inside=True, right=True, below=True),
    "weichen_block": dict(inside=True, right=True, below=True),
    "prellblock": dict(inside=True, right=True, below=True),
    "gks_gesteuert": dict(inside=True, left=True, right=True, below=True),
    "gks_festkodiert": dict(inside=True, left=True, right=True, below=True),
    "signal": dict(left=True, right=True, below=True, above=True),
}

def name_windows_for(anchor: dict, img_shape: Tuple[int, int, int], mode: str):
    H, W = img_shape[:2]
    x1, y1, x2, y2 = anchor["x1"], anchor["y1"], anchor["x2"], anchor["y2"]
    aw, ah = anchor["w"], anchor["h"]

    if anchor["name"] == "signal":
        dy = int(2.2 * ah)
        dx = int(2.4 * aw)
    else:
        dy = int(1.6 * ah)
        dx = int(1.0 * aw)

    win = []
    hints = NAME_RULES_EXTRA.get(anchor["name"], {})

    if hints.get("inside", False):
        ix1 = x1 + int(0.10 * aw)
        iy1 = y1 + int(0.10 * ah)
        ix2 = x2 - int(0.10 * aw)
        iy2 = y2 - int(0.10 * ah)
        if ix2 > ix1 and iy2 > iy1:
            win.append((ix1, iy1, ix2, iy2))

    if hints.get("right", False):
        rx1, ry1 = x2, max(0, y1 - int(0.6 * ah))
        rx2, ry2 = min(W, x2 + int(2.5 * aw)), min(H, y2 + int(0.6 * ah))
        if rx2 > rx1 and ry2 > ry1:
            win.append((rx1, ry1, rx2, ry2))

    if hints.get("left", False):
        lx1, ly1 = max(0, x1 - int(4.0 * aw)), max(0, y1 - int(0.6 * ah))
        lx2, ly2 = x1, min(H, y2 + int(0.6 * ah))
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
        sx1, sy1 = x2, max(0, y1 - int(0.3 * ah))
        sx2, sy2 = min(W, x2 + int(0.9 * aw)), min(H, y2 + int(0.3 * ah))
        if sx2 > sx1 and sy2 > sy1:
            win.append((sx1, sy1, sx2, sy2))

    if anchor["name"] == "signal":
        rx1 = x2
        ry1 = max(0, y1 - int(ah))
        rx2 = min(W, x2 + int(5.0 * aw))
        ry2 = min(H, y2 + int(ah))
        if rx2 > rx1 and ry2 > ry1:
            win.append((rx1, ry1, rx2, ry2))
        bx1 = max(0, x1 - int(2 * aw))
        by1 = y2
        bx2 = min(W, x2 + int(2 * aw))
        by2 = min(H, y2 + int(5.0 * ah))
        if by2 > by1:
            win.append((bx1, by1, bx2, by2))
        lx1 = max(0, x1 - int(5.0 * aw))
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
    
    # ✅ Convert RAW angle to radians for rotation matrix
    angle_rad = math.radians(angle_raw)
    
    # ✅ Rotate global vector to anchor's local coordinate system
    # Note: We use negative angle to rotate TO local coords (inverse rotation)
    dx_local = dx_global * math.cos(-angle_rad) - dy_global * math.sin(-angle_rad)
    dy_local = dx_global * math.sin(-angle_rad) + dy_global * math.cos(-angle_rad)
    
    # Return absolute distances
    return abs(dx_local), abs(dy_local)


def _check_direction(anchor, coord, mode, is_angular, angle_raw, tilted_ok):
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
        # ✅ Use oriented direction for angular boxes (with RAW angle)
        return _check_oriented_direction(anchor, coord, mode, angle_raw)
    else:
        # ✅ Use axis-aligned direction for cardinal boxes
        return _check_axis_aligned_direction(anchor, coord, mode)


def _check_oriented_direction(anchor, coord, mode, angle_raw):
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
    
    # ✅ Convert to anchor's local coordinate system using RAW angle
    angle_rad = math.radians(angle_raw)
    
    # Transform to local coordinates (inverse rotation)
    dx_local = dx_global * math.cos(-angle_rad) - dy_global * math.sin(-angle_rad)
    dy_local = dx_global * math.sin(-angle_rad) + dy_global * math.cos(-angle_rad)
    
    if DEBUG_ANGLE_ROUTING:
        print(f"      Oriented: dx_local={dx_local:.1f}, dy_local={dy_local:.1f}")
    
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


def _check_axis_aligned_direction(anchor, coord, mode):
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
        # ✅ FIXED: More lenient "right" check
        # Consider "right" if coordinate's LEFT edge is at or past anchor's RIGHT edge
        # OR if coordinate's right edge overlaps with anchor's right half
        # This handles side-by-side placements like "PB | 3,6223"
        
        is_to_right = coord["x1"] >= anchor["x2"] - 0.3 * anchor["w"]  # Allows slight overlap
        is_below = coord["cy"] > anchor["cy"] + 0.3 * anchor["h"]  # Must be clearly below
        
        if DEBUG_ANGLE_ROUTING:
            print(f"      right_or_below: is_to_right={is_to_right} "
                  f"(coord_x1={coord['x1']:.0f} vs anchor_x2-margin={anchor['x2'] - 0.3*anchor['w']:.0f}), "
                  f"is_below={is_below} (coord_cy={coord['cy']:.0f} vs anchor_cy+margin={anchor['cy']+0.3*anchor['h']:.0f})")
        
        return is_to_right or is_below
    
    return True


def link_anchor_to_coord(anchor, coords, learned_patterns=None):
    """
    Link anchor to coordinate with ANGLE-AWARE spatial relationships
    and CLASS-SPECIFIC horizontal tolerance.
    
    IMPROVED: Better angular linking with Euclidean distance priority
    """
    dy_max_base = 1.6 * anchor["h"]
    rule = LINK_RULES.get(anchor["name"], {})
    mode = rule.get("mode", "either")
    tight = rule.get("tight", False)
    tilted_ok = rule.get("tilted_ok", False)
    
    # Class-specific parameters
    dx_multiplier = rule.get("dx_multiplier", 1.0)
    dy_multiplier = rule.get("dy_multiplier", 1.0)
    prefer_horizontal = rule.get("prefer_horizontal", False)
    search_left = rule.get("search_left", False)
    
    # Apply dy_multiplier
    dy_max = dy_max_base * dy_multiplier
    
    # Get angles
    anchor_angle_norm = float(anchor.get("angle", 0.0))
    anchor_angle_raw = float(anchor.get("angle_raw", anchor_angle_norm))
    
    is_cardinal_box = _is_cardinal(anchor_angle_norm)
    is_angular = not is_cardinal_box
    
    # ✅ ONLY print if DEBUG_ANGLE_ROUTING is True
    anchor_text = anchor.get("text", anchor.get("anchor_text", ""))
    if DEBUG_ANGLE_ROUTING:
        print(f"\n🔗 LINKING {anchor['name'].upper()} '{anchor_text}': raw={anchor_angle_raw:.1f}° norm={anchor_angle_norm:.1f}° "
              f"cardinal={is_cardinal_box} mode={mode} dx_mult={dx_multiplier} dy_mult={dy_multiplier}")
        print(f"   Anchor position: cx={anchor['cx']:.1f}, cy={anchor['cy']:.1f}")
        print(f"   Searching in {len(coords)} coordinates...")
    
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
            
            if DEBUG_ANGLE_ROUTING:
                coord_text = c.get('text', c.get('coord_text', '?'))
                print(f"   Coord '{coord_text}': oriented dx={dx:.1f} dy={dy:.1f} euclidean={dist_euclidean:.1f}")
        else:
            # Axis-aligned
            dx = abs(c["cx"] - anchor["cx"])
            dy = abs(c["cy"] - anchor["cy"])
            dist_euclidean = math.sqrt(dx**2 + dy**2)
            
            if DEBUG_ANGLE_ROUTING:
                coord_text = c.get('text', c.get('coord_text', '?'))
                print(f"   Coord '{coord_text}': axis-aligned dx={dx:.1f} dy={dy:.1f} euclidean={dist_euclidean:.1f}")
                print(f"      Coord position: cx={c['cx']:.1f}, cy={c['cy']:.1f}")
        
        # Vertical distance check
        if dy > dy_max:
            if DEBUG_ANGLE_ROUTING:
                print(f"      → SKIP: dy={dy:.1f} > dy_max={dy_max:.1f}")
            continue
        
        # Directional check
        ok_dir = _check_direction(anchor, c, mode, is_angular, anchor_angle_raw, tilted_ok)
        
        if not ok_dir:
            if DEBUG_ANGLE_ROUTING:
                print(f"      → SKIP: wrong direction (mode={mode})")
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
                if DEBUG_ANGLE_ROUTING:
                    print(f"      → LEFT-SIDE BONUS: dx_max={dx_max:.1f}")
        
        if dx > dx_max:
            if DEBUG_ANGLE_ROUTING:
                print(f"      → SKIP: dx={dx:.1f} > dx_max={dx_max:.1f}")
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
        
        if DEBUG_ANGLE_ROUTING:
            print(f"      → CANDIDATE: score={score} xo={xo:.1f}")
        
        if score < best_score:
            best_score, best = score, c
            if DEBUG_ANGLE_ROUTING:
                print(f"      → NEW BEST!")
    
    # ✅ FINAL DEBUG - only if DEBUG_ANGLE_ROUTING
    if DEBUG_ANGLE_ROUTING:
        if best:
            print(f"   ✅ LINKED: {best.get('text', best.get('coord_text', '?'))}")
        else:
            print(f"   ❌ NO MATCH")
    
    # Adaptive fallback
    if best is None and learned_patterns and anchor["name"] in learned_patterns:
        patterns = learned_patterns[anchor["name"]]
        
        if len(patterns) >= 2:
            # ✅ ONLY print if DEBUG_ANGLE_ROUTING
            if DEBUG_ANGLE_ROUTING:
                print(f"\n🔄 ADAPTIVE SEARCH for {anchor['name']}: {len(patterns)} patterns learned")
            
            avg_dx = sum(p[0] for p in patterns) / len(patterns)
            avg_dy = sum(p[1] for p in patterns) / len(patterns)
            std_dx = (sum((p[0] - avg_dx)**2 for p in patterns) / len(patterns))**0.5 if len(patterns) > 1 else 100
            std_dy = (sum((p[1] - avg_dy)**2 for p in patterns) / len(patterns))**0.5 if len(patterns) > 1 else 50
            
            if DEBUG_ANGLE_ROUTING:
                print(f"   Pattern: dx={avg_dx:.1f}±{std_dx:.1f}, dy={avg_dy:.1f}±{std_dy:.1f}")
            
            search_dx = max(3 * std_dx, 150)
            search_dy = max(3 * std_dy, 80)
            
            adaptive_candidates = []
            for c in coords:
                dx_offset = c["cx"] - anchor["cx"]
                dy_offset = c["cy"] - anchor["cy"]
                
                if abs(dx_offset - avg_dx) < search_dx and abs(dy_offset - avg_dy) < search_dy:
                    pattern_distance = ((dx_offset - avg_dx)**2 + (dy_offset - avg_dy)**2)**0.5
                    adaptive_candidates.append((pattern_distance, c))
                    
                    if DEBUG_ANGLE_ROUTING:
                        coord_text = c.get('text', c.get('coord_text', '?'))
                        print(f"   Adaptive candidate: '{coord_text}' offset=({dx_offset:.1f}, {dy_offset:.1f}) dist={pattern_distance:.1f}")
            
            if adaptive_candidates:
                adaptive_candidates.sort(key=lambda x: x[0])
                best = adaptive_candidates[0][1]
                if DEBUG_ANGLE_ROUTING:
                    best_text = best.get('text', best.get('coord_text', '?'))
                    print(f"   ✅ ADAPTIVE MATCH: '{best_text}'")
    
    return best

def link_haltetafel_to_gks(haltetafel_det, gks_dets, coords, gks_coord_map,
                           max_distance=250,  # ✅ Increased from 150
                           dy_tolerance=100,   # ✅ Increased from 80
                           dx_tolerance=300):  # ✅ Increased from 100
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
        
    Returns:
        coordinate dict if found via GKS, else None
    """
    haltetafel_cx = (haltetafel_det["x1"] + haltetafel_det["x2"]) / 2
    haltetafel_cy = (haltetafel_det["y1"] + haltetafel_det["y2"]) / 2
    
    if DEBUG_ANGLE_ROUTING:
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
        
        if DEBUG_ANGLE_ROUTING:
            print(f"      GKS at ({gks_cx:.0f}, {gks_cy:.0f}): dx={dx:.0f}, dy={dy:.0f}, dist={distance:.0f}")
        
        # Check if haltetafel is touching/near GKS
        if distance < max_distance and dx < dx_tolerance and dy < dy_tolerance:
            if distance < min_distance:
                min_distance = distance
                nearest_gks = gks
    
    if not nearest_gks:
        if DEBUG_ANGLE_ROUTING:
            print(f"      → No nearby GKS found")
        return None
    
    # Get GKS's linked coordinate from the map
    gks_id = id(nearest_gks)
    gks_coord = gks_coord_map.get(gks_id)
    
    if DEBUG_ANGLE_ROUTING:
        gks_text = nearest_gks.get('text', '?')
        if gks_coord:
            coord_text = gks_coord.get('text', '?')
            print(f"      ✅ Found GKS '{gks_text}' with coordinate '{coord_text}'")
        else:
            print(f"      ⚠️ Found GKS '{gks_text}' but it has NO coordinate")
    
    return gks_coord

def detect_fahrtrichtung(signal_det, gks_dets, 
                        max_distance=250,
                        dy_min=30,             
                        dy_max=200,
                        dx_tolerance_left=120,
                        dx_tolerance_right=120,
                        angle_tolerance=20):  # NEW: Angle matching tolerance
    """
    Determine Fahrtrichtung (A or B) based on GKS box position relative to signal.
    Supports both HORIZONTAL and ANGULAR (tilted) signals.
    
    Parameters (all in PIXELS at DPI=500):
        max_distance: 250px ≈ 12.7mm - Maximum search radius
        dy_min: 30px ≈ 1.5mm - Minimum vertical separation
        dy_max: 200px ≈ 10mm - Maximum vertical separation
        dx_tolerance_left: 120px - How far left (-x) GKS can be
        dx_tolerance_right: 120px - How far right (+x) GKS can be
        angle_tolerance: 20° - Max angle difference for parallel detection
    
    Returns:
        "A", "B", or None
    """
    # Skip signals starting with "V"
    signal_text = signal_det.get("text", "")
    if signal_text.startswith("V"):
        return None
    
    # Get signal angle (normalized)
    signal_angle = float(signal_det.get("angle", 0.0))
    signal_angle_raw = float(signal_det.get("angle_raw", signal_angle))
    
    # Check if signal is angular (tilted > 15° from cardinal)
    is_angular_signal = abs(signal_angle) > 15.0
    
    # Signal center point
    signal_cx = (signal_det["x1"] + signal_det["x2"]) / 2
    signal_cy = (signal_det["y1"] + signal_det["y2"]) / 2
    
    # Find nearest GKS box within max_distance
    nearest_gks = None
    min_distance = float('inf')
    
    for gks in gks_dets:
        gks_cx = (gks["x1"] + gks["x2"]) / 2
        gks_cy = (gks["y1"] + gks["y2"]) / 2
        
        dx = gks_cx - signal_cx
        dy = gks_cy - signal_cy
        distance = (dx**2 + dy**2) ** 0.5
        
        # For angular signals, also check angle alignment
        if is_angular_signal:
            gks_angle = float(gks.get("angle", 0.0))
            angle_diff = abs(signal_angle - gks_angle)
            
            # Normalize angle difference to [0, 180]
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            # Skip GKS if not parallel (angles don't match)
            if angle_diff > angle_tolerance:
                if DEBUG_ANGLE_ROUTING:
                    print(f"   [Skip GKS] Angle mismatch: signal={signal_angle:.1f}°, gks={gks_angle:.1f}°, diff={angle_diff:.1f}°")
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
    
    if not nearest_gks:
        if DEBUG_ANGLE_ROUTING:
            mode = "ANGULAR" if is_angular_signal else "HORIZONTAL"
            print(f"   [{mode}] Signal '{signal_text}' (θ={signal_angle:.1f}°) → No matching GKS within {max_distance}px")
        return None
    
    dx = nearest_gks['dx']
    dy = nearest_gks['dy']
    gks_angle = float(nearest_gks['angle'])
    
    if DEBUG_ANGLE_ROUTING:
        mode = "ANGULAR" if is_angular_signal else "HORIZONTAL"
        angle_info = f", signal_θ={signal_angle:.1f}°, gks_θ={gks_angle:.1f}°" if is_angular_signal else ""
        print(f"   [{mode}] Signal '{signal_text}' → GKS: dx={dx:.1f}px, dy={dy:.1f}px, dist={nearest_gks['distance']:.1f}px{angle_info}")
    
    # ============================================================================
    # ANGULAR SIGNALS: Use rotated coordinate system
    # ============================================================================
    if is_angular_signal:
        # Transform dx/dy to signal's local coordinate system
        angle_rad = math.radians(signal_angle_raw)
        
        # Rotate the offset vector to signal's frame
        # dx_local = along signal's width direction
        # dy_local = perpendicular to signal (positive = "below" in rotated frame)
        dx_local = dx * math.cos(-angle_rad) - dy * math.sin(-angle_rad)
        dy_local = dx * math.sin(-angle_rad) + dy * math.cos(-angle_rad)
        
        if DEBUG_ANGLE_ROUTING:
            print(f"       Rotated coords: dx_local={dx_local:.1f}px, dy_local={dy_local:.1f}px")
        
        # B Direction: GKS is "below" in rotated frame (positive dy_local)
        if dy_min < dy_local < dy_max and -dx_tolerance_left < dx_local < dx_tolerance_right:
            if DEBUG_ANGLE_ROUTING:
                print(f"   → Fahrtrichtung: B (GKS below in rotated frame)")
            return "B"
        
        # A Direction: GKS is "above" in rotated frame (negative dy_local)
        if -dy_max < dy_local < -dy_min and -dx_tolerance_right < dx_local < dx_tolerance_left:
            if DEBUG_ANGLE_ROUTING:
                print(f"   → Fahrtrichtung: A (GKS above in rotated frame)")
            return "A"
    
    # ============================================================================
    # HORIZONTAL SIGNALS: Use standard axis-aligned coordinates
    # ============================================================================
    else:
        # B Direction: GKS is BELOW (positive dy) and in reasonable horizontal range
        if dy_min < dy < dy_max and -dx_tolerance_left < dx < dx_tolerance_right:
            if DEBUG_ANGLE_ROUTING:
                print(f"   → Fahrtrichtung: B (GKS below)")
            return "B"
        
        # A Direction: GKS is ABOVE (negative dy) and in reasonable horizontal range
        if -dy_max < dy < -dy_min and -dx_tolerance_right < dx < dx_tolerance_left:
            if DEBUG_ANGLE_ROUTING:
                print(f"   → Fahrtrichtung: A (GKS above)")
            return "A"
    
    if DEBUG_ANGLE_ROUTING:
        print(f"   → Fahrtrichtung: Undetermined (outside range)")
    
    return None

def detect_haltepunkt_signal_group(haltepunkt_det, signal_dets, coord_dets,
                                     max_distance=250,
                                     dy_signal_min=30,
                                     dy_signal_max=200,
                                     dy_coord_min=20,
                                     dy_coord_max=150,
                                     dx_tolerance=100):
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
    
    Returns:
        dict with 'signal': signal_text, 'coordinate': coord_text, or None
    """
    # Get haltepunkt angle and position
    haltepunkt_angle = float(haltepunkt_det.get("angle", 0.0))
    haltepunkt_angle_raw = float(haltepunkt_det.get("angle_raw", haltepunkt_angle))
    is_angular = abs(haltepunkt_angle) > 15.0
    
    haltepunkt_cx = (haltepunkt_det["x1"] + haltepunkt_det["x2"]) / 2
    haltepunkt_cy = (haltepunkt_det["y1"] + haltepunkt_det["y2"]) / 2
    
    if DEBUG_ANGLE_ROUTING:
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
            if angle_diff > 20:
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
        if DEBUG_ANGLE_ROUTING:
            print(f"      → No signal found")
        return None
    
    # Find coordinate in between haltepunkt and signal
    signal_det = nearest_signal['det']
    signal_cy = (signal_det["y1"] + signal_det["y2"]) / 2
    
    nearest_coord = None
    min_coord_dist = float('inf')
    
    for coord_det in coord_dets:
        # ✅ FIX: Handle both formats (detection dict vs processed dict)
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
        'coordinate': None
    }
    
    if nearest_coord:
        # Get coordinate text from the detection
        coord_text = nearest_coord.get('text', '')
        result['coordinate'] = coord_text
        
        if DEBUG_ANGLE_ROUTING:
            position = "below" if (nearest_signal.get('dy_local', nearest_signal.get('dy', 0)) > 0) else "above"
            print(f"      → Signal '{result['signal']}' {position}, Coordinate '{coord_text}' in between")
    else:
        if DEBUG_ANGLE_ROUTING:
            position = "below" if (nearest_signal.get('dy_local', nearest_signal.get('dy', 0)) > 0) else "above"
            print(f"      → Signal '{result['signal']}' {position}, No coordinate in between")
    
    return result

def merge_duplicate_signals(all_rows: List[dict]) -> List[dict]:
    """
    No longer hides signals - all signals remain visible.
    Just reassigns row_ids sequentially.
    """
    if DEBUG_ANGLE_ROUTING:
        print(f"\n📊 Processing {len(all_rows)} total rows (no hiding)")
    
    # Just reassign row_ids sequentially
    for i, row in enumerate(all_rows):
        row['row_id'] = i
    
    return all_rows

def parse_coord(text: str):
    """Parse coordinate text into float value and optional GI/GL identifier."""
    original_text = text
    s = (text or "").strip().replace(" ", "")
    
    # Remove trailing single letters (common OCR error)
    s = re.sub(r'[a-zA-Z]$', '', s)
    
    # ✅ ONLY print if DEBUG_ANGLE_ROUTING
    if DEBUG_ANGLE_ROUTING and text and text != s:
        print(f"   [parse_coord] Input: '{original_text}' → After cleaning: '{s}'")
    
    m = COORD_RE.match(s)
    if not m:
        # ✅ ONLY print if DEBUG_ANGLE_ROUTING
        if DEBUG_ANGLE_ROUTING and text:
            print(f"   [parse_coord] ❌ NO MATCH: '{s}' (COORD_RE pattern failed)")
        return None, None
    
    val = m.group(1).replace(",", ".")
    try:
        f = float(val)
    except:
        f = None
        if DEBUG_ANGLE_ROUTING:
            print(f"   [parse_coord] ❌ FLOAT CONVERSION FAILED: '{val}'")
    
    gi_gl = m.group(2) if len(m.groups()) > 1 else None
    
    # ✅ ONLY print if DEBUG_ANGLE_ROUTING
    if DEBUG_ANGLE_ROUTING and text:
        print(f"   [parse_coord] ✅ Parsed: '{original_text}' → value={f}, gi_gl={gi_gl}")
    
    return f, gi_gl
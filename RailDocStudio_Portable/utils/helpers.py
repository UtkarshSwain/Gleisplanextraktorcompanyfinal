"""
Helpers - Hilfsfunktionen fuer Gleisplanerkennung

Dieses Modul enthaelt allgemeine Hilfsfunktionen, die von mehreren
Modulen verwendet werden.

Kategorien:
    Qt-Hilfsfunktionen:
        _is_deleted(): Prueft ob Qt-Objekt geloescht wurde

    YOLO-Hilfsfunktionen:
        iou(): Intersection over Union berechnen
        nms(): Non-Maximum Suppression
        color_masks(): Rot/Gelb-Masken extrahieren

    Winkel-Hilfsfunktionen:
        _is_cardinal(): Prueft ob Winkel nahe 0°/90°/180°/270°
        _is_angular(): Prueft ob Winkel deutlich geneigt (>15°)
        _norm_angle(): Normalisiert Winkel auf -45° bis +45°
        get_params_for_angle(): Gibt winkelabhaengige OCR-Parameter

    Konstanten:
        ANGLE_TOL: Toleranz fuer Kardinal-Winkelpruefung (15°)

Abhaengigkeiten:
    cv2, numpy, PyQt5
"""
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional, Any, TYPE_CHECKING
from PyQt5 import QtCore

# Type hint for LayoutConfig without circular import
if TYPE_CHECKING:
    from core.config_models import LayoutConfig

# ============================================================================
# DEBUG UTILITY
# ============================================================================

# Debug flags - module-level defaults
DEBUG_SIGNALS = False
DEBUG_ANGLE_ROUTING = False
DEBUG_OCR = False
DEBUG_LINKING = False
DEBUG_TRACK = False
DEBUG_CUSTOM_SYMBOLS = False
DEBUG_YOLO = False
DEBUG_UI_BBOX = False
DEBUG_COMPARISON = False

# Debug file handle
_DEBUG_FILE = None

def debug_print(category: str, message: str):
    """
    Print debug message to debug.txt if category is enabled.

    Categories: signals, angle_routing, ocr, linking, track, custom_symbols, yolo, ui_bbox, comparison
    """
    global _DEBUG_FILE

    # Check if category is enabled
    flag_name = f"DEBUG_{category.upper()}"
    if not globals().get(flag_name, False):
        return

    # Open file on first use (overwrites previous debug.txt)
    if _DEBUG_FILE is None:
        from paths import get_debug_file_path
        _DEBUG_FILE = open(get_debug_file_path('debug.txt'), 'w', encoding='utf-8')

    _DEBUG_FILE.write(f"[{category.upper()}] {message}\n")
    _DEBUG_FILE.flush()


def configure_debug_from_config(config: 'LayoutConfig') -> None:
    """Configure debug flags from a LayoutConfig object."""
    global DEBUG_SIGNALS, DEBUG_ANGLE_ROUTING, DEBUG_OCR, DEBUG_LINKING
    global DEBUG_TRACK, DEBUG_CUSTOM_SYMBOLS, DEBUG_YOLO, DEBUG_UI_BBOX, DEBUG_COMPARISON

    if config is None:
        return

    DEBUG_SIGNALS = getattr(config, 'debug_signals', False)
    DEBUG_ANGLE_ROUTING = getattr(config, 'debug_angle_routing', False)
    DEBUG_OCR = getattr(config, 'debug_ocr', False)
    DEBUG_LINKING = getattr(config, 'debug_linking', False)
    DEBUG_TRACK = getattr(config, 'debug_track', False)
    DEBUG_CUSTOM_SYMBOLS = getattr(config, 'debug_custom_symbols', False)
    DEBUG_YOLO = getattr(config, 'debug_yolo', False)
    DEBUG_UI_BBOX = getattr(config, 'debug_ui_bbox', False)
    DEBUG_COMPARISON = getattr(config, 'debug_comparison', False)


# ============================================================================
# DEFAULT PARAMETERS
# ============================================================================

# Default parameters for backward compatibility (when config is not passed)
_DEFAULT_CARDINAL_PARAMS = {
    "detection_padding": {
        "coordinate": 4, "signal": 4, "weichenende": 8, "haltetafel": 4,
        "prellbock": 4, "gks_gesteuert": 8, "gks_festkodiert": 8,
        "weichengruppenende": 4, "weichen_block": 2,
    },
    "expansion_factor": {
        "coordinate": (1.0, 1.0), "signal": (1.0, 1.0),
        "gks_gesteuert": (0.6, 0.6), "gks_festkodiert": (0.6, 0.6),
        "weichen_block": (1.1, 1.0),
    }
}

_DEFAULT_ANGULAR_PARAMS = {
    "detection_padding": {
        "coordinate": 4, "signal": 8, "weichenende": 4, "haltetafel": 4,
        "prellbock": 4, "gks_gesteuert": 6, "gks_festkodiert": 6,
    },
    "expansion_factor": {
        "coordinate": (1.0, 1.0), "signal": (1.0, 1.05),
        "gks_gesteuert": (0.75, 0.75), "gks_festkodiert": (0.75, 0.75),
    }
}

try:
    import sip
except Exception:
    sip = None

def _is_deleted(qobj: Optional[QtCore.QObject]) -> bool:
    """Check if Qt object has been deleted."""
    if qobj is None:
        return True
    if sip is None:
        return False
    try:
        return sip.isdeleted(qobj)
    except Exception:
        return False
# ============================================================================
#YOLO HELPERS
# ============================================================================
def iou(a, b):
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0

def nms(boxes: List[Tuple[int, int, int, int]], scores: List[float], thr=0.5):
    order = np.argsort(scores)[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        remove = [0]
        for j in range(1, order.size):
            if iou(boxes[i], boxes[order[j]]) >= thr:
                remove.append(j)
        order = np.delete(order, remove)
    return keep

def color_masks(bgr: np.ndarray):
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    red1 = cv2.inRange(hsv, (0, 120, 120), (10, 255, 255))
    red2 = cv2.inRange(hsv, (170, 120, 120), (180, 255, 255))
    red = cv2.bitwise_or(red1, red2)
    yel = cv2.inRange(hsv, (20, 120, 140), (40, 255, 255))
    k = np.ones((3, 3), np.uint8)
    red = cv2.morphologyEx(cv2.morphologyEx(red, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    yel = cv2.morphologyEx(cv2.morphologyEx(yel, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    return red, yel

def box_color(mask_red, mask_yel, x1, y1, x2, y2, thr=0.20):
    area = max(1, (x2 - x1) * (y2 - y1))
    r = (mask_red[y1:y2, x1:x2] > 0).sum() / area
    y = (mask_yel[y1:y2, x1:x2] > 0).sum() / area
    if r >= thr:
        return "red"
    if y >= thr:
        return "yellow"
    return "none"


# ============================================================================
# ANTWERP DETECTION HELPERS
# ============================================================================

def nms_prefer_larger(boxes: List[Tuple[int, int, int, int]], scores: List[float],
                      areas: List[float], thr: float = 0.5) -> List[int]:
    """
    NMS that prefers larger boxes - sort by area first, then confidence.

    Args:
        boxes: List of (x1, y1, x2, y2) bounding boxes
        scores: List of confidence scores
        areas: List of box areas
        thr: IoU threshold for suppression

    Returns:
        List of indices to keep
    """
    if len(boxes) == 0:
        return []

    boxes_arr = np.array(boxes)
    scores_arr = np.array(scores)
    areas_arr = np.array(areas)

    # Sort by area (descending), then by score (descending)
    order = np.lexsort((scores_arr, areas_arr))[::-1]
    keep = []

    while order.size > 0:
        i = order[0]
        keep.append(i)
        remove = [0]

        for j in range(1, order.size):
            idx_j = order[j]
            if iou(boxes[i], boxes[idx_j]) >= thr:
                # Prefer larger box - check if candidate is >15% larger
                if areas_arr[idx_j] > areas_arr[i] * 1.15:
                    keep[-1] = idx_j  # Replace with larger
                remove.append(j)

        order = np.delete(order, remove)

    return keep


def filter_contained_boxes(detections: List[Dict], threshold: float = 0.80) -> List[Dict]:
    """
    Remove boxes that are >=threshold contained within larger boxes.

    Args:
        detections: List of detection dicts with x1,y1,x2,y2 keys
        threshold: Containment ratio threshold (0.80 = 80% contained)

    Returns:
        Filtered list of detections
    """
    if not detections:
        return detections

    def get_area(d: Dict) -> float:
        return (d['x2'] - d['x1']) * (d['y2'] - d['y1'])

    # Sort by area (largest first)
    sorted_dets = sorted(detections, key=get_area, reverse=True)
    keep = []

    for det in sorted_dets:
        is_contained = False
        det_area = get_area(det)

        for kept in keep:
            # Calculate intersection
            ix1 = max(det['x1'], kept['x1'])
            iy1 = max(det['y1'], kept['y1'])
            ix2 = min(det['x2'], kept['x2'])
            iy2 = min(det['y2'], kept['y2'])

            if ix1 < ix2 and iy1 < iy2:
                inter_area = (ix2 - ix1) * (iy2 - iy1)
                containment = inter_area / det_area if det_area > 0 else 0

                if containment >= threshold:
                    is_contained = True
                    break

        if not is_contained:
            keep.append(det)

    return keep


def filter_by_halo(detections: List[Dict], tile_x: int, tile_y: int,
                   tile_size: int, halo_ratio: float, conf_boost: float) -> List[Dict]:
    """
    Filter edge detections using centroid-based halo logic.

    Removes detections at tile edges UNLESS they have high confidence.

    Args:
        detections: List of detection dicts with x1,y1,x2,y2,conf keys
        tile_x: Tile origin X coordinate
        tile_y: Tile origin Y coordinate
        tile_size: Size of tile in pixels
        halo_ratio: Fraction of tile that is halo zone (e.g., 0.12 = 12%)
        conf_boost: Minimum confidence to keep edge detections

    Returns:
        Filtered list of detections
    """
    halo_px = int(tile_size * halo_ratio)
    core_x1 = tile_x + halo_px
    core_y1 = tile_y + halo_px
    core_x2 = tile_x + tile_size - halo_px
    core_y2 = tile_y + tile_size - halo_px

    keep = []
    for det in detections:
        # Get centroid
        cx = (det['x1'] + det['x2']) / 2
        cy = (det['y1'] + det['y2']) / 2

        # In core zone - always keep
        if core_x1 <= cx <= core_x2 and core_y1 <= cy <= core_y2:
            keep.append(det)
        # In halo zone - keep only if high confidence
        elif det.get('conf', 0) >= conf_boost:
            keep.append(det)

    return keep
# ============================================================================
# ANGLE DETECTION HELPERS (IMPROVED)
# ============================================================================

ANGLE_TOL = 12.0    # Degrees: threshold for cardinal vs angular
ANGLE_EPS = 0.15    # Small epsilon for float jitter (0.15° ≈ negligible)
def get_adaptive_padding(det: dict, bgr_color: np.ndarray) -> int:
    """More pad for tiny or blurry boxes; less for large/sharp ones."""
    w = float(det.get("obb_w", det["x2"] - det["x1"]))
    h = float(det.get("obb_h", det["y2"] - det["y1"]))
    min_dim = min(w, h)

    # quick blur probe on the AABB
    try:
        y1, y2 = int(det["y1"]), int(det["y2"])
        x1, x2 = int(det["x1"]), int(det["x2"])
        gray = cv2.cvtColor(bgr_color[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
        blur = cv2.Laplacian(gray, cv2.CV_64F).var()
        if blur < 50:   # very blurry
            return 22
        if blur < 100:  # mildly blurry
            return 16
    except Exception:
        pass

    if min_dim < 30:  return 18
    if min_dim < 60:  return 14
    return 10

def _norm_angle(deg: float) -> float:
    """Map any angle to [0, 360)."""
    a = float(deg) % 360.0
    return a + 360.0 if a < 0 else a

def _dist_to_cardinal(deg: float) -> float:
    """
    Return shortest angular distance to nearest cardinal direction.
    
    Cardinals: 0° (right), 90° (up), 180° (left), 270° (down)
    
    Examples:
        _dist_to_cardinal(-0.2)  → 0.2  (near 0°)
        _dist_to_cardinal(88)    → 2.0  (near 90°)
        _dist_to_cardinal(45)    → 45.0 (equidistant from 0° and 90°)
    """
    a = _norm_angle(deg)
    return min(
        abs(a - t) if abs(a - t) <= 180 else 360 - abs(a - t)
        for t in (0.0, 90.0, 180.0, 270.0)
    )

def _is_near(a: float, tgt: float, tol: float = ANGLE_TOL) -> bool:
    """Check if angle a is within tol degrees of target."""
    a = _norm_angle(a)
    tgt = _norm_angle(tgt)
    d = abs(a - tgt)
    d = min(d, 360.0 - d)
    return d <= tol

def _is_cardinal(deg: float) -> bool:
    """
    Check if NORMALIZED angle is axis-aligned (near 0° after normalization).
    
    After normalization, all cardinal directions map to near 0°.
    Uses small epsilon to handle floating-point jitter.
    """
    return abs(float(deg)) <= (ANGLE_TOL + ANGLE_EPS)

def _is_angular(deg: float) -> bool:
    """Check if NORMALIZED angle is tilted (>15° from 0°)."""
    return not _is_cardinal(deg)



def get_params_for_angle(angle_deg: float, class_name: str, config: 'LayoutConfig' = None) -> Tuple[int, Tuple[float, float]]:
    """
    Return (padding, expansion_factor) based on RAW text orientation.

    Uses RAW angle to distinguish horizontal vs vertical BEFORE dimension swap.

    Args:
        angle_deg: RAW angle from YOLO (in degrees, range [-90, 90])
        class_name: Detection class name
        config: Optional LayoutConfig for parameters (uses defaults if None)

    Returns:
        (padding_px, (expand_x, expand_y))
    """
    # Use config values if provided, otherwise use defaults
    if config is not None:
        cardinal_padding = config.ocr.cardinal_detection_padding
        cardinal_expansion = config.ocr.cardinal_expansion_factor
        angular_padding = config.ocr.angular_detection_padding
        angular_expansion = config.ocr.angular_expansion_factor
    else:
        cardinal_padding = _DEFAULT_CARDINAL_PARAMS["detection_padding"]
        cardinal_expansion = _DEFAULT_CARDINAL_PARAMS["expansion_factor"]
        angular_padding = _DEFAULT_ANGULAR_PARAMS["detection_padding"]
        angular_expansion = _DEFAULT_ANGULAR_PARAMS["expansion_factor"]

    # Normalize to [0, 360) for consistent checking
    a = _norm_angle(angle_deg)

    # Check if near any cardinal direction using RAW angle
    if _is_near(a, 0.0) or _is_near(a, 180.0):
        # Horizontal text
        pad = cardinal_padding.get(class_name, 8)
        exp = cardinal_expansion.get(class_name, (1.0, 1.0))
    elif _is_near(a, 90.0) or _is_near(a, 270.0):
        # Vertical text (also axis-aligned, same large boxes)
        pad = cardinal_padding.get(class_name, 8)
        exp = cardinal_expansion.get(class_name, (1.0, 1.0))
    else:
        # Angular text (tilted)
        pad = angular_padding.get(class_name, 4)
        exp = angular_expansion.get(class_name, (1.0, 1.0))

    return pad, exp
def _debug_angle(prefix: str, det: dict, decision: str, extra: str = "", config: 'LayoutConfig' = None):
    """
    Print angle routing debug info if debug_angle_routing is enabled.

    Args:
        prefix: Context (e.g., "DETECTION", "OCR_COORD", "OCR_SIGNAL")
        det: Detection dictionary with angle info
        decision: What category it was assigned
        extra: Optional extra info
        config: Optional LayoutConfig for debug flag (falls back to global if None)
    """
    # Check debug flag from config or fall back to module-level default
    if config is not None:
        debug_enabled = config.debug_angle_routing
    else:
        debug_enabled = DEBUG_ANGLE_ROUTING

    if not debug_enabled:
        return

    ang_raw = float(det.get("angle_raw", 0.0))
    ang_norm = float(det.get("angle", ang_raw))
    cls_name = det.get("name", det.get("cls", "unknown"))

    dist = _dist_to_cardinal(ang_raw)

    msg = f"[{prefix:12s}] {cls_name:15s} | raw={ang_raw:6.2f}° norm={ang_norm:6.2f}° dist={dist:5.2f}° → {decision:10s}"

    if extra:
        msg += f" | {extra}"

    print(msg)
import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional, Any 
from config import ALIASES, CLASS_REMAP, VERTICAL_PARAMS,HORIZONTAL_PARAMS,ANGULAR_PARAMS 
from typing import Optional
from PyQt5 import QtCore

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
def _alias_name(n: str) -> str:
    return ALIASES.get(n, n)

def canon_name(n: str) -> str:
    n0 = _alias_name(n)
    return CLASS_REMAP.get(n0, n0)
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



def get_params_for_angle(angle_deg: float, class_name: str) -> Tuple[int, Tuple[float, float]]:
    """
    Return (padding, expansion_factor) based on RAW text orientation.
    
    Uses RAW angle to distinguish horizontal vs vertical BEFORE dimension swap.
    
    Args:
        angle_deg: RAW angle from YOLO (in degrees, range [-90, 90])
        class_name: Detection class name
        
    Returns:
        (padding_px, (expand_x, expand_y))
    """
    # Normalize to [0, 360) for consistent checking
    a = _norm_angle(angle_deg)
    
    # Check if near any cardinal direction using RAW angle
    if _is_near(a, 0.0) or _is_near(a, 180.0):
        # Horizontal text
        pad = HORIZONTAL_PARAMS["detection_padding"].get(class_name, 8)
        exp = HORIZONTAL_PARAMS["expansion_factor"].get(class_name, (1.0, 1.0))
    elif _is_near(a, 90.0) or _is_near(a, 270.0):
        # Vertical text (also axis-aligned, same large boxes)
        pad = VERTICAL_PARAMS["detection_padding"].get(class_name, 8)
        exp = VERTICAL_PARAMS["expansion_factor"].get(class_name, (1.0, 1.0))
    else:
        # Angular text (tilted)
        pad = ANGULAR_PARAMS["detection_padding"].get(class_name, 4)
        exp = ANGULAR_PARAMS["expansion_factor"].get(class_name, (1.0, 1.0))
    
    return pad, exp
def _debug_angle(prefix: str, det: dict, decision: str, extra: str = ""):
    """
    Print angle routing debug info if DEBUG_ANGLE_ROUTING is enabled.
    
    Args:
        prefix: Context (e.g., "DETECTION", "OCR_COORD", "OCR_SIGNAL")
        det: Detection dictionary with angle info
        decision: What category it was assigned
        extra: Optional extra info
    """
    from config import DEBUG_ANGLE_ROUTING
    
    if not DEBUG_ANGLE_ROUTING:
        return
    
    ang_raw = float(det.get("angle_raw", 0.0))
    ang_norm = float(det.get("angle", ang_raw))
    cls_name = det.get("name", det.get("cls", "unknown"))
    
    dist = _dist_to_cardinal(ang_raw)
    
    msg = f"[{prefix:12s}] {cls_name:15s} | raw={ang_raw:6.2f}° norm={ang_norm:6.2f}° dist={dist:5.2f}° → {decision:10s}"
    
    if extra:
        msg += f" | {extra}"
    
    print(msg)
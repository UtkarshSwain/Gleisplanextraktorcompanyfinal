"""
Image Processing - Bildverarbeitungsfunktionen fuer Gleisplanerkennung

Dieses Modul enthaelt Hilfsfunktionen fuer die Bildverarbeitung,
insbesondere fuer das Zuschneiden und Transformieren von Erkennungsregionen.

Kernfunktionen:
    perspective_crop_from_det(): Perspektivkorrektur fuer geneigte Texte
    rotated_crop_from_det(): Rotierter Zuschnitt mit Padding
    obb_xywhr_to_polygon(): Konvertiert OBB zu 4-Punkt-Polygon
    parse_weichen_block(): Parst mehrzeiligen Weichenblock-Text

Bildverbesserung:
    _enhance_contrast(): CLAHE Kontrastverbesserung
    _binarize_for_text(): Adaptive Schwellwertbinarisierung
    _remove_long_lines_oriented(): Entfernt Rahmenlinien bei OCR
    _upscale_if_tiny(): Skaliert kleine Symbole hoch

Zuschnittstrategien:
    - Perspektivwarp: Fuer stark geneigte Texte (>15° von Kardinal)
    - Rotierter Zuschnitt: Fuer leicht geneigte oder horizontale Texte
    - Adaptive Raender: Basierend auf Neigungswinkel

Abhaengigkeiten:
    cv2, numpy, PIL
"""
from typing import Tuple, TYPE_CHECKING
import numpy as np
import cv2
from PIL import Image
import math
from PyQt5 import QtCore, QtGui, QtWidgets
from utils.helpers import _dist_to_cardinal

# Type hint for LayoutConfig without circular import
if TYPE_CHECKING:
    from core.config_models import LayoutConfig

# Default zoom size (can be overridden by config)
ZOOM_SIZE = 2048
def parse_weichen_block(text: str) -> dict:
    """
    Parse weichen block text into ID and coordinates.
    
    Example input:
        "WAHR921\\nWA  0.0000(Gl.113)\\nWA  0.0661(Gl.112)"
    
    Returns:
        {
            'id': 'WAHR921',
            'coordinates': ['WA  0.0000(Gl.113)', 'WA  0.0661(Gl.112)']
        }
    """
    if not text:
        return {'id': '', 'coordinates': []}
    
    lines = text.strip().split('\n')
    
    if len(lines) == 0:
        return {'id': '', 'coordinates': []}
    
    # First line is the block ID
    block_id = lines[0].strip()
    
    # Remaining lines are coordinates
    coordinates = [line.strip() for line in lines[1:] if line.strip()]
    
    return {
        'id': block_id,
        'coordinates': coordinates
    }
def obb_xywhr_to_polygon(cx, cy, w, h, theta_rad):
    c = math.cos(theta_rad)
    s = math.sin(theta_rad)
    dx, dy = w / 2.0, h / 2.0
    corners = np.array([[-dx, -dy], [dx, -dy], [dx, dy], [-dx, dy]], dtype=np.float32)
    R = np.array([[c, -s], [s, c]], dtype=np.float32)
    pts = (corners @ R.T) + np.array([cx, cy], dtype=np.float32)
    return pts.astype(np.float32)

def polygon_to_aabb_xyxy(pts):
    xs = pts[:, 0]
    ys = pts[:, 1]
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

def qpolygonf_from_pts(pts):
    return QtGui.QPolygonF([QtCore.QPointF(float(x), float(y)) for x, y in pts])

def _normalize_xywhr(cx: float, cy: float, w: float, h: float, theta_rad: float):
    theta = ((theta_rad + math.pi) % (2 * math.pi)) - math.pi
    if theta > math.pi / 4:
        theta -= math.pi / 2
        w, h = h, w
    elif theta < -math.pi / 4:
        theta += math.pi / 2
        w, h = h, w
    return cx, cy, w, h, theta

def _pil_to_gray_np(pil_img: Image.Image):
    return np.array(pil_img.convert("L"))

def _enhance_contrast(gray: np.ndarray):
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(gray)

def _binarize_for_text(gray: np.ndarray):
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10)

def _invert(img_np: np.ndarray) -> np.ndarray:
    return 255 - img_np

def _upscale_if_tiny(pil_img: Image.Image, min_side=80, scale=2):
    w, h = pil_img.size
    if max(w, h) < min_side:
        return pil_img.resize((w * scale, h * scale), Image.LANCZOS)
    return pil_img

def _deskew_small(pil_img: Image.Image, angles=(-20, -15, -10, -5, 0, 5, 10, 15, 20)):
    best = pil_img
    best_score = -1
    for a in angles:
        r = pil_img.rotate(a, expand=True, fillcolor="white")
        g = _pil_to_gray_np(r)
        proj = np.sum(255 - g, axis=1).astype(np.float32)
        sc = float(np.var(proj))
        if sc > best_score:
            best, best_score = r, sc
    return best

# ============================================================================
# CROPPING STRATEGIES (Code 1 + Code 2)
# ============================================================================

def rotated_crop_pil(page_bgr: np.ndarray, cx: float, cy: float, w: float, h: float,
                     angle_deg: float, pad_px: int = 0) -> Image.Image:
    """
    Simple rotation around center (Code 2 strategy - good for horizontal).
    Rotate local patch only to avoid SHRT_MAX limits.
    """
    H, W = page_bgr.shape[:2]
    bb_w = int(w + 2 * max(32, pad_px + 32))
    bb_h = int(h + 2 * max(32, pad_px + 32))
    x1 = max(0, int(cx - bb_w / 2))
    y1 = max(0, int(cy - bb_h / 2))
    x2 = min(W, int(cx + bb_w / 2))
    y2 = min(H, int(cy + bb_h / 2))
    patch = page_bgr[y1:y2, x1:x2].copy()

    cx_p = cx - x1
    cy_p = cy - y1

    M = cv2.getRotationMatrix2D((cx_p, cy_p), -angle_deg, 1.0)
    cos = abs(M[0, 0])
    sin = abs(M[0, 1])
    h0, w0 = patch.shape[:2]
    new_w = int(h0 * sin + w0 * cos)
    new_h = int(h0 * cos + w0 * sin)
    M[0, 2] += (new_w / 2 - cx_p)
    M[1, 2] += (new_h / 2 - cy_p)

    rot = cv2.warpAffine(patch, M, (new_w, new_h), flags=cv2.INTER_LINEAR,
                         borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))

    x1c = int(new_w / 2 - w / 2) - pad_px
    y1c = int(new_h / 2 - h / 2) - pad_px
    x2c = int(new_w / 2 + w / 2) + pad_px
    y2c = int(new_h / 2 + h / 2) + pad_px
    x1c = max(0, x1c)
    y1c = max(0, y1c)
    x2c = min(new_w, x2c)
    y2c = min(new_h, y2c)
    crop = rot[y1c:y2c, x1c:x2c]
    return Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))


def perspective_crop_from_det(det: dict, page_bgr: np.ndarray, pad: int = 6) -> Image.Image:
    """
    4-point perspective warp (Code 1 strategy - good for angular).
    Best for severely tilted text.
    """
    poly = det.get("poly", None)
    if isinstance(poly, np.ndarray):
        pts = poly.astype(np.float32)
        # Handle flat 1D array [x1,y1,x2,y2,x3,y3,x4,y4] -> reshape to [[x1,y1],...]
        if pts.ndim == 1 and len(pts) == 8:
            pts = pts.reshape(4, 2)
    elif isinstance(poly, (list, tuple)) and len(poly) == 4:
        pts = np.array(poly, dtype=np.float32)
    elif isinstance(poly, (list, tuple)) and len(poly) == 8:
        # Flat list [x1,y1,x2,y2,...] -> reshape to [[x1,y1],...]
        pts = np.array(poly, dtype=np.float32).reshape(4, 2)
    else:
        cx = float(det.get("obb_cx", (det["x1"] + det["x2"]) / 2))
        cy = float(det.get("obb_cy", (det["y1"] + det["y2"]) / 2))
        w = float(det.get("obb_w", det["x2"] - det["x1"]))
        h = float(det.get("obb_h", det["y2"] - det["y1"]))
        #  AFTER (CORRECT - use normalized angle with normalized dimensions):
        ang_deg = float(det.get("angle", det.get("angle_raw", 0.0)))
        pts = obb_xywhr_to_polygon(cx, cy, w, h, math.radians(ang_deg)).astype(np.float32)

    H, W = page_bgr.shape[:2]
    
    # Adaptive margin based on tilt severity
    ang_raw = float(det.get("angle_raw", det.get("angle", 0.0)))
    dist_from_cardinal = _dist_to_cardinal(ang_raw)
    
    if dist_from_cardinal > 35:      # Very tilted
        margin = 96
    elif dist_from_cardinal > 15:    # Moderately tilted
        margin = 64
    else:                            # Nearly cardinal
        margin = 48
    
    x_min = max(0, int(np.floor(pts[:, 0].min())) - margin)
    y_min = max(0, int(np.floor(pts[:, 1].min())) - margin)
    x_max = min(W, int(np.ceil(pts[:, 0].max())) + margin)
    y_max = min(H, int(np.ceil(pts[:, 1].max())) + margin)

    if x_max <= x_min or y_max <= y_min:
        return crop_pil(page_bgr, det["x1"], det["y1"], det["x2"], det["y2"], pad=pad)

    patch = page_bgr[y_min:y_max, x_min:x_max]
    pts_local = pts.copy()
    pts_local[:, 0] -= x_min
    pts_local[:, 1] -= y_min

    # Use polygon order directly (TL, TR, BR, BL from obb_xywhr_to_polygon)
    # The sum/diff method fails for significantly tilted rectangles
    tl = pts_local[0]
    tr = pts_local[1]
    br = pts_local[2]
    bl = pts_local[3]

    wA = np.linalg.norm(br - bl)
    wB = np.linalg.norm(tr - tl)
    hA = np.linalg.norm(tr - br)
    hB = np.linalg.norm(tl - bl)
    
    Wt = max(64, int(max(wA, wB) + 2 * pad))
    Ht = max(64, int(max(hA, hB) + 2 * pad))
    
    Wt = min(Wt, 8000)
    Ht = min(Ht, 8000)

    dst = np.array([[pad, pad], [Wt - pad, pad], [Wt - pad, Ht - pad], [pad, Ht - pad]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype=np.float32), dst)
    
    warped = cv2.warpPerspective(patch, M, (Wt, Ht), flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))


def rotated_crop_from_det(det: dict, bgr_color: np.ndarray, pad: int = 6) -> Image.Image:
    """
    Wrapper that uses the detector's NORMALIZED angle (matches normalized dimensions).
    
    CRITICAL FIX: Uses normalized angle to match normalized dimensions.
    Previously used raw angle with normalized dimensions → mismatch!
    """
    cx = float(det.get("obb_cx", (det["x1"] + det["x2"]) / 2))
    cy = float(det.get("obb_cy", (det["y1"] + det["y2"]) / 2))
    w = float(det.get("obb_w", det["x2"] - det["x1"]))
    h = float(det.get("obb_h", det["y2"] - det["y1"]))
    
    #  CRITICAL FIX: Use NORMALIZED angle (matches normalized dimensions)
    # Previously: used angle_raw → mismatch with obb_w/obb_h
    ang = float(det.get("angle", 0.0))  # Use normalized angle!
    
    # Fallback to raw only if normalized doesn't exist (shouldn't happen)
    if ang == 0.0 and "angle_raw" in det:
        ang = float(det.get("angle_raw", 0.0))
    
    return rotated_crop_pil(bgr_color, cx, cy, w, h, ang, pad_px=pad)


def crop_pil(bgr, x1, y1, x2, y2, pad=3) -> Image.Image:
    """Simple AABB crop with padding."""
    H, W = bgr.shape[:2]
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    x2 = min(W, x2 + pad)
    y2 = min(H, y2 + pad)
    return Image.fromarray(cv2.cvtColor(bgr[y1:y2, x1:x2], cv2.COLOR_BGR2RGB))

# ============================================================================
# LINE REMOVAL (Angular vs Horizontal)
# ============================================================================

def _remove_long_lines_oriented(pil_img: Image.Image, angle_deg: float, frac_len=0.25, thickness=3) -> Image.Image:
    """
    Code 1 strategy: Oriented line removal (follows text angle).
    Used for ANGULAR text to avoid destroying tilted strokes.
    """
    g = np.array(pil_img.convert('L'))
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    inv = 255 - bw
    # IMPROVED: Use _dist_to_cardinal instead of % 90 trick
    dist_from_cardinal = _dist_to_cardinal(angle_deg)
    # Gentler on severely tilted text
    if dist_from_cardinal > 30:  # Severely tilted (>30° from any cardinal)
        # Be VERY gentle - reduce thickness and length
        thickness = min(thickness, 2)
        frac_len = min(frac_len, 0.20)
    elif dist_from_cardinal > 15:  # Moderately tilted
        thickness = min(thickness, 3)
        frac_len = min(frac_len, 0.25)

    img_diag = math.sqrt(inv.shape[0] ** 2 + inv.shape[1] ** 2)
    L = max(9, min(201, int(frac_len * img_diag)))
    
    k = np.zeros((thickness, L), np.uint8)
    k[:, :] = 1
    
    center = (L // 2, thickness // 2)
    M = cv2.getRotationMatrix2D(center, angle_deg, 1.0)
    
    cos = abs(M[0, 0])
    sin = abs(M[0, 1])
    new_w = int(L * cos + thickness * sin) + 4
    new_h = int(L * sin + thickness * cos) + 4
    
    M[0, 2] += (new_w / 2 - center[0])
    M[1, 2] += (new_h / 2 - center[1])
    
    kbig = cv2.warpAffine(k, M, (new_w, new_h), flags=cv2.INTER_NEAREST)
    kbig[kbig > 0] = 1

    lines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kbig)
    cleaned = cv2.bitwise_and(inv, cv2.bitwise_not(lines))
    
    if dist_from_cardinal > 30:
        kernel_denoise = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel_denoise, iterations=1)
    
    out = 255 - cleaned
    return Image.fromarray(out)


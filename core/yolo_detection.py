from typing import List, Dict, Tuple
import numpy as np
import cv2
from ultralytics import YOLO
from config import TILE_SIZE, OVERLAP_PCT, PRED_IMGSZ, CLASS_THRESH, CLASSES,TILE_HALO, DEBUG_ANGLE_ROUTING, canon_name, OBB_ONLY
import math
from PyQt5 import QtCore, QtGui, QtWidgets
from PIL import Image, ImageFile
from core.image_processing import _normalize_xywhr,obb_xywhr_to_polygon,polygon_to_aabb_xyxy
from utils.helpers import _is_near, _norm_angle, get_params_for_angle, _debug_angle
from core.linking import _check_oriented_direction, _check_axis_aligned_direction
# ============================================================================
# YOLO DETECTION (with angle-aware expansion)
# ============================================================================

def pil_to_bgr(im: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)

def bgr_to_qpix(bgr: np.ndarray) -> QtGui.QPixmap:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qt_img = QtGui.QImage(rgb.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
    return QtGui.QPixmap.fromImage(qt_img)

def to_gray3(bgr: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)

def draw_box(bgr, x1, y1, x2, y2, color=(0, 255, 0), label=""):
    cv2.rectangle(bgr, (x1, y1), (x2, y2), color, 2)
    if label:
        cv2.putText(bgr, label, (x1, max(0, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

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

def tile_image(bgr: np.ndarray, tile=TILE_SIZE, overlap_pct=OVERLAP_PCT):
    step = int(tile * (1 - overlap_pct / 100.0))
    H, W = bgr.shape[:2]
    xs = list(range(0, max(1, W - tile + 1), step))
    ys = list(range(0, max(1, H - tile + 1), step))
    if (W - tile) % step != 0 and W > tile:
        xs.append(W - tile)
    if (H - tile) % step != 0 and H > tile:
        ys.append(H - tile)

    tiles = []
    for y0 in ys:
        for x0 in xs:
            vx1, vy1, vx2, vy2 = x0, y0, x0 + tile, y0 + tile
            crop = bgr[vy1:vy2, vx1:vx2]
            tiles.append(((vx1, vy1, vx2, vy2), crop))
    return tiles

def run_yolo_on_page(model, page_bgr: np.ndarray) -> List[dict]:
    """YOLO detection with angle-aware parameter selection."""
    assert OBB_ONLY, "This build expects OBB-only weights"
    tiles = tile_image(page_bgr, tile=TILE_SIZE, overlap_pct=OVERLAP_PCT)
    dets: List[dict] = []

    H, W = page_bgr.shape[:2]

    for (vx1, vy1, vx2, vy2), _crop_unused in tiles:
        hx1 = max(0, vx1 - TILE_HALO)
        hy1 = max(0, vy1 - TILE_HALO)
        hx2 = min(W, vx2 + TILE_HALO)
        hy2 = min(H, vy2 + TILE_HALO)
        halo_crop = page_bgr[hy1:hy2, hx1:hx2]

        r = model.predict(source=halo_crop, imgsz=PRED_IMGSZ, conf=0.01, verbose=False)[0]
        obb = getattr(r, "obb", None)
        if obb is None or len(obb) == 0:
            continue

        has_xywhr = hasattr(obb, "xywhr")
        has_cls = hasattr(obb, "cls")
        has_conf = hasattr(obb, "conf")

        gate_x1, gate_y1, gate_x2, gate_y2 = vx1, vy1, vx2, vy2

        n = len(obb)
        for i in range(n):
            if has_xywhr:
                cx, cy, w, h, theta = obb.xywhr[i].tolist()
            else:
                if not hasattr(obb, "xyxyxyxy"):
                    continue
                poly8 = np.array(obb.xyxyxyxy[i].tolist(), dtype=np.float32).reshape(4, 2)
                cx, cy = float(poly8[:, 0].mean()), float(poly8[:, 1].mean())
                e01 = np.linalg.norm(poly8[1] - poly8[0])
                e12 = np.linalg.norm(poly8[2] - poly8[1])
                w, h = float(max(e01, e12)), float(min(e01, e12))
                theta = 0.0

            cx_p = float(cx + hx1)
            cy_p = float(cy + hy1)

            if not (gate_x1 - 2 <= cx_p <= gate_x2 + 2 and gate_y1 - 2 <= cy_p <= gate_y2 + 2):
                continue

            cls_i = int(obb.cls[i]) if has_cls else -1
            if cls_i < 0 or cls_i >= len(CLASSES):
                continue
            raw_name = CLASSES[cls_i]
            name = canon_name(raw_name)
            conf = float(obb.conf[i]) if has_conf else 0.0
            if conf < CLASS_THRESH.get(name, 0.25):
                continue

            theta_raw = float(theta)
            _, _, w_n, h_n, theta_n = _normalize_xywhr(cx_p, cy_p, w, h, theta_raw)

            # ANGLE-AWARE PARAMETER SELECTION
            ang_deg_raw = math.degrees(theta_raw)
            pad_px, (exp_x, exp_y) = get_params_for_angle(ang_deg_raw, name)

            # DEBUG: Show detection parameter selection
            if DEBUG_ANGLE_ROUTING:
                
                a = _norm_angle(ang_deg_raw)
                if _is_near(a, 0.0) or _is_near(a, 180.0):
                    category = "HORIZONTAL"
                elif _is_near(a, 90.0) or _is_near(a, 270.0):
                    category = "VERTICAL"
                else:
                    category = "ANGULAR"
                
                # Create temporary dict for debug (detection not fully built yet)
                temp_det = {
                    "angle_raw": ang_deg_raw,
                    "angle": math.degrees(float(theta_n)),  # ✓ Use normalized angle!
                    "name": name
                }
                _debug_angle("DETECTION", temp_det, category, 
                            f"pad={pad_px}px exp=({exp_x:.2f},{exp_y:.2f})")

            w_eff = max(1.0, float(w_n) * float(exp_x) + 2.0 * pad_px)
            h_eff = max(1.0, float(h_n) * float(exp_y) + 2.0 * pad_px)

            poly = obb_xywhr_to_polygon(cx_p, cy_p, w_eff, h_eff, float(theta_n))
            x1, y1, x2, y2 = polygon_to_aabb_xyxy(poly)
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(W, x2)
            y2 = min(H, y2)
            if x2 <= x1 or y2 <= y1:
                continue

            dets.append(dict(
                cls=cls_i, raw_name=raw_name, name=name, conf=conf,
                x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2),
                w=int(x2 - x1), h=int(y2 - y1), cx=(int(x1) + int(x2)) / 2.0, cy=(int(y1) + int(y2)) / 2.0,
                obb_cx=cx_p, obb_cy=cy_p, obb_w=w_eff, obb_h=h_eff,
                angle=math.degrees(float(theta_n)),
                angle_raw=math.degrees(theta_raw),
                poly=poly
            ))

    final: List[dict] = []
    unique_names = sorted(set(canon_name(n) for n in CLASSES))
    for name in unique_names:
        ss = [d for d in dets if d["name"] == name]
        if not ss:
            continue
        boxes = [(d["x1"], d["y1"], d["x2"], d["y2"]) for d in ss]
        scores = [d["conf"] for d in ss]
        keep = nms(boxes, scores, thr=0.5)
        final.extend([ss[i] for i in keep])

    return final
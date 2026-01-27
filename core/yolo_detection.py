from typing import List, Dict, Tuple
import numpy as np
import cv2
from ultralytics import YOLO
from config import TILE_SIZE, OVERLAP_PCT, PRED_IMGSZ, CLASS_THRESH, CLASSES,TILE_HALO, DEBUG_ANGLE_ROUTING, canon_name, OBB_ONLY, NMS_THRESHOLDS
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
        
        # ✅ Use class-specific NMS threshold
        nms_thr = NMS_THRESHOLDS.get(name, NMS_THRESHOLDS.get("default", 0.5))
        keep = nms(boxes, scores, thr=nms_thr)

        final.extend([ss[i] for i in keep])

    return final


# ============================================================================
# COMBINED DETECTION: YOLO + CUSTOM SYMBOLS
# ============================================================================

def run_combined_detection(model, page_bgr: np.ndarray, detect_custom: bool = True) -> List[dict]:
    """
    Run both YOLO detection and custom symbol detection on a page.

    Args:
        model: YOLO model
        page_bgr: BGR image of the page
        detect_custom: Whether to run custom symbol detection

    Returns:
        Combined list of detections with 'is_custom_symbol' flag
    """
    # Run YOLO detection (existing)
    yolo_dets = run_yolo_on_page(model, page_bgr)

    # Mark all YOLO detections
    for det in yolo_dets:
        det['is_custom_symbol'] = False
        det['detection_source'] = 'YOLO'

    if not detect_custom:
        return yolo_dets

    # Try to load and run custom symbol detection
    try:
        from core.symbol_detector import NewSymbolDetector
        from pathlib import Path

        # Check if custom symbols are defined
        config_path = Path("custom_symbols.json")
        if not config_path.exists():
            # No custom symbols defined yet
            return yolo_dets

        detector = NewSymbolDetector(str(config_path))

        if not detector.symbols:
            # No symbols loaded
            return yolo_dets

        # Run custom detection on same tiles as YOLO
        custom_dets = _run_custom_detection_on_tiles(detector, page_bgr, yolo_dets)

        # Link custom symbols to coordinates (rotation-aware)
        if custom_dets:
            # Get coordinate detections from YOLO
            coord_dets = [d for d in yolo_dets if d.get('name') == 'coordinate']

            if coord_dets:
                # Link each custom symbol type to coordinates
                linked_custom_dets = []
                for det in custom_dets:
                    symbol_name = det.get('name', '')
                    if symbol_name in detector.symbols:
                        symbol = detector.symbols[symbol_name]
                        if symbol.links_to_coordinate:
                            # Create DetectionResult for linking
                            from core.symbol_detector import DetectionResult
                            det_result = DetectionResult(
                                class_name=det['name'],
                                bbox=(det['x1'], det['y1'], det['x2'], det['y2']),
                                confidence=det['conf'],
                                angle=det.get('angle', 0.0),
                                method=det.get('detection_method', 'template'),
                                center=(det['cx'], det['cy']),
                            )
                            # Link and get dict back
                            linked = detector.link_to_coordinates([det_result], coord_dets, symbol_name)
                            if linked:
                                # Merge linked info back to det
                                det.update(linked[0])
                    linked_custom_dets.append(det)
                custom_dets = linked_custom_dets

        # Combine results
        all_dets = yolo_dets + custom_dets

        return all_dets

    except ImportError:
        # symbol_detector module not available
        return yolo_dets
    except Exception as e:
        print(f"[WARNING] Custom symbol detection failed: {e}")
        return yolo_dets


def _run_custom_detection_on_tiles(detector, page_bgr: np.ndarray, yolo_dets: List[dict]) -> List[dict]:
    """
    Run custom symbol detection on the same tiles as YOLO.
    Uses multi-threading to speed up processing.

    Args:
        detector: NewSymbolDetector instance
        page_bgr: Full page BGR image
        yolo_dets: YOLO detections (to avoid duplicate areas)

    Returns:
        List of custom symbol detections
    """
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from core.symbol_detector import DetectionResult

    H, W = page_bgr.shape[:2]
    tiles = tile_image(page_bgr, tile=TILE_SIZE, overlap_pct=OVERLAP_PCT)

    # Use multi-threading for template matching
    max_workers = min(os.cpu_count() or 4, 8)

    def process_tile(tile_data):
        """Process a single tile and return detections."""
        (vx1, vy1, vx2, vy2), tile_crop = tile_data
        tile_dets = []

        try:
            tile_results = detector.detect_all_symbols(tile_crop)
        except Exception:
            return tile_dets

        for result in tile_results:
            # Adjust coordinates to page space
            if isinstance(result, DetectionResult):
                x1 = result.bbox[0] + vx1
                y1 = result.bbox[1] + vy1
                x2 = result.bbox[2] + vx1
                y2 = result.bbox[3] + vy1

                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0

                # Check if center is within tile bounds (avoid duplicates from overlap)
                if not (vx1 <= cx <= vx2 and vy1 <= cy <= vy2):
                    continue

                # Check bounds
                x1 = max(0, x1)
                y1 = max(0, y1)
                x2 = min(W, x2)
                y2 = min(H, y2)

                if x2 <= x1 or y2 <= y1:
                    continue

                # Create detection dict compatible with YOLO format
                det = {
                    'cls': -1,  # Custom symbols don't have YOLO class
                    'raw_name': result.class_name,
                    'name': result.class_name,
                    'conf': result.confidence,
                    'x1': int(x1),
                    'y1': int(y1),
                    'x2': int(x2),
                    'y2': int(y2),
                    'w': int(x2 - x1),
                    'h': int(y2 - y1),
                    'cx': cx,
                    'cy': cy,
                    'angle': result.angle,
                    'is_custom_symbol': True,
                    'detection_source': 'CUSTOM',
                    'detection_method': result.method,
                }
                tile_dets.append(det)

            elif isinstance(result, dict):
                # Already a dict
                x1 = result.get('x1', 0) + vx1
                y1 = result.get('y1', 0) + vy1
                x2 = result.get('x2', 0) + vx1
                y2 = result.get('y2', 0) + vy1

                cx = (x1 + x2) / 2.0
                cy = (y1 + y2) / 2.0

                if not (vx1 <= cx <= vx2 and vy1 <= cy <= vy2):
                    continue

                det = dict(result)  # Copy to avoid modifying original
                det['x1'] = int(max(0, x1))
                det['y1'] = int(max(0, y1))
                det['x2'] = int(min(W, x2))
                det['y2'] = int(min(H, y2))
                det['cx'] = cx
                det['cy'] = cy
                det['is_custom_symbol'] = True
                det['detection_source'] = 'CUSTOM'
                tile_dets.append(det)

        return tile_dets

    # Process tiles in parallel
    all_custom_dets = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_tile, tile) for tile in tiles]
        for future in as_completed(futures):
            try:
                tile_dets = future.result()
                all_custom_dets.extend(tile_dets)
            except Exception:
                pass

    # NMS on custom detections to remove duplicates from tile overlaps
    if all_custom_dets:
        unique_names = set(d.get('name', '') for d in all_custom_dets)
        final_custom = []

        for name in unique_names:
            ss = [d for d in all_custom_dets if d.get('name') == name]
            if not ss:
                continue
            boxes = [(d['x1'], d['y1'], d['x2'], d['y2']) for d in ss]
            scores = [d.get('conf', 0.5) for d in ss]
            keep = nms(boxes, scores, thr=0.3)  # Use lower threshold for custom
            kept_dets = [ss[i] for i in keep]

            # Additional center-based + confidence duplicate removal
            # Sort by confidence (highest first)
            kept_dets = sorted(kept_dets, key=lambda d: d.get('conf', 0), reverse=True)
            filtered = []
            for det in kept_dets:
                det_cx = (det['x1'] + det['x2']) / 2
                det_cy = (det['y1'] + det['y2']) / 2
                is_dup = False
                for kept in filtered:
                    kept_cx = (kept['x1'] + kept['x2']) / 2
                    kept_cy = (kept['y1'] + kept['y2']) / 2
                    dist = ((det_cx - kept_cx)**2 + (det_cy - kept_cy)**2) ** 0.5
                    conf_diff = kept.get('conf', 0) - det.get('conf', 0)
                    # If close and lower confidence, skip
                    if dist < 200 and conf_diff > 0.05:
                        is_dup = True
                        break
                if not is_dup:
                    filtered.append(det)
            final_custom.extend(filtered)

        return final_custom

    return []
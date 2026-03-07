"""
YOLO Detection - Objekterkennung mit YOLOv8 OBB

Dieses Modul implementiert die YOLO-basierte Objekterkennung fuer
Gleisplansymbole mit orientierten Bounding Boxes (OBB).

Kernfunktionen:
    run_yolo_on_page(): Hauptfunktion - erkennt alle Symbole auf einer Seite
    tile_image(): Unterteilt grosse Bilder in ueberlappende Kacheln
    nms(): Non-Maximum Suppression fuer Duplikatfilterung
    color_masks(): Extrahiert Rot/Gelb-Masken fuer Farbklassifikation

Kachelungsstrategie:
    - Grosse A0-Gleisplaene werden in 2048px Kacheln unterteilt
    - 40% Ueberlappung verhindert abgeschnittene Erkennungen
    - 320px Halo gibt zusaetzlichen Kontext an Kachelraendern
    - Ergebnisse werden per NMS ueber alle Kacheln zusammengefuehrt

Konfidenz-System:
    - Zwei-Stufen-Schwellwerte: CLASS_THRESH (bestaetigt) und UNCERTAIN (zur Pruefung)
    - Per-Klasse Schwellwerte in config.py definiert
    - Unsichere Erkennungen werden zur manuellen Pruefung markiert

Abhaengigkeiten:
    ultralytics (YOLOv8), cv2, numpy
"""
from typing import List, Dict, Tuple, TYPE_CHECKING
import numpy as np
import cv2
import os
from ultralytics import YOLO
import math

# Type hint for LayoutConfig without circular import
if TYPE_CHECKING:
    from core.config_models import LayoutConfig
from PyQt5 import QtCore, QtGui, QtWidgets
from PIL import Image, ImageFile
from core.image_processing import _normalize_xywhr,obb_xywhr_to_polygon,polygon_to_aabb_xyxy
from utils.helpers import (_is_near, _norm_angle, get_params_for_angle, _debug_angle,
                           iou, nms, color_masks, box_color,
                           nms_prefer_larger, filter_contained_boxes, filter_by_halo)
from core.linking import _check_oriented_direction, _check_axis_aligned_direction

# Module-level defaults for backward compatibility (when config is not passed)
TILE_SIZE = 2048
OVERLAP_PCT = 40

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

def tile_image(bgr: np.ndarray, config: 'LayoutConfig' = None, tile: int = None, overlap_pct: int = None):
    """
    Tile image using configuration parameters.

    Args:
        bgr: Input image array
        config: LayoutConfig containing tile_size and overlap_pct (preferred)
        tile: Tile size (fallback if config not provided)
        overlap_pct: Overlap percentage (fallback if config not provided)
    """
    # Validate input image
    if bgr is None or bgr.size == 0:
        print(f"Warning: tile_image received empty image, returning empty list")
        return []

    # Use config values if provided, otherwise use explicit params or defaults
    if config is not None:
        tile = config.detection.tile_size
        overlap_pct = config.detection.overlap_pct
        use_ink_filter = config.detection.use_ink_filter
        ink_threshold = config.detection.ink_threshold
    else:
        # Fallback to provided values or defaults
        tile = tile if tile is not None else 2048
        overlap_pct = overlap_pct if overlap_pct is not None else 40
        use_ink_filter = False
        ink_threshold = 0.012

    step = int(tile * (1 - overlap_pct / 100.0))
    H, W = bgr.shape[:2]

    # Ensure image is large enough
    if H < 10 or W < 10:
        print(f"Warning: Image too small ({W}x{H}), returning empty list")
        return []
    xs = list(range(0, max(1, W - tile + 1), step))
    ys = list(range(0, max(1, H - tile + 1), step))
    if (W - tile) % step != 0 and W > tile:
        xs.append(W - tile)
    if (H - tile) % step != 0 and H > tile:
        ys.append(H - tile)

    # Precompute ink integral image if ink filtering is enabled
    ink_integral = None
    if use_ink_filter:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_integral = cv2.integral(binary.astype(np.float32))

    tile_area = tile * tile
    tiles = []
    for y0 in ys:
        for x0 in xs:
            vx1, vy1, vx2, vy2 = x0, y0, x0 + tile, y0 + tile

            # Ink filtering: skip tiles with low ink content
            if use_ink_filter and ink_integral is not None:
                y1_clamp = min(vy2, H)
                x1_clamp = min(vx2, W)
                ink_sum = (ink_integral[y1_clamp, x1_clamp] - ink_integral[vy1, x1_clamp] -
                          ink_integral[y1_clamp, vx1] + ink_integral[vy1, vx1])
                ink_ratio = (ink_sum / 255.0) / tile_area
                if ink_ratio < ink_threshold:
                    continue  # Skip low-ink tile

            crop = bgr[vy1:vy2, vx1:vx2]
            tiles.append(((vx1, vy1, vx2, vy2), crop))
    return tiles

def _process_single_result(result, tile_info: dict, config: 'LayoutConfig',
                           class_names: List[str], H: int, W: int) -> List[dict]:
    """
    Process a single YOLO result and extract detections.

    Two modes controlled by config.detection.use_native_obb_polygons:
    - True (Antwerp): Use YOLO's native xyxyxyxy polygons directly
    - False (Wien): Reconstruct polygons from xywhr with angle normalization

    Args:
        result: YOLO prediction result
        tile_info: Dict with tile coordinates (vx1, vy1, vx2, vy2, hx1, hy1)
        config: LayoutConfig
        class_names: List of class names
        H, W: Page dimensions

    Returns:
        List of detection dicts for this tile
    """
    obb = getattr(result, "obb", None)
    if obb is None or len(obb) == 0:
        return []

    # Tile region (for gate check) and halo origin (for coordinate transform)
    vx1, vy1, vx2, vy2 = tile_info['vx1'], tile_info['vy1'], tile_info['vx2'], tile_info['vy2']
    hx1, hy1 = tile_info['hx1'], tile_info['hy1']

    # Check available attributes
    has_xyxyxyxy = hasattr(obb, "xyxyxyxy")
    has_xywhr = hasattr(obb, "xywhr")
    has_cls = hasattr(obb, "cls")
    has_conf = hasattr(obb, "conf")

    # Check which polygon mode to use
    use_native = config.detection.use_native_obb_polygons

    # Gate region - detections must have centroid in tile (not halo)
    gate_x1, gate_y1, gate_x2, gate_y2 = vx1, vy1, vx2, vy2
    tile_dets: List[dict] = []

    n = len(obb)
    for i in range(n):
        # === EXTRACT XYWHR ===
        if has_xywhr:
            cx, cy, w, h, theta = obb.xywhr[i].tolist()
        else:
            if not has_xyxyxyxy:
                continue
            poly8 = np.array(obb.xyxyxyxy[i].tolist(), dtype=np.float32).reshape(4, 2)
            cx, cy = float(poly8[:, 0].mean()), float(poly8[:, 1].mean())
            e01 = np.linalg.norm(poly8[1] - poly8[0])
            e12 = np.linalg.norm(poly8[2] - poly8[1])
            w, h = float(max(e01, e12)), float(min(e01, e12))
            theta = 0.0

        # Centroid in page coordinates
        cx_p = float(cx + hx1)
        cy_p = float(cy + hy1)

        # Gate check - centroid must be in tile region (not halo)
        if not (gate_x1 - 2 <= cx_p <= gate_x2 + 2 and gate_y1 - 2 <= cy_p <= gate_y2 + 2):
            continue

        # Class and confidence
        cls_i = int(obb.cls[i]) if has_cls else -1
        if cls_i < 0 or cls_i >= len(class_names):
            continue
        raw_name = class_names[cls_i]
        name = config.canon_name(raw_name)
        conf = float(obb.conf[i]) if has_conf else 0.0

        # Determine detection status based on confidence thresholds
        class_thresh = config.get_confidence_threshold(name)
        min_uncertain = config.get_min_uncertain_threshold(name)
        effective_min = min(min_uncertain, class_thresh * 0.9)
        uncertain_thresh = max(class_thresh * config.detection.uncertain_thresh_multiplier, effective_min)

        if conf >= class_thresh:
            detection_status = 'confirmed'
        elif conf >= uncertain_thresh:
            detection_status = 'uncertain'
        else:
            continue  # Too low confidence, discard

        theta_raw = float(theta)
        ang_deg_raw = math.degrees(theta_raw)

        # Get class OCR requirement
        class_def = config.get_class_by_name(name)
        requires_ocr = class_def.requires_ocr if class_def else True

        # === MODE-SPECIFIC POLYGON/AABB COMPUTATION ===
        if use_native and has_xyxyxyxy:
            # ANTWERP MODE: Use YOLO's native polygon directly
            poly_local = np.array(obb.xyxyxyxy[i].tolist(), dtype=np.float32).reshape(4, 2)
            poly = poly_local.copy()
            poly[:, 0] += hx1
            poly[:, 1] += hy1

            # Use raw angle (no normalization)
            angle_deg = ang_deg_raw
            theta_n = theta_raw

            # Compute AABB from native polygon
            x1, y1, x2, y2 = polygon_to_aabb_xyxy(poly)

            # For OCR classes, apply padding expansion to AABB
            if requires_ocr:
                pad_px, (exp_x, exp_y) = get_params_for_angle(angle_deg, name, config)
                box_w = x2 - x1
                box_h = y2 - y1
                expand_w = int(box_w * (exp_x - 1.0) / 2 + pad_px)
                expand_h = int(box_h * (exp_y - 1.0) / 2 + pad_px)
                x1 -= expand_w
                y1 -= expand_h
                x2 += expand_w
                y2 += expand_h
            else:
                pad_px, exp_x, exp_y = 0, 1.0, 1.0

            w_eff, h_eff = w, h
        else:
            # WIEN MODE: Reconstruct polygon from normalized xywhr
            _, _, w_n, h_n, theta_n = _normalize_xywhr(cx_p, cy_p, w, h, theta_raw)

            if requires_ocr:
                pad_px, (exp_x, exp_y) = get_params_for_angle(ang_deg_raw, name, config)
            else:
                pad_px, exp_x, exp_y = 0, 1.0, 1.0

            w_eff = max(1.0, float(w_n) * float(exp_x) + 2.0 * pad_px)
            h_eff = max(1.0, float(h_n) * float(exp_y) + 2.0 * pad_px)

            poly = obb_xywhr_to_polygon(cx_p, cy_p, w_eff, h_eff, float(theta_n))
            x1, y1, x2, y2 = polygon_to_aabb_xyxy(poly)
            angle_deg = math.degrees(float(theta_n))

        # Clamp to image bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(W, x2)
        y2 = min(H, y2)
        if x2 <= x1 or y2 <= y1:
            continue

        # DEBUG: Show detection parameter selection
        if config.debug_angle_routing:
            a = _norm_angle(ang_deg_raw)
            if _is_near(a, 0.0) or _is_near(a, 180.0):
                category = "HORIZONTAL"
            elif _is_near(a, 90.0) or _is_near(a, 270.0):
                category = "VERTICAL"
            else:
                category = "ANGULAR"
            temp_det = {"angle_raw": ang_deg_raw, "angle": angle_deg, "name": name}
            mode_str = "NATIVE" if use_native else "RECONSTRUCTED"
            _debug_angle("DETECTION", temp_det, category,
                        f"mode={mode_str} pad={pad_px}px exp=({exp_x:.2f},{exp_y:.2f}) ocr={requires_ocr}")

        tile_dets.append(dict(
            cls=cls_i, raw_name=raw_name, name=name, conf=conf,
            x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2),
            w=int(x2 - x1), h=int(y2 - y1),
            cx=(int(x1) + int(x2)) / 2.0, cy=(int(y1) + int(y2)) / 2.0,
            obb_cx=cx_p, obb_cy=cy_p, obb_w=w_eff, obb_h=h_eff,
            angle=angle_deg,
            angle_raw=ang_deg_raw,
            poly=poly,
            detection_status=detection_status
        ))

    return tile_dets


def run_yolo_on_page(model, page_bgr: np.ndarray, config: 'LayoutConfig') -> List[dict]:
    """
    YOLO detection with angle-aware parameter selection and batch inference support.

    Args:
        model: YOLO model instance
        page_bgr: Page image as BGR numpy array
        config: LayoutConfig with detection parameters
    """
    assert config.detection.obb_only, "This build expects OBB-only weights"
    tiles = tile_image(page_bgr, config=config)
    dets: List[dict] = []

    H, W = page_bgr.shape[:2]
    tile_halo = config.detection.tile_halo
    pred_imgsz = config.detection.pred_imgsz
    class_names = config.get_class_names()
    conf_thresh = config.detection.global_conf_threshold

    # Get halo filtering params (only used if use_centroid_halo=True)
    use_centroid_halo = config.detection.use_centroid_halo
    halo_ratio = config.detection.halo_ratio
    halo_conf_boost = config.detection.halo_conf_boost
    tile_size = config.detection.tile_size

    # Batch inference parameters with auto-detection support
    # Use -1 for auto mode: workers = CPU cores, batch_size = workers × 3
    cpu_count = os.cpu_count() or 4
    yolo_workers = config.detection.yolo_workers
    batch_size = config.detection.batch_size

    if yolo_workers < 0:
        yolo_workers = cpu_count  # Auto: use all CPU cores
    if batch_size < 0:
        batch_size = max(1, yolo_workers * 3)  # Auto: workers × 3

    # Step 1: Prepare all tile crops and their info
    use_halo_expansion = config.detection.use_halo_expansion
    tile_data = []

    for (vx1, vy1, vx2, vy2), _crop_unused in tiles:
        if use_halo_expansion:
            # Wien behavior: expand with halo context (320px on each side)
            hx1 = max(0, vx1 - tile_halo)
            hy1 = max(0, vy1 - tile_halo)
            hx2 = min(W, vx2 + tile_halo)
            hy2 = min(H, vy2 + tile_halo)
            halo_crop = page_bgr[hy1:hy2, hx1:hx2]
        else:
            # Antwerp/Colab behavior: exact tile (no expansion)
            hx1, hy1 = vx1, vy1
            halo_crop = page_bgr[vy1:vy2, vx1:vx2]

        tile_data.append({
            'crop': halo_crop,
            'vx1': vx1, 'vy1': vy1, 'vx2': vx2, 'vy2': vy2,
            'hx1': hx1, 'hy1': hy1
        })

    # Step 2: Process tiles (batch or sequential)
    if batch_size > 1 and len(tile_data) > 1:
        # Batch inference with workers
        num_batches = (len(tile_data) + batch_size - 1) // batch_size

        for batch_idx in range(num_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(tile_data))
            batch_tiles = tile_data[start_idx:end_idx]

            # Prepare batch input (list of numpy arrays)
            batch_crops = [t['crop'] for t in batch_tiles]

            # Run batch prediction with workers
            results = model.predict(
                source=batch_crops,
                imgsz=pred_imgsz,
                conf=conf_thresh,
                verbose=False,
                workers=yolo_workers,
                stream=False
            )

            # Process each result
            for result, tile_info in zip(results, batch_tiles):
                tile_dets = _process_single_result(result, tile_info, config, class_names, H, W)

                # Apply halo filtering if enabled
                if use_centroid_halo and tile_dets:
                    tile_dets = filter_by_halo(
                        tile_dets, tile_info['vx1'], tile_info['vy1'],
                        tile_size, halo_ratio, halo_conf_boost
                    )

                dets.extend(tile_dets)
    else:
        # Sequential inference (batch_size=1 or single tile)
        for tile_info in tile_data:
            result = model.predict(
                source=tile_info['crop'],
                imgsz=pred_imgsz,
                conf=conf_thresh,
                verbose=False
            )[0]

            tile_dets = _process_single_result(result, tile_info, config, class_names, H, W)

            # Apply halo filtering if enabled
            if use_centroid_halo and tile_dets:
                tile_dets = filter_by_halo(
                    tile_dets, tile_info['vx1'], tile_info['vy1'],
                    tile_size, halo_ratio, halo_conf_boost
                )

            dets.extend(tile_dets)

    final: List[dict] = []
    unique_names = sorted(set(config.canon_name(n) for n in class_names))
    use_prefer_larger = config.detection.prefer_larger_nms

    for name in unique_names:
        ss = [d for d in dets if d["name"] == name]
        if not ss:
            continue
        boxes = [(d["x1"], d["y1"], d["x2"], d["y2"]) for d in ss]
        scores = [d["conf"] for d in ss]

        # Use class-specific NMS threshold from config
        nms_thr = config.get_nms_threshold(name)

        # Use prefer-larger NMS if enabled (Antwerp), otherwise regular NMS (Wien)
        if use_prefer_larger:
            areas = [d["w"] * d["h"] for d in ss]
            keep = nms_prefer_larger(boxes, scores, areas, thr=nms_thr)
        else:
            keep = nms(boxes, scores, thr=nms_thr)

        final.extend([ss[i] for i in keep])

    # Post-processing: filter contained boxes if enabled
    if config.detection.filter_contained_boxes:
        final = filter_contained_boxes(final, config.detection.contained_box_threshold)

    return final


# ============================================================================
# COMBINED DETECTION: YOLO + CUSTOM SYMBOLS
# ============================================================================

def run_combined_detection(model, page_bgr: np.ndarray, config: 'LayoutConfig', detect_custom: bool = True) -> List[dict]:
    """
    Run both YOLO detection and custom symbol detection on a page.

    Args:
        model: YOLO model
        page_bgr: BGR image of the page
        config: LayoutConfig with detection parameters
        detect_custom: Whether to run custom symbol detection

    Returns:
        Combined list of detections with 'is_custom_symbol' flag
    """
    # Run YOLO detection (existing)
    yolo_dets = run_yolo_on_page(model, page_bgr, config)

    # Mark all YOLO detections
    for det in yolo_dets:
        det['is_custom_symbol'] = False
        det['is_new_symbol'] = False  # Alias for consistency
        det['detection_source'] = 'YOLO'

    # Filter detections in legend strip (right edge) if enabled - apply EARLY to all paths
    if config.detection.exclude_legend_strip:
        W = page_bgr.shape[1]
        percent_width = int(W * config.detection.legend_strip_width_percent / 100.0)
        exclude_width = min(percent_width, config.detection.legend_strip_max_pixels)
        threshold_x = W - exclude_width
        yolo_dets = [d for d in yolo_dets if d['cx'] < threshold_x]

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
        custom_dets = _run_custom_detection_on_tiles(detector, page_bgr, yolo_dets, config)

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

        # Filter custom detections in legend strip (yolo_dets already filtered above)
        if config.detection.exclude_legend_strip and custom_dets:
            W = page_bgr.shape[1]
            percent_width = int(W * config.detection.legend_strip_width_percent / 100.0)
            exclude_width = min(percent_width, config.detection.legend_strip_max_pixels)
            threshold_x = W - exclude_width
            custom_dets = [d for d in custom_dets if d['cx'] < threshold_x]

        # Combine results
        all_dets = yolo_dets + custom_dets

        return all_dets

    except ImportError:
        # symbol_detector module not available
        return yolo_dets
    except Exception as e:
        print(f"[WARNING] Custom symbol detection failed: {e}")
        return yolo_dets


def _run_custom_detection_on_tiles(detector, page_bgr: np.ndarray, yolo_dets: List[dict], config: 'LayoutConfig') -> List[dict]:
    """
    Run custom symbol detection on the same tiles as YOLO.
    Uses multi-threading to speed up processing.

    Args:
        detector: NewSymbolDetector instance
        page_bgr: Full page BGR image
        yolo_dets: YOLO detections (to avoid duplicate areas)
        config: LayoutConfig with detection parameters

    Returns:
        List of custom symbol detections
    """
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from core.symbol_detector import DetectionResult

    H, W = page_bgr.shape[:2]
    tiles = tile_image(page_bgr, config=config)

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
                    'is_new_symbol': True,  # Alias for consistency
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
                det['is_new_symbol'] = True  # Alias for consistency
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
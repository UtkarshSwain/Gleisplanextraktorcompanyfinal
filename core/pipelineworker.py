from PyQt5 import QtCore, QtGui, QtWidgets
import pandas as pd
import time
from PIL import Image, ImageFile
import cv2
import re
from config import POPPLER_PATH, DEBUG_ANGLE_ROUTING, MAX_OCR_WORKERS, CLASS_THRESH, CLASSES, LINK_RULES, ALIASES, DPI, TILE_SIZE
from pdf2image import convert_from_path, pdfinfo_from_path
from core.yolo_detection import run_yolo_on_page, box_color, pil_to_bgr, tile_image, OVERLAP_PCT, color_masks
from ultralytics import YOLO
from collections import Counter
from core.ocr_engine import ocr_coordinate_unified, _clean_coordinate_overlap, _fix_coordinate_brackets
from core.linking import parse_coord
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.ocr_engine import ocr_anchor_name, ocr_best_angle, ocr_text
from core.image_processing import parse_weichen_block
from core.linking import detect_fahrtrichtung, detect_haltepunkt_signal_group, link_haltetafel_to_gks, link_anchor_to_coord, merge_duplicate_signals
import numpy as np
import gc

# ============================================================================
# WORKER THREAD (with weighted progress + unified coordinate OCR)
# ============================================================================

NO_OCR_CLASSES = ["isolierstoß", "haltepunkt", "sverbinder", "weichenende", "weichengruppeende", "haltetafel"]
FIXED_TEXT_CLASSES = {"gm_block": "GM","prellblock": "PB"}

class PipelineWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int)  # 0..100
    status = QtCore.pyqtSignal(str)    # log lines
    page_processed = QtCore.pyqtSignal(int, object, pd.DataFrame)
    done = QtCore.pyqtSignal(pd.DataFrame, object, object, object) # df, page_dfs, track_skeleton, exception
    track_detection_progress = QtCore.pyqtSignal(str)

    def __init__(self, pdf_path: str, model_path: str, ocr_engine: str, parent=None, run_analysis=True, detect_tracks=False):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.model_path = model_path
        self.ocr_engine = ocr_engine
        self._is_interrupted = False
        self.run_analysis = run_analysis
        self.detect_tracks = detect_tracks
        
    def requestInterruption(self) -> None:
        self._is_interrupted = True
        super().requestInterruption()

    def run(self):
        try:
            # --- helper to emit weighted progress ---
            def emit_progress(pages_done: int, sub: float):
                # ... (no change to this helper function) ...
                if n_pages > 0:
                    per_page = 0.95 / n_pages
                    pct = 0.05 + pages_done * per_page + sub * per_page
                else:
                    pct = 1.0
                self.progress.emit(int(round(100 * max(0.0, min(1.0, pct)))))

            # --- START MODIFICATION ---

            # Define defaults
            model = None
            n_pages = 0
            all_rows = []
            page_bgr_arrays = {}
            page_dfs = {}

            # 1. ALWAYS get page count
            info = pdfinfo_from_path(self.pdf_path, poppler_path=POPPLER_PATH)
            n_pages = int(info["Pages"])
            self.status.emit(f"[pdf] {n_pages} page(s) total")

            # 2. CONDITIONALLY load model
            if self.run_analysis:
                # -------- Model load (5%) --------
                t0 = time.perf_counter()
                msg = f"[init] Loading model: {self.model_path}"
                self.status.emit(msg); print(msg)
                model = YOLO(self.model_path) # <-- This is the slow part
                self.status.emit(f"[init] Model loaded in {time.perf_counter() - t0:.2f}s")
                self.progress.emit(5)
                self.status.emit(f"[init] Model classes: {CLASSES}")

                ALIAS_REV = {}
                for variant, canonical in ALIASES.items():
                    ALIAS_REV.setdefault(canonical, set()).add(variant)

                def _class_present(canonical: str) -> bool:
                    if canonical in CLASSES:
                        return True
                    for variant in ALIAS_REV.get(canonical, ()):
                        if variant in CLASSES:
                            return True
                    return False

                missing_thresh = [k for k in CLASS_THRESH if not _class_present(k)]
                if missing_thresh:
                    self.status.emit(f"[warn] CLASS_THRESH has unknown classes: {missing_thresh}")

                missing_rules = [k for k in LINK_RULES if not _class_present(k)]
                if missing_rules:
                    self.status.emit(f"[warn] LINK_RULES has unknown classes: {missing_rules}")
            
            else: # <-- ADD THIS ELSE BLOCK
                self.status.emit("[init] Schnell-Laden: Überspringe Modell-Laden.")
                self.progress.emit(5) # Still show some progress

            # --- END MODIFICATION ---

            # per-page subweights sum to 1.0
            W = dict(raster=0.15, prep=0.05, det=0.35, ocr_c=0.20, ocr_a=0.15, link=0.10)

            # (These lines are now at the top, so they can be removed from here)
            # all_rows = []
            # page_bgr_arrays = {} 
            # page_dfs = {} 

            for pidx in range(1, n_pages + 1):
                if self._is_interrupted:
                    break
                
                # --- THIS PART (RASTERIZING) ALWAYS RUNS ---
                emit_progress(pidx - 1, 0.0)
                self.status.emit(f"[page {pidx}/{n_pages}] Rasterizing at {DPI} DPI…")
                t_pdf = time.perf_counter()
                pil = convert_from_path(
                    self.pdf_path, dpi=DPI, poppler_path=POPPLER_PATH,
                    first_page=pidx, last_page=pidx, fmt="png",
                    thread_count=2, strict=False
                )[0]
                self.status.emit(f"[page {pidx}] Rasterized in {time.perf_counter() - t_pdf:.2f}s")
                emit_progress(pidx - 1, W['raster']) # <-- This progress can stay

                if self._is_interrupted:
                    break

                self.status.emit(f"[page {pidx}] Preparing image…")
                bgr_color = pil_to_bgr(pil)
                
                # --- START MODIFICATION ---
                
                df_page = pd.DataFrame() # <-- Create empty DataFrame by default

                if self.run_analysis:
                    self.status.emit(f"[page {pidx}] Führe YOLO/OCR-Analyse aus...") # <-- Add status
                    
                    # --- ALL OF YOUR ANALYSIS CODE IS MOVED INSIDE THIS IF BLOCK ---
                    _ = tile_image(bgr_color, tile=TILE_SIZE, overlap_pct=OVERLAP_PCT)
                    emit_progress(pidx - 1, W['raster'] + W['prep'])

                    if self._is_interrupted:
                        break

                    t_det = time.perf_counter()
                    dets = run_yolo_on_page(model, bgr_color)
                    dt_det = time.perf_counter() - t_det
                    cnt = Counter(d['name'] for d in dets)
                    summary = ", ".join(f"{k}:{v}" for k, v in sorted(cnt.items()))
                    self.status.emit(f"[page {pidx}] YOLO: {len(dets)} boxes in {dt_det:.2f}s [{summary}]")
                    emit_progress(pidx - 1, W['raster'] + W['prep'] + W['det'])

                    mask_red, mask_yel = color_masks(bgr_color)
                    coords = [d for d in dets if d["name"] == "coordinate"]
                    anchors = [d for d in dets if d["name"] != "coordinate"]
                    self.status.emit(f"[page {pidx}] OCR: coords={len(coords)}, anchors={len(anchors)}")

                    # Coordinate OCR
                    coord_meta = {}
                    t_ocr = time.perf_counter()

                    def _do_coord(c):
                        try:
                            txt = ocr_coordinate_unified(c, bgr_color, self.ocr_engine)
                        except Exception:
                            txt = ""
                        
                        # ✅ STEP 2: ADD DEBUG OUTPUT HERE
                        if DEBUG_ANGLE_ROUTING and txt:
                            print(f"\n   [OCR Coordinate] Raw OCR output: '{txt}'")
                        
                        # Clean and fix
                        txt_cleaned = _clean_coordinate_overlap(txt)
                        txt_fixed = _fix_coordinate_brackets(txt_cleaned)
                        
                        # ✅ NEW: Apply final cleaning to remove trailing alphabet
                        txt_fixed = re.sub(r'\s*[a-zA-Z]\s*$', '', txt_fixed)
                        txt_fixed = re.sub(r'\s*[|/\\]\s*$', '', txt_fixed)
                        
                        if DEBUG_ANGLE_ROUTING and txt:
                            if txt_cleaned != txt:
                                print(f"   [OCR Coordinate] After clean_overlap: '{txt}' → '{txt_cleaned}'")
                            if txt_fixed != txt_cleaned:
                                print(f"   [OCR Coordinate] After fix_brackets: '{txt_cleaned}' → '{txt_fixed}'")
                        
                        # Parse
                        val, gi = parse_coord(txt_fixed)
                        
                        if DEBUG_ANGLE_ROUTING and txt:
                            print(f"   [OCR Coordinate] Final parse result: value={val}, gi_gl={gi}")
                            print(f"   [OCR Coordinate] Complete flow: '{txt}' → '{txt_fixed}' → value={val}, gi_gl={gi}\n")
                        
                        c_color = box_color(mask_red, mask_yel, c["x1"], c["y1"], c["x2"], c["y2"])
                        return (id(c), dict(text=txt_fixed, value=val, gi=gi, color=c_color))

                    if coords:
                        with ThreadPoolExecutor(max_workers=MAX_OCR_WORKERS) as ex:
                            for f in as_completed([ex.submit(_do_coord, c) for c in coords]):
                                k, v = f.result()
                                coord_meta[k] = v

                    self.status.emit(f"[page {pidx}] OCR coords done in {time.perf_counter() - t_ocr:.2f}s (threads={MAX_OCR_WORKERS})")
                    emit_progress(pidx - 1, W['raster'] + W['prep'] + W['det'] + W['ocr_c'])

                    if self._is_interrupted:
                        break

                    # Anchors OCR
                    anchor_results = []

                    def _do_anchor(a):
                        # ... (no change to this helper function) ...
                        a_color = box_color(mask_red, mask_yel, a["x1"], a["y1"], a["x2"], a["y2"])
                        if a["name"] in NO_OCR_CLASSES:
                            name_txt = ""
                            weichen_coords = [] 
                        elif a["name"] in FIXED_TEXT_CLASSES:
                            name_txt = FIXED_TEXT_CLASSES[a["name"]]
                            weichen_coords = []
                        else:
                            ocr_result = ocr_anchor_name(a, bgr_color, self.ocr_engine)
                            if a["name"] == "weichen_block":
                                parsed = parse_weichen_block(ocr_result)
                                name_txt = parsed['id'] 
                                weichen_coords = parsed['coordinates']
                            else:
                                name_txt = ocr_result
                                weichen_coords = [] 
                        return (a, a_color, name_txt, weichen_coords)

                    if anchors:
                        with ThreadPoolExecutor(max_workers=MAX_OCR_WORKERS) as ex:
                            for f in as_completed([ex.submit(_do_anchor, a) for a in anchors]):
                                anchor_results.append(f.result())

                    emit_progress(pidx - 1, W['raster'] + W['prep'] + W['det'] + W['ocr_c'] + W['ocr_a'])
                    
                    # ... (Fahrtrichtung detection, lines 181-213) ...
                    if DEBUG_ANGLE_ROUTING:
                        print(f"\n[page {pidx}] Detecting Fahrtrichtung...")
                    signal_dets = [a for a, _, _, _ in anchor_results if a["name"] == "signal"]
                    gks_dets = [a for a, _, _, _ in anchor_results if a["name"] == "gks_gesteuert"]
                    fahrtrichtung_map = {}
                    # Fahrtrichtung detection does NOT consume coordinates
                    for signal_det in signal_dets:
                        signal_text = None
                        for a, _, name_txt, _ in anchor_results:
                            if id(a) == id(signal_det):
                                signal_text = name_txt
                                break
                        signal_det["text"] = signal_text or ""
                        
                        # ✅ Fahrtrichtung detection - reads GKS positions but doesn't consume them
                        fahrtrichtung = detect_fahrtrichtung(signal_det, gks_dets, max_distance=250)
                        if fahrtrichtung:
                            fahrtrichtung_map[id(signal_det)] = fahrtrichtung
                            if DEBUG_ANGLE_ROUTING:
                                print(f"   Signal {signal_text}: Fahrtrichtung {fahrtrichtung}")
                                
                    # ✅ NEW: Haltepunkt-Signal-Coordinate grouping detection
                    if DEBUG_ANGLE_ROUTING:
                        print(f"\n[page {pidx}] Detecting Haltepunkt groups...")

                    haltepunkt_dets = [a for a, _, _, _ in anchor_results if a["name"] == "haltepunkt"]
                    haltepunkt_groups = {}  # Map haltepunkt id -> {'signal': text, 'coordinate': text}
                    # Prepare coordinate detections with their OCR text
                    coord_dets_with_text = []
                    for c in coords:
                        meta = coord_meta.get(id(c), {})
                        c_with_text = {
                            'x1': c.get('x1'),
                            'y1': c.get('y1'),
                            'x2': c.get('x2'),
                            'y2': c.get('y2'),
                            'cx1': c.get('x1'),  # ✅ Add cx1/cy1/cx2/cy2 for compatibility
                            'cy1': c.get('y1'),
                            'cx2': c.get('x2'),
                            'cy2': c.get('y2'),
                            'angle': c.get('angle', 0.0),
                            'angle_raw': c.get('angle_raw', 0.0),
                            'text': meta.get('text', '')
                        }
                        coord_dets_with_text.append(c_with_text)

                    # Detect groups for each haltepunkt
                    for haltepunkt_det in haltepunkt_dets:
                        group = detect_haltepunkt_signal_group(
                            haltepunkt_det, 
                            signal_dets,  # Already has 'text' attribute from Fahrtrichtung detection
                            coord_dets_with_text,
                            max_distance=250
                        )
                        
                        if group:
                            haltepunkt_groups[id(haltepunkt_det)] = group
                            
                            if DEBUG_ANGLE_ROUTING:
                                print(f"   Haltepunkt group: signal='{group['signal']}', coordinate='{group.get('coordinate', '')}'")
                            
                            # ✅ Mark signal TEXT as used (not just object ID)
                            # ✅ Just log that haltepunkt references this signal
                            if group['signal'] and DEBUG_ANGLE_ROUTING:
                                print(f"      → Haltepunkt references signal '{group['signal']}' (signal remains visible)")
                            
                    # Linking + rows
                    used_coord_ids = set()
                    learned_patterns = {}

                    # ✅ STEP 1: Build a map of GKS → coordinate FIRST
                    gks_coord_map = {}  # Maps id(gks_det) → coordinate dict

                    if DEBUG_ANGLE_ROUTING:
                        print(f"\n[STEP 1] Pre-linking GKS boxes to coordinates...")

                    for (a, a_color, name_txt, weichen_coords) in anchor_results:
                        if a["name"] in ["gks_festkodiert", "gks_gesteuert"]:
                            available_coords = [c for c in coords if id(c) not in used_coord_ids]
                            linked = link_anchor_to_coord(a, available_coords, learned_patterns)
                            
                            if linked is not None:
                                used_coord_ids.add(id(linked))
                                gks_coord_map[id(a)] = linked
                                
                                # Record pattern
                                dx_offset = linked["cx"] - a["cx"]
                                dy_offset = linked["cy"] - a["cy"]
                                if a["name"] not in learned_patterns:
                                    learned_patterns[a["name"]] = []
                                learned_patterns[a["name"]].append((dx_offset, dy_offset))
                                
                                if DEBUG_ANGLE_ROUTING:
                                    meta = coord_meta.get(id(linked), {})
                                    coord_txt = meta.get("text", "?")
                                    if coord_txt:
                                        coord_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', coord_txt)
                                        coord_txt = re.sub(r'\s*[|/\\]\s*$', '', coord_txt)
                                        coord_txt = ' '.join(coord_txt.split()).strip()
                                        print(f"   GKS '{name_txt}' → coordinate '{coord_txt}'")

                    if DEBUG_ANGLE_ROUTING:
                        print(f"\n[STEP 2] Linking all elements (including haltetafel)...")

                    # ✅ STEP 2: Now process ALL elements (including haltetafel)
                    for (a, a_color, name_txt, weichen_coords) in anchor_results:
                        row_id = len(all_rows)
                        fahrtrichtung = None
                        
                        if a["name"] == "signal":
                            fahrtrichtung = fahrtrichtung_map.get(id(a))
                        
                        # ✅ SPECIAL HANDLING FOR HALTEPUNKT (existing code)
                        if a["name"] == "haltepunkt":
                            group = haltepunkt_groups.get(id(a))
                            haltepunkt_counter = sum(1 for r in all_rows if r['cls'] == 'haltepunkt') + 1
                            
                            if group:
                                signal_text = group.get('signal', '')
                                coord_text = group.get('coordinate', '')
                                
                                if signal_text:
                                    haltepunkt_name = f"haltepunkt {haltepunkt_counter} ({signal_text})"
                                else:
                                    haltepunkt_name = f"haltepunkt {haltepunkt_counter}"
                                
                                coord_value = None
                                gi_gl = None
                                if coord_text:
                                    coord_value, gi_gl = parse_coord(coord_text)
                                
                                all_rows.append(dict(
                                    row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                    anchor_text=haltepunkt_name,
                                    coord_text=coord_text,
                                    coord_value=coord_value,
                                    gi_gl=gi_gl,
                                    ax1=a["x1"], ay1=a["y1"], ax2=a["x2"], ay2=a["y2"],
                                    cx1=None, cy1=None, cx2=None, cy2=None,
                                    angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                    obb_cx=a.get("obb_cx"), obb_cy=a.get("obb_cy"),
                                    obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                    poly=(a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly")),
                                    notes="", weichen_coordinates=[], fahrtrichtung=None
                                ))
                                continue
                            
                            haltepunkt_name = f"haltepunkt {haltepunkt_counter}"
                            all_rows.append(dict(
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=haltepunkt_name,
                                coord_text=None, coord_value=None, gi_gl=None,
                                ax1=a["x1"], ay1=a["y1"], ax2=a["x2"], ay2=a["y2"],
                                cx1=None, cy1=None, cx2=None, cy2=None,
                                angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=a.get("obb_cx"), obb_cy=a.get("obb_cy"),
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=(a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly")),
                                notes="", weichen_coordinates=[], fahrtrichtung=None
                            ))
                            continue
                        
                        # ✅ SPECIAL HANDLING FOR WEICHEN_BLOCK (existing code)
                        if a["name"] == "weichen_block":
                            coord_text_combined = " | ".join(weichen_coords) if weichen_coords else None
                            all_rows.append(dict(
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=name_txt, coord_text=coord_text_combined, coord_value=None, gi_gl=None,
                                ax1=a["x1"], ay1=a["y1"], ax2=a["x2"], ay2=a["y2"],
                                cx1=None, cy1=None, cx2=None, cy2=None, angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=a.get("obb_cx"), obb_cy=a.get("obb_cy"), obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=(a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly")),
                                notes="", weichen_coordinates=weichen_coords, fahrtrichtung=None
                            ))
                            continue
                        
                        # ✅ NEW: SPECIAL HANDLING FOR HALTETAFEL
                        if a["name"] == "haltetafel":
                            # First try normal coordinate linking
                            available_coords = [c for c in coords if id(c) not in used_coord_ids]
                            linked = link_anchor_to_coord(a, available_coords, learned_patterns)
                            
                            # If no direct coordinate found, try linking via GKS
                            if linked is None:
                                gks_dets = [det for det, _, _, _ in anchor_results if det["name"] == "gks_festkodiert"]
                                linked = link_haltetafel_to_gks(a, gks_dets, coords, gks_coord_map)
                                
                                if DEBUG_ANGLE_ROUTING and linked:
                                    meta = coord_meta.get(id(linked), {})
                                    coord_txt = meta.get("text", "?")
                                    print(f"   ✅ Haltetafel inherited coordinate from GKS: '{coord_txt}'")
                            
                            # Process coordinate
                            coord_txt, coord_val, gi = None, None, None
                            cbbox = (None, None, None, None)
                            
                            if linked is not None:
                                # Only mark as used if it was a direct link (not inherited from GKS)
                                if id(linked) not in [id(c) for c in gks_coord_map.values()]:
                                    used_coord_ids.add(id(linked))
                                
                                # Record pattern
                                dx_offset = linked["cx"] - a["cx"]
                                dy_offset = linked["cy"] - a["cy"]
                                if a["name"] not in learned_patterns:
                                    learned_patterns[a["name"]] = []
                                learned_patterns[a["name"]].append((dx_offset, dy_offset))
                                
                                meta = coord_meta.get(id(linked), {})
                                coord_txt, coord_val, gi = meta.get("text"), meta.get("value"), meta.get("gi")
                                cbbox = (linked["x1"], linked["y1"], linked["x2"], linked["y2"])
                            
                            # Create row
                            all_rows.append(dict(
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=name_txt, coord_text=coord_txt, coord_value=coord_val, gi_gl=gi,
                                ax1=a["x1"], ay1=a["y1"], ax2=a["x2"], ay2=a["y2"],
                                cx1=cbbox[0], cy1=cbbox[1], cx2=cbbox[2], cy2=cbbox[3],
                                angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=a.get("obb_cx"), obb_cy=a.get("obb_cy"),
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=(a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly")),
                                notes="", weichen_coordinates=[], fahrtrichtung=None
                            ))
                            continue
                        
                        # ✅ SKIP GKS (already processed in STEP 1)
                        if a["name"] in ["gks_festkodiert", "gks_gesteuert"]:
                            # Retrieve the already-linked coordinate
                            linked = gks_coord_map.get(id(a))
                            
                            coord_txt, coord_val, gi = None, None, None
                            cbbox = (None, None, None, None)
                            
                            if linked is not None:
                                meta = coord_meta.get(id(linked), {})
                                coord_txt, coord_val, gi = meta.get("text"), meta.get("value"), meta.get("gi")
                                if coord_txt:
                                    coord_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', coord_txt)
                                    coord_txt = re.sub(r'\s*[|/\\]\s*$', '', coord_txt)
                                    coord_txt = ' '.join(coord_txt.split()).strip()
                                cbbox = (linked["x1"], linked["y1"], linked["x2"], linked["y2"])
                            
                            all_rows.append(dict(
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=name_txt, coord_text=coord_txt, coord_value=coord_val, gi_gl=gi,
                                ax1=a["x1"], ay1=a["y1"], ax2=a["x2"], ay2=a["y2"],
                                cx1=cbbox[0], cy1=cbbox[1], cx2=cbbox[2], cy2=cbbox[3],
                                angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=a.get("obb_cx"), obb_cy=a.get("obb_cy"),
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=(a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly")),
                                notes="", weichen_coordinates=[], fahrtrichtung=fahrtrichtung
                            ))
                            continue
                        
                        # ✅ EXISTING CODE FOR OTHER CLASSES
                        available_coords = [c for c in coords if id(c) not in used_coord_ids]
                        linked = link_anchor_to_coord(a, available_coords, learned_patterns)
                        
                        coord_txt, coord_val, gi = None, None, None
                        cbbox = (None, None, None, None)
                        
                        if linked is not None:
                            used_coord_ids.add(id(linked))
                            
                            dx_offset = linked["cx"] - a["cx"]
                            dy_offset = linked["cy"] - a["cy"]
                            if a["name"] not in learned_patterns:
                                learned_patterns[a["name"]] = []
                            learned_patterns[a["name"]].append((dx_offset, dy_offset))
                            
                            meta = coord_meta.get(id(linked), {})
                            coord_txt, coord_val, gi = meta.get("text"), meta.get("value"), meta.get("gi")
                            if coord_txt:
                                # Remove trailing alphabets (single letters)
                                coord_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', coord_txt)
                                # Remove trailing slashes/pipes
                                coord_txt = re.sub(r'\s*[|/\\]\s*$', '', coord_txt)
                                # Remove extra whitespace
                                coord_txt = ' '.join(coord_txt.split())
                                # Strip leading/trailing whitespace
                                coord_txt = coord_txt.strip()

                            cbbox = (linked["x1"], linked["y1"], linked["x2"], linked["y2"])
                        else:
                            # Fallback OCR logic (existing code)
                            mode = LINK_RULES.get(a["name"], {}).get("mode", "either")
                            dy = int(1.6 * a["h"])
                            dx = int(0.6 * a["w"])
                            
                            if mode in ("below", "either", "right_or_below"):
                                sx1, sy1 = max(0, a["x1"] - dx), a["y2"]
                                sx2, sy2 = min(bgr_color.shape[1], a["x2"] + dx), min(bgr_color.shape[0], a["y2"] + dy)
                                if sy2 > sy1:
                                    crop = Image.fromarray(cv2.cvtColor(bgr_color[sy1:sy2, sx1:sx2], cv2.COLOR_BGR2RGB))
                                    txt = ocr_best_angle(crop, self.ocr_engine) if a["name"] == "isolierstoß" else ocr_text(crop, self.ocr_engine)
                                    if txt:
                                        txt = re.sub(r'\s*[a-zA-Z]\s*$', '', txt)
                                        txt = re.sub(r'\s*[|/\\]\s*$', '', txt)
                                        txt = ' '.join(txt.split()).strip()
                                    val, gi2 = parse_coord(txt)
                                    if val is not None:
                                        coord_txt, coord_val, gi = txt, val, gi2
                                        cbbox = (sx1, sy1, sx2, sy2)
                            
                            if coord_val is None and mode in ("above", "either"):
                                sy1, sy2 = max(0, a["y1"] - dy), a["y1"]
                                sx1, sx2 = max(0, a["x1"] - dx), min(bgr_color.shape[1], a["x2"] + dx)
                                if sy2 > sy1:
                                    crop = Image.fromarray(cv2.cvtColor(bgr_color[sy1:sy2, sx1:sx2], cv2.COLOR_BGR2RGB))
                                    txt = ocr_best_angle(crop, self.ocr_engine) if a["name"] == "isolierstoß" else ocr_text(crop, self.ocr_engine)
                                    if txt:
                                        txt = re.sub(r'\s*[a-zA-Z]\s*$', '', txt)
                                        txt = re.sub(r'\s*[|/\\]\s*$', '', txt)
                                        txt = ' '.join(txt.split()).strip()
                                    val, gi2 = parse_coord(txt)
                                    if val is not None:
                                        coord_txt, coord_val, gi = txt, val, gi2
                                        cbbox = (sx1, sy1, sx2, sy2)
                        
                        all_rows.append(dict(
                            row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                            anchor_text=name_txt, coord_text=coord_txt, coord_value=coord_val, gi_gl=gi,
                            ax1=a["x1"], ay1=a["y1"], ax2=a["x2"], ay2=a["y2"],
                            cx1=cbbox[0], cy1=cbbox[1], cx2=cbbox[2], cy2=cbbox[3],
                            angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                            obb_cx=a.get("obb_cx"), obb_cy=a.get("obb_cy"),
                            obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                            poly=(a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly")),
                            notes="", weichen_coordinates=[], fahrtrichtung=fahrtrichtung
                        ))

                    for c in coords:
                        row_id = len(all_rows)
                        meta = coord_meta.get(id(c), {})
                        all_rows.append(dict(
                            row_id=row_id, page=pidx, cls="coordinate", conf=round(c["conf"], 3), color=meta.get("color", "none"),
                            anchor_text="", coord_text=meta.get("text"), coord_value=meta.get("value"), gi_gl=meta.get("gi"),
                            ax1=None, ay1=None, ax2=None, ay2=None,
                            cx1=c["x1"], cy1=c["y1"], cx2=c["x2"], cy2=c["y2"],
                            angle=c.get("angle"), angle_raw=c.get("angle_raw"),
                            obb_cx=c.get("obb_cx"), obb_cy=c.get("obb_cy"),
                            obb_w=c.get("obb_w"), obb_h=c.get("obb_h"),
                            poly=(c.get("poly").tolist() if isinstance(c.get("poly"), np.ndarray) else c.get("poly")),
                            notes="", weichen_coordinates=[], fahrtrichtung=None
                        ))
                        
                    if DEBUG_ANGLE_ROUTING:
                        print(f"\n[page {pidx}] Merging duplicate signals...")
                        
                    all_rows = merge_duplicate_signals(all_rows) # <-- This is the last analysis step
                    emit_progress(pidx - 1, W['raster'] + W['prep'] + W['det'] + W['ocr_c'] + W['ocr_a'] + W['link'])

                    # Now, create the df_page from the rows for this page
                    df_page = pd.DataFrame([r for r in all_rows if r["page"] == pidx]) # <-- Re-create df_page
                
                else: # <-- ADD THIS ELSE BLOCK
                    self.status.emit(f"[page {pidx}] Extrahiere Bild (Überspringe Analyse)...")
                    emit_progress(pidx - 1, 1.0) # Mark page as "done"
                
                # --- END MODIFICATION ---

                # --- THIS PART (EMITTING) ALWAYS RUNS ---
                page_bgr_arrays[pidx] = bgr_color
                page_dfs[pidx] = df_page
                
                self.page_processed.emit(pidx, bgr_color, df_page)
                # --- (Your file had this logic, it is correct) ---
                
                self.status.emit(f"[page {pidx}] Done.")

                del pil, bgr_color # <-- MODIFIED (Don't del items that may not exist)
                if self.run_analysis: # <-- ADD THIS
                    del mask_red, mask_yel, coords, anchors, coord_meta, dets
                gc.collect()
            
            # --- START MODIFICATION ---

            df_all = pd.DataFrame(all_rows) # This will be empty if analysis was skipped

            if self.run_analysis: # <-- WRAP THIS FINAL MERGE
                self.status.emit(f"[done] Total rows: {len(df_all)}")
                
                if DEBUG_ANGLE_ROUTING:
                    print(f"\n[FINAL] Merging duplicate signals across all pages...")
                    original_len = len(all_rows)

                all_rows = merge_duplicate_signals(all_rows)
                df_all = pd.DataFrame(all_rows)

                if DEBUG_ANGLE_ROUTING:
                    merged_len = len(all_rows)
                    if original_len != merged_len:
                        print(f"   Final merge: {original_len} → {merged_len} (saved {original_len - merged_len} rows)")
            
            # --- END MODIFICATION ---

            # ========================================================================
            # STEP: TRACK DETECTION (if enabled)
            # ========================================================================
            track_skeleton = None
            if self.detect_tracks and self.run_analysis:
                self.status.emit("[track] Detecting main tracks...")
                self.progress.emit(98)
                
                try:
                    from track_detection import detect_main_tracks
                    
                    def track_progress(msg):
                        self.track_detection_progress.emit(msg)
                    
                    track_skeleton, _, _ = detect_main_tracks(
                        pdf_path=self.pdf_path,
                        page_idx=0,
                        dpi=DPI,
                        tile_size=TILE_SIZE,
                        overlap=int(TILE_SIZE * OVERLAP_PCT / 100),
                        progress_callback=track_progress
                    )
                    
                    self.status.emit(f"[track] ✓ Track detection complete")
                    
                except Exception as e:
                    import traceback
                    self.status.emit(f"[track] ⚠️ Track detection failed: {e}")
                    traceback.print_exc()
                    track_skeleton = None

            self.progress.emit(100)
            self.done.emit(df_all, page_dfs, track_skeleton, None)
            
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.status.emit(f"[error] {e}\n{tb_str}")
            df_err = pd.DataFrame([{"error": str(e)}])
            self.done.emit(df_err, {}, None, e)

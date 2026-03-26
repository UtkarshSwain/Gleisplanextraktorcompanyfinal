"""
PipelineWorker - Haupt-Verarbeitungsthread fuer Gleisplanerkennung

Dieses Modul enthaelt den PipelineWorker QThread, der die komplette
Verarbeitungspipeline fuer PDF- und Bilddateien orchestriert.

Verarbeitungsschritte:
    1. Datei laden (PDF via pdf2image oder Bild direkt)
    2. Farben fuer YOLO konvertieren (Farbige Pixel -> Schwarz)
    3. YOLO Objekterkennung ausfuehren
    4. Benutzerdefinierte Symbole erkennen (Template-Matching)
    5. OCR fuer jede Erkennung (Text, Koordinaten)
    6. Koordinaten-Verknuepfung und Fahrtrichtungserkennung
    7. Validierung und Qualitaetspruefung
    8. Ergebnisse als DataFrame emittieren

Hauptklassen:
    PipelineWorker: QThread fuer asynchrone Verarbeitung

Signale:
    progress(int): Fortschritt 0-100%
    status(str): Statusmeldungen
    page_processed(int, object, DataFrame): Seite fertig
    done(DataFrame, ...): Verarbeitung abgeschlossen

Abhaengigkeiten:
    PyQt5, pandas, ultralytics, cv2, pdf2image
"""
from PyQt5 import QtCore, QtGui, QtWidgets
import pandas as pd
import time
import os
from PIL import Image
import re
from typing import TYPE_CHECKING
from pdf2image import convert_from_path, pdfinfo_from_path
from core.yolo_detection import run_yolo_on_page, run_combined_detection, box_color, pil_to_bgr, tile_image, color_masks
from ultralytics import YOLO
from collections import Counter
from core.ocr_engine import ocr_coordinate_unified, _clean_coordinate_overlap, _fix_coordinate_brackets, configure_from_config as configure_ocr
from core.linking import parse_coord
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.ocr_engine import ocr_anchor_name, ocr_best_angle, ocr_text, ocr_custom_symbol_text
from core.image_processing import parse_weichen_block, ensure_landscape
from core.linking import (
    detect_fahrtrichtung, detect_haltepunkt_signal_group, link_haltetafel_to_gks,
    link_anchor_to_coord, link_anchor_to_text_id, merge_duplicate_signals, link_isolierstoss_fallback,
    detect_fahrtrichtung_gks_relaxed, detect_fahrtrichtung_gks_nearest, link_antwerp_coordinates,
    detect_fahrtrichtung_antwerp, calculate_durchrutschweg
)
import numpy as np
import gc
from utils.uuid_utils import generate_deterministic_uuid, extract_base_layout_name
import logging

# Type hint for LayoutConfig without circular import
if TYPE_CHECKING:
    from core.config_models import LayoutConfig

# Module-level defaults (can be overridden by config)
POPPLER_PATH = None
DEBUG_ANGLE_ROUTING = False
DEBUG_YOLO = False
DEBUG_TRACK = False
DEBUG_CUSTOM_SYMBOLS = False
DEBUG_LINKING = False
DEBUG_OCR = False
DEBUG_DATABASE = False
MAX_OCR_WORKERS = 8
DPI = 500
TILE_SIZE = 2048
EXCLUDE_LEGEND_STRIP = True
LEGEND_STRIP_WIDTH_PERCENT = 12
LEGEND_STRIP_MAX_PIXELS = 4000
OVERLAP_PCT = 40

# Default class thresholds
CLASS_THRESH = {
    "signal": 0.40, "gm_block": 0.22, "gks_festkodiert": 0.85,
    "gks_gesteuert": 0.5, "weichen_block": 0.42, "isolierstoß": 0.09,
    "haltepunkt": 0.32, "sverbinder": 0.50, "coordinate": 0.10,
    "prellbock": 0.30, "haltetafel": 0.55, "weichenende": 0.7,
    "weichengruppenende": 0.7
}

# Default class list
CLASSES = list(CLASS_THRESH.keys())

# Default linking rules - fallback when config is not provided
# These are overwritten by _configure_from_config() when a profile is loaded
LINK_RULES = {
    "signal": {"mode": "below"},
    "gm_block": {"mode": "below"},
    "gks_gesteuert": {"mode": "either"},
    "gks_festkodiert": {"mode": "either"},
    "weichen_block": {"mode": "inside", "block": True},
    "isolierstoß": {"mode": "above", "tilted_ok": True},
    "haltepunkt": {"mode": "either"},
    "sverbinder": {"mode": "above"},
    "prellbock": {"mode": "right_or_below", "dx_multiplier": 2.0, "prefer_horizontal": True},
    "haltetafel": {"mode": "either", "dx_multiplier": 2.0},
    "weichenende": {"mode": "either", "dx_multiplier": 3.0, "prefer_horizontal": True},
    "weichengruppenende": {"mode": "either", "dx_multiplier": 3.0, "prefer_horizontal": True, "search_left": True},
}

ALIASES = {}


def canon_name(name: str) -> str:
    """Canonicalize class name using aliases."""
    return ALIASES.get(name.lower(), name.lower()) if name else name


def set_classes_from_model(model):
    """Set CLASSES from model names."""
    global CLASSES
    if hasattr(model, 'names') and model.names:
        CLASSES = list(model.names.values())

logger = logging.getLogger(__name__)

# ============================================================================
# WORKER THREAD (with weighted progress + unified coordinate OCR)
# ============================================================================

# These are now built from config in _configure_from_config()
# Defaults for backward compatibility when no config provided
NO_OCR_CLASSES = []  # Will be populated from config.classes where requires_ocr=False
FIXED_TEXT_CLASSES = {}  # Will be populated from config.classes where fixed_text is set


class PipelineWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int)  # 0..100
    status = QtCore.pyqtSignal(str)    # log lines
    page_processed = QtCore.pyqtSignal(int, object, pd.DataFrame)
    done = QtCore.pyqtSignal(pd.DataFrame, object, object, object, list) # df, page_dfs, track_skeleton, exception, uncertain_detections
    track_detection_progress = QtCore.pyqtSignal(str)

    # Supported image formats (loaded directly without conversion)
    IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')

    def __init__(self, file_path: str, model_path: str, ocr_engine: str, parent=None,
                 run_analysis=True, detect_tracks=False, config: 'LayoutConfig' = None):
        super().__init__(parent)
        self.file_path = file_path  # Can be PDF or image file
        self.pdf_path = file_path   # Keep for backward compatibility
        self.model_path = model_path
        self.ocr_engine = ocr_engine
        self._is_interrupted = False
        self.run_analysis = run_analysis
        self.detect_tracks = detect_tracks
        self.config = config  # Store LayoutConfig for use throughout pipeline

        # Configure module-level variables from config
        if config is not None:
            self._configure_from_config(config)

        # Storage for uncertain (low-confidence) detections for user review
        self.uncertain_detections = []

        # Determine if input is an image file
        self._is_image_file = file_path.lower().endswith(self.IMAGE_EXTENSIONS)

    def _configure_from_config(self, config: 'LayoutConfig') -> None:
        """Configure module-level variables from LayoutConfig."""
        global POPPLER_PATH, DEBUG_ANGLE_ROUTING, DEBUG_YOLO, DEBUG_TRACK
        global DEBUG_CUSTOM_SYMBOLS, DEBUG_LINKING, DEBUG_OCR, DEBUG_DATABASE, MAX_OCR_WORKERS
        global DPI, TILE_SIZE, EXCLUDE_LEGEND_STRIP, LEGEND_STRIP_WIDTH_PERCENT
        global LEGEND_STRIP_MAX_PIXELS, CLASS_THRESH, CLASSES, LINK_RULES, ALIASES, OVERLAP_PCT

        # Debug flags
        DEBUG_ANGLE_ROUTING = config.debug_angle_routing
        DEBUG_YOLO = config.debug_yolo
        DEBUG_TRACK = config.debug_track
        DEBUG_CUSTOM_SYMBOLS = config.debug_custom_symbols
        DEBUG_LINKING = config.debug_linking
        DEBUG_OCR = config.debug_ocr
        DEBUG_DATABASE = config.debug_database if hasattr(config, 'debug_database') else False

        # Paths
        if config.poppler_path:
            POPPLER_PATH = config.poppler_path

        # Detection params
        if hasattr(config, 'detection'):
            det = config.detection
            DPI = det.dpi
            if DEBUG_DATABASE:
                print(f"DEBUG: Using DPI={DPI} from profile config")
            TILE_SIZE = det.tile_size
            OVERLAP_PCT = det.overlap_pct
            EXCLUDE_LEGEND_STRIP = det.exclude_legend_strip
            LEGEND_STRIP_WIDTH_PERCENT = det.legend_strip_width_percent
            LEGEND_STRIP_MAX_PIXELS = det.legend_strip_max_pixels

        # OCR params
        if hasattr(config, 'ocr'):
            MAX_OCR_WORKERS = config.ocr.max_workers

        # Class thresholds from config
        CLASS_THRESH = {}
        CLASSES = []
        LINK_RULES = {}
        for cls_def in config.classes:
            CLASS_THRESH[cls_def.name] = cls_def.confidence_threshold
            CLASSES.append(cls_def.name)
            if cls_def.linking_rule:
                LINK_RULES[cls_def.name] = {
                    "mode": cls_def.linking_rule.mode,
                    "dx_multiplier": cls_def.linking_rule.dx_multiplier,
                    "dy_multiplier": cls_def.linking_rule.dy_multiplier,
                    "prefer_horizontal": cls_def.linking_rule.prefer_horizontal,
                    "search_left": cls_def.linking_rule.search_left,
                    "tilted_ok": cls_def.linking_rule.tilted_ok,
                    "block": cls_def.linking_rule.block,
                    "fallback_dy_steps": cls_def.linking_rule.fallback_dy_steps,
                }

        # Build FIXED_TEXT_CLASSES from config (classes with fixed_text defined)
        # Must be built FIRST because NO_OCR_CLASSES excludes fixed_text classes
        global NO_OCR_CLASSES, FIXED_TEXT_CLASSES
        FIXED_TEXT_CLASSES = {c.name: c.fixed_text for c in config.classes
                              if c.fixed_text is not None}

        # Build NO_OCR_CLASSES from config (classes where requires_ocr=False AND no fixed_text)
        # Classes with fixed_text are handled separately via FIXED_TEXT_CLASSES
        NO_OCR_CLASSES = [c.name for c in config.classes
                         if not c.requires_ocr and c.fixed_text is None]

        # Configure OCR module
        configure_ocr(config)
        
    def requestInterruption(self) -> None:
        self._is_interrupted = True
        super().requestInterruption()

    def run(self):
        try:
            # Extract base layout name for deterministic UUIDs
            base_layout_name = extract_base_layout_name(self.pdf_path)
            if DEBUG_YOLO:
                print(f"\n Base layout name for UUID generation: '{base_layout_name}'")

            # Helper function to generate deterministic UUID
            def make_uuid(element_dict):
                """Generate deterministic UUID for an element"""
                return generate_deterministic_uuid(element_dict, base_layout_name)
            
            # --- helper to emit weighted progress ---
            def emit_progress(pages_done: int, sub: float):
                if n_pages > 0:
                    per_page = 0.95 / n_pages
                    pct = 0.05 + pages_done * per_page + sub * per_page
                else:
                    pct = 1.0
                self.progress.emit(int(round(100 * max(0.0, min(1.0, pct)))))

            # Define defaults
            model = None
            n_pages = 0
            all_rows = []
            page_bgr_arrays = {}
            page_dfs = {}
            track_skeleton = None  #  Define at top level
            gks_dets = []  #  Define at top level to avoid undefined variable
            all_gks_dets = []  #  Accumulate GKS from all pages for Tier 3/4 fallbacks

            # 1. ALWAYS get page count
            if self._is_image_file:
                # Image files are single-page
                n_pages = 1
            else:
                # PDF: get page count
                info = pdfinfo_from_path(self.pdf_path, poppler_path=POPPLER_PATH)
                n_pages = int(info["Pages"])

            # 2. CONDITIONALLY load model
            if self.run_analysis:
                # -------- Model load (5%) --------
                self.status.emit("Lade YOLO-Modell... (kann 30-60 Sekunden dauern)")
                model = YOLO(self.model_path)
                self.progress.emit(5)
                self.status.emit("YOLO-Modell geladen.")
                set_classes_from_model(model)
                self.status.emit(f"Erkennbare Klassen ({len(CLASSES)}): {', '.join(CLASSES)}")
                
                #  DIAGNOSTIC: Verify class order
                if DEBUG_YOLO:
                    print(f"\n{'='*70}")
                    print(f"CLASS ORDER VERIFICATION")
                    print(f"{'='*70}")

                    critical_classes = {
                        9: 'prellbock',
                        10: 'haltetafel',
                        11: 'weichenende',
                    }

                    all_correct = True
                    for idx, expected in critical_classes.items():
                        actual = CLASSES[idx] if idx < len(CLASSES) else '(missing)'
                        status = '' if actual == expected else ''
                        print(f"[{idx:2d}] {status} Expected: '{expected:15s}' | Got: '{actual}'")
                        if actual != expected:
                            all_correct = False

                    if all_correct:
                        print(f"\nClass order is CORRECT!")
                    else:
                        print(f"\nClass order is WRONG! Check your config.py")

                    print(f"\nAliasing test:")
                    print(f"canon_name('weichenende') → '{canon_name('weichenende')}'  (should be 'weichenende')")
                    print(f"canon_name('prellbock')  → '{canon_name('prellbock')}'   (should be 'prellbock')")
                    print(f"canon_name('haltetafel')  → '{canon_name('haltetafel')}'   (should be 'haltetafel')")

                    print(f"{'='*70}\n")

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
                missing_rules = [k for k in LINK_RULES if not _class_present(k)]
            
            else:
                self.progress.emit(5)

            # per-page subweights sum to 1.0
            W = dict(raster=0.15, prep=0.05, det=0.35, ocr_c=0.20, ocr_a=0.15, link=0.10)

            for pidx in range(1, n_pages + 1):
                if self._is_interrupted:
                    break
                
                # --- RASTERIZING / IMAGE LOADING (ALWAYS RUNS) ---
                emit_progress(pidx - 1, 0.0)
                t_load = time.perf_counter()

                if self._is_image_file:
                    # Load image directly with PIL (no conversion needed)
                    pil = Image.open(self.file_path)
                    # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
                    if pil.mode != 'RGB':
                        pil = pil.convert('RGB')
                else:
                    # PDF: Rasterize at specified DPI
                    pil = convert_from_path(
                        self.pdf_path, dpi=DPI, poppler_path=POPPLER_PATH,
                        first_page=pidx, last_page=pidx, fmt="png",
                        thread_count=2, strict=False
                    )[0]

                emit_progress(pidx - 1, W['raster'])

                if self._is_interrupted:
                    break

                bgr_color = pil_to_bgr(pil)

                # Validate image was loaded correctly
                if bgr_color is None or bgr_color.size == 0:
                    print(f"Error: Page {pidx} returned empty image from pil_to_bgr")
                    continue

                print(f"Page {pidx}: Original image size {bgr_color.shape[1]}x{bgr_color.shape[0]}")

                # Auto-rotate to landscape if enabled (Antwerp feature)
                if self.config and self.config.detection.auto_landscape:
                    bgr_color, was_rotated = ensure_landscape(
                        bgr_color,
                        rotation_direction=self.config.detection.landscape_rotation_direction
                    )
                    if was_rotated:
                        print(f"Page {pidx}: Rotated to landscape -> {bgr_color.shape[1]}x{bgr_color.shape[0]}")

                # Store FULL image for display (before any cropping)
                # Coordinates will be stored in full image space for consistent save/load
                full_bgr_color = bgr_color.copy()

                # Initialize crop offsets (used to convert detection coords to full image space)
                crop_t = crop_l = 0

                # DEBUG: Track full image dimensions for verification
                full_h, full_w = full_bgr_color.shape[:2]
                if DEBUG_DATABASE:
                    print(f"DEBUG: Page {pidx} - Full image size: {full_w}x{full_h}")

                # Apply 4-sided cropping if configured (for detection only)
                if self.config and (self.config.detection.crop_top or self.config.detection.crop_bottom or
                    self.config.detection.crop_left or self.config.detection.crop_right):
                    h, w = bgr_color.shape[:2]
                    crop_t = self.config.detection.crop_top
                    crop_b = self.config.detection.crop_bottom
                    crop_l = self.config.detection.crop_left
                    crop_r = self.config.detection.crop_right

                    # Calculate remaining dimensions after crop
                    remaining_h = h - crop_t - crop_b
                    remaining_w = w - crop_l - crop_r

                    # Only crop if we have at least 100px remaining in each dimension
                    if remaining_h >= 100 and remaining_w >= 100:
                        bgr_color = bgr_color[crop_t:h-crop_b, crop_l:w-crop_r]
                        print(f"Cropped for detection: {w}x{h} -> {bgr_color.shape[1]}x{bgr_color.shape[0]}")
                        if DEBUG_DATABASE:
                            print(f"DEBUG: Crop offsets that will be applied: crop_l={crop_l}, crop_t={crop_t}")
                    else:
                        print(f"Warning: Crop values too large for image ({w}x{h}), "
                              f"remaining would be {remaining_w}x{remaining_h}, skipping crop")
                        # Reset offsets since we didn't crop
                        crop_t = crop_l = 0

                df_page = pd.DataFrame()

                if self.run_analysis:
                    self.status.emit("Objekterkennung läuft...")
                    
                    _ = tile_image(bgr_color, tile=TILE_SIZE, overlap_pct=OVERLAP_PCT)
                    emit_progress(pidx - 1, W['raster'] + W['prep'])

                    if self._is_interrupted:
                        break

                    t_det = time.perf_counter()
                    # Use combined detection: YOLO + Custom Symbols
                    # HSV-trained model handles colors directly (no preprocessing needed)
                    all_dets = run_combined_detection(model, bgr_color, self.config, detect_custom=True)

                    # Separate confirmed and uncertain detections
                    confirmed_dets = [d for d in all_dets if d.get('detection_status', 'confirmed') == 'confirmed']
                    page_uncertain = [d for d in all_dets if d.get('detection_status') == 'uncertain']

                    # Add page info to uncertain detections and store them
                    for ud in page_uncertain:
                        ud['page'] = pidx
                    self.uncertain_detections.extend(page_uncertain)

                    if page_uncertain and DEBUG_YOLO:
                        print(f"[page {pidx}] Found {len(page_uncertain)} uncertain detections for user review")

                    # Continue processing with confirmed detections only
                    dets = confirmed_dets

                    # Count by source (YOLO vs CUSTOM)
                    yolo_count = sum(1 for d in dets if not d.get('is_custom_symbol', False))
                    custom_count = sum(1 for d in dets if d.get('is_custom_symbol', False))

                    class_counts = {}
                    for d in dets:
                        raw = d.get('raw_name', '?')
                        canon = d.get('name', '?')

                        if canon not in class_counts:
                            class_counts[canon] = {'raw': raw, 'count': 0, 'custom': 0}
                        class_counts[canon]['count'] += 1
                        if d.get('is_custom_symbol', False):
                            class_counts[canon]['custom'] += 1

                    if DEBUG_YOLO:
                        for canon, info in sorted(class_counts.items()):
                            custom_marker = f" [+{info['custom']} custom]" if info['custom'] > 0 else ""
                            print(f"{canon:20s} (raw: {info['raw']:20s}) → {info['count']:3d} detections{custom_marker}")

                        print(f"{'='*60}\n")
                    dt_det = time.perf_counter() - t_det
                    cnt = Counter(d['name'] for d in dets)
                    summary = ", ".join(f"{k}:{v}" for k, v in sorted(cnt.items()))

                    # Status message - show custom symbol breakdown
                    total_objects = yolo_count + custom_count

                    # Build custom symbol breakdown
                    custom_breakdown = ""
                    if custom_count > 0:
                        custom_by_name = {}
                        for d in dets:
                            if d.get('is_custom_symbol', False):
                                name = d['name']
                                custom_by_name[name] = custom_by_name.get(name, 0) + 1

                        custom_parts = [f"{count} {name}" for name, count in sorted(custom_by_name.items())]
                        custom_breakdown = f" (Custom: {', '.join(custom_parts)})"

                    self.status.emit(f"Objekterkennung: {total_objects} Objekte erkannt{custom_breakdown}")
                    emit_progress(pidx - 1, W['raster'] + W['prep'] + W['det'])

                    mask_red, mask_yel = color_masks(bgr_color)
                    coords = [d for d in dets if d["name"] == "coordinate"]
                    anchors = [d for d in dets if d["name"] != "coordinate"]
                    self.status.emit("Texterkennung läuft...")

                    # Coordinate OCR
                    coord_meta = {}
                    t_ocr = time.perf_counter()

                    def _do_coord(c):
                        try:
                            txt = ocr_coordinate_unified(c, bgr_color, self.ocr_engine, config=self.config, debug_class="coordinate")
                        except Exception:
                            txt = ""
                        
                        if DEBUG_ANGLE_ROUTING and txt:
                            print(f"\n   [OCR Coordinate] Raw OCR output: '{txt}'")

                        # Skip Wien-specific cleaning for simple OCR mode (Antwerp)
                        # Simple OCR already cleans with _clean_antwerp_coordinate
                        if self.config.ocr.use_simple_ocr:
                            txt_fixed = txt  # Already cleaned by ocr_simple_coordinate
                        else:
                            txt_cleaned = _clean_coordinate_overlap(txt)
                            txt_fixed = _fix_coordinate_brackets(txt_cleaned)
                            txt_fixed = re.sub(r'\s*[a-zA-Z]\s*$', '', txt_fixed)
                            txt_fixed = re.sub(r'\s*[|/\\]\s*$', '', txt_fixed)

                            # Debug output for Wien cleaning steps
                            if DEBUG_ANGLE_ROUTING and txt:
                                if txt_cleaned != txt:
                                    print(f"[OCR Coordinate] After clean_overlap: '{txt}' → '{txt_cleaned}'")
                                if txt_fixed != txt_cleaned:
                                    print(f"[OCR Coordinate] After fix_brackets: '{txt_cleaned}' → '{txt_fixed}'")
                        
                        val, gi = parse_coord(txt_fixed, self.config)
                        
                        if DEBUG_ANGLE_ROUTING and txt:
                            print(f"[OCR Coordinate] Final parse result: value={val}, gi_gl={gi}")
                            print(f"[OCR Coordinate] Complete flow: '{txt}' → '{txt_fixed}' → value={val}, gi_gl={gi}\n")
                        
                        c_color = box_color(mask_red, mask_yel, c["x1"], c["y1"], c["x2"], c["y2"])
                        # Ensure coordinate text is uppercase
                        txt_fixed = txt_fixed.upper() if txt_fixed else txt_fixed
                        return (id(c), dict(text=txt_fixed, value=val, gi=gi, color=c_color))

                    if coords:
                        with ThreadPoolExecutor(max_workers=MAX_OCR_WORKERS) as ex:
                            for f in as_completed([ex.submit(_do_coord, c) for c in coords]):
                                k, v = f.result()
                                coord_meta[k] = v

                    self.status.emit("Texterkennung abgeschlossen")
                    emit_progress(pidx - 1, W['raster'] + W['prep'] + W['det'] + W['ocr_c'])

                    if self._is_interrupted:
                        break

                    # Anchors OCR
                    anchor_results = []

                    # Load custom symbol config for OCR
                    custom_symbol_config = {}
                    loaded_from_db = False

                    # Try loading from database first
                    try:
                        from database_sqlite import is_db_available, get_all_custom_symbols
                        if is_db_available():
                            db_symbols = get_all_custom_symbols()
                            for sym_data in db_symbols:
                                name = sym_data['symbol_name']
                                cfg = sym_data['config']
                                custom_symbol_config[name] = cfg
                            if db_symbols:
                                loaded_from_db = True
                                logger.info(f"Loaded {len(custom_symbol_config)} custom symbol configs from database for OCR")
                    except Exception as e:
                        logger.debug(f"Could not load custom symbols from database: {e}")

                    # Fall back to JSON file if database not available or empty
                    if not loaded_from_db:
                        try:
                            import json
                            from paths import get_custom_symbols_path
                            config_path = get_custom_symbols_path()
                            if config_path.exists():
                                with open(config_path, 'r') as f:
                                    custom_symbol_config = json.load(f)
                                logger.info(f"Loaded {len(custom_symbol_config)} custom symbol configs from JSON for OCR")
                        except Exception as e:
                            logger.debug(f"Could not load custom symbols from JSON: {e}")

                    # DEBUG: Print loaded configs
                    if DEBUG_CUSTOM_SYMBOLS:
                        print(f"\nDEBUG: Loaded {len(custom_symbol_config)} custom symbol configs:")
                        for sym_name, sym_cfg in custom_symbol_config.items():
                            has_text = sym_cfg.get("has_text", False)
                            text_region = sym_cfg.get("text_region_offset", None)
                            print(f"  - {sym_name}: has_text={has_text}, text_region_offset={text_region}")

                    def _do_anchor(a):
                        a_color = box_color(mask_red, mask_yel, a["x1"], a["y1"], a["x2"], a["y2"])
                        #  Initialize all variables at the top to avoid UnboundLocalError
                        ocr_bbox = None
                        ocr_position = None
                        ocr_conf = 0.0
                        weichen_coords = []

                        if a["name"] in NO_OCR_CLASSES:
                            name_txt = ""
                        elif a["name"] in FIXED_TEXT_CLASSES:
                            name_txt = FIXED_TEXT_CLASSES[a["name"]]
                        elif a.get("is_custom_symbol") and a["name"] in custom_symbol_config:
                            # Custom symbol with specific text position (or precise region)
                            sym_cfg = custom_symbol_config[a["name"]]
                            if DEBUG_CUSTOM_SYMBOLS:
                                print(f"\nProcessing custom symbol: {a['name']}")
                                print(f"Config: has_text={sym_cfg.get('has_text', False)}, text_position={sym_cfg.get('text_position')}, text_region_offset={sym_cfg.get('text_region_offset')}")
                            if sym_cfg.get("has_text", False):
                                text_pos = sym_cfg.get("text_position", "left")
                                text_region = sym_cfg.get("text_region_offset", None)
                                if DEBUG_CUSTOM_SYMBOLS:
                                    print(f"Calling ocr_custom_symbol_text with text_region_offset={text_region}")
                                # ocr_custom_symbol_text now returns (text, bbox, position, confidence)
                                name_txt, ocr_bbox, ocr_position, ocr_conf = ocr_custom_symbol_text(
                                    a, bgr_color, text_pos, self.ocr_engine,
                                    text_region_offset=text_region,
                                    debug_class=a.get("name", "custom_symbol")
                                )
                                # Debug: Show OCR bbox result
                                if DEBUG_CUSTOM_SYMBOLS:
                                    if ocr_bbox:
                                        print(f"OCR bbox returned: {ocr_bbox}, position={ocr_position}, conf={ocr_conf:.2f}")
                                    else:
                                        print(f"No OCR bbox returned (text='{name_txt}')")
                            else:
                                if DEBUG_CUSTOM_SYMBOLS:
                                    print(f"Symbol has has_text=False, skipping OCR")
                                name_txt = ""
                        elif a.get("is_custom_symbol"):
                            # Custom symbol but NOT in config - this is the problem case!
                            if DEBUG_CUSTOM_SYMBOLS:
                                print(f"\n WARNING: Custom symbol '{a['name']}' detected but NOT in custom_symbol_config!")
                                print(f"Available configs: {list(custom_symbol_config.keys())}")
                            ocr_result = ocr_anchor_name(a, bgr_color, self.ocr_engine, config=self.config)
                            name_txt = ocr_result
                        else:
                            ocr_result = ocr_anchor_name(a, bgr_color, self.ocr_engine, config=self.config)
                            if a["name"] == "weichen_block":
                                parsed = parse_weichen_block(ocr_result)
                                name_txt = parsed['id']
                                weichen_coords = parsed['coordinates']
                                # Uppercase weichen coordinates
                                weichen_coords = [c.upper() if c else c for c in weichen_coords]
                            else:
                                name_txt = ocr_result
                        # Ensure anchor text is uppercase
                        name_txt = name_txt.upper() if name_txt else name_txt
                        return (a, a_color, name_txt, weichen_coords, ocr_bbox, ocr_position, ocr_conf)

                    if anchors:
                        with ThreadPoolExecutor(max_workers=MAX_OCR_WORKERS) as ex:
                            for f in as_completed([ex.submit(_do_anchor, a) for a in anchors]):
                                anchor_results.append(f.result())

                    emit_progress(pidx - 1, W['raster'] + W['prep'] + W['det'] + W['ocr_c'] + W['ocr_a'])
                    
                    # ========================================
                    # STEP: TRACK DETECTION (before Fahrtrichtung)
                    # ========================================
                    track_bounds = None  #  Initialize track_bounds

                    if self.detect_tracks:
                        if DEBUG_TRACK:
                            print(f"\n{'='*70}")
                            print(f"  TRACK DETECTION - Page {pidx}")
                            print(f"{'='*70}")

                        try:
                            from track_detection import detect_main_tracks
                            from core.linking import get_track_bounds  #  Import track bounds function

                            def track_progress(msg):
                                self.track_detection_progress.emit(msg)
                                if DEBUG_TRACK:
                                    print(msg)

                            # Detect tracks BEFORE Fahrtrichtung detection
                            # Get title block margin params from config
                            det_cfg = self.config.detection if self.config else None
                            if EXCLUDE_LEGEND_STRIP:
                                margin_width = LEGEND_STRIP_WIDTH_PERCENT
                                margin_height = det_cfg.title_block_margin_height if det_cfg else 100
                            else:
                                margin_width = det_cfg.title_block_margin_width_default if det_cfg else 8
                                margin_height = det_cfg.title_block_margin_height_default if det_cfg else 25

                            # For images, pass the BGR array directly; for PDFs, use pdf_path
                            if self._is_image_file:
                                track_skeleton, _, _ = detect_main_tracks(
                                    image_array=bgr_color,
                                    tile_size=TILE_SIZE,
                                    overlap=int(TILE_SIZE * OVERLAP_PCT / 100),
                                    title_block_margin_width=margin_width,
                                    title_block_margin_height=margin_height,
                                    progress_callback=track_progress
                                )
                            else:
                                track_skeleton, _, _ = detect_main_tracks(
                                    pdf_path=self.pdf_path,
                                    page_idx=pidx - 1,  # 0-indexed
                                    dpi=DPI,
                                    tile_size=TILE_SIZE,
                                    overlap=int(TILE_SIZE * OVERLAP_PCT / 100),
                                    title_block_margin_width=margin_width,
                                    title_block_margin_height=margin_height,
                                    progress_callback=track_progress
                                )
                            
                            track_pixels = np.count_nonzero(track_skeleton)
                            if DEBUG_TRACK:
                                print(f"Track detection complete: {track_pixels} pixels")
                                print(f"Track skeleton shape: {track_skeleton.shape}")

                            #  Calculate track bounds
                            if track_skeleton is not None and track_pixels > 0:
                                track_bounds = get_track_bounds(track_skeleton)
                                if DEBUG_TRACK:
                                    print(f"Track bounds: Y=[{track_bounds['y_min']}, {track_bounds['y_max']}] (height={track_bounds['height']}px)")
                                    print(f"X=[{track_bounds['x_min']}, {track_bounds['x_max']}] (width={track_bounds['width']}px)")

                            if DEBUG_TRACK:
                                print(f"{'='*70}\n")

                        except Exception as e:
                            import traceback
                            if DEBUG_TRACK:
                                print(f"Track detection failed: {e}")
                            traceback.print_exc()
                            self.status.emit("Gleiserkennung fehlgeschlagen")
                            track_skeleton = None
                            track_bounds = None  #  Ensure track_bounds is None on failure
                    
                    # ========================================
                    # STEP: FAHRTRICHTUNG DETECTION (GKS ONLY)
                    # ========================================
                    if DEBUG_LINKING:
                        print(f"\n{'='*70}")
                        print(f" FAHRTRICHTUNG DETECTION - Page {pidx} (GKS-based only)")
                        print(f"{'='*70}")

                    signal_dets = [a for a, _, _, _, _, _, _ in anchor_results if a["name"].lower() == "signal"]
                    gks_dets = [a for a, _, _, _, _, _, _ in anchor_results if a["name"] == "gks_gesteuert"]
                    fahrtrichtung_map = {}

                    if DEBUG_LINKING:
                        print(f"Signals to process: {len(signal_dets)}")
                        print(f"GKS boxes available: {len(gks_dets)}")

                    #  Accumulate GKS with page info for Tier 3/4 fallbacks
                    for gks_det in gks_dets:
                        gks_copy = gks_det.copy()
                        gks_copy['page'] = pidx
                        all_gks_dets.append(gks_copy)

                    #  GKS-based detection ONLY (no track fallback yet)
                    for signal_det in signal_dets:
                        signal_text = None
                        for a, _, name_txt, _, _, _, _ in anchor_results:
                            if id(a) == id(signal_det):
                                signal_text = name_txt
                                break
                        signal_det["text"] = signal_text or ""
                        
                        # GKS-based detection only - use config spatial params
                        sp_gks = self.config.spatial if self.config else None
                        fahrtrichtung = detect_fahrtrichtung(
                            signal_det,
                            gks_dets,
                            track_skeleton=None,  #  Don't use track yet
                            track_bounds=None,    #  NEW: Pass track_bounds (None for now)
                            max_distance=sp_gks.signal_gks_max_distance if sp_gks else 250,
                            dy_min=sp_gks.signal_gks_dy_min if sp_gks else 30,
                            dy_max=sp_gks.signal_gks_dy_max if sp_gks else 200,
                            dx_tolerance_left=sp_gks.signal_gks_dx_tolerance_left if sp_gks else 120,
                            dx_tolerance_right=sp_gks.signal_gks_dx_tolerance_right if sp_gks else 120,
                            angle_tolerance=sp_gks.signal_gks_angle_tolerance if sp_gks else 20,
                            config=self.config
                        )
                        
                        if fahrtrichtung:
                            #  CHANGE 1: Store as dict with source tracking
                            fahrtrichtung_map[id(signal_det)] = {
                                'fahrtrichtung': fahrtrichtung,
                                'source': 'gks'
                            }
                            if DEBUG_LINKING:
                                print(f"Signal '{signal_text}': Fahrtrichtung = {fahrtrichtung} (GKS)")
                        else:
                            if DEBUG_LINKING:
                                print(f"Signal '{signal_text}': No Fahrtrichtung from GKS")

                    if DEBUG_LINKING:
                        print(f"\n{'='*70}")
                        print(f"Total Fahrtrichtung from GKS: {len(fahrtrichtung_map)}/{len(signal_dets)}")
                        print(f"{'='*70}\n")

                    #  NEW: Haltepunkt-Signal-Coordinate grouping detection
                    if DEBUG_LINKING:
                        print(f"\n{'='*70}")
                        print(f" HALTEPUNKT GROUP DETECTION - Page {pidx}")
                        print(f"{'='*70}")

                    haltepunkt_dets = [a for a, _, _, _, _, _, _ in anchor_results if a["name"] == "haltepunkt"]
                    haltepunkt_groups = {}

                    if DEBUG_LINKING:
                        print(f"Haltepunkt detections: {len(haltepunkt_dets)}")
                    
                    # Prepare coordinate detections with their OCR text
                    coord_dets_with_text = []
                    for c in coords:
                        meta = coord_meta.get(id(c), {})
                        c_with_text = {
                            'x1': c.get('x1'),
                            'y1': c.get('y1'),
                            'x2': c.get('x2'),
                            'y2': c.get('y2'),
                            'cx1': c.get('x1'),
                            'cy1': c.get('y1'),
                            'cx2': c.get('x2'),
                            'cy2': c.get('y2'),
                            'angle': c.get('angle', 0.0),
                            'angle_raw': c.get('angle_raw', 0.0),
                            'text': meta.get('text', '')
                        }
                        coord_dets_with_text.append(c_with_text)

                    #  NEW: Track which signal detections are haltepunkt-referenced
                    haltepunkt_referenced_signals = set()

                    # Detect groups for each haltepunkt - get all spatial params from config
                    sp_cfg = self.config.spatial if self.config else None
                    for haltepunkt_det in haltepunkt_dets:
                        group = detect_haltepunkt_signal_group(
                            haltepunkt_det,
                            signal_dets,
                            coord_dets_with_text,
                            max_distance=sp_cfg.haltepunkt_cluster_max_distance if sp_cfg else 250,
                            dy_signal_min=sp_cfg.haltepunkt_signal_dy_min if sp_cfg else 30,
                            dy_signal_max=sp_cfg.haltepunkt_signal_dy_max if sp_cfg else 200,
                            dy_coord_min=sp_cfg.haltepunkt_coord_dy_min if sp_cfg else 20,
                            dy_coord_max=sp_cfg.haltepunkt_coord_dy_max if sp_cfg else 150,
                            dx_tolerance=sp_cfg.haltepunkt_dx_tolerance if sp_cfg else 100,
                            angle_tolerance=sp_cfg.haltepunkt_angle_tolerance if sp_cfg else 20.0,
                            config=self.config
                        )
                        
                        if group:
                            haltepunkt_groups[id(haltepunkt_det)] = group

                            #  Mark the signal detection to skip
                            if group.get('signal_det'):
                                haltepunkt_referenced_signals.add(id(group['signal_det']))
                                if DEBUG_LINKING:
                                    print(f"Haltepunkt group: signal='{group['signal']}' (will skip signal processing)")
                            else:
                                if DEBUG_LINKING:
                                    print(f"Haltepunkt group: signal='{group['signal']}', coordinate='{group.get('coordinate', '')}'")

                    if DEBUG_LINKING:
                        print(f"Total groups detected: {len(haltepunkt_groups)}")
                        print(f"Signals to skip: {len(haltepunkt_referenced_signals)}")
                        print(f"{'='*70}\n")

                    # Linking + rows
                    self.status.emit("Symbolzuordnung läuft...")
                    used_coord_ids = set()
                    learned_patterns = {}

                    #  STEP 1: Build a map of GKS → coordinate FIRST
                    gks_coord_map = {}

                    if DEBUG_LINKING:
                        print(f"\n{'='*70}")
                        print(f" STEP 1: Pre-linking GKS boxes to coordinates")
                        print(f"{'='*70}")

                    for (a, a_color, name_txt, weichen_coords, ocr_bbox, ocr_position, ocr_conf) in anchor_results:
                        if a["name"] in ["gks_festkodiert", "gks_gesteuert"]:
                            available_coords = [c for c in coords if id(c) not in used_coord_ids]
                            linked = link_anchor_to_coord(a, available_coords, config=self.config, learned_patterns=learned_patterns)
                            
                            if linked is not None:
                                used_coord_ids.add(id(linked))
                                gks_coord_map[id(a)] = linked
                                
                                # Record pattern
                                dx_offset = linked["cx"] - a["cx"]
                                dy_offset = linked["cy"] - a["cy"]
                                if a["name"] not in learned_patterns:
                                    learned_patterns[a["name"]] = []
                                learned_patterns[a["name"]].append((dx_offset, dy_offset))
                                
                                meta = coord_meta.get(id(linked), {})
                                coord_txt = meta.get("text", "?")
                                if coord_txt:
                                    coord_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', coord_txt)
                                    coord_txt = re.sub(r'\s*[|/\\]\s*$', '', coord_txt)
                                    coord_txt = ' '.join(coord_txt.split()).strip()
                                    if DEBUG_LINKING:
                                        print(f"GKS '{name_txt}' → coordinate '{coord_txt}'")

                    if DEBUG_LINKING:
                        print(f"Total GKS linked: {len(gks_coord_map)}")
                        print(f"{'='*70}\n")

                    # ========================================
                    #  STEP 1B: Pre-link SVERBINDER to coordinates
                    # ========================================
                    if DEBUG_LINKING:
                        print(f"\n{'='*70}")
                        print(f" STEP 1B: Pre-linking Sverbinder to coordinates")
                        print(f"{'='*70}")

                    sverbinder_coord_map = {}
                    sverbinder_dets = [a for a, _, _, _, _, _, _ in anchor_results if a["name"] == "sverbinder"]

                    if DEBUG_LINKING:
                        print(f"Sverbinder detections: {len(sverbinder_dets)}")

                    for sverbinder_det in sverbinder_dets:
                        available_coords = [c for c in coords if id(c) not in used_coord_ids]
                        linked = link_anchor_to_coord(sverbinder_det, available_coords, config=self.config, learned_patterns=learned_patterns)
                        
                        if linked is not None:
                            used_coord_ids.add(id(linked))
                            sverbinder_coord_map[id(sverbinder_det)] = linked
                            
                            # Record pattern
                            dx_offset = linked["cx"] - sverbinder_det["cx"]
                            dy_offset = linked["cy"] - sverbinder_det["cy"]
                            if sverbinder_det["name"] not in learned_patterns:
                                learned_patterns[sverbinder_det["name"]] = []
                            learned_patterns[sverbinder_det["name"]].append((dx_offset, dy_offset))
                            
                            meta = coord_meta.get(id(linked), {})
                            coord_txt = meta.get("text", "?")
                            if coord_txt:
                                coord_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', coord_txt)
                                coord_txt = re.sub(r'\s*[|/\\]\s*$', '', coord_txt)
                                coord_txt = ' '.join(coord_txt.split()).strip()
                                if DEBUG_LINKING:
                                    print(f"Sverbinder → coordinate '{coord_txt}'")

                    if DEBUG_LINKING:
                        print(f"Total Sverbinder linked: {len(sverbinder_coord_map)}")
                        print(f"{'='*70}\n")

                    # ========================================
                    #  STEP 1C: Pre-link HALTEPUNKT to coordinates (soft-claim)
                    # ========================================
                    if DEBUG_LINKING:
                        print(f"\n{'='*70}")
                        print(f" STEP 1C: Pre-linking Haltepunkt to coordinates (soft-claim)")
                        print(f"{'='*70}")

                    haltepunkt_coord_ids = set()  # Soft-claimed by haltepunkt
                    haltepunkt_coord_map = {}  # Map haltepunkt ID -> coordinate

                    for haltepunkt_det in haltepunkt_dets:
                        group = haltepunkt_groups.get(id(haltepunkt_det))

                        # Try to get coordinate from group detection first
                        if group and group.get('coordinate'):
                            coord_txt = group['coordinate']
                            # Find the coordinate detection
                            for c in coords:
                                meta = coord_meta.get(id(c), {})
                                if meta.get('text') == coord_txt:
                                    haltepunkt_coord_ids.add(id(c))
                                    haltepunkt_coord_map[id(haltepunkt_det)] = c
                                    if DEBUG_LINKING:
                                        print(f"Haltepunkt (group) → '{coord_txt}' (soft-claimed)")
                                    break
                        else:
                            # Direct linking fallback - exclude sverbinder coords
                            sverbinder_coord_id_set = set(id(c) for c in sverbinder_coord_map.values())
                            available_coords = [c for c in coords if id(c) not in used_coord_ids and id(c) not in sverbinder_coord_id_set]

                            linked = link_anchor_to_coord(haltepunkt_det, available_coords, config=self.config, learned_patterns=learned_patterns)

                            if linked is not None:
                                haltepunkt_coord_ids.add(id(linked))
                                haltepunkt_coord_map[id(haltepunkt_det)] = linked

                                meta = coord_meta.get(id(linked), {})
                                coord_txt = meta.get("text", "?")
                                if DEBUG_LINKING:
                                    print(f"Haltepunkt (direct) → '{coord_txt}' (soft-claimed)")

                    if DEBUG_LINKING:
                        print(f"Total Haltepunkt soft-claimed: {len(haltepunkt_coord_ids)}")
                        print(f"{'='*70}\n")

                    # ========================================================================
                    # STEP 1D: Link symbol-only anchors to text_id labels (ANTWERP ONLY)
                    # ========================================================================
                    # For Antwerp profile: Symbol-only classes (signal, mech_point, etc.) need
                    # to be linked to external text_id labels detected separately by YOLO.
                    # This is detection-to-detection spatial linking, not OCR-based.
                    if (self.config is not None and
                        hasattr(self.config, 'ocr') and
                        self.config.ocr.use_simple_ocr):  # Antwerp profile marker

                        if DEBUG_LINKING:
                            print(f"\n{'='*70}")
                            print(f" STEP 1D: Linking symbol-only anchors to text_id (Antwerp)")
                            print(f"{'='*70}")

                        # Extract text_id detections from anchor_results
                        text_id_detections = []
                        for (a, a_color, name_txt, weichen_coords, ocr_bbox, ocr_position, ocr_conf) in anchor_results:
                            if a["name"] == "text_id":
                                # Store text_id detection with its OCR'd text
                                a["anchor_text"] = name_txt  # Copy OCR text to detection dict
                                text_id_detections.append(a)

                        if DEBUG_LINKING:
                            print(f"Found {len(text_id_detections)} text_id detections")

                        # Link each symbol-only anchor to nearest text_id
                        text_id_links = {}  # Map anchor_id -> text_id detection
                        used_text_id_ids = set()

                        for (a, a_color, name_txt, weichen_coords, ocr_bbox, ocr_position, ocr_conf) in anchor_results:
                            # Skip text_id (they are the source, not target)
                            if a["name"] == "text_id":
                                continue

                            # Check if this class has name_search_rule configured
                            cls_def = self.config.get_class_by_name(a["name"])
                            if cls_def and cls_def.name_search_rule:
                                # Check if any search direction is enabled
                                has_name_search = (cls_def.name_search_rule.inside or
                                                   cls_def.name_search_rule.left or
                                                   cls_def.name_search_rule.right or
                                                   cls_def.name_search_rule.below or
                                                   cls_def.name_search_rule.above)

                                if has_name_search:
                                    # Filter out already-used text_ids
                                    available_text_ids = [tid for tid in text_id_detections
                                                          if id(tid) not in used_text_id_ids]

                                    # Link to nearest text_id (returns tuple: text_id, direction)
                                    linked_text_id, text_id_direction = link_anchor_to_text_id(a, available_text_ids, config=self.config)

                                    if linked_text_id is not None:
                                        # Store the link
                                        text_id_links[id(a)] = linked_text_id
                                        used_text_id_ids.add(id(linked_text_id))

                                        # Update anchor's anchor_text with text_id's text
                                        text_id_text = linked_text_id.get("anchor_text", linked_text_id.get("text", ""))
                                        a["anchor_text"] = text_id_text

                                        # Store text_id bbox for link_text_id_row_id tracking later
                                        a["text_id_x1"] = linked_text_id.get("x1")
                                        a["text_id_y1"] = linked_text_id.get("y1")
                                        a["text_id_x2"] = linked_text_id.get("x2")
                                        a["text_id_y2"] = linked_text_id.get("y2")

                                        # Store vertical direction in anchor (used for Phase 2/3 coordinate search)
                                        # For 'above'/'below' directions, use directly
                                        # For 'left'/'right' directions, calculate Y relationship
                                        if text_id_direction in ['above', 'below']:
                                            a["ocr_region_source"] = text_id_direction
                                        elif text_id_direction in ['left', 'right']:
                                            # For horizontal text_ids, determine vertical position
                                            text_id_cy = linked_text_id.get("cy", 0)
                                            anchor_cy = a.get("cy", 0)
                                            if text_id_cy > anchor_cy:
                                                a["ocr_region_source"] = "below"  # text_id is below anchor
                                            elif text_id_cy < anchor_cy:
                                                a["ocr_region_source"] = "above"  # text_id is above anchor

                                        if DEBUG_LINKING:
                                            vertical_dir = a.get("ocr_region_source", "none")
                                            print(f"Linked {a['name']} → text_id '{text_id_text}' (dir={text_id_direction}, vertical={vertical_dir})")

                        if DEBUG_LINKING:
                            print(f"Total symbol-to-text_id links: {len(text_id_links)}")
                            print(f"{'='*70}\n")

                    # ========================================================================
                    # STEP 1E: Link Phase 1 elements to coordinates (ANTWERP ONLY)
                    # ========================================================================
                    # For Antwerp profile: Link bond/junction elements to coordinates using
                    # vertical alignment (above/below). Phase 1 elements:
                    # s_bond, short_bond, terminal_bond, insulation_joint, spie_loop
                    antwerp_coord_links = {}  # Map element id -> coordinate text
                    if (self.config is not None and
                        hasattr(self.config, 'ocr') and
                        self.config.ocr.use_simple_ocr):  # Antwerp profile marker

                        if DEBUG_LINKING:
                            print(f"\n{'='*70}")
                            print(f" STEP 1E: Linking Phase 1 elements to coordinates (Antwerp)")
                            print(f"{'='*70}")

                        # Extract all detections from anchor_results
                        # Note: ocr_region_source is already set by link_anchor_to_text_id() for signals
                        all_detections = [a for (a, a_color, name_txt, weichen_coords, ocr_bbox, ocr_position, ocr_conf) in anchor_results]

                        # Build coordinate detections from coords list with OCR text from coord_meta
                        # (coordinates are NOT in anchor_results - they're processed separately)
                        coord_detections = []
                        for c in coords:
                            c_id = id(c)
                            if c_id in coord_meta:
                                # Add OCR text to coordinate detection
                                c["text"] = coord_meta[c_id].get("text", "")
                                coord_detections.append(c)

                        if DEBUG_LINKING:
                            print(f"  Total detections: {len(all_detections)}, Coordinates: {len(coord_detections)}")
                            if coord_detections:
                                print(f"  Coordinate examples: {[c.get('text', '?') for c in coord_detections[:5]]}")

                        # Link elements to coordinates
                        antwerp_coord_links = link_antwerp_coordinates(
                            all_detections, coord_detections, config=self.config
                        )

                        # Apply coordinate links to detections
                        for (a, a_color, name_txt, weichen_coords, ocr_bbox, ocr_position, ocr_conf) in anchor_results:
                            if id(a) in antwerp_coord_links:
                                a["linked_coordinate"] = antwerp_coord_links[id(a)]
                                if DEBUG_LINKING:
                                    print(f"  Applied coordinate '{antwerp_coord_links[id(a)]}' to {a['name']}")

                        if DEBUG_LINKING:
                            print(f"Total element-to-coordinate links: {len(antwerp_coord_links)}")
                            print(f"{'='*70}\n")

                    #  STEP 2: Now process ALL elements (including haltetafel)
                    # Initialize counters for NO_OCR_CLASSES to generate unique names
                    # Note: haltepunkt has its own counter logic in its special handling section
                    no_ocr_counters = {cls: 1 for cls in NO_OCR_CLASSES if cls != "haltepunkt"}

                    for (a, a_color, name_txt, weichen_coords, ocr_bbox, ocr_position, ocr_conf) in anchor_results:
                        row_id = len(all_rows)
                        fahrtrichtung = None
                        fahrtrichtung_source = 'none'  #  CHANGE 2: Default source

                        # Generate counter-based names for NO_OCR_CLASSES (except haltepunkt which has special handling)
                        if a["name"] in no_ocr_counters:
                            # Check if STEP 1D already linked a text_id to this anchor (Antwerp only)
                            if "anchor_text" in a and a["anchor_text"]:
                                # Use the linked text_id name
                                name_txt = a["anchor_text"]
                            else:
                                # Generate counter-based name
                                name_txt = f"{a['name']} {no_ocr_counters[a['name']]}"
                                no_ocr_counters[a["name"]] += 1
                        
                        #  NEW: SKIP if this signal is haltepunkt-referenced
                        if a["name"].lower() == "signal" and id(a) in haltepunkt_referenced_signals:
                            if DEBUG_LINKING:
                                print(f"SKIPPING signal '{name_txt}' (haltepunkt-referenced)")
                            continue  #  Don't process this signal at all

                        if a["name"].lower() == "signal":
                            #  CHANGE 2: Extract fahrtrichtung and source from map
                            fahr_data = fahrtrichtung_map.get(id(a))
                            if fahr_data:
                                if isinstance(fahr_data, dict):
                                    #  NEW FORMAT: {'fahrtrichtung': 'A', 'source': 'gks'}
                                    fahrtrichtung = fahr_data.get('fahrtrichtung')
                                    fahrtrichtung_source = fahr_data.get('source', 'gks')
                                else:
                                    #  OLD FORMAT: Just the string 'A' or 'B' (backward compatibility)
                                    fahrtrichtung = fahr_data
                                    fahrtrichtung_source = 'gks'
                        
                        #  SPECIAL HANDLING FOR HALTEPUNKT
                        if a["name"] == "haltepunkt":
                            group = haltepunkt_groups.get(id(a))
                            haltepunkt_counter = sum(1 for r in all_rows if r['cls'] == 'haltepunkt') + 1
                            
                            # Get signal name from group
                            if group and group.get('signal'):
                                signal_text = group['signal']
                                haltepunkt_name = f"haltepunkt {haltepunkt_counter} ({signal_text})"
                            else:
                                haltepunkt_name = f"haltepunkt {haltepunkt_counter}"
                            
                            coord_txt, coord_val, gi = None, None, None
                            cbbox = (None, None, None, None)
                            
                            # ========================================
                            # STEP 1: Try to get coordinate from group detection
                            # ========================================
                            if group and group.get('coordinate'):
                                coord_txt = group['coordinate']
                                coord_val, gi = parse_coord(coord_txt, self.config)
                                
                                # Try to find the coordinate detection to get its bounding box
                                for c in coords:
                                    meta = coord_meta.get(id(c), {})
                                    if meta.get('text') == coord_txt:
                                        cbbox = (c["x1"], c["y1"], c["x2"], c["y2"])
                                        break
                                
                                if DEBUG_LINKING:
                                    print(f"Haltepunkt '{haltepunkt_name}' → '{coord_txt}' (from group detection)")

                            # ========================================
                            # STEP 2: Use pre-linked coordinate from STEP 1C
                            # ========================================
                            else:
                                # Get the pre-linked coordinate from haltepunkt_coord_map
                                pre_linked = haltepunkt_coord_map.get(id(a))

                                if pre_linked is not None:
                                    meta = coord_meta.get(id(pre_linked), {})
                                    coord_txt, coord_val, gi = meta.get("text"), meta.get("value"), meta.get("gi")
                                    cbbox = (pre_linked["x1"], pre_linked["y1"], pre_linked["x2"], pre_linked["y2"])

                                    if DEBUG_LINKING:
                                        print(f"Haltepunkt '{haltepunkt_name}' → '{coord_txt}' (from pre-linking)")
                                else:
                                    if DEBUG_LINKING:
                                        print(f"Haltepunkt '{haltepunkt_name}' → NO COORDINATE")
                            
                            # ========================================
                            # STEP 3: Create row
                            # ========================================
                            # Ensure text is uppercase
                            haltepunkt_name = haltepunkt_name.upper() if haltepunkt_name else haltepunkt_name
                            coord_txt = coord_txt.upper() if coord_txt else coord_txt

                            element_for_uuid = {
                                'cls': a["name"],
                                'page': pidx,
                                'obb_cx': a.get("obb_cx"),
                                'obb_cy': a.get("obb_cy"),
                                'anchor_text': haltepunkt_name,
                                'coord_text': coord_txt
                            }

                            # Add crop offsets to convert detection coords to full image space
                            # DEBUG: Log first detection's coordinate transformation
                            if DEBUG_DATABASE and len(all_rows) == 0:
                                print(f"DEBUG DETECT: First detection raw coords: x1={a['x1']}, y1={a['y1']}, x2={a['x2']}, y2={a['y2']}")
                                print(f"DEBUG DETECT: After offset (crop_l={crop_l}, crop_t={crop_t}): ax1={a['x1']+crop_l}, ay1={a['y1']+crop_t}")
                            all_rows.append(dict(
                                detection_id=make_uuid(element_for_uuid),
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=haltepunkt_name,
                                anchor_conf=ocr_conf,
                                coord_text=coord_txt,
                                coord_value=coord_val,
                                gi_gl=gi,
                                ax1=a["x1"] + crop_l, ay1=a["y1"] + crop_t, ax2=a["x2"] + crop_l, ay2=a["y2"] + crop_t,
                                cx1=cbbox[0] + crop_l if cbbox[0] is not None else None,
                                cy1=cbbox[1] + crop_t if cbbox[1] is not None else None,
                                cx2=cbbox[2] + crop_l if cbbox[2] is not None else None,
                                cy2=cbbox[3] + crop_t if cbbox[3] is not None else None,
                                angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=(a.get("obb_cx") + crop_l) if a.get("obb_cx") is not None else None,
                                obb_cy=(a.get("obb_cy") + crop_t) if a.get("obb_cy") is not None else None,
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=[(p[0] + crop_l, p[1] + crop_t) for p in (a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly"))] if a.get("poly") is not None else None,
                                ocr_x1=(ocr_bbox[0] + crop_l) if ocr_bbox else None,
                                ocr_y1=(ocr_bbox[1] + crop_t) if ocr_bbox else None,
                                ocr_x2=(ocr_bbox[2] + crop_l) if ocr_bbox else None,
                                ocr_y2=(ocr_bbox[3] + crop_t) if ocr_bbox else None,
                                ocr_region_source=a.get("ocr_region_source", ocr_position),
                                notes="", weichen_coordinates=[],
                                fahrtrichtung=None,
                                _fahrtrichtung_source='none',  #  CHANGE 3
                                # Antwerp-specific fields for persistence
                                text_id_x1=(a.get("text_id_x1") + crop_l) if a.get("text_id_x1") is not None else None,
                                text_id_y1=(a.get("text_id_y1") + crop_t) if a.get("text_id_y1") is not None else None,
                                text_id_x2=(a.get("text_id_x2") + crop_l) if a.get("text_id_x2") is not None else None,
                                text_id_y2=(a.get("text_id_y2") + crop_t) if a.get("text_id_y2") is not None else None,
                                linked_coordinate=a.get("linked_coordinate")
                            ))
                            # Debug: Verify OCR coords were stored
                            if ocr_bbox and DEBUG_LINKING:
                                print(f" Stored OCR coords for row {row_id}: ocr_x1={ocr_bbox[0]:.0f}, ocr_y1={ocr_bbox[1]:.0f}, ocr_x2={ocr_bbox[2]:.0f}, ocr_y2={ocr_bbox[3]:.0f}")
                            continue
                        
                        #  SPECIAL HANDLING FOR WEICHEN_BLOCK
                        if a["name"] == "weichen_block":
                            coord_text_combined = " | ".join(weichen_coords) if weichen_coords else None
                            
                            element_for_uuid = {
                                'cls': a["name"],
                                'page': pidx,
                                'obb_cx': a.get("obb_cx"),
                                'obb_cy': a.get("obb_cy"),
                                'anchor_text': name_txt,
                                'coord_text': coord_text_combined
                            }
                            
                            # Add crop offsets to convert detection coords to full image space
                            all_rows.append(dict(
                                detection_id=make_uuid(element_for_uuid),
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=name_txt, anchor_conf=ocr_conf, coord_text=coord_text_combined, coord_value=None, gi_gl=None,
                                ax1=a["x1"] + crop_l, ay1=a["y1"] + crop_t, ax2=a["x2"] + crop_l, ay2=a["y2"] + crop_t,
                                cx1=None, cy1=None, cx2=None, cy2=None, angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=(a.get("obb_cx") + crop_l) if a.get("obb_cx") is not None else None,
                                obb_cy=(a.get("obb_cy") + crop_t) if a.get("obb_cy") is not None else None,
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=[(p[0] + crop_l, p[1] + crop_t) for p in (a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly"))] if a.get("poly") is not None else None,
                                ocr_x1=(ocr_bbox[0] + crop_l) if ocr_bbox else None,
                                ocr_y1=(ocr_bbox[1] + crop_t) if ocr_bbox else None,
                                ocr_x2=(ocr_bbox[2] + crop_l) if ocr_bbox else None,
                                ocr_y2=(ocr_bbox[3] + crop_t) if ocr_bbox else None,
                                ocr_region_source=a.get("ocr_region_source", ocr_position),
                                notes="", weichen_coordinates=weichen_coords,
                                fahrtrichtung=None,
                                _fahrtrichtung_source='none',  #  CHANGE 3
                                # Antwerp-specific fields for persistence
                                text_id_x1=(a.get("text_id_x1") + crop_l) if a.get("text_id_x1") is not None else None,
                                text_id_y1=(a.get("text_id_y1") + crop_t) if a.get("text_id_y1") is not None else None,
                                text_id_x2=(a.get("text_id_x2") + crop_l) if a.get("text_id_x2") is not None else None,
                                text_id_y2=(a.get("text_id_y2") + crop_t) if a.get("text_id_y2") is not None else None,
                                linked_coordinate=a.get("linked_coordinate")
                            ))
                            continue
                        
                        #  NEW: SPECIAL HANDLING FOR HALTETAFEL
                        if a["name"] == "haltetafel":
                            # First try normal coordinate linking
                            available_coords = [c for c in coords if id(c) not in used_coord_ids]
                            linked = link_anchor_to_coord(a, available_coords, config=self.config, learned_patterns=learned_patterns)
                            
                            # If no direct coordinate found, try linking via GKS
                            if linked is None:
                                gks_dets_for_haltetafel = [det for det, _, _, _, _, _, _ in anchor_results if det["name"] == "gks_festkodiert"]
                                # Get spatial params from config
                                sp_cfg = self.config.spatial if self.config else None
                                linked = link_haltetafel_to_gks(
                                    a, gks_dets_for_haltetafel, coords, gks_coord_map,
                                    max_distance=sp_cfg.haltetafel_gks_max_distance if sp_cfg else 250,
                                    dy_tolerance=sp_cfg.haltetafel_gks_dy_tolerance if sp_cfg else 100,
                                    dx_tolerance=sp_cfg.haltetafel_gks_dx_tolerance if sp_cfg else 300
                                )
                                
                                if linked:
                                    meta = coord_meta.get(id(linked), {})
                                    coord_txt = meta.get("text", "?")
                                    if DEBUG_LINKING:
                                        print(f"Haltetafel inherited coordinate from GKS: '{coord_txt}'")
                            
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
                            
                            element_for_uuid = {
                                'cls': a["name"],
                                'page': pidx,
                                'obb_cx': a.get("obb_cx"),
                                'obb_cy': a.get("obb_cy"),
                                'anchor_text': name_txt,
                                'coord_text': coord_txt
                            }
                            
                            # Add crop offsets to convert detection coords to full image space
                            all_rows.append(dict(
                                detection_id=make_uuid(element_for_uuid),
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=name_txt, anchor_conf=ocr_conf, coord_text=coord_txt, coord_value=coord_val, gi_gl=gi,
                                ax1=a["x1"] + crop_l, ay1=a["y1"] + crop_t, ax2=a["x2"] + crop_l, ay2=a["y2"] + crop_t,
                                cx1=cbbox[0] + crop_l if cbbox[0] is not None else None,
                                cy1=cbbox[1] + crop_t if cbbox[1] is not None else None,
                                cx2=cbbox[2] + crop_l if cbbox[2] is not None else None,
                                cy2=cbbox[3] + crop_t if cbbox[3] is not None else None,
                                angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=(a.get("obb_cx") + crop_l) if a.get("obb_cx") is not None else None,
                                obb_cy=(a.get("obb_cy") + crop_t) if a.get("obb_cy") is not None else None,
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=[(p[0] + crop_l, p[1] + crop_t) for p in (a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly"))] if a.get("poly") is not None else None,
                                ocr_x1=(ocr_bbox[0] + crop_l) if ocr_bbox else None,
                                ocr_y1=(ocr_bbox[1] + crop_t) if ocr_bbox else None,
                                ocr_x2=(ocr_bbox[2] + crop_l) if ocr_bbox else None,
                                ocr_y2=(ocr_bbox[3] + crop_t) if ocr_bbox else None,
                                ocr_region_source=a.get("ocr_region_source", ocr_position),
                                notes="", weichen_coordinates=[],
                                fahrtrichtung=None,
                                _fahrtrichtung_source='none',  #  CHANGE 3
                                # Antwerp-specific fields for persistence
                                text_id_x1=(a.get("text_id_x1") + crop_l) if a.get("text_id_x1") is not None else None,
                                text_id_y1=(a.get("text_id_y1") + crop_t) if a.get("text_id_y1") is not None else None,
                                text_id_x2=(a.get("text_id_x2") + crop_l) if a.get("text_id_x2") is not None else None,
                                text_id_y2=(a.get("text_id_y2") + crop_t) if a.get("text_id_y2") is not None else None,
                                linked_coordinate=a.get("linked_coordinate")
                            ))
                            # Debug: Verify OCR coords were stored
                            if ocr_bbox and DEBUG_LINKING:
                                print(f" Stored OCR coords for row {row_id}: ocr_x1={ocr_bbox[0]:.0f}, ocr_y1={ocr_bbox[1]:.0f}, ocr_x2={ocr_bbox[2]:.0f}, ocr_y2={ocr_bbox[3]:.0f}")
                            continue

                        #  SPECIAL HANDLING FOR SVERBINDER (use pre-linked coordinate)
                        if a["name"] == "sverbinder":
                            # Retrieve the already-linked coordinate from STEP 1B
                            linked = sverbinder_coord_map.get(id(a))
                            
                            coord_txt, coord_val, gi = None, None, None
                            cbbox = (None, None, None, None)
                            
                            if linked is not None:
                                # DON'T add to used_coord_ids again (already done in STEP 1B)
                                
                                meta = coord_meta.get(id(linked), {})
                                coord_txt, coord_val, gi = meta.get("text"), meta.get("value"), meta.get("gi")
                                if coord_txt:
                                    coord_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', coord_txt)
                                    coord_txt = re.sub(r'\s*[|/\\]\s*$', '', coord_txt)
                                    coord_txt = ' '.join(coord_txt.split()).strip()
                                cbbox = (linked["x1"], linked["y1"], linked["x2"], linked["y2"])
                            
                            element_for_uuid = {
                                'cls': a["name"],
                                'page': pidx,
                                'obb_cx': a.get("obb_cx"),
                                'obb_cy': a.get("obb_cy"),
                                'anchor_text': name_txt,
                                'coord_text': coord_txt
                            }
                            
                            # Add crop offsets to convert detection coords to full image space
                            all_rows.append(dict(
                                detection_id=make_uuid(element_for_uuid),
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=name_txt, anchor_conf=ocr_conf, coord_text=coord_txt, coord_value=coord_val, gi_gl=gi,
                                ax1=a["x1"] + crop_l, ay1=a["y1"] + crop_t, ax2=a["x2"] + crop_l, ay2=a["y2"] + crop_t,
                                cx1=cbbox[0] + crop_l if cbbox[0] is not None else None,
                                cy1=cbbox[1] + crop_t if cbbox[1] is not None else None,
                                cx2=cbbox[2] + crop_l if cbbox[2] is not None else None,
                                cy2=cbbox[3] + crop_t if cbbox[3] is not None else None,
                                angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=(a.get("obb_cx") + crop_l) if a.get("obb_cx") is not None else None,
                                obb_cy=(a.get("obb_cy") + crop_t) if a.get("obb_cy") is not None else None,
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=[(p[0] + crop_l, p[1] + crop_t) for p in (a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly"))] if a.get("poly") is not None else None,
                                ocr_x1=(ocr_bbox[0] + crop_l) if ocr_bbox else None,
                                ocr_y1=(ocr_bbox[1] + crop_t) if ocr_bbox else None,
                                ocr_x2=(ocr_bbox[2] + crop_l) if ocr_bbox else None,
                                ocr_y2=(ocr_bbox[3] + crop_t) if ocr_bbox else None,
                                ocr_region_source=a.get("ocr_region_source", ocr_position),
                                notes="", weichen_coordinates=[],
                                fahrtrichtung=fahrtrichtung,
                                _fahrtrichtung_source=fahrtrichtung_source,  #  CHANGE 3
                                # Antwerp-specific fields for persistence
                                text_id_x1=(a.get("text_id_x1") + crop_l) if a.get("text_id_x1") is not None else None,
                                text_id_y1=(a.get("text_id_y1") + crop_t) if a.get("text_id_y1") is not None else None,
                                text_id_x2=(a.get("text_id_x2") + crop_l) if a.get("text_id_x2") is not None else None,
                                text_id_y2=(a.get("text_id_y2") + crop_t) if a.get("text_id_y2") is not None else None,
                                linked_coordinate=a.get("linked_coordinate")
                            ))
                            continue

                        #  SKIP GKS (already processed in STEP 1)
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
                            
                            element_for_uuid = {
                                'cls': a["name"],
                                'page': pidx,
                                'obb_cx': a.get("obb_cx"),
                                'obb_cy': a.get("obb_cy"),
                                'anchor_text': name_txt,
                                'coord_text': coord_txt
                            }
                            
                            # Add crop offsets to convert detection coords to full image space
                            all_rows.append(dict(
                                detection_id=make_uuid(element_for_uuid),
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=name_txt, anchor_conf=ocr_conf, coord_text=coord_txt, coord_value=coord_val, gi_gl=gi,
                                ax1=a["x1"] + crop_l, ay1=a["y1"] + crop_t, ax2=a["x2"] + crop_l, ay2=a["y2"] + crop_t,
                                cx1=cbbox[0] + crop_l if cbbox[0] is not None else None,
                                cy1=cbbox[1] + crop_t if cbbox[1] is not None else None,
                                cx2=cbbox[2] + crop_l if cbbox[2] is not None else None,
                                cy2=cbbox[3] + crop_t if cbbox[3] is not None else None,
                                angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=(a.get("obb_cx") + crop_l) if a.get("obb_cx") is not None else None,
                                obb_cy=(a.get("obb_cy") + crop_t) if a.get("obb_cy") is not None else None,
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=[(p[0] + crop_l, p[1] + crop_t) for p in (a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly"))] if a.get("poly") is not None else None,
                                ocr_x1=(ocr_bbox[0] + crop_l) if ocr_bbox else None,
                                ocr_y1=(ocr_bbox[1] + crop_t) if ocr_bbox else None,
                                ocr_x2=(ocr_bbox[2] + crop_l) if ocr_bbox else None,
                                ocr_y2=(ocr_bbox[3] + crop_t) if ocr_bbox else None,
                                ocr_region_source=a.get("ocr_region_source", ocr_position),
                                notes="", weichen_coordinates=[],
                                fahrtrichtung=fahrtrichtung,
                                _fahrtrichtung_source=fahrtrichtung_source,  #  CHANGE 3
                                # Antwerp-specific fields for persistence
                                text_id_x1=(a.get("text_id_x1") + crop_l) if a.get("text_id_x1") is not None else None,
                                text_id_y1=(a.get("text_id_y1") + crop_t) if a.get("text_id_y1") is not None else None,
                                text_id_x2=(a.get("text_id_x2") + crop_l) if a.get("text_id_x2") is not None else None,
                                text_id_y2=(a.get("text_id_y2") + crop_t) if a.get("text_id_y2") is not None else None,
                                linked_coordinate=a.get("linked_coordinate")
                            ))
                            continue

                        #  SPECIAL HANDLING FOR ISOLIERSTOSS (with fallback)
                        if a["name"] == "isolierstoß":
                            # First: Try normal linking (mode="above")
                            available_coords = [c for c in coords if id(c) not in used_coord_ids]
                            linked = link_anchor_to_coord(a, available_coords, config=self.config, learned_patterns=learned_patterns)

                            # If normal linking fails, try fallback (search all around for unlinked coords)
                            if linked is None:
                                if DEBUG_ANGLE_ROUTING:
                                    print(f"\n    Isolierstoß: Normal linking failed, trying fallback...")

                                # Fallback: search in all directions for nearest unlinked coordinate
                                fallback_radius = self.config.spatial.isolierstoss_fallback_radius if self.config else 300
                                linked = link_isolierstoss_fallback(a, coords, used_coord_ids, max_radius=fallback_radius)

                            # Process coordinate
                            coord_txt, coord_val, gi = None, None, None
                            cbbox = (None, None, None, None)

                            if linked is not None:
                                used_coord_ids.add(id(linked))

                                # Record pattern
                                dx_offset = linked["cx"] - a["cx"]
                                dy_offset = linked["cy"] - a["cy"]
                                if a["name"] not in learned_patterns:
                                    learned_patterns[a["name"]] = []
                                learned_patterns[a["name"]].append((dx_offset, dy_offset))

                                meta = coord_meta.get(id(linked), {})
                                coord_txt, coord_val, gi = meta.get("text"), meta.get("value"), meta.get("gi")
                                if coord_txt:
                                    coord_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', coord_txt)
                                    coord_txt = re.sub(r'\s*[|/\\]\s*$', '', coord_txt)
                                    coord_txt = ' '.join(coord_txt.split()).strip()
                                cbbox = (linked["x1"], linked["y1"], linked["x2"], linked["y2"])

                                if DEBUG_ANGLE_ROUTING:
                                    print(f"Isolierstoß → coordinate '{coord_txt}'")

                            element_for_uuid = {
                                'cls': a["name"],
                                'page': pidx,
                                'obb_cx': a.get("obb_cx"),
                                'obb_cy': a.get("obb_cy"),
                                'anchor_text': name_txt,
                                'coord_text': coord_txt
                            }

                            # Add crop offsets to convert detection coords to full image space
                            all_rows.append(dict(
                                detection_id=make_uuid(element_for_uuid),
                                row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                                anchor_text=name_txt, anchor_conf=ocr_conf, coord_text=coord_txt, coord_value=coord_val, gi_gl=gi,
                                ax1=a["x1"] + crop_l, ay1=a["y1"] + crop_t, ax2=a["x2"] + crop_l, ay2=a["y2"] + crop_t,
                                cx1=cbbox[0] + crop_l if cbbox[0] is not None else None,
                                cy1=cbbox[1] + crop_t if cbbox[1] is not None else None,
                                cx2=cbbox[2] + crop_l if cbbox[2] is not None else None,
                                cy2=cbbox[3] + crop_t if cbbox[3] is not None else None,
                                angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                                obb_cx=(a.get("obb_cx") + crop_l) if a.get("obb_cx") is not None else None,
                                obb_cy=(a.get("obb_cy") + crop_t) if a.get("obb_cy") is not None else None,
                                obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                                poly=[(p[0] + crop_l, p[1] + crop_t) for p in (a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly"))] if a.get("poly") is not None else None,
                                ocr_x1=(ocr_bbox[0] + crop_l) if ocr_bbox else None,
                                ocr_y1=(ocr_bbox[1] + crop_t) if ocr_bbox else None,
                                ocr_x2=(ocr_bbox[2] + crop_l) if ocr_bbox else None,
                                ocr_y2=(ocr_bbox[3] + crop_t) if ocr_bbox else None,
                                ocr_region_source=a.get("ocr_region_source", ocr_position),
                                notes="", weichen_coordinates=[],
                                fahrtrichtung=fahrtrichtung,
                                _fahrtrichtung_source=fahrtrichtung_source,
                                # Antwerp-specific fields for persistence
                                text_id_x1=(a.get("text_id_x1") + crop_l) if a.get("text_id_x1") is not None else None,
                                text_id_y1=(a.get("text_id_y1") + crop_t) if a.get("text_id_y1") is not None else None,
                                text_id_x2=(a.get("text_id_x2") + crop_l) if a.get("text_id_x2") is not None else None,
                                text_id_y2=(a.get("text_id_y2") + crop_t) if a.get("text_id_y2") is not None else None,
                                linked_coordinate=a.get("linked_coordinate")
                            ))
                            continue

                        #  EXISTING CODE FOR OTHER CLASSES
                        # For signals: also exclude haltepunkt soft-claimed coordinates
                        if a["name"].lower() == "signal":
                            available_coords = [c for c in coords if id(c) not in used_coord_ids and id(c) not in haltepunkt_coord_ids]
                        elif a["name"] in ["weichenende", "weichengruppenende"]:
                            # LOWEST PRIORITY: exclude ALL claimed coordinates from ALL sources
                            # These classes should only take coordinates that NO OTHER class has claimed
                            all_claimed = (
                                used_coord_ids |
                                haltepunkt_coord_ids |
                                set(id(c) for c in sverbinder_coord_map.values()) |
                                set(id(c) for c in gks_coord_map.values())
                            )
                            available_coords = [c for c in coords if id(c) not in all_claimed]
                        else:
                            available_coords = [c for c in coords if id(c) not in used_coord_ids]
                        linked = link_anchor_to_coord(a, available_coords, config=self.config, learned_patterns=learned_patterns)
                        
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
                                coord_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', coord_txt)
                                coord_txt = re.sub(r'\s*[|/\\]\s*$', '', coord_txt)
                                coord_txt = ' '.join(coord_txt.split())
                                coord_txt = coord_txt.strip()

                            cbbox = (linked["x1"], linked["y1"], linked["x2"], linked["y2"])

                        # Check if STEP 1E already linked a coordinate to this anchor (Antwerp only)
                        if "linked_coordinate" in a and a["linked_coordinate"] and not coord_txt:
                            coord_txt = a["linked_coordinate"]
                            if DEBUG_LINKING:
                                print(f"  Using STEP 1E linked_coordinate '{coord_txt}' for {a['name']}")

                        element_for_uuid = {
                            'cls': a["name"],
                            'page': pidx,
                            'obb_cx': a.get("obb_cx"),
                            'obb_cy': a.get("obb_cy"),
                            'anchor_text': name_txt,
                            'coord_text': coord_txt
                        }
                        
                        # Add crop offsets to convert detection coords to full image space
                        all_rows.append(dict(
                            detection_id=make_uuid(element_for_uuid),
                            row_id=row_id, page=pidx, cls=a["name"], conf=round(a["conf"], 3), color=a_color,
                            anchor_text=name_txt, anchor_conf=ocr_conf, coord_text=coord_txt, coord_value=coord_val, gi_gl=gi,
                            ax1=a["x1"] + crop_l, ay1=a["y1"] + crop_t, ax2=a["x2"] + crop_l, ay2=a["y2"] + crop_t,
                            cx1=cbbox[0] + crop_l if cbbox[0] is not None else None,
                            cy1=cbbox[1] + crop_t if cbbox[1] is not None else None,
                            cx2=cbbox[2] + crop_l if cbbox[2] is not None else None,
                            cy2=cbbox[3] + crop_t if cbbox[3] is not None else None,
                            angle=a.get("angle"), angle_raw=a.get("angle_raw"),
                            obb_cx=(a.get("obb_cx") + crop_l) if a.get("obb_cx") is not None else None,
                            obb_cy=(a.get("obb_cy") + crop_t) if a.get("obb_cy") is not None else None,
                            obb_w=a.get("obb_w"), obb_h=a.get("obb_h"),
                            poly=[(p[0] + crop_l, p[1] + crop_t) for p in (a.get("poly").tolist() if isinstance(a.get("poly"), np.ndarray) else a.get("poly"))] if a.get("poly") is not None else None,
                            ocr_x1=(ocr_bbox[0] + crop_l) if ocr_bbox else None,
                            ocr_y1=(ocr_bbox[1] + crop_t) if ocr_bbox else None,
                            ocr_x2=(ocr_bbox[2] + crop_l) if ocr_bbox else None,
                            ocr_y2=(ocr_bbox[3] + crop_t) if ocr_bbox else None,
                            ocr_region_source=a.get("ocr_region_source", ocr_position),  # Prefer text_id direction for signals
                            notes="", weichen_coordinates=[],
                            fahrtrichtung=fahrtrichtung,
                            _fahrtrichtung_source=fahrtrichtung_source,  #  CHANGE 3
                            # Antwerp-specific fields for persistence
                            text_id_x1=(a.get("text_id_x1") + crop_l) if a.get("text_id_x1") is not None else None,
                            text_id_y1=(a.get("text_id_y1") + crop_t) if a.get("text_id_y1") is not None else None,
                            text_id_x2=(a.get("text_id_x2") + crop_l) if a.get("text_id_x2") is not None else None,
                            text_id_y2=(a.get("text_id_y2") + crop_t) if a.get("text_id_y2") is not None else None,
                            linked_coordinate=a.get("linked_coordinate")
                        ))

                    for c in coords:
                        row_id = len(all_rows)
                        meta = coord_meta.get(id(c), {})
                        
                        element_for_uuid = {
                            'cls': "coordinate",
                            'page': pidx,
                            'obb_cx': c.get("obb_cx"),
                            'obb_cy': c.get("obb_cy"),
                            'cx1': c["x1"],
                            'cy1': c["y1"],
                            'coord_text': meta.get("text")
                        }
                        
                        # Add crop offsets to convert detection coords to full image space
                        all_rows.append(dict(
                            detection_id=make_uuid(element_for_uuid),
                            row_id=row_id, page=pidx, cls="coordinate", conf=round(c["conf"], 3), color=meta.get("color", "none"),
                            anchor_text="", coord_text=meta.get("text"), coord_value=meta.get("value"), gi_gl=meta.get("gi"),
                            ax1=None, ay1=None, ax2=None, ay2=None,
                            cx1=c["x1"] + crop_l, cy1=c["y1"] + crop_t, cx2=c["x2"] + crop_l, cy2=c["y2"] + crop_t,
                            angle=c.get("angle"), angle_raw=c.get("angle_raw"),
                            obb_cx=(c.get("obb_cx") + crop_l) if c.get("obb_cx") is not None else None,
                            obb_cy=(c.get("obb_cy") + crop_t) if c.get("obb_cy") is not None else None,
                            obb_w=c.get("obb_w"), obb_h=c.get("obb_h"),
                            poly=[(p[0] + crop_l, p[1] + crop_t) for p in (c.get("poly").tolist() if isinstance(c.get("poly"), np.ndarray) else c.get("poly"))] if c.get("poly") is not None else None,
                            ocr_x1=None, ocr_y1=None, ocr_x2=None, ocr_y2=None,
                            ocr_region_source=None,
                            notes="", weichen_coordinates=[],
                            fahrtrichtung=None,
                            _fahrtrichtung_source='none',  #  CHANGE 3
                            # Antwerp-specific fields for persistence (None for coordinates)
                            text_id_x1=None,
                            text_id_y1=None,
                            text_id_x2=None,
                            text_id_y2=None,
                            linked_coordinate=None
                        ))

                    self.status.emit("Symbolzuordnung abgeschlossen")
                    emit_progress(pidx - 1, W['raster'] + W['prep'] + W['det'] + W['ocr_c'] + W['ocr_a'] + W['link'])

                    # NOTE: Coordinates are now in FULL image space (crop offsets added above)
                    # Visualization uses full_bgr_color to match these coordinates.

                    df_page = pd.DataFrame([r for r in all_rows if r["page"] == pidx])
                
                else:
                    self.status.emit("Bild wird extrahiert...")
                    emit_progress(pidx - 1, 1.0)

                # Store and emit FULL image (coordinates are in full image space)
                page_bgr_arrays[pidx] = full_bgr_color
                page_dfs[pidx] = df_page

                self.page_processed.emit(pidx, full_bgr_color, df_page)

                self.status.emit("Seite abgeschlossen")

                del pil, bgr_color, full_bgr_color
                if self.run_analysis:
                    del mask_red, mask_yel, coords, anchors, coord_meta, dets
                gc.collect()
            
            df_all = pd.DataFrame(all_rows)

            if self.run_analysis:
                self.status.emit(f"Analyse abgeschlossen: {len(df_all)} Einträge gefunden")
                
                # Only merge signals for Wien profiles (Antwerp signals are unique, don't need merging)
                is_antwerp = (self.config is not None and
                              hasattr(self.config, 'ocr') and
                              self.config.ocr.use_simple_ocr)

                if not is_antwerp:
                    if DEBUG_LINKING:
                        print(f"\n{'='*70}")
                        print(f" MERGING DUPLICATE SIGNALS")
                        print(f"{'='*70}")
                    original_len = len(all_rows)

                    #  Merge WITHOUT track fallback
                    all_rows = merge_duplicate_signals(
                        all_rows,
                        track_skeleton=None,  #  Don't pass track skeleton to merge
                        gks_dets=gks_dets
                    )
                    df_all = pd.DataFrame(all_rows)

                    merged_len = len(all_rows)
                    if DEBUG_LINKING:
                        if original_len != merged_len:
                            print(f"Merge complete: {original_len} → {merged_len} (saved {original_len - merged_len} rows)")
                        print(f"{'='*70}\n")
                
                # ========================================
                #  TRACK FALLBACK FOR MERGED SIGNALS (MAJORITY VOTE)
                # ========================================

                if track_skeleton is not None:
                    if DEBUG_TRACK:
                        print(f"\n{'='*70}")
                        print(f"  TRACK FALLBACK - Filling missing Fahrtrichtung (MAJORITY VOTE)")
                        print(f"{'='*70}")

                    #  Find signals that need track fallback (only those WITHOUT Fahrtrichtung)
                    signals_needing_fallback = [
                        row for row in all_rows
                        if row['cls'] == 'signal'
                        and not row.get('_hidden')
                        and not row.get('fahrtrichtung')  #  Only fill missing values
                    ]

                    if DEBUG_TRACK:
                        print(f"Signals without Fahrtrichtung: {len(signals_needing_fallback)}")
                    
                    fallback_success = 0
                    fallback_failed = 0
                    
                    for row in signals_needing_fallback:
                        signal_text = row.get('anchor_text', '?')
                        signal_text_upper = (signal_text or '').upper().strip()

                        # Skip signals that don't need Fahrtrichtung:
                        # 1. V-signals (Vorsignale)
                        # 2. Single letter + 3+ digits (e.g., A123, U456)
                        if signal_text_upper.startswith('V'):
                            continue

                        # Check single letter + 3+ digits pattern
                        if (len(signal_text_upper) >= 4 and
                            signal_text_upper[0].isalpha() and
                            signal_text_upper[1:].isdigit() and
                            len(signal_text_upper[1:]) >= 3):
                            continue

                        if DEBUG_TRACK:
                            print(f"\n     Trying track fallback for '{signal_text}'")

                        # ========================================
                        #  MAJORITY VOTE - Check ALL signal instances
                        # ========================================

                        signal_positions = row.get('_signal_positions', {})

                        if signal_positions:
                            if DEBUG_TRACK:
                                print(f"Found {len(signal_positions)} signal instances - using MAJORITY VOTE")
                            
                            votes = []  # List of (instance_name, fahrtrichtung)
                            
                            for instance_name, pos_data in signal_positions.items():
                                #  SKIP haltepunkt-referenced signal instances
                                # These are the actual signal detections that were near haltepunkt markers
                                # We only want the coordinate_signal and bare haltepunkt_signal for voting
                                if instance_name == 'haltepunkt_signal':
                                    if DEBUG_TRACK:
                                        print(f"{instance_name}: skipped (haltepunkt-referenced)")
                                    continue
                                
                                #  Calculate center from THIS instance's bounding box
                                instance_cx = (pos_data['ax1'] + pos_data['ax2']) / 2
                                instance_cy = (pos_data['ay1'] + pos_data['ay2']) / 2
                                
                                # Create detection dict for this instance
                                instance_det = {
                                    'x1': pos_data['ax1'],
                                    'y1': pos_data['ay1'],
                                    'x2': pos_data['ax2'],
                                    'y2': pos_data['ay2'],
                                    'cx': instance_cx,  #  Use THIS instance's center
                                    'cy': instance_cy,  #  Use THIS instance's center
                                    'text': signal_text,
                                    'angle': row.get('angle', 0.0),
                                    'angle_raw': row.get('angle_raw', row.get('angle', 0.0)),
                                    'obb_w': row.get('obb_w', 0),
                                    'obb_h': row.get('obb_h', 0)
                                }
                                
                                # Check this instance
                                fahr = detect_fahrtrichtung(
                                    instance_det,
                                    gks_dets=[],
                                    track_skeleton=track_skeleton,
                                    track_bounds=track_bounds,  #  NEW: Pass track bounds
                                    track_sample_distance=self.config.spatial.track_sample_distance if self.config else 300,
                                    track_search_radius=self.config.spatial.track_search_radius if self.config else 500,
                                    config=self.config
                                )
                                
                                if fahr:
                                    votes.append((instance_name, fahr))
                                    if DEBUG_TRACK:
                                        print(f"{instance_name}: {fahr}")
                                else:
                                    if DEBUG_TRACK:
                                        print(f"{instance_name}: undetermined")

                            # Count votes
                            if votes:
                                vote_counts = Counter([v[1] for v in votes])

                                if DEBUG_TRACK:
                                    print(f"Vote results: {dict(vote_counts)}")

                                # Get majority
                                if len(vote_counts) == 1:
                                    # Unanimous
                                    fahrtrichtung_from_track = votes[0][1]
                                    if DEBUG_TRACK:
                                        print(f"UNANIMOUS: All instances agree on '{fahrtrichtung_from_track}'")
                                else:
                                    # Majority wins
                                    majority_fahr, majority_count = vote_counts.most_common(1)[0]
                                    total_votes = len(votes)

                                    if majority_count > total_votes / 2:
                                        fahrtrichtung_from_track = majority_fahr
                                        if DEBUG_TRACK:
                                            print(f"MAJORITY: '{majority_fahr}' ({majority_count}/{total_votes} votes)")
                                    else:
                                        # Tie - use PRIMARY instance as tiebreaker
                                        fahrtrichtung_from_track = None
                                        if DEBUG_TRACK:
                                            print(f"TIE: No clear majority - fallback failed")
                            else:
                                # No votes - all instances failed
                                fahrtrichtung_from_track = None
                                if DEBUG_TRACK:
                                    print(f"All instances failed track detection")

                        else:
                            # ========================================
                            # FALLBACK: No _signal_positions (single instance)
                            # ========================================
                            if DEBUG_TRACK:
                                print(f"No _signal_positions found - using PRIMARY instance only")
                            
                            signal_det_for_track = {
                                'x1': row['ax1'],
                                'y1': row['ay1'],
                                'x2': row['ax2'],
                                'y2': row['ay2'],
                                'cx': row.get('obb_cx'),
                                'cy': row.get('obb_cy'),
                                'text': signal_text,
                                'angle': row.get('angle', 0.0),
                                'angle_raw': row.get('angle_raw', row.get('angle', 0.0)),
                                'obb_w': row.get('obb_w', 0),
                                'obb_h': row.get('obb_h', 0)
                            }
                            
                            fahrtrichtung_from_track = detect_fahrtrichtung(
                                signal_det_for_track,
                                gks_dets=[],
                                track_skeleton=track_skeleton,
                                track_bounds=track_bounds,
                                track_sample_distance=self.config.spatial.track_sample_distance if self.config else 300,
                                track_search_radius=self.config.spatial.track_search_radius if self.config else 500,
                                config=self.config
                            )
                        # ========================================
                        # Apply result
                        # ========================================
                        if fahrtrichtung_from_track:
                            row['fahrtrichtung'] = fahrtrichtung_from_track
                            row['_fahrtrichtung_source'] = 'track'
                            fallback_success += 1
                            if DEBUG_TRACK:
                                print(f"SUCCESS: Fahrtrichtung '{fahrtrichtung_from_track}' (track)")
                        else:
                            # ========================================
                            # TIER 3: GKS Relaxed Column Search (dy ≤ 600px)
                            # ========================================
                            signal_page = row.get('page', 1)
                            page_gks_dets = [g for g in all_gks_dets if g.get('page') == signal_page]

                            # Build signal_det for Tier 3/4
                            signal_det_tier34 = {
                                'x1': row['ax1'],
                                'y1': row['ay1'],
                                'x2': row['ax2'],
                                'y2': row['ay2'],
                                'cx': row.get('obb_cx'),
                                'cy': row.get('obb_cy'),
                                'text': signal_text,
                                'angle': row.get('angle', 0.0),
                                'angle_raw': row.get('angle_raw', row.get('angle', 0.0))
                            }

                            # Get relaxed/nearest params from config
                            sp = self.config.spatial if self.config else None
                            relaxed_dx = sp.signal_gks_relaxed_dx_tolerance if sp else 200
                            relaxed_dy_max = sp.signal_gks_relaxed_dy_max if sp else 600
                            relaxed_angle = sp.signal_gks_relaxed_angle_tolerance if sp else 25
                            nearest_max_dist = sp.signal_gks_nearest_max_distance if sp else 800
                            nearest_angle = sp.signal_gks_nearest_angle_tolerance if sp else 30
                            gks_dy_min = sp.signal_gks_dy_min if sp else 30

                            if DEBUG_TRACK:
                                print(f"Trying TIER 3 (GKS relaxed, dy≤{relaxed_dy_max}px)...")
                            tier3_result, tier3_gks = detect_fahrtrichtung_gks_relaxed(
                                signal_det_tier34,
                                page_gks_dets,
                                used_gks_ids=None,  # Not tracking used GKS for now
                                dx_tolerance=relaxed_dx,
                                dy_min=gks_dy_min,
                                dy_max=relaxed_dy_max,
                                angle_tolerance=relaxed_angle,
                                config=self.config
                            )

                            if tier3_result:
                                row['fahrtrichtung'] = tier3_result
                                row['_fahrtrichtung_source'] = 'gks_relaxed'
                                fallback_success += 1
                                if DEBUG_TRACK:
                                    print(f"SUCCESS: Fahrtrichtung '{tier3_result}' (gks_relaxed)")
                            else:
                                # ========================================
                                # TIER 4: Euclidean Nearest GKS (dist ≤ configured)
                                # ========================================
                                if DEBUG_TRACK:
                                    print(f"Trying TIER 4 (Euclidean nearest, dist≤{nearest_max_dist}px)...")
                                tier4_result, tier4_gks = detect_fahrtrichtung_gks_nearest(
                                    signal_det_tier34,
                                    page_gks_dets,
                                    used_gks_ids=None,
                                    max_distance=nearest_max_dist,
                                    dy_min=gks_dy_min,
                                    angle_tolerance=nearest_angle,
                                    config=self.config
                                )

                                if tier4_result:
                                    row['fahrtrichtung'] = tier4_result
                                    row['_fahrtrichtung_source'] = 'gks_nearest'
                                    fallback_success += 1
                                    if DEBUG_TRACK:
                                        print(f"SUCCESS: Fahrtrichtung '{tier4_result}' (gks_nearest)")
                                else:
                                    row['_fahrtrichtung_source'] = 'none'
                                    fallback_failed += 1
                                    if DEBUG_TRACK:
                                        print(f"FAILED: All 4 tiers failed")

                    if DEBUG_TRACK:
                        print(f"\n{'='*70}")
                        print(f"Track fallback results:")
                        print(f"Success: {fallback_success}")
                        print(f"Failed: {fallback_failed}")
                        print(f"{'='*70}\n")
                    
                    # Rebuild DataFrame with updated Fahrtrichtung
                    df_all = pd.DataFrame(all_rows)
                
                # Rebuild page_dfs from merged data
                if DEBUG_LINKING:
                    print(f"\n Rebuilding page_dfs from merged data...")
                page_dfs = {}
                if not df_all.empty and 'page' in df_all.columns:
                    for page_num in df_all['page'].unique():
                        page_num_int = int(page_num)
                        page_dfs[page_num_int] = df_all[df_all['page'] == page_num].copy()

                        if DEBUG_LINKING:
                            if '_all_bboxes' in page_dfs[page_num_int].columns:
                                signals_with_multi = page_dfs[page_num_int][page_dfs[page_num_int]['_all_bboxes'].notna()]
                                print(f"Page {page_num_int}: {len(signals_with_multi)} signals with _all_bboxes")
                            else:
                                print(f"Page {page_num_int}: _all_bboxes column missing!")
                else:
                    if DEBUG_LINKING:
                        print(f"No data to rebuild (df_all is empty)")

                if DEBUG_LINKING:
                    print(f"Rebuilt {len(page_dfs)} page DataFrames\n")

            #  ADD link_coord_row_id TRACKING
            # After all processing is complete, map anchors to their linked coordinates
            # Use the dataframe itself - find anchors that have coord_text matching a coordinate
            required_cols = ['cls', 'coord_text', 'cx1', 'cy1', 'row_id', 'page']
            has_required_cols = all(col in df_all.columns for col in required_cols)
            if self.run_analysis and not df_all.empty and has_required_cols:
                if DEBUG_LINKING:
                    print(f"\n{'='*70}")
                    print(f" ADDING link_coord_row_id TRACKING")
                    print(f"{'='*70}")

                # Create link_coord_row_id column
                df_all['link_coord_row_id'] = None

                # Find all anchors that have been linked (they have coord_text and coordinate bbox)
                linked_anchors = df_all[
                    (df_all['cls'] != 'coordinate') &  # Not a coordinate itself
                    (df_all['coord_text'].notna()) &    # Has coord_text
                    (df_all['cx1'].notna())             # Has coordinate bbox
                ]

                if DEBUG_LINKING:
                    print(f"Found {len(linked_anchors)} anchors with linked coordinates")

                link_count = 0
                for idx in linked_anchors.index:
                    anchor_row = df_all.loc[idx]
                    anchor_cls = anchor_row['cls']
                    anchor_coord_text = anchor_row['coord_text']
                    anchor_cx1 = anchor_row['cx1']
                    anchor_cy1 = anchor_row['cy1']

                    # Find the coordinate with matching text and bbox
                    matching_coords = df_all[
                        (df_all['cls'] == 'coordinate') &
                        (df_all['coord_text'] == anchor_coord_text) &
                        (df_all['cx1'] == anchor_cx1) &
                        (df_all['cy1'] == anchor_cy1)
                    ]

                    if not matching_coords.empty:
                        coord_row_id = matching_coords.iloc[0]['row_id']
                        df_all.at[idx, 'link_coord_row_id'] = coord_row_id
                        link_count += 1

                if DEBUG_LINKING:
                    print(f"Added {link_count} link_coord_row_id references")

                    # Rebuild page_dfs to include link_coord_row_id
                    print(f" Updating page_dfs with link_coord_row_id...")
                for page_num in df_all['page'].unique():
                    page_num_int = int(page_num)
                    page_dfs[page_num_int] = df_all[df_all['page'] == page_num].copy()

                if DEBUG_LINKING:
                    print(f"{'='*70}\n")

            #  ADD link_text_id_row_id TRACKING (for Antwerp text_id → signal links)
            # Match signals to text_ids using stored bbox coordinates OR proximity fallback
            text_id_cols = ['text_id_x1', 'text_id_y1', 'text_id_x2', 'text_id_y2']
            has_text_id_cols = all(col in df_all.columns for col in text_id_cols)

            if self.run_analysis and not df_all.empty:
                if DEBUG_LINKING:
                    print(f"\n{'='*70}")
                    print(f" ADDING link_text_id_row_id TRACKING")
                    print(f"{'='*70}")

                # Create link_text_id_row_id column
                if 'link_text_id_row_id' not in df_all.columns:
                    df_all['link_text_id_row_id'] = None

                link_count = 0

                if has_text_id_cols:
                    # METHOD 1: Use stored text_id bbox coordinates (preferred)
                    if DEBUG_LINKING:
                        print(f"Using stored text_id bbox coordinates for matching")

                    # Find all anchors that have text_id bbox stored (they were linked to text_ids)
                    linked_anchors = df_all[
                        (df_all['cls'] != 'text_id') &  # Not a text_id itself
                        (df_all['text_id_x1'].notna())  # Has text_id bbox
                    ]

                    if DEBUG_LINKING:
                        print(f"Found {len(linked_anchors)} anchors with linked text_ids")

                    for idx in linked_anchors.index:
                        anchor_row = df_all.loc[idx]
                        tid_x1 = anchor_row['text_id_x1']
                        tid_y1 = anchor_row['text_id_y1']
                        tid_x2 = anchor_row['text_id_x2']
                        tid_y2 = anchor_row['text_id_y2']
                        anchor_page = anchor_row['page']

                        # Find the text_id with matching bbox on same page
                        matching_text_ids = df_all[
                            (df_all['cls'] == 'text_id') &
                            (df_all['page'] == anchor_page) &
                            (abs(df_all['ax1'] - tid_x1) < 5) &
                            (abs(df_all['ay1'] - tid_y1) < 5) &
                            (abs(df_all['ax2'] - tid_x2) < 5) &
                            (abs(df_all['ay2'] - tid_y2) < 5)
                        ]

                        if not matching_text_ids.empty:
                            text_id_row_id = matching_text_ids.iloc[0]['row_id']
                            df_all.at[idx, 'link_text_id_row_id'] = text_id_row_id
                            link_count += 1
                else:
                    # METHOD 2: Fallback - match by proximity (for data processed before text_id columns were added)
                    if DEBUG_LINKING:
                        print(f"FALLBACK: Using proximity matching (text_id columns not found)")

                    # Get all text_ids
                    text_ids = df_all[df_all['cls'] == 'text_id']

                    # Classes that can be linked to text_ids (signals AND coupling coils)
                    linkable_classes = ['signal', 'coupling_coil_active', 'coupling_coil_disabled']
                    linkable_mask = df_all['cls'].str.lower().isin(linkable_classes)
                    linkable_rows = df_all[linkable_mask]

                    if DEBUG_LINKING:
                        print(f"Found {len(text_ids)} text_ids and {len(linkable_rows)} linkable rows")

                    # For each linkable row, find the nearest text_id (vertically close, horizontally aligned)
                    max_dx = 300  # Max horizontal distance (increased for coupling coils)
                    max_dy = 400  # Max vertical distance

                    for row_idx in linkable_rows.index:
                        row = df_all.loc[row_idx]
                        row_cx = (row['ax1'] + row['ax2']) / 2
                        row_cy = (row['ay1'] + row['ay2']) / 2
                        row_page = row['page']
                        row_cls = row['cls'].lower()

                        # Find text_ids on same page within distance
                        page_text_ids = text_ids[text_ids['page'] == row_page]

                        best_tid_row_id = None
                        best_distance = float('inf')

                        for tid_idx in page_text_ids.index:
                            tid_row = df_all.loc[tid_idx]
                            tid_cx = (tid_row['ax1'] + tid_row['ax2']) / 2
                            tid_cy = (tid_row['ay1'] + tid_row['ay2']) / 2
                            tid_text = str(tid_row.get('anchor_text', '')).upper()

                            dx = abs(tid_cx - row_cx)
                            dy = abs(tid_cy - row_cy)

                            # Must be within proximity limits
                            if dx > max_dx or dy > max_dy:
                                continue

                            # For coupling coils, prefer TCC-prefixed text_ids
                            # For signals, prefer S-prefixed text_ids
                            prefix_bonus = 0
                            if 'coupling_coil' in row_cls and tid_text.startswith('TCC'):
                                prefix_bonus = -100  # Strong preference
                            elif row_cls == 'signal' and tid_text.startswith('S') and not tid_text.startswith('TCC'):
                                prefix_bonus = -100  # Strong preference

                            # Prefer vertically close, horizontally aligned text_ids
                            distance = dy + (dx * 0.5) + prefix_bonus

                            if distance < best_distance:
                                best_distance = distance
                                best_tid_row_id = tid_row['row_id']

                        if best_tid_row_id is not None:
                            df_all.at[row_idx, 'link_text_id_row_id'] = best_tid_row_id
                            link_count += 1
                            if DEBUG_LINKING:
                                print(f"  {row_cls} {row.get('anchor_text', 'N/A')} → text_id row_id={best_tid_row_id}")

                if DEBUG_LINKING:
                    print(f"Added {link_count} link_text_id_row_id references")

                # Rebuild page_dfs to include link_text_id_row_id
                for page_num in df_all['page'].unique():
                    page_num_int = int(page_num)
                    page_dfs[page_num_int] = df_all[df_all['page'] == page_num].copy()

                if DEBUG_LINKING:
                    print(f"{'='*70}\n")

            # ================================================================
            # ANTWERP-SPECIFIC: Fahrtrichtung and Durchrutschweg calculations
            # ================================================================
            # Only run for Antwerp profiles - Wien uses GKS-based detection
            if self.config is not None and self.config.is_antwerp_profile():
                if DEBUG_LINKING:
                    print(f"\n{'='*70}")
                    print(f" ANTWERP: Fahrtrichtung + Durchrutschweg Calculation")
                    print(f"{'='*70}")

                # Get signal rows
                signal_mask = df_all['cls'].str.lower() == 'signal'
                antwerp_updated = 0

                for idx in df_all[signal_mask].index:
                    row_dict = df_all.loc[idx].to_dict()

                    # Calculate Fahrtrichtung based on text_id position
                    if not row_dict.get('fahrtrichtung'):
                        fahr = detect_fahrtrichtung_antwerp(row_dict, self.config)
                        if fahr:
                            df_all.at[idx, 'fahrtrichtung'] = fahr
                            df_all.at[idx, '_fahrtrichtung_source'] = 'antwerp_text_id'

                    # Calculate Durchrutschweg from bond coordinates
                    durchrutschweg = calculate_durchrutschweg(
                        row_dict,
                        all_rows,  # Pass all detections to find bonds
                        self.config
                    )
                    if durchrutschweg is not None:
                        df_all.at[idx, 'durchrutschweg'] = durchrutschweg
                        antwerp_updated += 1

                if DEBUG_LINKING:
                    print(f"Updated {antwerp_updated} signals with Durchrutschweg")
                    print(f"{'='*70}\n")

                # Rebuild page_dfs with new columns
                for page_num in df_all['page'].unique():
                    page_num_int = int(page_num)
                    page_dfs[page_num_int] = df_all[df_all['page'] == page_num].copy()

            self.progress.emit(100)
            self.done.emit(df_all, page_dfs, track_skeleton if self.detect_tracks else None, None, self.uncertain_detections)
            
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.status.emit(f"Fehler bei der Verarbeitung: {e}")
            df_err = pd.DataFrame([{"error": str(e)}])
            self.done.emit(df_err, {}, None, e, [])
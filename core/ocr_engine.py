"""
OCR Engine - Texterkennung fuer Gleisplansymbole

Dieses Modul implementiert die Texterkennungspipeline fuer verschiedene
Symbolklassen mit unterschiedlichen OCR-Strategien.

Kernfunktionen:
    paddleocr_recognize(): Hauptfunktion fuer PaddleOCR-Erkennung
    ocr_signal_name(): Signalbezeichnung erkennen (z.B. "A1234")
    ocr_coordinate_unified(): Koordinatentext erkennen (z.B. "0,1234 Gl.113")
    ocr_anchor_name(): Allgemeine Textfelder erkennen
    preprocess_for_paddleocr(): Bildvorverarbeitung pro Klasse

Winkelabhaengige Verarbeitung:
    - Kardinal (±15° von 0°/180°): Standardverarbeitung
    - Angular (>15°): Perspektivkorrektur + Rotation
    - Verschiedene Vorverarbeitung pro Symbolklasse

Klassenspezifische Strategien:
    - Signal: Alphanumerisch (Muster: [A-Z]{1,4}[0-9]{1,4})
    - GKS: Rein numerisch (3-4 Ziffern)
    - Koordinaten: Dezimalzahlen mit Gleisreferenz
    - Weichen-Block: Mehrzeiliger Text

Abhaengigkeiten:
    paddleocr, cv2, numpy, PIL
"""
from typing import Tuple, Optional, List, Dict, Any, TYPE_CHECKING
import numpy as np
import cv2
from PIL import Image
import re
import threading
import logging
import os

from core.image_processing import perspective_crop_from_det, rotated_crop_from_det, rotated_crop_pil, _upscale_if_tiny,_remove_long_lines_oriented, _pil_to_gray_np, _enhance_contrast, _binarize_for_text, _invert, crop_pil, _deskew_small
from utils.helpers import _is_cardinal, _debug_angle
from core.linking import name_windows_for

# Type hint for LayoutConfig without circular import
if TYPE_CHECKING:
    from core.config_models import LayoutConfig

# Module-level debug flags (defaults, can be overridden by config)
DEBUG_ANGLE_ROUTING = False
DEBUG_OCR = False
DEBUG_CUSTOM_SYMBOLS = False
DEBUG_SIGNALS = False
DEBUG_CROPS = False

# Default OCR parameters (can be overridden by config)
SIG_LINE_THICK = 5
SIG_USE_TIGHTEN = False
SIGNAL_TEXT_HEIGHT_HINT = None
SIG_SCORE_MIN = 1.3
TESSERACT_PATH = None

# Default regex patterns
COORD_RE = None
try:
    COORD_RE = re.compile(r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$')
except Exception:
    pass

CLASS_ID_PATTERNS = {
    "signal": r"^[A-ZÄÖÜ]{1,4}\d{1,4}$",
    "gks_gesteuert": r"^\d{3,4}$",
    "gks_festkodiert": r"^\d{3,4}$",
}

NUMERIC_OK = {"gks_gesteuert", "gks_festkodiert", "weichen_block", "prellbock"}

# Debug crop counter (for unique filenames)
_debug_crop_counter = 0
_debug_crop_lock = threading.Lock()

def _save_debug_crop(crop: np.ndarray, class_name: str, ocr_result: str = "", suffix: str = ""):
    """
    Save OCR crop to temporary debug folder.
    Only saves if DEBUG_OCR is enabled.

    Args:
        crop: BGR image array
        class_name: Class name (e.g., "text_id", "coordinate")
        ocr_result: OCR text result (for filename)
        suffix: Optional suffix for filename (e.g., "preprocessed", "cw", "ccw")
    """
    global _debug_crop_counter

    if not DEBUG_CROPS:
        return

    try:
        # Create debug directory
        debug_dir = os.path.join("debug_crops", class_name)
        os.makedirs(debug_dir, exist_ok=True)

        # Thread-safe counter increment
        with _debug_crop_lock:
            _debug_crop_counter += 1
            counter = _debug_crop_counter

        # Sanitize OCR result for filename (replace problematic characters)
        clean_result = re.sub(r'[<>:"/\\|?*]', '_', ocr_result)[:50] if ocr_result else "empty"

        # Build filename
        suffix_str = f"_{suffix}" if suffix else ""
        filename = f"{counter:04d}_{class_name}_{clean_result}{suffix_str}.png"
        filepath = os.path.join(debug_dir, filename)

        # Save crop
        cv2.imwrite(filepath, crop)

    except Exception as e:
        # Silently fail - debug feature shouldn't break OCR
        pass

# Default cardinal params (horizontal/vertical text)
CARDINAL_PARAMS = {
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

# Default angular params (rotated text)
ANGULAR_PARAMS = {
    "detection_padding": {
        "coordinate": 4, "signal": 8, "weichenende": 4, "haltetafel": 4,
        "prellbock": 4, "gks_gesteuert": 6, "gks_festkodiert": 6,
    },
    "expansion_factor": {
        "coordinate": (1.0, 1.0), "signal": (1.0, 1.05),
        "gks_gesteuert": (0.75, 0.75), "gks_festkodiert": (0.75, 0.75),
    }
}

# Default linking rules - fallback when config is not provided
# These are overwritten by configure_from_config() when a profile is loaded
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

# Decimal separator configuration (German uses comma, others may use dot)
# Updated by configure_from_config() when a profile is loaded
DECIMAL_SEP_INPUT = ","   # Character used in scanned documents
DECIMAL_SEP_OUTPUT = "."  # Character to normalize to for float parsing


def configure_from_config(config: 'LayoutConfig') -> None:
    """
    Configure module-level variables from LayoutConfig.

    Call this once at the start of processing to set debug flags and parameters
    from the loaded profile.

    Args:
        config: LayoutConfig loaded from YAML profile
    """
    global DEBUG_ANGLE_ROUTING, DEBUG_OCR, DEBUG_CUSTOM_SYMBOLS, DEBUG_SIGNALS, DEBUG_CROPS
    global SIG_LINE_THICK, SIG_USE_TIGHTEN, SIGNAL_TEXT_HEIGHT_HINT, SIG_SCORE_MIN
    global TESSERACT_PATH, COORD_RE, CLASS_ID_PATTERNS, NUMERIC_OK, CARDINAL_PARAMS, ANGULAR_PARAMS
    global LINK_RULES, DECIMAL_SEP_INPUT, DECIMAL_SEP_OUTPUT

    if config is None:
        return

    # Debug flags
    DEBUG_ANGLE_ROUTING = config.debug_angle_routing
    DEBUG_OCR = config.debug_ocr
    DEBUG_CUSTOM_SYMBOLS = config.debug_custom_symbols
    DEBUG_SIGNALS = config.debug_signals
    DEBUG_CROPS = config.debug_crops

    # OCR parameters
    if hasattr(config, 'ocr'):
        ocr = config.ocr
        SIG_LINE_THICK = getattr(ocr, 'sig_line_thick', SIG_LINE_THICK)
        SIG_USE_TIGHTEN = getattr(ocr, 'sig_use_tighten', SIG_USE_TIGHTEN)
        SIGNAL_TEXT_HEIGHT_HINT = getattr(ocr, 'signal_text_height_hint', SIGNAL_TEXT_HEIGHT_HINT)
        SIG_SCORE_MIN = getattr(ocr, 'sig_score_min', SIG_SCORE_MIN)

        # Cardinal params from config (horizontal/vertical text)
        if hasattr(ocr, 'cardinal_detection_padding') and ocr.cardinal_detection_padding:
            CARDINAL_PARAMS["detection_padding"].update(ocr.cardinal_detection_padding)
        if hasattr(ocr, 'cardinal_expansion_factor') and ocr.cardinal_expansion_factor:
            CARDINAL_PARAMS["expansion_factor"].update(ocr.cardinal_expansion_factor)

        # Angular params from config (rotated text)
        if hasattr(ocr, 'angular_detection_padding') and ocr.angular_detection_padding:
            ANGULAR_PARAMS["detection_padding"].update(ocr.angular_detection_padding)
        if hasattr(ocr, 'angular_expansion_factor') and ocr.angular_expansion_factor:
            ANGULAR_PARAMS["expansion_factor"].update(ocr.angular_expansion_factor)

    # Validation patterns
    if hasattr(config, 'validation'):
        val = config.validation
        if val.coordinate_re is not None:
            COORD_RE = val.coordinate_re
        if val.class_id_patterns:
            CLASS_ID_PATTERNS.update(val.class_id_patterns)
        if val.numeric_ok_classes:
            NUMERIC_OK = set(val.numeric_ok_classes)
        # Decimal separator configuration
        if hasattr(val, 'decimal_separator_input'):
            DECIMAL_SEP_INPUT = val.decimal_separator_input
        if hasattr(val, 'decimal_separator_output'):
            DECIMAL_SEP_OUTPUT = val.decimal_separator_output

    # Tesseract path
    if hasattr(config, 'poppler_path') and config.poppler_path:
        # Note: poppler_path might be used for tesseract on some systems
        pass

    # Build LINK_RULES from config classes
    if hasattr(config, 'classes') and config.classes:
        LINK_RULES.clear()
        for cls_def in config.classes:
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


# ============================================================================
# TESSERACT PATH CONFIGURATION
# ============================================================================
# Configure Tesseract path if specified in config (for company laptops)
if TESSERACT_PATH:
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        if DEBUG_OCR:
            print(f"[OCR] Tesseract path configured: {TESSERACT_PATH}")
    except ImportError:
        pass  # pytesseract not installed, will fail later if needed

# ============================================================================
# PADDLEOCR HELPER FUNCTIONS
# ============================================================================

def preprocess_for_paddleocr(pil_img: Image.Image, cls_name: str = "default") -> np.ndarray:
    """
    Minimal preprocessing for PaddleOCR.
    PaddleOCR has strong built-in preprocessing.
    
    Args:
        pil_img: PIL Image
        cls_name: Class name for class-specific preprocessing
    
    Returns:
        BGR numpy array ready for PaddleOCR
    """
    # Convert to grayscale array
    if isinstance(pil_img, Image.Image):
        arr = np.array(pil_img.convert('L'))
    else:
        arr = pil_img
    
    # CLAHE for contrast enhancement (fast and effective)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    arr = clahe.apply(arr)
    
    # Morphology for GKS digits (helps with frames and broken digits)
    if cls_name in ["gks_gesteuert", "gks_festkodiert"]:
        # Close small gaps in digits
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        arr = cv2.morphologyEx(arr, cv2.MORPH_CLOSE, kernel, iterations=1)
        
        # Remove thin lines (frames) while preserving thick strokes (digits)
        # Vertical lines
        k_vert = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
        no_vert = cv2.morphologyEx(arr, cv2.MORPH_OPEN, k_vert)
        arr = arr - no_vert  # Remove vertical lines
        
        # Horizontal lines
        k_horiz = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 1))
        no_horiz = cv2.morphologyEx(arr, cv2.MORPH_OPEN, k_horiz)
        arr = arr - no_horiz  # Remove horizontal lines
        
        # Slight thickening to repair any damage
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        arr = cv2.dilate(arr, kernel, iterations=1)
    
    # Light sharpening for signals and coordinates
    elif cls_name in ["signal", "coordinate"]:
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        arr = cv2.filter2D(arr, -1, kernel)
    
    # Convert to BGR for PaddleOCR
    return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)


def paddleocr_recognize(
    pil_img: Image.Image, 
    cls_name: str = "default",
    whitelist: str = None
) -> Tuple[str, float]:
    """
    Run PaddleOCR on PIL image.
    
    Args:
        pil_img: PIL Image to recognize
        cls_name: Class name for class-specific processing
        whitelist: Character whitelist (filtering applied post-OCR)
    
    Returns:
        (recognized_text, confidence_0_to_1)
    """
    paddle = get_paddleocr_instance()
    
    if paddle is None:
        return "", 0.0
    
    try:
        # Preprocess
        arr = preprocess_for_paddleocr(pil_img, cls_name)
        
        # Run PaddleOCR
        results = paddle.ocr(arr, cls=False)
        
        if not results or results[0] is None or len(results[0]) == 0:
            return "", 0.0
        
        # Extract all text and confidence
        texts = []
        confs = []
        for line in results[0]:
            if line is None:
                continue
            bbox, (text, conf) = line
            texts.append(text)
            confs.append(conf)
        
        if not texts:
            return "", 0.0
        
        # Combine multiple detections
        final_text = " ".join(texts)
        final_conf = sum(confs) / len(confs)
        
        # Apply whitelist filtering if provided
        if whitelist:
            filtered = ''.join(c for c in final_text if c in whitelist or c.isspace())
            if filtered.strip():
                final_text = filtered
        
        return final_text.strip(), final_conf
        
    except Exception as e:
        if DEBUG_SIGNALS:
            print(f" PaddleOCR error ({cls_name}): {e}")
        return "", 0.0


def paddleocr_recognize_multiline(
    pil_img: Image.Image,
    cls_name: str = "weichen_block",
    whitelist: str = None
) -> Tuple[str, float]:
    """
    Run PaddleOCR on PIL image for multi-line text (weichen_block).
    Preserves line structure by joining lines with newlines instead of spaces.

    Args:
        pil_img: PIL Image to recognize
        cls_name: Class name for class-specific processing
        whitelist: Character whitelist (filtering applied post-OCR)

    Returns:
        (recognized_text_with_newlines, confidence_0_to_1)
    """
    paddle = get_paddleocr_instance()

    if paddle is None:
        return "", 0.0

    try:
        # Preprocess
        arr = preprocess_for_paddleocr(pil_img, cls_name)

        # Run PaddleOCR
        results = paddle.ocr(arr, cls=False)

        if not results or results[0] is None or len(results[0]) == 0:
            return "", 0.0

        # Extract all text and confidence, preserving line structure
        texts = []
        confs = []
        for line in results[0]:
            if line is None:
                continue
            bbox, (text, conf) = line
            texts.append(text)
            confs.append(conf)

        if not texts:
            return "", 0.0

        #  Join with newlines to preserve multi-line structure for weichen_block
        final_text = "\n".join(texts)
        final_conf = sum(confs) / len(confs)

        # Apply whitelist filtering if provided (preserve newlines)
        if whitelist:
            filtered_lines = []
            for line in final_text.split('\n'):
                filtered_line = ''.join(c for c in line if c in whitelist or c.isspace())
                if filtered_line.strip():
                    filtered_lines.append(filtered_line)
            if filtered_lines:
                final_text = '\n'.join(filtered_lines)

        return final_text.strip(), final_conf

    except Exception as e:
        if DEBUG_SIGNALS:
            print(f" PaddleOCR multiline error ({cls_name}): {e}")
        return "", 0.0


def paddleocr_multi_rotation(
    pil_img: Image.Image,
    cls_name: str = "default",
    rotations: list = [0, 90, 180, 270],
    whitelist: str = None
) -> Tuple[str, float]:
    """
    Try PaddleOCR with multiple rotations, return best result.
    Useful for cardinal/horizontal text that may be in any orientation.
    
    Args:
        pil_img: PIL Image
        cls_name: Class name
        rotations: List of rotation angles to try
        whitelist: Character whitelist
    
    Returns:
        (best_text, best_confidence)
    """
    best_txt, best_conf = "", 0.0
    
    for rot in rotations:
        if rot == 0:
            test_img = pil_img
        else:
            test_img = pil_img.rotate(rot, expand=True, fillcolor=255)
        
        txt, conf = paddleocr_recognize(test_img, cls_name, whitelist)
        
        if conf > best_conf:
            best_txt, best_conf = txt, conf
    
    return best_txt, best_conf


# ============================================================================
# PADDLEOCR INTEGRATION
# ============================================================================

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    if DEBUG_OCR:
        print(" PaddleOCR not available. Install: pip install paddleocr paddlepaddle")

_PADDLE_OCR_INSTANCE = None

_PADDLE_OCR_LOCK = threading.RLock()  # RLock allows nested calls

def paddle_ocr_locked(func):
    """Thread-safe decorator for OCR functions."""
    def wrapper(*args, **kwargs):
        with _PADDLE_OCR_LOCK:
            return func(*args, **kwargs)
    return wrapper


def get_paddleocr_instance():
    """PaddleOCR optimized for speed."""
    global _PADDLE_OCR_INSTANCE
    
    if not PADDLEOCR_AVAILABLE:
        return None
    
    if _PADDLE_OCR_INSTANCE is None:
        with _PADDLE_OCR_LOCK:
            if _PADDLE_OCR_INSTANCE is None:
                try:
                    from paddleocr import PaddleOCR
                    
                    logging.getLogger('ppocr').setLevel(logging.ERROR)

                    _PADDLE_OCR_INSTANCE = PaddleOCR(
                    use_angle_cls=False,
                    lang='en',
                    use_gpu=False,
                    show_log=False,
                    det=True,
                    rec=True,
                    cls=False,
                    rec_batch_num=1,
                    det_db_thresh=0.3,
                    det_db_box_thresh=0.5,
                    use_mp=False,
                    total_process_num=1,
                    cpu_threads=max(2, min(12, os.cpu_count() or 4)),  # ← DYNAMIC
                )
                    
                    if DEBUG_OCR:
                        print(f"PaddleOCR initialized: threads=4, mkldnn=True")

                except Exception as e:
                    if DEBUG_OCR:
                        print(f"Failed to initialize PaddleOCR: {e}")
                    _PADDLE_OCR_INSTANCE = None
    
    return _PADDLE_OCR_INSTANCE

# ============================================================================
# SIMPLE OCR (For high-DPI scans like Antwerp 800 DPI)
# ============================================================================
# Skips heavy preprocessing - just crops and runs PaddleOCR directly.
# This works better for high-quality scans where preprocessing can harm text.
# ============================================================================

def _preprocess_colored_text(img: np.ndarray) -> np.ndarray:
    """
    Convert colored text (orange/red/blue) to high-contrast grayscale.

    Uses min(R,G,B) channel which makes colored text appear dark against white background.
    This fixes OCR for orange/red coordinates that appear washed out in standard grayscale.
    """
    if len(img.shape) == 2:
        return img  # Already grayscale

    b, g, r = cv2.split(img)
    # Min of RGB channels - colored pixels become dark, white stays white
    gray = np.minimum(np.minimum(b, g), r)
    # Convert back to BGR for PaddleOCR
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


def _preprocess_text_id_artifacts(img: np.ndarray) -> np.ndarray:
    """
    Remove small line artifacts from text_id images before OCR.
    Removes thin vertical/horizontal lines (< 3px) that OCR reads as "|" or "-".

    Args:
        img: BGR image array

    Returns:
        Cleaned BGR image
    """
    # Convert to grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    # Threshold to binary
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Invert (text should be white on black for morphology)
    inv = cv2.bitwise_not(binary)

    # Remove thin vertical artifacts (< 1px wide)
    # Use opening with horizontal kernel to remove vertical lines
    kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 1))  # Horizontal 2x1
    no_vlines = cv2.morphologyEx(inv, cv2.MORPH_OPEN, kernel_h)

    # Remove thin horizontal artifacts (< 1px tall)
    # Use opening with vertical kernel to remove horizontal lines
    kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 2))  # Vertical 1x2
    no_hlines = cv2.morphologyEx(no_vlines, cv2.MORPH_OPEN, kernel_v)

    # Optional: Small closing to reconnect text that may have been broken
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2))
    cleaned = cv2.morphologyEx(no_hlines, cv2.MORPH_CLOSE, kernel_close)

    # Invert back
    result = cv2.bitwise_not(cleaned)

    # Convert back to BGR if needed
    if len(img.shape) == 3:
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

    return result


def _remove_thin_artifacts_cc(img: np.ndarray) -> np.ndarray:
    """
    Remove thin line artifacts using connected component analysis.
    More intelligent than morphological operations - preserves text characters better.

    Analyzes each connected component and removes:
    - Very small noise (< 30 pixels)
    - Thin line artifacts with extreme aspect ratio (> 8:1) and small area (< 100 pixels)
    - Single-pixel strokes that are long (< 2px width/height AND > 15px length)

    Preserves:
    - Text characters like "S", "C", "O" (normal area and aspect ratio)
    - Multi-pixel text strokes

    Args:
        img: BGR image array

    Returns:
        Cleaned BGR image with thin artifacts removed
    """
    # Convert to grayscale
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    # Threshold to binary (inverted: text=white, background=black)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Find connected components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    # Create output image (start with all black)
    result = np.zeros_like(binary)

    # Analyze each component (skip background label 0)
    for i in range(1, num_labels):
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        area = stats[i, cv2.CC_STAT_AREA]

        # Calculate aspect ratio
        aspect_ratio = max(w, h) / (min(w, h) + 1e-6)

        # Filter criteria - identify artifacts to REMOVE:
        # 1. Very small area (< 30 pixels) = noise
        is_noise = area < 30

        # 2. Extreme aspect ratio (> 8:1) AND small area (< 100) = thin line artifact
        is_thin_line = (aspect_ratio > 8.0) and (area < 100)

        # 3. Very thin width or height (< 2 pixels) AND tall/wide (> 15) = stroke artifact like "|"
        is_stroke_artifact = ((w < 2 and h > 15) or (h < 2 and w > 15))

        # Keep component if it doesn't match any artifact criteria
        if not (is_noise or is_thin_line or is_stroke_artifact):
            result[labels == i] = 255

    # Invert back (text=black, background=white)
    result = cv2.bitwise_not(result)

    # Convert back to BGR if needed
    if len(img.shape) == 3:
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)

    return result


@paddle_ocr_locked
def ocr_simple(det: dict, bgr_color: np.ndarray, pad: int = 4, preprocess_fn=None, debug_class: str = "", skip_color_preprocessing: bool = False) -> str:
    """
    Simple OCR: Crop and run PaddleOCR with automatic rotation for vertical text.
    Also handles colored text (orange/red) via min-channel preprocessing.

    Best for high-DPI (800+) scans where preprocessing can degrade text quality.

    Args:
        det: Detection dict with x1, y1, x2, y2 keys
        bgr_color: BGR image array
        pad: Padding around crop (default 4px)
        preprocess_fn: Optional preprocessing function to apply to crop before OCR
        debug_class: Optional class name for debug crop saving (e.g., "text_id", "coordinate")
        skip_color_preprocessing: If True, skip color preprocessing (for black text on white background)

    Returns:
        OCR text result (empty string if no text found)
    """
    paddle = get_paddleocr_instance()
    if paddle is None:
        return ""

    # Simple crop with padding
    H, W = bgr_color.shape[:2]
    x1 = max(0, int(det["x1"]) - pad)
    y1 = max(0, int(det["y1"]) - pad)
    x2 = min(W, int(det["x2"]) + pad)
    y2 = min(H, int(det["y2"]) + pad)

    if x2 <= x1 or y2 <= y1:
        return ""

    crop = bgr_color[y1:y2, x1:x2]

    if crop.size == 0:
        return ""

    # Save original crop for debugging
    if debug_class:
        _save_debug_crop(crop, debug_class, suffix="original")

    # Apply preprocessing if provided (e.g., artifact removal for text_id)
    if preprocess_fn is not None:
        crop = preprocess_fn(crop)
        # Save preprocessed crop for debugging
        if debug_class:
            _save_debug_crop(crop, debug_class, suffix="preprocessed")

    crop_h, crop_w = crop.shape[:2]

    # Check if text is vertical (height > 1.5 * width)
    is_vertical = crop_h > crop_w * 1.5

    def run_ocr(img):
        """Run PaddleOCR and return concatenated text."""
        try:
            results = paddle.ocr(img, cls=False)
            if not results or not results[0]:
                return ""
            texts = []
            for line in results[0]:
                if line is None:
                    continue
                bbox, (text, conf) = line
                if text and conf > 0.3:
                    texts.append(text.strip())
            return " ".join(texts) if texts else ""
        except Exception:
            return ""

    def run_ocr_with_color_variants(img):
        """
        Try OCR on both original color and preprocessed (min-channel) versions.
        Returns the best result (longest text).
        """
        # Try original color
        result_color = run_ocr(img)

        # Skip color preprocessing if requested (for black text on white background)
        if skip_color_preprocessing:
            return result_color

        # Try preprocessed (for colored text like orange/red)
        img_processed = _preprocess_colored_text(img)
        result_processed = run_ocr(img_processed)

        # Pick longest result
        if len(result_processed) > len(result_color):
            if DEBUG_OCR:
                print(f"[ocr_simple] color preprocessing helped: '{result_color}' -> '{result_processed}'")
            return result_processed
        return result_color

    def score_antwerp_coordinate(text: str) -> float:
        """
        Score OCR result for Antwerp coordinate format.
        Higher score = better match to expected format.
        Prefers small km values (0-9) over large ones (100+).
        """
        import re
        if not text:
            return -1.0

        score = 0.0
        text = text.strip()

        # Extract km value if present (for km-based scoring)
        # Also accept "-" as OCR error for "+"
        km_match = re.match(r'^(\d+)\s*[+\-]', text)
        km_value = int(km_match.group(1)) if km_match else None

        # Best: Full Antwerp format with decimal (e.g., "0+033.5", "0-033.5")
        if re.search(r'^\d+\s*[+\-]\s*\d+\.\d+$', text):
            score = 10.0 + len(text)
        # Good: Antwerp format without decimal (e.g., "0+033", "0-033")
        elif re.search(r'^\d+\s*[+\-]\s*\d+$', text):
            score = 8.0 + len(text)
        # OK: Just decimal number (e.g., "033.5")
        elif re.search(r'^\d+\.\d+$', text):
            score = 5.0 + len(text)
        # Partial match: Contains + or - somewhere with digits
        elif ('+' in text or '-' in text) and any(c.isdigit() for c in text):
            score = 3.0 + sum(c.isdigit() for c in text)
        # Fallback: Just digits
        elif any(c.isdigit() for c in text):
            score = 1.0 + sum(c.isdigit() for c in text) * 0.1

        # Prefer small km values (typical: 0-9), penalize large ones (likely backwards)
        # This fixes "811+0" vs "0+108" - both match pattern but "0+108" is correct
        if km_value is not None:
            if km_value <= 9:
                score += 5.0  # Bonus: small km values are typical
            elif km_value <= 99:
                score += 2.0  # OK: medium km values
            else:
                score -= 3.0  # Penalty: large km (100+) likely means text is backwards

        # Penalty: Leading zeros in km position (except '0' itself)
        # '004' is unusual, '0' or '4' is normal
        if km_value is not None and km_value < 100:
            km_str = km_match.group(1)
            if len(km_str) > 1 and km_str[0] == '0':
                # Has leading zeros (e.g., '004', '012')
                score -= 2.0  # Penalty: unusual format

        # Bonus: Prefer 3-digit meter values (typical Antwerp format)
        # Extract meter portion after + or -
        meter_match = re.search(r'[+\-]\s*(\d+)', text)
        if meter_match:
            meter_str = meter_match.group(1)
            meter_len = len(meter_str.replace('.', '').split()[0])  # Digits before decimal/space

            if meter_len == 3:
                score += 2.0  # Bonus: typical 3-digit meter (e.g., '033', '415', '184')
            elif meter_len == 1:
                score -= 1.0  # Penalty: single-digit meter unusual (e.g., '3')
            elif meter_len == 2:
                score += 0.5  # Small bonus: 2-digit meter acceptable (e.g., '28')

        # Garbage characters reduce score
        # Accept both + and - (minus is OCR error for plus)
        garbage_chars = sum(1 for c in text if c not in '0123456789+-. ')
        score -= garbage_chars * 0.5

        return score

    try:
        if is_vertical:
            # Try rotated versions for vertical text
            # Rotate 90° clockwise (cv2.ROTATE_90_CLOCKWISE)
            crop_rot_cw = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
            result_cw = run_ocr_with_color_variants(crop_rot_cw)

            # Rotate 90° counter-clockwise (cv2.ROTATE_90_COUNTERCLOCKWISE)
            crop_rot_ccw = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)
            result_ccw = run_ocr_with_color_variants(crop_rot_ccw)

            # Also try original (in case detection is wrong)
            result_orig = run_ocr_with_color_variants(crop)

            # Score each result based on Antwerp coordinate pattern match
            score_cw = score_antwerp_coordinate(result_cw)
            score_ccw = score_antwerp_coordinate(result_ccw)
            score_orig = score_antwerp_coordinate(result_orig)

            results = [
                (score_cw, result_cw, 'cw'),
                (score_ccw, result_ccw, 'ccw'),
                (score_orig, result_orig, 'orig')
            ]

            # Find max score
            max_score = max(r[0] for r in results)

            # Get all results with max score (handle ties)
            top_results = [r for r in results if r[0] == max_score]

            if len(top_results) > 1:
                # Multiple results tied for best score - use majority voting
                # Count how many times each text appears
                from collections import Counter
                text_counts = Counter(r[1] for r in top_results)

                # Pick the text that appears most often (majority vote)
                most_common_text, count = text_counts.most_common(1)[0]

                # Find the first result with that text
                best = next(r for r in top_results if r[1] == most_common_text)

                if DEBUG_OCR:
                    tied_scores = ', '.join(f"{r[2]}='{r[1]}'({r[0]:.1f})" for r in top_results)
                    print(f"[ocr_simple] vertical: {tied_scores} -> '{best[1]}' ({best[2]}) [majority: {count}/{len(top_results)}]")
            else:
                # Only one best result
                best = top_results[0]

                if DEBUG_OCR:
                    print(f"[ocr_simple] vertical: cw='{result_cw}'({score_cw:.1f}) ccw='{result_ccw}'({score_ccw:.1f}) orig='{result_orig}'({score_orig:.1f}) -> '{best[1]}' ({best[2]})")

            # Save final crop with OCR result for debugging
            if debug_class:
                # Save the best rotated crop based on which rotation won
                if best[2] == 'cw':
                    _save_debug_crop(crop_rot_cw, debug_class, best[1], suffix="final_cw")
                elif best[2] == 'ccw':
                    _save_debug_crop(crop_rot_ccw, debug_class, best[1], suffix="final_ccw")
                else:
                    _save_debug_crop(crop, debug_class, best[1], suffix="final_orig")

            return best[1]
        else:
            # Horizontal text - run OCR with color variants
            result = run_ocr_with_color_variants(crop)

            # Save final crop with OCR result for debugging
            if debug_class:
                _save_debug_crop(crop, debug_class, result, suffix="final")

            return result

    except Exception as e:
        if DEBUG_OCR:
            print(f"ocr_simple error: {e}")
        return ""


def _clean_antwerp_coordinate(text: str) -> str:
    """
    Clean Antwerp-format coordinates like "0+033.5", "12+456.7".

    Antwerp format: km+meters.decimals (e.g., "0+033.5" = 0km + 33.5m)
    """
    import re

    if not text:
        return ""

    text = text.strip()

    # Pattern for Antwerp format: digits + plus/minus + digits.decimals
    # Accept both "+" and "-" (OCR sometimes misreads plus as minus)
    # Examples: "0+033.5", "12+456.7", "1+234.56", "0-100.5"
    antwerp_pattern = r'(\d+)\s*([+\-])\s*(\d+(?:\.\d+)?)'
    match = re.search(antwerp_pattern, text)

    if match:
        km = match.group(1)
        separator = match.group(2)  # Preserve original separator (+ or -)
        meters = match.group(3)
        result = f"{km}{separator}{meters}"  # Keep original separator
        if DEBUG_OCR:
            print(f"[antwerp_clean] matched: '{text}' -> '{result}'")
        return result

    # Fallback: just a decimal number (no + separator)
    # Examples: "033.5", "456.78"
    decimal_pattern = r'(\d+\.\d+)'
    decimal_match = re.search(decimal_pattern, text)

    if decimal_match:
        result = decimal_match.group(1)
        if DEBUG_OCR:
            print(f"[antwerp_clean] decimal only: '{text}' -> '{result}'")
        return result

    # Last fallback: just digits
    digits_pattern = r'(\d+)'
    digits_match = re.search(digits_pattern, text)

    if digits_match:
        result = digits_match.group(1)
        if DEBUG_OCR:
            print(f"[antwerp_clean] digits only: '{text}' -> '{result}'")
        return result

    if DEBUG_OCR:
        print(f"[antwerp_clean] no pattern matched: '{text}'")

    return text  # Return original if no pattern matches


def ocr_simple_coordinate(det: dict, bgr_color: np.ndarray, config=None) -> str:
    """
    Simple coordinate OCR for high-DPI scans (Antwerp).
    Crops, runs PaddleOCR, applies Antwerp-specific cleaning.

    Args:
        det: Detection dict with x1, y1, x2, y2 keys
        bgr_color: BGR image array
        config: Optional LayoutConfig for configurable padding
    """
    # Get padding from config or use default
    pad = 3
    if config is not None and hasattr(config, 'ocr'):
        pad = config.ocr.simple_ocr_padding.get("coordinate",
              config.ocr.simple_ocr_padding.get("default", 3))

    raw = ocr_simple(det, bgr_color, pad=pad, debug_class="coordinate")

    # Debug: show raw OCR result before cleaning
    if DEBUG_OCR:
        print(f"[simple_coord] raw='{raw}' box=({det.get('x1')},{det.get('y1')})-({det.get('x2')},{det.get('y2')})")

    if not raw:
        return ""

    # Post-processing: Remove common artifact characters before format-specific cleaning
    # Remove "|" (vertical line artifacts from scan imperfections)
    raw = raw.replace("|", "")

    # Use Antwerp-specific cleaning (different format from Wien)
    # Antwerp: "0+033.5" format, Wien: "0,1234 Gl.113" format
    cleaned = _clean_antwerp_coordinate(raw)

    if DEBUG_OCR and cleaned != raw:
        print(f"[simple_coord] cleaned: '{raw}' -> '{cleaned}'")

    return cleaned


def ocr_simple_text(det: dict, bgr_color: np.ndarray, config=None, debug_class: str = "text_id") -> str:
    """
    Simple text OCR for high-DPI scans (text_id class).
    NO preprocessing - all image preprocessing methods damage 'S' characters in this font.

    Args:
        det: Detection dict with x1, y1, x2, y2 keys
        bgr_color: BGR image array
        config: Optional LayoutConfig for configurable padding
        debug_class: Class name for debug crop saving
    """
    # Get padding from config or use default
    pad = 4
    if config is not None and hasattr(config, 'ocr'):
        pad = config.ocr.simple_ocr_padding.get("text_id",
              config.ocr.simple_ocr_padding.get("default", 4))

    # DISABLED: Connected component analysis ALSO damages "S" characters
    # The thin curved segments of "S" (< 2px wide) get filtered out as artifacts
    # return ocr_simple(det, bgr_color, pad=pad, preprocess_fn=_remove_thin_artifacts_cc, debug_class=debug_class)

    # Best approach: Let PaddleOCR handle raw 800 DPI crops directly
    # Skip color preprocessing to avoid orange line artifacts being read as "i"
    result = ocr_simple(det, bgr_color, pad=pad, preprocess_fn=None, debug_class=debug_class, skip_color_preprocessing=True)

    # Post-processing: Remove common artifact characters
    # Remove "|" (vertical line artifacts from scan imperfections)
    # Remove spaces (PaddleOCR sometimes adds spurious spaces)
    result = result.replace("|", "")
    result = result.replace(" ", "")

    return result


# ===================== =======================================================
# COORDINATE OCR (UNIFIED: Routes based on angle)
# ============================================================================

@paddle_ocr_locked
def ocr_coordinate_strong(det: dict, bgr_color: np.ndarray, engine: str, debug_class: str = "coordinate") -> str:
    """
    Angular coordinate OCR - handles both simple and bracketed coordinates.
    Uses 3-step cleaning: overlap removal → bracket fixing → scoring
    OPTIMIZED: Smart candidate generation with early exit for complete coordinates.
    """
    # Get BOTH angles
    ang_normalized = float(det.get("angle", 0.0))
    ang_raw = float(det.get("angle_raw", ang_normalized))

    # Get box dimensions
    w = float(det.get("obb_w", det["x2"] - det["x1"]))
    h = float(det.get("obb_h", det["y2"] - det["y1"]))
    box_min_side = min(w, h)

    # Adaptive padding - slightly increased for edge cases
    if box_min_side < 66:
        pad = 5   # ↑ +1 for edge cases
    elif box_min_side < 76:
        pad = 9   # ↑ +1 for edge cases
    else:
        pad = 9   # ↑ +1 for edge cases

    if DEBUG_ANGLE_ROUTING:
        print(f"\n COORD ANGULAR: {w:.0f}×{h:.0f}px | raw={ang_raw:.1f}° norm={ang_normalized:.1f}° | pad={pad}")

    best_txt, best_sc = "", -1.0

    # ========================================================================
    # STEP 1: Get crop (perspective warp)
    # ========================================================================
    try:
        pil_crop = perspective_crop_from_det(det, bgr_color, pad=pad)
    except Exception as e:
        pil_crop = rotated_crop_from_det(det, bgr_color, pad=pad)

    if pil_crop.width < 5 or pil_crop.height < 5:
        return ""

    # Upscale
    pil_crop = _upscale_if_tiny(pil_crop, min_side=80, scale=3)

    # Debug: Save original crop
    if debug_class:
        crop_bgr = cv2.cvtColor(np.array(pil_crop), cv2.COLOR_RGB2BGR)
        _save_debug_crop(crop_bgr, debug_class, suffix="original_angular")

    if DEBUG_ANGLE_ROUTING:
        print(f"→ Crop size: {pil_crop.width}×{pil_crop.height}px")
    
    # ========================================================================
    # STEP 2: Line removal for angular text (GENTLER for brackets)
    # ========================================================================
    if not _is_cardinal(ang_normalized):
        #  GENTLER line removal - slightly more conservative for edge cases
        pil_pass1 = _remove_long_lines_oriented(pil_crop, ang_raw, frac_len=0.32, thickness=2)   # ↑ 0.30→0.32
        pil_pass2 = _remove_long_lines_oriented(pil_pass1, ang_raw, frac_len=0.27, thickness=6)  # ↑ 0.25→0.27
        pil_final = _remove_long_lines_oriented(pil_pass2, ang_raw, frac_len=0.22, thickness=10) # ↑ 0.20→0.22

        if DEBUG_ANGLE_ROUTING:
            print(f"→ Applied 3-pass line removal (gentler)")
    else:
        pil_final = pil_crop
        if DEBUG_ANGLE_ROUTING:
            print(f"→ No line removal (near-cardinal)")
    
    # ========================================================================
    # STEP 3: Preprocessing variants
    # ========================================================================
    g0 = _pil_to_gray_np(pil_final)
    g1 = _enhance_contrast(g0)
    g2 = _binarize_for_text(g1)
    
    # Angular gets inverted variant too
    if _is_cardinal(ang_normalized):
        variants = [g2, g1, g0]
    else:
        variants = [g2, _invert(g2), g1, g0]

    bases = [Image.fromarray(v) for v in variants]
    rotations = [0, 90, 180, 270]
    
    # ========================================================================
    # STEP 4: PaddleOCR with 3-step cleaning + OPTIMIZED MERGING
    # ========================================================================
    paddle = get_paddleocr_instance()

    if paddle is None:
        if DEBUG_ANGLE_ROUTING:
            print(f"PaddleOCR not available")
        return ""

    if DEBUG_ANGLE_ROUTING:
        print(f"→ Running PaddleOCR...")

    try:
        for base_idx, base in enumerate(bases):
            for rot in rotations:
                test_img = base.rotate(rot, expand=True, fillcolor=255) if rot != 0 else base
                test_arr = np.array(test_img)

                if len(test_arr.shape) == 2:
                    test_arr = cv2.cvtColor(test_arr, cv2.COLOR_GRAY2BGR)

                # Run PaddleOCR
                results = paddle.ocr(test_arr, cls=False)

                if not results or not results[0]:
                    continue

                #  Collect ALL detections with their positions
                all_detections = []
                for line in results[0]:
                    if line is None:
                        continue
                    bbox, (text, conf) = line
                    
                    if not text:
                        continue
                    
                    # Calculate X-position (left edge of bbox)
                    x_pos = min(pt[0] for pt in bbox)
                    
                    all_detections.append({
                        'text': text,
                        'conf': conf,
                        'x_pos': x_pos,
                        'bbox': bbox
                    })
                
                if not all_detections:
                    continue
                
                #  Sort detections by X-position (left to right)
                all_detections.sort(key=lambda d: d['x_pos'])

                #  Quick quality check - skip if all detections are low confidence
                if all(d['conf'] < 0.40 for d in all_detections):
                    if DEBUG_ANGLE_ROUTING:
                        print(f"[var={base_idx} rot={rot:3d}°] → SKIP: All detections low confidence")
                    continue
                
                #  OPTIMIZED: Smart candidate generation with pre-filtering
                candidates = []
                
                # Quick check: Do we have a number and a bracket?
                has_number = any(any(c.isdigit() for c in d['text']) for d in all_detections)
                has_bracket = any('(' in d['text'] or ')' in d['text'] for d in all_detections)
                
                # CASE 1: Single detection (most common - ~60% of cases)
                if len(all_detections) == 1:
                    candidates.append({
                        'text': all_detections[0]['text'],
                        'conf': all_detections[0]['conf'],
                        'is_merged': False
                    })
                
                # CASE 2: Two detections - likely number + bracket
                elif len(all_detections) == 2:
                    det1, det2 = all_detections[0], all_detections[1]
                    avg_conf = (det1['conf'] + det2['conf']) / 2
                    
                    # Try both individual (in case one is complete)
                    candidates.append({'text': det1['text'], 'conf': det1['conf'], 'is_merged': False})
                    candidates.append({'text': det2['text'], 'conf': det2['conf'], 'is_merged': False})
                    
                    # Only merge if it looks like number + bracket
                    if has_number and has_bracket:
                        candidates.append({
                            'text': det1['text'] + det2['text'],  # No space
                            'conf': avg_conf,
                            'is_merged': True
                        })
                        # Only try with space if bracket is in second detection
                        if '(' in det2['text']:
                            candidates.append({
                                'text': det1['text'] + ' ' + det2['text'],  # With space
                                'conf': avg_conf,
                                'is_merged': True
                            })
                
                # CASE 3: Three or more detections - rare, but handle it
                else:
                    # Add individual detections
                    for det in all_detections:
                        candidates.append({'text': det['text'], 'conf': det['conf'], 'is_merged': False})
                    
                    # Only try merging if we have number + bracket pattern
                    if has_number and has_bracket:
                        all_texts = [d['text'] for d in all_detections]
                        avg_conf = sum(d['conf'] for d in all_detections) / len(all_detections)
                        
                        # Try without spaces
                        candidates.append({
                            'text': ''.join(all_texts),
                            'conf': avg_conf,
                            'is_merged': True
                        })
                        
                        # Try with spaces
                        if len(all_detections) == 2:
                            candidates.append({
                                'text': ' '.join(all_texts),
                                'conf': avg_conf,
                                'is_merged': True
                            })
                
                #  Process all candidates
                for cand in candidates:
                    text = cand['text']
                    conf = cand['conf']
                    is_merged = cand.get('is_merged', False)
                    
                    if DEBUG_ANGLE_ROUTING:
                        marker = "[MERGED]" if is_merged else "[SINGLE]"
                        print(f"[var={base_idx} rot={rot:3d}°] {marker} RAW: '{text}' (conf={conf:.2f})")
                    
                    # STEP 1: Remove overlap garbage (SKIP for merged candidates)
                    if is_merged:
                        txt_clean = text
                    else:
                        txt_clean = _clean_coordinate_overlap(text)

                        if not txt_clean:
                            if DEBUG_ANGLE_ROUTING:
                                print(f"→ SKIPPED: No valid coordinate pattern")
                            continue
                    
                    # STEP 2: Fix bracket mistakes
                    txt_fixed = _fix_coordinate_brackets(txt_clean)
                    
                    if DEBUG_ANGLE_ROUTING:
                        if txt_fixed != text:
                            print(f"→ CLEANED: '{text}' → '{txt_fixed}'")
                    
                    # STEP 3: Score
                    sc = _score_coord_text(txt_fixed)
                    
                    if DEBUG_ANGLE_ROUTING and sc > 0:
                        print(f"→ SCORE: {sc:.2f}")
                    
                    if sc > best_sc:
                        best_txt, best_sc = txt_fixed, sc
                        if DEBUG_ANGLE_ROUTING:
                            print(f"→ NEW BEST!")
                        
                        #  Smart early exit - only for complete coordinates
                        has_brackets = '(' in txt_fixed and ')' in txt_fixed
                        
                        if has_brackets and sc >= 2.0 and conf >= 0.50:
                            if DEBUG_ANGLE_ROUTING:
                                print(f"EARLY EXIT (complete): '{best_txt}'")
                            #  FINAL CLEANING before return
                            best_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', best_txt)
                            best_txt = re.sub(r'\s*[|/\\]\s*$', '', best_txt)
                            return best_txt.strip()
                        elif not has_brackets and sc >= 2.5 and conf >= 0.80:
                            if DEBUG_ANGLE_ROUTING:
                                print(f"EARLY EXIT (high conf simple): '{best_txt}'")
                            #  FINAL CLEANING before return
                            best_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', best_txt)
                            best_txt = re.sub(r'\s*[|/\\]\s*$', '', best_txt)
                            return best_txt.strip()
            
            # Check if we have a good result after each base variant
            if best_txt and best_sc >= 1.0:
                if DEBUG_ANGLE_ROUTING:
                    print(f"RESULT: '{best_txt}' (score:{best_sc:.2f})")
                #  FINAL CLEANING before return
                best_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', best_txt)
                best_txt = re.sub(r'\s*[|/\\]\s*$', '', best_txt)
                return best_txt.strip()
                        
    except Exception as e:
        if DEBUG_ANGLE_ROUTING:
            print(f"[PaddleOCR] → EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
    
    if DEBUG_ANGLE_ROUTING:
        if best_txt:
            print(f"FINAL: '{best_txt}' (score:{best_sc:.2f})")
        else:
            print(f"FAILED")

    #  FINAL CLEANING before return
    if best_txt:
        best_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', best_txt)
        best_txt = re.sub(r'\s*[|/\\]\s*$', '', best_txt)
    
    return best_txt.strip()

def _clean_coordinate_overlap(text: str) -> str:
    """
    Clean coordinate text that has overlap artifacts from nearby text.
    """
    if not text:
        return ""

    import re

    original_text = text

    # PRE-FIX: Common OCR errors where 0 is misread as O/Q
    # Only fix at positions where it looks like a coordinate number
    # Pattern: Q or O followed by comma/period and digits = likely "0,xxxx"
    text = re.sub(r'^[QOqo]([,.])', r'0\1', text)  # Start: Q,0294 -> 0,0294
    text = re.sub(r'^-[QOqo]([,.])', r'-0\1', text)  # Negative: -Q,0294 -> -0,0294
    text = re.sub(r'([,.])[QOqo]([,.\d])', r'\g<1>0\2', text)  # Middle: 0,Q294 -> 0,0294

    #  ONLY print if DEBUG_ANGLE_ROUTING
    if DEBUG_ANGLE_ROUTING:
        print(f"[clean_overlap] Input: '{original_text}' (after OCR fix: '{text}')")
    
    #  MOVED: Pre-clean AFTER pattern matching (not before!)
    # This preserves brackets during pattern detection
    
    # Pattern 1a: Complete bracketed coordinate
    bracket_complete_pattern = r'-?\d+[.,]\d+$[A-Za-z0-9.,]+$'
    bracket_complete_match = re.search(bracket_complete_pattern, text)
    
    if bracket_complete_match:
        result = bracket_complete_match.group(0).replace(DECIMAL_SEP_INPUT, DECIMAL_SEP_OUTPUT)
        
        #  NOW clean trailing alphabet AFTER extraction
        result = re.sub(r'\s*[a-zA-Z]\s*$', '', result)
        result = re.sub(r'\s*[|/\\]\s*$', '', result)
        
        if DEBUG_ANGLE_ROUTING:
            print(f"[clean_overlap] Pattern 1a (complete bracket): '{original_text}' → '{result}'")
        
        return result
    
    # Pattern 1b: Incomplete bracketed coordinate
    bracket_incomplete_pattern = r'-?\d+[.,]\d+\([A-Za-z0-9.,]+'
    bracket_incomplete_match = re.search(bracket_incomplete_pattern, text)
    
    if bracket_incomplete_match:
        result = bracket_incomplete_match.group(0).replace(DECIMAL_SEP_INPUT, DECIMAL_SEP_OUTPUT)
        
        # Add closing bracket if missing
        if ')' not in result:
            result += ')'
        
        #  NOW clean trailing alphabet AFTER extraction
        result = re.sub(r'\s*[a-zA-Z]\s*$', '', result)
        result = re.sub(r'\s*[|/\\]\s*$', '', result)
        
        if DEBUG_ANGLE_ROUTING:
            print(f"[clean_overlap] Pattern 1b (incomplete bracket, added closing): '{original_text}' → '{result}'")
        
        return result
    
    # Pattern 2: Simple number (no brackets)
    simple_pattern = r'-?\d+[.,]\d+(?=\s|$|[^0-9.,])'
    simple_match = re.search(simple_pattern, text)
    
    if simple_match:
        result = simple_match.group(0).replace(DECIMAL_SEP_INPUT, DECIMAL_SEP_OUTPUT)
        
        #  Clean trailing alphabet for simple coordinates too
        result = re.sub(r'\s*[a-zA-Z]\s*$', '', result)
        result = re.sub(r'\s*[|/\\]\s*$', '', result)
        
        if DEBUG_ANGLE_ROUTING:
            print(f"[clean_overlap] Pattern 2 (simple number): '{original_text}' → '{result}'")
        
        return result
    
    # No valid coordinate pattern found
    if DEBUG_ANGLE_ROUTING:
        print(f"[clean_overlap] NO VALID PATTERN in: '{text}'")
    
    return ""

def _score_coord_text(txt: str) -> float:
    """
    Score coordinate text - handles both simple and bracketed coordinates.
    Examples: 
        "0.0061" → 1.3
        "0.0734(Gl.112)" → 2.5
    """
    if not txt:
        return -1.0
    
    txt = txt.strip()
    
    # Quick validation
    if not _looks_like_coordinate(txt):
        if DEBUG_ANGLE_ROUTING:
            print(f"[score] Not a coordinate: '{txt}'")
        return 0.0
    
    #  HANDLE BRACKETED COORDINATES like "0.0734(Gl.112)"
    if '(' in txt and ')' in txt:
        try:
            main_part = txt.split('(')[0].strip()
            bracket_part = txt.split('(')[1].split(')')[0].strip()
        except:
            if DEBUG_ANGLE_ROUTING:
                print(f"[score]  Malformed bracket: '{txt}'")
            return 0.5  # Malformed
        
        # Score main coordinate part (e.g., "0.0734")
        main_digits = sum(c.isdigit() for c in main_part)
        main_has_dot = '.' in main_part
        
        main_score = 0.0
        if main_digits >= 1 and main_has_dot:
            main_score = 1.0 + (main_digits * 0.1)
        
        # Score bracket part (e.g., "Gl.112")
        bracket_score = 0.0
        if 'Gl.' in bracket_part or 'gl.' in bracket_part:
            bracket_score = 0.5
        bracket_digits = sum(c.isdigit() for c in bracket_part)
        bracket_score += bracket_digits * 0.05
        
        total_score = main_score + bracket_score
        
        if DEBUG_ANGLE_ROUTING:
            print(f"[score] Bracketed: '{txt}' → main={main_score:.2f}, bracket={bracket_score:.2f}, total={total_score:.2f}")
        
        return total_score
    
    #  SIMPLE COORDINATE (no brackets) - ORIGINAL LOGIC
    digit_count = sum(c.isdigit() for c in txt)
    has_dot = '.' in txt
    has_comma = ',' in txt
    
    if digit_count < 1:
        if DEBUG_ANGLE_ROUTING:
            print(f"[score] No digits: '{txt}'")
        return 0.0
    
    score = 1.0
    score += digit_count * 0.1
    
    if has_dot or has_comma:
        score += 0.3
    
    if DEBUG_ANGLE_ROUTING:
        print(f"[score] Simple: '{txt}' → {score:.2f}")
    
    return max(0.0, score)


def _fix_coordinate_brackets(text: str) -> str:
    """
    Fix common OCR mistakes in coordinates with brackets.
    Example: "0.0734(GI.112)" → "0.0734(Gl.112)"
    """
    if not text:
        return ""
    
    import re
    
    original_text = text  #  Save for debug
    
    # 1. Replace decimal separator (German uses comma, normalize to dot)
    text = text.replace(DECIMAL_SEP_INPUT, DECIMAL_SEP_OUTPUT)
    
    # 2. Fix Gl. pattern - all variations: GI, G1, Gi, gi, g1, gI → Gl.
    text = re.sub(r'[Gg][Ii1l]\.?', 'Gl.', text)
    
    # 3. Remove extra spaces inside brackets
    text = re.sub(r'\(\s+', '(', text)
    text = re.sub(r'\s+\)', ')', text)
    
    result = text.strip()
    
    if DEBUG_ANGLE_ROUTING and result != original_text:
        print(f"[fix_brackets] '{original_text}' → '{result}'")
    
    return result


def _looks_like_coordinate(text: str) -> bool:
    """
    Quick check if text looks like a valid coordinate.
    Examples: "0.0734", "0.0734(Gl.112)", "10.5"
    """
    if not text:
        return False
    
    # Must start with a digit or minus sign
    if not (text[0].isdigit() or text[0] == '-'):
        if DEBUG_ANGLE_ROUTING:
            print(f"[looks_like] Doesn't start with digit/minus: '{text}'")
        return False
    
    # Must contain at least one digit and one dot
    has_digit = any(c.isdigit() for c in text)
    has_dot = '.' in text
    
    if not (has_digit and has_dot):
        if DEBUG_ANGLE_ROUTING:
            print(f"[looks_like] Missing digit or dot: '{text}' (has_digit={has_digit}, has_dot={has_dot})")
        return False
    
    # If it has brackets, they must be paired
    if '(' in text or ')' in text:
        if not ('(' in text and ')' in text):
            if DEBUG_ANGLE_ROUTING:
                print(f"[looks_like] Unpaired brackets: '{text}'")
            return False
    
    if DEBUG_ANGLE_ROUTING:
        print(f"[looks_like] Valid: '{text}'")
    
    return True

@paddle_ocr_locked
def ocr_weichen_block(anchor: dict, bgr_color: np.ndarray, debug_class: str = "weichen_block") -> str:
    """
    OCR for weichen blocks - starts output from first line beginning with "W".
    Simplified version without strict validation.
    """
    cls_name = anchor.get("name", "weichen_block")

    # Get box dimensions
    w = float(anchor.get("obb_w", anchor["x2"] - anchor["x1"]))
    h = float(anchor.get("obb_h", anchor["y2"] - anchor["y1"]))

    if DEBUG_ANGLE_ROUTING:
        print(f"\n WEICHEN BLOCK: {w:.0f}×{h:.0f}px")

    # Minimal padding
    pad = 0
    x1 = max(0, int(anchor["x1"] - pad))
    y1 = max(0, int(anchor["y1"] - pad))
    x2 = min(bgr_color.shape[1], int(anchor["x2"] + pad))
    y2 = min(bgr_color.shape[0], int(anchor["y2"] + pad))

    crop_bgr = bgr_color[y1:y2, x1:x2]

    # Debug: Save original crop
    if debug_class:
        _save_debug_crop(crop_bgr, debug_class, suffix="original")

    pil_crop = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
    
    if pil_crop.width < 10 or pil_crop.height < 10:
        if DEBUG_ANGLE_ROUTING:
            print(f"Crop too small: {pil_crop.width}×{pil_crop.height}")
        return ""
    
    # Store original height
    crop_height_original = pil_crop.height
    
    # Gentle upscaling
    min_side = min(pil_crop.width, pil_crop.height)
    scale = 1
    
    if min_side < 80:
        scale = 2
        pil_crop = pil_crop.resize(
            (pil_crop.width * scale, pil_crop.height * scale), 
            Image.LANCZOS
        )
    
    crop_height_scaled = pil_crop.height
    
    if DEBUG_ANGLE_ROUTING:
        print(f"→ Crop: {pil_crop.width}×{pil_crop.height}px (pad={pad}px, scale={scale}x)")
    
    # Preprocessing
    g = _pil_to_gray_np(pil_crop)
    g_enhanced = _enhance_contrast(g)
    
    variants = [
        ("enhanced", g_enhanced),
        ("grayscale", g),
    ]
    
    paddle = get_paddleocr_instance()
    
    if paddle is None:
        if DEBUG_ANGLE_ROUTING:
            print(f"PaddleOCR not available")
        return ""
    
    best_lines = []
    best_score = 0.0
    
    if DEBUG_ANGLE_ROUTING:
        print(f"→ Running PaddleOCR...")
    
    try:
        for var_name, img_arr in variants:
            # Convert to BGR
            if len(img_arr.shape) == 2:
                img_arr = cv2.cvtColor(img_arr, cv2.COLOR_GRAY2BGR)
            
            # Run PaddleOCR
            results = paddle.ocr(img_arr, cls=False)
            
            if not results or not results[0]:
                if DEBUG_ANGLE_ROUTING:
                    print(f"[{var_name}] No text detected")
                continue
            
            if DEBUG_ANGLE_ROUTING:
                print(f"[{var_name}] Detected {len(results[0])} text lines")
            
            # Collect ALL text lines with positions
            all_text_lines = []
            
            for line in results[0]:
                if line is None:
                    continue
                bbox, (text, conf) = line
                
                if not text:
                    continue
                
                # Get Y position (vertical center of bbox)
                y_pos = sum(pt[1] for pt in bbox) / len(bbox)
                
                # Clean text (fix missing W)
                text_clean = text.strip()
                
                all_text_lines.append({
                    'text': text_clean,
                    'y_pos': y_pos,
                    'conf': conf
                })
                
                if DEBUG_ANGLE_ROUTING:
                    print(f"Line y={y_pos:.1f}: '{text_clean}' (conf={conf:.2f})")
            
            if not all_text_lines:
                if DEBUG_ANGLE_ROUTING:
                    print(f"[{var_name}] No valid text lines after cleaning")
                continue
            
            # Sort by Y-position (top to bottom)
            all_text_lines.sort(key=lambda x: x['y_pos'])
            
            # Find first line starting with "W"
            first_w_index = None
            for idx, line_info in enumerate(all_text_lines):
                if (line_info.get('text') or '').upper().startswith('W'):
                    first_w_index = idx
                    if DEBUG_ANGLE_ROUTING:
                        print(f"→ First 'W' line found at index {idx}: '{line_info['text']}'")
                    break
            
            #  SIMPLIFIED: Keep lines from first "W" onwards WITHOUT validation
            if first_w_index is not None:
                valid_lines = all_text_lines[first_w_index:]
                
                if DEBUG_ANGLE_ROUTING:
                    print(f"→ Keeping {len(valid_lines)} lines from first 'W' onwards")
                    if first_w_index > 0:
                        print(f"→ Discarded {first_w_index} lines before first 'W'")
                
                # Calculate score (no validation filtering)
                total_conf = sum(l['conf'] for l in valid_lines)
                avg_conf = total_conf / len(valid_lines)
                score = len(valid_lines) * avg_conf
                
                filtered_lines = valid_lines  #  Use all lines without validation
                
            else:
                # No line starting with "W" found
                if DEBUG_ANGLE_ROUTING:
                    print(f"→ No line starting with 'W' found, using all lines")
                
                #  FALLBACK: If no "W" line found, use all lines anyway
                filtered_lines = all_text_lines
                total_conf = sum(l['conf'] for l in filtered_lines)
                avg_conf = total_conf / len(filtered_lines)
                score = len(filtered_lines) * avg_conf
            
            if DEBUG_ANGLE_ROUTING:
                print(f"→ Score: {score:.2f} (lines={len(filtered_lines)})")
            
            if score > best_score:
                best_score = score
                best_lines = filtered_lines
                if DEBUG_ANGLE_ROUTING:
                    print(f"→ NEW BEST!")
                    
    except Exception as e:
        if DEBUG_ANGLE_ROUTING:
            print(f"[PaddleOCR] → EXCEPTION: {e}")
            import traceback
            traceback.print_exc()
    
    # Return result
    if best_lines:
        result = '\n'.join(line['text'] for line in best_lines)
        
        if DEBUG_ANGLE_ROUTING:
            print(f"\n   RESULT ({len(best_lines)} lines):")
            for i, line in enumerate(best_lines):
                print(f"Line {i+1}: {line['text']}")
        
        return result
    
    if DEBUG_ANGLE_ROUTING:
        print(f"FAILED: No text detected by PaddleOCR")
    
    return ""


@paddle_ocr_locked
def ocr_coordinate_horizontal(det: dict, bgr_color: np.ndarray, engine: str, debug_class: str = "coordinate") -> str:
    """
    Cardinal coordinate OCR - handles both simple and bracketed coordinates.
    OPTIMIZED: Smart candidate generation with early exit for complete coordinates.
    """
    ang_normalized = float(det.get("angle", 0.0))

    w = float(det.get("obb_w", det["x2"] - det["x1"]))
    h = float(det.get("obb_h", det["y2"] - det["y1"]))
    box_min_side = min(w, h)

    # ASYMMETRIC PADDING: No left padding, minimal right padding (capture close brackets, reject distant noise)
    pad_left = 0
    pad_right = max(3, min(5, int(box_min_side * 0.05)))  # Reduced: 3-5px instead of 8-15px
    pad_vertical = max(4, min(10, int(box_min_side * 0.08)))  # Small vertical padding

    if DEBUG_ANGLE_ROUTING:
        print(f"\n COORD CARDINAL: {w:.0f}×{h:.0f}px → pad_left={pad_left}, pad_right={pad_right}")

    # Manual asymmetric crop (can't use crop_pil which does symmetric padding)
    H, W = bgr_color.shape[:2]
    x1 = max(0, int(det["x1"]) - pad_left)
    y1 = max(0, int(det["y1"]) - pad_vertical)
    x2 = min(W, int(det["x2"]) + pad_right)
    y2 = min(H, int(det["y2"]) + pad_vertical)

    try:
        pil_crop = Image.fromarray(cv2.cvtColor(bgr_color[y1:y2, x1:x2], cv2.COLOR_BGR2RGB))
    except Exception:
        pil_crop = crop_pil(bgr_color, det["x1"], det["y1"], det["x2"], det["y2"], pad=pad_right)

    if pil_crop.width < 5 or pil_crop.height < 5:
        return ""

    pil_crop = _upscale_if_tiny(pil_crop, min_side=90, scale=3)

    # Debug: Save original crop
    if debug_class:
        crop_bgr = cv2.cvtColor(np.array(pil_crop), cv2.COLOR_RGB2BGR)
        _save_debug_crop(crop_bgr, debug_class, suffix="original_horizontal")
    
    if pil_crop.width < 10 or pil_crop.height < 10:
        return ""
    
    g0 = _pil_to_gray_np(pil_crop)
    g1 = _enhance_contrast(g0)
    g2 = _binarize_for_text(g1)
    
    bases = [Image.fromarray(g1), Image.fromarray(g2), Image.fromarray(g0)]
    
    best_txt, best_sc = "", -1.0
    rotations = [0, 90, 180, 270]
    
    paddle = get_paddleocr_instance()
    
    if paddle is None:
        return ""
    
    if DEBUG_ANGLE_ROUTING:
        print(f"→ Running PaddleOCR...")
    
    try:
        for base_idx, base in enumerate(bases):
            for rot in rotations:
                test_img = base.rotate(rot, expand=True, fillcolor=255) if rot != 0 else base
                test_arr = np.array(test_img)
                
                if len(test_arr.shape) == 2:
                    test_arr = cv2.cvtColor(test_arr, cv2.COLOR_GRAY2BGR)
                
                # Run PaddleOCR
                results = paddle.ocr(test_arr, cls=False)
                
                if not results or not results[0]:
                    continue
                
                #  Collect ALL detections with their positions
                all_detections = []
                for line in results[0]:
                    if line is None:
                        continue
                    bbox, (text, conf) = line
                    
                    if not text:
                        continue
                    
                    # Calculate X-position (left edge of bbox)
                    x_pos = min(pt[0] for pt in bbox)
                    
                    all_detections.append({
                        'text': text,
                        'conf': conf,
                        'x_pos': x_pos,
                        'bbox': bbox
                    })
                
                if not all_detections:
                    continue
                
                #  Sort detections by X-position (left to right)
                all_detections.sort(key=lambda d: d['x_pos'])
                
                #  Quick quality check
                if all(d['conf'] < 0.40 for d in all_detections):
                    if DEBUG_ANGLE_ROUTING:
                        print(f"[var={base_idx} rot={rot:3d}°] → SKIP: All detections low confidence")
                    continue
                
                #  OPTIMIZED: Smart candidate generation
                candidates = []
                
                has_number = any(any(c.isdigit() for c in d['text']) for d in all_detections)
                has_bracket = any('(' in d['text'] or ')' in d['text'] for d in all_detections)
                
                # CASE 1: Single detection
                if len(all_detections) == 1:
                    candidates.append({
                        'text': all_detections[0]['text'],
                        'conf': all_detections[0]['conf'],
                        'is_merged': False
                    })
                
                # CASE 2: Two detections
                elif len(all_detections) == 2:
                    det1, det2 = all_detections[0], all_detections[1]
                    avg_conf = (det1['conf'] + det2['conf']) / 2
                    
                    candidates.append({'text': det1['text'], 'conf': det1['conf'], 'is_merged': False})
                    candidates.append({'text': det2['text'], 'conf': det2['conf'], 'is_merged': False})
                    
                    if has_number and has_bracket:
                        candidates.append({
                            'text': det1['text'] + det2['text'],
                            'conf': avg_conf,
                            'is_merged': True
                        })
                        if '(' in det2['text']:
                            candidates.append({
                                'text': det1['text'] + ' ' + det2['text'],
                                'conf': avg_conf,
                                'is_merged': True
                            })
                
                # CASE 3: Three or more
                else:
                    for det in all_detections:
                        candidates.append({'text': det['text'], 'conf': det['conf'], 'is_merged': False})
                    
                    if has_number and has_bracket:
                        all_texts = [d['text'] for d in all_detections]
                        avg_conf = sum(d['conf'] for d in all_detections) / len(all_detections)
                        
                        candidates.append({
                            'text': ''.join(all_texts),
                            'conf': avg_conf,
                            'is_merged': True
                        })
                        
                        if len(all_detections) == 2:
                            candidates.append({
                                'text': ' '.join(all_texts),
                                'conf': avg_conf,
                                'is_merged': True
                            })
                
                #  Process all candidates
                for cand in candidates:
                    text = cand['text']
                    conf = cand['conf']
                    is_merged = cand.get('is_merged', False)
                    
                    if DEBUG_ANGLE_ROUTING:
                        marker = "[MERGED]" if is_merged else "[SINGLE]"
                        print(f"[var={base_idx} rot={rot:3d}°] {marker} RAW: '{text}' (conf={conf:.2f})")
                    
                    # STEP 1: Remove overlap garbage
                    if is_merged:
                        txt_clean = text
                    else:
                        txt_clean = _clean_coordinate_overlap(text)
                        
                        if not txt_clean:
                            if DEBUG_ANGLE_ROUTING:
                                print(f"→ SKIPPED: No valid pattern")
                            continue
                    
                    # STEP 2: Fix bracket mistakes
                    txt_fixed = _fix_coordinate_brackets(txt_clean)
                    
                    if DEBUG_ANGLE_ROUTING:
                        if txt_fixed != text:
                            print(f"→ CLEANED: '{text}' → '{txt_fixed}'")
                    
                    # STEP 3: Score
                    sc = _score_coord_text(txt_fixed)
                    
                    if DEBUG_ANGLE_ROUTING and sc > 0:
                        print(f"→ SCORE: {sc:.2f}")
                    
                    if sc > best_sc:
                        best_txt, best_sc = txt_fixed, sc
                        if DEBUG_ANGLE_ROUTING:
                            print(f"→ NEW BEST!")
                        
                        #  Smart early exit
                        has_brackets = '(' in txt_fixed and ')' in txt_fixed
                        
                        if has_brackets and sc >= 2.0 and conf >= 0.50:
                            if DEBUG_ANGLE_ROUTING:
                                print(f"EARLY EXIT (complete): '{best_txt}'")
                            #  FINAL CLEANING
                            best_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', best_txt)
                            best_txt = re.sub(r'\s*[|/\\]\s*$', '', best_txt)
                            return best_txt.strip()
                        elif not has_brackets and sc >= 2.5 and conf >= 0.80:
                            if DEBUG_ANGLE_ROUTING:
                                print(f"EARLY EXIT (high conf simple): '{best_txt}'")
                            #  FINAL CLEANING
                            best_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', best_txt)
                            best_txt = re.sub(r'\s*[|/\\]\s*$', '', best_txt)
                            return best_txt.strip()
            
            # Check after each base variant
            if best_txt and best_sc >= 1.0:
                if DEBUG_ANGLE_ROUTING:
                    print(f"RESULT: '{best_txt}' (score:{best_sc:.2f})")
                #  FINAL CLEANING
                best_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', best_txt)
                best_txt = re.sub(r'\s*[|/\\]\s*$', '', best_txt)
                return best_txt.strip()
                
    except Exception as e:
        if DEBUG_ANGLE_ROUTING:
            print(f"[PaddleOCR] → EXCEPTION: {e}")
    
    if DEBUG_ANGLE_ROUTING:
        if best_txt:
            print(f"FINAL: '{best_txt}' (score:{best_sc:.2f})")
        else:
            print(f"FAILED")
    
    if best_txt:
        #  FINAL CLEANING PASS
        best_txt = re.sub(r'\s*[a-zA-Z]\s*$', '', best_txt)
        best_txt = re.sub(r'\s*[|/\\]\s*$', '', best_txt)
        best_txt = best_txt.strip()
        
        if DEBUG_ANGLE_ROUTING:
            print(f"FINAL (after cleaning): '{best_txt}' (score:{best_sc:.2f})")
    
    return best_txt.strip()

def ocr_coordinate_angular(det: dict, bgr_color: np.ndarray, engine: str, debug_class: str = "coordinate") -> str:
    """
    Angular coordinate OCR: Uses strong path with PaddleOCR primary.
    PaddleOCR's angle classification handles tilted text well.
    """
    # ocr_coordinate_strong now has PaddleOCR as primary
    return ocr_coordinate_strong(det, bgr_color, "paddleocr", debug_class=debug_class)

def ocr_coordinate_unified(det: dict, bgr_color: np.ndarray, engine: str, config=None, debug_class: str = "coordinate") -> str:
    """
    UNIFIED COORDINATE OCR: Routes based on NORMALIZED angle (visual orientation).

    - If config.ocr.use_simple_ocr=True: Use simple PaddleOCR (for high-DPI like Antwerp)
    - Cardinal (near 0°, 90°, 180°, 270°): Use simple rotation with 4-direction sweep
    - Angular (tilted): Use perspective warp + rotation testing
    """
    # Check for simple OCR mode (high-DPI scans like Antwerp)
    if config is not None and hasattr(config, 'ocr') and config.ocr.use_simple_ocr:
        return ocr_simple_coordinate(det, bgr_color, config)

    # USE NORMALIZED ANGLE for routing decision
    ang_normalized = float(det.get("angle", 0.0))
    ang_raw = float(det.get("angle_raw", ang_normalized))

    if _is_cardinal(ang_normalized):  # Check normalized angle
        # Cardinal path (visually aligned to axes)
        _debug_angle("OCR_COORD", det, "CARDINAL", "→ horizontal OCR (4-dir sweep)")
        return ocr_coordinate_horizontal(det, bgr_color, engine, debug_class=debug_class)
    else:
        # Angular path (truly tilted, e.g., 30°, 45°, 60°)
        _debug_angle("OCR_COORD", det, "ANGULAR", "→ strong OCR (perspective+rotations)")
        return ocr_coordinate_angular(det, bgr_color, engine, debug_class=debug_class)

# ============================================================================
# SIGNAL OCR (with angle branching)
# ============================================================================

# Default signal pattern - overwritten by configure_from_config() when profile loaded
# Includes German umlauts (Ä, Ö, Ü) by default, configurable via validation.class_id_patterns
SIG_STRICT_RE = re.compile(r'^[A-ZÄÖÜ]{1,4}\s*\d{1,4}$')

def _only_az09(s: str) -> str:
    # Keep alphanumeric chars plus umlauts (for international support, extend as needed)
    t = ''.join(ch for ch in s.upper() if ch.isalnum() or ch in 'ÄÖÜ ')
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def _is_strict_signal_id(s: str) -> bool:
    """Check if string matches signal ID pattern (uses configurable CLASS_ID_PATTERNS)."""
    ss = _only_az09(s)
    # Use pattern from CLASS_ID_PATTERNS if available (updated by config)
    signal_pattern = CLASS_ID_PATTERNS.get("signal")
    if signal_pattern:
        # Allow whitespace in the match by using a relaxed version
        try:
            relaxed_pattern = signal_pattern.replace(r'\d', r'\s*\d')
            return bool(re.match(relaxed_pattern, ss))
        except re.error:
            pass
    return bool(SIG_STRICT_RE.match(ss))

def _normalize_signal_digits(s: str) -> str:
    ss = _only_az09(s)
    # Use a generic pattern that handles various signal formats
    m = re.match(r'^([A-ZÄÖÜ]{1,4})\s*([A-Z0-9]{1,4})$', ss)
    if not m:
        return ss
    head, tail = m.groups()
    trans = str.maketrans({'O': '0', 'I': '1', 'L': '1', 'S': '5', 'B': '8', 'Z': '2', 'G': '6', 'Q': '0', 'D': '0'})
    return head + tail.translate(trans)

def _post_fix_missing_zero_middle(s: str) -> str:
    """
    DISABLED - This function caused incorrect OCR results.
    Returns input unchanged. User can manually correct OCR errors if needed.
    """
    return s


def _merge_adjacent_tokens_easyocr(detail_items, anchor):
    if not detail_items:
        return None, -1.0

    items = []
    for it in detail_items:
        if len(it) < 3:
            continue
        bbox, txt, conf = it[0], (it[1] or "").strip(), float(it[2] or 0.0)
        if not txt:
            continue
        x = sum(p[0] for p in bbox) / 4.0
        y = sum(p[1] for p in bbox) / 4.0
        items.append((x, y, txt, conf))
    items.sort(key=lambda z: z[0])

    best_text, best_score = None, -1.0
    n = len(items)
    anchor_cx, anchor_cy = anchor["cx"], anchor["cy"]
    for i in range(n):
        for j in range(i, min(n, i + 4)):
            toks = [items[k][2] for k in range(i, j + 1)]
            confs = [items[k][3] for k in range(i, j + 1)]
            cand = _only_az09(' '.join(toks))
            if _is_strict_signal_id(cand):
                avg_x = sum(items[k][0] for k in range(i, j + 1)) / (j - i + 1)
                avg_y = sum(items[k][1] for k in range(i, j + 1)) / (j - i + 1)
                dist = ((avg_x - anchor_cx) ** 2 + (avg_y - anchor_cy) ** 2) ** 0.5
                score = sum(confs) + 0.2 * (4 - (j - i)) - 0.1 * dist / anchor["w"]
                if score > best_score:
                    best_text, best_score = cand.replace(' ', ''), score
    return best_text, best_score

def _tighten_to_text(pil_img, pad=3):
    g = np.array(pil_img.convert('L'))
    bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    inv = 255 - bw
    cnts, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return pil_img
    x, y, w, h = cv2.boundingRect(np.vstack(cnts))
    x = max(0, x - pad)
    y = max(0, y - pad)
    return pil_img.crop((x, y, x + w + 2 * pad, y + h + 2 * pad))

def _extract_textline_roi(pil_img, h_hint: Optional[int] = None):
    g = np.array(pil_img.convert('L'))
    bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    inv = 255 - bw
    cnts, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return pil_img

    img_w, img_h = pil_img.size
    aspect_ratio = img_w / max(1, img_h)
    
    if aspect_ratio > 4.0:
        return _tighten_to_text(pil_img, pad=8)
    
    hs = np.array([cv2.boundingRect(c)[3] for c in cnts], dtype=np.int32)
    if h_hint is None:
        hs_clip = hs[(hs >= 8) & (hs <= 120)]
        if len(hs_clip) == 0:
            return _tighten_to_text(pil_img, pad=6)
        h0 = int(np.median(hs_clip))
        lo, hi = int(0.6 * h0), int(1.6 * h0)
    else:
        lo, hi = int(0.7 * h_hint), int(1.3 * h_hint)

    keep = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if lo <= h <= hi and w >= 6:
            keep.append((x, y, w, h))
    
    if not keep:
        return _tighten_to_text(pil_img, pad=6)

    xs = [x for x, _, w, _ in keep]
    ys = [y for _, y, _, _ in keep]
    x2 = [x + w for x, _, w, _ in keep]
    y2 = [y + h for _, y, _, h in keep]
    x1, y1, X2, Y2 = min(xs), min(ys), max(x2), max(y2)
    
    pad = 8
    x1 = max(0, x1 - pad)
    y1 = max(0, y1 - pad)
    
    return pil_img.crop((x1, y1, X2 + pad, Y2 + pad))

@paddle_ocr_locked
def ocr_signal_name(anchor: dict, bgr_color: np.ndarray, engine: str, overlay: Optional[np.ndarray] = None, debug_class: str = "signal") -> Optional[str]:
    """
    Signal OCR with Tesseract PRIMARY, EasyOCR fallback.
    Uses angle-aware preprocessing (cardinal vs angular).
    NOW WITH ADAPTIVE PADDING based on box size!
    """
    ang_normalized = float(anchor.get("angle", 0.0))
    ang_raw = float(anchor.get("angle_raw", ang_normalized))

    #  ADAPTIVE PADDING - Calculate based on box size
    w = float(anchor.get("obb_w", anchor["x2"] - anchor["x1"]))
    h = float(anchor.get("obb_h", anchor["y2"] - anchor["y1"]))
    box_min_side = min(w, h)
    
    # Target ~15% padding for all signal sizes
    sig_pad = max(10, min(16, int(box_min_side * 0.15)))
    
    # Optional diagnostic output
    if DEBUG_ANGLE_ROUTING:
        padding_ratio = (sig_pad / box_min_side) * 100
        print(f" {w:.0f}×{h:.0f}px (min:{box_min_side:.0f}) → pad={sig_pad} ({padding_ratio:.0f}%)", end="")
    #  END ADAPTIVE PADDING

    # ========================================================================
    # STEP 1: Get crop based on orientation
    # ========================================================================
    if _is_cardinal(ang_normalized):
        # Cardinal path (axis-aligned)
        try:
            pil_crop = rotated_crop_from_det(anchor, bgr_color, pad=sig_pad)  # ← Use adaptive pad
        except Exception:
            pil_crop = crop_pil(bgr_color, anchor["x1"], anchor["y1"], anchor["x2"], anchor["y2"], pad=sig_pad)  # ← Use adaptive pad
        
        pil_crop = _upscale_if_tiny(pil_crop, min_side=80, scale=3)
        pil_final = pil_crop  # No line removal for cardinal
        rotation_order = [0, 90, 180, 270]
    else:
        # Angular path (tilted)
        try:
            pil_crop = perspective_crop_from_det(anchor, bgr_color, pad=sig_pad)  # ← Use adaptive pad
        except Exception:
            pil_crop = rotated_crop_from_det(anchor, bgr_color, pad=sig_pad)  # ← Use adaptive pad
        
        pil_crop = _upscale_if_tiny(pil_crop, min_side=80, scale=3)
        pil_nolines = _remove_long_lines_oriented(pil_crop, ang_raw, frac_len=0.25, thickness=SIG_LINE_THICK)
        pil_final = pil_nolines if not SIG_USE_TIGHTEN else _extract_textline_roi(_tighten_to_text(pil_nolines), h_hint=SIGNAL_TEXT_HEIGHT_HINT)
        rotation_order = [0, 90, 180, 270]

    # Debug: Save original crop
    if debug_class:
        crop_bgr = cv2.cvtColor(np.array(pil_final), cv2.COLOR_RGB2BGR)
        _save_debug_crop(crop_bgr, debug_class, suffix="original")

    # ========================================================================
    # STEP 2: Prepare preprocessing variants
    # ========================================================================
    g0 = _pil_to_gray_np(pil_final)
    g1 = _enhance_contrast(g0)
    g2 = _binarize_for_text(g1)
    
    # Angular gets inverted variant too
    if _is_cardinal(ang_normalized):
        variants = [g2, g1, g0]  # Binary first (usually best for Tesseract)
    else:
        variants = [g2, _invert(g2), g1, g0]

    best_txt, best_sc = None, -1.0

    # ========================================================================
    # STEP 3: PRIMARY METHOD - PaddleOCR (if available)
    # ========================================================================
    paddle = get_paddleocr_instance()
    
    if paddle is not None:
        for var_arr in variants:
            pil_var = Image.fromarray(var_arr)
            
            for rot in rotation_order:
                test_img = pil_var.rotate(rot, expand=True, fillcolor=255) if rot != 0 else pil_var
                
                # Run PaddleOCR
                txt, conf = paddleocr_recognize(
                    test_img,
                    cls_name="signal",
                    whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789 "
                )
                
                # Process candidates
                candidates = [
                    txt,
                    _only_az09(txt),
                    re.sub(r'\s+', '', txt),
                    _normalize_signal_digits(txt),
                ]
                # Dedupe
                _seen = set()
                candidates = [c for c in candidates if c and not (c in _seen or _seen.add(c))]
                
                for cand in candidates:
                    if cand and _is_strict_signal_id(cand):
                        # PaddleOCR confidence is 0-1, adjust scoring
                        sc = score_name_token(cand, conf=conf, allow_numeric=False, cls_name="signal")
                        if sc > best_sc:
                            best_txt, best_sc = cand.replace(' ', ''), sc
                            
                            # Early exit on high confidence
                            if sc >= SIG_SCORE_MIN + 0.3:
                                if DEBUG_ANGLE_ROUTING:
                                    print(f" → '{best_txt}' (PaddleOCR)")
                                return best_txt  # DISABLED _post_fix_missing_zero_middle - causes AHR31→AHR301 bugs
        
        # If PaddleOCR found something good, return it
        if best_txt and best_sc >= SIG_SCORE_MIN - 0.2 and len(best_txt) >= 3:
            if DEBUG_ANGLE_ROUTING:
                print(f" → '{best_txt}' (PaddleOCR)")
            return best_txt  # DISABLED _post_fix_missing_zero_middle - causes AHR31→AHR301 bugs

    # ========================================================================
    # STEP 4: SECONDARY METHOD - Tesseract (if PaddleOCR failed)
    # ========================================================================
    try:
        import pytesseract
        
        for var_arr in variants:
            pil_var = Image.fromarray(var_arr)
            
            for rot in rotation_order:
                test_img = pil_var.rotate(rot, expand=True, fillcolor=255) if rot != 0 else pil_var
                
                # Try multiple PSM modes
                for psm in [7, 8, 13]:  # 7=line, 8=word, 13=raw line
                    cfg = f"--psm {psm} -l eng+deu -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789 --oem 1"
                    raw = pytesseract.image_to_string(test_img, config=cfg).strip()

                    candidates = [
                        raw,
                        _only_az09(raw),
                        re.sub(r'\s+', '', raw),
                        _normalize_signal_digits(raw),
                    ]
                    _seen = set()
                    candidates = [c for c in candidates if c and not (c in _seen or _seen.add(c))]

                    for cand in candidates:
                        if cand and _is_strict_signal_id(cand):
                            sc = score_name_token(cand, conf=0.85, allow_numeric=False, cls_name="signal")
                            if sc > best_sc:
                                best_txt, best_sc = cand.replace(' ', ''), sc
                                
                                # Early exit on high confidence
                                if sc >= SIG_SCORE_MIN + 0.5:
                                    if DEBUG_ANGLE_ROUTING:
                                        print(f" → '{best_txt}' (Tesseract)")
                                    return best_txt  # DISABLED _post_fix_missing_zero_middle - causes AHR31→AHR301 bugs
        
        # If Tesseract found something good, return it
        if best_txt and best_sc >= SIG_SCORE_MIN and len(best_txt) >= 3:
            if DEBUG_ANGLE_ROUTING:
                print(f" → '{best_txt}' (Tesseract)")
            return best_txt  # DISABLED _post_fix_missing_zero_middle - causes AHR31→AHR301 bugs
    
    except Exception:
        pass

    # ========================================================================
    # STEP 5: FALLBACK - EasyOCR (if both PaddleOCR and Tesseract failed)
    # ========================================================================
    if engine == "easyocr" and (best_txt is None or best_sc < SIG_SCORE_MIN):
        try:
            reader = get_easyocr_reader()
            all_items = []
            
            for var_arr in variants:
                items = easyocr_readtext(var_arr, detail=1, paragraph=False, 
                                        rotation_info=rotation_order,
                                        allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789') or []
                all_items.extend(items)

            # Try individual tokens
            for it in all_items:
                if len(it) < 3:
                    continue
                txt = _normalize_signal_digits(it[1] or "")
                conf = float(it[2] or 0.0)
                if _is_strict_signal_id(txt):
                    sc = score_name_token(txt, conf=conf, allow_numeric=False, cls_name="signal")
                    if sc > best_sc:
                        best_txt, best_sc = txt.replace(' ', ''), sc

            # Try merged tokens
            if best_txt is None and all_items:
                joined, jscore = _merge_adjacent_tokens_easyocr(all_items, anchor)
                if joined:
                    joined = _normalize_signal_digits(joined)
                    if _is_strict_signal_id(joined):
                        if jscore > best_sc:
                            best_txt, best_sc = joined, jscore
        
        except Exception:
            pass

    # ========================================================================
    # STEP 6: Return best result
    # ========================================================================
    if best_txt and best_sc >= SIG_SCORE_MIN and len(best_txt) >= 3:
        # Debug: Save final result
        if debug_class:
            crop_bgr = cv2.cvtColor(np.array(pil_final), cv2.COLOR_RGB2BGR)
            _save_debug_crop(crop_bgr, debug_class, best_txt, suffix="final")

        if DEBUG_ANGLE_ROUTING:
            print(f" → '{best_txt}' ")
        return best_txt  # DISABLED _post_fix_missing_zero_middle - causes AHR31→AHR301 bugs

    if DEBUG_ANGLE_ROUTING:
        print(f" → FAILED ")

    return None

# ============================================================================
# GENERIC NAME OCR + OTHER HELPERS
# ============================================================================
def _kill_frame_and_thicken_digits(bw: np.ndarray) -> np.ndarray:
    """
    Aggressively remove DOUBLE rectangular frames from GKS plates.
    """
    # Invert: morphology operations work on white foreground
    inv = 255 - bw
    
    # Remove vertical lines (frame left/right edges)
    k_vert = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 20))
    no_vert = cv2.morphologyEx(inv, cv2.MORPH_OPEN, k_vert)
    
    # Remove horizontal lines (frame top/bottom edges)
    k_horiz = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 1))
    no_horiz = cv2.morphologyEx(no_vert, cv2.MORPH_OPEN, k_horiz)
    
    # Remove noise and frame corners
    k_noise = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(no_horiz, cv2.MORPH_OPEN, k_noise, iterations=2)
    
    # Thicken digits to avoid broken strokes
    k_thick = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    thickened = cv2.dilate(cleaned, k_thick, iterations=1)
    
    # Invert back: white background, black text
    return 255 - thickened

_easy_reader = None
def get_easyocr_reader():
    global _easy_reader
    if _easy_reader is None:
        import easyocr
        _easy_reader = easyocr.Reader(['de', 'en'], gpu=False)
    return _easy_reader

import threading
_EASYOCR_LOCK = threading.Lock()

def easyocr_readtext(arr, *, detail=1, paragraph=False, rotation_info=None, allowlist=None, **kwargs):
    reader = get_easyocr_reader()
    default_params = {
        'text_threshold': 0.5,
        'low_text': 0.3,
        'link_threshold': 0.3,
        'canvas_size': 2560,
        'mag_ratio': 1.5,
        'slope_ths': 0.3,
        'ycenter_ths': 0.6,
        'height_ths': 0.6,
        'width_ths': 0.6,
        'add_margin': 0.15
    }
    params = {**default_params, **kwargs}
    with _EASYOCR_LOCK:
        return reader.readtext(arr, detail=detail, paragraph=paragraph,
                               rotation_info=rotation_info, allowlist=allowlist, **params) or []

def ocr_text(pil_img: Image.Image, engine: str) -> str:
    if engine == "easyocr":
        reader = get_easyocr_reader()
        arr = np.array(pil_img.convert("L"))
        result = easyocr_readtext(arr, detail=0, paragraph=False)
        if not result:
            return ""
        return sorted(result, key=lambda s: len(s), reverse=True)[0].strip()
    else:
        import pytesseract
        cfg = "--psm 7 -l deu+eng"
        return pytesseract.image_to_string(pil_img, config=cfg).strip()

def ocr_name_candidates(pil_img: Image.Image, engine: str) -> List[Tuple[str, float]]:
    win0 = _upscale_if_tiny(pil_img)
    win1 = _deskew_small(win0)
    g0 = _pil_to_gray_np(win1)
    g1 = _enhance_contrast(g0)
    g2 = _binarize_for_text(g1)
    variants = [Image.fromarray(g0), Image.fromarray(g1), Image.fromarray(g2)]

    cands: List[Tuple[str, float]] = []
    if engine == "easyocr":
        reader = get_easyocr_reader()
        for v in variants:
            arr = np.array(v)
            res = easyocr_readtext(arr, detail=1, paragraph=False) or []
            for item in res:
                if len(item) >= 2:
                    txt = (item[1] or "").strip()
                    conf = float(item[2]) if len(item) >= 3 and isinstance(item[2], (int, float)) else 0.5
                    if txt:
                        cands.append((txt, conf))
    else:
        import pytesseract
        cfg = "--psm 6 -l eng+deu -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789./-_"
        for v in variants:
            txt = pytesseract.image_to_string(v, config=cfg)
            for tok in (t.strip() for t in txt.split() if t.strip()):
                cands.append((tok, 0.50))

    if not cands:
        try:
            import pytesseract
            cfg = "--psm 6 -l eng+deu -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789./-_"
            for v in variants:
                txt = pytesseract.image_to_string(v, config=cfg)
                for tok in (t.strip() for t in txt.split() if t.strip()):
                    cands.append((tok, 0.50))
        except Exception:
            pass
    return cands

def score_name_token(tok: str, conf: float = 0.5, allow_numeric: bool = False, cls_name: Optional[str] = None) -> float:
    s = tok.strip()
    if not s or len(s) > 18:
        return -1
    if COORD_RE.match(s.replace(" ", "")):
        return -1
    if not allow_numeric and s.isdigit():
        return -1
    if all(ch in "-_/()." for ch in s):
        return -1

    has_alpha = any(c.isalpha() for c in s)
    has_digit = any(c.isdigit() for c in s)
    upper_ratio = (sum(c.isupper() for c in s) / max(1, sum(c.isalpha() for c in s)))

    score = 0.0
    if has_alpha:
        score += 1.0
    if has_digit:
        score += 0.7
    score += 0.4 * upper_ratio
    score += max(0, 6 - abs(len(s) - 5)) * 0.1
    score += 0.6 * conf

    if cls_name and cls_name in CLASS_ID_PATTERNS:
        import re as _re
        if _re.match(CLASS_ID_PATTERNS[cls_name], s, flags=_re.IGNORECASE):
            score += 1.2
    return score

def best_name_from_window(pil_img: Image.Image, engine: str, allow_numeric: bool = False,
                          cls_name: Optional[str] = None) -> Tuple[Optional[str], float]:
    cands = ocr_name_candidates(pil_img, engine)
    if not cands:
        return None, -1.0
    scored = [(score_name_token(t, c, allow_numeric, cls_name), t) for (t, c) in cands]
    scored.sort(reverse=True)
    best_score, best_tok = scored[0]
    return (best_tok if best_score > 0 else None), best_score

def ocr_best_angle(pil_img: Image.Image, engine: str, angles=(-20, -15, -10, -5, 0, 5, 10, 15, 20)) -> str:
    best = ""
    best_score = -1
    for ang in angles:
        rot = pil_img.rotate(ang, expand=True, fillcolor="white")
        txt = ocr_text(rot, engine)
        m = COORD_RE.match(txt.replace(" ", ""))
        score = 2 if (m and m.group(2)) else (1 if m else 0)
        if score > best_score or (score == best_score and len(txt) > len(best)):
            best, best_score = txt, score
    return best

def ocr_generic_name(anchor: dict, bgr_color: np.ndarray, engine: str, allow_numeric: bool,
                    cls_name: Optional[str], debug_class: str = "") -> Optional[str]:
    # Use cls_name as fallback for debug_class
    if not debug_class:
        debug_class = cls_name or "generic"

    # USE NORMALIZED ANGLE for routing
    ang_normalized = float(anchor.get("angle", 0.0))
    ang_raw = float(anchor.get("angle_raw", ang_normalized))

    if _is_cardinal(ang_normalized):  # Check normalized angle
        # Cardinal path - simple rotation
        try:
            pil_crop = rotated_crop_from_det(anchor, bgr_color, pad=8)
        except Exception:
            pil_crop = crop_pil(bgr_color, anchor["x1"], anchor["y1"], anchor["x2"], anchor["y2"], pad=8)
    else:
        # Angular path - perspective warp
        try:
            pil_crop = perspective_crop_from_det(anchor, bgr_color, pad=8)
        except Exception:
            pil_crop = rotated_crop_from_det(anchor, bgr_color, pad=8)

    pil_crop = _upscale_if_tiny(pil_crop, min_side=80, scale=3)

    # Debug: Save original crop
    if debug_class:
        crop_bgr = cv2.cvtColor(np.array(pil_crop), cv2.COLOR_RGB2BGR)
        _save_debug_crop(crop_bgr, debug_class, suffix="original")

    if _is_cardinal(ang_normalized):
        pil_final = pil_crop
        rotations = [0, 90, 180, 270]  # Simple order - text already aligned after crop fix
    else:
        pil_final = _remove_long_lines_oriented(pil_crop, ang_raw, frac_len=0.25, thickness=3)
        rotations = [0, 90, 180, 270]

    g0 = _pil_to_gray_np(pil_final)
    g1 = _enhance_contrast(g0)
    g2 = _binarize_for_text(g1)

    variants_np = [g0, g1, g2]
    if not _is_cardinal(ang_normalized):
        variants_np.append(_invert(g2))

    best_name, best_score = None, -1.0

    if engine == "easyocr":
        reader = get_easyocr_reader()
        if allow_numeric:
            allowlist = 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789./-_'
        else:
            allowlist = 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ./-_'

        all_items = []
        for v in variants_np:
            items = easyocr_readtext(
                v, detail=1, paragraph=False, 
                rotation_info=rotations,  # ← Use smart ordering
                allowlist=allowlist
            ) or []
            all_items.extend(items)

        for it in all_items:
            if len(it) < 3:
                continue
            tok = (it[1] or "").strip()
            conf = float(it[2] or 0.0)
            sc = score_name_token(tok, conf=conf, allow_numeric=allow_numeric, cls_name=cls_name)
            if sc > best_score:
                best_name, best_score = tok, sc

    else:
        import pytesseract
        wl = 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789./-_' if allow_numeric else 'ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ./-_'
        cfg = f"--psm 6 -l eng+deu -c tessedit_char_whitelist={wl}"
        
        #  FIX: Test rotations in smart order for Tesseract too
        for v in variants_np:
            for rot_deg in rotations:  # Use smart-ordered rotations
                test_img = Image.fromarray(v).rotate(rot_deg, expand=True, fillcolor=255) if rot_deg != 0 else Image.fromarray(v)
                txt = pytesseract.image_to_string(test_img, config=cfg)
                for tok in (t.strip() for t in txt.split() if t.strip()):
                    sc = score_name_token(tok, conf=0.5, allow_numeric=allow_numeric, cls_name=cls_name)
                    if sc > best_score:
                        best_name, best_score = tok, sc

    # Debug: Save final result
    if debug_class and best_name:
        crop_bgr = cv2.cvtColor(np.array(pil_final), cv2.COLOR_RGB2BGR)
        _save_debug_crop(crop_bgr, debug_class, best_name, suffix="final")

    return best_name if (best_name and best_score > 0) else None

@paddle_ocr_locked
def ocr_numeric_cardinal_box(anchor: dict, bgr_color: np.ndarray, debug_class: str = "gks") -> Optional[str]:
    """
    Robust numeric OCR for axis-aligned GKS plates.
    PaddleOCR with LIGHTER preprocessing - grayscale+CLAHE works best!
    """
    cls_name = anchor.get("name", "gks_festkodiert")
    if not debug_class:
        debug_class = cls_name
    
    # Get class-specific parameters
    pad_dict = CARDINAL_PARAMS["detection_padding"]
    pad = pad_dict.get(cls_name, 8)
    
    if DEBUG_ANGLE_ROUTING:
        w = float(anchor.get("obb_w", anchor["x2"] - anchor["x1"]))
        h = float(anchor.get("obb_h", anchor["y2"] - anchor["y1"]))
        ang_raw = float(anchor.get("angle_raw", 0.0))
        ang_norm = float(anchor.get("angle", 0.0))
        print(f"\n GKS CARDINAL BOX: {w:.0f}×{h:.0f}px | angles: raw={ang_raw:.1f}° norm={ang_norm:.1f}°")
        print(f"→ Class params: pad={pad}")
    
    # 1) Crop
    try:
        base = rotated_crop_from_det(anchor, bgr_color, pad=pad)
    except Exception:
        base = crop_pil(bgr_color, anchor["x1"], anchor["y1"], anchor["x2"], anchor["y2"], pad=pad)

    # 2) Upscale
    min_side = min(base.width, base.height)
    scale = 8 if min_side < 60 else (6 if min_side < 80 else 4)
    base = base.resize((base.width * scale, base.height * scale), Image.LANCZOS)

    if DEBUG_ANGLE_ROUTING:
        print(f"→ Upscaled to: {base.width}×{base.height}px (scale={scale}x)")

    # Debug: Save original crop
    if debug_class:
        crop_bgr = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2BGR)
        _save_debug_crop(crop_bgr, debug_class, suffix="original")

    best, best_sc = None, -1.0

    paddle = get_paddleocr_instance()
    
    if paddle is None:
        if DEBUG_ANGLE_ROUTING:
            print(f"PaddleOCR not available")
        return None
    
    if DEBUG_ANGLE_ROUTING:
        print(f"→ Running PaddleOCR...")
    
    try:
        # LIGHT preprocessing - grayscale+CLAHE only (works best!)
        g = _pil_to_gray_np(base)
        g_enhanced = _enhance_contrast(g)
        img = Image.fromarray(g_enhanced)
        
        for rot in (0, 180):
            test_img = img.rotate(rot, expand=True, fillcolor=255) if rot else img
            test_arr = np.array(test_img)
            
            # Convert to BGR
            if len(test_arr.shape) == 2:
                test_arr = cv2.cvtColor(test_arr, cv2.COLOR_GRAY2BGR)
            
            #  CRITICAL: Use thread lock for PaddleOCR
            with _PADDLE_OCR_LOCK:
                results = paddle.ocr(test_arr, cls=False)
            
            if DEBUG_ANGLE_ROUTING:
                n_det = len(results[0]) if results and results[0] else 0
                print(f"[grayscale+CLAHE rot={rot:3d}°] {n_det} detections")
            
            if results and results[0]:
                for line in results[0]:
                    if line is None:
                        continue
                    bbox, (text, conf) = line
                    
                    # Clean: digits only
                    t = ''.join(c for c in text if c.isdigit())
                    
                    if DEBUG_ANGLE_ROUTING and text:
                        print(f"raw='{text}' → clean='{t}' (conf={conf:.2f})")
                    
                    if t and len(t) >= 3:
                        sc = score_name_token(t, conf=conf, allow_numeric=True, cls_name=cls_name)
                        if DEBUG_ANGLE_ROUTING:
                            print(f"score={sc:.2f}")
                        
                        if sc > best_sc:
                            best_sc, best = sc, t
                            if sc > 1.6 and conf > 0.60:
                                if DEBUG_ANGLE_ROUTING:
                                    print(f"EARLY EXIT: '{best}'")
                                return best
                                    
    except Exception as e:
        if DEBUG_ANGLE_ROUTING:
            print(f"EXCEPTION: {e}")
            import traceback
            traceback.print_exc()

    if DEBUG_ANGLE_ROUTING:
        if best:
            print(f"RESULT: '{best}' (score:{best_sc:.2f})")
        else:
            print(f"FAILED")

    # Debug: Save final result
    if debug_class and best:
        crop_bgr = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2BGR)
        _save_debug_crop(crop_bgr, debug_class, best, suffix="final")

    return best


@paddle_ocr_locked
def ocr_numeric_tilted_box(anchor: dict, bgr_color: np.ndarray, debug_class: str = "gks") -> Optional[str]:
    """
    Robust numeric OCR for tilted GKS plates.
    Tests ALL rotations, picks best 4-digit result.
    """
    ang_norm = float(anchor.get("angle", 0.0))
    ang_raw = float(anchor.get("angle_raw", ang_norm))
    cls_name = anchor.get("name", "gks_festkodiert")
    if not debug_class:
        debug_class = cls_name
    
    # Get box size
    w = float(anchor.get("obb_w", anchor["x2"] - anchor["x1"]))
    h = float(anchor.get("obb_h", anchor["y2"] - anchor["y1"]))
    box_min_side = min(w, h)

    # Get class-specific angular padding from config, with adaptive scaling
    pad_dict = ANGULAR_PARAMS["detection_padding"]
    base_pad = pad_dict.get(cls_name, 8)

    # Apply adaptive scaling based on box size (generous for angular text)
    if box_min_side < 70:
        pad = int(base_pad * 3.0)  # Very generous for small boxes
    elif box_min_side < 100:
        pad = int(base_pad * 2.5)
    else:
        pad = int(base_pad * 2.0)
    
    if DEBUG_ANGLE_ROUTING:
        print(f"\n GKS ANGULAR BOX: {w:.0f}×{h:.0f}px | angles: raw={ang_raw:.1f}° norm={ang_norm:.1f}°")
        print(f"→ Using pad={pad}px ({pad/box_min_side*100:.0f}% of min side)")

    # 1) Crop with generous padding
    try:
        base = perspective_crop_from_det(anchor, bgr_color, pad=pad)
    except Exception:
        base = rotated_crop_from_det(anchor, bgr_color, pad=pad)

    # 2) Aggressive upscaling
    min_side = min(base.width, base.height)
    scale = 7 if min_side < 60 else (5 if min_side < 90 else 4)
    base = base.resize((base.width * scale, base.height * scale), Image.LANCZOS)

    if DEBUG_ANGLE_ROUTING:
        print(f"→ Upscaled to: {base.width}×{base.height}px (scale={scale}x)")

    # Debug: Save original crop
    if debug_class:
        crop_bgr = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2BGR)
        _save_debug_crop(crop_bgr, debug_class, suffix="original")

    best_txt = None
    best_sc = -1.0
    best_conf = 0.0
    best_rot = 0
    
    #  Track ALL 4-digit results
    four_digit_results = []
    
    test_rotations = [0, 90, 180, 270]

    paddle = get_paddleocr_instance()
    
    if paddle is None:
        if DEBUG_ANGLE_ROUTING:
            print(f"PaddleOCR not available")
        return None
    
    if DEBUG_ANGLE_ROUTING:
        print(f"→ Running PaddleOCR (testing ALL rotations)...")
    
    try:
        # LIGHT preprocessing
        g = _pil_to_gray_np(base)
        g_enhanced = _enhance_contrast(g)
        img = Image.fromarray(g_enhanced)
        
        #  TEST ALL ROTATIONS - NO EARLY EXIT
        for rot_deg in test_rotations:
            test_img = img.rotate(rot_deg, expand=True, fillcolor=255) if rot_deg != 0 else img
            test_arr = np.array(test_img)
            
            # Convert to BGR
            if len(test_arr.shape) == 2:
                test_arr = cv2.cvtColor(test_arr, cv2.COLOR_GRAY2BGR)
            
            # Run PaddleOCR
            results = paddle.ocr(test_arr, cls=False)
            
            if DEBUG_ANGLE_ROUTING:
                n_det = len(results[0]) if results and results[0] else 0
                print(f"[rot={rot_deg:3d}°] {n_det} detections")
            
            if results and results[0]:
                for line in results[0]:
                    if line is None:
                        continue
                    bbox, (text, conf) = line
                    
                    # Clean: digits only
                    t = ''.join(c for c in text if c.isdigit())
                    
                    if DEBUG_ANGLE_ROUTING and text:
                        print(f"raw='{text}' → clean='{t}' (conf={conf:.2f})")
                    
                    if t and len(t) >= 3:
                        sc = score_name_token(t, conf=conf, allow_numeric=True, cls_name=cls_name)
                        
                        if DEBUG_ANGLE_ROUTING:
                            print(f"score={sc:.2f}, len={len(t)}")
                        
                        #  TRACK BEST OVERALL
                        if sc > best_sc:
                            best_sc = sc
                            best_txt = t
                            best_conf = conf
                            best_rot = rot_deg
                        
                        #  SEPARATELY TRACK 4-DIGIT RESULTS
                        if len(t) == 4:
                            four_digit_results.append({
                                'text': t,
                                'score': sc,
                                'conf': conf,
                                'rot': rot_deg
                            })
                            if DEBUG_ANGLE_ROUTING:
                                print(f" 4-digit candidate: '{t}'")
                                    
    except Exception as e:
        if DEBUG_ANGLE_ROUTING:
            print(f"EXCEPTION: {e}")
            import traceback
            traceback.print_exc()

    #  PREFER 4-DIGIT RESULTS (sort by score)
    if four_digit_results:
        # Sort by score descending
        four_digit_results.sort(key=lambda x: x['score'], reverse=True)
        best_4d = four_digit_results[0]
        
        if DEBUG_ANGLE_ROUTING:
            print(f"\n   Found {len(four_digit_results)} 4-digit results:")
            for i, res in enumerate(four_digit_results):
                marker = "" if i == 0 else "  "
                print(f"{marker} '{res['text']}' score={res['score']:.2f} conf={res['conf']:.2f} rot={res['rot']}°")
            print(f"BEST 4-DIGIT: '{best_4d['text']}' (score:{best_4d['score']:.2f}, rot:{best_4d['rot']}°)")

        # Debug: Save final result
        if debug_class:
            crop_bgr = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2BGR)
            _save_debug_crop(crop_bgr, debug_class, best_4d['text'], suffix="final")

        return best_4d['text']

    #  FALLBACK: Accept 3-digit if no 4-digit found and score is good
    if best_txt and len(best_txt) == 3 and best_sc > 1.5:
        # Debug: Save final result
        if debug_class:
            crop_bgr = cv2.cvtColor(np.array(base), cv2.COLOR_RGB2BGR)
            _save_debug_crop(crop_bgr, debug_class, best_txt, suffix="final")

        if DEBUG_ANGLE_ROUTING:
            print(f"ACCEPTING 3-DIGIT: '{best_txt}' (score:{best_sc:.2f}, conf:{best_conf:.2f}, rot:{best_rot}°)")
        return best_txt
    
    if DEBUG_ANGLE_ROUTING:
        if best_txt:
            print(f"REJECTED: '{best_txt}' (len={len(best_txt)}, score:{best_sc:.2f}) - expected 4 digits")
        else:
            print(f"FAILED: No valid result")
    
    return None



def ocr_anchor_name(anchor: dict, bgr_color: np.ndarray, engine: str, config=None) -> Optional[str]:
    """
    OCR for anchor boxes with correct dual-angle routing.

    If config.ocr.use_simple_ocr=True, uses simple OCR for supported classes.
    For symbol-only classes (requires_ocr=false), skips direct OCR and uses name window search.
    """
    cls = anchor["name"]

    # Simple OCR mode for high-DPI scans (Antwerp text_id and coordinate classes)
    if config is not None and hasattr(config, 'ocr') and config.ocr.use_simple_ocr:
        # Use simple OCR for text_id and other generic classes
        if cls not in {"signal", "weichen_block", "gks_gesteuert", "gks_festkodiert"}:
            return ocr_simple_text(anchor, bgr_color, config, debug_class=cls)

    if cls == "signal":
        return ocr_signal_name(anchor, bgr_color, engine, debug_class=cls)

    if cls == "weichen_block":
        return ocr_weichen_block(anchor, bgr_color, debug_class=cls)


    # ========================================================================
    # GKS NUMERIC PLATES: Use specialized functions with normalized angle routing
    # ========================================================================
    if cls in {"gks_gesteuert", "gks_festkodiert"}:
        ang_norm = float(anchor.get("angle", 0.0))  #  Use NORMALIZED angle
        ang_raw = float(anchor.get("angle_raw", ang_norm))
        
        if DEBUG_ANGLE_ROUTING:
            print(f"\n{'='*70}")
            print(f"GKS OCR: {cls}")
            print(f"Angles: raw={ang_raw:.1f}° norm={ang_norm:.1f}°")
            print(f"Box: {anchor['x2']-anchor['x1']}×{anchor['y2']-anchor['y1']}px")
        
        # Route based on NORMALIZED angle
        if _is_cardinal(ang_norm):  #  Check normalized angle
            if DEBUG_ANGLE_ROUTING:
                print(f"→ CARDINAL path (|norm|≤15°)")

            val = ocr_numeric_cardinal_box(anchor, bgr_color, debug_class=cls)  #  Call cardinal function

            if val:
                if DEBUG_ANGLE_ROUTING:
                    print(f"SUCCESS: '{val}'")
                return val
            else:
                if DEBUG_ANGLE_ROUTING:
                    print(f"CARDINAL FAILED")
        else:
            if DEBUG_ANGLE_ROUTING:
                print(f"→ ANGULAR path (|norm|={abs(ang_norm):.1f}° > 15°)")

            val = ocr_numeric_tilted_box(anchor, bgr_color, debug_class=cls)  #  Call angular function
            
            if val:
                if DEBUG_ANGLE_ROUTING:
                    print(f"SUCCESS: '{val}'")
                return val
            else:
                if DEBUG_ANGLE_ROUTING:
                    print(f"ANGULAR FAILED")
        
        if DEBUG_ANGLE_ROUTING:
            print(f"{'='*70}\n")
        

    # ========================================================================
    # FALLBACK: Generic OCR for all other classes
    # ========================================================================
    allow_numeric = cls in NUMERIC_OK

    try:
        inner_crop = rotated_crop_from_det(anchor, bgr_color, pad=6)
        name_in = ocr_text(inner_crop, engine).strip()
        if name_in:
            sc = score_name_token(name_in, 0.6, allow_numeric=allow_numeric, cls_name=cls)
            if sc > 0.9:
                return name_in
    except Exception:
        pass

    name = ocr_generic_name(anchor, bgr_color, engine, allow_numeric=allow_numeric, cls_name=cls, debug_class=cls)
    if name:
        return name

    rule = LINK_RULES.get(cls, {}).get("mode", "either")
    windows = name_windows_for(anchor, bgr_color.shape, rule, config)
    for (x1, y1, x2, y2) in windows:
        crop = Image.fromarray(cv2.cvtColor(bgr_color[y1:y2, x1:x2], cv2.COLOR_BGR2RGB))
        best_name, best_score = None, -1.0
        for ang in (-10, 0, 10):
            rot = crop.rotate(ang, expand=True, fillcolor="white")
            name2, score = best_name_from_window(rot, engine, allow_numeric=allow_numeric, cls_name=cls)
            if score > best_score:
                best_name, best_score = name2, score
        if best_name:
            return best_name

    return None


def manual_angular_ocr(crop_bgr: np.ndarray, cls_name: str) -> tuple:
    """
    Process angular/tilted text for manual OCR.
    User has already aligned the rectangle, so NO rotation needed.
    Uses the same preprocessing pipeline as automated angular OCR.
    
    Args:
        crop_bgr: BGR image crop (numpy array) - already extracted with padding
        cls_name: Class name for context
    
    Returns:
        (text, confidence)
    """
    # Convert to PIL
    crop_pil = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
    
    # 1. Upscale if tiny (same as automated OCR)
    min_side = min(crop_pil.width, crop_pil.height)
    if min_side < 80:
        scale = 3
        crop_pil = crop_pil.resize(
            (crop_pil.width * scale, crop_pil.height * scale), 
            Image.LANCZOS
        )
    
    # 2. Apply preprocessing variants (same as automated OCR)
    g0 = _pil_to_gray_np(crop_pil)
    g1 = _enhance_contrast(g0)
    g2 = _binarize_for_text(g1)
    
    # Angular gets inverted variant too
    variants = [g2, _invert(g2), g1, g0]
    
    best_txt = None
    best_conf = 0.0
    
    # 3. Try PaddleOCR on each variant (NO ROTATION - already aligned)
    paddle = get_paddleocr_instance()
    
    if paddle is not None:
        for var_arr in variants:
            var_pil = Image.fromarray(var_arr)
            
            # Run OCR without whitelist - let PaddleOCR recognize freely
            txt, conf = paddleocr_recognize(
                var_pil,
                cls_name=cls_name,
                whitelist=None  # No restrictions
            )
            
            if conf > best_conf and txt:
                best_txt = txt
                best_conf = conf
                
                # Early exit on high confidence
                if conf > 0.9:
                    break
        
        if best_txt:
            # Apply class-specific post-processing
            if cls_name == "signal":
                best_txt = _normalize_signal_digits(best_txt)
                best_txt = best_txt.replace(' ', '')
            elif cls_name in ["gks_gesteuert", "gks_festkodiert"]:
                # For numeric classes, extract only digits
                best_txt = ''.join(c for c in best_txt if c.isdigit())
            
            return best_txt, best_conf
    
    # 4. Fallback: Try Tesseract if PaddleOCR failed
    try:
        import pytesseract
        
        for var_arr in variants:
            var_pil = Image.fromarray(var_arr)
            
            # Even Tesseract can work without whitelist, but we'll keep it for numeric classes
            if cls_name in ["gks_gesteuert", "gks_festkodiert"]:
                cfg = "--psm 7 -c tessedit_char_whitelist=0123456789 --oem 1"
            else:
                cfg = "--psm 7 -l eng+deu --oem 1"  # No whitelist
            
            raw = pytesseract.image_to_string(var_pil, config=cfg).strip()
            
            if raw and len(raw) > len(best_txt or ""):
                best_txt = raw
                best_conf = 0.85  # Tesseract doesn't provide confidence
                
                # Apply class-specific cleaning
                if cls_name == "signal":
                    best_txt = _normalize_signal_digits(best_txt)
                    best_txt = best_txt.replace(' ', '')
                elif cls_name in ["gks_gesteuert", "gks_festkodiert"]:
                    best_txt = ''.join(c for c in best_txt if c.isdigit())
    
    except Exception:
        pass
    
    return best_txt or "", best_conf


# ============================================================================
# CUSTOM SYMBOL OCR - For user-defined symbols with text
# ============================================================================

@paddle_ocr_locked
def ocr_custom_symbol_text(
    anchor: dict,
    bgr_color: np.ndarray,
    text_position,  # str or List[str] - supports multiple positions
    engine: str,
    text_region_offset: dict = None,
    search_distance: int = 300,  # Generous distance to avoid cutting off long text
    search_width: int = 80,
    debug_class: str = "custom_symbol",
):
    """
    OCR text near a custom symbol based on configured text position.

    The user specifies where text appears relative to the symbol:
    - "left": Search to the left of the symbol
    - "right": Search to the right of the symbol
    - "above": Search above the symbol
    - "below": Search below the symbol
    - "inside": Search inside the symbol bounding box (for speed signs, etc.)

    Supports a list of positions - will try each until text is found.

    Or provides a precise text_region_offset with dx, dy, width, height.

    Args:
        anchor: Detection dict with x1,y1,x2,y2 and optionally angle
        bgr_color: Full BGR image
        text_position: Direction to search ("left", "right", "above", "below")
        engine: OCR engine ("paddleocr" or "tesseract")
        text_region_offset: Precise offset {"dx", "dy", "width", "height"} from symbol center
        search_distance: How far to search in the specified direction (pixels)
        search_width: Width of the search region perpendicular to direction

    Returns:
        tuple: (text, bbox, position_used, confidence) where:
            - text: Recognized text or empty string
            - bbox: tuple (x1, y1, x2, y2) of OCR region, or None if no text found
            - position_used: Which position was successful, or None if no text found
            - confidence: OCR confidence score (0.0 to 1.0)
    """
    import math

    # Handle list of positions - try each until text is found
    positions_to_try = text_position if isinstance(text_position, list) else [text_position]

    # Get symbol bounding box
    x1, y1 = int(anchor.get("x1", 0)), int(anchor.get("y1", 0))
    x2, y2 = int(anchor.get("x2", 0)), int(anchor.get("y2", 0))

    # Symbol center and dimensions
    sym_cx = (x1 + x2) / 2
    sym_cy = (y1 + y2) / 2
    sym_w = x2 - x1
    sym_h = y2 - y1

    # Get symbol rotation angle (if any)
    sym_angle = float(anchor.get("angle", 0.0))

    # Image dimensions
    img_h, img_w = bgr_color.shape[:2]

    if DEBUG_CUSTOM_SYMBOLS:
        print(f"\n CUSTOM SYMBOL OCR: text_position='{text_position}', angle={sym_angle:.1f}°")
        print(f"Symbol bbox: ({x1},{y1})-({x2},{y2}) size={sym_w}x{sym_h}")
        if text_region_offset:
            print(f"Using precise text_region_offset: {text_region_offset}")

    # Try each position until we find text
    for current_position in positions_to_try:
        result = _ocr_custom_symbol_single_position(
            anchor, bgr_color, current_position, engine,
            text_region_offset, search_distance, search_width,
            x1, y1, x2, y2, sym_cx, sym_cy, sym_w, sym_h, sym_angle, img_h, img_w
        )
        # result is now (text, bbox, position, confidence)
        text, bbox, position, conf = result
        if text:
            return text, bbox, position, conf

    return "", None, None, 0.0


def _ocr_custom_symbol_single_position(
    anchor: dict,
    bgr_color: np.ndarray,
    text_position: str,
    engine: str,
    text_region_offset: dict,
    search_distance: int,
    search_width: int,
    x1: int, y1: int, x2: int, y2: int,
    sym_cx: float, sym_cy: float, sym_w: int, sym_h: int,
    sym_angle: float, img_h: int, img_w: int
):
    """
    OCR for a single text position. Called by ocr_custom_symbol_text.

    Returns:
        tuple: (text, bbox, position, confidence) where:
            - text: Recognized text or empty string
            - bbox: tuple (x1, y1, x2, y2) of OCR region, or None if no text found
            - position: The text_position parameter (for tracking which position worked)
            - confidence: OCR confidence score (0.0 to 1.0)
    """
    import math

    if DEBUG_CUSTOM_SYMBOLS:
        print(f"Trying position: '{text_position}'")

    # PRIORITY: Use precise text_region_offset if provided
    if text_region_offset and isinstance(text_region_offset, dict):
        dx = text_region_offset.get("dx", 0)
        dy = text_region_offset.get("dy", 0)
        tw = text_region_offset.get("width", 100)
        th = text_region_offset.get("height", 50)

        # VALIDATION: Check for invalid dimensions
        if tw <= 0 or th <= 0:
            if DEBUG_CUSTOM_SYMBOLS:
                print(f"Invalid text_region_offset: width={tw}, height={th}. Falling back to position-based search.")
            text_region_offset = None  # Force fallback to position-based search
        else:
            # SCALE COMPENSATION: Adjust offset based on detected symbol size vs. reference size
            # This handles cases where symbol is detected at different sizes (different DPI, etc.)
            ref_sym_w = text_region_offset.get("ref_sym_width", 0)
            ref_sym_h = text_region_offset.get("ref_sym_height", 0)

            if ref_sym_w > 0 and ref_sym_h > 0 and sym_w > 0 and sym_h > 0:
                # Calculate scale factor (use average of width and height ratios)
                scale_x = sym_w / ref_sym_w
                scale_y = sym_h / ref_sym_h
                scale_factor = (scale_x + scale_y) / 2

                # Apply scaling to offset and text region dimensions
                dx = dx * scale_factor
                dy = dy * scale_factor
                tw = tw * scale_factor
                th = th * scale_factor

                if DEBUG_CUSTOM_SYMBOLS:
                    print(f"Scale compensation: ref_size=({ref_sym_w}x{ref_sym_h}), "
                          f"detected_size=({sym_w}x{sym_h}), scale={scale_factor:.2f}")

            # IMPORTANT: Rotate the offset based on symbol rotation
            # The offset was defined relative to the 0° template, so we need to
            # transform it for rotated symbols
            from utils.rotation_utils import transform_offset_forward

            dx_rot, dy_rot, tw_rot, th_rot = transform_offset_forward(
                dx, dy, tw, th, sym_angle
            )

            if DEBUG_CUSTOM_SYMBOLS:
                print(f"Manual offset rotation: ({dx},{dy}) @ {sym_angle:.1f}° → ({dx_rot:.1f},{dy_rot:.1f})")

            # Calculate text region center from symbol center + rotated offset
            txt_cx = sym_cx + dx_rot
            txt_cy = sym_cy + dy_rot

            # Calculate ideal crop bounds (before clamping)
            ideal_x1 = int(txt_cx - tw_rot / 2)
            ideal_y1 = int(txt_cy - th_rot / 2)
            ideal_x2 = int(txt_cx + tw_rot / 2)
            ideal_y2 = int(txt_cy + th_rot / 2)

            # Calculate clamped crop bounds
            crop_x1 = max(0, ideal_x1)
            crop_y1 = max(0, ideal_y1)
            crop_x2 = min(img_w, ideal_x2)
            crop_y2 = min(img_h, ideal_y2)

            # VALIDATION: Check if significant portion of text region is outside image
            ideal_area = (ideal_x2 - ideal_x1) * (ideal_y2 - ideal_y1)
            actual_area = (crop_x2 - crop_x1) * (crop_y2 - crop_y1)

            if ideal_area > 0:
                coverage = actual_area / ideal_area
                if coverage < 0.5:
                    if DEBUG_CUSTOM_SYMBOLS:
                        print(f"⚠ WARNING: Text region mostly outside image! "
                              f"Coverage: {coverage*100:.0f}%, ideal=({ideal_x1},{ideal_y1})-({ideal_x2},{ideal_y2})")
                    # Fall back to position-based search
                    text_region_offset = None
                elif coverage < 0.8:
                    if DEBUG_CUSTOM_SYMBOLS:
                        print(f"⚠ Text region partially clipped. Coverage: {coverage*100:.0f}%")

            # VALIDATION: Check if region is too small for OCR
            if text_region_offset and (crop_x2 - crop_x1 < 15 or crop_y2 - crop_y1 < 10):
                if DEBUG_CUSTOM_SYMBOLS:
                    print(f"⚠ WARNING: Text region too small for OCR: {crop_x2-crop_x1}x{crop_y2-crop_y1}px. Falling back.")
                text_region_offset = None

            if DEBUG_CUSTOM_SYMBOLS and text_region_offset:
                print(f"Precise region: ({crop_x1},{crop_y1})-({crop_x2},{crop_y2})")

    # FALLBACK: Use direction-based search with LARGER area for auto-detection
    # PaddleOCR will find text boxes automatically, we just need to give it enough area
    if not text_region_offset or text_region_offset is None:
        # IMPORTANT: Adjust text_position based on symbol rotation
        # When symbol is rotated, "left" relative to symbol changes in image coordinates
        # Rotation mapping (counterclockwise):
        #   0°:   left=left, right=right, above=above, below=below
        #   90°:  left=below, right=above, above=left, below=right
        #   180°: left=right, right=left, above=below, below=above
        #   270°: left=above, right=below, above=right, below=left

        effective_position = text_position

        # Normalize angle to 0-360
        norm_angle = sym_angle % 360

        # Map direction based on rotation - TRACK-RELATIVE positioning for Gleisplans
        # Text stays on same SIDE of track, only LEFT/RIGHT changes with signal direction
        # 0°: below-left → 90°: above-left → 180°: below-right → 270°: below-left
        # NOTE: Use narrow ranges to match rotation_utils.py behavior (quadrant angles only)
        # For non-quadrant angles (45°, 135°, etc.), no direction change (fallback uses auto-detection)
        if 85 < norm_angle < 95:  # ~90° rotation - Y flips only (below↔above)
            direction_map = {"above": "below", "below": "above"}  # left/right unchanged
            effective_position = direction_map.get(text_position, text_position)
        elif 175 < norm_angle < 185:  # ~180° rotation - X flips only (left↔right)
            direction_map = {"left": "right", "right": "left"}  # above/below unchanged
            effective_position = direction_map.get(text_position, text_position)
        elif 265 < norm_angle < 275:  # ~270° rotation - no flip
            pass  # All directions stay same (just dimension swap in bbox)
        # else: 0° or 315-360° or non-quadrant angles - no change needed

        if DEBUG_CUSTOM_SYMBOLS:
            print(f"Rotation adjustment: {text_position} @ {sym_angle:.1f}° → {effective_position}")

        # Now use effective_position for search direction
        if effective_position == "left":
            # Search region to the LEFT of symbol (generous area)
            crop_x2 = x1 + 20  # Extend slightly INTO symbol to catch adjacent text
            crop_x1 = max(0, x1 - search_distance)  # Start further left
            # Height: Match symbol's exact vertical extent (no extension above/below)
            crop_y1 = max(0, y1)
            crop_y2 = min(img_h, y2)

        elif effective_position == "right":
            # Search region to the RIGHT of symbol
            crop_x1 = x2 - 20  # Extend slightly INTO symbol
            crop_x2 = min(img_w, x2 + search_distance)
            # Height: Match symbol's exact vertical extent (no extension above/below)
            crop_y1 = max(0, y1)
            crop_y2 = min(img_h, y2)

        elif effective_position == "above":
            # Search region ABOVE symbol
            # Text is aligned HORIZONTALLY (parallel to symbol), so use 300px horizontal range
            crop_y2 = y1 + 20  # Extend slightly INTO symbol
            crop_y1 = max(0, y1 - search_distance)
            # 300px horizontal: 150px on each side of symbol center
            crop_x1 = max(0, int(sym_cx - search_distance / 2))
            crop_x2 = min(img_w, int(sym_cx + search_distance / 2))

        elif effective_position == "below":
            # Search region BELOW symbol
            # Text is aligned HORIZONTALLY (parallel to symbol), so use 300px horizontal range
            crop_y1 = y2 - 20  # Extend slightly INTO symbol
            crop_y2 = min(img_h, y2 + search_distance)
            # 300px horizontal: 150px on each side of symbol center
            crop_x1 = max(0, int(sym_cx - search_distance / 2))
            crop_x2 = min(img_w, int(sym_cx + search_distance / 2))

        elif effective_position == "inside":
            # Search INSIDE the symbol bounding box (for speed signs with numbers inside)
            # Use tight crop - just the symbol's interior with small padding
            padding = 5
            crop_x1 = max(0, x1 + padding)
            crop_y1 = max(0, y1 + padding)
            crop_x2 = min(img_w, x2 - padding)
            crop_y2 = min(img_h, y2 - padding)

            if DEBUG_CUSTOM_SYMBOLS:
                print(f"INSIDE mode: tight crop ({crop_x1},{crop_y1})-({crop_x2},{crop_y2})")

        else:
            # Default to left with symbol's exact vertical extent
            crop_x2 = x1 + 20
            crop_x1 = max(0, x1 - search_distance)
            crop_y1 = max(0, y1)
            crop_y2 = min(img_h, y2)

    if DEBUG_CUSTOM_SYMBOLS:
        print(f"Search region: ({crop_x1},{crop_y1})-({crop_x2},{crop_y2})")

    # Validate crop
    if crop_x2 <= crop_x1 or crop_y2 <= crop_y1:
        if DEBUG_CUSTOM_SYMBOLS:
            print(f"Invalid search region")
        return "", None, text_position, 0.0

    crop_w = crop_x2 - crop_x1
    crop_h = crop_y2 - crop_y1

    if crop_w < 10 or crop_h < 10:
        if DEBUG_CUSTOM_SYMBOLS:
            print(f"Crop too small: {crop_w}x{crop_h}")
        return "", None, text_position, 0.0

    # Extract crop
    crop_bgr = bgr_color[crop_y1:crop_y2, crop_x1:crop_x2]
    pil_crop = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))

    # Upscale if small
    pil_crop = _upscale_if_tiny(pil_crop, min_side=80, scale=2)

    if DEBUG_CUSTOM_SYMBOLS:
        print(f"Crop size: {pil_crop.width}x{pil_crop.height}")

    # Debug: Save original crop (using anchor's name if available)
    anchor_name = anchor.get("name", "custom_symbol")
    if anchor_name:  # This should always be true if called properly
        _save_debug_crop(crop_bgr, anchor_name, suffix="original")

    # Preprocessing
    g0 = _pil_to_gray_np(pil_crop)
    g1 = _enhance_contrast(g0)

    # Try PaddleOCR with AUTO text detection
    paddle = get_paddleocr_instance()

    if paddle is None:
        if DEBUG_CUSTOM_SYMBOLS:
            print(f"PaddleOCR not available")
        return "", None, text_position, 0.0

    best_txt = ""
    best_conf = 0.0
    best_distance = float('inf')

    # Symbol center relative to crop
    sym_cx_rel = sym_cx - crop_x1
    sym_cy_rel = sym_cy - crop_y1

    try:
        # Run PaddleOCR - it will DETECT text boxes automatically
        test_arr = cv2.cvtColor(g1, cv2.COLOR_GRAY2BGR)
        results = paddle.ocr(test_arr, cls=False)

        if results and results[0]:
            if DEBUG_CUSTOM_SYMBOLS:
                print(f"Found {len(results[0])} text boxes")

            for line in results[0]:
                if line is None:
                    continue
                bbox, (text, conf) = line

                if not text or conf < 0.4:
                    continue

                text = text.strip()
                if len(text) < 2:
                    continue

                # Get text box center (relative to crop)
                txt_cx = sum(pt[0] for pt in bbox) / 4
                txt_cy = sum(pt[1] for pt in bbox) / 4

                # Calculate distance from symbol to text
                dx = txt_cx - sym_cx_rel
                dy = txt_cy - sym_cy_rel
                distance = (dx**2 + dy**2) ** 0.5

                # Check if text is in the correct direction
                is_correct_direction = True
                if text_position == "left" and dx > 0:
                    is_correct_direction = False
                elif text_position == "right" and dx < 0:
                    is_correct_direction = False
                elif text_position == "above" and dy > 0:
                    is_correct_direction = False
                elif text_position == "below" and dy < 0:
                    is_correct_direction = False

                if DEBUG_CUSTOM_SYMBOLS:
                    dir_ok = "" if is_correct_direction else ""
                    print(f"[{dir_ok}] '{text}' conf={conf:.2f} dist={distance:.0f}px dx={dx:.0f} dy={dy:.0f}")

                # Pick the CLOSEST text in the correct direction
                if is_correct_direction and distance < best_distance:
                    best_txt = text
                    best_conf = conf
                    best_distance = distance

        # If no text found in correct direction, try without direction filter
        if not best_txt and results and results[0]:
            if DEBUG_CUSTOM_SYMBOLS:
                print(f"No text in '{text_position}' direction, taking closest...")
            for line in results[0]:
                if line is None:
                    continue
                bbox, (text, conf) = line
                if not text or conf < 0.4 or len(text.strip()) < 2:
                    continue
                text = text.strip()
                txt_cx = sum(pt[0] for pt in bbox) / 4
                txt_cy = sum(pt[1] for pt in bbox) / 4
                distance = ((txt_cx - sym_cx_rel)**2 + (txt_cy - sym_cy_rel)**2) ** 0.5
                if distance < best_distance:
                    best_txt = text
                    best_conf = conf
                    best_distance = distance

    except Exception as e:
        if DEBUG_CUSTOM_SYMBOLS:
            print(f"OCR error: {e}")

    if DEBUG_CUSTOM_SYMBOLS:
        if best_txt:
            print(f"RESULT: '{best_txt}' in region ({crop_x1},{crop_y1})-({crop_x2},{crop_y2})")
        else:
            print(f"NO TEXT FOUND")

    # Debug: Save final result if text was found
    anchor_name = anchor.get("name", "custom_symbol")
    if best_txt and anchor_name:
        _save_debug_crop(crop_bgr, anchor_name, best_txt, suffix="final")

    # Return text, bbox coordinates, position used, and confidence
    if best_txt:
        ocr_bbox = (crop_x1, crop_y1, crop_x2, crop_y2)
        return best_txt.strip(), ocr_bbox, text_position, best_conf
    else:
        return "", None, text_position, 0.0
# config.py
"""
Centralized configuration for railway detection system.
All constants, thresholds, and parameters in one place.
"""

import re
from typing import List, Dict, Optional
import os

# ============================================================================
# SYSTEM SETTINGS
# ============================================================================

POPPLER_PATH = None
DEBUG_SIGNALS = False
DEBUG_ANGLE_ROUTING = False

# ============================================================================
# PROCESSING PARAMETERS
# ============================================================================

TILE_SIZE = 2048
OVERLAP_PCT = 30
DPI = 500
PRED_IMGSZ = 1024
TILE_HALO = 192
OBB_ONLY = True
ZOOM_SIZE = 2048

MAX_OCR_WORKERS = max(2, min(12, (os.cpu_count() or 4)))

# ============================================================================
# OCR ENGINE SELECTION
# ============================================================================

OCR_ENGINE = "paddleocr"

# ============================================================================
# CLASS DEFINITIONS
# ============================================================================

CLASSES = [
    'signal',
    'gm_block',
    'gks_festkodiert',
    'gks_gesteuert',
    'weichen_block',
    'isolierstoß',
    'haltepunkt',
    'sverbinder',
    'coordinate',
    'weichenende',
    'prellblock',
    'haltetafel',
    'weichengruppeende'
]
# Build index mapping
IDX = {name: i for i, name in enumerate(CLASSES)}

# ============================================================================
# ALIASES & REMAPPING
# ============================================================================

ALIASES = {
    "endeweichen": "weichenende",
}

def _alias_name(n: str) -> str:
    """Apply class name aliases."""
    return ALIASES.get(n, n)

CLASS_REMAP = {}

def canon_name(n: str) -> str:
    """Get canonical class name after aliasing and remapping."""
    n0 = _alias_name(n)
    return CLASS_REMAP.get(n0, n0)

# ============================================================================
# VALIDATION PATTERNS
# ============================================================================

NUMERIC_OK = {"gks_gesteuert", "gks_festkodiert", "weichen_block", "prellblock"}

CLASS_ID_PATTERNS = {
    "signal": r"^[A-ZÄÖÜ]{1,4}\d{1,4}$",
    "gks_gesteuert": r"^\d{3,4}$",
    "gks_festkodiert": r"^\d{3,4}$",
}

COORD_RE = re.compile(r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$')

# ============================================================================
# CONFIDENCE THRESHOLDS
# ============================================================================

CLASS_THRESH = {
    "signal": 0.8,
    "gm_block": 0.8,
    "gks_festkodiert": 0.7,
    "gks_gesteuert": 0.7,
    "weichen_block": 0.90,
    "isolierstoß": 0.7,
    "haltepunkt": 0.8,
    "sverbinder": 0.80,
    "coordinate": 0.65,
    "weichenende": 0.8,
    "prellblock": 0.8,
    "haltetafel": 0.70,
    "weichengruppeende": 0.8
}

# ============================================================================
# LINKING RULES
# ============================================================================

LINK_RULES = {
    "signal": dict(mode="below"),
    "gm_block": dict(mode="below"),
    "gks_festkodiert": dict(mode="either"),
    "gks_gesteuert": dict(mode="either"),
    "weichen_block": dict(mode="inside", block=True),
    "isolierstoß": dict(mode="above", tilted_ok=True),
    "haltepunkt": dict(mode="either"),
    "sverbinder": dict(mode="above"),
    "weichenende": dict(mode="either", dx_multiplier=3.0, prefer_horizontal=True),
    "prellblock": dict(mode="right_or_below", dx_multiplier=2.0, prefer_horizontal=True),
    "haltetafel": dict(mode="either", dx_multiplier=2.0),
    "weichengruppeende": dict(mode="either", dx_multiplier=4.0, prefer_horizontal=True, search_left=True)
}

# ============================================================================
# ORIENTATION-BASED PARAMETERS
# ============================================================================

# CARDINAL (Horizontal/Vertical) PARAMETERS
CARDINAL_PARAMS = {
    "detection_padding": {
        "coordinate": 4,
        "signal": 4,
        "weichenende": 8,
        "haltetafel": 4,
        "prellblock": 4,
        "gks_gesteuert": 8,
        "gks_festkodiert": 8,
        "weichengruppeende": 4,
        "weichen_block": 2,
    },
    "expansion_factor": {
        "coordinate": (1.0, 1.0),
        "signal": (1.0, 1.0),
        "gks_gesteuert": (0.6, 0.6),   
        "gks_festkodiert": (0.6, 0.6),
        "weichen_block": (1.1, 1.0),
    }
}

HORIZONTAL_PARAMS = CARDINAL_PARAMS
VERTICAL_PARAMS = CARDINAL_PARAMS

# ANGULAR PARAMETERS (>15° from cardinal)
ANGULAR_PARAMS = {
    "detection_padding": {
        "coordinate": 4,
        "signal": 8,
        "weichenende": 4,
        "haltetafel": 4,
        "prellblock": 4,
        "gks_gesteuert": 6,
        "gks_festkodiert": 6,
    },
    "expansion_factor": {
        "coordinate": (1.0, 1.0),
        "signal": (1.0, 1.05),
        "gks_gesteuert": (0.75, 0.75),
        "gks_festkodiert": (0.75, 0.75),
    }
}

# ============================================================================
# SIGNAL OCR PARAMETERS
# ============================================================================

SIG_ONE_WINDOW = True
SIG_PAD = 14
SIG_EXPAND_X = 0.18
SIG_EXPAND_Y = 0.22
SIG_USE_TIGHTEN = False
SIG_SCORE_MIN = 1.3
SIG_LINE_THICK = 5
LEFT_BIAS_EXPANSION_CLASSES = {"signal"}
LEFT_BIAS_RATIO_H = 0.8
SIGNAL_TEXT_HEIGHT_HINT: Optional[int] = None

# ============================================================================
# PADDLEOCR PARAMETERS
# ============================================================================

PADDLEOCR_PARAMS = {
    "denoise_strength": 3,
    "sharpen_amount": 1.2,
    "confidence_threshold": {
        "signal": 0.60,
        "gks_gesteuert": 0.50,
        "gks_festkodiert": 0.50,
        "coordinate": 0.55,
        "default": 0.50
    },
    "use_preprocessing": True,
    "use_adaptive_threshold": False,
    "use_morph_operations": True,
}

# ============================================================================
# VALIDATION
# ============================================================================

def validate_config():
    """Validate configuration consistency."""
    errors = []
    
    # Check CLASS_THRESH
    for cls in CLASS_THRESH.keys():
        if cls not in CLASSES:
            errors.append(f"CLASS_THRESH references unknown class: '{cls}'")
    
    # Check LINK_RULES
    for cls in LINK_RULES.keys():
        if cls not in CLASSES:
            errors.append(f"LINK_RULES references unknown class: '{cls}'")
    
    # Check NUMERIC_OK
    for cls in NUMERIC_OK:
        if cls not in CLASSES:
            errors.append(f"NUMERIC_OK references unknown class: '{cls}'")
    
    # Check CLASS_ID_PATTERNS
    for cls in CLASS_ID_PATTERNS.keys():
        if cls not in CLASSES:
            errors.append(f"CLASS_ID_PATTERNS references unknown class: '{cls}'")
    
    if errors:
        print("⚠️ Configuration warnings:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✓ Configuration validated successfully")

# Auto-validate on import
validate_config()



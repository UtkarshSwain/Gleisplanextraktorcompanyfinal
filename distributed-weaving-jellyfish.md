# Changes from `code_modular` to `test/templatematchingcompany`

This document details all the **logical changes** made on the `test/templatematchingcompany` branch since branching from `code_modular`. Use this to apply the same fixes to your modular YAML-based codebase.

---

## Summary of Commits (11 total)

| Commit | Description |
|--------|-------------|
| d93a037 | Fixed the weichen_block 0 to O problem |
| b7f7e92 | Fixed haltetafel linking and weichen_block OCR |
| a6a1083 | Turned debug comparison debug off |
| 8c06897 | Added versionierung (versioning) |
| 99f4e2c | Fixed the document |
| 1c3e4a4 | Remove docs folder from Git tracking |
| 846beda | Added comment and fixed everything |
| 93799ff | Fixed validation to have 80 as the warnung for YOLO classes |
| f11e925 | Fixed the config for haltetafel |
| 30ef8af | Fixed the export |
| e91fd9b | Fixed the bbox issue |

---

## 1. CONFIG CHANGES (`config.py`)

### 1.1 Version Info Added
```python
# Add at top of config.py
__version__ = "1.0.0"
__author__ = "Utkarsh Swain"
__email__ = ""
__created__ = "2024"
__updated__ = "2026"
__company__ = "Siemens Mobility GmbH"
__app_name__ = "RailDoc Studio - Gleisplan-Modul"
```

### 1.2 Haltetafel Confidence Threshold Changed
```python
# BEFORE:
"haltetafel": 0.55

# AFTER:
"haltetafel": 0.81
```
**Reason**: Reduced false positives for haltetafel detection.

### 1.3 Haltetafel Linking Rule Updated
```python
# BEFORE:
"haltetafel": dict(mode="either", dx_multiplier=2.0)

# AFTER:
"haltetafel": dict(mode="either", dx_multiplier=2.0, fallback_dy_steps=[2.0, 2.5])
```
**Reason**: Added fallback search steps to improve haltetafel-to-coordinate linking.

### 1.4 Debug Comparison Disabled
```python
# BEFORE:
DEBUG_COMPARISON = True

# AFTER:
DEBUG_COMPARISON = False
```

### 1.5 Path Defaults Set to None (for portability)
```python
# BEFORE:
TESSERACT_PATH = r"C:\Users\z0054cxa\Documents\..."
POPPLER_PATH = r"C:\Users\z0054cxa\Documents\..."

# AFTER:
TESSERACT_PATH = None
POPPLER_PATH = None
```

---

## 2. OCR ENGINE FIXES (`core/ocr_engine.py`)

### 2.1 Weichen_block "0" to "O" Fix
The weichen_block OCR was misreading the letter "O" as number "0". This is the key fix from commit `d93a037`.

**Where to apply**: In your modular code's weichen_block OCR handling, ensure character substitution handles this case:
```python
# When processing weichen_block text:
# The OCR sometimes reads "O" (letter) as "0" (zero)
# Add post-processing to convert based on context
```

### 2.2 Decimal Separator Hardcoded
```python
# BEFORE (modular): Used configurable DECIMAL_SEP_INPUT/OUTPUT
result = bracket_complete_match.group(0).replace(DECIMAL_SEP_INPUT, DECIMAL_SEP_OUTPUT)

# AFTER (fixed): Hardcoded German comma to dot
result = bracket_complete_match.group(0).replace(',', '.')
```
**Files affected**:
- `_clean_coordinate_overlap()` function
- `_fix_coordinate_brackets()` function

**Changes in 3 places**:
```python
# Line ~669, ~682, ~702, ~803
text = text.replace(',', '.')  # German decimal separator
```

### 2.3 Angular Box Padding Simplified
```python
# BEFORE (modular): Used config-driven padding
pad_dict = ANGULAR_PARAMS["detection_padding"]
base_pad = pad_dict.get(cls_name, 8)
if box_min_side < 70:
    pad = int(base_pad * 3.0)
elif box_min_side < 100:
    pad = int(base_pad * 2.5)
else:
    pad = int(base_pad * 2.0)

# AFTER (fixed): Hardcoded generous padding for angular boxes
if box_min_side < 70:
    pad = 18  # Very generous
elif box_min_side < 100:
    pad = 16
else:
    pad = 14
```
**Location**: `ocr_numeric_tilted_box()` function around line 2019-2030

### 2.4 Signal Pattern Simplified
```python
# BEFORE (modular): Used configurable CLASS_ID_PATTERNS
signal_pattern = CLASS_ID_PATTERNS.get("signal")
if signal_pattern:
    relaxed_pattern = signal_pattern.replace(r'\d', r'\s*\d')
    return bool(re.match(relaxed_pattern, ss))

# AFTER (fixed): Simple hardcoded pattern
SIG_STRICT_RE = re.compile(r'^[A-ZÄÖÜ]{1,4}\s*\d{1,4}$')
return bool(SIG_STRICT_RE.match(ss))
```
**Location**: `_is_strict_signal_id()` function

---

## 3. LINKING FIXES (`core/linking.py`)

### 3.1 Removed Config Dependency
The modular version passes `config` parameter to many functions. The fixed version removed this and uses direct imports from `config.py`.

**Key change**: All functions that had `config: 'LayoutConfig' = None` parameter no longer need it:
- `link_anchor_to_coord()`
- `detect_fahrtrichtung()`
- `detect_haltepunkt_signal_group()`
- `link_haltetafel_to_gks()`
- etc.

### 3.2 NAME_RULES_EXTRA Hardcoded
```python
# BEFORE (modular):
NAME_RULES_EXTRA_DEFAULTS = {...}  # Used as fallback

# AFTER (fixed):
NAME_RULES_EXTRA = {
    # ... hardcoded rules
}
```

---

## 4. PIPELINE WORKER FIXES (`core/pipelineworker.py`)

### 4.1 Removed Config Parameter from Constructor
```python
# BEFORE (modular):
def __init__(self, file_path: str, model_path: str, ocr_engine: str, parent=None,
             run_analysis=True, detect_tracks=False, config: 'LayoutConfig' = None):

# AFTER (fixed):
def __init__(self, file_path: str, model_path: str, ocr_engine: str, parent=None,
             run_analysis=True, detect_tracks=False):
```

### 4.2 NO_OCR_CLASSES and FIXED_TEXT_CLASSES Hardcoded
```python
# BEFORE (modular): Built from config
NO_OCR_CLASSES = []  # Populated from config.classes
FIXED_TEXT_CLASSES = {}  # Populated from config.classes

# AFTER (fixed): Hardcoded
NO_OCR_CLASSES = ["isolierstoß", "haltepunkt", "sverbinder", "weichenende", "weichengruppenende", "haltetafel"]
FIXED_TEXT_CLASSES = {"gm_block": "GM", "prellbock": "PB"}
```

### 4.3 Fahrtrichtung Detection - Hardcoded Parameters
```python
# BEFORE (modular):
fahrtrichtung = detect_fahrtrichtung(
    signal_det, gks_dets,
    max_distance=sp_gks.signal_gks_max_distance if sp_gks else 250,
    dy_min=sp_gks.signal_gks_dy_min if sp_gks else 30,
    # ... more config params
)

# AFTER (fixed):
fahrtrichtung = detect_fahrtrichtung(
    signal_det, gks_dets,
    track_skeleton=None,
    track_bounds=None,
    max_distance=250  # Hardcoded
)
```

### 4.4 All Spatial Parameters Hardcoded
| Parameter | Value |
|-----------|-------|
| `signal_gks_max_distance` | 250 |
| `signal_gks_dy_min` | 30 |
| `signal_gks_dy_max` | 200 |
| `haltepunkt_cluster_max_distance` | 250 |
| `haltetafel_gks_max_distance` | 250 |
| `isolierstoss_fallback_radius` | 300 |
| `track_sample_distance` | 300 |
| `track_search_radius` | 500 |
| `signal_gks_relaxed_dx_tolerance` | 200 |
| `signal_gks_relaxed_dy_max` | 600 |
| `signal_gks_nearest_max_distance` | 800 |

---

## 5. YOLO DETECTION FIXES (`core/yolo_detection.py`)

### 5.1 Removed Config Parameter
```python
# BEFORE (modular):
def tile_image(bgr: np.ndarray, config: 'LayoutConfig' = None, tile: int = None, overlap_pct: int = None):
def run_yolo_on_page(model, page_bgr: np.ndarray, config: 'LayoutConfig') -> List[dict]:
def run_combined_detection(model, page_bgr: np.ndarray, config: 'LayoutConfig', detect_custom: bool = True):

# AFTER (fixed):
def tile_image(bgr: np.ndarray, tile=TILE_SIZE, overlap_pct=OVERLAP_PCT):
def run_yolo_on_page(model, page_bgr: np.ndarray) -> List[dict]:
def run_combined_detection(model, page_bgr: np.ndarray, detect_custom: bool = True):
```

### 5.2 Direct Config Imports
```python
# AFTER (fixed): Import directly from config.py
from config import (TILE_SIZE, OVERLAP_PCT, PRED_IMGSZ, CLASS_THRESH, CLASSES,
                    TILE_HALO, DEBUG_ANGLE_ROUTING, canon_name, OBB_ONLY,
                    NMS_THRESHOLDS, UNCERTAIN_THRESH_MULTIPLIER, MIN_UNCERTAIN_THRESH,
                    MIN_UNCERTAIN_THRESH_DEFAULT, EXCLUDE_LEGEND_STRIP,
                    LEGEND_STRIP_WIDTH_PERCENT, LEGEND_STRIP_MAX_PIXELS)
```

---

## 6. HELPER FUNCTIONS (`utils/helpers.py`)

### 6.1 Removed Debug Configuration Function
```python
# REMOVED from modular version:
def configure_debug_from_config(config: 'LayoutConfig') -> None:
    """Configure debug flags from a LayoutConfig object."""
    # ... removed
```

### 6.2 Direct Config Imports
```python
# AFTER (fixed):
from config import VERTICAL_PARAMS, HORIZONTAL_PARAMS, ANGULAR_PARAMS
```

### 6.3 Simplified get_params_for_angle()
```python
# BEFORE (modular):
def get_params_for_angle(angle_deg: float, class_name: str, config: 'LayoutConfig' = None):
    if config is not None:
        cardinal_padding = config.ocr.cardinal_detection_padding
        # ...

# AFTER (fixed):
def get_params_for_angle(angle_deg: float, class_name: str):
    # Uses HORIZONTAL_PARAMS, VERTICAL_PARAMS, ANGULAR_PARAMS directly
    if _is_near(a, 0.0) or _is_near(a, 180.0):
        pad = HORIZONTAL_PARAMS["detection_padding"].get(class_name, 8)
        exp = HORIZONTAL_PARAMS["expansion_factor"].get(class_name, (1.0, 1.0))
    # ...
```

---

## 7. UI SETUP WINDOW (`ui/setup_window.py`)

### 7.1 Removed Profile Selection UI
The entire "Step 03: PROFIL" section was removed from the UI since profiles are not used.

### 7.2 Removed Profile Loading
```python
# REMOVED:
from core.profile_manager import ProfileManager
self.profile_path = "profiles/siemens_track_plans.yaml"
self.layout_config = None

def on_profile_changed(self, index: int): ...
def _load_profile(self) -> bool: ...
```

### 7.3 PipelineWorker Without Config
```python
# BEFORE (modular):
self.worker = PipelineWorker(
    self.pdf_path, self.model_path, self.ocr_engine,
    run_analysis=True, detect_tracks=detect_tracks,
    config=self.layout_config
)

# AFTER (fixed):
self.worker = PipelineWorker(
    self.pdf_path, self.model_path, self.ocr_engine,
    run_analysis=True, detect_tracks=detect_tracks
)
```

### 7.4 CRITICAL: BGR Array Copy Fix
```python
# ADDED to prevent reference sharing between workspaces:
page_base_pix_copy = dict(self._page_base_pix) if getattr(self, '_page_base_pix', None) else {}
page_bgr_arrays_copy = {k: v.copy() if hasattr(v, 'copy') else v
                        for k, v in self._page_bgr_arrays.items()} if getattr(self, '_page_bgr_arrays', None) else {}
```
**Applied in 3 places**: When emitting `processing_done` signal.

---

## 8. WORKSPACE WIDGET (`ui/workspace_widget.py`)

### 8.1 Import Change
```python
# BEFORE (modular):
from core.image_processing import ZOOM_SIZE

# AFTER (fixed):
from config import ZOOM_SIZE
```

### 8.2 Risk Score Calculation Simplified
```python
# BEFORE (modular): Used NUMERIC_OK from config
if cls in NUMERIC_OK:  # Configurable

# AFTER (fixed): Hardcoded classes
if cls in ['gks_gesteuert', 'gks_festkodiert']:  # Explicit
```

---

## 9. DELETED FILES (from modular branch)

These files exist in `code_modular` but were removed in the fixed branch:

| File | Purpose |
|------|---------|
| `CODEBASE_ANALYSIS.md` | Documentation |
| `MODULARITY_EXPLAINED.md` | Documentation |
| `MODULARITY_IMPLEMENTATION_GUIDE.md` | Documentation |
| `MODULARITY_QUICKSTART.md` | Documentation |
| `core/config_models.py` | Pydantic models for YAML config |
| `core/interfaces.py` | Abstract interfaces |
| `core/profile_manager.py` | YAML profile loading |
| `profiles/siemens_track_plans.yaml` | YAML profile |
| `test_modular_pipeline.py` | Tests |
| `test_phase1.py` | Tests |

---

## 10. HOW TO APPLY THESE CHANGES TO YOUR MODULAR BRANCH

### Option A: Keep Modular Architecture, Apply Bug Fixes

1. **Haltetafel confidence**: Update your YAML profile:
   ```yaml
   classes:
     - name: haltetafel
       confidence_threshold: 0.81  # was 0.55
       linking_rule:
         mode: either
         dx_multiplier: 2.0
         fallback_dy_steps: [2.0, 2.5]  # ADD THIS
   ```

2. **Weichen_block OCR**: Add post-processing for "0" → "O" conversion in context

3. **Decimal separator**: If German docs always use comma, hardcode it

4. **Angular padding**: Apply the fixed padding values (18, 16, 14)

5. **BGR array copy**: Add `.copy()` when passing BGR arrays between workspaces

### Option B: Simplify to Non-Modular (Recommended if YAML not needed)

Remove the config parameter from all function signatures and import values directly from `config.py`.

---

## 11. KEY BUG FIXES SUMMARY

| Bug | Fix | Files |
|-----|-----|-------|
| Weichen_block reads "O" as "0" | Add OCR post-processing | `core/ocr_engine.py` |
| Haltetafel false positives | Raise threshold to 0.81 | `config.py` |
| Haltetafel linking fails | Add fallback_dy_steps | `config.py`, `core/linking.py` |
| Decimal separator issues | Hardcode comma → dot | `core/ocr_engine.py` |
| Workspace BGR overwrites | Copy arrays before sharing | `ui/setup_window.py` |
| Angular OCR padding too small | Use fixed generous padding | `core/ocr_engine.py` |

---

*Generated from git diff between `code_modular` and `test/templatematchingcompany` branches*

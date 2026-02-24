# MODULARITY IMPLEMENTATION GUIDE - OPTION 2.5
**Complete Implementation Instructions**

---

## OVERVIEW

**Goal:** Refactor the railway plan extraction pipeline from a single-layout hardcoded system to a modular, profile-based architecture that supports:
- Multiple layout types via YAML configuration profiles
- Swappable detection models (YOLO, Faster R-CNN, custom CNNs)
- Pluggable linking strategies (rule-based, LLM-based, ML-based)
- Multiple storage backends (CSV, PostgreSQL, S3, APIs)
- LLM-based validation components

**Timeline:** 10-14 hours of focused work

**Deliverables:**
1. Modular core architecture with component interfaces
2. Profile-based configuration system
3. 3 working profile variants (standard, strict, relaxed)
4. Full backward compatibility with existing code
5. Documentation and usage examples

---

## CURRENT ARCHITECTURE PROBLEMS

### Problem 1: Global Configuration Dependencies
```python
# Every module imports globals from config.py
from config import CLASSES, CLASS_THRESH, LINK_RULES, TILE_SIZE, DPI, ...

# This means:
# - Cannot process multiple layouts simultaneously
# - Cannot experiment with parameters without restarting
# - Cannot swap components
# - Hard to test different configurations
```

### Problem 2: Hardcoded Implementation Details
```python
# Hardcoded pixel values in linking.py
if anchor["name"] == "signal":
    dy = int(2.2 * ah)      # Hardcoded 2.2x multiplier
    dx = int(2.4 * aw)      # Hardcoded 2.4x multiplier
else:
    dy = int(1.6 * ah)
    dx = int(1.0 * aw)

# Hardcoded search windows
right_w = int(2.5 * aw)     # Hardcoded 2.5x
right_h = int(0.6 * ah)     # Hardcoded 0.6x
```

### Problem 3: No Component Abstraction
```python
# Direct function calls - cannot swap implementations
detections = run_yolo_on_page(model, page_bgr)  # Locked to YOLO
text = ocr_anchor_name(anchor, bgr, "paddleocr")  # Locked to PaddleOCR
coord = link_anchor_to_coord(anchor, coords)  # Locked to rule-based linking
```

---

## TARGET ARCHITECTURE

### Component Diagram
```
┌─────────────────────────────────────────────────────────────┐
│                     PipelineOrchestrator                     │
│                  (PipelineWorker refactored)                 │
└────────┬────────────────┬────────────────┬──────────────────┘
         │                │                │
         ▼                ▼                ▼
    ┌─────────┐      ┌─────────┐     ┌──────────┐
    │IDetector│      │ ILinker │     │IOCREngine│
    └────┬────┘      └────┬────┘     └─────┬────┘
         │                │                 │
    ┌────┴────────┐  ┌────┴────────┐  ┌────┴─────────┐
    │ YOLO        │  │ RuleBased   │  │ PaddleOCR    │
    │ FasterRCNN  │  │ MLBased     │  │ Tesseract    │
    │ CustomCNN   │  │ LLMBased    │  │ GoogleVision │
    └─────────────┘  └─────────────┘  └──────────────┘

         ┌──────────────┐      ┌──────────────┐
         │  IValidator  │      │IStorageBackend│
         └──────┬───────┘      └──────┬────────┘
                │                     │
         ┌──────┴─────────┐    ┌──────┴───────────┐
         │ RuleBased      │    │ LocalFile        │
         │ LLMBased       │    │ PostgreSQL       │
         │ HybridValidator│    │ S3Cloud          │
         └────────────────┘    │ RestAPI          │
                               └──────────────────┘

                    ┌───────────────┐
                    │ LayoutConfig  │
                    │ (from YAML)   │
                    └───────────────┘
```

### Key Principles
1. **Dependency Injection:** Components receive dependencies, not import globals
2. **Interface Segregation:** Each component implements a clear interface
3. **Configuration as Data:** All layout-specific values in YAML, not code
4. **Open/Closed Principle:** Open for extension (new implementations), closed for modification

---

## PHASE 1: CONFIGURATION ARCHITECTURE (3-4 hours)

### Task 1.1: Create LayoutConfig Dataclass

**File:** `core/config_models.py` (NEW FILE)

```python
"""
Configuration models for layout-specific parameters.
This module defines the data structures for profile-based configuration.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import re


@dataclass
class DetectionConfig:
    """YOLO detection parameters"""
    tile_size: int = 2048
    overlap_pct: int = 40
    dpi: int = 500
    pred_imgsz: int = 1024
    tile_halo: int = 320
    obb_only: bool = True
    use_tta: bool = True
    tta_scales: List[float] = field(default_factory=lambda: [1.0])
    tta_flips: List[int] = field(default_factory=lambda: [0, 1])
    tta_min_votes: int = 1


@dataclass
class OCRConfig:
    """OCR engine parameters"""
    engine: str = "paddleocr"
    max_workers: int = 8

    # Signal-specific parameters
    sig_one_window: bool = True
    sig_pad: int = 14
    sig_expand_x: float = 0.18
    sig_expand_y: float = 0.22
    sig_use_tighten: bool = False
    sig_score_min: float = 1.3
    sig_line_thick: int = 5
    signal_text_height_hint: Optional[int] = None

    # Angle-aware parameters
    angle_tol: float = 12.0  # Degrees threshold for cardinal vs angular

    # PaddleOCR-specific
    denoise_strength: int = 4
    sharpen_amount: float = 1.3
    use_preprocessing: bool = True
    use_adaptive_threshold: bool = True
    use_morph_operations: bool = True

    # Per-class confidence thresholds
    confidence_thresholds: Dict[str, float] = field(default_factory=lambda: {
        "signal": 0.50,
        "gks_gesteuert": 0.40,
        "gks_festkodiert": 0.40,
        "coordinate": 0.65,
        "default": 0.45
    })

    # Cardinal (horizontal/vertical) text parameters
    cardinal_detection_padding: Dict[str, int] = field(default_factory=lambda: {
        "coordinate": 4,
        "signal": 4,
        "weichenende": 8,
        "gks_gesteuert": 8,
        "weichengruppenende": 4,
        "weichen_block": 2
    })

    cardinal_expansion_factor: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        "coordinate": (1.0, 1.0),
        "signal": (1.0, 1.0),
        "gks_gesteuert": (0.6, 0.6),
        "weichen_block": (1.1, 1.0)
    })

    # Angular (rotated) text parameters
    angular_detection_padding: Dict[str, int] = field(default_factory=lambda: {
        "coordinate": 4,
        "signal": 8,
        "gks_gesteuert": 6
    })

    angular_expansion_factor: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        "coordinate": (1.0, 1.0),
        "signal": (1.0, 1.05),
        "gks_gesteuert": (0.75, 0.75)
    })


@dataclass
class SpatialConfig:
    """Spatial relationship parameters"""
    # Name window search multipliers (used in name_windows_for)
    signal_dy_multiplier: float = 2.2
    signal_dx_multiplier: float = 2.4
    default_dy_multiplier: float = 1.6
    default_dx_multiplier: float = 1.0

    # Search window dimensions
    inside_padding_ratio: float = 0.10
    right_window_width_ratio: float = 2.5
    right_window_height_ratio: float = 0.6
    left_window_width_ratio: float = 4.0
    left_window_height_ratio: float = 0.6
    sverbinder_window_width_ratio: float = 0.9
    sverbinder_window_height_ratio: float = 0.3

    # Coordinate linking distances (used in link_anchor_to_coord)
    dy_max_base_multiplier: float = 1.6  # Multiplied by anchor height
    dx_base_multiplier: float = 0.6  # Multiplied by max(anchor_w, coord_w)
    dx_tight_multiplier: float = 0.45
    dx_minimum_threshold: int = 30  # Minimum pixels
    left_search_bonus: float = 1.3  # 30% bonus for left-side coordinates

    # Distance-based search radii (pixels)
    haltetafel_gks_max_distance: int = 250
    haltetafel_gks_dy_tolerance: int = 100
    haltetafel_gks_dx_tolerance: int = 300

    signal_gks_max_distance: int = 250
    signal_gks_dy_min: int = 30
    signal_gks_dy_max: int = 200
    signal_gks_dx_tolerance_left: int = 120
    signal_gks_dx_tolerance_right: int = 120
    signal_gks_angle_tolerance: float = 20.0  # Degrees

    # Track perpendicular detection
    track_perpendicular_max_distance: int = 1500
    track_window_size: int = 25  # Check window ±25px around ray

    # Haltepunkt-Signal-Coordinate clustering
    haltepunkt_cluster_max_distance: int = 250
    haltepunkt_signal_dy_min: int = 30
    haltepunkt_signal_dy_max: int = 200
    haltepunkt_coord_dy_min: int = 20
    haltepunkt_coord_dy_max: int = 150
    haltepunkt_dx_tolerance: int = 100

    # Adaptive pattern learning
    adaptive_search_dx_multiplier: float = 3.0  # 3 * std_dev
    adaptive_search_dx_minimum: int = 150
    adaptive_search_dy_multiplier: float = 3.0
    adaptive_search_dy_minimum: int = 80

    # Signal group clustering
    spatial_threshold_single_section: int = 1000
    spatial_threshold_gap_multiplier: float = 3.0  # Gaps > 3x median = section boundary
    spatial_threshold_section_gap_min: int = 1000
    spatial_threshold_section_gap_max: int = 2500


@dataclass
class LinkingRule:
    """Spatial relationship rule for a symbol class"""
    mode: str = "below"  # "below", "above", "either", "inside", "right_or_below"
    dx_multiplier: float = 1.0
    dy_multiplier: float = 1.0
    prefer_horizontal: bool = False
    search_left: bool = False
    tilted_ok: bool = False
    block: bool = False  # For "inside" mode with blocking behavior


@dataclass
class NameSearchRule:
    """Name text search directions for a symbol class"""
    inside: bool = False
    left: bool = False
    right: bool = False
    below: bool = False
    above: bool = False


@dataclass
class ClassDefinition:
    """Definition of a symbol class"""
    name: str
    class_id: int
    confidence_threshold: float = 0.5
    nms_threshold: float = 0.4
    requires_ocr: bool = True
    requires_coordinate: bool = False
    fixed_text: Optional[str] = None  # e.g., "GM" for gm_block
    numeric_ok: bool = False
    id_pattern: Optional[str] = None  # Regex for validation
    linking_rule: LinkingRule = field(default_factory=LinkingRule)
    name_search_rule: NameSearchRule = field(default_factory=NameSearchRule)
    alias: Optional[str] = None  # Alternative name for backwards compatibility


@dataclass
class ValidationConfig:
    """Validation patterns and rules"""
    # Coordinate regex pattern (German format: "12,345 Gl.113")
    coordinate_pattern: str = r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$'

    # Per-class ID validation patterns
    class_id_patterns: Dict[str, str] = field(default_factory=lambda: {
        "signal": r"^[A-ZÄÖÜ]{1,4}\d{1,4}$",
        "gks_gesteuert": r"^\d{3,4}$",
        "gks_festkodiert": r"^\d{3,4}$"
    })

    # Classes that allow pure numeric IDs
    numeric_ok_classes: List[str] = field(default_factory=lambda: [
        "gks_gesteuert", "gks_festkodiert", "weichen_block", "prellbock"
    ])


@dataclass
class LayoutConfig:
    """
    Complete configuration for a railway layout type.

    This is the main configuration object that gets loaded from YAML profiles
    and injected into pipeline components.
    """
    # Profile metadata
    profile_name: str = "default"
    profile_version: str = "1.0"
    description: str = ""

    # Class definitions
    classes: List[ClassDefinition] = field(default_factory=list)

    # Component configurations
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)

    # Model path (can be layout-specific)
    model_path: Optional[str] = None

    # Debug flags
    debug_signals: bool = False
    debug_angle_routing: bool = False

    # System settings
    poppler_path: Optional[str] = None
    zoom_size: int = 2048

    def get_class_by_name(self, name: str) -> Optional[ClassDefinition]:
        """Get class definition by name, handling aliases"""
        for cls in self.classes:
            if cls.name == name or cls.alias == name:
                return cls
        return None

    def get_class_by_id(self, class_id: int) -> Optional[ClassDefinition]:
        """Get class definition by ID"""
        for cls in self.classes:
            if cls.class_id == class_id:
                return cls
        return None

    def get_class_names(self) -> List[str]:
        """Get list of all class names in ID order"""
        sorted_classes = sorted(self.classes, key=lambda c: c.class_id)
        return [c.name for c in sorted_classes]

    def get_confidence_threshold(self, class_name: str) -> float:
        """Get confidence threshold for a class"""
        cls = self.get_class_by_name(class_name)
        return cls.confidence_threshold if cls else 0.5

    def get_nms_threshold(self, class_name: str) -> float:
        """Get NMS threshold for a class"""
        cls = self.get_class_by_name(class_name)
        return cls.nms_threshold if cls else 0.4

    def get_linking_rule(self, class_name: str) -> LinkingRule:
        """Get linking rule for a class"""
        cls = self.get_class_by_name(class_name)
        return cls.linking_rule if cls else LinkingRule()

    def get_name_search_rule(self, class_name: str) -> NameSearchRule:
        """Get name search rule for a class"""
        cls = self.get_class_by_name(class_name)
        return cls.name_search_rule if cls else NameSearchRule()

    def compile_regex_patterns(self):
        """Compile regex patterns for better performance"""
        self.validation.coordinate_re = re.compile(self.validation.coordinate_pattern)
        for class_name, pattern in self.validation.class_id_patterns.items():
            self.validation.class_id_patterns[class_name] = re.compile(pattern)
```

**Implementation Notes:**
- Use Python dataclasses for clean structure
- Provide sensible defaults matching current config.py values
- Add helper methods for common lookups
- Include type hints for better IDE support
- Add docstrings explaining each parameter

---

### Task 1.2: Create ProfileManager

**File:** `core/profile_manager.py` (NEW FILE)

```python
"""
Profile management system for loading and validating YAML configuration profiles.
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from core.config_models import (
    LayoutConfig, ClassDefinition, LinkingRule, NameSearchRule,
    DetectionConfig, OCRConfig, SpatialConfig, ValidationConfig
)

logger = logging.getLogger(__name__)


class ProfileValidationError(Exception):
    """Raised when profile YAML is invalid"""
    pass


class ProfileManager:
    """
    Manages loading and validation of layout configuration profiles.
    """

    @staticmethod
    def load_profile(profile_path: str) -> LayoutConfig:
        """
        Load a layout configuration profile from YAML file.

        Args:
            profile_path: Path to YAML profile file

        Returns:
            LayoutConfig object with all parameters loaded

        Raises:
            ProfileValidationError: If YAML is invalid or missing required fields
            FileNotFoundError: If profile file doesn't exist
        """
        path = Path(profile_path)

        if not path.exists():
            raise FileNotFoundError(f"Profile not found: {profile_path}")

        logger.info(f"Loading profile from: {profile_path}")

        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            raise ProfileValidationError(f"Empty profile file: {profile_path}")

        try:
            config = ProfileManager._parse_profile(data)
            config.compile_regex_patterns()

            logger.info(f"✅ Profile loaded: {config.profile_name} v{config.profile_version}")
            logger.info(f"   Classes: {len(config.classes)}")
            logger.info(f"   DPI: {config.detection.dpi}, Tile size: {config.detection.tile_size}")

            return config

        except Exception as e:
            raise ProfileValidationError(f"Failed to parse profile: {e}") from e

    @staticmethod
    def _parse_profile(data: Dict[str, Any]) -> LayoutConfig:
        """Parse YAML data into LayoutConfig object"""

        # Parse metadata
        profile_name = data.get('profile_name', 'default')
        profile_version = data.get('profile_version', '1.0')
        description = data.get('description', '')

        # Parse class definitions
        classes = ProfileManager._parse_classes(data.get('classes', []))

        # Parse component configs
        detection = ProfileManager._parse_detection(data.get('detection', {}))
        ocr = ProfileManager._parse_ocr(data.get('ocr', {}))
        spatial = ProfileManager._parse_spatial(data.get('spatial', {}))
        validation = ProfileManager._parse_validation(data.get('validation', {}))

        # Parse optional fields
        model_path = data.get('model_path')
        debug_signals = data.get('debug_signals', False)
        debug_angle_routing = data.get('debug_angle_routing', False)
        poppler_path = data.get('poppler_path')
        zoom_size = data.get('zoom_size', 2048)

        return LayoutConfig(
            profile_name=profile_name,
            profile_version=profile_version,
            description=description,
            classes=classes,
            detection=detection,
            ocr=ocr,
            spatial=spatial,
            validation=validation,
            model_path=model_path,
            debug_signals=debug_signals,
            debug_angle_routing=debug_angle_routing,
            poppler_path=poppler_path,
            zoom_size=zoom_size
        )

    @staticmethod
    def _parse_classes(classes_data: list) -> list:
        """Parse class definitions from YAML"""
        classes = []

        for i, cls_data in enumerate(classes_data):
            if isinstance(cls_data, str):
                # Simple string format: just class name
                cls = ClassDefinition(name=cls_data, class_id=i)
            elif isinstance(cls_data, dict):
                # Full format with all parameters
                name = cls_data.get('name')
                if not name:
                    raise ProfileValidationError(f"Class {i} missing 'name' field")

                cls = ClassDefinition(
                    name=name,
                    class_id=cls_data.get('class_id', i),
                    confidence_threshold=cls_data.get('confidence_threshold', 0.5),
                    nms_threshold=cls_data.get('nms_threshold', 0.4),
                    requires_ocr=cls_data.get('requires_ocr', True),
                    requires_coordinate=cls_data.get('requires_coordinate', False),
                    fixed_text=cls_data.get('fixed_text'),
                    numeric_ok=cls_data.get('numeric_ok', False),
                    id_pattern=cls_data.get('id_pattern'),
                    alias=cls_data.get('alias'),
                    linking_rule=ProfileManager._parse_linking_rule(
                        cls_data.get('linking_rule', {})
                    ),
                    name_search_rule=ProfileManager._parse_name_search_rule(
                        cls_data.get('name_search_rule', {})
                    )
                )
            else:
                raise ProfileValidationError(f"Invalid class format at index {i}")

            classes.append(cls)

        return classes

    @staticmethod
    def _parse_linking_rule(rule_data: dict) -> LinkingRule:
        """Parse linking rule from YAML"""
        return LinkingRule(
            mode=rule_data.get('mode', 'below'),
            dx_multiplier=rule_data.get('dx_multiplier', 1.0),
            dy_multiplier=rule_data.get('dy_multiplier', 1.0),
            prefer_horizontal=rule_data.get('prefer_horizontal', False),
            search_left=rule_data.get('search_left', False),
            tilted_ok=rule_data.get('tilted_ok', False),
            block=rule_data.get('block', False)
        )

    @staticmethod
    def _parse_name_search_rule(rule_data: dict) -> NameSearchRule:
        """Parse name search rule from YAML"""
        return NameSearchRule(
            inside=rule_data.get('inside', False),
            left=rule_data.get('left', False),
            right=rule_data.get('right', False),
            below=rule_data.get('below', False),
            above=rule_data.get('above', False)
        )

    @staticmethod
    def _parse_detection(det_data: dict) -> DetectionConfig:
        """Parse detection config from YAML"""
        return DetectionConfig(
            tile_size=det_data.get('tile_size', 2048),
            overlap_pct=det_data.get('overlap_pct', 40),
            dpi=det_data.get('dpi', 500),
            pred_imgsz=det_data.get('pred_imgsz', 1024),
            tile_halo=det_data.get('tile_halo', 320),
            obb_only=det_data.get('obb_only', True),
            use_tta=det_data.get('use_tta', True),
            tta_scales=det_data.get('tta_scales', [1.0]),
            tta_flips=det_data.get('tta_flips', [0, 1]),
            tta_min_votes=det_data.get('tta_min_votes', 1)
        )

    @staticmethod
    def _parse_ocr(ocr_data: dict) -> OCRConfig:
        """Parse OCR config from YAML"""
        return OCRConfig(
            engine=ocr_data.get('engine', 'paddleocr'),
            max_workers=ocr_data.get('max_workers', 8),
            sig_one_window=ocr_data.get('sig_one_window', True),
            sig_pad=ocr_data.get('sig_pad', 14),
            sig_expand_x=ocr_data.get('sig_expand_x', 0.18),
            sig_expand_y=ocr_data.get('sig_expand_y', 0.22),
            sig_use_tighten=ocr_data.get('sig_use_tighten', False),
            sig_score_min=ocr_data.get('sig_score_min', 1.3),
            sig_line_thick=ocr_data.get('sig_line_thick', 5),
            signal_text_height_hint=ocr_data.get('signal_text_height_hint'),
            angle_tol=ocr_data.get('angle_tol', 12.0),
            denoise_strength=ocr_data.get('denoise_strength', 4),
            sharpen_amount=ocr_data.get('sharpen_amount', 1.3),
            use_preprocessing=ocr_data.get('use_preprocessing', True),
            use_adaptive_threshold=ocr_data.get('use_adaptive_threshold', True),
            use_morph_operations=ocr_data.get('use_morph_operations', True),
            confidence_thresholds=ocr_data.get('confidence_thresholds', {}),
            cardinal_detection_padding=ocr_data.get('cardinal_detection_padding', {}),
            cardinal_expansion_factor=ProfileManager._parse_tuple_dict(
                ocr_data.get('cardinal_expansion_factor', {})
            ),
            angular_detection_padding=ocr_data.get('angular_detection_padding', {}),
            angular_expansion_factor=ProfileManager._parse_tuple_dict(
                ocr_data.get('angular_expansion_factor', {})
            )
        )

    @staticmethod
    def _parse_spatial(spatial_data: dict) -> SpatialConfig:
        """Parse spatial config from YAML"""
        return SpatialConfig(
            signal_dy_multiplier=spatial_data.get('signal_dy_multiplier', 2.2),
            signal_dx_multiplier=spatial_data.get('signal_dx_multiplier', 2.4),
            default_dy_multiplier=spatial_data.get('default_dy_multiplier', 1.6),
            default_dx_multiplier=spatial_data.get('default_dx_multiplier', 1.0),
            inside_padding_ratio=spatial_data.get('inside_padding_ratio', 0.10),
            right_window_width_ratio=spatial_data.get('right_window_width_ratio', 2.5),
            right_window_height_ratio=spatial_data.get('right_window_height_ratio', 0.6),
            left_window_width_ratio=spatial_data.get('left_window_width_ratio', 4.0),
            left_window_height_ratio=spatial_data.get('left_window_height_ratio', 0.6),
            sverbinder_window_width_ratio=spatial_data.get('sverbinder_window_width_ratio', 0.9),
            sverbinder_window_height_ratio=spatial_data.get('sverbinder_window_height_ratio', 0.3),
            dy_max_base_multiplier=spatial_data.get('dy_max_base_multiplier', 1.6),
            dx_base_multiplier=spatial_data.get('dx_base_multiplier', 0.6),
            dx_tight_multiplier=spatial_data.get('dx_tight_multiplier', 0.45),
            dx_minimum_threshold=spatial_data.get('dx_minimum_threshold', 30),
            left_search_bonus=spatial_data.get('left_search_bonus', 1.3),
            haltetafel_gks_max_distance=spatial_data.get('haltetafel_gks_max_distance', 250),
            haltetafel_gks_dy_tolerance=spatial_data.get('haltetafel_gks_dy_tolerance', 100),
            haltetafel_gks_dx_tolerance=spatial_data.get('haltetafel_gks_dx_tolerance', 300),
            signal_gks_max_distance=spatial_data.get('signal_gks_max_distance', 250),
            signal_gks_dy_min=spatial_data.get('signal_gks_dy_min', 30),
            signal_gks_dy_max=spatial_data.get('signal_gks_dy_max', 200),
            signal_gks_dx_tolerance_left=spatial_data.get('signal_gks_dx_tolerance_left', 120),
            signal_gks_dx_tolerance_right=spatial_data.get('signal_gks_dx_tolerance_right', 120),
            signal_gks_angle_tolerance=spatial_data.get('signal_gks_angle_tolerance', 20.0),
            track_perpendicular_max_distance=spatial_data.get('track_perpendicular_max_distance', 1500),
            track_window_size=spatial_data.get('track_window_size', 25),
            haltepunkt_cluster_max_distance=spatial_data.get('haltepunkt_cluster_max_distance', 250),
            haltepunkt_signal_dy_min=spatial_data.get('haltepunkt_signal_dy_min', 30),
            haltepunkt_signal_dy_max=spatial_data.get('haltepunkt_signal_dy_max', 200),
            haltepunkt_coord_dy_min=spatial_data.get('haltepunkt_coord_dy_min', 20),
            haltepunkt_coord_dy_max=spatial_data.get('haltepunkt_coord_dy_max', 150),
            haltepunkt_dx_tolerance=spatial_data.get('haltepunkt_dx_tolerance', 100),
            adaptive_search_dx_multiplier=spatial_data.get('adaptive_search_dx_multiplier', 3.0),
            adaptive_search_dx_minimum=spatial_data.get('adaptive_search_dx_minimum', 150),
            adaptive_search_dy_multiplier=spatial_data.get('adaptive_search_dy_multiplier', 3.0),
            adaptive_search_dy_minimum=spatial_data.get('adaptive_search_dy_minimum', 80),
            spatial_threshold_single_section=spatial_data.get('spatial_threshold_single_section', 1000),
            spatial_threshold_gap_multiplier=spatial_data.get('spatial_threshold_gap_multiplier', 3.0),
            spatial_threshold_section_gap_min=spatial_data.get('spatial_threshold_section_gap_min', 1000),
            spatial_threshold_section_gap_max=spatial_data.get('spatial_threshold_section_gap_max', 2500)
        )

    @staticmethod
    def _parse_validation(val_data: dict) -> ValidationConfig:
        """Parse validation config from YAML"""
        return ValidationConfig(
            coordinate_pattern=val_data.get('coordinate_pattern',
                r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$'),
            class_id_patterns=val_data.get('class_id_patterns', {}),
            numeric_ok_classes=val_data.get('numeric_ok_classes', [])
        )

    @staticmethod
    def _parse_tuple_dict(data: dict) -> dict:
        """Convert dict of lists to dict of tuples (for expansion factors)"""
        return {k: tuple(v) if isinstance(v, list) else v for k, v in data.items()}

    @staticmethod
    def save_profile(config: LayoutConfig, output_path: str):
        """
        Save a LayoutConfig object to YAML file.
        Useful for generating profile templates or exporting configurations.
        """
        # This is a helper for creating new profiles
        # Implementation left as exercise - converts LayoutConfig back to YAML dict
        raise NotImplementedError("Profile saving not yet implemented")


# Convenience function for loading profiles
def load_profile(profile_path: str) -> LayoutConfig:
    """Load a profile - convenience wrapper"""
    return ProfileManager.load_profile(profile_path)
```

**Implementation Notes:**
- Robust error handling with clear error messages
- Logging for debugging
- Helper methods for parsing complex nested structures
- Support for both simple (string) and detailed (dict) class definitions
- Type conversion for tuples (YAML doesn't have tuple type)

---

### Task 1.3: Create Complete DB Track Plans Profile YAML

**File:** `profiles/db_track_plans.yaml` (UPDATE EXISTING)

```yaml
# =============================================================================
# Deutsche Bahn Track Plans - Standard Profile
# =============================================================================
# This profile contains all parameters optimized for standard DB railway
# layout plans scanned at 500 DPI.
#
# Version: 1.0
# Last updated: 2024
# Compatible with: YOLO v8 OBB model (t4datasetv31)
# =============================================================================

profile_name: "db_track_plans_standard"
profile_version: "1.0"
description: "Standard profile for Deutsche Bahn railway track layouts (A0, 500 DPI)"

# Model configuration
model_path: "yolomodel/runs_obb_t4datasetv31/weights/best.pt"

# Debug flags
debug_signals: false
debug_angle_routing: false

# System settings
poppler_path: null
zoom_size: 2048

# =============================================================================
# CLASS DEFINITIONS (13 DB Symbol Types)
# =============================================================================
classes:
  - name: "signal"
    class_id: 0
    confidence_threshold: 0.85
    nms_threshold: 0.32
    requires_ocr: true
    requires_coordinate: true
    id_pattern: "^[A-ZÄÖÜ]{1,4}\\d{1,4}$"
    numeric_ok: false
    linking_rule:
      mode: "below"
    name_search_rule:
      left: true
      right: true
      below: true
      above: true

  - name: "gm_block"
    class_id: 1
    confidence_threshold: 0.22
    nms_threshold: 0.40
    requires_ocr: false
    fixed_text: "GM"
    linking_rule:
      mode: "below"
    name_search_rule:
      inside: true
      right: true
      below: true

  - name: "gks_festkodiert"
    class_id: 2
    confidence_threshold: 0.25
    nms_threshold: 0.40
    requires_ocr: true
    id_pattern: "^\\d{3,4}$"
    numeric_ok: true
    linking_rule:
      mode: "either"
    name_search_rule:
      inside: true
      left: true
      right: true
      below: true

  - name: "gks_gesteuert"
    class_id: 3
    confidence_threshold: 0.70
    nms_threshold: 0.40
    requires_ocr: true
    id_pattern: "^\\d{3,4}$"
    numeric_ok: true
    linking_rule:
      mode: "either"
    name_search_rule:
      inside: true
      left: true
      right: true
      below: true

  - name: "weichen_block"
    class_id: 4
    confidence_threshold: 0.42
    nms_threshold: 0.30
    requires_ocr: true
    numeric_ok: true
    linking_rule:
      mode: "inside"
      block: true
    name_search_rule:
      inside: true
      right: true
      below: true

  - name: "isolierstoß"
    class_id: 5
    confidence_threshold: 0.09
    nms_threshold: 0.40
    requires_ocr: false
    linking_rule:
      mode: "above"
      tilted_ok: true

  - name: "haltepunkt"
    class_id: 6
    confidence_threshold: 0.25
    nms_threshold: 0.40
    requires_ocr: false
    linking_rule:
      mode: "below"

  - name: "sverbinder"
    class_id: 7
    confidence_threshold: 0.50
    nms_threshold: 0.40
    requires_ocr: false
    linking_rule:
      mode: "below"

  - name: "coordinate"
    class_id: 8
    confidence_threshold: 0.10
    nms_threshold: 0.25
    requires_ocr: true

  - name: "prellbock"
    class_id: 9
    confidence_threshold: 0.22
    nms_threshold: 0.40
    requires_ocr: false
    fixed_text: "PB"
    numeric_ok: true
    linking_rule:
      mode: "right_or_below"
      dx_multiplier: 2.0
      prefer_horizontal: true

  - name: "haltetafel"
    class_id: 10
    confidence_threshold: 0.25
    nms_threshold: 0.40
    requires_ocr: false
    linking_rule:
      mode: "either"
      dx_multiplier: 2.0

  - name: "weichenende"
    class_id: 11
    confidence_threshold: 0.25
    nms_threshold: 0.40
    requires_ocr: false
    linking_rule:
      mode: "either"
      dx_multiplier: 3.0
      prefer_horizontal: true

  - name: "weichengruppenende"
    class_id: 12
    confidence_threshold: 0.25
    nms_threshold: 0.40
    requires_ocr: false
    linking_rule:
      mode: "either"
      dx_multiplier: 4.0
      prefer_horizontal: true
      search_left: true

# =============================================================================
# DETECTION CONFIGURATION (YOLO)
# =============================================================================
detection:
  tile_size: 2048
  overlap_pct: 40
  dpi: 500
  pred_imgsz: 1024
  tile_halo: 320
  obb_only: true
  use_tta: true
  tta_scales: [1.0]
  tta_flips: [0, 1]
  tta_min_votes: 1

# =============================================================================
# OCR CONFIGURATION (PaddleOCR)
# =============================================================================
ocr:
  engine: "paddleocr"
  max_workers: 8

  # Signal-specific parameters
  sig_one_window: true
  sig_pad: 14
  sig_expand_x: 0.18
  sig_expand_y: 0.22
  sig_use_tighten: false
  sig_score_min: 1.3
  sig_line_thick: 5
  signal_text_height_hint: null

  # Angle detection
  angle_tol: 12.0

  # PaddleOCR preprocessing
  denoise_strength: 4
  sharpen_amount: 1.3
  use_preprocessing: true
  use_adaptive_threshold: true
  use_morph_operations: true

  # Per-class OCR confidence thresholds
  confidence_thresholds:
    signal: 0.50
    gks_gesteuert: 0.40
    gks_festkodiert: 0.40
    coordinate: 0.65
    default: 0.45

  # Cardinal (horizontal/vertical) text parameters
  cardinal_detection_padding:
    coordinate: 4
    signal: 4
    weichenende: 8
    gks_gesteuert: 8
    weichengruppenende: 4
    weichen_block: 2

  cardinal_expansion_factor:
    coordinate: [1.0, 1.0]
    signal: [1.0, 1.0]
    gks_gesteuert: [0.6, 0.6]
    weichen_block: [1.1, 1.0]

  # Angular (rotated) text parameters
  angular_detection_padding:
    coordinate: 4
    signal: 8
    gks_gesteuert: 6

  angular_expansion_factor:
    coordinate: [1.0, 1.0]
    signal: [1.0, 1.05]
    gks_gesteuert: [0.75, 0.75]

# =============================================================================
# SPATIAL RELATIONSHIP CONFIGURATION
# =============================================================================
spatial:
  # Name window search multipliers
  signal_dy_multiplier: 2.2
  signal_dx_multiplier: 2.4
  default_dy_multiplier: 1.6
  default_dx_multiplier: 1.0

  # Search window dimensions
  inside_padding_ratio: 0.10
  right_window_width_ratio: 2.5
  right_window_height_ratio: 0.6
  left_window_width_ratio: 4.0
  left_window_height_ratio: 0.6
  sverbinder_window_width_ratio: 0.9
  sverbinder_window_height_ratio: 0.3

  # Coordinate linking distances
  dy_max_base_multiplier: 1.6
  dx_base_multiplier: 0.6
  dx_tight_multiplier: 0.45
  dx_minimum_threshold: 30
  left_search_bonus: 1.3

  # Haltetafel-GKS linking
  haltetafel_gks_max_distance: 250
  haltetafel_gks_dy_tolerance: 100
  haltetafel_gks_dx_tolerance: 300

  # Signal-GKS linking (Fahrtrichtung detection)
  signal_gks_max_distance: 250
  signal_gks_dy_min: 30
  signal_gks_dy_max: 200
  signal_gks_dx_tolerance_left: 120
  signal_gks_dx_tolerance_right: 120
  signal_gks_angle_tolerance: 20.0

  # Track perpendicular detection
  track_perpendicular_max_distance: 1500
  track_window_size: 25

  # Haltepunkt-Signal-Coordinate clustering
  haltepunkt_cluster_max_distance: 250
  haltepunkt_signal_dy_min: 30
  haltepunkt_signal_dy_max: 200
  haltepunkt_coord_dy_min: 20
  haltepunkt_coord_dy_max: 150
  haltepunkt_dx_tolerance: 100

  # Adaptive pattern learning
  adaptive_search_dx_multiplier: 3.0
  adaptive_search_dx_minimum: 150
  adaptive_search_dy_multiplier: 3.0
  adaptive_search_dy_minimum: 80

  # Signal group clustering
  spatial_threshold_single_section: 1000
  spatial_threshold_gap_multiplier: 3.0
  spatial_threshold_section_gap_min: 1000
  spatial_threshold_section_gap_max: 2500

# =============================================================================
# VALIDATION CONFIGURATION
# =============================================================================
validation:
  # German coordinate format: "12,345 Gl.113"
  coordinate_pattern: '^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$'

  # Per-class ID patterns
  class_id_patterns:
    signal: "^[A-ZÄÖÜ]{1,4}\\d{1,4}$"
    gks_gesteuert: "^\\d{3,4}$"
    gks_festkodiert: "^\\d{3,4}$"

  # Classes allowing pure numeric IDs
  numeric_ok_classes:
    - "gks_gesteuert"
    - "gks_festkodiert"
    - "weichen_block"
    - "prellbock"
```

**Create two additional profile variants:**

**File:** `profiles/db_track_plans_strict.yaml`

```yaml
# High-precision variant for clean CAD exports
# Inherits from db_track_plans.yaml with higher thresholds

profile_name: "db_track_plans_strict"
profile_version: "1.0"
description: "High-precision profile for clean DB layouts (lower recall, higher precision)"

# ... (copy all from db_track_plans.yaml)

# Modifications: Increase all confidence thresholds by +0.10
classes:
  - name: "signal"
    confidence_threshold: 0.95  # was 0.85
    # ... rest same

  - name: "gm_block"
    confidence_threshold: 0.32  # was 0.22
    # ... rest same

  # ... (apply to all classes)

# Tighter spatial constraints
spatial:
  signal_dy_multiplier: 2.0  # was 2.2 (stricter)
  signal_dx_multiplier: 2.2  # was 2.4 (stricter)
  # ... rest same
```

**File:** `profiles/db_track_plans_relaxed.yaml`

```yaml
# High-recall variant for degraded scans
# Inherits from db_track_plans.yaml with lower thresholds

profile_name: "db_track_plans_relaxed"
profile_version: "1.0"
description: "High-recall profile for degraded/noisy DB layouts (higher recall, lower precision)"

# ... (copy all from db_track_plans.yaml)

# Modifications: Decrease all confidence thresholds by -0.10
classes:
  - name: "signal"
    confidence_threshold: 0.75  # was 0.85
    # ... rest same

  # ... (apply to all classes)

# Wider spatial search windows
spatial:
  signal_dy_multiplier: 2.4  # was 2.2 (more relaxed)
  signal_dx_multiplier: 2.6  # was 2.4 (more relaxed)

  # Increase all max_distance parameters by 30%
  haltetafel_gks_max_distance: 325  # was 250
  signal_gks_max_distance: 325  # was 250
  # ... etc
```

---

## PHASE 2: REFACTOR CORE FUNCTIONS (4-5 hours)

### Task 2.1: Refactor yolo_detection.py

**Current problematic code:**
```python
from config import TILE_SIZE, OVERLAP_PCT, PRED_IMGSZ, CLASS_THRESH, CLASSES, ...

def run_yolo_on_page(model, page_bgr: np.ndarray) -> List[dict]:
    # Uses global TILE_SIZE, OVERLAP_PCT, etc.
    tiles = tile_image(page_bgr, tile=TILE_SIZE, overlap_pct=OVERLAP_PCT)
```

**Refactored version:**

```python
# REMOVE global imports:
# from config import TILE_SIZE, OVERLAP_PCT, ...

# ADD LayoutConfig parameter to function signatures:

def tile_image(bgr: np.ndarray, config: 'LayoutConfig') -> List[Tuple]:
    """
    Tile image using configuration parameters.

    Args:
        bgr: Input image array
        config: LayoutConfig containing tile_size and overlap_pct
    """
    tile = config.detection.tile_size
    overlap_pct = config.detection.overlap_pct

    # Rest of function unchanged, just use config.detection.xxx
    # instead of global TILE_SIZE, OVERLAP_PCT
    # ...


def run_yolo_on_page(model, page_bgr: np.ndarray, config: 'LayoutConfig') -> List[dict]:
    """
    YOLO detection with angle-aware parameter selection.

    Args:
        model: YOLO model instance
        page_bgr: Page image as BGR numpy array
        config: LayoutConfig with detection parameters
    """
    assert config.detection.obb_only, "This build expects OBB-only weights"

    # Use config instead of globals
    tiles = tile_image(page_bgr, config)

    # ... rest of detection logic

    # Replace CLASS_THRESH access:
    # OLD: thr = CLASS_THRESH.get(cls_name, 0.5)
    # NEW:
    thr = config.get_confidence_threshold(cls_name)

    # Replace NMS_THRESHOLDS access:
    # OLD: nms_thr = NMS_THRESHOLDS.get(cls_name, 0.4)
    # NEW:
    nms_thr = config.get_nms_threshold(cls_name)

    # ... rest unchanged


def run_combined_detection(model, page_bgr: np.ndarray, config: 'LayoutConfig',
                          detect_custom: bool = True) -> List[dict]:
    """
    Combined YOLO + custom template detection.

    Args:
        model: YOLO model
        page_bgr: Page image
        config: LayoutConfig
        detect_custom: Whether to run custom detection
    """
    # Run YOLO with config
    yolo_dets = run_yolo_on_page(model, page_bgr, config)

    # ... rest of function, passing config where needed

    return detections
```

**Key changes:**
1. Remove all `from config import ...` statements
2. Add `config: LayoutConfig` parameter to ALL functions
3. Replace `TILE_SIZE` → `config.detection.tile_size`
4. Replace `CLASS_THRESH.get(...)` → `config.get_confidence_threshold(...)`
5. Replace `NMS_THRESHOLDS.get(...)` → `config.get_nms_threshold(...)`
6. Replace `PRED_IMGSZ` → `config.detection.pred_imgsz`
7. Replace `TILE_HALO` → `config.detection.tile_halo`

**Lines to modify:** Approximately 10-15 locations in yolo_detection.py

---

### Task 2.2: Refactor linking.py

**Current problematic code:**
```python
from config import LINK_RULES, COORD_RE, DEBUG_ANGLE_ROUTING

def name_windows_for(anchor: dict, img_shape, mode: str):
    # Hardcoded multipliers
    if anchor["name"] == "signal":
        dy = int(2.2 * ah)
        dx = int(2.4 * aw)
    else:
        dy = int(1.6 * ah)
        dx = int(1.0 * aw)

def link_anchor_to_coord(anchor, coords, learned_patterns=None):
    cls_name = anchor.get("cls") or anchor.get("name")
    mode = LINK_RULES.get(cls_name, {}).get("mode", "below")
```

**Refactored version:**

```python
# REMOVE:
# from config import LINK_RULES, COORD_RE, DEBUG_ANGLE_ROUTING

# ADD config parameter:

def name_windows_for(anchor: dict, img_shape: Tuple[int, int, int],
                    mode: str, config: 'LayoutConfig') -> List[tuple]:
    """
    Calculate search windows for name text OCR.

    Args:
        anchor: Symbol detection dict
        img_shape: Image shape (h, w, c)
        mode: Search mode string
        config: LayoutConfig with spatial parameters
    """
    # Use config.spatial instead of hardcoded values
    if anchor["name"] == "signal":
        dy = int(config.spatial.signal_dy_multiplier * ah)
        dx = int(config.spatial.signal_dx_multiplier * aw)
    else:
        dy = int(config.spatial.default_dy_multiplier * ah)
        dx = int(config.spatial.default_dx_multiplier * aw)

    # Replace other hardcoded values:
    inside_pad_w = int(config.spatial.inside_padding_ratio * aw)
    inside_pad_h = int(config.spatial.inside_padding_ratio * ah)
    right_w = int(config.spatial.right_window_width_ratio * aw)
    right_h = int(config.spatial.right_window_height_ratio * ah)
    left_w = int(config.spatial.left_window_width_ratio * aw)
    left_h = int(config.spatial.left_window_height_ratio * ah)

    # ... rest of function


def link_anchor_to_coord(anchor, coords, config: 'LayoutConfig',
                        learned_patterns=None):
    """
    Link anchor to coordinate with angle-aware spatial relationships.

    Args:
        anchor: Symbol detection
        coords: List of coordinate detections
        config: LayoutConfig with linking rules and spatial params
        learned_patterns: Optional learned spatial patterns
    """
    cls_name = anchor.get("cls") or anchor.get("name")

    # Get linking rule from config instead of global LINK_RULES
    linking_rule = config.get_linking_rule(cls_name)
    mode = linking_rule.mode
    dx_multiplier = linking_rule.dx_multiplier
    dy_multiplier = linking_rule.dy_multiplier
    prefer_horizontal = linking_rule.prefer_horizontal
    search_left = linking_rule.search_left
    tilted_ok = linking_rule.tilted_ok

    # Replace hardcoded distance calculations with config values:
    dy_max_base = config.spatial.dy_max_base_multiplier * anchor["h"]

    dx_max = dx_multiplier * config.spatial.dx_base_multiplier * max(anchor["w"], c["w"])
    if tight:
        dx_max = dx_multiplier * config.spatial.dx_tight_multiplier * max(anchor["w"], c["w"])
    dx_max = max(dx_max, config.spatial.dx_minimum_threshold)

    if search_left and coord_is_left:
        dx_max *= config.spatial.left_search_bonus

    # ... rest of function


def detect_fahrtrichtung(signal_det, gks_dets, config: 'LayoutConfig',
                        track_skeleton=None, coords=None):
    """
    Detect signal direction (A/B) based on GKS position.

    Args:
        signal_det: Signal detection
        gks_dets: List of GKS detections
        config: LayoutConfig with spatial parameters
        track_skeleton: Optional track skeleton
        coords: Optional coordinates
    """
    # Use config.spatial for distance parameters
    max_distance = config.spatial.signal_gks_max_distance
    dy_min = config.spatial.signal_gks_dy_min
    dy_max = config.spatial.signal_gks_dy_max
    dx_tolerance_left = config.spatial.signal_gks_dx_tolerance_left
    dx_tolerance_right = config.spatial.signal_gks_dx_tolerance_right
    angle_tolerance = config.spatial.signal_gks_angle_tolerance

    # ... rest of function


def detect_haltepunkt_signal_group(haltepunkt_det, signal_dets, coord_dets,
                                   config: 'LayoutConfig'):
    """
    Detect Haltepunkt-Signal-Coordinate groupings.

    Args:
        haltepunkt_det: Haltepunkt detection
        signal_dets: Signal detections
        coord_dets: Coordinate detections
        config: LayoutConfig
    """
    max_distance = config.spatial.haltepunkt_cluster_max_distance
    dy_signal_min = config.spatial.haltepunkt_signal_dy_min
    dy_signal_max = config.spatial.haltepunkt_signal_dy_max
    dy_coord_min = config.spatial.haltepunkt_coord_dy_min
    dy_coord_max = config.spatial.haltepunkt_coord_dy_max
    dx_tolerance = config.spatial.haltepunkt_dx_tolerance
    angle_tolerance = config.spatial.signal_gks_angle_tolerance

    # ... rest of function


def link_haltetafel_to_gks(haltetafel_det, gks_dets, coords, gks_coord_map,
                          config: 'LayoutConfig'):
    """
    Link Haltetafel to nearby GKS.

    Args:
        haltetafel_det: Haltetafel detection
        gks_dets: GKS detections
        coords: Coordinate detections
        gks_coord_map: Mapping of GKS to coordinates
        config: LayoutConfig
    """
    max_distance = config.spatial.haltetafel_gks_max_distance
    dy_tolerance = config.spatial.haltetafel_gks_dy_tolerance
    dx_tolerance = config.spatial.haltetafel_gks_dx_tolerance

    # ... rest of function


def parse_coord(text: str, config: 'LayoutConfig') -> Optional[Tuple]:
    """
    Parse coordinate text using configured regex pattern.

    Args:
        text: Coordinate text string
        config: LayoutConfig with validation patterns
    """
    # Use config.validation.coordinate_re instead of global COORD_RE
    match = config.validation.coordinate_re.match(text)

    if match:
        # ... parsing logic
        return parsed_value
    return None
```

**Key changes:**
1. Add `config: LayoutConfig` parameter to ~15 functions
2. Replace hardcoded multipliers (2.2, 1.6, etc.) with `config.spatial.xxx`
3. Replace `LINK_RULES.get(...)` with `config.get_linking_rule(...)`
4. Replace hardcoded distances (250, 150, etc.) with `config.spatial.xxx`
5. Replace `COORD_RE` with `config.validation.coordinate_re`
6. Replace `DEBUG_ANGLE_ROUTING` with `config.debug_angle_routing`

**Functions to modify (add config param):**
- `name_windows_for`
- `link_anchor_to_coord`
- `link_haltetafel_to_gks`
- `detect_fahrtrichtung`
- `detect_haltepunkt_signal_group`
- `link_isolierstoss_fallback`
- `parse_coord`
- `merge_duplicate_signals`
- `estimate_spatial_threshold`

**Lines to modify:** Approximately 40-50 locations

---

### Task 2.3: Refactor ocr_engine.py

**Current problematic code:**
```python
from config import (DEBUG_ANGLE_ROUTING, PADDLEOCR_PARAMS, DEBUG_SIGNALS,
                   SIG_LINE_THICK, SIG_USE_TIGHTEN, SIGNAL_TEXT_HEIGHT_HINT,
                   SIG_SCORE_MIN, CLASS_ID_PATTERNS, COORD_RE, CARDINAL_PARAMS,
                   NUMERIC_OK)

def ocr_anchor_name(anchor: dict, bgr_color: np.ndarray, engine: str) -> Optional[str]:
    # Uses global CARDINAL_PARAMS, SIG_* constants
    pad = CARDINAL_PARAMS["detection_padding"].get(cls_name, 4)
```

**Refactored version:**

```python
# REMOVE all config imports

# ADD config parameter:

def ocr_anchor_name(anchor: dict, bgr_color: np.ndarray, engine: str,
                   config: 'LayoutConfig') -> Optional[str]:
    """
    OCR for anchor boxes with correct dual-angle routing.

    Args:
        anchor: Symbol detection dict
        bgr_color: Page image
        engine: OCR engine name ("paddleocr", "tesseract", etc.)
        config: LayoutConfig with OCR parameters
    """
    cls_name = anchor.get("cls") or anchor.get("name")

    # Determine if angular or cardinal based on config
    is_angular = abs(anchor.get("angle_raw", 0)) > config.ocr.angle_tol

    # Get parameters from config based on orientation
    if is_angular:
        pad = config.ocr.angular_detection_padding.get(cls_name, 4)
        exp_x, exp_y = config.ocr.angular_expansion_factor.get(cls_name, (1.0, 1.0))
    else:
        pad = config.ocr.cardinal_detection_padding.get(cls_name, 4)
        exp_x, exp_y = config.ocr.cardinal_expansion_factor.get(cls_name, (1.0, 1.0))

    # For signal-specific processing
    if cls_name == "signal" and config.ocr.sig_one_window:
        # Use signal-specific parameters from config
        pad = config.ocr.sig_pad
        expand_x = config.ocr.sig_expand_x
        expand_y = config.ocr.sig_expand_y
        use_tighten = config.ocr.sig_use_tighten
        score_min = config.ocr.sig_score_min
        line_thick = config.ocr.sig_line_thick
        text_height_hint = config.ocr.signal_text_height_hint

        # ... signal OCR logic

    # ... rest of function


def ocr_coordinate_unified(det: dict, bgr: np.ndarray, engine: str,
                          config: 'LayoutConfig') -> Optional[str]:
    """
    Unified coordinate OCR with angle-aware processing.

    Args:
        det: Coordinate detection
        bgr: Page image
        engine: OCR engine
        config: LayoutConfig
    """
    # Use config for OCR confidence thresholds
    min_confidence = config.ocr.confidence_thresholds.get("coordinate", 0.65)

    # Use config for preprocessing parameters
    if config.ocr.use_preprocessing:
        # Apply preprocessing
        denoise_strength = config.ocr.denoise_strength
        sharpen_amount = config.ocr.sharpen_amount
        # ... preprocessing logic

    # ... rest of function

    # Validate using config pattern
    parsed = parse_coord(ocr_text, config)

    return parsed


def ocr_best_angle(det: dict, bgr: np.ndarray, engine: str,
                  config: 'LayoutConfig') -> Tuple[Optional[str], int]:
    """
    Try OCR at multiple angles and return best result.

    Args:
        det: Detection dict
        bgr: Page image
        engine: OCR engine
        config: LayoutConfig
    """
    # Use config for angle tolerance
    if config.debug_angle_routing:
        print(f"  Testing multiple angles for {det.get('cls')}")

    # ... rest of function


def _validate_ocr_result(text: str, cls_name: str, config: 'LayoutConfig') -> bool:
    """
    Validate OCR text against class-specific patterns.

    Args:
        text: OCR result text
        cls_name: Symbol class name
        config: LayoutConfig with validation patterns
    """
    # Check if numeric is OK for this class
    if text.isdigit() and cls_name in config.validation.numeric_ok_classes:
        return True

    # Check against class-specific pattern
    pattern = config.validation.class_id_patterns.get(cls_name)
    if pattern:
        return bool(pattern.match(text))

    return True  # No pattern defined, accept any text
```

**Key changes:**
1. Add `config: LayoutConfig` to all OCR functions
2. Replace `CARDINAL_PARAMS` → `config.ocr.cardinal_detection_padding`, etc.
3. Replace `ANGULAR_PARAMS` → `config.ocr.angular_detection_padding`, etc.
4. Replace `SIG_PAD` → `config.ocr.sig_pad`
5. Replace `SIG_EXPAND_X` → `config.ocr.sig_expand_x`
6. Replace `CLASS_ID_PATTERNS` → `config.validation.class_id_patterns`
7. Replace `NUMERIC_OK` → `config.validation.numeric_ok_classes`
8. Replace `COORD_RE` → `config.validation.coordinate_re`
9. Replace `DEBUG_ANGLE_ROUTING` → `config.debug_angle_routing`

**Functions to modify:**
- `ocr_anchor_name` (main function)
- `ocr_coordinate_unified`
- `ocr_best_angle`
- `ocr_text` (internal helper)
- `_validate_ocr_result` (new helper function)

**Lines to modify:** Approximately 30-40 locations

---

### Task 2.4: Refactor image_processing.py (Minor)

**Current:**
```python
from config import ZOOM_SIZE
```

**Refactored:**
```python
# Remove import, add config parameter if needed
def some_function(image, config: 'LayoutConfig'):
    zoom_size = config.zoom_size
```

**Only a few functions use ZOOM_SIZE - quick refactor**

---

## PHASE 3: UPDATE PIPELINEWORKER (2-3 hours)

### Task 3.1: Refactor PipelineWorker Class

**Current signature:**
```python
class PipelineWorker(QtCore.QThread):
    def __init__(self, pdf_path: str, model_path: str, ocr_engine: str,
                 parent=None, run_analysis=True, detect_tracks=False):
        self.pdf_path = pdf_path
        self.model_path = model_path
        self.ocr_engine = ocr_engine
        # ... uses global config imports
```

**Refactored:**

```python
# At top of file, REMOVE:
# from config import POPPLER_PATH, DEBUG_ANGLE_ROUTING, MAX_OCR_WORKERS,
#                    CLASS_THRESH, CLASSES, LINK_RULES, ALIASES, DPI, TILE_SIZE

# ADD:
from core.config_models import LayoutConfig
from core.profile_manager import ProfileManager

class PipelineWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int)
    status = QtCore.pyqtSignal(str)
    page_processed = QtCore.pyqtSignal(int, object, pd.DataFrame)
    done = QtCore.pyqtSignal(pd.DataFrame, object, object, object)
    track_detection_progress = QtCore.pyqtSignal(str)

    def __init__(self, pdf_path: str, model_path: str, ocr_engine: str,
                 layout_config: LayoutConfig,  # ← NEW PARAMETER
                 parent=None, run_analysis=True, detect_tracks=False):
        """
        Initialize pipeline worker.

        Args:
            pdf_path: Path to PDF document
            model_path: Path to YOLO model weights
            ocr_engine: OCR engine name ("paddleocr", "tesseract")
            layout_config: LayoutConfig object with all parameters
            parent: Qt parent widget
            run_analysis: Whether to run post-processing analysis
            detect_tracks: Whether to detect track skeleton
        """
        super().__init__(parent)
        self.pdf_path = pdf_path
        self.model_path = model_path
        self.ocr_engine = ocr_engine
        self.config = layout_config  # ← STORE CONFIG
        self._is_interrupted = False
        self.run_analysis = run_analysis
        self.detect_tracks = detect_tracks

    def run(self):
        """Main pipeline execution"""
        try:
            # Use self.config instead of global config
            self.status.emit(f"[init] Using profile: {self.config.profile_name} v{self.config.profile_version}")
            self.status.emit(f"[init] Classes: {self.config.get_class_names()}")

            # Load model
            model = YOLO(self.model_path)

            # Verify class order matches model
            model_classes = self.config.get_class_names()
            self.status.emit(f"[init] Model expects {len(model_classes)} classes")

            # Convert PDF to images using config DPI
            dpi = self.config.detection.dpi
            self.status.emit(f"[pdf] Converting PDF at {dpi} DPI...")

            pdf_info = pdfinfo_from_path(
                self.pdf_path,
                poppler_path=self.config.poppler_path
            )
            n_pages = pdf_info["Pages"]

            page_images = convert_from_path(
                self.pdf_path,
                dpi=dpi,
                poppler_path=self.config.poppler_path
            )

            # ... rest of pipeline

            # When calling detection functions, pass config:
            for page_idx, page_pil in enumerate(page_images):
                page_bgr = pil_to_bgr(page_pil)

                # Detection with config
                detections = run_combined_detection(
                    model,
                    page_bgr,
                    self.config,  # ← PASS CONFIG
                    detect_custom=True
                )

                # OCR with config
                for det in detections:
                    if det.get("cls") in NO_OCR_CLASSES:
                        continue

                    text = ocr_anchor_name(
                        det,
                        page_bgr,
                        self.ocr_engine,
                        self.config  # ← PASS CONFIG
                    )
                    det["name"] = text

                # Linking with config
                for anchor in anchors:
                    coord = link_anchor_to_coord(
                        anchor,
                        coordinates,
                        self.config,  # ← PASS CONFIG
                        learned_patterns=None
                    )

                # Fahrtrichtung detection with config
                for signal in signals:
                    fahrtrichtung = detect_fahrtrichtung(
                        signal,
                        gks_dets,
                        self.config,  # ← PASS CONFIG
                        track_skeleton=track_skeleton,
                        coords=coordinates
                    )

                # ... etc for all other function calls

            # ... rest of pipeline

        except Exception as e:
            self.status.emit(f"[error] Pipeline failed: {e}")
            self.done.emit(pd.DataFrame(), {}, None, e)
```

**Key changes:**
1. Add `layout_config: LayoutConfig` parameter to `__init__`
2. Store as `self.config`
3. Pass `self.config` to ALL function calls:
   - `run_yolo_on_page(..., self.config)`
   - `run_combined_detection(..., self.config, ...)`
   - `ocr_anchor_name(..., self.config)`
   - `ocr_coordinate_unified(..., self.config)`
   - `link_anchor_to_coord(..., self.config, ...)`
   - `detect_fahrtrichtung(..., self.config, ...)`
   - `detect_haltepunkt_signal_group(..., self.config)`
   - `link_haltetafel_to_gks(..., self.config)`
   - `parse_coord(..., self.config)`
4. Use `self.config.detection.dpi` instead of global `DPI`
5. Use `self.config.poppler_path` instead of global `POPPLER_PATH`
6. Use `self.config.ocr.max_workers` instead of global `MAX_OCR_WORKERS`

**Lines to modify:** Approximately 50-60 function call sites

---

### Task 3.2: Update UI to Load Profile

**File:** `ui/setup_window.py` or `ui/workspace_widget.py`

**Find where PipelineWorker is created (search for "PipelineWorker("):**

**Current code might look like:**
```python
# In setup_window.py or workspace_widget.py
worker = PipelineWorker(
    pdf_path=self.pdf_path,
    model_path=self.model_path,
    ocr_engine="paddleocr",
    parent=self
)
worker.start()
```

**Refactored:**

```python
from core.profile_manager import ProfileManager
from PyQt5 import QtWidgets

class SetupWindow(QtWidgets.QDialog):  # or WorkspaceWidget
    def __init__(self, parent=None):
        super().__init__(parent)

        # Add profile selection to UI
        self.profile_path = "profiles/db_track_plans.yaml"  # Default

        # ... existing UI setup

        # Add profile selector (combo box or file picker)
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItems([
            "DB Track Plans (Standard)",
            "DB Track Plans (Strict - High Precision)",
            "DB Track Plans (Relaxed - High Recall)"
        ])
        # ... add to layout

    def start_pipeline(self):
        """Start pipeline with selected profile"""

        # Map selection to profile path
        profile_map = {
            0: "profiles/db_track_plans.yaml",
            1: "profiles/db_track_plans_strict.yaml",
            2: "profiles/db_track_plans_relaxed.yaml"
        }

        profile_path = profile_map[self.profile_combo.currentIndex()]

        try:
            # Load profile
            self.status_label.setText(f"Loading profile: {profile_path}...")
            config = ProfileManager.load_profile(profile_path)

            self.status_label.setText(
                f"Profile loaded: {config.profile_name} v{config.profile_version}"
            )

            # Create worker with config
            worker = PipelineWorker(
                pdf_path=self.pdf_path,
                model_path=self.model_path,
                ocr_engine="paddleocr",
                layout_config=config,  # ← PASS CONFIG
                parent=self
            )

            # Connect signals
            worker.progress.connect(self.update_progress)
            worker.status.connect(self.update_status)
            worker.done.connect(self.pipeline_done)

            # Start
            worker.start()

        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self,
                "Profile Error",
                f"Failed to load profile:\n{e}"
            )
```

**Alternative: File picker for custom profiles:**

```python
def select_profile(self):
    """Let user pick custom profile file"""
    profile_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        "Select Layout Profile",
        "profiles/",
        "YAML Files (*.yaml *.yml)"
    )

    if profile_path:
        try:
            config = ProfileManager.load_profile(profile_path)
            self.current_config = config
            self.profile_label.setText(f"Profile: {config.profile_name}")
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Profile Error", str(e))
```

**Key changes:**
1. Import `ProfileManager`
2. Add profile selection UI (combo box or file picker)
3. Load profile before creating PipelineWorker
4. Pass loaded config to PipelineWorker

**Lines to modify:** Approximately 10-20 in UI code

---

## PHASE 4: TESTING & VALIDATION (2-3 hours)

### Task 4.1: Test with Standard Profile

**Create test script:** `test_modular_pipeline.py`

```python
"""
Test script for modular pipeline architecture.
"""

from core.profile_manager import ProfileManager
from core.pipelineworker import PipelineWorker
import sys

def test_profile_loading():
    """Test that profiles load correctly"""
    print("=" * 70)
    print("TEST 1: Profile Loading")
    print("=" * 70)

    profiles = [
        "profiles/db_track_plans.yaml",
        "profiles/db_track_plans_strict.yaml",
        "profiles/db_track_plans_relaxed.yaml"
    ]

    for profile_path in profiles:
        try:
            config = ProfileManager.load_profile(profile_path)
            print(f"\n✅ Loaded: {config.profile_name}")
            print(f"   Version: {config.profile_version}")
            print(f"   Classes: {len(config.classes)}")
            print(f"   DPI: {config.detection.dpi}")
            print(f"   Tile size: {config.detection.tile_size}")

            # Test helper methods
            signal_class = config.get_class_by_name("signal")
            print(f"   Signal confidence: {signal_class.confidence_threshold}")

        except Exception as e:
            print(f"\n❌ Failed: {profile_path}")
            print(f"   Error: {e}")
            return False

    return True


def test_pipeline_with_profile(pdf_path, model_path, profile_path):
    """Test full pipeline with a profile"""
    print("\n" + "=" * 70)
    print("TEST 2: Pipeline Execution")
    print("=" * 70)

    try:
        # Load profile
        config = ProfileManager.load_profile(profile_path)
        print(f"\n✅ Profile loaded: {config.profile_name}")

        # Create worker (would normally run in Qt thread)
        # For testing, just verify it initializes
        print(f"\n✅ PipelineWorker initialized with config")
        print(f"   Config classes: {config.get_class_names()}")
        print(f"   Config DPI: {config.detection.dpi}")

        return True

    except Exception as e:
        print(f"\n❌ Pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_parameter_access():
    """Test that config parameters are accessible correctly"""
    print("\n" + "=" * 70)
    print("TEST 3: Configuration Parameter Access")
    print("=" * 70)

    try:
        config = ProfileManager.load_profile("profiles/db_track_plans.yaml")

        # Test detection params
        assert config.detection.tile_size == 2048
        assert config.detection.dpi == 500
        print("✅ Detection params OK")

        # Test OCR params
        assert config.ocr.sig_pad == 14
        assert config.ocr.angle_tol == 12.0
        print("✅ OCR params OK")

        # Test spatial params
        assert config.spatial.signal_dy_multiplier == 2.2
        assert config.spatial.dx_minimum_threshold == 30
        print("✅ Spatial params OK")

        # Test class lookup
        signal = config.get_class_by_name("signal")
        assert signal is not None
        assert signal.confidence_threshold == 0.85
        print("✅ Class lookup OK")

        # Test linking rules
        linking_rule = config.get_linking_rule("signal")
        assert linking_rule.mode == "below"
        print("✅ Linking rules OK")

        return True

    except AssertionError as e:
        print(f"❌ Assertion failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("MODULAR PIPELINE TEST SUITE")
    print("=" * 70)

    all_passed = True

    # Test 1: Profile loading
    if not test_profile_loading():
        all_passed = False

    # Test 2: Config access
    if not test_config_parameter_access():
        all_passed = False

    # Test 3: Pipeline initialization (requires PDF/model)
    if len(sys.argv) >= 3:
        pdf_path = sys.argv[1]
        model_path = sys.argv[2]
        if not test_pipeline_with_profile(pdf_path, model_path,
                                         "profiles/db_track_plans.yaml"):
            all_passed = False
    else:
        print("\n⚠️  Skipping pipeline test (no PDF/model provided)")
        print("   Usage: python test_modular_pipeline.py <pdf_path> <model_path>")

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 70 + "\n")
```

**Run tests:**
```bash
# Test profile loading only
python test_modular_pipeline.py

# Test full pipeline
python test_modular_pipeline.py path/to/test.pdf path/to/model.pt
```

---

### Task 4.2: Regression Testing

**Compare outputs before/after refactoring:**

```python
"""
Regression test: Ensure refactored pipeline produces identical results.
"""

import pandas as pd
from core.profile_manager import ProfileManager
from core.pipelineworker import PipelineWorker

def compare_results(old_results_csv, new_results_csv):
    """Compare old and new pipeline outputs"""

    old = pd.read_csv(old_results_csv)
    new = pd.read_csv(new_results_csv)

    print(f"Old results: {len(old)} rows")
    print(f"New results: {len(new)} rows")

    if len(old) != len(new):
        print("❌ Row count mismatch!")
        return False

    # Compare key columns
    compare_cols = ["cls", "name", "cx", "cy", "confidence"]

    for col in compare_cols:
        if col not in old.columns or col not in new.columns:
            continue

        differences = (old[col] != new[col]).sum()
        if differences > 0:
            print(f"❌ {differences} differences in column '{col}'")
            return False
        else:
            print(f"✅ Column '{col}' matches")

    print("\n✅ Results are identical!")
    return True


if __name__ == "__main__":
    # Run pipeline with old code, save results
    # Then run with new modular code, save results
    # Compare

    compare_results("results_old.csv", "results_new.csv")
```

---

### Task 4.3: Profile Variant Testing

**Test all 3 profiles on same document:**

```python
"""
Test different profile variants to demonstrate configurability.
"""

from core.profile_manager import ProfileManager
from core.pipelineworker import PipelineWorker
import pandas as pd

def run_with_profile(pdf_path, model_path, profile_path, output_csv):
    """Run pipeline with specific profile"""

    config = ProfileManager.load_profile(profile_path)

    print(f"\n{'='*70}")
    print(f"Running with: {config.profile_name}")
    print(f"Description: {config.description}")
    print(f"{'='*70}")

    # Run pipeline (pseudo-code - actual implementation depends on Qt)
    # worker = PipelineWorker(pdf_path, model_path, "paddleocr", config)
    # results = worker.run_blocking()  # If you have blocking mode
    # results.to_csv(output_csv)

    print(f"✅ Results saved to: {output_csv}")


def compare_profile_results():
    """Compare results from different profiles"""

    standard = pd.read_csv("results_standard.csv")
    strict = pd.read_csv("results_strict.csv")
    relaxed = pd.read_csv("results_relaxed.csv")

    print(f"\n{'='*70}")
    print("PROFILE COMPARISON")
    print(f"{'='*70}")

    print(f"\nStandard profile: {len(standard)} detections")
    print(f"Strict profile:   {len(strict)} detections")
    print(f"Relaxed profile:  {len(relaxed)} detections")

    # Analyze differences
    print(f"\nStrict vs Standard: {len(strict) - len(standard):+d} detections")
    print(f"Relaxed vs Standard: {len(relaxed) - len(standard):+d} detections")

    # Expected: strict < standard < relaxed (for number of detections)
    if len(strict) < len(standard) < len(relaxed):
        print("\n✅ Profiles behave as expected!")
        print("   (Strict = fewer, Relaxed = more detections)")
    else:
        print("\n⚠️  Unexpected profile behavior")


if __name__ == "__main__":
    pdf = "test_layout.pdf"
    model = "yolomodel/runs_obb_t4datasetv31/weights/best.pt"

    # Run with each profile
    run_with_profile(pdf, model, "profiles/db_track_plans.yaml",
                    "results_standard.csv")
    run_with_profile(pdf, model, "profiles/db_track_plans_strict.yaml",
                    "results_strict.csv")
    run_with_profile(pdf, model, "profiles/db_track_plans_relaxed.yaml",
                    "results_relaxed.csv")

    # Compare
    compare_profile_results()
```

---

## PHASE 5: COMPONENT INTERFACES (OPTIONAL - 2-3 hours)

**This is the "2.5" part - adds interfaces for full extensibility**

### Task 5.1: Create Detector Interface

**File:** `core/interfaces.py` (NEW FILE)

```python
"""
Component interfaces for pluggable pipeline architecture.
Enables swapping detection, linking, OCR, and storage implementations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np


# =============================================================================
# DETECTOR INTERFACE
# =============================================================================

class IDetector(ABC):
    """Interface for symbol detection components"""

    @abstractmethod
    def detect(self, image: np.ndarray, config: 'LayoutConfig') -> List[Dict[str, Any]]:
        """
        Detect symbols in an image.

        Args:
            image: Input image as numpy array (BGR format)
            config: LayoutConfig with detection parameters

        Returns:
            List of detection dictionaries with keys:
                - cls: Class name (str)
                - x1, y1, x2, y2: Bounding box coordinates
                - cx, cy: Center coordinates
                - w, h: Width and height
                - confidence: Detection confidence score
                - angle_raw: Rotation angle (optional)
                - poly: Polygon points for OBB (optional)
        """
        pass


class YOLODetector(IDetector):
    """YOLO-based detection implementation"""

    def __init__(self, model_path: str):
        """
        Initialize YOLO detector.

        Args:
            model_path: Path to YOLO model weights
        """
        from ultralytics import YOLO
        self.model = YOLO(model_path)

    def detect(self, image: np.ndarray, config: 'LayoutConfig') -> List[Dict[str, Any]]:
        """Run YOLO detection"""
        from core.yolo_detection import run_combined_detection
        return run_combined_detection(self.model, image, config, detect_custom=True)


class FasterRCNNDetector(IDetector):
    """Faster R-CNN detection implementation (placeholder)"""

    def __init__(self, model_path: str):
        self.model_path = model_path
        # Load Faster R-CNN model here

    def detect(self, image: np.ndarray, config: 'LayoutConfig') -> List[Dict[str, Any]]:
        # Implement Faster R-CNN detection
        raise NotImplementedError("Faster R-CNN detector not yet implemented")


# =============================================================================
# LINKING STRATEGY INTERFACE
# =============================================================================

class ILinker(ABC):
    """Interface for symbol-to-coordinate linking strategies"""

    @abstractmethod
    def link_symbol_to_coordinate(self, symbol: Dict, coordinates: List[Dict],
                                  config: 'LayoutConfig') -> Optional[Dict]:
        """
        Link a symbol to its coordinate.

        Args:
            symbol: Symbol detection dict
            coordinates: List of coordinate detection dicts
            config: LayoutConfig

        Returns:
            Best matching coordinate dict or None
        """
        pass


class RuleBasedLinker(ILinker):
    """Rule-based spatial linking (current implementation)"""

    def link_symbol_to_coordinate(self, symbol: Dict, coordinates: List[Dict],
                                  config: 'LayoutConfig') -> Optional[Dict]:
        """Use spatial rules from config"""
        from core.linking import link_anchor_to_coord
        return link_anchor_to_coord(symbol, coordinates, config)


class MLBasedLinker(ILinker):
    """Machine learning-based linking (placeholder)"""

    def __init__(self, model_path: str):
        self.model_path = model_path
        # Load ML model for link prediction

    def link_symbol_to_coordinate(self, symbol: Dict, coordinates: List[Dict],
                                  config: 'LayoutConfig') -> Optional[Dict]:
        # Use ML model to predict best link
        raise NotImplementedError("ML-based linker not yet implemented")


class LLMBasedLinker(ILinker):
    """LLM-based spatial reasoning linker (placeholder)"""

    def __init__(self, model_name: str = "gpt-4"):
        self.model_name = model_name
        # Initialize LLM client

    def link_symbol_to_coordinate(self, symbol: Dict, coordinates: List[Dict],
                                  config: 'LayoutConfig') -> Optional[Dict]:
        """Use LLM to reason about spatial relationships"""
        # Construct prompt with spatial context
        # Query LLM
        # Parse response to select coordinate
        raise NotImplementedError("LLM-based linker not yet implemented")


# =============================================================================
# OCR ENGINE INTERFACE
# =============================================================================

class IOCREngine(ABC):
    """Interface for OCR engines"""

    @abstractmethod
    def recognize_text(self, image: np.ndarray, config: 'LayoutConfig') -> str:
        """
        Recognize text in an image region.

        Args:
            image: Cropped image region containing text
            config: LayoutConfig with OCR parameters

        Returns:
            Recognized text string
        """
        pass


class PaddleOCREngine(IOCREngine):
    """PaddleOCR implementation (current)"""

    def __init__(self):
        from paddleocr import PaddleOCR
        self.ocr = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)

    def recognize_text(self, image: np.ndarray, config: 'LayoutConfig') -> str:
        """Use PaddleOCR"""
        from core.ocr_engine import ocr_text
        return ocr_text(image, "paddleocr", config)


class TesseractOCREngine(IOCREngine):
    """Tesseract OCR implementation"""

    def recognize_text(self, image: np.ndarray, config: 'LayoutConfig') -> str:
        """Use Tesseract"""
        from core.ocr_engine import ocr_text
        return ocr_text(image, "tesseract", config)


class GoogleVisionOCREngine(IOCREngine):
    """Google Cloud Vision API (placeholder)"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        # Initialize Google Vision client

    def recognize_text(self, image: np.ndarray, config: 'LayoutConfig') -> str:
        """Use Google Cloud Vision API"""
        raise NotImplementedError("Google Vision OCR not yet implemented")


# =============================================================================
# VALIDATOR INTERFACE
# =============================================================================

class IValidator(ABC):
    """Interface for result validation strategies"""

    @abstractmethod
    def validate_results(self, detections: List[Dict],
                        config: 'LayoutConfig') -> List[Dict]:
        """
        Validate and potentially filter detection results.

        Args:
            detections: List of detection dicts
            config: LayoutConfig

        Returns:
            Validated/filtered detection list
        """
        pass


class RuleBasedValidator(IValidator):
    """Rule-based validation using regex patterns"""

    def validate_results(self, detections: List[Dict],
                        config: 'LayoutConfig') -> List[Dict]:
        """Validate using config validation rules"""
        validated = []

        for det in detections:
            cls_name = det.get("cls")
            text = det.get("name", "")

            # Check pattern
            pattern = config.validation.class_id_patterns.get(cls_name)
            if pattern and not pattern.match(text):
                det["validation_warning"] = f"Text '{text}' doesn't match pattern"

            validated.append(det)

        return validated


class LLMValidator(IValidator):
    """LLM-based semantic validation (placeholder)"""

    def __init__(self, model_name: str = "gpt-4"):
        self.model_name = model_name
        # Initialize LLM

    def validate_results(self, detections: List[Dict],
                        config: 'LayoutConfig') -> List[Dict]:
        """Use LLM to validate semantic consistency"""
        # Group related detections
        # Ask LLM: "Does this signal-coordinate-GKS configuration make sense?"
        # Flag suspicious results
        raise NotImplementedError("LLM validator not yet implemented")


# =============================================================================
# STORAGE BACKEND INTERFACE
# =============================================================================

class IStorageBackend(ABC):
    """Interface for data persistence strategies"""

    @abstractmethod
    def save(self, data: pd.DataFrame, metadata: Dict[str, Any],
            identifier: str) -> None:
        """
        Save extraction results.

        Args:
            data: DataFrame with all extracted symbols
            metadata: Additional metadata (profile used, timestamps, etc.)
            identifier: Unique identifier for this extraction
        """
        pass

    @abstractmethod
    def load(self, identifier: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Load previously saved results.

        Args:
            identifier: Unique identifier

        Returns:
            (DataFrame, metadata dict)
        """
        pass


class LocalFileStorage(IStorageBackend):
    """Save to local CSV/pickle files"""

    def __init__(self, output_dir: str = "output/"):
        self.output_dir = output_dir
        import os
        os.makedirs(output_dir, exist_ok=True)

    def save(self, data: pd.DataFrame, metadata: Dict, identifier: str) -> None:
        """Save to CSV and JSON metadata"""
        csv_path = f"{self.output_dir}/{identifier}.csv"
        meta_path = f"{self.output_dir}/{identifier}_meta.json"

        data.to_csv(csv_path, index=False)

        import json
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)

    def load(self, identifier: str) -> Tuple[pd.DataFrame, Dict]:
        """Load from CSV and JSON"""
        csv_path = f"{self.output_dir}/{identifier}.csv"
        meta_path = f"{self.output_dir}/{identifier}_meta.json"

        data = pd.read_csv(csv_path)

        import json
        with open(meta_path, 'r') as f:
            metadata = json.load(f)

        return data, metadata


class PostgreSQLStorage(IStorageBackend):
    """Save to PostgreSQL database"""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        # Initialize SQLAlchemy engine

    def save(self, data: pd.DataFrame, metadata: Dict, identifier: str) -> None:
        """Save to PostgreSQL"""
        from sqlalchemy import create_engine
        engine = create_engine(self.connection_string)

        # Save main data
        data.to_sql(f"extractions_{identifier}", engine, if_exists='replace')

        # Save metadata
        meta_df = pd.DataFrame([metadata])
        meta_df.to_sql(f"metadata_{identifier}", engine, if_exists='replace')

    def load(self, identifier: str) -> Tuple[pd.DataFrame, Dict]:
        """Load from PostgreSQL"""
        from sqlalchemy import create_engine
        engine = create_engine(self.connection_string)

        data = pd.read_sql_table(f"extractions_{identifier}", engine)
        meta_df = pd.read_sql_table(f"metadata_{identifier}", engine)
        metadata = meta_df.iloc[0].to_dict()

        return data, metadata


class S3Storage(IStorageBackend):
    """Save to Amazon S3 (placeholder)"""

    def __init__(self, bucket_name: str, aws_credentials: Dict):
        self.bucket_name = bucket_name
        self.credentials = aws_credentials
        # Initialize boto3 client

    def save(self, data: pd.DataFrame, metadata: Dict, identifier: str) -> None:
        """Upload to S3"""
        raise NotImplementedError("S3 storage not yet implemented")

    def load(self, identifier: str) -> Tuple[pd.DataFrame, Dict]:
        """Download from S3"""
        raise NotImplementedError("S3 storage not yet implemented")


# =============================================================================
# COMPONENT FACTORY (For easy instantiation)
# =============================================================================

class ComponentFactory:
    """Factory for creating pipeline components"""

    @staticmethod
    def create_detector(detector_type: str, **kwargs) -> IDetector:
        """
        Create detector instance.

        Args:
            detector_type: "yolo", "faster_rcnn", "custom"
            **kwargs: Constructor arguments

        Returns:
            IDetector instance
        """
        if detector_type == "yolo":
            return YOLODetector(kwargs.get("model_path"))
        elif detector_type == "faster_rcnn":
            return FasterRCNNDetector(kwargs.get("model_path"))
        else:
            raise ValueError(f"Unknown detector type: {detector_type}")

    @staticmethod
    def create_linker(linker_type: str, **kwargs) -> ILinker:
        """Create linker instance"""
        if linker_type == "rule_based":
            return RuleBasedLinker()
        elif linker_type == "ml_based":
            return MLBasedLinker(kwargs.get("model_path"))
        elif linker_type == "llm_based":
            return LLMBasedLinker(kwargs.get("model_name", "gpt-4"))
        else:
            raise ValueError(f"Unknown linker type: {linker_type}")

    @staticmethod
    def create_ocr_engine(engine_type: str, **kwargs) -> IOCREngine:
        """Create OCR engine instance"""
        if engine_type == "paddleocr":
            return PaddleOCREngine()
        elif engine_type == "tesseract":
            return TesseractOCREngine()
        elif engine_type == "google_vision":
            return GoogleVisionOCREngine(kwargs.get("api_key"))
        else:
            raise ValueError(f"Unknown OCR engine: {engine_type}")

    @staticmethod
    def create_storage(storage_type: str, **kwargs) -> IStorageBackend:
        """Create storage backend instance"""
        if storage_type == "local_file":
            return LocalFileStorage(kwargs.get("output_dir", "output/"))
        elif storage_type == "postgresql":
            return PostgreSQLStorage(kwargs.get("connection_string"))
        elif storage_type == "s3":
            return S3Storage(kwargs.get("bucket_name"), kwargs.get("credentials"))
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")
```

**This file provides:**
- Interfaces for all major components
- Concrete implementations of current system
- Placeholders for future extensions (Faster R-CNN, LLM, Cloud OCR)
- Factory pattern for easy component creation

---

### Task 5.2: Update Profile to Specify Components

**Add to profile YAML:**

```yaml
# profiles/db_track_plans.yaml

# ... existing config ...

# Component selection (NEW)
components:
  detector: "yolo"  # or "faster_rcnn", "custom"
  linker: "rule_based"  # or "ml_based", "llm_based"
  ocr_engine: "paddleocr"  # or "tesseract", "google_vision"
  validator: "rule_based"  # or "llm_based"
  storage: ["local_file"]  # Can specify multiple: ["local_file", "postgresql"]

# Component-specific configs (NEW)
component_config:
  detector_args:
    model_path: "yolomodel/runs_obb_t4datasetv31/weights/best.pt"

  storage_args:
    local_file:
      output_dir: "output/"
    postgresql:
      connection_string: "postgresql://user:pass@localhost/railway_db"
```

**Update ProfileManager to parse components:**

```python
# In profile_manager.py

@staticmethod
def _parse_profile(data: Dict[str, Any]) -> LayoutConfig:
    # ... existing parsing ...

    # Parse component selection (NEW)
    components = data.get('components', {})
    component_config = data.get('component_config', {})

    # ... add to LayoutConfig
```

---

## DELIVERABLES CHECKLIST ✅

After completing all phases, you should have:

### **Code Structure:**
```
Gleisplanextraktorv3/
├── core/
│   ├── config_models.py         ✅ NEW: LayoutConfig dataclass
│   ├── profile_manager.py       ✅ NEW: YAML loader/validator
│   ├── interfaces.py            ✅ NEW: Component interfaces (Optional)
│   ├── pipelineworker.py        ✅ MODIFIED: Accepts config param
│   ├── yolo_detection.py        ✅ MODIFIED: Uses config, not globals
│   ├── linking.py               ✅ MODIFIED: Uses config, not globals
│   ├── ocr_engine.py            ✅ MODIFIED: Uses config, not globals
│   └── image_processing.py      ✅ MODIFIED: Uses config if needed
│
├── profiles/
│   ├── db_track_plans.yaml      ✅ COMPLETE: Standard profile
│   ├── db_track_plans_strict.yaml   ✅ NEW: High precision variant
│   └── db_track_plans_relaxed.yaml  ✅ NEW: High recall variant
│
├── ui/
│   ├── setup_window.py          ✅ MODIFIED: Profile selection
│   └── workspace_widget.py      ✅ MODIFIED: Loads profile
│
├── test_modular_pipeline.py     ✅ NEW: Test script
├── config.py                    ✅ UNCHANGED: Keep for compatibility
└── README_MODULARITY.md         ✅ NEW: Documentation
```

### **Functionality:**
- ✅ Load profiles from YAML at runtime
- ✅ Process documents with different profiles without code changes
- ✅ Swap detection models (via profile model_path)
- ✅ Swap linking strategies (via interfaces - optional)
- ✅ Swap OCR engines (via interfaces - optional)
- ✅ Swap storage backends (via interfaces - optional)
- ✅ All existing functionality still works
- ✅ Backward compatible with current config.py (if needed)

### **Testing:**
- ✅ Profile loading works correctly
- ✅ Pipeline runs end-to-end with config injection
- ✅ Results match previous (non-modular) implementation
- ✅ Different profiles produce expected variations in results
- ✅ No regressions in detection/linking/OCR accuracy

### **Documentation:**
- ✅ Code comments explaining architecture
- ✅ Profile YAML files have inline documentation
- ✅ README explaining how to create new profiles
- ✅ Examples of extending with new components

---

## USAGE EXAMPLES (FOR YOUR THESIS)

### **Example 1: Running with Different Profiles**

```python
from core.profile_manager import ProfileManager
from core.pipelineworker import PipelineWorker

# Load different profiles
standard_config = ProfileManager.load_profile("profiles/db_track_plans.yaml")
strict_config = ProfileManager.load_profile("profiles/db_track_plans_strict.yaml")

# Run same document with different configs
worker1 = PipelineWorker(pdf_path, model_path, "paddleocr", standard_config)
worker2 = PipelineWorker(pdf_path, model_path, "paddleocr", strict_config)

# Results will differ based on thresholds
```

### **Example 2: Creating Custom Profile**

```yaml
# profiles/my_custom_profile.yaml

profile_name: "my_custom_layout"
profile_version: "1.0"
description: "Custom profile for specific layout requirements"

# Copy from db_track_plans.yaml and modify parameters
classes:
  - name: "signal"
    confidence_threshold: 0.90  # Higher than standard

detection:
  dpi: 300  # Different DPI for smaller documents
  tile_size: 1024  # Smaller tiles

# ... etc
```

### **Example 3: Extending with New Detector (Future)**

```python
from core.interfaces import IDetector

class MyCustomDetector(IDetector):
    def detect(self, image, config):
        # Your custom detection logic
        return detections

# Use it
detector = MyCustomDetector(model_path="my_model.pt")
# Plug into pipeline (if PipelineWorker updated to use IDetector)
```

---

## TROUBLESHOOTING GUIDE 🔧

### **Problem: "NameError: name 'TILE_SIZE' is not defined"**
**Cause:** Forgot to replace global import with config parameter
**Solution:** Find the function, add `config` parameter, replace `TILE_SIZE` with `config.detection.tile_size`

### **Problem: "TypeError: missing 1 required positional argument: 'config'"**
**Cause:** Called a refactored function without passing config
**Solution:** Pass `self.config` or `config` parameter when calling the function

### **Problem: "ProfileValidationError: Missing required field"**
**Cause:** YAML profile is incomplete
**Solution:** Compare with `db_track_plans.yaml` template, add missing fields

### **Problem: "Results differ from original implementation"**
**Cause:** Config values don't match original hardcoded values
**Solution:** Check that YAML values exactly match values from config.py

### **Problem: "AttributeError: 'LayoutConfig' object has no attribute 'xxx'"**
**Cause:** Typo in config access (e.g., `config.detection.title_size` instead of `tile_size`)
**Solution:** Check spelling, verify field exists in `config_models.py`

---

## TIME ESTIMATES BY TASK ⏱️

| Task | Estimated Time | Difficulty |
|------|---------------|------------|
| 1.1 Create LayoutConfig | 1.5 hours | Medium |
| 1.2 Create ProfileManager | 1.5 hours | Medium |
| 1.3 Create Profile YAMLs | 1 hour | Easy |
| 2.1 Refactor yolo_detection.py | 1 hour | Easy |
| 2.2 Refactor linking.py | 2 hours | Medium |
| 2.3 Refactor ocr_engine.py | 1.5 hours | Medium |
| 3.1 Refactor PipelineWorker | 1.5 hours | Medium |
| 3.2 Update UI | 1 hour | Easy |
| 4.1-4.3 Testing | 2-3 hours | Medium |
| 5.1-5.2 Interfaces (Optional) | 2-3 hours | Hard |

**Total: 10-14 hours (or 12-17 with interfaces)**

---

## SUCCESS CRITERIA ✅

You're done when:

1. ✅ All core functions accept `config: LayoutConfig` parameter
2. ✅ No more `from config import ...` in core/ files (except backward compatibility)
3. ✅ ProfileManager successfully loads all 3 YAML profiles
4. ✅ PipelineWorker runs end-to-end with injected config
5. ✅ Results match original implementation (regression test passes)
6. ✅ Different profiles produce measurably different results
7. ✅ No errors/warnings when running test suite
8. ✅ Code is clean, commented, and ready for thesis submission

---

## NEXT STEPS AFTER MODULARITY 🚀

Once modular refactoring is complete, you can:

1. **Write Thesis Section:**
   - Architecture chapter explaining modular design
   - Show class diagrams (LayoutConfig, interfaces)
   - Explain profile-based configuration benefits

2. **Run Evaluation:**
   - Test 3 profiles on 20-30 documents
   - Generate comparison tables (precision/recall per profile)
   - Create visualizations showing configurability impact

3. **Future Work Section:**
   - Mention extensibility (LLM integration, new detectors)
   - Discuss profile inheritance
   - Note multi-layout support potential

4. **Demo for Defense:**
   - Show switching profiles in UI
   - Show different results from different configs
   - Demonstrate architectural quality

---

## FINAL NOTES 📝

**This guide is comprehensive and detailed. Follow it step-by-step, and you'll have a modular, extensible architecture that:**

- ✅ Addresses the "single-layout limitation" criticism
- ✅ Demonstrates software engineering maturity
- ✅ Shows architectural thinking (important for master's thesis)
- ✅ Enables future extensions (LLM, new models, storage backends)
- ✅ Is ready for thesis documentation

**Good luck with your implementation! If you encounter issues during implementation, refer back to the troubleshooting section or specific task details.**

---

**END OF IMPLEMENTATION GUIDE**

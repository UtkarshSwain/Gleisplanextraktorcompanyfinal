"""
Configuration models for layout-specific parameters.
This module defines the data structures for profile-based configuration.

Replaces the centralized config.py global variables with injectable
configuration objects loaded from YAML profiles.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any, Set
import re


@dataclass
class DetectionConfig:
    """YOLO detection parameters"""
    # Tiling Strategy
    tile_size: int = 2048
    overlap_pct: int = 40
    dpi: int = 500
    pred_imgsz: int = 1024
    tile_halo: int = 320
    obb_only: bool = True

    # Legend Strip Exclusion
    exclude_legend_strip: bool = True
    legend_strip_width_percent: int = 12
    legend_strip_max_pixels: int = 4200

    # Title block margins (for track detection)
    title_block_margin_height: int = 100  # when legend strip is excluded
    title_block_margin_height_default: int = 25  # when legend strip is NOT excluded
    title_block_margin_width_default: int = 8  # when legend strip is NOT excluded

    # 4-sided cropping (more flexible than legend strip only)
    crop_top: int = 0
    crop_bottom: int = 0
    crop_left: int = 0
    crop_right: int = 0

    # Test-Time Augmentation
    use_tta: bool = True
    tta_scales: List[float] = field(default_factory=lambda: [1.0])
    tta_flips: List[int] = field(default_factory=lambda: [0, 1])
    tta_min_votes: int = 1

    # Uncertain detection thresholds
    uncertain_thresh_multiplier: float = 0.5
    min_uncertain_thresh_default: float = 0.10
    min_uncertain_thresh: Dict[str, float] = field(default_factory=lambda: {
        "coordinate": 0.01,
        "isolierstoß": 0.01,
    })

    # Antwerp-specific detection features
    global_conf_threshold: float = 0.01  # YOLO confidence cutoff (Antwerp uses 0.05)
    use_ink_filter: bool = False  # Skip tiles with low ink content
    ink_threshold: float = 0.012  # 1.2% minimum ink ratio
    use_centroid_halo: bool = False  # Filter edge detections by centroid
    halo_ratio: float = 0.12  # 12% from each tile edge
    halo_conf_boost: float = 0.50  # Min conf to keep edge detections
    filter_contained_boxes: bool = False  # Remove boxes contained in larger boxes
    contained_box_threshold: float = 0.80  # Containment ratio threshold
    prefer_larger_nms: bool = False  # NMS prefers larger boxes over smaller

    # Batch inference parameters (disabled by default - needs testing)
    batch_size: int = 1  # 1 = sequential mode (safe), >1 = batch mode
    yolo_workers: int = 0  # DataLoader workers (0 = disabled)

    # Polygon handling (Antwerp fix for missing/rotated boxes)
    use_native_obb_polygons: bool = False  # True = use YOLO's native xyxyxyxy, False = reconstruct from xywhr

    # Halo expansion for inference (default True = current behavior for Wien)
    use_halo_expansion: bool = True  # True = expand tiles with halo, False = exact tiles like Colab

    # Automatic landscape orientation (Antwerp feature)
    auto_landscape: bool = False  # True = rotate portrait pages to landscape before cropping
    landscape_rotation_direction: str = "cw"  # "cw" = clockwise (90° right), "ccw" = counterclockwise (90° left)


@dataclass
class OCRConfig:
    """OCR engine parameters"""
    engine: str = "paddleocr"
    max_workers: int = 8
    tesseract_path: Optional[str] = None

    # Signal-specific parameters
    sig_one_window: bool = True
    sig_pad: int = 14
    sig_expand_x: float = 0.18
    sig_expand_y: float = 0.22
    sig_use_tighten: bool = False
    sig_score_min: float = 1.3
    sig_line_thick: int = 5
    signal_text_height_hint: Optional[int] = None

    # Left bias expansion
    left_bias_expansion_classes: Set[str] = field(default_factory=lambda: {"signal"})
    left_bias_ratio_h: float = 0.8

    # Angle-aware parameters
    angle_tol: float = 12.0  # Degrees threshold for cardinal vs angular

    # PaddleOCR-specific preprocessing
    denoise_strength: int = 4
    sharpen_amount: float = 1.3
    use_preprocessing: bool = True
    use_adaptive_threshold: bool = True
    use_morph_operations: bool = True

    # Simple OCR mode (for high-DPI scans like Antwerp 800 DPI)
    # When True: skips heavy preprocessing, just crops and runs PaddleOCR directly
    use_simple_ocr: bool = False

    # Simple OCR padding per class (pixels around crop box)
    # Used when use_simple_ocr=True
    simple_ocr_padding: Dict[str, int] = field(default_factory=lambda: {
        "coordinate": 3,
        "text_id": 4,
        "default": 4
    })

    # Per-class OCR confidence thresholds
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
        "haltetafel": 4,
        "prellbock": 4,
        "gks_gesteuert": 8,
        "gks_festkodiert": 8,
        "weichengruppenende": 4,
        "weichen_block": 2,
    })

    cardinal_expansion_factor: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        "coordinate": (1.0, 1.0),
        "signal": (1.0, 1.0),
        "gks_gesteuert": (0.6, 0.6),
        "gks_festkodiert": (0.6, 0.6),
        "weichen_block": (1.1, 1.0),
    })

    # Angular (rotated) text parameters
    angular_detection_padding: Dict[str, int] = field(default_factory=lambda: {
        "coordinate": 4,
        "signal": 8,
        "weichenende": 4,
        "haltetafel": 4,
        "prellbock": 4,
        "gks_gesteuert": 6,
        "gks_festkodiert": 6,
    })

    angular_expansion_factor: Dict[str, Tuple[float, float]] = field(default_factory=lambda: {
        "coordinate": (1.0, 1.0),
        "signal": (1.0, 1.05),
        "gks_gesteuert": (0.75, 0.75),
        "gks_festkodiert": (0.75, 0.75),
    })


@dataclass
class SpatialConfig:
    """Spatial relationship parameters for linking"""
    # Track detection control
    enable_track_detection: bool = True  # Default: enabled for Wien

    # Name window search multipliers (used in name_windows_for)
    signal_dy_multiplier: float = 2.2
    signal_dx_multiplier: float = 2.4
    default_dy_multiplier: float = 1.6
    default_dx_multiplier: float = 1.0
    signal_extended_dx_ratio: float = 5.0

    # Progressive search steps for text_id linking (Antwerp-specific)
    text_id_search_steps: List[float] = field(default_factory=lambda: [1.0, 1.5, 2.0, 2.5, 3.0, 3.5])

    # Coordinate linking for Antwerp Phase 1 elements
    coord_search_steps: List[float] = field(default_factory=lambda: [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0])
    coord_dx_steps: List[int] = field(default_factory=lambda: [5, 10, 15, 20, 25, 30])  # Progressive dx tolerance steps
    coord_dy_min: int = 30             # Minimum vertical distance
    coord_dy_base: int = 300           # Base vertical distance (multiplied by steps) - max 2100px at step 7.0
    terminal_bond_pair_dy_max: int = 300  # Max vertical distance to consider terminal_bonds as paired
    coord_phase1_classes: List[str] = field(default_factory=lambda: ["s_bond", "short_bond", "terminal_bond", "insulation_joint", "spie_loop"])

    # Search window dimensions
    inside_padding_ratio: float = 0.10
    right_window_width_ratio: float = 2.5
    right_window_height_ratio: float = 0.6
    left_window_width_ratio: float = 4.0
    left_window_height_ratio: float = 0.6
    sverbinder_window_width_ratio: float = 0.9
    sverbinder_window_height_ratio: float = 0.3

    # Coordinate linking distances (used in link_anchor_to_coord)
    dy_max_base_multiplier: float = 1.6
    dx_base_multiplier: float = 0.6
    dx_tight_multiplier: float = 0.45
    dx_minimum_threshold: int = 30
    left_search_bonus: float = 1.3

    # Haltetafel-GKS linking
    haltetafel_gks_max_distance: int = 250
    haltetafel_gks_dy_tolerance: int = 100
    haltetafel_gks_dx_tolerance: int = 300

    # Signal-GKS linking (Fahrtrichtung detection)
    signal_gks_max_distance: int = 250
    signal_gks_dy_min: int = 30
    signal_gks_dy_max: int = 200
    signal_gks_dx_tolerance_left: int = 120
    signal_gks_dx_tolerance_right: int = 120
    signal_gks_angle_tolerance: float = 20.0

    # Signal-GKS linking - Relaxed mode (fallback)
    signal_gks_relaxed_dx_tolerance: int = 200
    signal_gks_relaxed_dy_max: int = 600
    signal_gks_relaxed_angle_tolerance: float = 25.0

    # Signal-GKS linking - Nearest mode (last resort)
    signal_gks_nearest_max_distance: int = 800
    signal_gks_nearest_angle_tolerance: float = 30.0

    # Track perpendicular detection
    track_perpendicular_max_distance: int = 1500
    track_window_size: int = 25
    track_search_radius: int = 500
    track_sample_distance: int = 200

    # Haltepunkt-Signal-Coordinate clustering
    haltepunkt_cluster_max_distance: int = 250
    haltepunkt_signal_dy_min: int = 30
    haltepunkt_signal_dy_max: int = 200
    haltepunkt_coord_dy_min: int = 20
    haltepunkt_coord_dy_max: int = 150
    haltepunkt_dx_tolerance: int = 100
    haltepunkt_angle_tolerance: float = 20.0  # Max angle difference for angular haltepunkt

    # Isolierstoß fallback linking
    isolierstoss_fallback_radius: int = 300

    # Adaptive pattern learning
    adaptive_search_dx_multiplier: float = 3.0
    adaptive_search_dx_minimum: int = 150
    adaptive_search_dy_multiplier: float = 3.0
    adaptive_search_dy_minimum: int = 80

    # Signal group clustering
    spatial_threshold_single_section: int = 1000
    spatial_threshold_gap_multiplier: float = 3.0
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
    fallback_dy_steps: List[float] = field(default_factory=list)


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
    id_pattern: Optional[str] = None  # Regex pattern for validation
    linking_rule: LinkingRule = field(default_factory=LinkingRule)
    name_search_rule: NameSearchRule = field(default_factory=NameSearchRule)
    alias: Optional[str] = None  # Alternative name


@dataclass
class ValidationConfig:
    """Validation patterns and rules"""
    # Coordinate regex pattern (German format: "12,345 Gl.113")
    coordinate_pattern: str = r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$'

    # Per-class ID validation patterns
    class_id_patterns: Dict[str, str] = field(default_factory=lambda: {
        "signal": r"^[A-ZÄÖÜ]{1,4}\d{1,4}$",
        "gks_gesteuert": r"^\d{3,4}$",
        "gks_festkodiert": r"^\d{3,4}$",
    })

    # Classes that allow pure numeric IDs
    numeric_ok_classes: List[str] = field(default_factory=lambda: [
        "gks_gesteuert", "gks_festkodiert", "weichen_block", "prellbock"
    ])

    # Decimal separator for coordinates (German uses comma, others use dot)
    # Input separator is what appears in the scanned document
    # Output separator is what to normalize to (usually dot for float parsing)
    decimal_separator_input: str = ","  # Character used in scanned documents
    decimal_separator_output: str = "."  # Character to normalize to

    # Compiled regex patterns (populated by compile_regex_patterns)
    coordinate_re: Any = field(default=None, repr=False)
    compiled_class_patterns: Dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class ComponentConfig:
    """Configuration for component selection (interfaces)"""
    detector: str = "yolo"
    linker: str = "rule_based"
    ocr_engine: str = "paddleocr"
    validator: str = "rule_based"
    storage: List[str] = field(default_factory=lambda: ["local_file"])

    # Component-specific arguments
    detector_args: Dict[str, Any] = field(default_factory=dict)
    linker_args: Dict[str, Any] = field(default_factory=dict)
    ocr_engine_args: Dict[str, Any] = field(default_factory=dict)
    validator_args: Dict[str, Any] = field(default_factory=dict)
    storage_args: Dict[str, Dict[str, Any]] = field(default_factory=dict)


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

    # Aliases for class names
    aliases: Dict[str, str] = field(default_factory=dict)

    # Class remapping
    class_remap: Dict[str, str] = field(default_factory=dict)

    # Component configurations
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    spatial: SpatialConfig = field(default_factory=SpatialConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    components: ComponentConfig = field(default_factory=ComponentConfig)

    # Model path (can be layout-specific)
    model_path: Optional[str] = None

    # Debug flags
    debug_signals: bool = False
    debug_angle_routing: bool = False
    debug_ocr: bool = False
    debug_linking: bool = False
    debug_track: bool = False
    debug_custom_symbols: bool = False
    debug_yolo: bool = False
    debug_ui_bbox: bool = False
    debug_comparison: bool = False
    debug_crops: bool = False  # Save OCR crops to debug_crops/ folder

    # System settings
    poppler_path: Optional[str] = None
    zoom_size: int = 2048

    # Internal: class name to ClassDefinition mapping
    _class_by_name: Dict[str, ClassDefinition] = field(default_factory=dict, repr=False)
    _class_by_id: Dict[int, ClassDefinition] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        """Build internal lookup tables"""
        self._rebuild_class_lookups()

    def _rebuild_class_lookups(self):
        """Rebuild internal class lookup dictionaries"""
        self._class_by_name = {}
        self._class_by_id = {}
        for cls in self.classes:
            self._class_by_name[cls.name] = cls
            self._class_by_id[cls.class_id] = cls
            if cls.alias:
                self._class_by_name[cls.alias] = cls

    def get_class_by_name(self, name: str) -> Optional[ClassDefinition]:
        """Get class definition by name, handling aliases"""
        # Check direct lookup first
        if name in self._class_by_name:
            return self._class_by_name[name]

        # Check aliases
        aliased = self.aliases.get(name, name)
        if aliased in self._class_by_name:
            return self._class_by_name[aliased]

        return None

    def get_class_by_id(self, class_id: int) -> Optional[ClassDefinition]:
        """Get class definition by ID"""
        return self._class_by_id.get(class_id)

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

    def canon_name(self, name: str) -> str:
        """Get canonical class name after aliasing and remapping"""
        # Apply alias
        aliased = self.aliases.get(name, name)
        # Apply remap
        return self.class_remap.get(aliased, aliased)

    def compile_regex_patterns(self):
        """Compile regex patterns for better performance"""
        # Compile coordinate pattern
        self.validation.coordinate_re = re.compile(self.validation.coordinate_pattern)

        # Compile class ID patterns
        self.validation.compiled_class_patterns = {}
        for class_name, pattern in self.validation.class_id_patterns.items():
            if isinstance(pattern, str):
                self.validation.compiled_class_patterns[class_name] = re.compile(pattern)
            else:
                self.validation.compiled_class_patterns[class_name] = pattern

    def get_min_uncertain_threshold(self, class_name: str) -> float:
        """Get minimum uncertain threshold for a class"""
        return self.detection.min_uncertain_thresh.get(
            class_name,
            self.detection.min_uncertain_thresh_default
        )

    def is_debug_enabled(self, category: str) -> bool:
        """Check if debug is enabled for a category"""
        flag_name = f"debug_{category.lower()}"
        return getattr(self, flag_name, False)

# core/symbol_detector.py
"""
New Symbol Detection System - No Retraining Required!

This module provides:
1. Automatic detection of unknown/new symbols in track layouts
2. Template-based detection for user-defined symbols
3. Contour matching for rotation-invariant detection
4. Integration with existing YOLO pipeline

For Masterarbeit: Demonstrates system adaptability without retraining.
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import json
import math
import pickle
import io
from collections import defaultdict
import threading
from utils.helpers import debug_print

# Database availability flag (checked once at module load) - with thread safety
_DB_AVAILABLE = None
_DB_AVAILABLE_LOCK = threading.Lock()

def _check_db_available() -> bool:
    """Check if database is available (cached, thread-safe)."""
    global _DB_AVAILABLE
    if _DB_AVAILABLE is None:
        with _DB_AVAILABLE_LOCK:
            # Double-check after acquiring lock
            if _DB_AVAILABLE is None:
                try:
                    from database_sqlite import is_db_available
                    _DB_AVAILABLE = is_db_available()
                except Exception as e:
                    debug_print('custom_symbols', f"Database not available: {e}")
                    _DB_AVAILABLE = False
    return _DB_AVAILABLE


@dataclass
class SymbolDefinition:
    """Definition of a user-defined symbol."""
    name: str
    templates: List[np.ndarray] = field(default_factory=list)
    contours: List[np.ndarray] = field(default_factory=list)
    hu_moments: List[np.ndarray] = field(default_factory=list)

    # Detection parameters
    detection_method: str = "auto"  # "template", "contour", "circle", "auto"
    similarity_threshold: float = 0.75
    min_size: Tuple[int, int] = (15, 15)
    max_size: Tuple[int, int] = (200, 200)

    # OCR parameters
    has_text: bool = False
    text_position: List[str] = field(default_factory=lambda: ["below"])  # List of: "above", "below", "left", "right", "inside", diagonals
    text_pattern: Optional[str] = None  # Regex for validation
    text_region_offset: Optional[Dict] = None  # {"dx": int, "dy": int, "width": int, "height": int}

    # Linking parameters
    links_to_coordinate: bool = False
    coordinate_position: List[str] = field(default_factory=lambda: ["below"])  # List of positions to search
    max_link_distance: int = 150

    # Metadata
    color: Tuple[int, int, int] = (255, 0, 255)  # Magenta for new symbols
    example_count: int = 0

    def to_dict(self) -> dict:
        """Convert to serializable dict (without numpy arrays)."""
        return {
            "name": self.name,
            "detection_method": self.detection_method,
            "similarity_threshold": self.similarity_threshold,
            "min_size": self.min_size,
            "max_size": self.max_size,
            "has_text": self.has_text,
            "text_position": self.text_position,
            "text_pattern": self.text_pattern,
            "text_region_offset": self.text_region_offset,
            "links_to_coordinate": self.links_to_coordinate,
            "coordinate_position": self.coordinate_position,
            "max_link_distance": self.max_link_distance,
            "color": self.color,
            "example_count": self.example_count,
        }


@dataclass
class DetectionResult:
    """Result of symbol detection."""
    class_name: str
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    angle: float = 0.0
    method: str = "template"  # "template", "contour", "circle", "yolo"
    is_new_symbol: bool = True  # True if from this module, False if from YOLO

    # For linking
    center: Tuple[float, float] = (0, 0)

    def to_dict(self) -> dict:
        return {
            "name": self.class_name,
            "cls": -1,  # Custom symbols don't have YOLO class ID
            "x1": self.bbox[0],
            "y1": self.bbox[1],
            "x2": self.bbox[2],
            "y2": self.bbox[3],
            "w": self.bbox[2] - self.bbox[0],
            "h": self.bbox[3] - self.bbox[1],
            "cx": self.center[0],
            "cy": self.center[1],
            "conf": self.confidence,
            "angle": self.angle,
            "detection_method": self.method,
            "is_new_symbol": self.is_new_symbol,
            "is_custom_symbol": self.is_new_symbol,  # Alias for consistency
        }


class UnknownSymbolDetector:
    """
    Automatically detects potential unknown symbols in track layouts.

    Finds objects that:
    1. Look like symbols (geometric shapes, high contrast)
    2. Were NOT detected by YOLO
    3. Appear multiple times (not random noise)
    """

    def __init__(self):
        self.min_symbol_size = 15
        self.max_symbol_size = 200
        self.min_occurrences = 2  # Must appear at least twice

    def find_unknown_symbols(
        self,
        image: np.ndarray,
        yolo_detections: List[dict],
        mask_detected: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Find potential unknown symbols not detected by YOLO.

        Args:
            image: BGR image
            yolo_detections: List of YOLO detection dicts with x1,y1,x2,y2
            mask_detected: If True, mask out YOLO detections before searching

        Returns:
            List of potential unknown symbol regions with clustering
        """
        # Convert to grayscale
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()

        # Create mask of YOLO detections (areas to ignore)
        yolo_mask = np.zeros(gray.shape, dtype=np.uint8)
        for det in yolo_detections:
            x1, y1 = int(det.get("x1", 0)), int(det.get("y1", 0))
            x2, y2 = int(det.get("x2", 0)), int(det.get("y2", 0))
            # Expand slightly to avoid edge artifacts
            padding = 10
            x1, y1 = max(0, x1 - padding), max(0, y1 - padding)
            x2, y2 = min(gray.shape[1], x2 + padding), min(gray.shape[0], y2 + padding)
            yolo_mask[y1:y2, x1:x2] = 255

        # Find all contours in image
        # Use adaptive threshold for varying lighting
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 5
        )

        # Mask out YOLO detections
        if mask_detected:
            binary = cv2.bitwise_and(binary, cv2.bitwise_not(yolo_mask))

        # Morphological operations to clean up
        kernel = np.ones((3, 3), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours by size and shape
        potential_symbols = []
        for contour in contours:
            # Get bounding box
            x, y, w, h = cv2.boundingRect(contour)

            # Size filter
            if w < self.min_symbol_size or h < self.min_symbol_size:
                continue
            if w > self.max_symbol_size or h > self.max_symbol_size:
                continue

            # Aspect ratio filter (symbols are usually roughly square-ish)
            aspect = max(w, h) / min(w, h) if min(w, h) > 0 else 999
            if aspect > 5:  # Too elongated, probably text or line
                continue

            # Area filter (not too small)
            area = cv2.contourArea(contour)
            if area < 100:
                continue

            # Compute Hu moments for shape matching
            moments = cv2.moments(contour)
            hu = cv2.HuMoments(moments).flatten()

            # Crop region
            padding = 5
            x1 = max(0, x - padding)
            y1 = max(0, y - padding)
            x2 = min(gray.shape[1], x + w + padding)
            y2 = min(gray.shape[0], y + h + padding)
            crop = gray[y1:y2, x1:x2]

            potential_symbols.append({
                "bbox": (x1, y1, x2, y2),
                "contour": contour,
                "hu_moments": hu,
                "crop": crop,
                "area": area,
                "center": (x + w/2, y + h/2),
            })

        # Cluster similar symbols
        clusters = self._cluster_similar_symbols(potential_symbols)

        # Filter to clusters with multiple occurrences
        significant_clusters = [
            c for c in clusters if len(c["instances"]) >= self.min_occurrences
        ]

        return significant_clusters

    def _cluster_similar_symbols(
        self,
        symbols: List[Dict],
        similarity_threshold: float = 0.3,
    ) -> List[Dict]:
        """Cluster symbols by shape similarity using Hu moments."""
        if not symbols:
            return []

        clusters = []
        used = set()

        for i, sym1 in enumerate(symbols):
            if i in used:
                continue

            cluster = {
                "representative": sym1,
                "instances": [sym1],
                "hu_moments": sym1["hu_moments"],
            }
            used.add(i)

            for j, sym2 in enumerate(symbols):
                if j in used:
                    continue

                # Compare Hu moments
                similarity = cv2.matchShapes(
                    sym1["contour"], sym2["contour"], cv2.CONTOURS_MATCH_I1, 0
                )

                if similarity < similarity_threshold:
                    cluster["instances"].append(sym2)
                    used.add(j)

            clusters.append(cluster)

        return clusters


class NewSymbolDetector:
    """
    Detects user-defined symbols using multiple methods:
    1. Template matching (with rotation)
    2. Contour/shape matching (rotation invariant)
    3. Circle detection (for circular symbols)
    """

    def __init__(self, config_path: Optional[str] = None):
        self.symbols: Dict[str, SymbolDefinition] = {}
        self.config_path = Path(config_path) if config_path else Path("custom_symbols.json")
        self._load_config()

    def _load_config(self):
        """Load saved symbol definitions - from PostgreSQL first, then local files."""
        loaded_from_db = False

        # Try PostgreSQL first
        if _check_db_available():
            try:
                from database_sqlite import get_all_custom_symbols
                db_symbols = get_all_custom_symbols()

                for sym_data in db_symbols:
                    name = sym_data['symbol_name']
                    cfg = sym_data['config']
                    templates_blob = sym_data['templates_data']

                    # Remove 'name' from cfg to avoid duplicate argument
                    cfg_copy = {k: v for k, v in cfg.items() if k != 'name'}
                    symbol = SymbolDefinition(name=name, **cfg_copy)

                    # Deserialize templates from blob
                    if templates_blob:
                        arrays = pickle.loads(templates_blob)
                        symbol.templates = arrays.get('templates', [])
                        symbol.contours = arrays.get('contours', [])
                        symbol.hu_moments = arrays.get('hu_moments', [])

                    self.symbols[name] = symbol
                    debug_print('custom_symbols',f"Loaded symbol '{name}' from database with {len(symbol.templates)} templates")

                if db_symbols:
                    loaded_from_db = True
                    debug_print('custom_symbols',f"Loaded {len(self.symbols)} custom symbols from PostgreSQL")
            except Exception as e:
                print(f"Could not load from database: {e}")

        # Fall back to local files if DB not available or empty
        if not loaded_from_db and self.config_path.exists():
            self._load_config_from_files()

    def _load_config_from_files(self):
        """Load symbol definitions from local files (fallback)."""
        try:
            with open(self.config_path, 'r') as f:
                data = json.load(f)

            # Create templates directory path
            templates_dir = self.config_path.parent / "custom_symbol_templates"

            for name, cfg in data.items():
                # Skip if already loaded from DB
                if name in self.symbols:
                    continue

                # Remove 'name' from cfg to avoid duplicate argument
                cfg_copy = {k: v for k, v in cfg.items() if k != 'name'}
                symbol = SymbolDefinition(name=name, **cfg_copy)

                # Load templates from .npy files
                symbol_dir = templates_dir / name
                if symbol_dir.exists():
                    # Load templates
                    for i in range(cfg.get('example_count', 0)):
                        template_path = symbol_dir / f"template_{i}.npy"
                        if template_path.exists():
                            template = np.load(str(template_path))
                            symbol.templates.append(template)

                        contour_path = symbol_dir / f"contour_{i}.npy"
                        if contour_path.exists():
                            contour = np.load(str(contour_path))
                            symbol.contours.append(contour)

                        hu_path = symbol_dir / f"hu_moments_{i}.npy"
                        if hu_path.exists():
                            hu = np.load(str(hu_path))
                            symbol.hu_moments.append(hu)

                self.symbols[name] = symbol
                debug_print('custom_symbols',f"Loaded symbol '{name}' from files with {len(symbol.templates)} templates")

            debug_print('custom_symbols',f"Loaded {len(self.symbols)} custom symbol definitions from local files")
        except Exception as e:
            print(f"Could not load symbol config from files: {e}")

    def _save_config(self):
        """Save symbol definitions to PostgreSQL and local files (for offline fallback)."""
        # Save to PostgreSQL if available
        if _check_db_available():
            self._save_config_to_db()

        # Always save to local files as fallback
        self._save_config_to_files()

    def _save_config_to_db(self):
        """Save symbol definitions to PostgreSQL database."""
        try:
            from database_sqlite import save_custom_symbol

            for name, symbol in self.symbols.items():
                # Serialize numpy arrays to bytes
                arrays_data = {
                    'templates': symbol.templates,
                    'contours': symbol.contours,
                    'hu_moments': symbol.hu_moments,
                }
                templates_blob = pickle.dumps(arrays_data)

                # Save to database
                save_custom_symbol(
                    symbol_name=name,
                    config=symbol.to_dict(),
                    templates_data=templates_blob
                )

            debug_print('custom_symbols',f"Saved {len(self.symbols)} symbols to PostgreSQL database")
        except Exception as e:
            print(f"Could not save to database: {e}")
            print(f"[WARNING] Database save failed: {e}")

    def _save_config_to_files(self):
        """Save symbol definitions to local files (fallback)."""
        # Save JSON metadata
        data = {name: sym.to_dict() for name, sym in self.symbols.items()}
        with open(self.config_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"[DEBUG] Saved JSON to: {self.config_path.absolute()}")

        # Create templates directory
        templates_dir = self.config_path.parent / "custom_symbol_templates"
        templates_dir.mkdir(parents=True, exist_ok=True)
        print(f"[DEBUG] Templates directory: {templates_dir.absolute()}")

        # Save numpy arrays for each symbol
        for name, symbol in self.symbols.items():
            symbol_dir = templates_dir / name
            symbol_dir.mkdir(parents=True, exist_ok=True)
            print(f"[DEBUG] Symbol directory: {symbol_dir.absolute()}")

            # Save templates
            for i, template in enumerate(symbol.templates):
                template_path = symbol_dir / f"template_{i}.npy"
                np.save(str(template_path), template)
                print(f"[DEBUG] Saved template: {template_path.absolute()}")

            # Save contours
            for i, contour in enumerate(symbol.contours):
                np.save(str(symbol_dir / f"contour_{i}.npy"), contour)

            # Save Hu moments
            for i, hu in enumerate(symbol.hu_moments):
                np.save(str(symbol_dir / f"hu_moments_{i}.npy"), hu)

            debug_print('custom_symbols',f"Saved {len(symbol.templates)} templates for symbol '{name}' to local files")

    def add_symbol_from_examples(
        self,
        name: str,
        example_crops: List[np.ndarray],
        has_text: bool = False,
        text_position: Optional[List[str]] = None,
        text_region_offset: Optional[Dict] = None,
        links_to_coordinate: bool = False,
        coordinate_position: Optional[List[str]] = None,
        similarity_threshold: float = 0.75,
        max_link_distance: int = 150,
    ) -> SymbolDefinition:
        """
        Add a new symbol definition from example crops.

        Args:
            name: Symbol name
            example_crops: List of cropped images containing the symbol
            has_text: Does this symbol have associated text?
            text_position: List of positions where text can be found (e.g., ["below", "right"])
            text_region_offset: Precise text region {"dx", "dy", "width", "height"}
            links_to_coordinate: Should this link to coordinates?
            coordinate_position: List of positions where coordinates can be found
            similarity_threshold: How similar must matches be? (0-1)
            max_link_distance: Maximum pixel distance for coordinate linking

        Returns:
            Created SymbolDefinition
        """
        # Handle default values and backward compatibility with string arguments
        if text_position is None:
            text_position = ["below"]
        elif isinstance(text_position, str):
            text_position = [text_position]

        if coordinate_position is None:
            coordinate_position = ["below"]
        elif isinstance(coordinate_position, str):
            coordinate_position = [coordinate_position]

        symbol = SymbolDefinition(
            name=name,
            has_text=has_text,
            text_position=text_position,
            text_region_offset=text_region_offset,
            links_to_coordinate=links_to_coordinate,
            coordinate_position=coordinate_position,
            similarity_threshold=similarity_threshold,
            max_link_distance=max_link_distance,
            example_count=len(example_crops),
        )

        for crop in example_crops:
            # Convert to grayscale if needed
            if len(crop.shape) == 3:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            else:
                gray = crop

            # Store template
            symbol.templates.append(gray)

            # Extract contour
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if contours:
                # Take largest contour
                largest = max(contours, key=cv2.contourArea)
                symbol.contours.append(largest)

                # Compute Hu moments
                moments = cv2.moments(largest)
                hu = cv2.HuMoments(moments).flatten()
                symbol.hu_moments.append(hu)

        # Auto-detect best method
        symbol.detection_method = self._choose_detection_method(symbol)

        self.symbols[name] = symbol
        self._save_config()

        debug_print('custom_symbols',f"Added new symbol '{name}' with {len(example_crops)} examples, method: {symbol.detection_method}")

        return symbol

    def _choose_detection_method(self, symbol: SymbolDefinition) -> str:
        """Automatically choose best detection method based on symbol characteristics."""
        if not symbol.contours:
            return "template"

        contour = symbol.contours[0]

        # Check if circular
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if perimeter > 0:
            circularity = 4 * math.pi * area / (perimeter * perimeter)
            if circularity > 0.7:
                return "circle"

        # Check complexity
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approx) < 8:
            return "contour"  # Simple shape, contour matching works well

        return "template"  # Complex shape, use template

    def detect_symbol(
        self,
        image: np.ndarray,
        symbol_name: str,
    ) -> List[DetectionResult]:
        """
        Detect a specific symbol in the image.

        Args:
            image: BGR or grayscale image
            symbol_name: Name of symbol to detect

        Returns:
            List of DetectionResult
        """
        if symbol_name not in self.symbols:
            print(f"Symbol '{symbol_name}' not defined")
            return []

        symbol = self.symbols[symbol_name]

        if symbol.detection_method == "circle":
            return self._detect_circle_symbol(image, symbol)
        elif symbol.detection_method == "contour":
            return self._detect_contour_symbol(image, symbol)
        else:
            return self._detect_template_symbol(image, symbol)

    def detect_all_symbols(self, image: np.ndarray) -> List[DetectionResult]:
        """Detect all defined custom symbols in the image."""
        all_detections = []

        for name in self.symbols:
            detections = self.detect_symbol(image, name)
            all_detections.extend(detections)

        # NMS across all custom symbols
        all_detections = self._nms(all_detections, iou_threshold=0.5)

        return all_detections

    def _detect_template_symbol(
        self,
        image: np.ndarray,
        symbol: SymbolDefinition,
    ) -> List[DetectionResult]:
        """Template matching with rotation (optimized for speed)."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        detections = []

        # OPTIMIZATION: Only use first template and fewer rotations
        # This reduces time from ~1 hour to ~5-10 minutes
        templates_to_use = symbol.templates[:1]  # Use only first template
        rotation_step = 45  # Every 45° instead of 15° (8 vs 24 rotations)

        for template in templates_to_use:
            # Try rotations: 0°, 45°, 90°, 135°, 180°, 225°, 270°, 315°
            for angle in range(0, 360, rotation_step):
                # Rotate template
                h, w = template.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)

                # Calculate new bounds
                cos = abs(M[0, 0])
                sin = abs(M[0, 1])
                new_w = int(h * sin + w * cos)
                new_h = int(h * cos + w * sin)
                M[0, 2] += (new_w - w) / 2
                M[1, 2] += (new_h - h) / 2

                rotated = cv2.warpAffine(template, M, (new_w, new_h),
                                         borderValue=255)  # White background

                # Skip if template is larger than image
                if rotated.shape[0] > gray.shape[0] or rotated.shape[1] > gray.shape[1]:
                    continue

                # Template matching
                result = cv2.matchTemplate(gray, rotated, cv2.TM_CCOEFF_NORMED)

                # Find matches above threshold
                locations = np.where(result >= symbol.similarity_threshold)

                for pt in zip(*locations[::-1]):
                    x1, y1 = pt
                    x2, y2 = x1 + rotated.shape[1], y1 + rotated.shape[0]
                    conf = result[pt[1], pt[0]]

                    detections.append(DetectionResult(
                        class_name=symbol.name,
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        confidence=float(conf),
                        angle=float(angle),
                        method="template",
                        center=((x1 + x2) / 2, (y1 + y2) / 2),
                    ))

        # NMS + Center-based duplicate removal
        # Use higher min_distance (150px) to aggressively remove duplicates from different rotation angles
        # Also use lower IoU threshold (0.2) to catch more overlapping boxes
        detections = self._nms(detections, iou_threshold=0.2)
        detections = self._remove_center_duplicates(detections, min_distance=150)
        return detections

    def _remove_center_duplicates(
        self,
        detections: List[DetectionResult],
        min_distance: float = 50,
    ) -> List[DetectionResult]:
        """Remove detections whose centers are too close or overlap (keep highest confidence)."""
        if not detections:
            return []

        # Sort by confidence (highest first)
        detections = sorted(detections, key=lambda d: d.confidence, reverse=True)

        kept = []
        for det in detections:
            is_duplicate = False
            det_cx, det_cy = det.center
            det_x1, det_y1, det_x2, det_y2 = det.bbox

            for kept_det in kept:
                kept_cx, kept_cy = kept_det.center
                kept_x1, kept_y1, kept_x2, kept_y2 = kept_det.bbox

                # Check 0: Angle-aware - different orientations (0° vs 180°) are not duplicates
                # This handles cases where same symbol appears in opposite orientations
                if hasattr(det, 'angle') and hasattr(kept_det, 'angle'):
                    angle_diff = abs(det.angle - kept_det.angle) % 360
                    angle_diff = min(angle_diff, 360 - angle_diff)
                    if angle_diff > 90:
                        # Significantly different orientations - not duplicates
                        continue

                # Check 1: Center distance
                dx = det_cx - kept_cx
                dy = det_cy - kept_cy
                distance = (dx**2 + dy**2) ** 0.5

                if distance < min_distance:
                    is_duplicate = True
                    break

                # Check 2: Is this detection's center inside a kept detection's bbox?
                if kept_x1 <= det_cx <= kept_x2 and kept_y1 <= det_cy <= kept_y2:
                    is_duplicate = True
                    break

                # Check 3: Is a kept detection's center inside this detection's bbox?
                if det_x1 <= kept_cx <= det_x2 and det_y1 <= kept_cy <= det_y2:
                    is_duplicate = True
                    break

                # Check 4: If confidence is much lower (>0.1 diff) and within reasonable distance
                # This catches cases where template matches at wrong angles with lower confidence
                conf_diff = kept_det.confidence - det.confidence
                if conf_diff > 0.1 and distance < 500:
                    is_duplicate = True
                    break

            if not is_duplicate:
                kept.append(det)

        return kept

    def _detect_contour_symbol(
        self,
        image: np.ndarray,
        symbol: SymbolDefinition,
    ) -> List[DetectionResult]:
        """Contour/shape matching (rotation invariant)."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Threshold
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Find contours
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []

        for contour in contours:
            # Size filter
            x, y, w, h = cv2.boundingRect(contour)
            if w < symbol.min_size[0] or h < symbol.min_size[1]:
                continue
            if w > symbol.max_size[0] or h > symbol.max_size[1]:
                continue

            # Compare with symbol contours
            best_similarity = float('inf')
            for sym_contour in symbol.contours:
                similarity = cv2.matchShapes(
                    sym_contour, contour, cv2.CONTOURS_MATCH_I1, 0
                )
                best_similarity = min(best_similarity, similarity)

            # Convert similarity (lower is better) to confidence (higher is better)
            # matchShapes returns 0 for identical, higher for different
            confidence = max(0, 1 - best_similarity * 5)  # Scale factor

            if confidence >= symbol.similarity_threshold:
                detections.append(DetectionResult(
                    class_name=symbol.name,
                    bbox=(x, y, x + w, y + h),
                    confidence=float(confidence),
                    angle=0.0,  # Rotation invariant
                    method="contour",
                    center=(x + w/2, y + h/2),
                ))

        return self._nms(detections, iou_threshold=0.3)

    def _detect_circle_symbol(
        self,
        image: np.ndarray,
        symbol: SymbolDefinition,
    ) -> List[DetectionResult]:
        """Circle detection using Hough transform."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Estimate circle radius from templates
        radii = []
        for template in symbol.templates:
            h, w = template.shape[:2]
            radii.append(min(h, w) // 2)

        if not radii:
            return []

        min_radius = max(5, int(min(radii) * 0.5))
        max_radius = int(max(radii) * 1.5)

        # Hough circle detection
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1,
            minDist=min_radius * 2,
            param1=50,
            param2=30,
            minRadius=min_radius,
            maxRadius=max_radius,
        )

        detections = []

        if circles is not None:
            circles = np.uint16(np.around(circles))
            for circle in circles[0, :]:
                cx, cy, r = circle
                x1, y1 = int(cx - r), int(cy - r)
                x2, y2 = int(cx + r), int(cy + r)

                detections.append(DetectionResult(
                    class_name=symbol.name,
                    bbox=(x1, y1, x2, y2),
                    confidence=0.85,  # Hough doesn't give confidence
                    angle=0.0,
                    method="circle",
                    center=(float(cx), float(cy)),
                ))

        return detections

    def _nms(
        self,
        detections: List[DetectionResult],
        iou_threshold: float = 0.5,
    ) -> List[DetectionResult]:
        """Non-maximum suppression."""
        if not detections:
            return []

        # Sort by confidence
        detections = sorted(detections, key=lambda d: d.confidence, reverse=True)

        kept = []
        for det in detections:
            is_duplicate = False
            for kept_det in kept:
                iou = self._compute_iou(det.bbox, kept_det.bbox)
                if iou > iou_threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                kept.append(det)

        return kept

    def _compute_iou(
        self,
        box1: Tuple[int, int, int, int],
        box2: Tuple[int, int, int, int],
    ) -> float:
        """Compute IoU between two boxes."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        if x2 <= x1 or y2 <= y1:
            return 0.0

        intersection = (x2 - x1) * (y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection

        return intersection / union if union > 0 else 0.0

    def link_to_coordinates(
        self,
        custom_detections: List[DetectionResult],
        coordinate_detections: List[dict],
        symbol_name: str,
    ) -> List[dict]:
        """
        Link custom symbol detections to nearby coordinates using rotation-aware logic.

        Uses the same rotation-aware direction checking as linking.py:
        - Transforms global coordinates to symbol's local coordinate frame
        - "below" means positive dy in rotated frame

        Args:
            custom_detections: List of custom symbol DetectionResult
            coordinate_detections: List of coordinate dicts with cx, cy, anchor_text
            symbol_name: Name of symbol to get linking config

        Returns:
            List of custom detection dicts with linked coordinate info
        """
        if symbol_name not in self.symbols:
            return [d.to_dict() for d in custom_detections]

        symbol = self.symbols[symbol_name]

        if not symbol.links_to_coordinate:
            return [d.to_dict() for d in custom_detections]

        results = []

        for det in custom_detections:
            det_dict = det.to_dict()

            # Get symbol center and angle
            sym_cx, sym_cy = det.center
            sym_angle = det.angle  # In degrees

            # Find nearest coordinate in the correct direction
            best_coord = None
            best_distance = float('inf')

            for coord in coordinate_detections:
                coord_cx = coord.get('cx', (coord.get('x1', 0) + coord.get('x2', 0)) / 2)
                coord_cy = coord.get('cy', (coord.get('y1', 0) + coord.get('y2', 0)) / 2)

                # Global distance
                dx_global = coord_cx - sym_cx
                dy_global = coord_cy - sym_cy
                distance = math.sqrt(dx_global**2 + dy_global**2)

                # Check max distance
                if distance > symbol.max_link_distance:
                    continue

                # Transform to symbol's local coordinate system (rotation-aware)
                angle_rad = math.radians(sym_angle)
                dx_local = dx_global * math.cos(-angle_rad) - dy_global * math.sin(-angle_rad)
                dy_local = dx_global * math.sin(-angle_rad) + dy_global * math.cos(-angle_rad)

                # Check direction based on symbol's coordinate_position setting (supports list)
                positions = symbol.coordinate_position
                # Handle both string and list (for backward compatibility)
                if isinstance(positions, str):
                    positions = [positions]

                is_correct_direction = False
                for pos in positions:
                    if pos == "any":
                        is_correct_direction = True
                        break
                    elif pos == "below" and dy_local > 0:
                        is_correct_direction = True
                        break
                    elif pos == "above" and dy_local < 0:
                        is_correct_direction = True
                        break
                    elif pos == "right" and dx_local > 0:
                        is_correct_direction = True
                        break
                    elif pos == "left" and dx_local < 0:
                        is_correct_direction = True
                        break
                    # Diagonal positions
                    elif pos == "below_right" and dy_local > 0 and dx_local > 0:
                        is_correct_direction = True
                        break
                    elif pos == "below_left" and dy_local > 0 and dx_local < 0:
                        is_correct_direction = True
                        break
                    elif pos == "above_right" and dy_local < 0 and dx_local > 0:
                        is_correct_direction = True
                        break
                    elif pos == "above_left" and dy_local < 0 and dx_local < 0:
                        is_correct_direction = True
                        break

                if not is_correct_direction:
                    continue

                # Found valid coordinate - check if closest
                if distance < best_distance:
                    best_distance = distance
                    best_coord = coord

            # Add linked coordinate info
            if best_coord:
                det_dict['linked_coordinate'] = best_coord.get('anchor_text', '')
                det_dict['linked_coord_id'] = best_coord.get('row_id', None)
                det_dict['link_distance'] = best_distance
            else:
                det_dict['linked_coordinate'] = None
                det_dict['linked_coord_id'] = None
                det_dict['link_distance'] = None

            results.append(det_dict)

        return results


class SymbolRetrainer:
    """
    Fine-tune YOLO model with new symbols.
    Supports CPU training (slower but works).
    """

    def __init__(self, base_model_path: str):
        self.base_model_path = base_model_path
        self.training_data_dir = Path("training_data/new_symbols")
        self.training_data_dir.mkdir(parents=True, exist_ok=True)

    def add_training_example(
        self,
        image: np.ndarray,
        symbol_name: str,
        bbox: Tuple[int, int, int, int],
        angle: float = 0.0,
    ):
        """Add a training example for fine-tuning."""
        # Create directories
        images_dir = self.training_data_dir / "images" / "train"
        labels_dir = self.training_data_dir / "labels" / "train"
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        import uuid
        file_id = str(uuid.uuid4())[:8]

        # Save image
        image_path = images_dir / f"{file_id}.png"
        cv2.imwrite(str(image_path), image)

        # Save label (YOLO OBB format)
        h, w = image.shape[:2]
        x1, y1, x2, y2 = bbox
        cx = ((x1 + x2) / 2) / w
        cy = ((y1 + y2) / 2) / h
        bw = (x2 - x1) / w
        bh = (y2 - y1) / h

        label_path = labels_dir / f"{file_id}.txt"
        # Format: class_id cx cy w h angle
        with open(label_path, 'w') as f:
            f.write(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f} {angle:.1f}\n")

        debug_print('custom_symbols',f"Added training example for '{symbol_name}'")

    def get_training_stats(self) -> Dict[str, int]:
        """Get count of training examples."""
        images_dir = self.training_data_dir / "images" / "train"
        if images_dir.exists():
            return {"examples": len(list(images_dir.glob("*.png")))}
        return {"examples": 0}

    def fine_tune(
        self,
        new_class_names: List[str],
        epochs: int = 20,
        device: str = "cpu",  # "cpu" or "cuda" or "0" for GPU
        batch_size: int = 4,  # Lower for CPU
    ) -> str:
        """
        Fine-tune the YOLO model with new symbols.

        Args:
            new_class_names: List of new class names to add
            epochs: Number of training epochs
            device: "cpu" for CPU training, "cuda" or "0" for GPU
            batch_size: Batch size (use 2-4 for CPU, 8-16 for GPU)

        Returns:
            Path to fine-tuned model
        """
        from ultralytics import YOLO

        # Create dataset.yaml
        dataset_yaml = self.training_data_dir / "dataset.yaml"

        # Get existing classes from base model
        base_model = YOLO(self.base_model_path)
        existing_classes = list(base_model.names.values())

        # Combine classes
        all_classes = existing_classes + new_class_names

        with open(dataset_yaml, 'w') as f:
            f.write(f"path: {self.training_data_dir.absolute()}\n")
            f.write("train: images/train\n")
            f.write("val: images/train\n")  # Use same for demo
            f.write(f"nc: {len(all_classes)}\n")
            f.write(f"names: {all_classes}\n")

        # Training parameters optimized for CPU
        train_params = {
            "data": str(dataset_yaml),
            "epochs": epochs,
            "imgsz": 640,  # Smaller for CPU
            "batch": batch_size,
            "device": device,
            "workers": 2 if device == "cpu" else 8,
            "patience": 10,
            "save": True,
            "project": str(self.training_data_dir / "runs"),
            "name": "fine_tune",
            "exist_ok": True,
        }

        if device == "cpu":
            train_params["half"] = False  # CPU doesn't support FP16
            debug_print('custom_symbols'," Training on CPU - this will be slow (2-4 hours for 20 epochs)")

        # Train
        debug_print('custom_symbols',f"Starting fine-tuning with {epochs} epochs on {device}...")
        results = base_model.train(**train_params)

        # Return path to best model
        best_model = self.training_data_dir / "runs" / "fine_tune" / "weights" / "best.pt"
        debug_print('custom_symbols',f"Fine-tuning complete! Model saved to: {best_model}")

        return str(best_model)

    def estimate_training_time(self, epochs: int, device: str = "cpu") -> str:
        """Estimate training time."""
        stats = self.get_training_stats()
        examples = stats.get("examples", 0)

        if device == "cpu":
            # Rough estimate: ~2-3 minutes per epoch with 50 images on CPU
            minutes_per_epoch = max(2, examples / 25)
            total_minutes = epochs * minutes_per_epoch
        else:
            # GPU is ~10-20x faster
            minutes_per_epoch = max(0.2, examples / 250)
            total_minutes = epochs * minutes_per_epoch

        if total_minutes < 60:
            return f"~{int(total_minutes)} minutes"
        else:
            hours = total_minutes / 60
            return f"~{hours:.1f} hours"


# Convenience function for integration with pipeline
def detect_custom_symbols(
    image: np.ndarray,
    yolo_detections: List[dict],
) -> Tuple[List[dict], List[dict]]:
    """
    Main entry point for custom symbol detection.

    Args:
        image: BGR image
        yolo_detections: Existing YOLO detections

    Returns:
        Tuple of (custom_symbol_detections, unknown_symbol_clusters)
    """
    # Detect user-defined custom symbols
    detector = NewSymbolDetector()
    custom_detections = detector.detect_all_symbols(image)

    # Find potential unknown symbols
    unknown_detector = UnknownSymbolDetector()
    unknown_clusters = unknown_detector.find_unknown_symbols(image, yolo_detections)

    # Convert to dict format for pipeline compatibility
    custom_dets = [det.to_dict() for det in custom_detections]

    return custom_dets, unknown_clusters
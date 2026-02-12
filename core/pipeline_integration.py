# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Integration of New Symbol Detection with existing pipeline.

This module provides functions to integrate custom symbol detection
into the existing PipelineWorker without modifying the core code heavily.

Usage in pipelineworker.py:
    from core.pipeline_integration import detect_with_custom_symbols

    # After YOLO detection:
    dets = run_yolo_on_page(model, page_bgr)

    # Add custom symbol detection:
    dets, unknown_clusters = detect_with_custom_symbols(page_bgr, dets)
"""

from typing import List, Dict, Tuple, Any, Optional, Union
import numpy as np
import logging

logger = logging.getLogger(__name__)


def detect_with_custom_symbols(
    image: np.ndarray,
    yolo_detections: List[dict],
    detect_unknown: bool = True,
) -> Tuple[List[dict], List[dict]]:
    """
    Enhance YOLO detections with custom symbol detection.

    This function:
    1. Detects user-defined custom symbols (template/contour matching)
    2. Optionally finds unknown symbols for user review
    3. Merges results with YOLO detections

    Args:
        image: BGR image (numpy array)
        yolo_detections: List of YOLO detection dicts
        detect_unknown: Whether to look for unknown symbols

    Returns:
        Tuple of:
        - Enhanced detection list (YOLO + custom symbols)
        - List of unknown symbol clusters (for user review)
    """
    from core.symbol_detector import NewSymbolDetector, UnknownSymbolDetector

    # 1. Detect user-defined custom symbols
    custom_detector = NewSymbolDetector()
    custom_detections = custom_detector.detect_all_symbols(image)

    # Convert to pipeline format
    custom_dets = []
    for det in custom_detections:
        custom_dets.append(det.to_dict())

    logger.info(f"Custom symbol detection: found {len(custom_dets)} custom symbols")

    # 2. Find unknown symbols (optional)
    unknown_clusters = []
    if detect_unknown:
        unknown_detector = UnknownSymbolDetector()
        unknown_clusters = unknown_detector.find_unknown_symbols(
            image,
            yolo_detections + custom_dets  # Exclude both YOLO and custom from search
        )

        if unknown_clusters:
            logger.info(f"Found {len(unknown_clusters)} potential unknown symbol types")

    # 3. Merge detections
    all_detections = yolo_detections + custom_dets

    # 4. Remove duplicates (if custom detection found something YOLO also found)
    all_detections = _remove_duplicate_detections(all_detections)

    return all_detections, unknown_clusters


def _remove_duplicate_detections(
    detections: List[dict],
    iou_threshold: float = 0.5,
) -> List[dict]:
    """Remove duplicate detections, preferring YOLO over custom."""
    if not detections:
        return []

    # Separate YOLO and custom detections
    yolo_dets = [d for d in detections if not d.get("is_new_symbol", False)]
    custom_dets = [d for d in detections if d.get("is_new_symbol", False)]

    # Keep all YOLO detections
    kept = list(yolo_dets)

    # Add custom detections only if they don't overlap with YOLO
    for custom in custom_dets:
        is_duplicate = False
        custom_box = (custom["x1"], custom["y1"], custom["x2"], custom["y2"])

        for yolo in yolo_dets:
            yolo_box = (yolo["x1"], yolo["y1"], yolo["x2"], yolo["y2"])
            if _compute_iou(custom_box, yolo_box) > iou_threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            kept.append(custom)

    return kept


def _compute_iou(box1: tuple, box2: tuple) -> float:
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


def apply_ocr_to_custom_symbols(
    custom_detections: List[dict],
    image: np.ndarray,
    ocr_function,  # Reference to existing OCR function
) -> List[dict]:
    """
    Apply OCR to custom symbol detections that need text extraction.

    Args:
        custom_detections: List of custom symbol detections
        image: BGR image
        ocr_function: Reference to OCR function (e.g., ocr_anchor_name)

    Returns:
        Updated detections with OCR results
    """
    from core.symbol_detector import NewSymbolDetector

    detector = NewSymbolDetector()

    for det in custom_detections:
        if not det.get("is_new_symbol", False):
            continue

        symbol_name = det.get("name", "")
        if symbol_name not in detector.symbols:
            continue

        symbol_def = detector.symbols[symbol_name]

        if symbol_def.has_text:
            # Get text region based on text_position
            text_bbox = _get_text_region(det, symbol_def.text_position)

            # Extract text using existing OCR
            try:
                x1, y1, x2, y2 = text_bbox
                crop = image[y1:y2, x1:x2]

                # Use provided OCR function
                text = ocr_function(crop)
                det["text"] = text
                det["ocr_applied"] = True

            except Exception as e:
                logger.warning(f"OCR failed for custom symbol: {e}")
                det["text"] = ""
                det["ocr_applied"] = False

    return custom_detections


def _get_text_region(
    detection: dict,
    text_position: Union[str, List[str]],
    padding: int = 10,
    text_region_size: int = 100,
) -> Tuple[int, int, int, int]:
    """
    Get the region where text should be found relative to symbol.

    Args:
        detection: Detection dict with x1, y1, x2, y2
        text_position: "below", "above", "left", "right", "inside" - or list of positions
        padding: Padding between symbol and text region
        text_region_size: Size of text search region

    Returns:
        (x1, y1, x2, y2) of text region
    """
    # Handle list of positions - use first one
    if isinstance(text_position, list):
        text_position = text_position[0] if text_position else "below"

    x1, y1, x2, y2 = detection["x1"], detection["y1"], detection["x2"], detection["y2"]
    w, h = x2 - x1, y2 - y1

    if text_position == "below":
        return (x1, y2 + padding, x2, y2 + padding + text_region_size)
    elif text_position == "above":
        return (x1, y1 - padding - text_region_size, x2, y1 - padding)
    elif text_position == "left":
        return (x1 - padding - text_region_size, y1, x1 - padding, y2)
    elif text_position == "right":
        return (x2 + padding, y1, x2 + padding + text_region_size, y2)
    elif text_position == "inside":
        return (x1, y1, x2, y2)
    else:
        return (x1, y2 + padding, x2, y2 + padding + text_region_size)


def link_custom_symbols_to_coordinates(
    custom_detections: List[dict],
    coordinate_detections: List[dict],
) -> List[dict]:
    """
    Link custom symbols to coordinates based on their configuration.

    Args:
        custom_detections: List of custom symbol detections
        coordinate_detections: List of coordinate detections

    Returns:
        Updated custom detections with linked coordinates
    """
    from core.symbol_detector import NewSymbolDetector

    detector = NewSymbolDetector()

    for det in custom_detections:
        if not det.get("is_new_symbol", False):
            continue

        symbol_name = det.get("name", "")
        if symbol_name not in detector.symbols:
            continue

        symbol_def = detector.symbols[symbol_name]

        if symbol_def.links_to_coordinate:
            # Find nearest coordinate in the expected direction
            nearest = _find_nearest_coordinate(
                det,
                coordinate_detections,
                symbol_def.coordinate_position,
                symbol_def.max_link_distance,
            )

            if nearest:
                det["linked_coordinate"] = nearest.get("text", "")
                det["coordinate_det"] = nearest

    return custom_detections


def _find_nearest_coordinate(
    symbol_det: dict,
    coordinates: List[dict],
    expected_position: str,
    max_distance: int,
) -> Optional[dict]:
    """Find nearest coordinate in expected direction."""
    sym_cx = (symbol_det["x1"] + symbol_det["x2"]) / 2
    sym_cy = (symbol_det["y1"] + symbol_det["y2"]) / 2

    best_coord = None
    best_distance = float('inf')

    for coord in coordinates:
        if coord.get("name") != "coordinate":
            continue

        coord_cx = (coord["x1"] + coord["x2"]) / 2
        coord_cy = (coord["y1"] + coord["y2"]) / 2

        dx = coord_cx - sym_cx
        dy = coord_cy - sym_cy
        distance = (dx**2 + dy**2) ** 0.5

        if distance > max_distance:
            continue

        # Check position constraint
        position_ok = False
        if expected_position == "below" and dy > 0:
            position_ok = True
        elif expected_position == "above" and dy < 0:
            position_ok = True
        elif expected_position == "left" and dx < 0:
            position_ok = True
        elif expected_position == "right" and dx > 0:
            position_ok = True

        if position_ok and distance < best_distance:
            best_distance = distance
            best_coord = coord

    return best_coord


# ============================================================================
# INTEGRATION POINTS FOR PIPELINEWORKER
# ============================================================================

"""
To integrate with existing pipelineworker.py, add these changes:

1. At the top of pipelineworker.py, add import:

   from core.pipeline_integration import detect_with_custom_symbols

2. After YOLO detection (around line 180), add:

   # Original YOLO detection
   dets = run_yolo_on_page(model, page_bgr)

   # NEW: Add custom symbol detection
   dets, unknown_clusters = detect_with_custom_symbols(page_bgr, dets)

   # Store unknown clusters for later UI prompt
   if unknown_clusters:
       self._unknown_symbols_found = unknown_clusters

3. In the done signal or page_processed signal, include unknown_clusters
   so the UI can show the UnknownSymbolsDialog.

4. In setup_window.py or auditing_window.py, add button:

   btn_add_symbol = QPushButton(" Neues Symbol")
   btn_add_symbol.clicked.connect(self.on_add_new_symbol)

   def on_add_new_symbol(self):
       from ui.new_symbol_dialog import NewSymbolDialog
       dialog = NewSymbolDialog(self.current_page_bgr_array, self)
       dialog.exec_()

"""

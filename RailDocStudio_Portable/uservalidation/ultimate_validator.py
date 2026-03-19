# ultimate_validator.py
"""
Ultimate Combined Validator - Everything in One Place

Combines:
1. Your existing OCR validation (format, duplicates, missing data)
2. Enhanced YOLO quality checks (confidence, duplicates, sizes)
3. Missing data detection (coordinates, signals, isolation)
4. Auto-correction support

This is the ONE validator to rule them all!
"""

import pandas as pd
import numpy as np
from typing import List, Dict
from uservalidation.data_validator2 import EnhancedDataValidator, ValidationIssue
from uservalidation.missing_detection_analyzer import MissingDetectionAnalyzer, MissingDetectionRegion
from core.linking import coord_to_sort_key

# Import shared validation config (single source of truth)
from validation_config import (
    CLASSES_REQUIRING_COORDINATES,
    CLASSES_REQUIRING_TEXT,
    CLASSES_EXCLUDED,
    CONFIDENCE_THRESHOLDS,
    DEFAULT_CONFIDENCE_THRESHOLD,
    get_confidence_threshold,
    needs_coordinate,
    needs_text,
    is_excluded,
)

class UltimateValidator:
    """
    Combined OCR + YOLO validator with all features.

    Includes:
    - All your existing OCR checks (format, duplicates, etc.)
    - YOLO quality checks (confidence, duplicates, sizes)
    - Missing data detection (coordinates, isolated objects)
    - Jump-to-detection support
    - Auto-correction for OCR format errors
    """

    #  Use shared configuration from validation_config.py
    CLASSES_NEEDING_COORDS = CLASSES_REQUIRING_COORDINATES
    CLASSES_NEEDING_TEXT = CLASSES_REQUIRING_TEXT
    CONFIDENCE_THRESHOLDS = CONFIDENCE_THRESHOLDS
    
    def __init__(self, df: pd.DataFrame):
        #  FILTER: Exclude classes defined in shared validation config
        if 'cls' in df.columns:
            # Use is_excluded() from shared config
            df_filtered = df[~df['cls'].apply(lambda x: is_excluded(str(x)))].copy()
        else:
            df_filtered = df.copy()

        #  ENSURE REQUIRED COLUMNS EXIST FIRST
        self.df = self._ensure_columns(df_filtered)

        # Your existing OCR validator
        self.ocr_validator = EnhancedDataValidator(self.df)

        #  Load NewSymbolDetector ONCE for template validation (performance fix)
        self.symbol_detector = None
        try:
            from core.symbol_detector import NewSymbolDetector
            self.symbol_detector = NewSymbolDetector()
        except Exception as e:
            print(f"Could not load NewSymbolDetector: {e}")
    
    def _ensure_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure all required columns exist for YOLO validation.
        Creates xc, yc, w, h if missing.
        """
        df = df.copy()
        if 'page' not in df.columns:
            print("Warning: 'page' column missing, adding default value 1")
            df['page'] = 1
        # Add center coordinates (xc, yc) if missing
        if 'xc' not in df.columns:
            df['xc'] = df.apply(
                lambda row: (row['cx1'] + row['cx2']) / 2 if pd.notna(row.get('cx1')) 
                           else (row['ax1'] + row['ax2']) / 2 if pd.notna(row.get('ax1'))
                           else None,
                axis=1
            )
        
        if 'yc' not in df.columns:
            df['yc'] = df.apply(
                lambda row: (row['cy1'] + row['cy2']) / 2 if pd.notna(row.get('cy1'))
                           else (row['ay1'] + row['ay2']) / 2 if pd.notna(row.get('ay1'))
                           else None,
                axis=1
            )
        
        # Add width/height if missing
        if 'w' not in df.columns:
            df['w'] = df.apply(
                lambda row: row['cx2'] - row['cx1'] if pd.notna(row.get('cx1'))
                           else row['ax2'] - row['ax1'] if pd.notna(row.get('ax1'))
                           else None,
                axis=1
            )
        
        if 'h' not in df.columns:
            df['h'] = df.apply(
                lambda row: row['cy2'] - row['cy1'] if pd.notna(row.get('cy1'))
                           else row['ay2'] - row['ay1'] if pd.notna(row.get('ay1'))
                           else None,
                axis=1
            )
        
        return df
    
    def validate_all(self, auto_correct: bool = False):
        """
        Run ALL validation checks - OCR + YOLO + Template Matching.

        Args:
            auto_correct: If True, apply OCR format auto-corrections

        Returns:
            ValidationResult with all issues
        """
        #  Safety check
        if self.df is None or self.df.empty:
            print("Warning: Empty DataFrame, skipping validation")
            from uservalidation.data_validator2 import ValidationResult
            return ValidationResult()
        
        print(f"Validating {len(self.df)} rows...")
        
        # ========================================
        # PART 1: Your Existing OCR Validation
        # ========================================
        print(f"Running OCR validation...")
        result = self.ocr_validator.validate_all(auto_correct=auto_correct)
        print(f"OCR validation found {len(result.issues)} issues")
        
        # ========================================
        # PART 2: Enhanced YOLO Checks
        # ========================================
        print(f"Running YOLO quality checks...")
        yolo_issues = []

        # YOLO Quality
        yolo_issues.extend(self._check_low_confidence())
        yolo_issues.extend(self._check_yolo_duplicates())
        #  Very sensitive - detect even slight overlaps (5%)
        yolo_issues.extend(self._check_bbox_overlaps(same_class_iou=0.05, cross_class_iou=0.05))
        #  DISABLED: Size outliers (user doesn't want "ungewöhnliche Größe" warnings)
        # yolo_issues.extend(self._check_size_outliers())

        #  DISABLED: Class relationships check (user doesn't want "ohne nahe Koordinaten")
        # yolo_issues.extend(self._check_class_relationships())

        # False Positive Detection
        yolo_issues.extend(self._check_false_positives())  #  NEW: Detect likely false positives

        #  DISABLED: Cross-references (contains unwanted coordinate_sequence_gap)
        # yolo_issues.extend(self._check_cross_references())

        # Missing Data Detection
        yolo_issues.extend(self._check_missing_coordinates_spatial())
        yolo_issues.extend(self._check_missing_text())
        #  DISABLED: Isolated detections (user doesn't want "weit von anderen entfernt")
        # yolo_issues.extend(self._check_isolated_detections())
        yolo_issues.extend(self._check_expected_ratios())
        yolo_issues.extend(self._check_link_distance_outliers())

        # Haltepunkt-Signal Reference Check
        print(f"Running haltepunkt-signal reference check...")
        yolo_issues.extend(self._check_haltepunkt_signal_reference())

        print(f"YOLO checks found {len(yolo_issues)} issues")

        # ========================================
        # PART 3: Coordinate Pattern Validation
        # ========================================
        #  DISABLED: Gap detection (too aggressive, flags blank spaces)
        # Instead: Check if coordinates match the majority pattern
        print(f"Running coordinate pattern validation...")
        yolo_issues.extend(self._check_coordinate_patterns())

        # ========================================
        # PART 3b: OCR Text Outlier Detection
        # ========================================
        print(f"Running OCR text outlier detection...")
        yolo_issues.extend(self._check_ocr_text_outliers())

        # ========================================
        # PART 4: Template Matching Validation
        # ========================================
        print(f"Running template matching validation...")

        # Debug: Check how many template symbols we have
        template_count = 0
        if 'is_new_symbol' in self.df.columns:
            template_count = self.df['is_new_symbol'].sum() if self.df['is_new_symbol'].dtype == bool else (self.df['is_new_symbol'] == True).sum()
        print(f"Found {template_count} template symbols in DataFrame")

        # Debug: Check what columns exist and sample some template symbols
        if template_count > 0:
            template_mask = self.df['is_new_symbol'] == True
            sample_templates = self.df[template_mask].head(5)
            print(f"Sample template symbols:")
            for idx, row in sample_templates.iterrows():
                cls_val = row.get('cls', 'MISSING')
                det_method = row.get('detection_method', 'MISSING')
                coord_val = row.get('coord_value', 'MISSING')
                anchor_text = row.get('anchor_text', 'MISSING')

                # Check if this is actually a YOLO class
                is_yolo_class = cls_val in self.CONFIDENCE_THRESHOLDS

                print(f"- cls: '{cls_val}' {'YOLO CLASS!' if is_yolo_class else 'Template'}")
                print(f"detection_method: {det_method}")
                print(f"anchor_text: {anchor_text}")
                print(f"coord_value: {coord_val}")

        # Debug: Check symbol_detector and show name matching
        if self.symbol_detector:
            print(f"Symbol detector loaded with {len(self.symbol_detector.symbols)} symbols:")
            for sym_name in self.symbol_detector.symbols.keys():
                sym_def = self.symbol_detector.symbols[sym_name]
                print(f"- '{sym_name}': has_text={sym_def.has_text}, links_to_coordinate={sym_def.links_to_coordinate}")

            # Check if any DataFrame cls values match detector symbols
            if template_count > 0:
                template_cls_values = self.df[self.df['is_new_symbol'] == True]['cls'].unique()
                print(f"Template cls values in DataFrame: {list(template_cls_values)}")
                print(f"Name matching check:")
                for cls_val in template_cls_values:
                    if cls_val in self.symbol_detector.symbols:
                        print(f"- '{cls_val}':  EXACT MATCH in detector")
                    else:
                        # Check for partial matches
                        partial_matches = [s for s in self.symbol_detector.symbols.keys() if cls_val.startswith(s) or s.startswith(cls_val)]
                        if partial_matches:
                            print(f"- '{cls_val}': NO EXACT MATCH, but found partial: {partial_matches}")
                        else:
                            print(f"- '{cls_val}': NO MATCH in detector")
        else:
            print(f"Symbol detector is None - cannot check symbol requirements!")

        template_issues = []

        # High priority template checks
        template_issues.extend(self._check_template_false_positive_score())  # Hybrid composite score
        template_issues.extend(self._check_template_no_coordinate())  # H - Missing coordinate
        template_issues.extend(self._check_template_missing_text())  # D - Missing text
        template_issues.extend(self._check_template_low_confidence())  # A - Low confidence
        template_issues.extend(self._check_template_size_outlier())  # M - Size outlier

        # Medium priority template checks
        template_issues.extend(self._check_template_link_distance_large())  # I - Link distance
        template_issues.extend(self._check_template_text_pattern())  # F - Text pattern

        print(f"Template validation found {len(template_issues)} issues")

        # ========================================
        # Combine All Issues (OCR + YOLO + Template)
        # ========================================
        result.issues.extend(yolo_issues)
        result.issues.extend(template_issues)
        result.total_issues = len(result.issues)
        
        print(f"Total validation issues: {result.total_issues}")
        
        # Update category stats
        from collections import Counter
        result.stats['by_category'] = dict(Counter(i.category for i in result.issues))
        
        return result

        
    # ========================================================================
    # YOLO QUALITY CHECKS
    # ========================================================================
    
    def _check_low_confidence(self) -> List[ValidationIssue]:
        """Flag YOLO detections with low confidence (using your thresholds)"""
        issues = []

        #  Safety checks
        if 'conf' not in self.df.columns:
            return issues

        if not all(col in self.df.columns for col in ['xc', 'yc']):
            return issues

        for _, row in self.df.iterrows():
            #  Skip if position is missing
            if pd.isna(row.get('xc')) or pd.isna(row.get('yc')):
                continue

            cls = row['cls']
            conf = row['conf']

            #  Use YOUR class-specific thresholds
            expected_threshold = self.CONFIDENCE_THRESHOLDS.get(cls, 0.5)
            
            if conf < expected_threshold:
                if conf < expected_threshold * 0.6:  # Very low (< 60% of expected)
                    severity = 'error'
                    msg = f"YOLO: {cls} sehr niedrige Konfidenz ({conf:.0%}, erwartet ≥{expected_threshold:.0%})"
                else:
                    severity = 'warning'
                    msg = f"YOLO: {cls} niedrige Konfidenz ({conf:.0%}, erwartet ≥{expected_threshold:.0%})"
                
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity=severity,
                    category='yolo_confidence',
                    field='conf',
                    message=msg,
                    current_value=f"{conf:.0%}",
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=0.0,
                    context={
                        'position': (float(row['xc']), float(row['yc'])),
                        'expected_threshold': expected_threshold,
                        'suggestion': f'YOLO war unsicher (Konfidenz {conf:.0%} < {expected_threshold:.0%}). Überprüfen und ggf. löschen.',
                        'can_jump': True,
                        #  Low confidence suggests deletion or review
                        'suggested_action': 'delete',
                        'alternative_actions': ['review', 'bbox_resize'],
                        'action_description': f'Niedrige YOLO-Konfidenz ({conf:.0%}). Möglicherweise Falscherkennung - löschen oder überprüfen.',
                    }
                ))
        
        return issues
    
    def _check_yolo_duplicates(self, distance: float = 50) -> List[ValidationIssue]:
        """
        Flag YOLO duplicate detections

        Uses class-specific thresholds to avoid false positives for classes
        that naturally appear close together or rarely duplicate
        """
        issues = []

        if not all(col in self.df.columns for col in ['xc', 'yc', 'cls']):
            return issues

        #  Class-specific duplicate detection thresholds
        # None = skip duplicate detection for this class (rare duplicates, often close together)
        class_thresholds = {
            'signal': 50,
            'gks_gesteuert': 30,
            'gks_festkodiert': 30,
            'haltepunkt': None,        # Skip - can be legitimately close, rarely duplicates
            'haltetafel': None,        # Skip - can be legitimately close, rarely duplicates
            'sverbinder': 30,
            'gm_block': 40,
            'prellbock': 30,
            'isolierstoß': None,       # Skip - often appear in sequence, rarely duplicates
            'weichenende': None,       # Skip - can be legitimately close
            'weichengruppenende': 40,
        }

        for cls in self.df['cls'].unique():
            #  Skip classes that don't need duplicate detection
            threshold = class_thresholds.get(cls, distance)
            if threshold is None:
                continue

            cls_df = self.df[self.df['cls'] == cls].copy()

            #  Filter out rows with missing positions
            cls_df = cls_df[cls_df['xc'].notna() & cls_df['yc'].notna()]

            if len(cls_df) < 2:
                continue

            positions = cls_df[['xc', 'yc']].values

            #  Track which pairs we've already reported
            reported_pairs = set()

            for i in range(len(positions)):
                for j in range(i + 1, len(positions)):
                    #  Skip if we've already reported this pair
                    pair_key = tuple(sorted([i, j]))
                    if pair_key in reported_pairs:
                        continue

                    dist = np.linalg.norm(positions[i] - positions[j])

                    if dist < threshold:
                        row_i = cls_df.iloc[i]
                        row_j = cls_df.iloc[j]
                        
                        conf_i = row_i.get('conf', 1.0)
                        conf_j = row_j.get('conf', 1.0)
                        
                        #  Keep higher confidence, delete lower
                        if conf_i >= conf_j:
                            keep, delete = row_i, row_j
                        else:
                            keep, delete = row_j, row_i
                        
                        issues.append(ValidationIssue(
                            row_id=delete['row_id'],
                            severity='warning',
                            category='yolo_duplicate',
                            field='position',
                            message=f"YOLO: {cls} Duplikat - {dist:.0f}px von Zeile {keep['row_id']}",
                            current_value=f"Zeile {delete['row_id']}",
                            suggested_value=f"Löschen (Zeile {keep['row_id']} behalten)",
                            auto_correctable=False,
                            confidence=0.0,
                            context={
                                'position': (float(delete['xc']), float(delete['yc'])),
                                'keep_row': int(keep['row_id']),
                                'suggestion': f"YOLO Duplikat erkannt. Löschen Sie Zeile {delete['row_id']} (Konfidenz {delete.get('conf', 1.0):.0%}), behalten Sie Zeile {keep['row_id']} (Konfidenz {keep.get('conf', 1.0):.0%}).",
                                'can_jump': True,
                                #  Duplicate detection - delete lower confidence
                                'suggested_action': 'delete',
                                'alternative_actions': ['review'],
                                'action_description': f'Duplikat erkannt ({dist:.0f}px entfernt). Löschen Sie das Element mit niedrigerer Konfidenz.',
                            }
                        ))
                        
                        reported_pairs.add(pair_key)
        
        return issues

    def _check_bbox_overlaps(self, same_class_iou: float = 0.5, cross_class_iou: float = 0.3) -> List[ValidationIssue]:
        """
         NEW: Check for bbox overlaps using IoU (Intersection over Union).

        Detects:
        - Same-class overlaps (likely duplicates)
        - Cross-class overlaps (coordinates overlapping signals, etc.)

        Args:
            same_class_iou: IoU threshold for same-class overlaps (default 0.5 = 50% overlap)
            cross_class_iou: IoU threshold for cross-class overlaps (default 0.3 = 30% overlap)
        """
        issues = []

        # Check for required bbox columns
        anchor_cols = ['ax1', 'ay1', 'ax2', 'ay2']
        coord_cols = ['cx1', 'cy1', 'cx2', 'cy2']

        if not all(col in self.df.columns for col in ['xc', 'yc', 'cls']):
            return issues

        def calculate_iou(bbox1, bbox2):
            """Calculate IoU between two bboxes [x1, y1, x2, y2]"""
            # Skip if any bbox coordinate is None/NaN
            if any(pd.isna(c) or c is None for c in bbox1 + bbox2):
                return 0.0

            x1_inter = max(bbox1[0], bbox2[0])
            y1_inter = max(bbox1[1], bbox2[1])
            x2_inter = min(bbox1[2], bbox2[2])
            y2_inter = min(bbox1[3], bbox2[3])

            if x2_inter <= x1_inter or y2_inter <= y1_inter:
                return 0.0

            inter_area = (x2_inter - x1_inter) * (y2_inter - y1_inter)

            bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
            bbox2_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])

            union_area = bbox1_area + bbox2_area - inter_area

            return inter_area / union_area if union_area > 0 else 0.0

        def calculate_containment(bbox1, bbox2):
            """
            Calculate max containment ratio between two bboxes.
            Returns (containment_ratio, smaller_bbox_index)
            where smaller_bbox_index is 0 if bbox1 is smaller, 1 if bbox2 is smaller.

            Containment = intersection_area / smaller_box_area
            This is better than IoU for detecting when one box is inside another.
            """
            # Skip if any bbox coordinate is None/NaN
            if any(pd.isna(c) or c is None for c in bbox1 + bbox2):
                return 0.0, 0

            # Calculate intersection
            x1_inter = max(bbox1[0], bbox2[0])
            y1_inter = max(bbox1[1], bbox2[1])
            x2_inter = min(bbox1[2], bbox2[2])
            y2_inter = min(bbox1[3], bbox2[3])

            if x2_inter <= x1_inter or y2_inter <= y1_inter:
                return 0.0, 0

            inter_area = (x2_inter - x1_inter) * (y2_inter - y1_inter)

            # Calculate both box areas
            bbox1_area = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
            bbox2_area = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])

            if bbox1_area <= 0 or bbox2_area <= 0:
                return 0.0, 0

            # Containment = intersection / smaller_box_area
            smaller_area = min(bbox1_area, bbox2_area)
            containment = inter_area / smaller_area
            smaller_idx = 0 if bbox1_area <= bbox2_area else 1

            return containment, smaller_idx

        def get_bbox(row):
            """Get bbox coordinates for a row (tries anchor first, then coord)"""
            # Try anchor bbox
            if all(col in row.index and pd.notna(row.get(col)) and row.get(col) is not None
                   for col in anchor_cols):
                return [float(row['ax1']), float(row['ay1']), float(row['ax2']), float(row['ay2'])]
            # Try coord bbox
            elif all(col in row.index and pd.notna(row.get(col)) and row.get(col) is not None
                     for col in coord_cols):
                return [float(row['cx1']), float(row['cy1']), float(row['cx2']), float(row['cy2'])]
            else:
                return None

        # Filter rows with valid bboxes
        valid_rows = []
        for idx, row in self.df.iterrows():
            bbox = get_bbox(row)
            if bbox:
                valid_rows.append((idx, row, bbox))

        print(f"Bbox overlap check: Found {len(valid_rows)} rows with valid bboxes out of {len(self.df)}")

        if len(valid_rows) < 2:
            print(f"Not enough valid bboxes to check overlaps (need at least 2)")
            return issues

        # Track reported pairs
        reported_pairs = set()
        overlaps_found = 0

        # =====================================================================
        # CHECK 1: High-containment pairwise overlaps (one box inside another)
        # =====================================================================
        HIGH_CONTAINMENT_THRESHOLD = 0.95
        reported_containment_pairs = set()

        for i in range(len(valid_rows)):
            for j in range(i + 1, len(valid_rows)):  # Only check each pair once (j > i)
                idx_i, row_i, bbox_i = valid_rows[i]
                idx_j, row_j, bbox_j = valid_rows[j]

                row_id_i = int(row_i['row_id'])
                row_id_j = int(row_j['row_id'])

                # Skip if already reported
                pair_key = tuple(sorted([row_id_i, row_id_j]))
                if pair_key in reported_containment_pairs:
                    continue

                containment, smaller_idx = calculate_containment(bbox_i, bbox_j)

                if containment >= HIGH_CONTAINMENT_THRESHOLD:
                    reported_containment_pairs.add(pair_key)

                    # Identify which box is smaller/larger (for info only - don't assume which is wrong)
                    if smaller_idx == 0:
                        smaller_row, larger_row = row_i, row_j
                        smaller_bbox, larger_bbox = bbox_i, bbox_j
                    else:
                        smaller_row, larger_row = row_j, row_i
                        smaller_bbox, larger_bbox = bbox_j, bbox_i

                    smaller_row_id = int(smaller_row['row_id'])
                    larger_row_id = int(larger_row['row_id'])
                    cls_smaller = smaller_row['cls']
                    cls_larger = larger_row['cls']

                    # Calculate areas for message
                    smaller_area = (smaller_bbox[2] - smaller_bbox[0]) * (smaller_bbox[3] - smaller_bbox[1])
                    larger_area = (larger_bbox[2] - larger_bbox[0]) * (larger_bbox[3] - larger_bbox[1])

                    # Report on the FIRST row (row_i) - neutral, user decides which to delete
                    report_row_id = row_id_i
                    report_row = row_i

                    issues.append(ValidationIssue(
                        row_id=report_row_id,
                        severity='warning',
                        category='bbox_high_containment',
                        field='bbox',
                        message=f"Bbox-Überlappung {containment:.0%}: {cls_smaller} (Zeile {smaller_row_id}) in {cls_larger} (Zeile {larger_row_id})",
                        current_value=f"{containment:.0%} Überlappung",
                        suggested_value=f"Eine der Zeilen {smaller_row_id} oder {larger_row_id} prüfen/löschen",
                        auto_correctable=False,
                        confidence=containment,
                        context={
                            'position': (float(report_row['xc']), float(report_row['yc'])),
                            'containment': float(containment),
                            'smaller_row_id': smaller_row_id,
                            'larger_row_id': larger_row_id,
                            'smaller_class': cls_smaller,
                            'larger_class': cls_larger,
                            'smaller_area': float(smaller_area),
                            'larger_area': float(larger_area),
                            'overlapping_rows': [smaller_row_id, larger_row_id],
                            'suggestion': f"'{cls_smaller}' (Zeile {smaller_row_id}, {smaller_area:.0f}px²) ist zu {containment:.0%} innerhalb von '{cls_larger}' (Zeile {larger_row_id}, {larger_area:.0f}px²). Eine der beiden Erkennungen ist wahrscheinlich falsch - prüfen Sie welche.",
                            'can_jump': True,
                            'suggested_action': 'review',
                            'alternative_actions': ['delete'],
                            'action_description': f'Zwei Erkennungen überlappen stark ({containment:.0%}).\n\n• Kleinere: {cls_smaller} (Zeile {smaller_row_id}, {smaller_area:.0f}px²)\n• Größere: {cls_larger} (Zeile {larger_row_id}, {larger_area:.0f}px²)\n\nPrüfen Sie welche korrekt ist und löschen Sie die andere.',
                        }
                    ))

                    print(f"High containment: {cls_smaller} (row {smaller_row_id}) is {containment:.0%} inside {cls_larger} (row {larger_row_id})")

        print(f"High containment check: Found {len(reported_containment_pairs)} pairs with ≥95% containment")

        # =====================================================================
        # CHECK 2: Build overlap graph to find clusters of 3+ overlapping bboxes
        # =====================================================================
        # First, find all pairwise overlaps
        overlap_graph = {}  # row_id -> list of (other_row_id, iou, bbox_data)

        for i in range(len(valid_rows)):
            idx_i, row_i, bbox_i = valid_rows[i]
            row_id_i = int(row_i['row_id'])

            if row_id_i not in overlap_graph:
                overlap_graph[row_id_i] = []

            for j in range(len(valid_rows)):
                if i == j:
                    continue

                idx_j, row_j, bbox_j = valid_rows[j]
                row_id_j = int(row_j['row_id'])

                iou = calculate_iou(bbox_i, bbox_j)

                cls_i = row_i['cls']
                cls_j = row_j['cls']
                same_class = (cls_i == cls_j)
                threshold = same_class_iou if same_class else cross_class_iou

                if iou >= threshold:
                    overlap_graph[row_id_i].append({
                        'row_id': row_id_j,
                        'iou': iou,
                        'cls': cls_j,
                        'row_data': row_j,
                        'same_class': same_class
                    })

        #  Filter: Only include boxes that DIRECTLY overlap with 2+ others
        # This excludes chains (A→B→C) and only finds true clusters
        multi_overlap_boxes = {}
        for row_id, neighbors in overlap_graph.items():
            if len(neighbors) >= 2:  # Must overlap with 2+ boxes directly
                multi_overlap_boxes[row_id] = neighbors

        print(f"Found {len(multi_overlap_boxes)} boxes with 2+ direct overlaps")

        if len(multi_overlap_boxes) < 3:
            print(f"Not enough boxes with multiple overlaps to form clusters")
            return issues

        #  Find unique clusters among boxes with 2+ overlaps
        visited = set()
        clusters = []

        def find_cluster(start_id):
            """DFS to find all connected boxes (only among multi-overlap boxes)"""
            cluster = set()
            stack = [start_id]

            while stack:
                current_id = stack.pop()
                if current_id in cluster:
                    continue
                cluster.add(current_id)

                # Add neighbors that also have 2+ overlaps
                for neighbor in multi_overlap_boxes.get(current_id, []):
                    neighbor_id = neighbor['row_id']
                    if neighbor_id in multi_overlap_boxes and neighbor_id not in cluster:
                        stack.append(neighbor_id)

            return cluster

        # Find all unique clusters
        for row_id in multi_overlap_boxes.keys():
            if row_id not in visited:
                cluster = find_cluster(row_id)

                # Report clusters of any size (already filtered for 2+ overlaps)
                if len(cluster) >= 1:
                    clusters.append(cluster)
                    visited.update(cluster)

        print(f"Found {len(clusters)} unique clusters of 3+ overlapping bboxes")

        # Create ONE warning per cluster
        for cluster in clusters:
            cluster_rows = [row for idx, row, bbox in valid_rows if int(row['row_id']) in cluster]

            if not cluster_rows:
                continue

            # Use first box as representative
            first_row = cluster_rows[0]
            row_id_rep = int(first_row['row_id'])

            # Collect cluster info
            cluster_row_ids = [int(r['row_id']) for r in cluster_rows]
            cluster_classes = [r['cls'] for r in cluster_rows]

            # Calculate average IoU across all pairs in cluster
            total_iou = 0
            pair_count = 0
            for row_id in cluster:
                for neighbor in overlap_graph.get(row_id, []):
                    if neighbor['row_id'] in cluster:
                        total_iou += neighbor['iou']
                        pair_count += 1
            avg_iou = total_iou / pair_count if pair_count > 0 else 0

            overlaps_found += 1
            print(f"Cluster of {len(cluster)} boxes: {', '.join(set(cluster_classes))} (rows: {cluster_row_ids})")

            severity = 'error' if avg_iou > 0.5 else 'warning'
            msg = f"YOLO Bbox-Cluster: {len(cluster)} Bboxen überlappen ({', '.join(set(cluster_classes))})"
            suggestion = f"Cluster mit {len(cluster)} überlappenden Bboxen: {cluster_row_ids}. Durchschnittliche IoU: {avg_iou:.0%}"

            issues.append(ValidationIssue(
                row_id=row_id_rep,
                severity=severity,
                category='bbox_overlap_cluster',
                field='bbox',
                message=msg,
                current_value=f"Cluster: {len(cluster)} Bboxen, IoU avg={avg_iou:.0%}",
                suggested_value=None,
                auto_correctable=False,
                confidence=1.0 - avg_iou,
                context={
                    'position': (float(first_row['xc']), float(first_row['yc'])),
                    'cluster_size': len(cluster),
                    'avg_iou': float(avg_iou),
                    'overlapping_rows': cluster_row_ids,
                    'overlapping_classes': cluster_classes,
                    'suggestion': suggestion,
                    'can_jump': True,
                    #  Overlapping bboxes - review or delete
                    'suggested_action': 'review',
                    'alternative_actions': ['delete'],
                    'action_description': f'{len(cluster)} überlappende Erkennungen (Avg IoU: {avg_iou:.0%}). Überprüfen und ggf. löschen.',
                }
            ))

        print(f"Bbox overlap check complete: Found {overlaps_found} bboxes in 3+ clusters, created {len(issues)} validation issues")
        return issues

    def _check_class_relationships(self) -> List[ValidationIssue]:
        """
         NEW: Validate expected class co-occurrences and relationships.

        Rules (all classes that need coordinates EXCEPT weichen_block):
        - signal → must have coordinate within 200px (error)
        - gks_gesteuert → must have coordinate within 150px (error)
        - gks_festkodiert → must have coordinate within 150px (error)
        - sverbinder → must have coordinate within 150px (error)
        - gm_block → must have coordinate within 150px (error)
        - prellbock → should have coordinate within 200px (warning)
        - haltepunkt → should have coordinate within 200px (warning)
        - haltetafel → should have coordinate within 200px (warning)
        - weichengruppenende → should have coordinate within 200px (warning)
        - weichenende → should have coordinate within 200px (warning)
        """
        issues = []

        if 'cls' not in self.df.columns or 'xc' not in self.df.columns or 'yc' not in self.df.columns:
            return issues

        # Get all coordinates
        coords = self.df[self.df['cls'] == 'coordinate']

        if coords.empty:
            # No coordinates at all - flag this as critical issue for all classes needing coords
            # Use same list as CLASSES_NEEDING_COORDS
            critical_classes = [
                'signal', 'gks_gesteuert', 'gks_festkodiert', 'isolierstoß',
                'prellbock', 'haltepunkt', 'sverbinder', 'gm_block',
                'haltetafel', 'weichenende', 'weichengruppenende'
            ]
            for cls in critical_classes:
                count = len(self.df[self.df['cls'] == cls])
                if count > 0:
                    issues.append(ValidationIssue(
                        row_id=-1,
                        severity='error',
                        category='missing_coordinates_global',
                        field='coordinate',
                        message=f"Keine Koordinaten erkannt, aber {count} {cls}-Objekte vorhanden",
                        current_value=None,
                        suggested_value="Koordinaten müssen erkannt werden",
                        auto_correctable=False,
                        confidence=1.0,
                        context={
                            'suggestion': f"Es wurden {count} {cls}-Objekte erkannt, aber keine Koordinaten. Überprüfen Sie die YOLO-Erkennung für Koordinaten.",
                            'can_jump': False,
                            #  Global issue - review entire document
                            'suggested_action': 'review',
                            'alternative_actions': [],
                            'action_description': 'Globales Problem: Keine Koordinaten erkannt. Überprüfen Sie die YOLO-Erkennung.',
                        }
                    ))
            return issues

        coord_positions = coords[['xc', 'yc']].values

        # Define class-specific requirements (all coordinate-linked classes except weichen_block)
        relationship_rules = {
            # Critical classes (errors if missing coordinate)
            'signal': {'max_distance': 200, 'severity': 'error', 'required': True},
            'gks_gesteuert': {'max_distance': 150, 'severity': 'error', 'required': True},
            'gks_festkodiert': {'max_distance': 150, 'severity': 'error', 'required': True},
            'sverbinder': {'max_distance': 150, 'severity': 'error', 'required': True},
            'gm_block': {'max_distance': 150, 'severity': 'error', 'required': True},
            # Optional classes (warnings if missing coordinate)
            'prellbock': {'max_distance': 200, 'severity': 'warning', 'required': False},
            'haltepunkt': {'max_distance': 200, 'severity': 'warning', 'required': False},
            'haltetafel': {'max_distance': 200, 'severity': 'warning', 'required': False},
            'weichengruppenende': {'max_distance': 200, 'severity': 'warning', 'required': False},
            'weichenende': {'max_distance': 200, 'severity': 'warning', 'required': False},
        }

        for cls, rule in relationship_rules.items():
            cls_df = self.df[self.df['cls'] == cls]

            for _, row in cls_df.iterrows():
                # Skip if position missing
                if pd.isna(row.get('xc')) or pd.isna(row.get('yc')):
                    continue

                obj_pos = np.array([row['xc'], row['yc']])

                # Find nearest coordinate
                distances = np.linalg.norm(coord_positions - obj_pos, axis=1)
                min_distance = distances.min() if len(distances) > 0 else float('inf')

                # Check if coordinate is within acceptable range
                if min_distance > rule['max_distance']:
                    severity = rule['severity']
                    required_text = "erforderlich" if rule['required'] else "empfohlen"

                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity=severity,
                        category='missing_relationship',
                        field='coord_text',
                        message=f"{cls}: Keine Koordinate in Nähe ({required_text}, nächste: {min_distance:.0f}px)",
                        current_value=row.get('coord_text', 'None'),
                        suggested_value=f"Koordinate innerhalb {rule['max_distance']}px {required_text}",
                        auto_correctable=False,
                        confidence=min(1.0, min_distance / rule['max_distance']),
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'min_distance': float(min_distance),
                            'max_distance': rule['max_distance'],
                            'suggestion': f"{cls} (Zeile {row['row_id']}) hat keine Koordinate in Nähe. Nächste Koordinate ist {min_distance:.0f}px entfernt (>{rule['max_distance']}px). {'Koordinate ist erforderlich.' if rule['required'] else 'Koordinate wird empfohlen.'}",
                            'can_jump': True
                        }
                    ))

        return issues

    def _check_false_positives(self) -> List[ValidationIssue]:
        """
         NEW: Detect likely false positive YOLO detections.

        Flags detections with multiple red flags:
        - Low confidence (<0.4) + missing OCR text
        - Low confidence + no coordinate relationship
        - Missing text + no coordinate (for classes that need both)

        Simple and direct: tells user which detections to remove.
        """
        issues = []

        if 'conf' not in self.df.columns or 'cls' not in self.df.columns:
            return issues

        # Classes that MUST have OCR text
        text_required_classes = ['signal', 'gks_gesteuert', 'gks_festkodiert']

        # Classes that MUST have coordinate nearby (same as CLASSES_NEEDING_COORDS)
        coord_required_classes = [
            'signal', 'gks_gesteuert', 'gks_festkodiert', 'isolierstoß',
            'prellbock', 'haltepunkt', 'sverbinder', 'gm_block',
            'haltetafel', 'weichenende', 'weichengruppenende'
        ]

        # Get all coordinates for distance checks
        coords = self.df[self.df['cls'] == 'coordinate']
        coord_positions = coords[['xc', 'yc']].values if not coords.empty else np.array([])

        for _, row in self.df.iterrows():
            cls = row.get('cls')
            conf = row.get('conf', 1.0)
            row_id = row.get('row_id', -1)

            # Skip coordinates themselves
            if cls == 'coordinate':
                continue

            # Check for position data
            if pd.isna(row.get('xc')) or pd.isna(row.get('yc')):
                continue

            red_flags = []
            flag_score = 0

            # RED FLAG 1: Low confidence
            if conf < 0.4:
                red_flags.append(f"sehr niedrige Konfidenz ({conf:.2f})")
                flag_score += 40
            elif conf < 0.5:
                red_flags.append(f"niedrige Konfidenz ({conf:.2f})")
                flag_score += 20

            # RED FLAG 2: Missing OCR text for classes that need it
            if cls in text_required_classes:
                anchor_text = row.get('anchor_text', '')
                if pd.isna(anchor_text) or anchor_text == '':
                    red_flags.append("kein OCR-Text erkannt")
                    flag_score += 30

            # RED FLAG 3: No coordinate nearby for classes that need it
            if cls in coord_required_classes and len(coord_positions) > 0:
                obj_pos = np.array([row['xc'], row['yc']])
                distances = np.linalg.norm(coord_positions - obj_pos, axis=1)
                min_distance = distances.min() if len(distances) > 0 else float('inf')

                max_allowed = 200 if cls == 'signal' else 150
                if min_distance > max_allowed:
                    red_flags.append(f"keine Koordinate in Nähe ({min_distance:.0f}px)")
                    flag_score += 20

            # Only flag if multiple red flags (score >= 50)
            if flag_score >= 50:
                severity = 'error' if flag_score >= 70 else 'warning'

                issues.append(ValidationIssue(
                    row_id=row_id,
                    severity=severity,
                    category='likely_false_positive',
                    field='detection',
                    message=f"Wahrscheinlich Fehl-Erkennung: {', '.join(red_flags)}",
                    current_value=f"{cls} (conf={conf:.2f})",
                    suggested_value="Überprüfen und ggf. löschen",
                    auto_correctable=False,
                    confidence=min(1.0, flag_score / 100.0),
                    context={
                        'position': (float(row['xc']), float(row['yc'])),
                        'red_flags': red_flags,
                        'flag_score': flag_score,
                        'suggestion': f"Diese {cls}-Erkennung hat mehrere verdächtige Merkmale: {', '.join(red_flags)}. Überprüfen Sie, ob dies eine Fehl-Erkennung ist.",
                        'can_jump': True,
                        #  False positive detection - delete
                        'suggested_action': 'delete',
                        'alternative_actions': ['review'],
                        'action_description': f'Wahrscheinliche Fehl-Erkennung: {", ".join(red_flags)}. Überprüfen und ggf. löschen.',
                    }
                ))

        return issues

    def _check_coordinate_patterns(self) -> List[ValidationIssue]:
        """
         NEW: Check if coordinates match the majority pattern.

        Instead of flagging coordinate gaps (too aggressive), this checks
        if coordinate values follow the same format as the majority.

        Examples:
        - Majority: "0,0260", "0,0269", "5,8132" (format: d,dddd)
        - Outlier: "10.5", "ABC", "999" (doesn't match)
        """
        issues = []

        coords = self.df[self.df['cls'] == 'coordinate'].copy()

        if len(coords) < 3:  # Need at least 3 coordinates to establish pattern
            return issues

        if 'coord_value' not in coords.columns:
            return issues

        # Filter valid coordinate values
        valid_coords = coords[coords['coord_value'].notna()].copy()

        if len(valid_coords) < 3:
            return issues

        # Analyze patterns
        import re
        from collections import Counter

        def extract_pattern(value):
            """Extract pattern from coordinate value"""
            val_str = str(value)

            # Check format patterns
            if re.match(r'^\d+,\d{4}$', val_str):  # e.g., "0,0260"
                return 'digit_comma_4digits'
            elif re.match(r'^\d+\.\d+$', val_str):  # e.g., "10.5"
                return 'decimal_dot'
            elif re.match(r'^\d+,\d+$', val_str):  # e.g., "10,5"
                return 'decimal_comma'
            elif re.match(r'^\d+$', val_str):  # e.g., "105"
                return 'integer'
            else:
                return 'unknown'

        # Find majority pattern
        patterns = valid_coords['coord_value'].apply(extract_pattern)
        pattern_counts = Counter(patterns)

        if not pattern_counts:
            return issues

        majority_pattern, majority_count = pattern_counts.most_common(1)[0]

        # Only flag if majority is clear (>60% of coordinates)
        if majority_count < len(valid_coords) * 0.6:
            return issues

        # Flag coordinates that don't match majority pattern
        for _, row in valid_coords.iterrows():
            coord_val = row['coord_value']
            pattern = extract_pattern(coord_val)

            if pattern != majority_pattern:
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='warning',
                    category='coordinate_pattern_mismatch',
                    field='coord_value',
                    message=f"Koordinatenformat weicht ab: {coord_val} (Format: {pattern}, erwartet: {majority_pattern})",
                    current_value=str(coord_val),
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=0.7,
                    context={
                        'position': (float(row['xc']), float(row['yc'])) if pd.notna(row.get('xc')) and pd.notna(row.get('yc')) else None,
                        'pattern': pattern,
                        'expected_pattern': majority_pattern,
                        'suggestion': f"Koordinate '{coord_val}' hat Format '{pattern}', aber {majority_count}/{len(valid_coords)} Koordinaten haben Format '{majority_pattern}'. Überprüfen Sie ob OCR korrekt ist.",
                        'can_jump': True,
                        #  Pattern mismatch - OCR issue
                        'suggested_action': 'bbox_resize',
                        'alternative_actions': ['manual_ocr_horizontal', 'manual_edit'],
                        'action_description': f'Koordinatenformat weicht ab. Passen Sie die Erkennungsfläche an oder korrigieren Sie manuell.',
                    }
                ))

        return issues

    def _check_ocr_text_outliers(self) -> List[ValidationIssue]:
        """
        Detect OCR text that doesn't fit the pattern of others in the same class.

        Checks:
        - signal: anchor_text should be letter(s) + number (e.g., "A1", "N12", "AA5")
        - gks_gesteuert/gks_festkodiert: anchor_text should be numbers only (e.g., "12 34")

        Flags texts that deviate significantly from the majority pattern in their class.
        """
        issues = []

        import re
        from collections import Counter

        if 'anchor_text' not in self.df.columns:
            return issues

        # =====================================================================
        # CHECK 1: Signal text pattern outliers
        # =====================================================================
        signals = self.df[self.df['cls'] == 'signal'].copy()
        signals = signals[signals['anchor_text'].notna() & (signals['anchor_text'] != '')]

        if len(signals) >= 3:
            def classify_signal_text(text):
                """Classify signal text pattern"""
                text = str(text).strip()
                if not text:
                    return 'empty'
                # Common patterns: A1, N12, AA5, P1, etc.
                if re.match(r'^[A-ZÄÖÜ]{1,3}\d{1,3}$', text):
                    return 'letter_number'  # Standard: A1, N12, AA5
                elif re.match(r'^\d{1,3}[A-ZÄÖÜ]{1,3}$', text):
                    return 'number_letter'  # Reversed: 1A, 12N
                elif re.match(r'^[A-ZÄÖÜ]+$', text):
                    return 'letters_only'
                elif re.match(r'^\d+$', text):
                    return 'numbers_only'
                elif re.match(r'^[A-ZÄÖÜ]{1,3}\d{1,3}[A-ZÄÖÜ]$', text):
                    return 'letter_number_letter'  # A1a, N12b
                else:
                    return 'other'

            # Find majority pattern
            signal_patterns = signals['anchor_text'].apply(classify_signal_text)
            pattern_counts = Counter(signal_patterns)

            if pattern_counts:
                majority_pattern, majority_count = pattern_counts.most_common(1)[0]

                # Only flag if majority is clear (>50% of signals)
                if majority_count >= len(signals) * 0.5:
                    for _, row in signals.iterrows():
                        text = str(row['anchor_text']).strip()
                        pattern = classify_signal_text(text)

                        if pattern != majority_pattern and pattern != 'empty':
                            issues.append(ValidationIssue(
                                row_id=row['row_id'],
                                severity='warning',
                                category='ocr_text_outlier',
                                field='anchor_text',
                                message=f"Signal-Text weicht ab: '{text}' (Format: {pattern}, Mehrheit: {majority_pattern})",
                                current_value=text,
                                suggested_value=None,
                                auto_correctable=False,
                                confidence=0.7,
                                context={
                                    'position': (float(row['xc']), float(row['yc'])) if pd.notna(row.get('xc')) and pd.notna(row.get('yc')) else None,
                                    'pattern': pattern,
                                    'expected_pattern': majority_pattern,
                                    'class': 'signal',
                                    'suggestion': f"Signal-Text '{text}' hat Format '{pattern}', aber {majority_count}/{len(signals)} Signale haben Format '{majority_pattern}'. Möglicherweise OCR-Fehler.",
                                    'can_jump': True,
                                    'suggested_action': 'review',
                                    'alternative_actions': ['manual_edit', 'bbox_resize'],
                                    'action_description': f'Text weicht vom Mehrheitsmuster ab. Prüfen Sie ob OCR korrekt ist.',
                                }
                            ))

        # =====================================================================
        # CHECK 2: GKS text pattern outliers (should be numbers only)
        # =====================================================================
        for gks_class in ['gks_gesteuert', 'gks_festkodiert']:
            gks_df = self.df[self.df['cls'] == gks_class].copy()
            gks_df = gks_df[gks_df['anchor_text'].notna() & (gks_df['anchor_text'] != '')]

            if len(gks_df) >= 3:
                def classify_gks_text(text):
                    """Classify GKS text pattern"""
                    text = str(text).strip()
                    if not text:
                        return 'empty'
                    # Remove spaces and dashes for analysis
                    cleaned = text.replace(' ', '').replace('-', '')
                    if cleaned.isdigit():
                        return 'numbers_only'
                    elif any(c.isalpha() for c in cleaned):
                        return 'contains_letters'
                    else:
                        return 'other'

                # Find majority pattern
                gks_patterns = gks_df['anchor_text'].apply(classify_gks_text)
                pattern_counts = Counter(gks_patterns)

                if pattern_counts:
                    majority_pattern, majority_count = pattern_counts.most_common(1)[0]

                    # GKS should always be numbers - flag any with letters
                    for _, row in gks_df.iterrows():
                        text = str(row['anchor_text']).strip()
                        pattern = classify_gks_text(text)

                        # Flag if contains letters (always wrong for GKS)
                        if pattern == 'contains_letters':
                            issues.append(ValidationIssue(
                                row_id=row['row_id'],
                                severity='warning',
                                category='ocr_text_outlier',
                                field='anchor_text',
                                message=f"{gks_class}-Text enthält Buchstaben: '{text}' (sollte nur Zahlen sein)",
                                current_value=text,
                                suggested_value=None,
                                auto_correctable=False,
                                confidence=0.8,
                                context={
                                    'position': (float(row['xc']), float(row['yc'])) if pd.notna(row.get('xc')) and pd.notna(row.get('yc')) else None,
                                    'pattern': pattern,
                                    'expected_pattern': 'numbers_only',
                                    'class': gks_class,
                                    'suggestion': f"GKS-Text '{text}' enthält Buchstaben, sollte aber nur Zahlen enthalten. Wahrscheinlich OCR-Fehler (z.B. O statt 0, I statt 1).",
                                    'can_jump': True,
                                    'suggested_action': 'manual_edit',
                                    'alternative_actions': ['bbox_resize', 'manual_ocr_horizontal'],
                                    'action_description': f'GKS-Text sollte nur Zahlen enthalten. Korrigieren Sie den Text (z.B. O→0, I→1, S→5).',
                                }
                            ))
                        # Also flag if pattern differs from majority (and majority is numbers)
                        elif pattern != majority_pattern and majority_pattern == 'numbers_only':
                            issues.append(ValidationIssue(
                                row_id=row['row_id'],
                                severity='warning',
                                category='ocr_text_outlier',
                                field='anchor_text',
                                message=f"{gks_class}-Text weicht ab: '{text}' (Format: {pattern})",
                                current_value=text,
                                suggested_value=None,
                                auto_correctable=False,
                                confidence=0.6,
                                context={
                                    'position': (float(row['xc']), float(row['yc'])) if pd.notna(row.get('xc')) and pd.notna(row.get('yc')) else None,
                                    'pattern': pattern,
                                    'expected_pattern': majority_pattern,
                                    'class': gks_class,
                                    'suggestion': f"GKS-Text '{text}' hat Format '{pattern}', aber {majority_count}/{len(gks_df)} haben Format '{majority_pattern}'.",
                                    'can_jump': True,
                                    'suggested_action': 'review',
                                    'alternative_actions': ['manual_edit'],
                                    'action_description': f'Text weicht vom Mehrheitsmuster ab.',
                                }
                            ))

        # =====================================================================
        # CHECK 3: Text length outliers (unusually long or short)
        # =====================================================================
        for cls in ['signal', 'gks_gesteuert', 'gks_festkodiert']:
            cls_df = self.df[self.df['cls'] == cls].copy()
            cls_df = cls_df[cls_df['anchor_text'].notna() & (cls_df['anchor_text'] != '')]

            if len(cls_df) >= 5:
                # Calculate text lengths
                lengths = cls_df['anchor_text'].apply(lambda x: len(str(x).strip()))
                median_len = lengths.median()

                # Flag texts that are significantly longer or shorter than median
                for _, row in cls_df.iterrows():
                    text = str(row['anchor_text']).strip()
                    text_len = len(text)

                    # Flag if >3x median length or <0.3x median length (and median is reasonable)
                    if median_len >= 2:
                        if text_len > median_len * 3 and text_len > 10:
                            issues.append(ValidationIssue(
                                row_id=row['row_id'],
                                severity='warning',
                                category='ocr_text_length_outlier',
                                field='anchor_text',
                                message=f"{cls}-Text ungewöhnlich lang: '{text[:20]}...' ({text_len} Zeichen, Median: {median_len:.0f})",
                                current_value=text,
                                suggested_value=None,
                                auto_correctable=False,
                                confidence=0.6,
                                context={
                                    'position': (float(row['xc']), float(row['yc'])) if pd.notna(row.get('xc')) and pd.notna(row.get('yc')) else None,
                                    'text_length': text_len,
                                    'median_length': float(median_len),
                                    'class': cls,
                                    'suggestion': f"Text ist {text_len} Zeichen lang, aber Median ist {median_len:.0f}. Möglicherweise wurde mehr Text erkannt als nötig.",
                                    'can_jump': True,
                                    'suggested_action': 'bbox_resize',
                                    'alternative_actions': ['manual_edit'],
                                    'action_description': f'Ungewöhnlich langer Text. Verkleinern Sie die Bbox oder korrigieren Sie manuell.',
                                }
                            ))

        print(f"OCR text outlier check: Found {len(issues)} text pattern issues")
        return issues

    def _check_size_outliers(self, std_threshold: float = 2.5) -> List[ValidationIssue]:
        """Automatic size outlier detection using statistics"""
        issues = []
        
        if not all(col in self.df.columns for col in ['w', 'h', 'cls', 'xc', 'yc']):
            return issues
        
        for cls in self.df['cls'].unique():
            cls_df = self.df[self.df['cls'] == cls].copy()
            
            #  Filter out rows with missing data
            cls_df = cls_df[cls_df['w'].notna() & cls_df['h'].notna() & 
                           cls_df['xc'].notna() & cls_df['yc'].notna()]
            
            if len(cls_df) < 5:  # Need at least 5 samples for statistics
                continue
            
            w_mean = cls_df['w'].mean()
            w_std = cls_df['w'].std()
            h_mean = cls_df['h'].mean()
            h_std = cls_df['h'].std()
            
            if w_std < 1 or h_std < 1:  # Too uniform, skip
                continue
            
            for _, row in cls_df.iterrows():
                w = row['w']
                h = row['h']
                
                w_zscore = abs(w - w_mean) / w_std if w_std > 0 else 0
                h_zscore = abs(h - h_mean) / h_std if h_std > 0 else 0
                
                if w_zscore > std_threshold or h_zscore > std_threshold:
                    if w < w_mean * 0.5 or h < h_mean * 0.5:
                        size_desc = "sehr klein"
                        suggestion = f"Ungewöhnlich kleine {cls}-Erkennung ({w:.0f}×{h:.0f}px, typisch: {w_mean:.0f}×{h_mean:.0f}px). Könnte Rauschen oder Teilobjekt sein."
                    else:
                        size_desc = "sehr groß"
                        suggestion = f"Ungewöhnlich große {cls}-Erkennung ({w:.0f}×{h:.0f}px, typisch: {w_mean:.0f}×{h_mean:.0f}px). Könnte mehrere Objekte enthalten."
                    
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='warning',
                        category='yolo_size',
                        field='size',
                        message=f"YOLO: {cls} ungewöhnliche Größe ({w:.0f}×{h:.0f}px, {size_desc})",
                        current_value=f"{w:.0f}×{h:.0f}",
                        suggested_value=f"Typisch: {w_mean:.0f}×{h_mean:.0f}",
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'w_mean': float(w_mean),
                            'h_mean': float(h_mean),
                            'w_zscore': float(w_zscore),
                            'h_zscore': float(h_zscore),
                            'suggestion': suggestion,
                            'can_jump': True
                        }
                    ))
        
        return issues
    
    # ========================================================================
    # MISSING DATA DETECTION
    # ========================================================================
    
    def _check_missing_coordinates_spatial(self) -> List[ValidationIssue]:
        """Check if elements are missing nearby coordinates (using YOUR class list)"""
        issues = []
        
        coords = self.df[self.df['cls'] == 'coordinate']
        
        if coords.empty:
            return issues
        
        #  Use existing columns (already created in __init__)
        coord_positions = coords[['xc', 'yc']].values
        
        #  Use YOUR class list (excluding weichen_block)
        for cls in self.CLASSES_NEEDING_COORDS:
            # Skip weichen_block from missing coordinate check
            if cls == 'weichen_block':
                continue

            cls_df = self.df[self.df['cls'] == cls]
            
            for _, row in cls_df.iterrows():
                #  Skip if position is missing
                if pd.isna(row.get('xc')) or pd.isna(row.get('yc')):
                    continue
                
                obj_pos = np.array([row['xc'], row['yc']])
                
                distances = np.linalg.norm(coord_positions - obj_pos, axis=1)
                min_dist = distances.min() if len(distances) > 0 else float('inf')

                #  Default threshold for all classes (weichen_block is filtered out)
                threshold = 500
                
                if min_dist > threshold:
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='warning',
                        category='missing_coordinate',
                        field='coordinate',
                        message=f"{cls}: Keine Koordinate verknüpft",
                        current_value=None,
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'nearest_coord_distance': float(min_dist),
                            'threshold': threshold,
                            'suggestion': f'YOLO hat möglicherweise eine Koordinate übersehen. Überprüfen Sie den Bereich um ({row["xc"]:.0f}, {row["yc"]:.0f}).',
                            'can_jump': True,
                            #  Add manual correction actions
                            'suggested_action': 'manual_link',
                            'alternative_actions': ['manual_ocr_horizontal', 'review'],
                            'action_description': 'Koordinate manuell verknüpfen. Verwenden Sie den Button "Koordinate manuell verknüpfen".',
                        }
                    ))
        
        return issues
    
    def _check_missing_text(self) -> List[ValidationIssue]:
        """Check if elements that should have text are missing it"""
        issues = []
        
        if 'anchor_text' not in self.df.columns:
            return issues
        
        for cls in self.CLASSES_NEEDING_TEXT:
            cls_df = self.df[self.df['cls'] == cls]
            
            for _, row in cls_df.iterrows():
                anchor_text = row.get('anchor_text', '')
                
                #  Check if text is missing or empty
                if pd.isna(anchor_text) or not str(anchor_text).strip():
                    #  Skip if position is missing
                    if pd.isna(row.get('xc')) or pd.isna(row.get('yc')):
                        continue
                    
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='warning',
                        category='missing_text',
                        field='anchor_text',
                        message=f"{cls}: Text fehlt oder leer",
                        current_value="(leer)",
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'suggestion': f'OCR konnte keinen Text erkennen. Vergrößern Sie die Erkennungsfläche durch Bbox-Anpassung.',
                            'can_jump': True,
                            #  Bbox resize as primary action (faster and more intuitive)
                            'suggested_action': 'bbox_resize',
                            'alternative_actions': ['manual_ocr_horizontal', 'delete'],
                            'action_description': f'{cls}-Text wurde nicht erkannt. Passen Sie die Erkennungsfläche an (Bbox-Kanten ziehen).',
                        }
                    ))
        
        return issues
    
    def _check_isolated_detections(self, isolation_distance: float = 1000) -> List[ValidationIssue]:
        """Flag objects far from others (might be noise)"""
        issues = []
        
        if not all(col in self.df.columns for col in ['xc', 'yc', 'cls']):
            return issues
        
        for cls in self.df['cls'].unique():
            cls_df = self.df[self.df['cls'] == cls].copy()
            
            #  Filter out rows with missing positions
            cls_df = cls_df[cls_df['xc'].notna() & cls_df['yc'].notna()]
            
            if len(cls_df) < 3:  # Need at least 3 to detect isolation
                continue
            
            positions = cls_df[['xc', 'yc']].values
            
            for i, row in cls_df.iterrows():
                obj_pos = positions[cls_df.index.get_loc(i)]
                other_positions = np.delete(positions, cls_df.index.get_loc(i), axis=0)
                distances = np.linalg.norm(other_positions - obj_pos, axis=1)
                min_dist = distances.min() if len(distances) > 0 else float('inf')
                
                if min_dist > isolation_distance:
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='warning',
                        category='isolated_object',
                        field='position',
                        message=f"Isoliertes Objekt: {cls} weit von anderen entfernt ({min_dist:.0f}px)",
                        current_value=f"({row['xc']:.0f}, {row['yc']:.0f})",
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'min_distance': float(min_dist),
                            'suggestion': f'Weit von anderen {cls} entfernt ({min_dist:.0f}px). Möglicherweise Rauschen oder Fehlerkennung.',
                            'can_jump': True
                        }
                    ))
        
        return issues
    
    def _check_expected_ratios(self) -> List[ValidationIssue]:
        """Check for unusual object count ratios"""
        issues = []

        #  Count LINKED coordinates (elements with coord_text filled) not standalone coordinates
        # Since we filter out cls='coordinate', we count elements that HAVE coordinates
        coord_count = len(self.df[self.df['coord_text'].notna() & (self.df['coord_text'] != '')])

        signal_count = len(self.df[self.df['cls'] == 'signal'])
        gks_count = len(self.df[self.df['cls'].isin(['gks_gesteuert', 'gks_festkodiert'])])
        #  weichen_block filtered out, so always 0 - removed from calculation

        total_objects = signal_count + gks_count

        #  Too few coordinates - check if most objects are missing coordinates
        if total_objects > 5 and coord_count < total_objects * 0.3:
            issues.append(ValidationIssue(
                row_id=-1,
                severity='error',
                category='missing_data',
                field='coordinates',
                message=f"Zu wenige Koordinaten: Nur {coord_count} von {total_objects} Objekten haben Koordinaten",
                current_value=str(coord_count),
                suggested_value=f"Erwartet: ≥{int(total_objects * 0.3)}",
                auto_correctable=False,
                confidence=0.0,
                context={
                    'suggestion': f'Viele Objekte haben keine verknüpften Koordinaten ({coord_count}/{total_objects}). Überprüfen Sie das Dokument.',
                    'signal_count': signal_count,
                    'gks_count': gks_count,
                    'coord_count': coord_count,
                    'can_jump': False,  # Global check, no specific row
                    #  Global review action
                    'suggested_action': 'review',
                    'alternative_actions': [],
                    'action_description': 'Globale Prüfung: Zu viele Objekte ohne Koordinaten. Überprüfen Sie das gesamte Dokument.',
                }
            ))
        
        #  Unusually few signals
        if gks_count > 10 and signal_count < gks_count * 0.3:
            issues.append(ValidationIssue(
                row_id=-1,
                severity='warning',
                category='missing_data',
                field='signals',
                message=f"Wenige Signale: Nur {signal_count} für {gks_count} GKS-Kästen",
                current_value=str(signal_count),
                suggested_value=f"Erwartet: ≥{int(gks_count * 0.3)}",
                auto_correctable=False,
                confidence=0.0,
                context={
                    'suggestion': f'YOLO hat möglicherweise einige Signale nicht erkannt. Überprüfen Sie Bereiche mit GKS-Kästen.',
                    'signal_count': signal_count,
                    'gks_count': gks_count,
                    'can_jump': False,  # Global check
                    #  Global review action
                    'suggested_action': 'review',
                    'alternative_actions': [],
                    'action_description': 'Globale Prüfung: Ungewöhnlich wenig Signale für die Anzahl GKS. Überprüfen Sie das Dokument.',
                }
            ))
        
        return issues

    def _check_cross_references(self) -> List[ValidationIssue]:
        """
         NEW: Cross-reference validation for data consistency.

        Checks:
        - Coordinate sequence gaps (e.g., 10.5, 10.7, 11.0 → 10.6 missing?)

        Note: Duplicate coordinate values and signal IDs are expected in railway layouts,
        so those checks have been removed.
        """
        issues = []

        if 'coord_value' not in self.df.columns:
            return issues

        # ============================================================
        # COORDINATE SEQUENCE GAPS
        # ============================================================
        coords = self.df[self.df['cls'] == 'coordinate'].copy()

        if not coords.empty and 'coord_value' in coords.columns:
            coords_with_values = coords[coords['coord_value'].notna()].copy()
        else:
            coords_with_values = pd.DataFrame()

        if not coords_with_values.empty:
            # Sort by coordinate value (using sort key for Antwerp string format)
            coords_with_values['_sort_key'] = coords_with_values['coord_value'].apply(coord_to_sort_key)
            coords_sorted = coords_with_values.sort_values('_sort_key').drop(columns=['_sort_key']).copy()

            # Group by page
            for page in coords_sorted['page'].unique():
                page_coords = coords_sorted[coords_sorted['page'] == page].copy()

                if len(page_coords) < 2:
                    continue

                values = page_coords['coord_value'].values

                for i in range(len(values) - 1):
                    curr_val = values[i]
                    next_val = values[i + 1]

                    if pd.isna(curr_val) or pd.isna(next_val):
                        continue

                    # Convert to numeric for gap calculation (handles Antwerp string format)
                    curr_numeric = coord_to_sort_key(curr_val)
                    next_numeric = coord_to_sort_key(next_val)

                    if curr_numeric is None or next_numeric is None:
                        continue

                    gap = next_numeric - curr_numeric

                    # Flag large gaps (> 0.5 km = 500m typically indicates missing coordinate)
                    if gap > 0.5:
                        row = page_coords.iloc[i]

                        issues.append(ValidationIssue(
                            row_id=row['row_id'],
                            severity='warning',
                            category='coordinate_sequence_gap',
                            field='coord_value',
                            message=f"Große Lücke in Koordinatensequenz: {curr_val:.3f} → {next_val:.3f} (Δ={gap:.3f})",
                            current_value=f"{curr_val:.3f}",
                            suggested_value=None,
                            auto_correctable=False,
                            confidence=min(1.0, gap / 1.0),  # Higher gap = higher confidence it's an issue
                            context={
                                'position': (float(row['xc']), float(row['yc'])) if pd.notna(row.get('xc')) and pd.notna(row.get('yc')) else None,
                                'gap_size': float(gap),
                                'suggestion': f"Zwischen Koordinaten {curr_val:.3f} und {next_val:.3f} ist eine große Lücke ({gap:.3f}). Möglicherweise fehlt eine Koordinate dazwischen.",
                                'can_jump': True
                            }
                        ))

        return issues

    def compute_quality_metrics(self) -> Dict:
        """
         NEW: Compute comprehensive quality metrics for YOLO and OCR.

        Returns dict with metrics suitable for database storage.
        """
        metrics = {}

        if self.df is None or self.df.empty:
            return metrics

        # ============================================================
        # YOLO CONFIDENCE METRICS
        # ============================================================
        if 'conf' in self.df.columns and 'cls' in self.df.columns:
            # Overall confidence
            metrics['avg_confidence_all'] = float(self.df['conf'].mean())
            metrics['min_confidence_all'] = float(self.df['conf'].min())
            metrics['max_confidence_all'] = float(self.df['conf'].max())
            metrics['std_confidence_all'] = float(self.df['conf'].std())

            # Per-class confidence
            for cls in self.df['cls'].unique():
                cls_df = self.df[self.df['cls'] == cls]
                if not cls_df.empty:
                    metrics[f'avg_confidence_{cls}'] = float(cls_df['conf'].mean())
                    metrics[f'min_confidence_{cls}'] = float(cls_df['conf'].min())
                    metrics[f'count_{cls}'] = int(len(cls_df))

                    # Low confidence count
                    expected_threshold = self.CONFIDENCE_THRESHOLDS.get(cls, 0.5)
                    low_conf_count = len(cls_df[cls_df['conf'] < expected_threshold])
                    metrics[f'low_confidence_count_{cls}'] = int(low_conf_count)

            # Per-page confidence (if page column exists)
            if 'page' in self.df.columns:
                for page in self.df['page'].unique():
                    page_df = self.df[self.df['page'] == page]
                    if not page_df.empty:
                        metrics[f'avg_confidence_page_{page}'] = float(page_df['conf'].mean())

        # ============================================================
        # DETECTION COUNTS
        # ============================================================
        if 'cls' in self.df.columns:
            for cls in self.df['cls'].unique():
                count = len(self.df[self.df['cls'] == cls])
                metrics[f'total_{cls}'] = int(count)

            # Total detections
            metrics['total_detections'] = int(len(self.df))

        # ============================================================
        # OCR QUALITY METRICS
        # ============================================================
        if 'coord_text' in self.df.columns:
            coords = self.df[self.df['cls'] == 'coordinate']
            if not coords.empty:
                # OCR success rate
                ocr_success = coords['coord_text'].notna().sum()
                metrics['coord_ocr_success_rate'] = float(ocr_success / len(coords))

        if 'anchor_text' in self.df.columns:
            signals = self.df[self.df['cls'] == 'signal']
            if not signals.empty:
                ocr_success = signals['anchor_text'].notna().sum()
                metrics['signal_ocr_success_rate'] = float(ocr_success / len(signals))

        # ============================================================
        # LINKING QUALITY
        # ============================================================
        if 'coord_value' in self.df.columns:
            # Anchors with coordinates
            anchors = self.df[self.df['cls'].isin(self.CLASSES_NEEDING_COORDS)]
            if not anchors.empty:
                linked_count = anchors['coord_value'].notna().sum()
                metrics['anchor_linking_success_rate'] = float(linked_count / len(anchors))

        return metrics

    # ========================================================================
    # TEMPLATE MATCHING VALIDATION - Helper Functions
    # ========================================================================

    def _get_template_threshold(self, symbol_name: str) -> float:
        """Get similarity threshold from symbol definition"""
        if self.symbol_detector and symbol_name in self.symbol_detector.symbols:
            return self.symbol_detector.symbols[symbol_name].similarity_threshold
        return 0.75  # Default

    def _symbol_needs_coordinate(self, symbol_name: str) -> bool:
        """Check if template symbol requires coordinate linking"""
        if self.symbol_detector and symbol_name in self.symbol_detector.symbols:
            return self.symbol_detector.symbols[symbol_name].links_to_coordinate
        return False

    def _symbol_needs_text(self, symbol_name: str) -> bool:
        """Check if template symbol requires text/ID"""
        if self.symbol_detector and symbol_name in self.symbol_detector.symbols:
            return self.symbol_detector.symbols[symbol_name].has_text
        return False

    def _get_template_text_pattern(self, symbol_name: str) -> str:
        """Get text pattern from symbol definition"""
        if self.symbol_detector and symbol_name in self.symbol_detector.symbols:
            return self.symbol_detector.symbols[symbol_name].text_pattern
        return None

    def _get_max_link_distance(self, symbol_name: str) -> int:
        """Get max link distance from symbol definition"""
        if self.symbol_detector and symbol_name in self.symbol_detector.symbols:
            return self.symbol_detector.symbols[symbol_name].max_link_distance
        return 150  # Default

    def _get_template_avg_size(self, symbol_name: str) -> float:
        """Get average template size from examples"""
        if self.symbol_detector and symbol_name in self.symbol_detector.symbols:
            symbol_def = self.symbol_detector.symbols[symbol_name]
            if symbol_def.templates:
                sizes = [(t.shape[1] + t.shape[0]) / 2 for t in symbol_def.templates]
                return sum(sizes) / len(sizes) if sizes else 0
        return 0

    def _matches_text_pattern(self, text: str, pattern: str) -> bool:
        """Check if text matches expected pattern"""
        if not pattern or not text:
            return True

        import re
        # Map user-friendly patterns to regex
        pattern_map = {
            "Nur Zahlen": r"^\d+$",
            "Buchstaben + Zahlen": r"^[A-Z]+\d+$",
            "Signal-ID": r"^[A-ZÄÖÜ]{1,2}\d{1,3}$",
            "Nur Buchstaben": r"^[A-ZÄÖÜ]+$",
            "Koordinate": r"^\d+\+\d+$",
        }

        regex = pattern_map.get(pattern, pattern)
        return bool(re.match(regex, text))

    def _could_auto_correct_text(self, text: str, pattern: str) -> bool:
        """Check if text can be auto-corrected to match pattern"""
        if pattern == "Nur Zahlen":
            # Check if it's almost numeric (e.g., "O12" → "012")
            cleaned = text.replace('O', '0').replace('I', '1').replace('S', '5').replace('B', '8').replace('Z', '2')
            return cleaned.isdigit()
        return False

    def _auto_correct_text(self, text: str, pattern: str) -> str:
        """Auto-correct text to match pattern"""
        if pattern == "Nur Zahlen":
            return text.replace('O', '0').replace('I', '1').replace('S', '5').replace('B', '8').replace('Z', '2')
        return text

    def _calculate_template_fp_score(self, row: pd.Series) -> tuple:
        """
        Calculate false positive likelihood score (0-100+).
        Returns (score, list of reasons).
        """
        score = 0
        reasons = []

        #  FIX: Template symbols use 'cls' field, not 'name'
        symbol_name = row.get('cls', '')

        # Check 1: Missing required coordinate (50 points)
        #  FIX: Template symbols use 'coord_value', not 'linked_coordinate'
        if self._symbol_needs_coordinate(symbol_name) and not row.get('coord_value'):
            score += 50
            reasons.append("Keine Koordinate verknüpft (+50)")

        # Check 2: Missing required text (40 points)
        if self._symbol_needs_text(symbol_name):
            #  FIX: Template symbols use 'anchor_text', not 'text'
            text = row.get('anchor_text', '')
            if not text or len(str(text)) < 2:
                score += 40
                reasons.append("Text-ID fehlt (+40)")

        # Check 3: Text pattern mismatch (35 points)
        text_pattern = self._get_template_text_pattern(symbol_name)
        if text_pattern:
            #  FIX: Template symbols use 'anchor_text', not 'text'
            text = row.get('anchor_text', '')
            if text and not self._matches_text_pattern(str(text), text_pattern):
                score += 35
                reasons.append(f"Text '{text}' entspricht nicht Muster (+35)")

        # Check 4: Extreme size outlier (25 points)
        template_avg = self._get_template_avg_size(symbol_name)
        if template_avg > 0:
            w, h = row.get('w', 0), row.get('h', 0)
            det_size = (w + h) / 2
            ratio = det_size / template_avg if template_avg > 0 else 1.0
            if ratio > 2.5 or ratio < 0.4:
                score += 25
                reasons.append(f"Größe {ratio:.1f}x Template-Durchschnitt (+25)")

        # Check 5: Low confidence (15 points)
        threshold = self._get_template_threshold(symbol_name)
        conf = row.get('conf', 1.0)
        if threshold <= conf < threshold + 0.05:
            score += 15
            reasons.append(f"Konfidenz grenzwertig {conf:.0%} (+15)")

        # Check 6: At edge (15 points) - would need image dimensions
        # Skip for now

        # Check 7: Link distance too large (10 points)
        link_dist = row.get('link_distance')
        max_dist = self._get_max_link_distance(symbol_name)
        if link_dist and max_dist and link_dist > max_dist * 0.8:
            score += 10
            reasons.append(f"Koordinate weit entfernt ({link_dist:.0f}px) (+10)")

        return min(score, 100), reasons  # Cap at 100

    # ========================================================================
    # TEMPLATE MATCHING VALIDATION - Check Methods
    # ========================================================================

    def _check_template_false_positive_score(self) -> List[ValidationIssue]:
        """
        Composite false positive detection using multiple signals.
        Only creates issue if score >= 40 (medium confidence or higher).
        """
        issues = []

        for _, row in self.df.iterrows():
            if not row.get('is_new_symbol', False):
                continue

            #  FILTER: Skip if this is actually a YOLO class (incorrectly marked as template)
            symbol_name = row.get('cls', '')
            if symbol_name in self.CONFIDENCE_THRESHOLDS:
                continue

            score, reasons = self._calculate_template_fp_score(row)

            if score >= 70:
                # HIGH confidence false positive
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='error',
                    category='template_false_positive_high',
                    field='detection',
                    #  FIX: Template symbols use 'cls' field, not 'name'
                    message=f"Template '{row.get('cls', '')}': Wahrscheinlich Fehlerkennung (Score: {score})",
                    current_value=f"Score: {score}/100",
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=1.0 - (score / 100),
                    context={
                        'position': (float(row['xc']), float(row['yc'])),
                        'suggestion': 'Gründe:\n' + '\n'.join(f'• {r}' for r in reasons),
                        'can_jump': True,
                        'suggested_action': 'delete',
                        'alternative_actions': ['review'],
                        'action_description': f'Wahrscheinlich Fehlerkennung - Löschen empfohlen.\n\nGründe:\n' + '\n'.join(f'• {r}' for r in reasons),
                        'score': score,
                        'reasons': reasons
                    }
                ))

            elif score >= 40:
                # MEDIUM confidence - show as warning
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='warning',
                    category='template_false_positive_medium',
                    field='detection',
                    #  FIX: Template symbols use 'cls' field, not 'name'
                    message=f"Template '{row.get('cls', '')}': Möglicherweise Fehlerkennung (Score: {score})",
                    current_value=f"Score: {score}/100",
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=0.5,
                    context={
                        'position': (float(row['xc']), float(row['yc'])),
                        'suggestion': 'Gründe:\n' + '\n'.join(f'• {r}' for r in reasons),
                        'can_jump': True,
                        'suggested_action': 'review',
                        'alternative_actions': ['delete'],
                        'action_description': f'Unsichere Erkennung - Überprüfung empfohlen.\n\nGründe:\n' + '\n'.join(f'• {r}' for r in reasons),
                        'score': score,
                        'reasons': reasons
                    }
                ))

        return issues

    def _check_template_no_coordinate(self) -> List[ValidationIssue]:
        """Check if template-matched symbols missing required coordinates"""
        issues = []
        checked_count = 0
        needs_coord_count = 0

        # Debug: Show first few symbol names we're checking
        symbol_names_seen = []

        for _, row in self.df.iterrows():
            if not row.get('is_new_symbol', False):
                continue

            #  FIX: Template symbols use 'cls' field, not 'name'
            symbol_name = row.get('cls', '')

            #  FILTER: Skip if this is actually a YOLO class (incorrectly marked as template)
            if symbol_name in self.CONFIDENCE_THRESHOLDS:
                continue

            checked_count += 1

            if len(symbol_names_seen) < 5:
                symbol_names_seen.append(symbol_name)

            if self._symbol_needs_coordinate(symbol_name):
                needs_coord_count += 1
                #  FIX: Template symbols use 'coord_value', not 'linked_coordinate'
                linked_coord = row.get('coord_value')
                print(f"Template '{symbol_name}' coordinate check: coord_value='{linked_coord}', needs_coord=True")
                if not linked_coord:
                    print(f"Missing coordinate for '{symbol_name}' (row_id={row.get('row_id')})")
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='error',
                        category='template_no_coordinate',
                        field='coord_value',
                        message=f"Template '{symbol_name}': Keine Koordinate verknüpft",
                        current_value=None,
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'suggestion': f"Symbol '{symbol_name}' benötigt Koordinate",
                            'can_jump': True,
                            'suggested_action': 'manual_link',
                            'alternative_actions': ['review', 'delete'],
                            'action_description': 'Verknüpfen Sie eine Koordinate mit dem Symbol'
                        }
                    ))

        print(f"Checked {checked_count} template symbols (sample names: {symbol_names_seen}), {needs_coord_count} need coordinates, found {len(issues)} missing coordinate issues")
        return issues

    def _check_template_missing_text(self) -> List[ValidationIssue]:
        """Check if template-matched symbols missing required text"""
        issues = []
        checked_count = 0
        needs_text_count = 0

        # Debug: Show first few symbol names we're checking
        symbol_names_seen = []

        for _, row in self.df.iterrows():
            if not row.get('is_new_symbol', False):
                continue

            #  FIX: Template symbols use 'cls' field, not 'name'
            symbol_name = row.get('cls', '')

            #  FILTER: Skip if this is actually a YOLO class (incorrectly marked as template)
            if symbol_name in self.CONFIDENCE_THRESHOLDS:
                continue

            checked_count += 1

            if len(symbol_names_seen) < 5:
                symbol_names_seen.append(symbol_name)

            if self._symbol_needs_text(symbol_name):
                needs_text_count += 1
                #  FIX: Template symbols use 'anchor_text', not 'text'
                text = row.get('anchor_text', '')
                print(f"Template '{symbol_name}' text check: anchor_text='{text}', needs_text=True")
                if not text or len(str(text)) < 2:
                    print(f"Missing text for '{symbol_name}' (row_id={row.get('row_id')})")
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='error',
                        category='template_no_text',
                        field='anchor_text',
                        message=f"Template '{symbol_name}': Text-ID fehlt",
                        current_value=text or '',
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'suggestion': f"Symbol '{symbol_name}' benötigt Text-ID",
                            'can_jump': True,
                            'suggested_action': 'manual_ocr_horizontal',
                            'alternative_actions': ['manual_ocr_angular', 'bbox_resize', 'manual_edit'],
                            'action_description': (
                                'Option 1 (empfohlen): Aktivieren Sie "Manuelles OCR (Horizontal)" und zeichnen Sie ein Rechteck um den Text.\n'
                                'Option 2: Passen Sie das Symbol-Bounding-Box an und OCR wird automatisch neu ausgeführt.\n'
                                'Option 3: Geben Sie den Text manuell in der Tabelle ein.'
                            )
                        }
                    ))

        print(f"Checked {checked_count} template symbols (sample names: {symbol_names_seen}), {needs_text_count} need text, found {len(issues)} missing text issues")
        return issues

    def _check_template_low_confidence(self) -> List[ValidationIssue]:
        """Flag template matches with low confidence scores"""
        issues = []

        for _, row in self.df.iterrows():
            if not row.get('is_new_symbol', False):
                continue

            #  FIX: Template symbols use 'cls' field, not 'name'
            symbol_name = row.get('cls', '')

            #  FILTER: Skip if this is actually a YOLO class (incorrectly marked as template)
            if symbol_name in self.CONFIDENCE_THRESHOLDS:
                continue

            conf = row.get('conf', 1.0)
            threshold = self._get_template_threshold(symbol_name)

            # Marginal confidence (within 5% of threshold)
            if threshold <= conf < threshold + 0.05:
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='warning',
                    category='template_low_confidence',
                    field='conf',
                    message=f"Template '{symbol_name}': Konfidenz grenzwertig ({conf:.0%})",
                    current_value=f"{conf:.0%}",
                    suggested_value=f">{threshold+0.05:.0%}",
                    auto_correctable=False,
                    confidence=0.0,
                    context={
                        'position': (float(row['xc']), float(row['yc'])),
                        'suggestion': f"Match-Konfidenz {conf:.0%} knapp über Schwelle {threshold:.0%} - möglicherweise Fehlerkennung",
                        'can_jump': True,
                        'suggested_action': 'review',
                        'alternative_actions': ['delete', 'bbox_resize'],
                        'action_description': (
                            'Niedrige Konfidenz deutet oft auf Fehlerkennung hin.\n\n'
                            ' Empfohlen: Visuell prüfen, dann entscheiden:\n'
                            '  • Falls falsch erkannt → Löschen\n'
                            '  • Falls korrekt aber schwache Qualität → Behalten\n'
                            '  • Falls teilweise sichtbar → Bbox anpassen'
                        )
                    }
                ))
        return issues

    def _check_template_size_outlier(self) -> List[ValidationIssue]:
        """Flag template detections with unusual sizes compared to training examples"""
        issues = []

        # Get all template symbols
        if 'is_new_symbol' in self.df.columns:
            template_df = self.df[self.df['is_new_symbol'] == True].copy()
        else:
            template_df = pd.DataFrame()

        if template_df.empty:
            return issues

        #  FIX: Template symbols use 'cls' field, not 'name'
        if 'cls' not in template_df.columns:
            print("Template symbols found but 'cls' column missing")
            return issues

        # Filter out YOLO classes that are incorrectly marked as templates
        template_df = template_df[~template_df['cls'].isin(self.CONFIDENCE_THRESHOLDS)]

        if template_df.empty:
            return issues

        # Group by symbol name (using 'cls' field)
        for symbol_name in template_df['cls'].unique():
            symbol_df = template_df[template_df['cls'] == symbol_name]

            # Get average template size from symbol definition
            template_avg_size = self._get_template_avg_size(symbol_name)

            if template_avg_size == 0:
                continue

            for _, row in symbol_df.iterrows():
                w, h = row.get('w', 0), row.get('h', 0)
                det_size = (w + h) / 2

                ratio = det_size / template_avg_size

                if ratio > 2.5 or ratio < 0.4:
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='warning',
                        category='template_size_outlier',
                        field='size',
                        message=f"Template '{symbol_name}': Größe ungewöhnlich ({w:.0f}×{h:.0f}px)",
                        current_value=f"{w:.0f}×{h:.0f}",
                        suggested_value=f"~{template_avg_size:.0f}×{template_avg_size:.0f}",
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'suggestion': f"Größe {ratio:.1f}x Template-Durchschnitt (erwartet ~1.0x)",
                            'can_jump': True,
                            'suggested_action': 'review',
                            'alternative_actions': ['delete', 'bbox_resize'],
                            'action_description': (
                                'Überprüfen Sie visuell:\n'
                                '• Falls Symbol teilweise abgeschnitten: Passen Sie Bbox an (OCR wird automatisch neu ausgeführt)\n'
                                '• Falls falsche Erkennung: Löschen Sie das Symbol'
                            )
                        }
                    ))

        return issues

    def _check_template_link_distance_large(self) -> List[ValidationIssue]:
        """Warn if linked coordinate is far away (possibly wrong)"""
        issues = []

        for _, row in self.df.iterrows():
            if not row.get('is_new_symbol', False):
                continue

            #  FIX: Template symbols use 'cls' field, not 'name'
            symbol_name = row.get('cls', '')

            #  FILTER: Skip if this is actually a YOLO class (incorrectly marked as template)
            if symbol_name in self.CONFIDENCE_THRESHOLDS:
                continue

            link_dist = row.get('link_distance')
            max_dist = self._get_max_link_distance(symbol_name)

            if link_dist and max_dist:
                # Warn if > 80% of max distance
                if link_dist > max_dist * 0.8:
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='warning',
                        category='template_link_distance_large',
                        field='link_distance',
                        message=f"Template '{symbol_name}': Koordinate weit entfernt ({link_dist:.0f}px)",
                        current_value=f"{link_dist:.0f}px",
                        suggested_value=f"<{max_dist*0.5:.0f}px",
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'suggestion': f"Verknüpfte Koordinate {link_dist:.0f}px entfernt (Limit {max_dist}px)",
                            'can_jump': True,
                            'suggested_action': 'manual_link',
                            'alternative_actions': ['review'],
                            'action_description': 'Verknüpfung überprüfen - möglicherweise falsche Koordinate'
                        }
                    ))
        return issues

    def _check_template_text_pattern(self) -> List[ValidationIssue]:
        """Validate extracted text against symbol's text pattern"""
        issues = []

        for _, row in self.df.iterrows():
            if not row.get('is_new_symbol', False):
                continue

            #  FIX: Template symbols use 'cls' field, not 'name'
            symbol_name = row.get('cls', '')

            #  FILTER: Skip if this is actually a YOLO class (incorrectly marked as template)
            if symbol_name in self.CONFIDENCE_THRESHOLDS:
                continue

            text_pattern = self._get_template_text_pattern(symbol_name)

            if text_pattern:
                #  FIX: Template symbols use 'anchor_text', not 'text'
                text = row.get('anchor_text', '')

                if text and not self._matches_text_pattern(str(text), text_pattern):
                    auto_correctable = self._could_auto_correct_text(str(text), text_pattern)

                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='warning',
                        category='template_text_pattern_invalid',
                        field='anchor_text',
                        message=f"Template '{symbol_name}': Text '{text}' entspricht nicht Muster",
                        current_value=str(text),
                        suggested_value=self._auto_correct_text(str(text), text_pattern) if auto_correctable else None,
                        auto_correctable=auto_correctable,
                        confidence=0.0,
                        context={
                            'position': (float(row['xc']), float(row['yc'])),
                            'suggestion': f"Text '{text}' entspricht nicht erwartetem Muster '{text_pattern}'",
                            'can_jump': True,
                            'suggested_action': 'apply_auto_correction' if auto_correctable else 'manual_ocr_horizontal',
                            'alternative_actions': ['manual_edit', 'manual_ocr_angular'] if auto_correctable else ['bbox_resize', 'manual_edit'],
                            'action_description': (
                                'Option 1: Automatische Korrektur anwenden (z.B. O→0, I→1).\n'
                                'Option 2: Korrigieren Sie den Text manuell in der Tabelle.' if auto_correctable else
                                'Option 1: Zeichnen Sie mit Manuellem OCR ein Rechteck um den Text.\n'
                                'Option 2: Korrigieren Sie den Text manuell in der Tabelle.'
                            )
                        }
                    ))
        return issues

    def _check_link_distance_outliers(self) -> List[ValidationIssue]:
        """
        Detect symbols with unusually large link distances compared to class median.
        Flags potential missed coordinate detections.
        """
        from collections import defaultdict
        import numpy as np
        import math

        print(f"\n{'='*60}")
        print(f"[LinkDistanceOutliers] === STARTING CHECK ===")
        print(f"[LinkDistanceOutliers] DataFrame rows: {len(self.df)}")
        print(f"[LinkDistanceOutliers] Columns available: {list(self.df.columns)}")

        issues = []

        # Check required columns
        required = ['cls', 'ax1', 'ay1', 'ax2', 'ay2', 'cx1', 'cy1', 'cx2', 'cy2', 'row_id']
        missing = [c for c in required if c not in self.df.columns]
        if missing:
            print(f"[LinkDistanceOutliers] MISSING COLUMNS: {missing}")
            return issues

        # Collect link distances by class
        class_distances = defaultdict(list)
        class_rows = defaultdict(list)

        # Classes that should have close coordinate links
        link_classes = {'gks_gesteuert', 'gks_festkodiert', 'signal'}

        # Count classes
        cls_counts = self.df['cls'].value_counts()
        for cls in link_classes:
            print(f"[LinkDistanceOutliers] Class '{cls}': {cls_counts.get(cls, 0)} total rows")

        for idx, row in self.df.iterrows():
            cls = row.get('cls', '')
            if cls not in link_classes:
                continue

            # Calculate link distance from position data
            # ax1/ay1/ax2/ay2 = anchor (symbol) bbox
            # cx1/cy1/cx2/cy2 = coordinate bbox
            ax1 = row.get('ax1')
            ay1 = row.get('ay1')
            ax2 = row.get('ax2')
            ay2 = row.get('ay2')
            cx1 = row.get('cx1')
            cy1 = row.get('cy1')
            cx2 = row.get('cx2')
            cy2 = row.get('cy2')

            # Skip if no coordinate linked (check for None and NaN)
            if ax1 is None or cx1 is None:
                continue
            if pd.isna(ax1) or pd.isna(cx1):
                continue

            # Calculate center-to-center distance
            anchor_cx = (ax1 + ax2) / 2
            anchor_cy = (ay1 + ay2) / 2
            coord_cx = (cx1 + cx2) / 2
            coord_cy = (cy1 + cy2) / 2
            link_dist = math.sqrt((anchor_cx - coord_cx)**2 + (anchor_cy - coord_cy)**2)

            if link_dist > 0:
                class_distances[cls].append(link_dist)
                class_rows[cls].append((row['row_id'], row, link_dist))

        # Debug output
        print(f"[LinkDistanceOutliers] Found distances by class:")
        for cls, distances in class_distances.items():
            print(f"  {cls}: {len(distances)} samples, median={np.median(distances):.1f}px" if distances else f"  {cls}: 0 samples")

        # Check each class for outliers
        for cls, distances in class_distances.items():
            if len(distances) < 3:  # Need enough samples
                print(f"  {cls}: Skipping - need at least 3 samples")
                continue

            median_dist = float(np.median(distances))
            # Threshold: 1.5x median or 100px minimum, whichever is larger
            threshold = max(median_dist * 1.5, 100)
            print(f"  {cls}: median={median_dist:.1f}px, threshold={threshold:.1f}px")

            for row_id, row, dist in class_rows[cls]:
                if dist > threshold:
                    ratio = dist / median_dist if median_dist > 0 else 0

                    anchor_text = row.get('anchor_text', row.get('id', ''))
                    coord_text = row.get('coord_text', 'unknown')

                    print(f"  → OUTLIER: {cls} '{anchor_text}' dist={dist:.0f}px (>{threshold:.0f}px)")

                    issues.append(ValidationIssue(
                        row_id=row_id,
                        severity='warning',
                        category='link_distance_outlier',
                        field='coord_text',
                        message=(
                            f"{cls} '{anchor_text}': Koordinaten-Link ungewöhnlich weit "
                            f"({dist:.0f}px vs. Median {median_dist:.0f}px, {ratio:.1f}x). "
                            f"Möglicherweise fehlt eine nähere Koordinate."
                        ),
                        current_value=f"{coord_text} @ {dist:.0f}px",
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'position': (float(row.get('ax1', 0)), float(row.get('ay1', 0))),
                            'can_jump': True,
                            'class': cls,
                            'link_distance': dist,
                            'median_distance': median_dist,
                            'threshold': threshold,
                            'ratio': ratio,
                            'suggested_action': 'manual_link',
                            'alternative_actions': ['manual_ocr_horizontal', 'manual_edit', 'review'],
                            'action_description': (
                                'Option 1: Mit "Verknüpfen" eine andere Koordinate auswählen.\n'
                                'Option 2: Mit "OCR Horizontal" eine fehlende Koordinate einlesen.\n'
                                'Option 3: Koordinate direkt in der Tabelle bearbeiten.'
                            )
                        }
                    ))

        print(f"[LinkDistanceOutliers] Found {len(issues)} outliers")
        return issues

    def _check_haltepunkt_signal_reference(self) -> List[ValidationIssue]:
        """
        Check that signal names referenced in haltepunkt brackets exist as actual signals.

        Haltepunkt anchor_text format: "haltepunkt {counter} ({signal_name})"
        Example: "haltepunkt 1 (AHR313)" references signal "AHR313"

        This validates that the referenced signal actually exists on the same page.
        """
        import re
        issues = []

        if 'cls' not in self.df.columns:
            return issues

        haltepunkt_mask = self.df['cls'] == 'haltepunkt'
        haltepunkt_count = haltepunkt_mask.sum()
        print(f"[HaltepunktSignalRef] Checking {haltepunkt_count} haltepunkt elements...")

        for idx, row in self.df[haltepunkt_mask].iterrows():
            anchor = str(row.get('anchor_text', ''))

            # Extract signal name from brackets: "haltepunkt 1 (AHR313)" → "AHR313"
            match = re.search(r'\(([^)]+)\)\s*$', anchor)
            if not match:
                continue

            signal_name = match.group(1).strip()
            page = row.get('page', 0)

            # Check if signal exists on same page
            signal_mask = (
                (self.df['cls'] == 'signal') &
                (self.df['page'] == page) &
                (self.df['anchor_text'].fillna('').str.strip() == signal_name)
            )

            if not signal_mask.any():
                # Signal not found - create validation issue
                xc = row.get('xc', 0)
                yc = row.get('yc', 0)
                if pd.isna(xc):
                    xc = (row.get('ax1', 0) + row.get('ax2', 0)) / 2
                if pd.isna(yc):
                    yc = (row.get('ay1', 0) + row.get('ay2', 0)) / 2

                issues.append(ValidationIssue(
                    row_id=row.get('row_id', -1),
                    category='Referenzfehler',
                    severity='warning',
                    field='anchor_text',
                    message=f'Haltepunkt referenziert Signal "{signal_name}", aber kein Signal mit diesem Namen auf Seite {page+1} gefunden',
                    current_value=anchor,
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=0.0,
                    context={
                        'position': (float(xc), float(yc)),
                        'can_jump': True,
                        'class': 'haltepunkt',
                        'referenced_signal': signal_name,
                        'page': page,
                    }
                ))

        print(f"[HaltepunktSignalRef] Found {len(issues)} issues")
        return issues

# ============================================================================
# DATABASE INTEGRATION HELPERS
# ============================================================================

def save_validation_to_db(layout_name: str, validation_result):
    """
     NEW: Save validation results to PostgreSQL database.

    Saves to validation_log table.
    """
    try:
        from database_sqlite import save_validation_results

        # Convert ValidationResult to list of dicts
        validation_data = []

        for issue in validation_result.issues:
            validation_data.append({
                'validation_type': issue.category,
                'severity': issue.severity.upper(),
                'message': issue.message,
                'row_id': issue.row_id if issue.row_id >= 0 else None,
                'details': {
                    'field': issue.field,
                    'current_value': str(issue.current_value) if issue.current_value else None,
                    'suggested_value': str(issue.suggested_value) if issue.suggested_value else None,
                    'confidence': issue.confidence,
                    **issue.context
                }
            })

        save_validation_results(layout_name, validation_data)
        print(f"Saved {len(validation_data)} validation issues to database")

    except Exception as e:
        print(f"Failed to save validation results to database: {e}")


def save_quality_metrics_to_db(layout_name: str, metrics: Dict):
    """
     NEW: Save quality metrics to PostgreSQL database.

    Saves to quality_metrics table.
    """
    try:
        from database_sqlite import save_quality_metrics

        save_quality_metrics(layout_name, metrics)
        print(f"Saved {len(metrics)} quality metrics to database")

    except Exception as e:
        print(f"Failed to save quality metrics to database: {e}")


# ============================================================================
# SIMPLE INTEGRATION FUNCTION
# ============================================================================

def validate_everything(df: pd.DataFrame, auto_correct: bool = False, layout_name: str = None, save_to_db: bool = False):
    """
    ONE function to validate EVERYTHING + compute quality metrics + save to database.

    Usage in your AuditingWindow:
        from uservalidation.ultimate_validator import validate_everything

        result = validate_everything(
            workspace.df_all,
            auto_correct=False,
            layout_name=workspace.layout_name,  # For database
            save_to_db=True  # Save to PostgreSQL
        )
        dialog = EnhancedValidationResultsDialog(result, self)
        dialog.exec_()

    Args:
        df: DataFrame with YOLO + OCR results
        auto_correct: Apply auto-corrections for OCR format errors
        layout_name: Layout name (required if save_to_db=True)
        save_to_db: Save validation results and metrics to PostgreSQL

    Returns:
        ValidationResult with ALL issues (OCR + YOLO) + quality metrics
    """
    validator = UltimateValidator(df)

    # Run validation
    result = validator.validate_all(auto_correct=auto_correct)

    # Compute quality metrics
    print(f"Computing quality metrics...")
    metrics = validator.compute_quality_metrics()
    print(f"Computed {len(metrics)} quality metrics")

    # Add metrics to result (for GUI display)
    if not hasattr(result, 'metrics'):
        result.metrics = metrics

    # Save to database if requested
    if save_to_db and layout_name:
        print(f"Saving validation results to database...")
        save_validation_to_db(layout_name, result)
        save_quality_metrics_to_db(layout_name, metrics)
    elif save_to_db and not layout_name:
        print(f"Warning: save_to_db=True but layout_name not provided. Skipping database save.")

    return result
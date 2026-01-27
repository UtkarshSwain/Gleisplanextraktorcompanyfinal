"""
Enhanced PDF Comparison Engine
Handles all 13 classes with spatial + semantic matching
"""

import pandas as pd
import numpy as np
import math
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum

# ============================================================================
# COMPARISON RESULT TYPES
# ============================================================================

class ChangeType(Enum):
    """Type of change detected"""
    ADDED = 'added'        # New element in new version
    DELETED = 'deleted'    # Element removed from old version
    MOVED = 'moved'        # Same identifier, different position (FA-011: Verschoben)
    MODIFIED = 'modified'  # Same position, changed fields
    UNCHANGED = 'unchanged'

class ChangeSeverity(Enum):
    MINOR = "minor"      # Small coordinate change (< 5m)
    MODERATE = "moderate"  # Moderate change (5-20m)
    MAJOR = "major"      # Large change (> 20m) or class change

@dataclass
class ElementChange:
    """Represents a change to a single element"""
    change_type: ChangeType
    severity: ChangeSeverity
    element_class: str
    page: int
    
    # Old version data (None if ADDED)
    old_data: Optional[Dict] = None
    
    # New version data (None if DELETED)
    new_data: Optional[Dict] = None
    
    # Detailed changes (for MODIFIED)
    field_changes: Optional[Dict] = None
    
    # Spatial changes
    spatial_change: Optional[Dict] = None
    
    # Match confidence (0.0 - 1.0)
    match_confidence: float = 1.0

# ============================================================================
# COMPARISON ENGINE
# ============================================================================

class LayoutComparisonEngine:
    """
    Compares two track layouts with intelligent matching.
    
    Features:
    - UUID-based matching (when available)
    - Spatial fallback matching (for legacy data)
    - Semantic similarity (coordinate values, text)
    - Class-specific rules
    - Spatial movement detection
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._default_config()
    
    def _default_config(self) -> Dict:
        """Default comparison configuration"""
        return {
            # Matching thresholds
            'coordinate_tolerance': 0.001,  # 1mm in km
            'spatial_distance_threshold': 200,  # pixels
            'text_similarity_threshold': 0.85,  # Levenshtein
            
            # Change detection
            'min_coordinate_change': 0.5,  # meters
            'significant_coordinate_change': 10.0,  # meters
            'min_spatial_movement': 10,  # pixels
            'min_angle_change': 10.0,  # 

            # Weights for hybrid matching
            'weight_uuid': 1.0,      # Perfect match if UUIDs exist
            'weight_text': 0.6,      # Text similarity
            'weight_spatial': 0.4,   # Spatial proximity
            
            # Class-specific rules
            'critical_fields': {
                # OCR classes - track by anchor_text
                'signal': {
                    'identifier': 'anchor_text',  # ✅ What identifies this element
                    'tracked_fields': ['coord_value', 'fahrtrichtung']  # ✅ What to track for changes
                },
                'gks_gesteuert': {
                    'identifier': 'anchor_text',
                    'tracked_fields': ['coord_value']
                },
                'gks_festkodiert': {
                    'identifier': 'anchor_text',
                    'tracked_fields': ['coord_value']
                },

                # Coordinate class - special handling
                'coordinate': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },

                # Non-OCR symbol classes - track by coord_text
                'gm_block': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'weichen_block': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value', 'fahrtrichtung']
                },
                'isolierstoß': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'haltepunkt': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'sverbinder': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'prellblock': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'haltetafel': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'endeweichen': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'weichengruppeende': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
            }
        }

    def _get_comparable_fields(self, cls: str) -> Dict[str, List[str]]:
        """
        Get identifier and tracked fields for a specific class.
        
        Args:
            cls: Element class name
            
        Returns:
            {
                'identifier': 'anchor_text' or 'coord_text',
                'tracked_fields': ['coord_value', 'fahrtrichtung', ...]
            }
        """
        class_config = self.config['critical_fields'].get(cls)
        
        if not class_config:
            # Default fallback
            return {
                'identifier': 'coord_text',
                'tracked_fields': ['coord_value']
            }
        
        return class_config

    def compare(self, df_old: pd.DataFrame, df_new: pd.DataFrame) -> Dict:
        """
        Compare two layout DataFrames and return detailed changes.
        """
        print("\n" + "="*70)
        print("🔍 LAYOUT COMPARISON ENGINE")
        print("="*70)
        
        # Convert DataFrames to dictionaries
        dict_old = self._df_to_dict(df_old)
        dict_new = self._df_to_dict(df_new)
        
        # Filter out standalone coordinates (not linked to anchors)
        dict_old = {
            k: v for k, v in dict_old.items()
            if v.get('cls') != 'coordinate' or (
                v.get('cls') == 'coordinate' and 
                self._is_linked_to_anchor(v, dict_old)
            )
        }
        
        dict_new = {
            k: v for k, v in dict_new.items()
            if v.get('cls') != 'coordinate' or (
                v.get('cls') == 'coordinate' and 
                self._is_linked_to_anchor(v, dict_new)
            )
        }

        # Exclude weichen_block class
        dict_old = {
            k: v for k, v in dict_old.items()
            if v.get('cls') != 'weichen_block'
        }
        
        dict_new = {
            k: v for k, v in dict_new.items()
            if v.get('cls') != 'weichen_block'
        }

        print(f"Old layout: {len(df_old)} elements")
        print(f"New layout: {len(df_new)} elements")
        print(f"  old: {len(dict_old)} elements indexed")
        print(f"  new: {len(dict_new)} elements indexed")
        
        # Try UUID matching first
        matches = self._match_by_uuid(dict_old, dict_new)
        uuid_matches = len(matches)
        print(f"  UUID matches: {uuid_matches}")
        
        # Fall back to spatial matching for unmatched elements
        matched_old = set(matches.keys())
        matched_new = set(matches.values())
        
        unmatched_old = {k: v for k, v in dict_old.items() if k not in matched_old}
        unmatched_new = {k: v for k, v in dict_new.items() if k not in matched_new}
        
        spatial_matches = self._match_spatially(unmatched_old, unmatched_new)
        matches.update(spatial_matches)
        
        print(f"  Spatial matches: {len(spatial_matches)}")
        print(f"  Total matches: {len(matches)}")
        
        # ✅ DEBUG: Show sample of matched elements
        if len(matches) > 0:
            print(f"\n📊 Sample of matched elements:")
            for i, (old_key, new_key) in enumerate(list(matches.items())[:5]):
                old_elem = dict_old[old_key]
                new_elem = dict_new[new_key]
                print(f"  {i+1}. {old_elem.get('cls')} on page {old_elem.get('page')}")
                old_anchor = str(old_elem.get('anchor_text') or 'N/A')[:30]
                new_anchor = str(new_elem.get('anchor_text') or 'N/A')[:30]
                print(f"     Old: {old_anchor}")
                print(f"     New: {new_anchor}")

                # Check distance (with None safety)
                old_cx = old_elem.get('obb_cx') or 0
                old_cy = old_elem.get('obb_cy') or 0
                new_cx = new_elem.get('obb_cx') or 0
                new_cy = new_elem.get('obb_cy') or 0
                distance = ((old_cx - new_cx)**2 + (old_cy - new_cy)**2)**0.5
                print(f"     Distance: {distance:.2f} pixels")
        
        # Classify changes
        changes = self._classify_changes(matches, dict_old, dict_new)
        
        # Generate summary
        summary = self._generate_summary(changes)
        
        print("\n" + "="*70)
        print("✅ COMPARISON COMPLETE")
        print("="*70 + "\n")
        
        return {
            'added': changes['added'],
            'deleted': changes['deleted'],
            'moved': changes['moved'],        # FA-011: Verschoben
            'modified': changes['modified'],
            'unchanged': changes['unchanged'],
            'summary': summary
        }
    
    def _df_to_dict(self, df):
        """
        Convert DataFrame to dictionary format for comparison.
        Creates a mapping of detection_id -> element data.
        
        Args:
            df: DataFrame containing layout elements
            
        Returns:
            dict: Mapping of detection_id to element properties
        """
        result = {}
        
        for idx, row in df.iterrows():  # ✅ Changed: use idx
            detection_id = row.get('detection_id')
            
            if not detection_id:
                continue
                
            result[detection_id] = {
                'cls': row.get('cls'),
                'page': row.get('page'),
                'row_id': idx,  # ✅ ADD THIS
                'anchor_text': row.get('anchor_text'),
                'coord_text': row.get('coord_text'),
                'coord_value': row.get('coord_value'),
                'gi_gl': row.get('gi_gl'),
                'color': row.get('color'),
                'conf': row.get('conf'),
                'ax1': row.get('ax1'),
                'ay1': row.get('ay1'),
                'ax2': row.get('ax2'),
                'ay2': row.get('ay2'),
                'cx1': row.get('cx1'),
                'cy1': row.get('cy1'),
                'cx2': row.get('cx2'),
                'cy2': row.get('cy2'),
                'obb_cx': row.get('obb_cx'),
                'obb_cy': row.get('obb_cy'),
                'obb_w': row.get('obb_w'),
                'obb_h': row.get('obb_h'),
                'angle': row.get('angle'),
                'angle_raw': row.get('angle_raw'),
                'poly': row.get('poly'),
                'notes': row.get('notes'),
                'weichen_coordinates': row.get('weichen_coordinates'),
                'fahrtrichtung': row.get('fahrtrichtung'),
                '_all_bboxes': row.get('_all_bboxes'),
            }
        
        return result

    def _get_display_label(self, element: Dict) -> str:
        """
        Get display label for an element.
        Shows the element's identifier (what makes it unique).
        
        Format:
        - OCR classes: "anchor_text @ coord_text"
        - Non-OCR classes: "class @ coord_text"
        - Coordinate class: "@ coord_text"
        """
        cls = element.get('cls', 'unknown')
        class_config = self._get_comparable_fields(cls)
        identifier_field = class_config['identifier']
        
        # Get identifier value
        identifier = element.get(identifier_field)
        identifier_str = str(identifier or '').strip()
        
        # Get coordinate text (for context)
        coord_text = str(element.get('coord_text') or '').strip()  # ✅ Safe
        
        # ============================================================
        # Format label based on class type
        # ============================================================
        
        if cls == 'coordinate':
            # Coordinate class: just show coordinate
            return f"@ {identifier_str}" if identifier_str else "[coordinate]"
        
        elif identifier_field == 'anchor_text':
            # OCR classes (signal, gks_*): show anchor_text @ coord
            if identifier_str:
                if coord_text:
                    return f"{identifier_str} @ {coord_text}"
                else:
                    return identifier_str
            else:
                return f"[{cls}]"
        
        else:
            # Non-OCR classes: show class @ coord_text
            if identifier_str:
                return f"{cls} @ {identifier_str}"
            else:
                page = element.get('page', '?')
                return f"{cls} (Page {page})"

    def _match_by_uuid(self, dict_old: Dict, dict_new: Dict) -> Dict:
        """
        Match elements by UUID (detection_id).
        
        Args:
            dict_old: Old layout elements {detection_id: element_data}
            dict_new: New layout elements {detection_id: element_data}
        
        Returns:
            Matches {old_detection_id: new_detection_id}
        """
        matches = {}
        
        # Find common UUIDs
        old_uuids = set(dict_old.keys())
        new_uuids = set(dict_new.keys())
        common_uuids = old_uuids & new_uuids
        
        for uuid in common_uuids:
            matches[uuid] = uuid
        
        return matches

    def _match_spatially(self, dict_old: Dict, dict_new: Dict) -> Dict:
        """
        Match elements by spatial proximity and semantic similarity.
        
        Args:
            dict_old: Unmatched old elements {detection_id: element_data}
            dict_new: Unmatched new elements {detection_id: element_data}
        
        Returns:
            Matches {old_detection_id: new_detection_id}
        """
        matches = {}
        matched_new = set()
        
        for old_id, old_elem in dict_old.items():
            best_match_id = None
            best_score = 0.0
            
            for new_id, new_elem in dict_new.items():
                if new_id in matched_new:
                    continue
                
                # Calculate match score
                score = self._calculate_match_score(old_elem, new_elem)
                
                if score > best_score and score > 0.7:  # Threshold
                    best_score = score
                    best_match_id = new_id
            
            if best_match_id:
                matches[old_id] = best_match_id
                matched_new.add(best_match_id)
        
        return matches
    
    def _calculate_match_score(self, row1: Dict, row2: Dict) -> float:
        """
        Calculate similarity score between two elements.
        
        Matching strategy:
        - OCR classes (signal, gks_*): Match by anchor_text + coord_value
        - Non-OCR symbol classes: Match by SPATIAL POSITION first
        - Coordinate class: Match by coord_text
        
        Returns: 0.0 (no match) to 1.0 (perfect match)
        """
        # Must be same class
        cls = row1.get('cls')
        if cls != row2.get('cls'):
            return 0.0
        
        # Must be same page (or adjacent pages)
        page1 = row1.get('page', 0)
        page2 = row2.get('page', 0)
        if abs(page1 - page2) > 1:
            return 0.0
        
        # ============================================================
        # MATCHING STRATEGY BY CLASS TYPE
        # ============================================================
        
        # OCR classes: Match by text + coordinate value
        if cls in {'signal', 'gks_festkodiert', 'gks_gesteuert'}:
            return self._match_ocr_element(row1, row2)
        
        # Coordinate class: Match by coord_text
        elif cls == 'coordinate':
            return self._match_coordinate_element(row1, row2)
        
        # Non-OCR symbol classes: Match by SPATIAL POSITION
        else:
            return self._match_symbol_element(row1, row2)

    def _match_ocr_element(self, row1: Dict, row2: Dict) -> float:
        """
        Match OCR elements (signal, gks_*) by anchor_text + coord_value.

        For GKS elements: anchor_text must match EXACTLY (0305 ≠ 0306)
        For signals: anchor_text can have fuzzy match (minor OCR differences OK)

        Example:
            "Hp 0 @ 45.234" matches "Hp 0 @ 45.456" (same signal, moved)
            "Hp 0 @ 45.234" does NOT match "Hp 1 @ 45.234" (different signal)
            "0305 @ 0.177" does NOT match "0306 @ 0.177" (different GKS numbers!)
        """
        score = 0.0
        cls = row1.get('cls', '')

        # Anchor text similarity (primary identifier)
        text1 = str(row1.get('anchor_text') or '').strip()
        text2 = str(row2.get('anchor_text') or '').strip()

        if not text1 or not text2:
            return 0.0  # No anchor_text = can't match

        # For GKS elements: require EXACT match of anchor_text (GKS numbers)
        # "0305" and "0306" are different GKS devices - they should NOT match
        if cls in {'gks_festkodiert', 'gks_gesteuert'}:
            if text1 != text2:
                return 0.0  # Different GKS number = different element
            score += 0.7  # Exact match
        else:
            # For signals: allow fuzzy match (OCR might have minor errors)
            text_sim = self._text_similarity(text1, text2)
            if text_sim < 0.9:  # Must be very similar
                return 0.0
            score += 0.7 * text_sim

        # Coordinate value similarity (secondary)
        coord_val1 = row1.get('coord_value')
        coord_val2 = row2.get('coord_value')

        # Check for valid coordinate values (not None and not NaN)
        val1_valid = coord_val1 is not None and not (isinstance(coord_val1, float) and math.isnan(coord_val1))
        val2_valid = coord_val2 is not None and not (isinstance(coord_val2, float) and math.isnan(coord_val2))

        if val1_valid and val2_valid:
            coord_diff = abs(coord_val1 - coord_val2)
            if coord_diff < 0.5:  # Within 500m
                score += 0.2

        # Spatial proximity (tertiary)
        spatial_sim = self._spatial_similarity(row1, row2)
        score += 0.1 * spatial_sim

        return min(score, 1.0)

    def _match_coordinate_element(self, row1: Dict, row2: Dict) -> float:
        """
        Match coordinate elements by coord_text.
        
        Example:
            "45.234" matches "45.234" (same coordinate)
        """
        text1 = str(row1.get('coord_text') or '').strip()
        text2 = str(row2.get('coord_text') or '').strip()
        
        if not text1 or not text2:
            return 0.0
        
        if text1 == text2:
            return 1.0  # Perfect match
        
        # Fuzzy match for slight variations
        text_sim = self._text_similarity(text1, text2)
        return text_sim if text_sim > 0.9 else 0.0

    def _is_auto_generated_name(self, anchor_text: str, cls: str) -> bool:
        """
        Check if an anchor_text is auto-generated (e.g., "sverbinder 7", "gm_block 3").

        Auto-generated names follow the pattern: "{class_name} {number}"

        Args:
            anchor_text: The anchor text to check
            cls: The element class

        Returns:
            True if auto-generated, False if user-defined
        """
        import re

        if not anchor_text or not cls:
            return False

        anchor_text = str(anchor_text).strip()

        # Pattern: class name (with underscores replaced by spaces or kept) followed by a number
        # Examples: "sverbinder 7", "gm_block 3", "gm block 3", "isolierstoß 2", "gm_block5"
        cls_variants = [
            cls,                          # Original: "gm_block"
            cls.replace('_', ' '),        # With space: "gm block"
            cls.replace('_', ''),         # No separator: "gmblock"
        ]

        for variant in cls_variants:
            # Case-insensitive match: "{class} {number}" or "{class}{number}" (with or without space)
            pattern = rf'^{re.escape(variant)}\s*\d+$'
            if re.match(pattern, anchor_text, re.IGNORECASE):
                return True

        return False

    def _match_symbol_element(self, row1: Dict, row2: Dict) -> float:
        """
        Match non-OCR symbol elements by SPATIAL POSITION + coord_text.

        Strategy:
        1. Check anchor_text: if both are user-defined and different → no match
        2. If both auto-generated or missing → ignore anchor_text
        3. Check coord_text match (primary for symbols like gm_block, sverbinder)
        4. Calculate spatial proximity
        5. Combine for final score

        Example:
            "sverbinder 7 @ 0.0537" matches "sverbinder 5 @ 0.0537" (both auto-generated names)
            But "SV-Alpha @ 0.0537" does NOT match "SV-Beta @ 0.0537" (user-defined names)
        """
        score = 0.0
        cls = row1.get('cls', '')

        # ✅ CHECK anchor_text: detect auto-generated vs user-defined
        anchor1 = str(row1.get('anchor_text') or '').strip()
        anchor2 = str(row2.get('anchor_text') or '').strip()

        auto1 = self._is_auto_generated_name(anchor1, cls)
        auto2 = self._is_auto_generated_name(anchor2, cls)

        # If BOTH have user-defined names and they're DIFFERENT → no match
        if anchor1 and anchor2 and not auto1 and not auto2:
            if anchor1 != anchor2:
                return 0.0  # Different user-defined names = different elements

        # If one has user-defined name and other has auto-generated → no match
        # (user explicitly named it differently)
        if anchor1 and anchor2:
            if (auto1 and not auto2) or (not auto1 and auto2):
                if anchor1 != anchor2:
                    return 0.0

        # ✅ PRIMARY: coord_text match (most important for gm_block, sverbinder, etc.)
        text1 = str(row1.get('coord_text') or '').strip()
        text2 = str(row2.get('coord_text') or '').strip()

        if text1 and text2:
            if text1 == text2:
                # Same coord_text = very likely same element
                # This is strong enough to match even with large spatial shifts
                score += 0.8
            else:
                # Different coord_text = different elements, no match
                return 0.0
        elif not text1 and not text2:
            # Both have no coord_text - rely on spatial proximity only
            # Give a base score so very close elements can still match
            score += 0.5

        # ✅ SECONDARY: Spatial proximity (CONTINUOUS - closer is ALWAYS better)
        # This ensures when multiple elements have same coord_text, the closest pair matches
        cx1 = row1.get('obb_cx') or row1.get('cx') or 0
        cy1 = row1.get('obb_cy') or row1.get('cy') or 0
        cx2 = row2.get('obb_cx') or row2.get('cx') or 0
        cy2 = row2.get('obb_cy') or row2.get('cy') or 0

        try:
            distance = ((float(cx1) - float(cx2))**2 + (float(cy1) - float(cy2))**2)**0.5
        except (ValueError, TypeError):
            distance = 9999

        # Continuous distance scoring using inverse function
        # distance=0 → 0.2, distance=100 → 0.167, distance=500 → 0.1, distance=1000 → 0.067
        # This ensures closer matches are ALWAYS preferred, preventing cross-matching
        spatial_bonus = 0.2 * (500 / (distance + 500))
        score += spatial_bonus

        return min(score, 1.0)

    def _calculate_bbox_iou(self, row1: Dict, row2: Dict) -> float:
        """
        Calculate Intersection over Union (IoU) of two bounding boxes.

        Returns: 0.0 (no overlap) to 1.0 (perfect overlap)
        """
        # Get bounding boxes (use 'or 0' to handle None values safely)
        x1_min = row1.get('ax1') or 0
        y1_min = row1.get('ay1') or 0
        x1_max = row1.get('ax2') or 0
        y1_max = row1.get('ay2') or 0

        x2_min = row2.get('ax1') or 0
        y2_min = row2.get('ay1') or 0
        x2_max = row2.get('ax2') or 0
        y2_max = row2.get('ay2') or 0
        
        # Calculate intersection
        x_overlap = max(0, min(x1_max, x2_max) - max(x1_min, x2_min))
        y_overlap = max(0, min(y1_max, y2_max) - max(y1_min, y2_min))
        intersection = x_overlap * y_overlap
        
        # Calculate union
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union = area1 + area2 - intersection
        
        if union == 0:
            return 0.0
        
        return intersection / union
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Levenshtein similarity"""
        import difflib
        return difflib.SequenceMatcher(None, text1, text2).ratio()
    
    def _spatial_similarity(self, row1: Dict, row2: Dict) -> float:
        cls = row1.get('cls')

        # Get center points (use 'or 0' to handle None values safely)
        if cls == 'coordinate':
            # Use center of coordinate box
            x1 = ((row1.get('cx1') or 0) + (row1.get('cx2') or 0)) / 2
            y1 = ((row1.get('cy1') or 0) + (row1.get('cy2') or 0)) / 2
            x2 = ((row2.get('cx1') or 0) + (row2.get('cx2') or 0)) / 2
            y2 = ((row2.get('cy1') or 0) + (row2.get('cy2') or 0)) / 2
        else:
            x1 = ((row1.get('ax1') or 0) + (row1.get('ax2') or 0)) / 2
            y1 = ((row1.get('ay1') or 0) + (row1.get('ay2') or 0)) / 2
            x2 = ((row2.get('ax1') or 0) + (row2.get('ax2') or 0)) / 2
            y2 = ((row2.get('ay1') or 0) + (row2.get('ay2') or 0)) / 2

        # Euclidean distance
        distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

        # Convert to similarity (safeguard against division by zero)
        threshold = self.config.get('spatial_distance_threshold', 200) or 200
        similarity = max(0.0, 1.0 - (distance / threshold))

        return similarity

    def _classify_changes(self, matches: Dict, dict_old: Dict, dict_new: Dict) -> Dict:
        """
        Classify all changes.
        
        Args:
            matches: {old_detection_id: new_detection_id}
            dict_old: Old layout elements
            dict_new: New layout elements
        
        Returns:
            {
                'added': [...],
                'deleted': [...],
                'moved': [...],      # FA-011: Verschoben
                'modified': [...],
                'unchanged': [...]
            }
        """
        changes = {
            'added': [],
            'deleted': [],
            'moved': [],         # FA-011: Same identifier, different position
            'modified': [],
            'unchanged': []
        }
        
        # ✅ FIXED: matches is now {old_id: new_id}, not {key: {old_key, new_key}}
        matched_old = set(matches.keys())
        matched_new = set(matches.values())
        
        # Deleted elements
        for old_id, old_elem in dict_old.items():
            if old_id not in matched_old:
                changes['deleted'].append(ElementChange(
                    change_type=ChangeType.DELETED,
                    severity=ChangeSeverity.MAJOR,
                    element_class=old_elem.get('cls', ''),
                    page=old_elem.get('page', 0),
                    old_data=old_elem
                ))
        
        # Added elements
        for new_id, new_elem in dict_new.items():
            if new_id not in matched_new:
                changes['added'].append(ElementChange(
                    change_type=ChangeType.ADDED,
                    severity=ChangeSeverity.MAJOR,
                    element_class=new_elem.get('cls', ''),
                    page=new_elem.get('page', 0),
                    new_data=new_elem
                ))
        
        # Modified/moved/unchanged elements
        for old_id, new_id in matches.items():
            old_elem = dict_old[old_id]
            new_elem = dict_new[new_id]

            # Detect changes
            field_changes, spatial_change = self._detect_changes(old_elem, new_elem)

            # FA-011 Logic:
            # - VERSCHOBEN: coord_value changed (element moved along the track)
            # - MODIFIZIERT: other field changes (fahrtrichtung, etc.) but NOT coord_value
            # - Ignore pure spatial (pixel) changes - just drawing shift, same logical position

            # Check if coord_value changed (this means element MOVED along the track)
            coord_value_changed = field_changes and 'coord_value' in field_changes

            if coord_value_changed:
                # FA-011: VERSCHOBEN - Element moved to different km position
                # Remove coord_value from field_changes and put in spatial context
                coord_change = field_changes.pop('coord_value')
                move_info = {
                    'old_coord': coord_change.get('old'),
                    'new_coord': coord_change.get('new'),
                    'delta_meters': coord_change.get('delta_meters'),
                    'direction': 'along track'
                }
                severity = self._determine_severity({'coord_value': coord_change}, None)

                # If there are remaining field changes, they go with the move
                remaining_changes = field_changes if field_changes else None

                changes['moved'].append(ElementChange(
                    change_type=ChangeType.MOVED,
                    severity=severity,
                    element_class=new_elem.get('cls', ''),
                    page=new_elem.get('page', 0),
                    old_data=old_elem,
                    new_data=new_elem,
                    field_changes=remaining_changes,  # Other changes if any
                    spatial_change=move_info,
                    match_confidence=1.0
                ))
            elif field_changes:
                # MODIFIZIERT - Field changes but NOT coord_value (e.g., fahrtrichtung)
                severity = self._determine_severity(field_changes, None)
                changes['modified'].append(ElementChange(
                    change_type=ChangeType.MODIFIED,
                    severity=severity,
                    element_class=new_elem.get('cls', ''),
                    page=new_elem.get('page', 0),
                    old_data=old_elem,
                    new_data=new_elem,
                    field_changes=field_changes,
                    spatial_change=None,  # Ignore spatial pixel changes
                    match_confidence=1.0
                ))
            else:
                # UNCHANGED - No meaningful changes
                # (spatial pixel changes are ignored - just drawing shift)
                changes['unchanged'].append(ElementChange(
                    change_type=ChangeType.UNCHANGED,
                    severity=ChangeSeverity.MINOR,
                    element_class=new_elem.get('cls', ''),
                    page=new_elem.get('page', 0),
                    old_data=old_elem,
                    new_data=new_elem,
                    match_confidence=1.0
                ))
        
        return changes

    def _detect_changes(self, old_row: Dict, new_row: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
        """
        Detect field changes and spatial changes.
        
        Strategy:
        1. Check if identifier changed (anchor_text or coord_text)
        - If changed → MAJOR change (element renumbered/relabeled)
        2. For same identifier, check tracked fields
        - coord_value change → position change
        - fahrtrichtung change → direction change
        - etc.
        3. Check spatial movement (for non-coordinate classes)
        
        Returns:
            (field_changes, spatial_change)
        """
        cls = old_row.get('cls')
        class_config = self._get_comparable_fields(cls)
        
        identifier_field = class_config['identifier']
        tracked_fields = class_config['tracked_fields']
        
        field_changes = {}
        
        # ============================================================
        # STEP 1: Check if identifier changed
        # ============================================================
        old_identifier = old_row.get(identifier_field)
        new_identifier = new_row.get(identifier_field)

        # Normalize identifiers
        old_id_str = str(old_identifier or '').strip()
        new_id_str = str(new_identifier or '').strip()

        if old_id_str != new_id_str:
            # ✅ Identifier changed
            
            # For non-OCR symbols: coord_text change = symbol renumbered
            if identifier_field == 'coord_text':
                field_changes[identifier_field] = {
                    'old': old_identifier,
                    'new': new_identifier,
                    'change_type': 'symbol_renumbered',  # ✅ More specific
                    'severity': 'MAJOR',
                    'description': f'Symbol renumbered: {old_id_str} → {new_id_str}'
                }
            
            # For OCR classes: anchor_text change = element relabeled
            elif identifier_field == 'anchor_text':
                field_changes[identifier_field] = {
                    'old': old_identifier,
                    'new': new_identifier,
                    'change_type': 'identifier_changed',
                    'severity': 'MAJOR'
                }
                
                # Component-level comparison
                if cls in {'signal', 'gks_festkodiert', 'gks_gesteuert'}:
                    component_changes = self._compare_ocr_components(old_identifier, new_identifier)
                    if component_changes:
                        field_changes[identifier_field]['component_changes'] = component_changes['component_changes']
        
        # ============================================================
        # STEP 2: Check tracked fields (for same identifier)
        # ============================================================
        for field in tracked_fields:
            old_val = old_row.get(field)
            new_val = new_row.get(field)
            
            # Skip if both empty
            if self._is_empty(old_val) and self._is_empty(new_val):
                continue
            
            # Special handling for coord_value
            if field == 'coord_value':
                if not self._coords_equal(old_val, new_val):
                    # Use 'is not None' instead of truthy check (0.0 is a valid coordinate!)
                    delta = abs(new_val - old_val) if (new_val is not None and old_val is not None) else None

                    field_changes[field] = {
                        'old': old_val,
                        'new': new_val,
                        'delta': delta,
                        'delta_meters': delta * 1000 if delta is not None else None,
                        'description': f'{old_id_str} moved by {delta * 1000:.1f}m' if delta is not None else None,
                        'element_identifier': old_id_str  # ✅ Track which element moved
                    }
            
            # Text/categorical fields
            elif field in ['fahrtrichtung']:
                if str(old_val or '').strip() != str(new_val or '').strip():
                    field_changes[field] = {
                        'old': old_val,
                        'new': new_val,
                        'element_identifier': old_id_str  # ✅ Track which element changed
                    }
        
        # ============================================================
        # STEP 3: Check angle changes (minimum 10 degrees)
        # ============================================================
        old_angle = old_row.get('angle')
        new_angle = new_row.get('angle')
        
        if old_angle is not None and new_angle is not None:
            # Normalize angles to 0-360 range
            old_angle_norm = old_angle % 360
            new_angle_norm = new_angle % 360
            
            # Calculate smallest angle difference (accounting for wrap-around)
            angle_diff = abs(new_angle_norm - old_angle_norm)
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            # Only report if change >= 10 degrees
            if angle_diff >= self.config.get('min_angle_change', 10.0):
                field_changes['angle'] = {
                    'old': old_angle,
                    'new': new_angle,
                    'delta': angle_diff,
                    'direction': 'clockwise' if new_angle_norm > old_angle_norm else 'counter-clockwise',
                    'element_identifier': old_id_str  # ✅ Track which element rotated
                }
        
        # ============================================================
        # STEP 4: Spatial change detection (skip for coordinate class)
        # ============================================================
        spatial_change = None
        if cls != 'coordinate':
            spatial_change = self._detect_spatial_change(old_row, new_row)
            if spatial_change:
                spatial_change['element_identifier'] = old_id_str  # ✅ Track which element moved
        
        return (field_changes if field_changes else None, spatial_change)
    
    def _detect_spatial_change(self, old_row: Dict, new_row: Dict) -> Optional[Dict]:
        """Detect if element moved spatially"""
        cls = old_row.get('cls')
        
        # Skip spatial change detection for coordinate class
        if cls == 'coordinate':
            return None
        
        # Get center points (use 'or 0' to handle None values safely)
        old_cx = ((old_row.get('ax1') or 0) + (old_row.get('ax2') or 0)) / 2
        old_cy = ((old_row.get('ay1') or 0) + (old_row.get('ay2') or 0)) / 2
        new_cx = ((new_row.get('ax1') or 0) + (new_row.get('ax2') or 0)) / 2
        new_cy = ((new_row.get('ay1') or 0) + (new_row.get('ay2') or 0)) / 2
        
        # Calculate movement
        dx = new_cx - old_cx
        dy = new_cy - old_cy
        distance = math.sqrt(dx**2 + dy**2)
        
        # Only report significant movements
        if distance < self.config.get('min_spatial_movement', 10):
            return None
        
        # Determine direction
        angle = math.degrees(math.atan2(dy, dx))
        if angle < 0:
            angle += 360
        
        direction = self._angle_to_direction(angle)
        
        return {
            'old_center': (old_cx, old_cy),
            'new_center': (new_cx, new_cy),
            'movement_vector': (dx, dy),
            'distance': distance,
            'direction': direction
            # ✅ element_identifier will be added by _detect_changes()
        }
        
    def _angle_to_direction(self, angle: float) -> str:
        """Convert angle to compass direction"""
        if angle < 22.5 or angle >= 337.5:
            return "right"
        elif angle < 67.5:
            return "down-right"
        elif angle < 112.5:
            return "down"
        elif angle < 157.5:
            return "down-left"
        elif angle < 202.5:
            return "left"
        elif angle < 247.5:
            return "up-left"
        elif angle < 292.5:
            return "up"
        else:
            return "up-right"

    def _determine_severity(self, field_changes: Optional[Dict], spatial_change: Optional[Dict]) -> ChangeSeverity:
        """
        Determine change severity based on field changes and spatial movement.
        
        Severity levels:
        - MAJOR:
            * Identifier changed (anchor_text or coord_text)
            * Class change
            * Large coordinate change (>20m)
        - MODERATE:
            * Medium coordinate change (5-20m)
            * Direction changes (fahrtrichtung)
            * Medium spatial movement (50-100px)
        - MINOR:
            * Small changes (<5m)
            * Small spatial movement (<50px)
        """
        if not field_changes and not spatial_change:
            return ChangeSeverity.MINOR
        
        # ============================================================
        # MAJOR SEVERITY
        # ============================================================
        
        # Identifier changed (element renumbered/relabeled)
        if field_changes:
            for field in ['anchor_text', 'coord_text']:
                if field in field_changes:
                    change_type = field_changes[field].get('change_type')
                    if change_type == 'identifier_changed':
                        return ChangeSeverity.MAJOR
            
            # Class change
            if 'cls' in field_changes:
                return ChangeSeverity.MAJOR
            
            # Note: Removed color, weichen_coordinates from critical fields as not relevant
            
            # Large coordinate change (>20m)
            if 'coord_value' in field_changes:
                delta_m = field_changes['coord_value'].get('delta_meters', 0)
                if delta_m and delta_m > 20:  # >20m (delta_meters is already in meters)
                    return ChangeSeverity.MAJOR
        
        # Large spatial movement (>100px)
        if spatial_change:
            distance = spatial_change.get('distance', 0)
            if distance > 100:
                return ChangeSeverity.MAJOR
        
        # ============================================================
        # MODERATE SEVERITY
        # ============================================================
        
        if field_changes:
            # Medium coordinate change (5-20m)
            if 'coord_value' in field_changes:
                delta_m = field_changes['coord_value'].get('delta_meters', 0)
                if delta_m and delta_m > 5:  # >5m (delta_meters is already in meters)
                    return ChangeSeverity.MODERATE
            
            # Significant field changes
            significant_fields = ['fahrtrichtung']
            for field in significant_fields:
                if field in field_changes:
                    return ChangeSeverity.MODERATE
        
        # Medium spatial movement (50-100px)
        if spatial_change:
            distance = spatial_change.get('distance', 0)
            if distance > 50:
                return ChangeSeverity.MODERATE
        
        # ============================================================
        # MINOR SEVERITY (default)
        # ============================================================
        return ChangeSeverity.MINOR

    def _is_empty(self, value) -> bool:
        """Check if value is empty (but 0.0 is NOT empty - it's a valid coordinate)"""
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, float) and math.isnan(value):
            return True
        return False
    
    def _coords_equal(self, val1, val2, tolerance: float = None) -> bool:
        """Compare coordinate values with tolerance"""
        if tolerance is None:
            tolerance = self.config['coordinate_tolerance']
        
        if self._is_empty(val1) and self._is_empty(val2):
            return True
        
        if self._is_empty(val1) or self._is_empty(val2):
            return False
        
        try:
            v1 = float(val1)
            v2 = float(val2)
            return abs(v1 - v2) < tolerance
        except (ValueError, TypeError):
            return str(val1).strip() == str(val2).strip()
        
    def _generate_summary(self, changes: Dict[str, List[ElementChange]]) -> Dict:
        """
        Generate summary statistics from comparison results.

        Args:
            changes: Dictionary with 'added', 'deleted', 'moved', 'modified', 'unchanged' lists

        Returns:
            Dictionary with summary statistics
        """
        summary = {
            'total_added': len(changes['added']),
            'total_deleted': len(changes['deleted']),
            'total_moved': len(changes['moved']),        # FA-011: Verschoben
            'total_modified': len(changes['modified']),
            'total_unchanged': len(changes['unchanged']),
            'by_severity': {
                'major': 0,
                'moderate': 0,
                'minor': 0
            },
            'by_class': {},
            'by_page': {}
        }

        # Count by severity (for moved and modified)
        for change in changes['moved'] + changes['modified']:
            summary['by_severity'][change.severity.value] += 1

        # Count by class
        all_changes = changes['added'] + changes['deleted'] + changes['moved'] + changes['modified']

        for change in all_changes:
            cls = change.element_class

            if cls not in summary['by_class']:
                summary['by_class'][cls] = {
                    'added': 0,
                    'deleted': 0,
                    'moved': 0,
                    'modified': 0
                }

            summary['by_class'][cls][change.change_type.value] += 1

        # Count by page
        for change in all_changes:
            page = change.page

            if page not in summary['by_page']:
                summary['by_page'][page] = {
                    'added': 0,
                    'deleted': 0,
                    'moved': 0,
                    'modified': 0
                }

            summary['by_page'][page][change.change_type.value] += 1

        return summary
    
    def _is_linked_to_anchor(self, coord_elem: Dict, all_elements: Dict) -> bool:
        """
        Check if a coordinate is linked to any anchor element.
        
        A coordinate is linked if any anchor element references it
        (shares the same coord_text).
        
        Args:
            coord_elem: The coordinate element to check
            all_elements: Dictionary of all elements {detection_id: element_data}
        
        Returns:
            True if linked to an anchor, False if standalone
        """
        # Get coord_text from the coordinate element (handle None safely)
        coord_text = str(coord_elem.get('coord_text') or '').strip()
        
        if not coord_text:
            return False  # No coord_text = can't be linked
        
        # Check if any non-coordinate element has this coord_text
        for elem in all_elements.values():
            # Skip other coordinate elements
            if elem.get('cls') == 'coordinate':
                continue
            
            # Get coord_text from this element (handle None safely)
            elem_coord_text = str(elem.get('coord_text') or '').strip()
            
            # If they match, this coordinate is linked to this anchor
            if elem_coord_text == coord_text:
                return True
        
        # No anchor found with this coord_text
        return False
    
    def _compare_ocr_components(self, old_text: str, new_text: str) -> Optional[Dict]:
        """
        Compare OCR text at component level (each alphanumeric part).
        
        Examples:
            "Hp 0/Hp 1" vs "Hp 0/Hp 2" → component changed: "1" → "2"
            "W123" vs "W456" → component changed: "123" → "456"
            "Signal A" vs "Signal B" → component changed: "A" → "B"
        
        Args:
            old_text: Old OCR text
            new_text: New OCR text
        
        Returns:
            Dictionary with component-level changes, or None if no changes
        """
        if old_text == new_text:
            return None
        
        # Normalize
        old_text = str(old_text or '').strip()
        new_text = str(new_text or '').strip()
        
        if not old_text and not new_text:
            return None
        
        # Split into alphanumeric components
        import re
        old_components = re.findall(r'\w+', old_text)
        new_components = re.findall(r'\w+', new_text)
        
        # Find differences
        changed_components = []
        
        # Compare component by component
        max_len = max(len(old_components), len(new_components))
        for i in range(max_len):
            old_comp = old_components[i] if i < len(old_components) else None
            new_comp = new_components[i] if i < len(new_components) else None
            
            if old_comp != new_comp:
                changed_components.append({
                    'position': i,
                    'old': old_comp,
                    'new': new_comp
                })
        
        if changed_components:
            return {
                'old': old_text,
                'new': new_text,
                'component_changes': changed_components
            }
        
        return None
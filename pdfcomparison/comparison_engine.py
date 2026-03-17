"""
Enhanced PDF Comparison Engine
Handles all 13 classes with spatial + semantic matching
"""

import pandas as pd
import numpy as np
import math
import re
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum
from scipy.optimize import linear_sum_assignment

# Module-level debug flag (can be configured from LayoutConfig)
DEBUG_COMPARISON = False

# Debug output file handle (module-level for persistence)
_DEBUG_FILE = None

def _debug_print(message: str):
    """Write debug message to output.txt only"""
    global _DEBUG_FILE
    if _DEBUG_FILE is None:
        _DEBUG_FILE = open('output.txt', 'w', encoding='utf-8')
    _DEBUG_FILE.write(message + '\n')
    _DEBUG_FILE.flush()  # Ensure immediate write

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

    # Debug flag - controlled by DEBUG_COMPARISON in config.py
    DEBUG = DEBUG_COMPARISON

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._default_config()
        # Use DEBUG_COMPARISON from config.py (can be overridden by config dict)
        LayoutComparisonEngine.DEBUG = self.config.get('debug', DEBUG_COMPARISON)

    def _default_config(self) -> Dict:
        """Default comparison configuration"""
        return {
            # Note: Debug mode is controlled by DEBUG_COMPARISON in config.py

            # Matching thresholds
            'coordinate_tolerance': 0.0001,  # 0.1m (10cm) in km - only truly identical positions
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
                    'identifier': 'anchor_text',  #  What identifies this element
                    'tracked_fields': ['coord_value', 'fahrtrichtung']  #  What to track for changes
                },
                'gks_gesteuert': {
                    'identifier': 'anchor_text',
                    'tracked_fields': ['coord_value']
                },
                'gks_festkodiert': {
                    'identifier': 'anchor_text',
                    'tracked_fields': ['coord_value']
                },

                # NOTE: coordinate class is excluded from comparison entirely

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
                'prellbock': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'haltetafel': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'weichenende': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'weichengruppenende': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },

                # ============================================
                # ANTWERP CLASSES
                # ============================================
                # Antwerp Signal - gets name from linked text_id
                'Signal': {
                    'identifier': 'anchor_text',  # e.g., "S04301" from text_id
                    'tracked_fields': ['coord_value', 'fahrtrichtung', 'durchrutschweg']
                },
                # Antwerp Coupling Coils - get name from linked text_id
                'coupling_coil_active': {
                    'identifier': 'anchor_text',  # e.g., "TCC02251" from text_id
                    'tracked_fields': ['coord_value']
                },
                'coupling_coil_disabled': {
                    'identifier': 'anchor_text',  # e.g., "TCC02252" from text_id
                    'tracked_fields': ['coord_value']
                },
                # Antwerp bonds - use coord_text (default symbol matching)
                's_bond': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'short_bond': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'insulation_joint': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'terminal_bond': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                # Antwerp points - use coord_text (default symbol matching)
                'mech_point': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                'elec_point': {
                    'identifier': 'coord_text',
                    'tracked_fields': ['coord_value']
                },
                # Antwerp spie_loop - use coord_text (default symbol matching)
                'spie_loop': {
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
        print("LAYOUT COMPARISON ENGINE")
        print("="*70)
        
        # Convert DataFrames to dictionaries
        dict_old = self._df_to_dict(df_old)
        dict_new = self._df_to_dict(df_new)
        
        # Exclude coordinate class entirely from comparison
        # (coordinate elements are for reference only, not tracked as changes)
        dict_old = {
            k: v for k, v in dict_old.items()
            if v.get('cls') != 'coordinate'
        }

        dict_new = {
            k: v for k, v in dict_new.items()
            if v.get('cls') != 'coordinate'
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

        # Exclude text_id class (Antwerp reference class, like coordinate for Wien)
        dict_old = {
            k: v for k, v in dict_old.items()
            if v.get('cls') != 'text_id'
        }

        dict_new = {
            k: v for k, v in dict_new.items()
            if v.get('cls') != 'text_id'
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
        
        #  DEBUG: Show sample of matched elements
        if len(matches) > 0:
            print(f"\nSample of matched elements:")
            for i, (old_key, new_key) in enumerate(list(matches.items())[:5]):
                old_elem = dict_old[old_key]
                new_elem = dict_new[new_key]
                print(f"  {i+1}. {old_elem.get('cls')} on page {old_elem.get('page')}")
                old_anchor = str(old_elem.get('anchor_text') or 'N/A')[:30]
                new_anchor = str(new_elem.get('anchor_text') or 'N/A')[:30]
                print(f"Old: {old_anchor}")
                print(f"New: {new_anchor}")

                # Check distance (with None safety)
                old_cx = old_elem.get('obb_cx') or 0
                old_cy = old_elem.get('obb_cy') or 0
                new_cx = new_elem.get('obb_cx') or 0
                new_cy = new_elem.get('obb_cy') or 0
                distance = ((old_cx - new_cx)**2 + (old_cy - new_cy)**2)**0.5
                print(f"Distance: {distance:.2f} pixels")
        
        # Classify changes
        changes = self._classify_changes(matches, dict_old, dict_new)
        
        # Generate summary
        summary = self._generate_summary(changes)
        
        print("\n" + "="*70)
        print("COMPARISON COMPLETE")
        print("="*70 + "\n")
        
        return {
            'added': changes['added'],
            'deleted': changes['deleted'],
            'moved': changes['moved'],        # FA-011: Verschoben
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

        for idx, row in df.iterrows():  #  Changed: use idx
            # Skip hidden/merged rows - they are secondary instances that should not be compared
            hidden_val = row.get('_hidden')
            if hidden_val is True or (isinstance(hidden_val, float) and not math.isnan(hidden_val) and hidden_val):
                continue

            detection_id = row.get('detection_id')

            if not detection_id:
                continue
                
            result[detection_id] = {
                'cls': row.get('cls'),
                'page': row.get('page'),
                'row_id': row.get('row_id'),  # Use actual row_id column, not dataframe index
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
        coord_text = str(element.get('coord_text') or '').strip()  #  Safe
        
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
        Match elements using Hungarian algorithm for optimal assignment.

        This handles duplicates correctly by finding globally optimal pairing,
        unlike greedy matching which can mismatch elements with same coord_text.

        Args:
            dict_old: Unmatched old elements {detection_id: element_data}
            dict_new: Unmatched new elements {detection_id: element_data}

        Returns:
            Matches {old_detection_id: new_detection_id}
        """
        if not dict_old or not dict_new:
            return {}

        # Group by class for class-specific matching
        old_by_class = self._group_by_class(dict_old)
        new_by_class = self._group_by_class(dict_new)

        matches = {}

        for cls in old_by_class:
            if cls not in new_by_class:
                if self.DEBUG:
                    _debug_print(f"  [DEBUG] Class '{cls}': {len(old_by_class[cls])} in old, 0 in new → all DELETED")
                continue  # All elements of this class are deleted

            old_items = list(old_by_class[cls].items())
            new_items = list(new_by_class[cls].items())

            if not old_items or not new_items:
                continue

            if self.DEBUG:
                _debug_print(f"\n  [DEBUG] Hungarian matching for class '{cls}':")
                _debug_print(f"    Old elements: {len(old_items)}, New elements: {len(new_items)}")

            # Build cost matrix (negative scores for minimization)
            n_old = len(old_items)
            n_new = len(new_items)
            cost_matrix = np.zeros((n_old, n_new))

            for i, (old_id, old_elem) in enumerate(old_items):
                for j, (new_id, new_elem) in enumerate(new_items):
                    score = self._calculate_match_score(old_elem, new_elem)
                    cost_matrix[i, j] = -score  # Negative for minimization

                    if self.DEBUG and score > 0.5:
                        old_label = old_elem.get('anchor_text') or old_elem.get('coord_text') or old_id[:8]
                        new_label = new_elem.get('anchor_text') or new_elem.get('coord_text') or new_id[:8]
                        _debug_print(f"    Score[{i},{j}]: {score:.3f} | Old: {old_label} → New: {new_label}")

            # Hungarian algorithm finds optimal assignment
            row_ind, col_ind = linear_sum_assignment(cost_matrix)

            if self.DEBUG:
                _debug_print(f"    Hungarian assignment: {list(zip(row_ind, col_ind))}")

            # Extract matches above threshold
            for i, j in zip(row_ind, col_ind):
                score = -cost_matrix[i, j]
                if score > 0.7:  # Threshold
                    old_id = old_items[i][0]
                    new_id = new_items[j][0]
                    matches[old_id] = new_id

                    if self.DEBUG:
                        old_elem = old_items[i][1]
                        new_elem = new_items[j][1]
                        old_label = old_elem.get('anchor_text') or old_elem.get('coord_text') or 'N/A'
                        new_label = new_elem.get('anchor_text') or new_elem.get('coord_text') or 'N/A'
                        old_coord = old_elem.get('coord_value')
                        new_coord = new_elem.get('coord_value')
                        _debug_print(f"    ✓ MATCHED (score={score:.3f}): '{old_label}' @ {old_coord} → '{new_label}' @ {new_coord}")
                elif self.DEBUG:
                    old_elem = old_items[i][1]
                    new_elem = new_items[j][1]
                    old_label = old_elem.get('anchor_text') or old_elem.get('coord_text') or 'N/A'
                    new_label = new_elem.get('anchor_text') or new_elem.get('coord_text') or 'N/A'
                    _debug_print(f"    ✗ REJECTED (score={score:.3f} < 0.7): '{old_label}' → '{new_label}'")

        return matches

    def _group_by_class(self, elements: Dict) -> Dict[str, Dict]:
        """
        Group elements by class for class-specific matching.

        Args:
            elements: Dictionary of elements {detection_id: element_data}

        Returns:
            Dictionary grouped by class {cls: {detection_id: element_data}}
        """
        grouped = {}
        for elem_id, elem in elements.items():
            cls = elem.get('cls', 'unknown')
            if cls not in grouped:
                grouped[cls] = {}
            grouped[cls][elem_id] = elem
        return grouped
    
    def _calculate_match_score(self, row1: Dict, row2: Dict) -> float:
        """
        Calculate similarity score between two elements.

        Matching strategy:
        - OCR classes (signal, gks_*): Match by anchor_text + coord_value
        - Non-OCR symbol classes: Match by SPATIAL POSITION + coord_value
        - Coordinate class: Match by coord_text

        Args:
            row1: Old element data
            row2: New element data

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
        # NOTE: OCR vs Non-OCR have INTENTIONALLY different coord tolerances:
        #
        # OCR classes (signal, gks_*): No hard coord cutoff (up to 500m)
        #   - These have UNIQUE identifiers (signal names, GKS numbers)
        #   - Same name = same element, regardless of distance
        #   - Distance only affects score tiebreaking for duplicates
        #
        # Non-OCR classes (sverbinder, gm_block, etc.): 50m hard cutoff
        #   - These have AUTO-GENERATED names (not unique)
        #   - Must rely on coord_value for identity
        #   - Elements >50m apart are considered different elements
        # ============================================================

        # OCR classes: Match by text + coordinate value
        # These classes have meaningful anchor_text that identifies them
        # Wien: signal, gks_festkodiert, gks_gesteuert (from OCR)
        # Antwerp: Signal, coupling_coil_active, coupling_coil_disabled (from linked text_id)
        if cls in {'signal', 'gks_festkodiert', 'gks_gesteuert', 'Signal', 'coupling_coil_active', 'coupling_coil_disabled'}:
            return self._match_ocr_element(row1, row2)

        # Coordinate class: Match by coord_text (special class)
        elif cls == 'coordinate':
            return self._match_coordinate_element(row1, row2)

        # Non-OCR symbol classes: Match by SPATIAL POSITION + coord_value
        # These are symbols identified by position rather than text
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
            score += 0.6  # Exact match (allows spatial differentiation while staying above 0.7 threshold)
        else:
            # For signals: allow fuzzy match (OCR might have minor errors)
            text_sim = self._text_similarity(text1, text2)
            if text_sim < 0.9:  # Must be very similar
                return 0.0
            score += 0.7 * text_sim

        # Coordinate value similarity (secondary) - TIERED scoring
        coord_val1 = row1.get('coord_value')
        coord_val2 = row2.get('coord_value')

        # Check for valid coordinate values (not None and not NaN)
        val1_valid = coord_val1 is not None and not (isinstance(coord_val1, float) and math.isnan(coord_val1))
        val2_valid = coord_val2 is not None and not (isinstance(coord_val2, float) and math.isnan(coord_val2))

        if val1_valid and val2_valid:
            coord_diff = abs(coord_val1 - coord_val2)
            # Normal scoring: closer coordinates get higher scores
            # Fine-grained tiers help differentiate duplicates with similar coords
            if coord_diff < 0.001:  # < 1m (essentially identical)
                score += 0.15
            elif coord_diff < 0.005:  # < 5m
                score += 0.12
            elif coord_diff < 0.01:  # < 10m
                score += 0.10
            elif coord_diff < 0.02:  # < 20m
                score += 0.08
            elif coord_diff < 0.05:  # < 50m
                score += 0.06
            elif coord_diff < 0.1:  # < 100m
                score += 0.04
            elif coord_diff < 0.5:  # < 500m
                score += 0.02

        # Spatial proximity - TIERED scoring (critical for GKS duplicates)
        # This ensures when multiple GKS have same anchor_text, the spatially closest pair matches
        cx1 = row1.get('obb_cx') or row1.get('cx') or 0
        cy1 = row1.get('obb_cy') or row1.get('cy') or 0
        cx2 = row2.get('obb_cx') or row2.get('cx') or 0
        cy2 = row2.get('obb_cy') or row2.get('cy') or 0

        try:
            distance = ((float(cx1) - float(cx2))**2 + (float(cy1) - float(cy2))**2)**0.5
        except (ValueError, TypeError):
            distance = 9999

        # Tiered spatial bonus - important for distinguishing duplicates
        # Higher bonuses ensure correct pairing when multiple GKS have same anchor_text
        if distance < 50:
            spatial_bonus = 0.30  # Very close - high confidence
        elif distance < 100:
            spatial_bonus = 0.26
        elif distance < 150:
            spatial_bonus = 0.22
        elif distance < 250:
            spatial_bonus = 0.18
        elif distance < 400:
            spatial_bonus = 0.14
        elif distance < 600:
            spatial_bonus = 0.12
        else:
            spatial_bonus = 0.10  # Far but still ensures 0.7+ threshold with base 0.6

        score += spatial_bonus

        if self.DEBUG:
            coord_str = f"{coord_diff:.4f}" if val1_valid and val2_valid else "N/A"
            _debug_print(f"      [OCR Match] {text1} vs {text2}: base=0.6/0.7, coord_diff={coord_str}, dist={distance:.1f}px, spatial_bonus={spatial_bonus:.2f} → total={score:.3f}")

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
            if self.DEBUG:
                _debug_print(f"      [Coord Match] REJECTED: text1='{text1}', text2='{text2}' (empty)")
            return 0.0

        if text1 == text2:
            if self.DEBUG:
                _debug_print(f"      [Coord Match] '{text1}' == '{text2}': perfect match → 1.0")
            return 1.0  # Perfect match

        # Fuzzy match for slight variations
        text_sim = self._text_similarity(text1, text2)
        score = text_sim if text_sim > 0.9 else 0.0
        if self.DEBUG:
            _debug_print(f"      [Coord Match] '{text1}' vs '{text2}': similarity={text_sim:.3f} → {score:.3f}")
        return score

    def _is_auto_generated_name(self, anchor_text: str, cls: str) -> bool:
        """
        Check if an anchor_text is auto-generated (not meaningful for matching).

        Returns True for:
        - Pattern: "{class_name} {number}" (e.g., "sverbinder 7")
        - Fixed names: "GM", "PB" (for gm_block, prellbock)
        - Haltepunkt with signal: "haltepunkt 1 (MB456)"

        Args:
            anchor_text: The anchor text to check
            cls: The element class

        Returns:
            True if auto-generated, False if user-defined
        """
        if not anchor_text or not cls:
            return False

        anchor_text = str(anchor_text).strip()

        # FIXED NAMES - always auto-generated (not meaningful identifiers)
        if cls == 'gm_block' and anchor_text.upper() == 'GM':
            return True
        if cls == 'prellbock' and anchor_text.upper() == 'PB':
            return True

        # HALTEPUNKT with signal name in brackets
        if cls == 'haltepunkt':
            # Pattern: "haltepunkt {number}" OR "haltepunkt {number} ({signal})"
            if re.match(r'^haltepunkt\s*\d+(\s*\([^)]+\))?$', anchor_text, re.IGNORECASE):
                return True

        # STANDARD PATTERN: "{class_name} {number}"
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

    def _extract_haltepunkt_signal_name(self, anchor_text: str) -> Optional[str]:
        """
        Extract signal name from haltepunkt anchor_text.

        Format: "haltepunkt {counter} ({signal_name})"
        Example: "haltepunkt 1 (MB456)" → "MB456"

        Args:
            anchor_text: The haltepunkt anchor text

        Returns:
            Signal name if found, None otherwise
        """
        if not anchor_text:
            return None

        # Pattern: anything inside parentheses at the end
        match = re.search(r'\(([^)]+)\)\s*$', anchor_text)
        if match:
            return match.group(1).strip()

        return None

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

        #  CHECK anchor_text: detect auto-generated vs user-defined
        anchor1 = str(row1.get('anchor_text') or '').strip()
        anchor2 = str(row2.get('anchor_text') or '').strip()

        # ================================================================
        # SPECIAL HANDLING for haltepunkt class
        # Haltepunkt anchor_text format: "haltepunkt {counter} ({signal_name})"
        # The signal_name in brackets is the real identifier (e.g., "MB456")
        # ================================================================
        if cls == 'haltepunkt':
            signal1 = self._extract_haltepunkt_signal_name(anchor1)
            signal2 = self._extract_haltepunkt_signal_name(anchor2)

            if signal1 and signal2:
                # Both have signal names - use as primary identifier
                if signal1 == signal2:
                    # Same signal name = same haltepunkt, just counter changed
                    # High score - will match
                    score = 0.9

                    # Add tiered spatial proximity bonus (consistent with symbol matching)
                    cx1 = row1.get('obb_cx') or row1.get('cx') or 0
                    cy1 = row1.get('obb_cy') or row1.get('cy') or 0
                    cx2 = row2.get('obb_cx') or row2.get('cx') or 0
                    cy2 = row2.get('obb_cy') or row2.get('cy') or 0

                    try:
                        distance = ((float(cx1) - float(cx2))**2 + (float(cy1) - float(cy2))**2)**0.5
                    except (ValueError, TypeError):
                        distance = 9999

                    # Tiered spatial bonus (MUST match _match_symbol_element tiers)
                    if distance < 50:
                        spatial_bonus = 0.10
                    elif distance < 100:
                        spatial_bonus = 0.07
                    elif distance < 200:
                        spatial_bonus = 0.04
                    elif distance < 350:
                        spatial_bonus = 0.02
                    else:
                        spatial_bonus = 0.0

                    final_score = min(score + spatial_bonus, 1.0)
                    if self.DEBUG:
                        _debug_print(f"      [Haltepunkt Match] signal1='{signal1}' vs signal2='{signal2}': base=0.9, dist={distance:.1f}px, spatial_bonus={spatial_bonus:.2f} → total={final_score:.3f}")
                    return final_score
                else:
                    # Different signal names = different haltepunkts
                    if self.DEBUG:
                        _debug_print(f"      [Haltepunkt Match] REJECTED: signal1='{signal1}' ≠ signal2='{signal2}'")
                    return 0.0

            # If only one has signal name, or neither has, fall through to standard matching

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

        #  PRIMARY: coord_value match (most important for gm_block, sverbinder, etc.)
        # Use numeric coord_value with tolerance, not exact string match
        # This allows matching elements that moved slightly (e.g., 5.8548 → 5.8549)
        text1 = str(row1.get('coord_text') or '').strip()
        text2 = str(row2.get('coord_text') or '').strip()
        val1 = row1.get('coord_value')
        val2 = row2.get('coord_value')

        # Try numeric comparison first (with 0.05 km = ±50m tolerance for matching)
        COORD_MATCH_TOLERANCE = 0.05  # ±50 meters - elements within 50m are same element

        # Check for valid coord_values (not None AND not NaN)
        val1_valid = val1 is not None and not (isinstance(val1, float) and math.isnan(val1))
        val2_valid = val2 is not None and not (isinstance(val2, float) and math.isnan(val2))

        if val1_valid and val2_valid:
            try:
                numeric_diff = abs(float(val1) - float(val2))
                # Tiered scoring based on coordinate difference (±50m tolerance)
                # Closer matches get higher scores (Hungarian algorithm prefers these)
                if numeric_diff < 0.001:  # < 1m = essentially same position
                    score += 0.85
                elif numeric_diff < 0.005:  # < 5m = very close
                    score += 0.82
                elif numeric_diff < 0.01:  # < 10m = close
                    score += 0.78
                elif numeric_diff < 0.02:  # < 20m = medium distance
                    score += 0.74
                elif numeric_diff < 0.035:  # < 35m = far
                    score += 0.72
                elif numeric_diff < COORD_MATCH_TOLERANCE:  # < 50m = max tolerance
                    score += 0.70
                else:
                    # > 50m difference = different elements
                    return 0.0
            except (ValueError, TypeError):
                # Fallback to string comparison
                if text1 == text2:
                    score += 0.8
                elif text1 and text2:
                    return 0.0
        elif text1 and text2:
            if text1 == text2:
                # Same coord_text = very likely same element
                score += 0.8
            else:
                # Different coord_text = different elements, no match
                return 0.0
        elif not text1 and not text2:
            # Both have no coord_text - use TIERED spatial matching
            # This allows fallback matching with decreasing confidence
            # NOTE: These scores must be high enough to pass 0.7 threshold after spatial bonus
            cx1 = row1.get('obb_cx') or row1.get('cx') or 0
            cy1 = row1.get('obb_cy') or row1.get('cy') or 0
            cx2 = row2.get('obb_cx') or row2.get('cx') or 0
            cy2 = row2.get('obb_cy') or row2.get('cy') or 0

            try:
                distance = ((float(cx1) - float(cx2))**2 + (float(cy1) - float(cy2))**2)**0.5
            except (ValueError, TypeError):
                distance = 9999

            # Tiered scoring based on distance
            # Hungarian algorithm will prefer higher scores (closer matches)
            # Scores are set to ensure final score (with spatial bonus) passes 0.7 threshold
            if distance < 50:
                # Tier 1: Very close - high confidence (same PDF re-processed)
                score += 0.85  # + 0.15 spatial = 1.0
            elif distance < 100:
                # Tier 2: Close - good confidence
                score += 0.80  # + 0.10 spatial = 0.90
            elif distance < 200:
                # Tier 3: Medium distance - moderate confidence (layout shift)
                score += 0.72  # + 0.05 spatial = 0.77
            elif distance < 350:
                # Tier 4: Far - lower confidence (larger layout changes)
                score += 0.68  # + 0.02 spatial = 0.70 (just passes)
            else:
                # Too far apart - no match
                return 0.0
        else:
            # One has coord_text, other doesn't - shouldn't match
            # (one is linked to coordinate, other isn't)
            return 0.0

        #  SECONDARY: Spatial proximity bonus (TIERED)
        # This ensures when multiple elements have same coord_value, the closest pair matches
        # Combined with coord_value tiers, this creates a robust matching system
        cx1 = row1.get('obb_cx') or row1.get('cx') or 0
        cy1 = row1.get('obb_cy') or row1.get('cy') or 0
        cx2 = row2.get('obb_cx') or row2.get('cx') or 0
        cy2 = row2.get('obb_cy') or row2.get('cy') or 0

        try:
            distance = ((float(cx1) - float(cx2))**2 + (float(cy1) - float(cy2))**2)**0.5
        except (ValueError, TypeError):
            distance = 9999

        # Tiered spatial bonus - adds to coord_value score
        # Example: coord within 10m (0.8) + spatial < 50px (0.15) = 0.95 (very confident match)
        # Example: coord within 30m (0.7) + spatial < 200px (0.05) = 0.75 (good match)
        # Tiers aligned with no-coord-text fallback scoring above
        if distance < 50:
            spatial_bonus = 0.15  # Very close spatially
        elif distance < 100:
            spatial_bonus = 0.10  # Close
        elif distance < 200:
            spatial_bonus = 0.05  # Medium distance
        elif distance < 350:
            spatial_bonus = 0.02  # Far but still adds small bonus
        else:
            spatial_bonus = 0.0   # Too far for any bonus

        score += spatial_bonus

        if self.DEBUG:
            # Handle case where numeric_diff might not be defined (no-coord-text path)
            if val1_valid and val2_valid:
                try:
                    coord_str = f"{abs(float(val1) - float(val2)):.4f}km"
                except (ValueError, TypeError):
                    coord_str = "N/A"
            else:
                coord_str = f"text:{text1[:8] if text1 else 'None'}" if text1 or text2 else "no-coord"
            anchor_info = f"anchor1={anchor1[:15] if anchor1 else 'None'}, anchor2={anchor2[:15] if anchor2 else 'None'}"
            _debug_print(f"      [Symbol Match] {cls}: coord={coord_str}, dist={distance:.1f}px, spatial_bonus={spatial_bonus:.2f}, {anchor_info} → total={score:.3f}")

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
                'unchanged': [...]
            }
        """
        changes = {
            'added': [],
            'deleted': [],
            'moved': [],         # FA-011: Same identifier, different position
            'unchanged': []
        }
        
        #  FIXED: matches is now {old_id: new_id}, not {key: {old_key, new_key}}
        matched_old = set(matches.keys())
        matched_new = set(matches.values())

        # Deleted elements
        if self.DEBUG:
            deleted_count = sum(1 for old_id in dict_old if old_id not in matched_old)
            _debug_print(f"\n  [DEBUG] DELETED elements: {deleted_count}")

        for old_id, old_elem in dict_old.items():
            if old_id not in matched_old:
                if self.DEBUG:
                    cls = old_elem.get('cls', '?')
                    anchor = old_elem.get('anchor_text') or 'N/A'
                    coord_text = old_elem.get('coord_text') or 'N/A'
                    coord_val = old_elem.get('coord_value')
                    _debug_print(f"    DELETED [{cls}] anchor='{anchor}' coord_text='{coord_text}' coord_value={coord_val}")

                changes['deleted'].append(ElementChange(
                    change_type=ChangeType.DELETED,
                    severity=ChangeSeverity.MAJOR,
                    element_class=old_elem.get('cls', ''),
                    page=old_elem.get('page', 0),
                    old_data=old_elem
                ))

        # Added elements
        if self.DEBUG:
            added_count = sum(1 for new_id in dict_new if new_id not in matched_new)
            _debug_print(f"\n  [DEBUG] ADDED elements: {added_count}")

        for new_id, new_elem in dict_new.items():
            if new_id not in matched_new:
                if self.DEBUG:
                    cls = new_elem.get('cls', '?')
                    anchor = new_elem.get('anchor_text') or 'N/A'
                    coord_text = new_elem.get('coord_text') or 'N/A'
                    coord_val = new_elem.get('coord_value')
                    _debug_print(f"    ADDED [{cls}] anchor='{anchor}' coord_text='{coord_text}' coord_value={coord_val}")

                changes['added'].append(ElementChange(
                    change_type=ChangeType.ADDED,
                    severity=ChangeSeverity.MAJOR,
                    element_class=new_elem.get('cls', ''),
                    page=new_elem.get('page', 0),
                    new_data=new_elem
                ))

        # Modified/moved/unchanged elements
        if self.DEBUG:
            _debug_print(f"\n  [DEBUG] Classifying {len(matches)} matched elements:")

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

            if self.DEBUG:
                cls = old_elem.get('cls', '?')
                old_anchor = old_elem.get('anchor_text') or 'N/A'
                new_anchor = new_elem.get('anchor_text') or 'N/A'
                old_coord_text = old_elem.get('coord_text') or 'N/A'
                new_coord_text = new_elem.get('coord_text') or 'N/A'
                old_coord_val = old_elem.get('coord_value')
                new_coord_val = new_elem.get('coord_value')
                _debug_print(f"\n    [{cls}] anchor: '{old_anchor}' → '{new_anchor}'")
                _debug_print(f"           coord_text: '{old_coord_text}' → '{new_coord_text}'")
                _debug_print(f"           coord_value: {old_coord_val} → {new_coord_val}")
                if coord_value_changed:
                    delta = field_changes['coord_value'].get('delta_meters')
                    _debug_print(f"           → VERSCHOBEN: delta = {delta:+.1f}m" if delta is not None else "           → VERSCHOBEN: delta = N/A")
                elif field_changes:
                    _debug_print(f"           → MODIFIZIERT: {list(field_changes.keys())}")
                else:
                    _debug_print(f"           → UNCHANGED")

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
            #  Identifier changed

            # For non-OCR symbols: coord_text change = symbol renumbered
            # BUT: Skip if the numeric coord_values are within tolerance (same logical position)
            # This prevents "5.8500" vs "5.8501" from being flagged as "renumbered"
            if identifier_field == 'coord_text':
                # Check if coord_values are numerically close
                old_coord_val = old_row.get('coord_value')
                new_coord_val = new_row.get('coord_value')

                # Use matching tolerance (100m) not change detection tolerance (1m)
                RENUMBER_TOLERANCE = 0.1  # 100m - same as matching tolerance
                coords_numerically_same = False

                if old_coord_val is not None and new_coord_val is not None:
                    try:
                        if not (isinstance(old_coord_val, float) and math.isnan(old_coord_val)):
                            if not (isinstance(new_coord_val, float) and math.isnan(new_coord_val)):
                                if abs(float(old_coord_val) - float(new_coord_val)) < RENUMBER_TOLERANCE:
                                    coords_numerically_same = True
                    except (ValueError, TypeError):
                        pass

                # Only flag as "renumbered" if coordinates are genuinely different
                if not coords_numerically_same:
                    field_changes[identifier_field] = {
                        'old': old_identifier,
                        'new': new_identifier,
                        'change_type': 'symbol_renumbered',  #  More specific
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
                
                # Component-level comparison (OCR classes from Wien + Antwerp linked text_id classes)
                if cls in {'signal', 'gks_festkodiert', 'gks_gesteuert', 'Signal', 'coupling_coil_active', 'coupling_coil_disabled'}:
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
                    # Calculate delta - must check for BOTH None AND NaN
                    # Keep sign to show direction: + = forward (increasing km), - = backward (decreasing km)
                    delta = None
                    if old_val is not None and new_val is not None:
                        # Also check for NaN (NaN passes 'is not None' check!)
                        old_is_nan = isinstance(old_val, float) and math.isnan(old_val)
                        new_is_nan = isinstance(new_val, float) and math.isnan(new_val)
                        if not old_is_nan and not new_is_nan:
                            try:
                                delta = float(new_val) - float(old_val)  # Signed delta (no abs)
                            except (ValueError, TypeError):
                                delta = None

                    field_changes[field] = {
                        'old': old_val,
                        'new': new_val,
                        'delta': delta,
                        'delta_meters': delta * 1000 if delta is not None else None,
                        'description': f'{old_id_str} moved by {delta * 1000:+.1f}m' if delta is not None else None,
                        'element_identifier': old_id_str  #  Track which element moved
                    }
            
            # Text/categorical fields
            elif field in ['fahrtrichtung']:
                if str(old_val or '').strip() != str(new_val or '').strip():
                    field_changes[field] = {
                        'old': old_val,
                        'new': new_val,
                        'element_identifier': old_id_str  #  Track which element changed
                    }
        
        # ============================================================
        # STEP 3: Spatial change detection (skip for coordinate class)
        # ============================================================
        # NOTE: Angle changes are intentionally NOT tracked
        spatial_change = None
        if cls != 'coordinate':
            spatial_change = self._detect_spatial_change(old_row, new_row)
            if spatial_change:
                spatial_change['element_identifier'] = old_id_str  #  Track which element moved
        
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
            #  element_identifier will be added by _detect_changes()
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
                if delta_m and abs(delta_m) > 20:  # >20m (use abs since delta can be negative)
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
                if delta_m and abs(delta_m) > 5:  # >5m (use abs since delta can be negative)
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
            changes: Dictionary with 'added', 'deleted', 'moved', 'unchanged' lists

        Returns:
            Dictionary with summary statistics
        """
        summary = {
            'total_added': len(changes['added']),
            'total_deleted': len(changes['deleted']),
            'total_moved': len(changes['moved']),        # FA-011: Verschoben
            'total_unchanged': len(changes['unchanged']),
            'by_severity': {
                'major': 0,
                'moderate': 0,
                'minor': 0
            },
            'by_class': {},
            'by_page': {}
        }

        # Count by severity (for moved)
        for change in changes['moved']:
            summary['by_severity'][change.severity.value] += 1

        # Count by class
        all_changes = changes['added'] + changes['deleted'] + changes['moved']

        for change in all_changes:
            cls = change.element_class

            if cls not in summary['by_class']:
                summary['by_class'][cls] = {
                    'added': 0,
                    'deleted': 0,
                    'moved': 0
                }

            summary['by_class'][cls][change.change_type.value] += 1

        # Count by page
        for change in all_changes:
            page = change.page

            if page not in summary['by_page']:
                summary['by_page'][page] = {
                    'added': 0,
                    'deleted': 0,
                    'moved': 0
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
"""
Data Validation Module for Gleisplan Extraction
Detects errors, inconsistencies, and anomalies in extracted data
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
import re
from collections import Counter
import math

class ValidationResult:
    """Container for validation results"""
    def __init__(self, severity: str, message: str, row_id: Optional[int] = None, 
                 details: Optional[dict] = None):
        self.severity = severity  # 'ERROR', 'WARNING', 'INFO'
        self.message = message
        self.row_id = row_id
        self.details = details or {}
    
    def __repr__(self):
        return f"[{self.severity}] {self.message} (row_id={self.row_id})"

class DataValidator:
    """
    Comprehensive data validation for extracted gleisplan data
    """
    
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.results: List[ValidationResult] = []

    def validate_all(self) -> List[ValidationResult]:
        """Run all validation checks"""
        self.results = []
        
        # Basic integrity checks
        self.check_missing_required_fields()
        self.check_confidence_thresholds()
        self.check_coordinate_format()
        self.check_coordinate_values()
        self.check_signal_format()
        self.check_gks_format()
        self.check_fahrtrichtung_validity()
        
        # Spatial consistency checks
        self.check_duplicate_positions()
        self.check_overlapping_elements()
        self.check_coordinate_linking()
        
        # Signal duplicate validation
        self.check_signal_duplicates()
        
        # Statistical anomaly detection
        self.detect_outlier_coordinates()
        self.detect_unusual_confidence_patterns()
        
        # Cross-validation
        self.check_signal_coordinate_proximity()
        self.check_page_continuity()
        
        return self.results

    # ========================================================================
    # BASIC INTEGRITY CHECKS
    # ========================================================================
    
    def check_missing_required_fields(self):
        """
        Check for missing required fields
        ✅ UPDATED: Removed coord_text from coordinate required fields
        """
        required_by_class = {
            'signal': ['anchor_text', 'page'],
            'coordinate': ['page'],  # ✅ REMOVED 'coord_text' and 'coord_value'
            'gks_gesteuert': ['anchor_text', 'page'],
            'gks_festkodiert': ['anchor_text', 'page'],
        }
        
        for cls, required_fields in required_by_class.items():
            df_class = self.df[self.df['cls'] == cls]
            
            for field in required_fields:
                if field not in df_class.columns:
                    continue
                
                missing = df_class[df_class[field].isna() | (df_class[field] == '')]
                
                for _, row in missing.iterrows():
                    self.results.append(ValidationResult(
                        severity='ERROR',
                        message=f"{cls}: Fehlendes Pflichtfeld '{field}'",
                        row_id=int(row['row_id']),
                        details={'field': field, 'class': cls}
                    ))
    
    def check_confidence_thresholds(self):
        """Check for suspiciously low confidence values"""
        LOW_CONF_THRESHOLD = 0.3
        
        low_conf = self.df[self.df['conf'] < LOW_CONF_THRESHOLD]
        
        for _, row in low_conf.iterrows():
            self.results.append(ValidationResult(
                severity='WARNING',
                message=f"{row['cls']}: Niedrige Konfidenz ({row['conf']:.2f})",
                row_id=int(row['row_id']),
                details={'confidence': float(row['conf']), 'class': row['cls']}
            ))

    def check_coordinate_format(self):
        """
        Validate coordinate text format with STRICT rules:
        ✅ UPDATED: 
        - Allows brackets and uppercase letters (e.g., "0.0734(Gl.112)")
        - Allows lowercase 'l' in "Gl" pattern (e.g., "0.0734(Gl.112)" with lowercase l)
        - ERROR if OTHER lowercase letters found
        - ERROR if letters appear between digits in the numeric part
        """
        coords = self.df[self.df['cls'] == 'coordinate']
        
        for _, row in coords.iterrows():
            coord_text = str(row.get('coord_text', '')).strip()
            
            if not coord_text:
                continue  # Empty is OK (not required field anymore)
            
            # ✅ CHECK 1: No lowercase letters allowed (EXCEPT 'l' in "Gl" pattern)
            # First, temporarily replace valid "Gl" patterns to avoid false positives
            temp_text = coord_text
            
            # Replace all valid "Gl" patterns (with lowercase l) with placeholder
            # Patterns: Gl. or Gl followed by digit or end of bracket
            temp_text = re.sub(r'G[l]\.', 'GL.', temp_text)  # Gl. -> GL.
            temp_text = re.sub(r'G[l](?=\d)', 'GL', temp_text)  # Gl123 -> GL123
            temp_text = re.sub(r'G[l](?=\))', 'GL', temp_text)  # Gl) -> GL)
            
            # Now check for remaining lowercase letters
            remaining_lowercase = [c for c in temp_text if c.islower()]
            
            if remaining_lowercase:
                lowercase_chars = ''.join(set(remaining_lowercase))
                self.results.append(ValidationResult(
                    severity='ERROR',
                    message=f"Koordinate: Kleinbuchstaben gefunden '{coord_text}' (gefunden: {lowercase_chars})",
                    row_id=int(row['row_id']),
                    details={
                        'coord_text': coord_text,
                        'lowercase_chars': lowercase_chars,
                        'fix_suggestion': coord_text.upper()
                    }
                ))
                continue  # Skip further checks for this coordinate
            
            # ✅ CHECK 2: Extract numeric part (before any brackets)
            # Pattern: -?digits.digits (before any brackets or letters)
            numeric_part_match = re.match(r'^(-?\d+[.,]\d+)', coord_text)
            
            if not numeric_part_match:
                self.results.append(ValidationResult(
                    severity='ERROR',
                    message=f"Koordinate: Ungültiges Format '{coord_text}' (erwartet: Zahl.Zahl)",
                    row_id=int(row['row_id']),
                    details={'coord_text': coord_text}
                ))
                continue
            
            numeric_part = numeric_part_match.group(1)
            
            # ✅ CHECK 3: No letters between digits in numeric part
            # After removing the decimal separator, there should be only digits (and optional minus)
            numeric_clean = numeric_part.replace('.', '').replace(',', '').replace('-', '')
            
            if not numeric_clean.isdigit():
                # Find the offending characters
                invalid_chars = ''.join(c for c in numeric_clean if not c.isdigit())
                self.results.append(ValidationResult(
                    severity='ERROR',
                    message=f"Koordinate: Buchstaben zwischen Zahlen '{coord_text}' (gefunden: {invalid_chars} in '{numeric_part}')",
                    row_id=int(row['row_id']),
                    details={
                        'coord_text': coord_text,
                        'numeric_part': numeric_part,
                        'invalid_chars': invalid_chars
                    }
                ))
                continue
            
            # ✅ CHECK 4: Validate bracket part (if present)
            # Pattern: (Gl.XXX) or (GI.XXX) or similar
            bracket_part = coord_text[len(numeric_part):].strip()
            
            if bracket_part:
                # Should start with '(' and end with ')'
                if not (bracket_part.startswith('(') and bracket_part.endswith(')')):
                    self.results.append(ValidationResult(
                        severity='WARNING',
                        message=f"Koordinate: Klammern nicht korrekt geschlossen '{coord_text}'",
                        row_id=int(row['row_id']),
                        details={'coord_text': coord_text, 'bracket_part': bracket_part}
                    ))
                else:
                    # Check content inside brackets
                    inside_brackets = bracket_part[1:-1]  # Remove ( and )
                    
                    # ✅ UPDATED: Allow uppercase letters, digits, dots, slashes, hyphens
                    # AND lowercase 'l' (for "Gl" pattern)
                    # Pattern: Should match things like "Gl.112", "GI.13", "PF13", etc.
                    
                    # First, replace valid "Gl" patterns
                    temp_inside = inside_brackets
                    temp_inside = re.sub(r'G[l]\.', 'GL.', temp_inside)
                    temp_inside = re.sub(r'G[l](?=\d)', 'GL', temp_inside)
                    temp_inside = re.sub(r'G[l]$', 'GL', temp_inside)
                    
                    # Now check if remaining characters are valid
                    allowed_pattern = re.compile(r'^[A-ZÄÖÜ0-9.\-/]+$')
                    
                    if not allowed_pattern.match(temp_inside):
                        # Find invalid characters (excluding the valid 'l' in Gl)
                        invalid_chars = []
                        for i, c in enumerate(inside_brackets):
                            # Skip 'l' if it's part of "Gl"
                            if c == 'l':
                                if i > 0 and inside_brackets[i-1] == 'G':
                                    continue  # Valid 'l' in "Gl"
                            
                            if not re.match(r'[A-ZÄÖÜ0-9.\-/l]', c):
                                invalid_chars.append(c)
                            elif c.islower() and c != 'l':
                                invalid_chars.append(c)
                        
                        if invalid_chars:
                            invalid_chars_str = ''.join(set(invalid_chars))
                            self.results.append(ValidationResult(
                                severity='ERROR',
                                message=f"Koordinate: Ungültige Zeichen in Klammern '{coord_text}' (gefunden: {invalid_chars_str})",
                                row_id=int(row['row_id']),
                                details={
                                    'coord_text': coord_text,
                                    'bracket_content': inside_brackets,
                                    'invalid_chars': invalid_chars_str
                                }
                            ))
            
            # ✅ ALL CHECKS PASSED - This is a valid coordinate format
            # (No warning/error added)

    def check_coordinate_values(self):
        """
        Check coordinate values for plausibility
        ✅ UPDATED: Removed warning for unparseable coord_text
        """
        coords = self.df[self.df['cls'] == 'coordinate']
        
        for _, row in coords.iterrows():
            coord_val = row.get('coord_value')
            
            # ✅ REMOVED: Warning for missing coord_value when coord_text exists
            # This is now silently accepted (parsing failures are OK)
            
            if pd.isna(coord_val):
                continue  # Skip if no value
            
            # Check for unrealistic values (adjust based on your project)
            if abs(coord_val) > 1000:
                self.results.append(ValidationResult(
                    severity='WARNING',
                    message=f"Koordinate: Ungewöhnlich großer Wert ({coord_val:.4f})",
                    row_id=int(row['row_id']),
                    details={'coord_value': float(coord_val)}
                ))
    
    def check_signal_format(self):
        """Validate signal name format"""
        SIGNAL_PATTERN = re.compile(r'^[A-ZÄÖÜ]{1,4}\d{1,4}$')
        
        signals = self.df[self.df['cls'] == 'signal']
        
        for _, row in signals.iterrows():
            signal_text = str(row.get('anchor_text', '')).strip()
            
            if not signal_text:
                continue
            
            if not SIGNAL_PATTERN.match(signal_text):
                self.results.append(ValidationResult(
                    severity='WARNING',
                    message=f"Signal: Ungültiges Format '{signal_text}'",
                    row_id=int(row['row_id']),
                    details={'signal_text': signal_text}
                ))
  
    def check_signal_duplicates(self):
        """
        Check for duplicate signal names and validate their consistency
        ✅ NEW: Validates that duplicate signals have:
        - Same Fahrtrichtung across all instances
        - Same coordinate across all instances
        - Warns if any instance is missing coordinate or Fahrtrichtung
        """
        signals = self.df[self.df['cls'] == 'signal'].copy()
        
        if signals.empty:
            return
        
        # Group by signal name (anchor_text)
        grouped = signals.groupby('anchor_text')
        
        for signal_name, group in grouped:
            if pd.isna(signal_name) or not signal_name:
                continue
            
            # Only check if there are multiple instances
            instances = len(group)
            
            if instances == 1:
                # Single instance - just check if it has coord and fahrtrichtung
                row = group.iloc[0]
                
                if pd.isna(row.get('coord_text')) or not row.get('coord_text'):
                    self.results.append(ValidationResult(
                        severity='WARNING',
                        message=f"Signal '{signal_name}': Keine Koordinate verknüpft",
                        row_id=int(row['row_id']),
                        details={
                            'signal_name': signal_name,
                            'instances': 1
                        }
                    ))
                
                if pd.isna(row.get('fahrtrichtung')) or not row.get('fahrtrichtung'):
                    self.results.append(ValidationResult(
                        severity='WARNING',
                        message=f"Signal '{signal_name}': Keine Fahrtrichtung angegeben",
                        row_id=int(row['row_id']),
                        details={
                            'signal_name': signal_name,
                            'instances': 1
                        }
                    ))
            
            else:
                # Multiple instances - check for consistency
                row_ids = group['row_id'].tolist()
                
                # ✅ CHECK 1: Collect all coordinates
                coords = group['coord_text'].dropna()
                coords = coords[coords != '']  # Remove empty strings
                unique_coords = coords.unique()
                
                # ✅ CHECK 2: Collect all Fahrtrichtung values
                fahrtrichtungen = group['fahrtrichtung'].dropna()
                fahrtrichtungen = fahrtrichtungen[fahrtrichtungen != '']
                unique_fahrtrichtungen = fahrtrichtungen.unique()
                
                # ✅ ERROR: Different coordinates for same signal
                if len(unique_coords) > 1:
                    coord_details = []
                    for _, row in group.iterrows():
                        coord_details.append({
                            'row_id': int(row['row_id']),
                            'coord_text': row.get('coord_text', ''),
                            'page': int(row['page'])
                        })
                    
                    self.results.append(ValidationResult(
                        severity='ERROR',
                        message=f"Signal '{signal_name}': Unterschiedliche Koordinaten bei {instances} Instanzen ({', '.join(str(c) for c in unique_coords)})",
                        row_id=int(row_ids[0]),
                        details={
                            'signal_name': signal_name,
                            'instances': instances,
                            'unique_coordinates': list(unique_coords),
                            'all_instances': coord_details
                        }
                    ))
                
                # ✅ ERROR: Different Fahrtrichtung for same signal
                if len(unique_fahrtrichtungen) > 1:
                    fahrt_details = []
                    for _, row in group.iterrows():
                        fahrt_details.append({
                            'row_id': int(row['row_id']),
                            'fahrtrichtung': row.get('fahrtrichtung', ''),
                            'page': int(row['page'])
                        })
                    
                    self.results.append(ValidationResult(
                        severity='ERROR',
                        message=f"Signal '{signal_name}': Unterschiedliche Fahrtrichtungen bei {instances} Instanzen ({', '.join(str(f) for f in unique_fahrtrichtungen)})",
                        row_id=int(row_ids[0]),
                        details={
                            'signal_name': signal_name,
                            'instances': instances,
                            'unique_fahrtrichtungen': list(unique_fahrtrichtungen),
                            'all_instances': fahrt_details
                        }
                    ))
                
                # ✅ WARNING: Some instances missing coordinate
                missing_coord_count = group['coord_text'].isna().sum() + (group['coord_text'] == '').sum()
                
                if missing_coord_count > 0 and missing_coord_count < instances:
                    # Some have coords, some don't
                    missing_rows = []
                    for _, row in group.iterrows():
                        if pd.isna(row.get('coord_text')) or not row.get('coord_text'):
                            missing_rows.append({
                                'row_id': int(row['row_id']),
                                'page': int(row['page'])
                            })
                    
                    self.results.append(ValidationResult(
                        severity='WARNING',
                        message=f"Signal '{signal_name}': {missing_coord_count} von {instances} Instanzen ohne Koordinate",
                        row_id=int(row_ids[0]),
                        details={
                            'signal_name': signal_name,
                            'instances': instances,
                            'missing_count': missing_coord_count,
                            'missing_instances': missing_rows
                        }
                    ))
                
                elif missing_coord_count == instances:
                    # All instances missing coordinate
                    self.results.append(ValidationResult(
                        severity='WARNING',
                        message=f"Signal '{signal_name}': Alle {instances} Instanzen ohne Koordinate",
                        row_id=int(row_ids[0]),
                        details={
                            'signal_name': signal_name,
                            'instances': instances,
                            'all_row_ids': [int(r) for r in row_ids]
                        }
                    ))
                
                # ✅ WARNING: Some instances missing Fahrtrichtung
                missing_fahrt_count = group['fahrtrichtung'].isna().sum() + (group['fahrtrichtung'] == '').sum()
                
                if missing_fahrt_count > 0 and missing_fahrt_count < instances:
                    # Some have Fahrtrichtung, some don't
                    missing_rows = []
                    for _, row in group.iterrows():
                        if pd.isna(row.get('fahrtrichtung')) or not row.get('fahrtrichtung'):
                            missing_rows.append({
                                'row_id': int(row['row_id']),
                                'page': int(row['page'])
                            })
                    
                    self.results.append(ValidationResult(
                        severity='WARNING',
                        message=f"Signal '{signal_name}': {missing_fahrt_count} von {instances} Instanzen ohne Fahrtrichtung",
                        row_id=int(row_ids[0]),
                        details={
                            'signal_name': signal_name,
                            'instances': instances,
                            'missing_count': missing_fahrt_count,
                            'missing_instances': missing_rows
                        }
                    ))
                
                elif missing_fahrt_count == instances:
                    # All instances missing Fahrtrichtung
                    self.results.append(ValidationResult(
                        severity='WARNING',
                        message=f"Signal '{signal_name}': Alle {instances} Instanzen ohne Fahrtrichtung",
                        row_id=int(row_ids[0]),
                        details={
                            'signal_name': signal_name,
                            'instances': instances,
                            'all_row_ids': [int(r) for r in row_ids]
                        }
                    ))  
  
    def check_gks_format(self):
        """Validate GKS number format"""
        GKS_PATTERN = re.compile(r'^\d{3,4}$')
        
        gks = self.df[self.df['cls'].isin(['gks_gesteuert', 'gks_festkodiert'])]
        
        for _, row in gks.iterrows():
            gks_text = str(row.get('anchor_text', '')).strip()
            
            if not gks_text:
                continue
            
            if not GKS_PATTERN.match(gks_text):
                self.results.append(ValidationResult(
                    severity='WARNING',
                    message=f"GKS: Ungültiges Format '{gks_text}' (erwartet 3-4 Ziffern)",
                    row_id=int(row['row_id']),
                    details={'gks_text': gks_text, 'class': row['cls']}
                ))
    
    def check_fahrtrichtung_validity(self):
        """Check Fahrtrichtung values"""
        signals = self.df[self.df['cls'] == 'signal']
        
        for _, row in signals.iterrows():
            fahrt = row.get('fahrtrichtung')
            
            if pd.notna(fahrt) and fahrt not in ['A', 'B', '', None]:
                self.results.append(ValidationResult(
                    severity='ERROR',
                    message=f"Signal: Ungültige Fahrtrichtung '{fahrt}' (nur A oder B erlaubt)",
                    row_id=int(row['row_id']),
                    details={'fahrtrichtung': str(fahrt)}
                ))
    
    # ========================================================================
    # SPATIAL CONSISTENCY CHECKS
    # ========================================================================
    
    def check_duplicate_positions(self):
        """Detect elements at identical positions"""
        POSITION_TOLERANCE = 10  # pixels
        
        for cls in self.df['cls'].unique():
            df_class = self.df[self.df['cls'] == cls]
            
            if cls == 'coordinate':
                pos_cols = ['cx1', 'cy1']
            else:
                pos_cols = ['ax1', 'ay1']
            
            if not all(col in df_class.columns for col in pos_cols):
                continue
            
            # Group by approximate position
            df_class = df_class.copy()
            df_class['pos_x_rounded'] = (df_class[pos_cols[0]] / POSITION_TOLERANCE).round() * POSITION_TOLERANCE
            df_class['pos_y_rounded'] = (df_class[pos_cols[1]] / POSITION_TOLERANCE).round() * POSITION_TOLERANCE
            
            duplicates = df_class.groupby(['page', 'pos_x_rounded', 'pos_y_rounded']).filter(lambda x: len(x) > 1)
            
            for (page, x, y), group in duplicates.groupby(['page', 'pos_x_rounded', 'pos_y_rounded']):
                row_ids = group['row_id'].tolist()
                self.results.append(ValidationResult(
                    severity='WARNING',
                    message=f"{cls}: {len(group)} Elemente an gleicher Position (Seite {page})",
                    row_id=int(row_ids[0]),
                    details={'duplicate_row_ids': [int(r) for r in row_ids], 'position': (float(x), float(y))}
                ))
    
    def check_overlapping_elements(self):
        """Detect heavily overlapping bounding boxes"""
        OVERLAP_THRESHOLD = 0.7  # 70% overlap
        
        for page in self.df['page'].unique():
            df_page = self.df[self.df['page'] == page]
            
            for i, row1 in df_page.iterrows():
                for j, row2 in df_page.iterrows():
                    if i >= j:
                        continue
                    
                    # Get bounding boxes
                    if row1['cls'] == 'coordinate':
                        box1 = (row1.get('cx1'), row1.get('cy1'), row1.get('cx2'), row1.get('cy2'))
                    else:
                        box1 = (row1.get('ax1'), row1.get('ay1'), row1.get('ax2'), row1.get('ay2'))
                    
                    if row2['cls'] == 'coordinate':
                        box2 = (row2.get('cx1'), row2.get('cy1'), row2.get('cx2'), row2.get('cy2'))
                    else:
                        box2 = (row2.get('ax1'), row2.get('ay1'), row2.get('ax2'), row2.get('ay2'))
                    
                    if any(pd.isna(v) for v in box1 + box2):
                        continue
                    
                    # Calculate IoU
                    iou = self._calculate_iou(box1, box2)
                    
                    if iou > OVERLAP_THRESHOLD:
                        self.results.append(ValidationResult(
                            severity='WARNING',
                            message=f"Starke Überlappung ({iou:.1%}) zwischen {row1['cls']} und {row2['cls']}",
                            row_id=int(row1['row_id']),
                            details={
                                'row_id_2': int(row2['row_id']),
                                'iou': float(iou),
                                'class_1': row1['cls'],
                                'class_2': row2['cls']
                            }
                        ))
    
    def check_coordinate_linking(self):
        """Check if anchors have appropriate coordinate links"""
        LINKABLE_CLASSES = ['gks_gesteuert', 'gks_festkodiert', 'isolierstoß']
        
        for cls in LINKABLE_CLASSES:
            df_class = self.df[self.df['cls'] == cls]
            
            missing_coords = df_class[df_class['coord_text'].isna() | (df_class['coord_text'] == '')]
            
            for _, row in missing_coords.iterrows():
                self.results.append(ValidationResult(
                    severity='INFO',
                    message=f"{cls}: Keine Koordinate verknüpft",
                    row_id=int(row['row_id']),
                    details={'class': cls, 'anchor_text': row.get('anchor_text', '')}
                ))
    
    # ========================================================================
    # STATISTICAL ANOMALY DETECTION
    # ========================================================================
    
    def detect_outlier_coordinates(self):
        """Detect coordinate values that are statistical outliers"""
        coords = self.df[self.df['cls'] == 'coordinate'].copy()
        
        if len(coords) < 10:
            return  # Not enough data
        
        values = coords['coord_value'].dropna()
        
        if len(values) < 10:
            return
        
        # Use IQR method
        Q1 = values.quantile(0.25)
        Q3 = values.quantile(0.75)
        IQR = Q3 - Q1
        
        lower_bound = Q1 - 3 * IQR
        upper_bound = Q3 + 3 * IQR
        
        outliers = coords[(coords['coord_value'] < lower_bound) | (coords['coord_value'] > upper_bound)]
        
        for _, row in outliers.iterrows():
            self.results.append(ValidationResult(
                severity='INFO',
                message=f"Koordinate: Statistischer Ausreißer ({row['coord_value']:.4f})",
                row_id=int(row['row_id']),
                details={
                    'coord_value': float(row['coord_value']),
                    'expected_range': (float(lower_bound), float(upper_bound))
                }
            ))
    
    def detect_unusual_confidence_patterns(self):
        """Detect unusual confidence patterns by class"""
        for cls in self.df['cls'].unique():
            df_class = self.df[self.df['cls'] == cls]
            
            if len(df_class) < 5:
                continue
            
            mean_conf = df_class['conf'].mean()
            std_conf = df_class['conf'].std()
            
            # Flag elements with confidence > 2 std deviations below mean
            low_conf_threshold = mean_conf - 2 * std_conf
            
            unusual = df_class[df_class['conf'] < low_conf_threshold]
            
            for _, row in unusual.iterrows():
                self.results.append(ValidationResult(
                    severity='INFO',
                    message=f"{cls}: Ungewöhnlich niedrige Konfidenz für diese Klasse ({row['conf']:.2f} vs. Durchschnitt {mean_conf:.2f})",
                    row_id=int(row['row_id']),
                    details={
                        'confidence': float(row['conf']),
                        'class_mean': float(mean_conf),
                        'class_std': float(std_conf)
                    }
                ))
    
    # ========================================================================
    # CROSS-VALIDATION
    # ========================================================================
    
    def check_signal_coordinate_proximity(self):
        """Check if signals and their linked coordinates are reasonably close"""
        MAX_DISTANCE = 500  # pixels
        
        signals = self.df[self.df['cls'] == 'signal']
        
        for _, signal in signals.iterrows():
            if pd.isna(signal.get('coord_text')) or not signal.get('coord_text'):
                continue
            
            # Find the coordinate
            coord_text = signal['coord_text']
            coords = self.df[(self.df['cls'] == 'coordinate') & (self.df['coord_text'] == coord_text)]
            
            if coords.empty:
                self.results.append(ValidationResult(
                    severity='WARNING',
                    message=f"Signal: Verknüpfte Koordinate '{coord_text}' nicht gefunden",
                    row_id=int(signal['row_id']),
                    details={'coord_text': coord_text}
                ))
                continue
            
            coord = coords.iloc[0]
            
            # Calculate distance
            signal_cx = (signal.get('ax1', 0) + signal.get('ax2', 0)) / 2
            signal_cy = (signal.get('ay1', 0) + signal.get('ay2', 0)) / 2
            coord_cx = (coord.get('cx1', 0) + coord.get('cx2', 0)) / 2
            coord_cy = (coord.get('cy1', 0) + coord.get('cy2', 0)) / 2
            
            distance = math.sqrt((signal_cx - coord_cx)**2 + (signal_cy - coord_cy)**2)
            
            if distance > MAX_DISTANCE:
                self.results.append(ValidationResult(
                    severity='WARNING',
                    message=f"Signal: Große Distanz zur verknüpften Koordinate ({distance:.0f}px)",
                    row_id=int(signal['row_id']),
                    details={
                        'distance': float(distance),
                        'coord_text': coord_text,
                        'coord_row_id': int(coord['row_id'])
                    }
                ))
    
    def check_page_continuity(self):
        """Check for missing pages or gaps"""
        pages = sorted(self.df['page'].unique())
        
        if not pages:
            return
        
        expected_pages = set(range(pages[0], pages[-1] + 1))
        actual_pages = set(pages)
        
        missing_pages = expected_pages - actual_pages
        
        if missing_pages:
            self.results.append(ValidationResult(
                severity='INFO',
                message=f"Fehlende Seiten: {sorted(missing_pages)}",
                details={'missing_pages': sorted(missing_pages)}
            ))
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def _calculate_iou(self, box1: tuple, box2: tuple) -> float:
        """Calculate Intersection over Union"""
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2
        
        # Intersection
        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)
        
        if x2_i < x1_i or y2_i < y1_i:
            return 0.0
        
        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        
        # Union
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0
    
    def get_summary(self) -> dict:
        """Get validation summary statistics"""
        summary = {
            'total_checks': len(self.results),
            'errors': len([r for r in self.results if r.severity == 'ERROR']),
            'warnings': len([r for r in self.results if r.severity == 'WARNING']),
            'info': len([r for r in self.results if r.severity == 'INFO']),
        }
        
        # Group by message type
        message_counts = Counter(r.message.split(':')[0] for r in self.results)
        summary['by_type'] = dict(message_counts)
        
        return summary
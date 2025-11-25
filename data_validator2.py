"""
Enhanced Data Validation Module with Auto-Correction Support
Detects errors, inconsistencies, and provides automatic fixes
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
import re
from collections import Counter
from dataclasses import dataclass, field
import math

# ========================================================================
# DATA CLASSES
# ========================================================================

@dataclass
class ValidationIssue:
    """Single validation issue with auto-correction support"""
    row_id: int
    severity: str  # 'error', 'warning', 'info'
    category: str  # 'missing_data', 'format', 'duplicate', etc.
    field: str
    message: str
    current_value: any
    suggested_value: any = None
    auto_correctable: bool = False
    confidence: float = 0.0  # 0.0 to 1.0
    context: dict = None
    
    def __post_init__(self):
        if self.context is None:
            self.context = {}
    
    # ✅ ADD THIS PROPERTY (for compatibility with dialog)
    @property
    def correction_confidence(self) -> float:
        """Alias for confidence (for dialog compatibility)"""
        return self.confidence

@dataclass
class ValidationResult:
    """Container for all validation results"""
    total_issues: int
    issues: List[ValidationIssue]
    df: pd.DataFrame
    auto_corrections: List[tuple] = None  # ✅ ADD THIS
    
    def __post_init__(self):
        if self.auto_corrections is None:
            self.auto_corrections = []
    
    def get_by_severity(self, severity: str) -> List[ValidationIssue]:
        """Get issues by severity level"""
        return [i for i in self.issues if i.severity.lower() == severity.lower()]
    
    def get_by_category(self, category: str) -> List[ValidationIssue]:
        """Get issues by category"""
        return [i for i in self.issues if i.category == category]
    
    def get_categories(self) -> List[str]:
        """Get list of all unique categories"""
        if not self.issues:
            return []
        return list(set(i.category for i in self.issues))
    
    def get_summary(self) -> dict:
        """Get summary statistics"""
        auto_correctable_issues = [i for i in self.issues if i.auto_correctable]
        high_conf = [i for i in auto_correctable_issues if i.confidence >= 0.8]
        med_conf = [i for i in auto_correctable_issues if 0.6 <= i.confidence < 0.8]
        
        return {
            'total_issues': self.total_issues,
            'errors': len(self.get_by_severity('error')),
            'warnings': len(self.get_by_severity('warning')),
            'info': len(self.get_by_severity('info')),
            'auto_correctable': len(auto_correctable_issues),  # ✅ This is now a number
            'high_confidence_fixes': len(high_conf),
            'medium_confidence_fixes': len(med_conf),
            'corrections_applied': len(self.auto_corrections),
            'by_category': {
                category: len(self.get_by_category(category))
                for category in self.get_categories()
            }
        }
    
    @property
    def stats(self) -> dict:
        """Statistics property for compatibility"""
        return self.get_summary()
    
    @property
    def total(self) -> int:
        """Alias for total_issues"""
        return self.total_issues
    
    @property
    def errors(self) -> int:
        """Count of error-level issues"""
        return len(self.get_by_severity('error'))
    
    @property
    def warnings(self) -> int:
        """Count of warning-level issues"""
        return len(self.get_by_severity('warning'))
    
    @property
    def info(self) -> int:
        """Count of info-level issues"""
        return len(self.get_by_severity('info'))
    
    @property
    def auto_correctable(self) -> int:
        """Count of auto-correctable issues"""
        return len([i for i in self.issues if i.auto_correctable])
    
    def __repr__(self):
        return f"ValidationResult(total={self.total_issues}, errors={self.errors}, warnings={self.warnings})"


# ========================================================================
# ENHANCED DATA VALIDATOR
# ========================================================================

class EnhancedDataValidator:
    """Enhanced validator with auto-correction support"""
    
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.issues: List[ValidationIssue] = []
    
    # ========================================================================
    # MAIN VALIDATION METHOD
    # ========================================================================
    
    def validate_all(self, auto_correct: bool = False) -> ValidationResult:
        """
        Run all validation checks.
        
        Args:
            auto_correct: If True, apply auto-corrections immediately
            
        Returns:
            ValidationResult with all issues found
        """
        self.issues.clear()
        
        # ✅ ESSENTIAL CHECKS
        self.issues.extend(self.check_missing_coordinates())
        self.issues.extend(self.check_duplicate_ids())
        self.issues.extend(self.check_coordinate_format())
        self.issues.extend(self.check_signal_format())
        self.issues.extend(self.check_gks_format())
        self.issues.extend(self.check_fahrtrichtung_validity())
        
        # ✅ ADDITIONAL CHECKS
        self.issues.extend(self.check_signal_duplicates())
        self.issues.extend(self.check_confidence_thresholds(min_confidence=0.3))
        self.issues.extend(self.check_coordinate_values())
        
        # ✅ Track corrections
        corrections_log = []
        
        # Apply auto-corrections if requested
        if auto_correct:
            corrections_log = self._apply_auto_corrections()
        
        # Create result
        return ValidationResult(
            total_issues=len(self.issues),
            issues=self.issues,
            df=self.df,
            auto_corrections=corrections_log  # ✅ ADD THIS
        )
    
    # ========================================================================
    # BASIC INTEGRITY CHECKS (from old validator)
    # ========================================================================
    
    def check_missing_coordinates(self) -> List[ValidationIssue]:
        """Check for anchors without coordinates"""
        issues = []
        
        # Classes that should have coordinates
        LINKABLE_CLASSES = ['signal', 'gks_gesteuert', 'gks_festkodiert', 'isolierstoß']
        
        for cls in LINKABLE_CLASSES:
            df_class = self.df[self.df['cls'] == cls]
            
            missing = df_class[df_class['coord_text'].isna() | (df_class['coord_text'] == '')]
            
            for _, row in missing.iterrows():
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='warning',
                    category='missing_data',
                    field='coord_text',
                    message=f"{cls}: Keine Koordinate verknüpft",
                    current_value=None,
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=0.0,
                    context={
                        'class': cls,
                        'anchor_text': row.get('anchor_text', '')
                    }
                ))
        
        return issues
    
    def check_duplicate_ids(self) -> List[ValidationIssue]:
        """Check for duplicate IDs within same class"""
        issues = []
        
        for cls in self.df['cls'].unique():
            df_class = self.df[self.df['cls'] == cls]
            
            # Check anchor_text duplicates
            if 'anchor_text' in df_class.columns:
                duplicates = df_class[df_class.duplicated(subset=['anchor_text'], keep=False)]
                duplicates = duplicates[duplicates['anchor_text'].notna()]
                duplicates = duplicates[duplicates['anchor_text'] != '']
                
                for anchor_text, group in duplicates.groupby('anchor_text'):
                    row_ids = group['row_id'].tolist()
                    
                    issues.append(ValidationIssue(
                        row_id=row_ids[0],
                        severity='warning',
                        category='duplicate',
                        field='anchor_text',
                        message=f"{cls}: Doppelte ID '{anchor_text}' ({len(row_ids)} Vorkommen)",
                        current_value=anchor_text,
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'class': cls,
                            'duplicate_row_ids': row_ids,
                            'count': len(row_ids)
                        }
                    ))
        
        return issues
    
    def check_coordinate_format(self) -> List[ValidationIssue]:
        """Validate coordinate text format and suggest fixes"""
        issues = []
        coords = self.df[self.df['cls'] == 'coordinate']
        
        for _, row in coords.iterrows():
            coord_text = str(row.get('coord_text', '')).strip()
            
            if not coord_text:
                continue
            
            # ✅ CHECK 1: Lowercase letters (except 'l' in "Gl")
            temp_text = coord_text
            temp_text = re.sub(r'G[l]\.', 'GL.', temp_text)
            temp_text = re.sub(r'G[l](?=\d)', 'GL', temp_text)
            temp_text = re.sub(r'G[l](?=\))', 'GL', temp_text)
            
            remaining_lowercase = [c for c in temp_text if c.islower()]
            
            if remaining_lowercase:
                lowercase_chars = ''.join(set(remaining_lowercase))
                suggested = coord_text.upper()
                
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='error',
                    category='format',
                    field='coord_text',
                    message=f"Koordinate: Kleinbuchstaben gefunden '{coord_text}'",
                    current_value=coord_text,
                    suggested_value=suggested,
                    auto_correctable=True,
                    confidence=0.95,
                    context={
                        'lowercase_chars': lowercase_chars,
                        'fix_type': 'uppercase_conversion'
                    }
                ))
                continue
            
            # ✅ CHECK 2: Validate numeric part
            numeric_part_match = re.match(r'^(-?\d+[.,]\d+)', coord_text)
            
            if not numeric_part_match:
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='error',
                    category='format',
                    field='coord_text',
                    message=f"Koordinate: Ungültiges Format '{coord_text}'",
                    current_value=coord_text,
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=0.0,
                    context={'expected_format': 'Zahl.Zahl'}
                ))
                continue
            
            numeric_part = numeric_part_match.group(1)
            numeric_clean = numeric_part.replace('.', '').replace(',', '').replace('-', '')
            
            if not numeric_clean.isdigit():
                invalid_chars = ''.join(c for c in numeric_clean if not c.isdigit())
                
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='error',
                    category='format',
                    field='coord_text',
                    message=f"Koordinate: Buchstaben zwischen Zahlen '{coord_text}'",
                    current_value=coord_text,
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=0.0,
                    context={
                        'numeric_part': numeric_part,
                        'invalid_chars': invalid_chars
                    }
                ))
                continue
            
            # ✅ CHECK 3: Validate brackets
            bracket_part = coord_text[len(numeric_part):].strip()
            
            if bracket_part:
                if not (bracket_part.startswith('(') and bracket_part.endswith(')')):
                    issues.append(ValidationIssue(
                        row_id=row['row_id'],
                        severity='warning',
                        category='format',
                        field='coord_text',
                        message=f"Koordinate: Klammern nicht korrekt '{coord_text}'",
                        current_value=coord_text,
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={'bracket_part': bracket_part}
                    ))
        
        return issues
    
    def check_signal_format(self) -> List[ValidationIssue]:
        """Validate signal ID format (e.g., 'A101', 'BHR201')"""
        issues = []
        SIGNAL_PATTERN = re.compile(r'^[A-ZÄÖÜ]{1,4}\d{1,4}$')
        
        signals = self.df[self.df['cls'] == 'signal']
        
        for _, row in signals.iterrows():
            signal_text = str(row.get('anchor_text', '')).strip()
            
            if not signal_text:
                continue
            
            if not SIGNAL_PATTERN.match(signal_text):
                # Try to suggest a fix
                suggested = signal_text.upper().replace(' ', '').replace('-', '')
                
                if SIGNAL_PATTERN.match(suggested):
                    auto_correctable = True
                    confidence = 0.8
                else:
                    suggested = None
                    auto_correctable = False
                    confidence = 0.0
                
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='warning',
                    category='format',
                    field='anchor_text',
                    message=f"Signal: Ungültiges Format '{signal_text}'",
                    current_value=signal_text,
                    suggested_value=suggested,
                    auto_correctable=auto_correctable,
                    confidence=confidence,
                    context={'expected_pattern': 'Buchstaben+Zahlen (z.B. A101)'}
                ))
        
        return issues
    
    def check_gks_format(self) -> List[ValidationIssue]:
        """Validate GKS format (3-4 digits)"""
        issues = []
        GKS_PATTERN = re.compile(r'^\d{3,4}$')
        
        gks = self.df[self.df['cls'].isin(['gks_gesteuert', 'gks_festkodiert'])]
        
        for _, row in gks.iterrows():
            gks_text = str(row.get('anchor_text', '')).strip()
            
            if not gks_text:
                continue
            
            if not GKS_PATTERN.match(gks_text):
                # Try to fix by removing non-digits
                suggested = re.sub(r'\D', '', gks_text)
                
                if GKS_PATTERN.match(suggested):
                    auto_correctable = True
                    confidence = 0.7
                else:
                    suggested = None
                    auto_correctable = False
                    confidence = 0.0
                
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='warning',
                    category='format',
                    field='anchor_text',
                    message=f"GKS: Ungültiges Format '{gks_text}'",
                    current_value=gks_text,
                    suggested_value=suggested,
                    auto_correctable=auto_correctable,
                    confidence=confidence,
                    context={
                        'class': row['cls'],
                        'expected_format': '3-4 Ziffern'
                    }
                ))
        
        return issues
    
    def check_fahrtrichtung_validity(self) -> List[ValidationIssue]:
        """Check Fahrtrichtung values"""
        issues = []
        signals = self.df[self.df['cls'] == 'signal']
        
        for _, row in signals.iterrows():
            fahrt = row.get('fahrtrichtung')
            
            if pd.notna(fahrt) and fahrt not in ['A', 'B', '', None]:
                # Try to fix
                fahrt_upper = str(fahrt).upper().strip()
                
                if fahrt_upper in ['A', 'B']:
                    suggested = fahrt_upper
                    auto_correctable = True
                    confidence = 0.9
                else:
                    suggested = None
                    auto_correctable = False
                    confidence = 0.0
                
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='error',
                    category='invalid_value',
                    field='fahrtrichtung',
                    message=f"Signal: Ungültige Fahrtrichtung '{fahrt}'",
                    current_value=str(fahrt),
                    suggested_value=suggested,
                    auto_correctable=auto_correctable,
                    confidence=confidence,
                    context={'allowed_values': ['A', 'B']}
                ))
        
        return issues
    
    def check_signal_duplicates(self) -> List[ValidationIssue]:
        """Check for duplicate signal names and validate consistency"""
        issues = []
        signals = self.df[self.df['cls'] == 'signal'].copy()
        
        if signals.empty:
            return issues
        
        grouped = signals.groupby('anchor_text')
        
        for signal_name, group in grouped:
            if pd.isna(signal_name) or not signal_name:
                continue
            
            instances = len(group)
            
            if instances > 1:
                row_ids = group['row_id'].tolist()
                
                # Check coordinate consistency
                coords = group['coord_text'].dropna()
                coords = coords[coords != '']
                unique_coords = coords.unique()
                
                if len(unique_coords) > 1:
                    issues.append(ValidationIssue(
                        row_id=row_ids[0],
                        severity='error',
                        category='inconsistency',
                        field='coord_text',
                        message=f"Signal '{signal_name}': Unterschiedliche Koordinaten",
                        current_value=None,
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'signal_name': signal_name,
                            'instances': instances,
                            'unique_coordinates': list(unique_coords),
                            'all_row_ids': row_ids
                        }
                    ))
                
                # Check Fahrtrichtung consistency
                fahrtrichtungen = group['fahrtrichtung'].dropna()
                fahrtrichtungen = fahrtrichtungen[fahrtrichtungen != '']
                unique_fahrtrichtungen = fahrtrichtungen.unique()
                
                if len(unique_fahrtrichtungen) > 1:
                    issues.append(ValidationIssue(
                        row_id=row_ids[0],
                        severity='error',
                        category='inconsistency',
                        field='fahrtrichtung',
                        message=f"Signal '{signal_name}': Unterschiedliche Fahrtrichtungen",
                        current_value=None,
                        suggested_value=None,
                        auto_correctable=False,
                        confidence=0.0,
                        context={
                            'signal_name': signal_name,
                            'instances': instances,
                            'unique_fahrtrichtungen': list(unique_fahrtrichtungen),
                            'all_row_ids': row_ids
                        }
                    ))
        
        return issues
    
    def check_confidence_thresholds(self, min_confidence: float = 0.3) -> List[ValidationIssue]:
        """Check if confidence values are above threshold"""
        issues = []
        
        if 'conf' not in self.df.columns:
            return issues
        
        low_conf = self.df[self.df['conf'] < min_confidence]
        
        for _, row in low_conf.iterrows():
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='warning',
                category='confidence',
                field='conf',
                message=f"{row['cls']}: Niedrige Konfidenz ({row['conf']:.2f})",
                current_value=row['conf'],
                suggested_value=None,
                auto_correctable=False,
                confidence=0.0,
                context={
                    'class': row['cls'],
                    'threshold': min_confidence
                }
            ))
        
        return issues
    
    def check_coordinate_values(self) -> List[ValidationIssue]:
        """Check coordinate values for plausibility"""
        issues = []
        coords = self.df[self.df['cls'] == 'coordinate']
        
        for _, row in coords.iterrows():
            coord_val = row.get('coord_value')
            
            if pd.isna(coord_val):
                continue
            
            # Check for unrealistic values
            if abs(coord_val) > 1000:
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='warning',
                    category='value_range',
                    field='coord_value',
                    message=f"Koordinate: Ungewöhnlich großer Wert ({coord_val:.4f})",
                    current_value=coord_val,
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=0.0,
                    context={'coord_text': row.get('coord_text', '')}
                ))
        
        return issues
    
    # ========================================================================
    # AUTO-CORRECTION
    # ========================================================================
    
    def _apply_auto_corrections(self) -> List[tuple]:
        """
        Apply all auto-correctable fixes
        
        Returns:
            List of (row_id, field, old_value, new_value) tuples
        """
        corrections_log = []
        
        for issue in self.issues:
            if issue.auto_correctable and issue.suggested_value is not None:
                mask = self.df['row_id'] == issue.row_id
                if mask.any():
                    old_value = self.df.loc[mask, issue.field].iloc[0]
                    self.df.loc[mask, issue.field] = issue.suggested_value
                    
                    # Log the correction
                    corrections_log.append((
                        issue.row_id,
                        issue.field,
                        old_value,
                        issue.suggested_value
                    ))
                    
                    issue.context['corrected'] = True
        
        return corrections_log

# ========================================================================
# LEGACY COMPATIBILITY (for old code)
# ========================================================================

class ValidationResult_Old:
    """Old-style validation result for backwards compatibility"""
    def __init__(self, severity: str, message: str, row_id: Optional[int] = None, 
                 details: Optional[dict] = None):
        self.severity = severity
        self.message = message
        self.row_id = row_id
        self.details = details or {}
    
    def __repr__(self):
        return f"[{self.severity}] {self.message} (row_id={self.row_id})"
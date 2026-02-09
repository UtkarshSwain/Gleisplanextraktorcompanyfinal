# Adaptive Learning Implementation Guide for Gleisplanextraktor v3

## Document Purpose

This document provides a complete reference for implementing adaptive learning features in Gleisplanextraktor v3. All adaptive learning is designed as a **FALLBACK mechanism** - the existing static rules work for most cases and must remain the primary behavior.

---

## PART 1: FALLBACK ARCHITECTURE PRINCIPLE

### Core Design Rule

```
┌─────────────────────────────────────────────────────────────────────┐
│                    DECISION FLOW FOR ALL FEATURES                    │
│                                                                     │
│   1. TRY STATIC RULES FIRST (always)                               │
│      ↓                                                              │
│   2. Did static rules produce a result?                            │
│      ├── YES → Use static result, DONE (no adaptive learning)      │
│      └── NO  → Continue to step 3                                  │
│      ↓                                                              │
│   3. FALLBACK: Try adaptive/learned rules                          │
│      ├── Has enough samples (MIN_SAMPLES)?                         │
│      │   ├── YES → Apply learned rule, mark as "fallback_used"     │
│      │   └── NO  → No result available                             │
│      ↓                                                              │
│   4. Return result (or None if nothing worked)                     │
└─────────────────────────────────────────────────────────────────────┘
```

### When Adaptive Learning Activates (FALLBACK ONLY)

| Feature | Static Rule | Fallback Condition |
|---------|-------------|-------------------|
| **Linking** | LINK_RULES spatial search | Static search finds NO match after all fallback_dy_steps |
| **OCR Correction** | Character whitelists + patterns | OCR confidence < 0.6 AND learned pattern has 5+ samples |
| **Threshold** | CLASS_THRESH values | After 10+ false positive/negative samples AND change ≤ 0.05 |
| **Uncertainty Review** | Detections pass CLASS_THRESH | Only for items with uncertainty_score > 0.3 |

### Safety Guards (Prevent Overriding Good Rules)

```python
# In all adaptive learning modules:
MIN_SAMPLES_BEFORE_ADJUSTMENT = 10    # Need substantial evidence
MAX_THRESHOLD_CHANGE = 0.05           # Small incremental changes only
HARD_MIN_THRESHOLD = 0.10             # Never go below 10%
HARD_MAX_THRESHOLD = 0.95             # Never go above 95%
AUTO_APPLY_CONFIDENCE = 0.95          # Only auto-apply if 95%+ confident
FALLBACK_REQUIRES_SAMPLES = 5         # Minimum samples for fallback rules
```

---

## PART 2: COMPLETE STATIC RULES REFERENCE

### 2.1 LINK_RULES (config.py:259-274)

These rules define spatial relationships for linking anchors to coordinates.

```python
LINK_RULES = {
    "signal": dict(mode="below"),
    "gm_block": dict(mode="below"),
    "gks_festkodiert": dict(mode="either"),
    "gks_gesteuert": dict(mode="either"),
    "weichen_block": dict(mode="inside", block=True),
    "isolierstoß": dict(mode="above", tilted_ok=True),
    "haltepunkt": dict(mode="either"),
    "sverbinder": dict(mode="above"),
    "weichenende": dict(
        mode="either",
        dx_multiplier=3.0,
        prefer_horizontal=True,
        fallback_dy_steps=[1.5, 2.0, 2.5]
    ),
    "prellbock": dict(
        mode="right_or_below",
        dx_multiplier=2.0,
        prefer_horizontal=True
    ),
    "haltetafel": dict(
        mode="either",
        dx_multiplier=2.0
    ),
    "weichengruppenende": dict(
        mode="either",
        dx_multiplier=3.0,
        prefer_horizontal=True,
        search_left=True,
        fallback_dy_steps=[1.5, 2.0, 2.5, 3.0]
    )
}
```

#### Parameter Reference Table

| Class | mode | dx_mult | dy_mult | Special Parameters |
|-------|------|---------|---------|-------------------|
| signal | below | 1.0 | 1.0 | - |
| gm_block | below | 1.0 | 1.0 | - |
| gks_festkodiert | either | 1.0 | 1.0 | - |
| gks_gesteuert | either | 1.0 | 1.0 | - |
| weichen_block | inside | 1.0 | 1.0 | block=True |
| isolierstoß | above | 1.0 | 1.0 | tilted_ok=True |
| haltepunkt | either | 1.0 | 1.0 | - |
| sverbinder | above | 1.0 | 1.0 | - |
| weichenende | either | 3.0 | 1.0 | prefer_horizontal, fallback_dy_steps=[1.5,2.0,2.5] |
| prellbock | right_or_below | 2.0 | 1.0 | prefer_horizontal |
| haltetafel | either | 2.0 | 1.0 | - |
| weichengruppenende | either | 3.0 | 1.0 | prefer_horizontal, search_left, fallback_dy_steps=[1.5,2.0,2.5,3.0] |

#### Parameter Definitions

| Parameter | Default | Description |
|-----------|---------|-------------|
| mode | "either" | Spatial constraint: "below", "above", "either", "inside", "right_or_below" |
| dx_multiplier | 1.0 | Horizontal distance tolerance multiplier |
| dy_multiplier | 1.0 | Vertical distance tolerance multiplier |
| tight / block | False | Use tighter horizontal tolerance (0.45 vs 0.6 factor) |
| tilted_ok | False | Allow tilted coordinates for direction checks |
| prefer_horizontal | False | Prioritize horizontal proximity in scoring |
| search_left | False | Allow coordinates to the left with 1.3x bonus |
| fallback_dy_steps | [] | Expand vertical search in steps if no match |

#### Distance Calculation Formulas

```python
dy_max_base = 1.6 * anchor["h"]
dy_max = dy_max_base * dy_multiplier

dx_max = dx_multiplier * 0.6 * max(anchor["w"], coord["w"])
# If tight/block: dx_max = dx_multiplier * 0.45 * max(anchor["w"], coord["w"])
dx_max = max(dx_max, 30)  # Minimum 30 pixels

# If search_left and coord is left of anchor:
dx_max *= 1.3  # 30% bonus
```

---

### 2.2 CLASS_THRESH (config.py:188-209)

Detection thresholds for accepting YOLO predictions as "confirmed".

```python
CLASS_THRESH = {
    "gm_block": 0.22,           # Very confident (mAP50: 0.995)
    "sverbinder": 0.50,         # Very confident (mAP50: 0.988)
    "prellbock": 0.30,          # Very confident (mAP50: 0.995)
    "weichengruppenende": 0.7,  # Good performer (mAP50: 0.995)
    "signal": 0.40,             # Good (mAP50: 0.989)
    "isolierstoß": 0.09,        # Good (mAP50: 0.994) - Lowest threshold!
    "haltetafel": 0.55,         # Moderate (mAP50: 0.966)
    "haltepunkt": 0.32,         # Good (mAP50: 0.995)
    "gks_festkodiert": 0.85,    # Highest threshold! (mAP50: 0.985)
    "coordinate": 0.10,         # Very low (35 background FPs)
    "weichen_block": 0.42,      # Moderate (14 background FPs)
    "gks_gesteuert": 0.5,       # Moderate (mAP50: 0.973)
    "weichenende": 0.7,         # Same as weichengruppenende
}
```

#### Threshold Summary (Sorted)

| Class | Threshold | Model Performance |
|-------|-----------|-------------------|
| isolierstoß | 0.09 | mAP50: 0.994 |
| coordinate | 0.10 | mAP50: 0.993 |
| gm_block | 0.22 | mAP50: 0.995 |
| prellbock | 0.30 | mAP50: 0.995 |
| haltepunkt | 0.32 | mAP50: 0.995 |
| signal | 0.40 | mAP50: 0.989 |
| weichen_block | 0.42 | mAP50: 0.979 |
| gks_gesteuert | 0.50 | mAP50: 0.973 |
| sverbinder | 0.50 | mAP50: 0.988 |
| haltetafel | 0.55 | mAP50: 0.966 |
| weichenende | 0.70 | mAP50: 0.995 |
| weichengruppenende | 0.70 | mAP50: 0.995 |
| gks_festkodiert | 0.85 | mAP50: 0.985 |

---

### 2.3 Uncertain Detection Thresholds (config.py:217-224)

```python
UNCERTAIN_THRESH_MULTIPLIER = 0.5  # 50% of CLASS_THRESH

MIN_UNCERTAIN_THRESH = {
    "coordinate": 0.01,    # Very low - catch almost all
    "isolierstoß": 0.01,   # Very low - catch almost all
}
MIN_UNCERTAIN_THRESH_DEFAULT = 0.10
```

#### Detection Status Classification

```python
# For each class:
uncertain_thresh = max(CLASS_THRESH * 0.5, MIN_UNCERTAIN_THRESH.get(cls, 0.10))

if conf >= CLASS_THRESH:
    status = 'confirmed'
elif conf >= uncertain_thresh:
    status = 'uncertain'  # Flagged for review
else:
    status = 'discarded'  # Too low, not shown
```

---

### 2.4 NMS_THRESHOLDS (config.py:230-238)

Non-Maximum Suppression thresholds for merging overlapping boxes.

```python
NMS_THRESHOLDS = {
    "coordinate": 0.25,       # Very strict - many false positives
    "weichen_block": 0.30,    # Stricter
    "signal": 0.32,           # Stricter
    "haltetafel": 0.35,       # Stricter
    "gks_gesteuert": 0.30,    # Very strict
    "gks_festkodiert": 0.30,  # Very strict
    "default": 0.40,          # Fallback for unlisted classes
}
```

---

### 2.5 CONFIDENCE_THRESHOLDS for Validation (validation_config.py:53-67)

These are HIGHER than CLASS_THRESH - used for quality assessment, not detection.

```python
CONFIDENCE_THRESHOLDS = {
    "signal": 0.80,
    "gm_block": 0.80,
    "gks_festkodiert": 0.70,
    "gks_gesteuert": 0.70,
    "weichen_block": 0.90,
    "isolierstoß": 0.70,
    "haltepunkt": 0.80,
    "sverbinder": 0.80,
    "coordinate": 0.65,
    "weichenende": 0.80,
    "prellbock": 0.80,
    "haltetafel": 0.70,
    "weichengruppenende": 0.80,
}
DEFAULT_CONFIDENCE_THRESHOLD = 0.60
```

---

### 2.6 RISK_WEIGHTS (validation_config.py:78-88)

```python
RISK_WEIGHTS = {
    'low_confidence': 0.40,            # Highest weight
    'missing_coordinate': 0.30,
    'haltepunkt_signal_mismatch': 0.25,
    'invalid_coordinate': 0.20,
    'gks_letters': 0.15,
    'missing_text': 0.15,
    'duplicate_nearby': 0.15,
    'size_anomaly': 0.10,
    'formatting_error': 0.05,          # Lowest weight
}

RISK_THRESHOLDS = {
    'high': 0.20,    # > 20% = Red / "Sofort prüfen"
    'medium': 0.10,  # 10-20% = Yellow / "Bald prüfen"
    # < 10% = Green / "Gut erkannt"
}
```

---

### 2.7 Text Validation Patterns (config.py)

```python
# Signal ID pattern
CLASS_ID_PATTERNS = {
    "signal": r"^[A-ZÄÖÜ]{1,4}\d{1,4}$",      # A12, SIG1, ÜB99
    "gks_gesteuert": r"^\d{3,4}$",             # 123, 1234
    "gks_festkodiert": r"^\d{3,4}$",           # 123, 1234
}

# Coordinate pattern (line 180)
COORD_RE = re.compile(
    r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$'
)
# Group 1: Numeric value (e.g., "1,234")
# Group 2: Optional track identifier (e.g., "A", "B1")

# Classes that allow purely numeric OCR results
NUMERIC_OK = {"gks_gesteuert", "gks_festkodiert", "weichen_block", "prellbock"}
```

---

### 2.8 OCR Character Whitelists (ocr_engine.py)

| Class Type | Whitelist Characters |
|------------|---------------------|
| Signals | `ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789 ` |
| Coordinates/Special | `ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÜ0123456789./-_` |
| GKS (numeric only) | `0123456789` |

---

### 2.9 OCR Confidence Thresholds (config.py:342-355)

```python
PADDLEOCR_PARAMS = {
    "confidence_threshold": {
        "signal": 0.50,           # More lenient
        "gks_gesteuert": 0.40,    # More lenient
        "gks_festkodiert": 0.40,  # More lenient
        "coordinate": 0.65,       # Stricter (many false positives)
        "default": 0.45,          # Default leniency
    },
}
```

---

## PART 3: DATABASE TABLES FOR ADAPTIVE LEARNING

### 3.1 Existing Tables (Already Present)

| Table | Purpose |
|-------|---------|
| `track_layouts` | Layout registry |
| `workspaces` | Saved detection data + learned_patterns_json, uncertain_detections_json |
| `manual_corrections` | User correction log |
| `validation_log` | Validation errors |
| `quality_metrics` | Quality scores |
| `custom_symbols` | Template definitions |

### 3.2 New Tables to Add

```sql
-- ============================================================
-- OCR PATTERN LEARNING
-- ============================================================

CREATE TABLE ocr_confusion_matrix (
    id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL,
    original_char TEXT NOT NULL,
    corrected_char TEXT NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    UNIQUE(class_name, original_char, corrected_char)
);

CREATE TABLE ocr_pattern_corrections (
    id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL,
    original_pattern TEXT NOT NULL,
    corrected_pattern TEXT NOT NULL,
    occurrence_count INTEGER DEFAULT 1,
    confidence REAL DEFAULT 0.5
);

-- ============================================================
-- THRESHOLD CALIBRATION
-- ============================================================

CREATE TABLE learned_thresholds (
    id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL UNIQUE,
    original_threshold REAL,
    learned_threshold REAL,
    false_positive_count INTEGER DEFAULT 0,
    false_negative_count INTEGER DEFAULT 0,
    sample_count INTEGER DEFAULT 0,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE threshold_feedback (
    id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL,
    feedback_type TEXT CHECK (feedback_type IN ('false_positive', 'false_negative', 'confirmed')),
    original_confidence REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- ACTIVE LEARNING / UNCERTAINTY
-- ============================================================

CREATE TABLE uncertainty_feedback (
    id INTEGER PRIMARY KEY,
    layout_id INTEGER NOT NULL,
    row_id INTEGER NOT NULL,
    class_name TEXT NOT NULL,
    original_confidence REAL,
    uncertainty_score REAL,
    user_action TEXT CHECK (user_action IN ('confirm', 'reject', 'correct')),
    corrected_value TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE class_error_rates (
    id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL UNIQUE,
    conf_band TEXT NOT NULL,
    confirmed_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    error_rate REAL,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- LINKING RULE LEARNING
-- ============================================================

CREATE TABLE manual_link_log (
    id INTEGER PRIMARY KEY,
    anchor_class TEXT NOT NULL,
    anchor_angle REAL,
    normalized_dx REAL,
    normalized_dy REAL,
    link_distance REAL,
    direction TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE learned_link_rules (
    id INTEGER PRIMARY KEY,
    class_name TEXT NOT NULL UNIQUE,
    learned_mode TEXT,
    learned_dx_multiplier REAL,
    learned_dy_multiplier REAL,
    mean_normalized_dx REAL,
    mean_normalized_dy REAL,
    std_normalized_dx REAL,
    std_normalized_dy REAL,
    sample_count INTEGER,
    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================

CREATE INDEX idx_ocr_confusion_class ON ocr_confusion_matrix(class_name);
CREATE INDEX idx_threshold_feedback_class ON threshold_feedback(class_name);
CREATE INDEX idx_uncertainty_feedback_layout ON uncertainty_feedback(layout_id);
CREATE INDEX idx_manual_link_log_class ON manual_link_log(anchor_class);
```

---

## PART 4: NEW FILES TO CREATE

### 4.1 core/ocr_pattern_learner.py

```python
"""
OCR Pattern Learning Module

Learns common OCR mistakes from user corrections and applies them as FALLBACK
when OCR confidence is low.

IMPORTANT: This is a FALLBACK mechanism. Static OCR rules (whitelists, patterns)
are always applied first. Learned patterns only apply when OCR confidence < 0.6.
"""

from typing import Dict, Tuple, List, Optional
from database_sqlite import db_cursor

class OCRPatternLearner:
    MIN_SAMPLES = 5  # Minimum corrections before auto-applying
    LOW_CONFIDENCE_THRESHOLD = 0.6  # Only apply learned patterns below this

    def record_correction(
        self,
        cls: str,
        old_text: str,
        new_text: str,
        confidence: float
    ) -> None:
        """
        Record a text correction to build confusion matrix.
        Called from workspace_widget.py when user edits text.
        """
        # Calculate character-level edits using Levenshtein
        edits = self._get_edit_operations(old_text, new_text)

        for op_type, old_char, new_char, position in edits:
            if op_type == 'replace':
                self._update_confusion_matrix(cls, old_char, new_char)

    def suggest_correction(
        self,
        cls: str,
        text: str,
        confidence: float
    ) -> Optional[str]:
        """
        Suggest correction based on learned patterns.

        FALLBACK ONLY: Returns None if confidence >= LOW_CONFIDENCE_THRESHOLD.
        """
        if confidence >= self.LOW_CONFIDENCE_THRESHOLD:
            return None  # Trust high-confidence OCR

        confusion = self._get_confusion_matrix(cls)
        if not confusion:
            return None

        result = text
        changes_made = False

        for i, char in enumerate(text):
            if char in confusion:
                corrections = confusion[char]
                best = max(corrections, key=corrections.get)
                count = corrections[best]

                if count >= self.MIN_SAMPLES:
                    result = result[:i] + best + result[i+1:]
                    changes_made = True

        return result if changes_made else None

    def _get_confusion_matrix(self, cls: str) -> Dict[str, Dict[str, int]]:
        """Load confusion matrix from database."""
        sql = """
        SELECT original_char, corrected_char, occurrence_count
        FROM ocr_confusion_matrix
        WHERE class_name = ?
        """
        with db_cursor() as cursor:
            cursor.execute(sql, (cls,))
            rows = cursor.fetchall()

        matrix = {}
        for row in rows:
            orig = row['original_char']
            corr = row['corrected_char']
            count = row['occurrence_count']

            if orig not in matrix:
                matrix[orig] = {}
            matrix[orig][corr] = count

        return matrix

    def _update_confusion_matrix(self, cls: str, old_char: str, new_char: str) -> None:
        """Update confusion matrix in database."""
        sql = """
        INSERT INTO ocr_confusion_matrix (class_name, original_char, corrected_char, occurrence_count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(class_name, original_char, corrected_char)
        DO UPDATE SET occurrence_count = occurrence_count + 1
        """
        with db_cursor(commit=True) as cursor:
            cursor.execute(sql, (cls, old_char, new_char))

    def _get_edit_operations(self, old: str, new: str) -> List[Tuple]:
        """Calculate character-level edit operations using Levenshtein."""
        # Implementation using dynamic programming
        # Returns list of (op_type, old_char, new_char, position)
        # op_type: 'replace', 'insert', 'delete'
        pass  # TODO: Implement Levenshtein with backtracking


# Singleton instance
ocr_pattern_learner = OCRPatternLearner()
```

### 4.2 core/link_learner.py

```python
"""
Linking Rule Learning Module

Learns spatial relationships from manual coordinate linkings and uses them
as FALLBACK when static LINK_RULES don't find a match.

IMPORTANT: This is a FALLBACK mechanism. Static LINK_RULES are always tried first.
Learned rules only apply when static rules find NO match.
"""

from typing import Dict, Optional
from math import sqrt
from statistics import mean, stdev
from database_sqlite import db_cursor

class LinkRuleLearner:
    MIN_SAMPLES = 5  # Minimum manual links before applying learned rules

    def record_manual_link(
        self,
        anchor_class: str,
        anchor_cx: float,
        anchor_cy: float,
        anchor_w: float,
        anchor_h: float,
        anchor_angle: float,
        coord_cx: float,
        coord_cy: float
    ) -> None:
        """
        Record a manual link to learn spatial patterns.
        Called from workspace_widget.py when user manually links anchor to coordinate.
        """
        # Calculate relative position
        dx = coord_cx - anchor_cx
        dy = coord_cy - anchor_cy

        # Normalize by anchor size
        normalized_dx = dx / anchor_w if anchor_w > 0 else 0
        normalized_dy = dy / anchor_h if anchor_h > 0 else 0

        # Euclidean distance
        distance = sqrt(dx**2 + dy**2)

        # Determine direction
        if abs(dx) > abs(dy):
            direction = "right" if dx > 0 else "left"
        else:
            direction = "below" if dy > 0 else "above"

        # Store in database
        self._log_manual_link(
            anchor_class, anchor_angle,
            normalized_dx, normalized_dy,
            distance, direction
        )

        # Recompute learned rules for this class
        self._recompute_learned_rules(anchor_class)

    def get_learned_rules(self, cls: str) -> Optional[Dict]:
        """
        Get learned linking rules for a class.
        Returns None if not enough samples or static rules should be used.
        """
        sql = """
        SELECT * FROM learned_link_rules WHERE class_name = ?
        """
        with db_cursor() as cursor:
            cursor.execute(sql, (cls,))
            row = cursor.fetchone()

        if row and row['sample_count'] >= self.MIN_SAMPLES:
            return {
                'learned_mode': row['learned_mode'],
                'learned_dx_multiplier': row['learned_dx_multiplier'],
                'learned_dy_multiplier': row['learned_dy_multiplier'],
                'mean_normalized_dx': row['mean_normalized_dx'],
                'mean_normalized_dy': row['mean_normalized_dy'],
                'std_normalized_dx': row['std_normalized_dx'],
                'std_normalized_dy': row['std_normalized_dy'],
                'sample_count': row['sample_count'],
            }
        return None

    def _log_manual_link(self, cls, angle, norm_dx, norm_dy, dist, direction):
        """Store manual link in database."""
        sql = """
        INSERT INTO manual_link_log
            (anchor_class, anchor_angle, normalized_dx, normalized_dy, link_distance, direction)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        with db_cursor(commit=True) as cursor:
            cursor.execute(sql, (cls, angle, norm_dx, norm_dy, dist, direction))

    def _recompute_learned_rules(self, cls: str) -> None:
        """Recompute learned rules from all manual links for a class."""
        sql = """
        SELECT normalized_dx, normalized_dy, direction
        FROM manual_link_log
        WHERE anchor_class = ?
        """
        with db_cursor() as cursor:
            cursor.execute(sql, (cls,))
            rows = cursor.fetchall()

        if len(rows) < self.MIN_SAMPLES:
            return  # Not enough data

        # Calculate statistics
        dx_values = [r['normalized_dx'] for r in rows]
        dy_values = [r['normalized_dy'] for r in rows]
        directions = [r['direction'] for r in rows]

        mean_dx = mean(dx_values)
        mean_dy = mean(dy_values)
        std_dx = stdev(dx_values) if len(dx_values) > 1 else 0
        std_dy = stdev(dy_values) if len(dy_values) > 1 else 0

        # Determine dominant direction
        from collections import Counter
        direction_counts = Counter(directions)
        dominant_mode = direction_counts.most_common(1)[0][0]

        # Calculate multipliers (relative to default 1.0)
        dx_mult = abs(mean_dx) if abs(mean_dx) > 0.5 else 1.0
        dy_mult = abs(mean_dy) if abs(mean_dy) > 0.5 else 1.0

        # Upsert learned rules
        sql = """
        INSERT INTO learned_link_rules
            (class_name, learned_mode, learned_dx_multiplier, learned_dy_multiplier,
             mean_normalized_dx, mean_normalized_dy, std_normalized_dx, std_normalized_dy,
             sample_count, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(class_name) DO UPDATE SET
            learned_mode = excluded.learned_mode,
            learned_dx_multiplier = excluded.learned_dx_multiplier,
            learned_dy_multiplier = excluded.learned_dy_multiplier,
            mean_normalized_dx = excluded.mean_normalized_dx,
            mean_normalized_dy = excluded.mean_normalized_dy,
            std_normalized_dx = excluded.std_normalized_dx,
            std_normalized_dy = excluded.std_normalized_dy,
            sample_count = excluded.sample_count,
            last_updated = CURRENT_TIMESTAMP
        """
        with db_cursor(commit=True) as cursor:
            cursor.execute(sql, (
                cls, dominant_mode, dx_mult, dy_mult,
                mean_dx, mean_dy, std_dx, std_dy, len(rows)
            ))


# Singleton instance
link_learner = LinkRuleLearner()
```

### 4.3 core/active_learner.py

```python
"""
Active Learning Module

Computes uncertainty scores and manages review queue for uncertain detections.
Learns from user feedback to improve threshold calibration.
"""

from typing import List, Dict, Optional, Tuple
from config import CLASS_THRESH
from database_sqlite import db_cursor

class ActiveLearner:
    MIN_SAMPLES_FOR_CALIBRATION = 20
    UNCERTAINTY_THRESHOLD = 0.3  # Only include items above this in review queue

    def compute_uncertainty_score(self, detection: Dict) -> float:
        """
        Compute uncertainty score for a detection.
        Higher score = more uncertain = higher priority for review.
        """
        cls = detection.get('cls', 'unknown')
        conf = detection.get('conf', 0.5)
        thresh = CLASS_THRESH.get(cls, 0.5)

        # Distance from threshold (0 = at threshold = maximum uncertainty)
        distance = abs(conf - thresh)

        # Normalize by threshold
        uncertainty = 1.0 - (distance / max(thresh, 0.1))
        uncertainty = max(0.0, min(1.0, uncertainty))

        # Bonus factors for higher uncertainty
        if not detection.get('anchor_text'):
            uncertainty += 0.1  # Missing text
        if not detection.get('coord_text') and cls != 'coordinate':
            uncertainty += 0.1  # Missing coordinate link

        return min(1.0, uncertainty)

    def get_review_queue(self, detections: List[Dict]) -> List[Dict]:
        """
        Generate prioritized review queue from detections.
        Only includes items with uncertainty > UNCERTAINTY_THRESHOLD.
        """
        queue = []

        for det in detections:
            score = self.compute_uncertainty_score(det)
            if score > self.UNCERTAINTY_THRESHOLD:
                queue.append({
                    'row_id': det.get('row_id'),
                    'cls': det.get('cls'),
                    'conf': det.get('conf', 0),
                    'uncertainty': score,
                    'anchor_text': det.get('anchor_text', ''),
                    'coord_text': det.get('coord_text', ''),
                })

        # Sort by uncertainty (highest first)
        queue.sort(key=lambda x: -x['uncertainty'])

        return queue

    def process_feedback(
        self,
        layout_id: int,
        row_id: int,
        cls: str,
        confidence: float,
        uncertainty: float,
        action: str,  # 'confirm', 'reject', 'correct'
        corrected_value: Optional[str] = None
    ) -> None:
        """
        Process user feedback on an uncertain detection.
        Updates database and may trigger threshold recalibration.
        """
        sql = """
        INSERT INTO uncertainty_feedback
            (layout_id, row_id, class_name, original_confidence,
             uncertainty_score, user_action, corrected_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with db_cursor(commit=True) as cursor:
            cursor.execute(sql, (
                layout_id, row_id, cls, confidence,
                uncertainty, action, corrected_value
            ))

        # Update error rates
        self._update_error_rate(cls, confidence, action)

    def _update_error_rate(self, cls: str, confidence: float, action: str) -> None:
        """Update class error rates for threshold calibration."""
        # Determine confidence band
        if confidence < 0.25:
            band = '0.0-0.25'
        elif confidence < 0.50:
            band = '0.25-0.50'
        elif confidence < 0.75:
            band = '0.50-0.75'
        else:
            band = '0.75-1.00'

        # Update counts
        if action == 'confirm':
            sql = """
            INSERT INTO class_error_rates (class_name, conf_band, confirmed_count, rejected_count, error_rate)
            VALUES (?, ?, 1, 0, 0.0)
            ON CONFLICT(class_name) DO UPDATE SET
                confirmed_count = confirmed_count + 1,
                error_rate = CAST(rejected_count AS REAL) / (confirmed_count + rejected_count + 1),
                last_updated = CURRENT_TIMESTAMP
            """
        elif action == 'reject':
            sql = """
            INSERT INTO class_error_rates (class_name, conf_band, confirmed_count, rejected_count, error_rate)
            VALUES (?, ?, 0, 1, 1.0)
            ON CONFLICT(class_name) DO UPDATE SET
                rejected_count = rejected_count + 1,
                error_rate = CAST(rejected_count + 1 AS REAL) / (confirmed_count + rejected_count + 1),
                last_updated = CURRENT_TIMESTAMP
            """
        else:
            return

        with db_cursor(commit=True) as cursor:
            cursor.execute(sql, (cls, band))


# Singleton instance
active_learner = ActiveLearner()
```

---

## PART 5: INTEGRATION POINTS

### 5.1 workspace_widget.py - OCR Pattern Learning

**Location:** `on_tree_item_changed()` at line ~2471

**Current code:**
```python
idx_list = self.df_all.index[self.df_all['row_id'] == row_id].tolist()
if idx_list:
    idx = idx_list[0]
    if col_to_update == 'anchor_text':
        old_anchor_text = self.df_all.loc[idx, 'anchor_text']
    self.df_all.loc[idx, col_to_update] = new_text
```

**Add after:**
```python
    # === ADAPTIVE LEARNING: Record OCR correction ===
    if col_to_update in ['anchor_text', 'coord_text']:
        old_value = old_anchor_text if col_to_update == 'anchor_text' else self.df_all.loc[idx, 'coord_text']
        if old_value and old_value != new_text:  # Actual correction
            from core.ocr_pattern_learner import ocr_pattern_learner
            ocr_pattern_learner.record_correction(
                cls=cls,
                old_text=str(old_value),
                new_text=str(new_text),
                confidence=self.df_all.loc[idx].get('conf', 0.5)
            )
```

### 5.2 workspace_widget.py - Link Learning

**Location:** `_link_anchor_to_coordinate()` at line ~4547

**Current code:**
```python
print(f"Linked anchor row_id={anchor_row_id} to coordinate row_id={coord_row_id}")
```

**Add after:**
```python
# === ADAPTIVE LEARNING: Record manual link ===
from core.link_learner import link_learner
link_learner.record_manual_link(
    anchor_class=anchor_class,
    anchor_cx=anchor_row.get('cx', (anchor_row['ax1'] + anchor_row['ax2']) / 2),
    anchor_cy=anchor_row.get('cy', (anchor_row['ay1'] + anchor_row['ay2']) / 2),
    anchor_w=anchor_row.get('w', anchor_row['ax2'] - anchor_row['ax1']),
    anchor_h=anchor_row.get('h', anchor_row['ay2'] - anchor_row['ay1']),
    anchor_angle=anchor_row.get('angle', 0),
    coord_cx=coord_row.get('cx', (coord_row['cx1'] + coord_row['cx2']) / 2),
    coord_cy=coord_row.get('cy', (coord_row['cy1'] + coord_row['cy2']) / 2)
)
```

### 5.3 core/linking.py - Apply Learned Rules as Fallback

**Location:** `link_anchor_to_coord()` at end of function (before return None)

**Add:**
```python
# === FALLBACK: Try learned rules if static rules found nothing ===
if best is None:
    from core.link_learner import link_learner
    learned = link_learner.get_learned_rules(anchor["name"])

    if learned and learned['sample_count'] >= 5:
        # Use learned rules with expanded search
        fallback_rule = {
            "mode": learned["learned_mode"],
            "dx_multiplier": learned["learned_dx_multiplier"],
            "dy_multiplier": learned["learned_dy_multiplier"],
        }
        # Re-run search with learned parameters
        best = _find_best_link_with_rule(anchor, coords, fallback_rule)
        if best:
            best["used_fallback"] = True  # Mark as fallback
```

### 5.4 core/ocr_engine.py - Apply Learned OCR Patterns as Fallback

**Location:** After PaddleOCR recognition, before returning text

**Add:**
```python
# === FALLBACK: Apply learned OCR patterns if confidence is low ===
if ocr_confidence < 0.6:
    from core.ocr_pattern_learner import ocr_pattern_learner
    corrected = ocr_pattern_learner.suggest_correction(
        cls=cls_name,
        text=raw_text,
        confidence=ocr_confidence
    )
    if corrected and corrected != raw_text:
        return corrected, ocr_confidence  # Applied learned pattern
```

---

## PART 6: VERIFICATION CHECKLIST

### Before Implementation

- [ ] Backup database before adding new tables
- [ ] Review all CLASS_THRESH values are correct
- [ ] Review all LINK_RULES parameters are documented

### After Implementation

- [ ] Verify static rules still work (no regression)
- [ ] Test linking with existing LINK_RULES
- [ ] Test OCR with existing whitelists
- [ ] Verify fallback only activates when static rules fail
- [ ] Check MIN_SAMPLES thresholds are respected
- [ ] Verify safety guards prevent excessive changes

### Testing Scenarios

1. **Linking Test:** Process layout where static rules work → verify no fallback used
2. **Linking Fallback Test:** Create scenario where static rules fail → verify learned rules activate
3. **OCR Test:** High-confidence OCR → verify no learned patterns applied
4. **OCR Fallback Test:** Low-confidence OCR → verify learned patterns apply
5. **Threshold Test:** Verify thresholds only change after 10+ samples

---

## PART 7: SUMMARY

This implementation guide provides:

1. **Clear Fallback Architecture:** Adaptive learning only activates when static rules fail
2. **Complete Static Rules Reference:** All parameters for LINK_RULES, CLASS_THRESH, NMS, validation
3. **Database Schema:** All new tables with indexes
4. **Module Code:** Ready-to-implement Python modules
5. **Integration Points:** Exact locations in existing code to add hooks
6. **Safety Guards:** Minimum samples, maximum changes, hard bounds
7. **Verification Checklist:** Testing scenarios to ensure correct behavior

The key principle remains: **Your existing static rules work for most cases. Adaptive learning is purely supplementary and only activates as a fallback.**

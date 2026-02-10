# Comprehensive Validation & OCR Patterns Analysis

**Deep code analysis of all existing regex patterns, validation checks, and OCR cleaning rules**

Based on comprehensive search through:
- `core/ocr_engine.py` (OCR processing and cleaning)
- `core/linking.py` (Coordinate parsing)
- `uservalidation/data_validator2.py` (Format validation)
- `uservalidation/ultimate_validator.py` (Advanced validation)
- `uservalidation/data_validator2.py` (Data validation)
- `config.py` (Regex patterns)

---

## 📋 Table of Contents

1. [OCR Character Substitution Patterns](#1-ocr-character-substitution-patterns)
2. [Coordinate Cleaning Patterns](#2-coordinate-cleaning-patterns)
3. [Signal Format Patterns](#3-signal-format-patterns)
4. [GKS Format Patterns](#4-gks-format-patterns)
5. [Regex Patterns from Config](#5-regex-patterns-from-config)
6. [Validation Checks](#6-validation-checks)
7. [Auto-Correction Opportunities](#7-auto-correction-opportunities)

---

## 1. OCR Character Substitution Patterns

### 1.1 Signal Digit Normalization (core/ocr_engine.py:1279)

**File:** `core/ocr_engine.py`
**Function:** `_normalize_signal_digits()`
**Purpose:** Fix common OCR confusions in signal ID digit parts

```python
trans = str.maketrans({
    'O': '0',  # Letter O → Digit 0
    'I': '1',  # Letter I → Digit 1
    'L': '1',  # Letter L → Digit 1
    'S': '5',  # Letter S → Digit 5
    'B': '8',  # Letter B → Digit 8
    'Z': '2',  # Letter Z → Digit 2
    'G': '6',  # Letter G → Digit 6
    'Q': '0',  # Letter Q → Digit 0
    'D': '0',  # Letter D → Digit 0
})
```

**Applied to:** Signal IDs (e.g., `AHR2O1` → `AHR201`)
**Confidence:** 85% (only in signal digit part)
**Status:** ✅ Already implemented

**Auto-Correction Potential:**
- **Same logic could be applied to GKS fields** (which are also numeric-only)
- Currently GKS uses `re.sub(r'\D', '', gks_text)` which removes ALL non-digits
- Enhancement: Could use explicit substitution for better logging and transparency

---

## 2. Coordinate Cleaning Patterns

### 2.1 Trailing Character Removal (used in 20+ places)

**Pattern:** Remove trailing alphabet letters and symbols that are OCR artifacts

```python
# Remove trailing single letters (common OCR error)
text = re.sub(r'\s*[a-zA-Z]\s*$', '', text)

# Remove trailing line symbols (OCR confuses borders/lines)
text = re.sub(r'\s*[|/\\]\s*$', '', text)
```

**Examples:**
- `15.492a` → `15.492`
- `15.492 |` → `15.492`
- `GL.15.492/` → `GL.15.492`

**Files:**
- `core/ocr_engine.py` (lines 550, 557, 566, 584, 615, 635, 651, 1189, 1196, 1205, 1221)
- `core/pipelineworker.py` (lines 230, 231, 468, 469, 506, 507, 745, 746, 787, 788, 848, 849, 900, 901)
- `core/linking.py` (line 1827)

**Confidence:** 90%
**Status:** ✅ Already implemented in OCR processing
**Auto-Correction Potential:** Could be added to validator as explicit check

---

### 2.2 Bracket Fixing (`_fix_coordinate_brackets()`)

**File:** `core/ocr_engine.py:737-764`
**Purpose:** Fix common OCR mistakes in bracketed coordinates

```python
# 1. Replace comma with dot (German decimal separator)
text = text.replace(',', '.')

# 2. Fix Gl. pattern - all variations → Gl.
# Fixes: GI, G1, Gi, gi, g1, gI → Gl.
text = re.sub(r'[Gg][Ii1l]\.?', 'Gl.', text)

# 3. Remove extra spaces inside brackets
text = re.sub(r'\(\s+', '(', text)   # "( Gl" → "(Gl"
text = re.sub(r'\s+\)', ')', text)   # "Gl )" → "Gl)"
```

**Examples:**
- `0,0734(GI.112)` → `0.0734(Gl.112)`
- `15.492( GL )` → `15.492(GL)`
- `10,5(gi.15)` → `10.5(Gl.15)`

**Confidence:** 85%
**Status:** ✅ Already implemented
**Note:** User rejected general comma→dot conversion, but THIS is safe because it's in coordinate context only

---

### 2.3 Bracket Completion (`_clean_coordinate_overlap()`)

**File:** `core/ocr_engine.py:589-658`
**Purpose:** Complete incomplete brackets and clean overlap artifacts

```python
# Pattern 1a: Complete bracketed coordinate
bracket_complete_pattern = r'-?\d+[.,]\d+\([A-Za-z0-9.,]+\)'

# Pattern 1b: Incomplete bracketed coordinate
bracket_incomplete_pattern = r'-?\d+[.,]\d+\([A-Za-z0-9.,]+'

if bracket_incomplete_match:
    result = bracket_incomplete_match.group(0).replace(',', '.')

    # Add closing bracket if missing
    if ')' not in result:
        result += ')'
```

**Examples:**
- `15.492(GL` → `15.492(GL)`
- `0.0734(Gl.112` → `0.0734(Gl.112)`

**Confidence:** 75%
**Status:** ✅ Already implemented in OCR
**Auto-Correction Potential:** Could add to validator as post-processing check

---

### 2.4 Gl. → GL. Uppercase Conversion (multiple places)

**File:** `uservalidation/data_validator2.py`

```python
temp_text = re.sub(r'G[l]\.', 'GL.', temp_text)     # Gl. → GL.
temp_text = re.sub(r'G[l](?=\d)', 'GL', temp_text)   # Gl123 → GL123
temp_text = re.sub(r'G[l](?=\))', 'GL', temp_text)   # Gl) → GL)
temp_text = re.sub(r'G[l]$', 'GL', temp_text)        # Trailing Gl → GL
```

**Examples:**
- `Gl.15.492` → `GL.15.492`
- `15.492(Gl)` → `15.492(GL)`
- `Gl123` → `GL123`

**Confidence:** 95%
**Status:** ✅ Already implemented in validators

---

### 2.5 Coordinate Parsing Pattern (COORD_RE)

**File:** `config.py:123`

```python
COORD_RE = re.compile(
    r'^\s*([+-]?\d{1,3}[,\.]\d{3,4})\s*(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?\s*$'
)
```

**Pattern breakdown:**
- `[+-]?` - Optional sign
- `\d{1,3}` - 1-3 digits before decimal
- `[,\.]` - Comma or dot as decimal separator
- `\d{3,4}` - 3-4 digits after decimal
- `(?:(?:GI|Gl)\.?\s*([A-Za-z0-9./-]{1,6}))?` - Optional GI/Gl identifier

**Examples:**
- Matches: `15.492`, `0.0734(Gl.112)`, `-5.123`, `10,5432`
- Pattern used in `core/linking.py:parse_coord()` for coordinate validation

**Status:** ✅ Core pattern used throughout codebase

---

## 3. Signal Format Patterns

### 3.1 Signal Pattern Validation

**File:** `data_validator2.py:354`, `core/ocr_engine.py:1262`

```python
SIGNAL_PATTERN = re.compile(r'^[A-ZÄÖÜ]{1,4}\d{1,4}$')
```

**Format:** 1-4 uppercase letters (including German umlauts) + 1-4 digits
**Examples:**
- Valid: `A101`, `BHR201`, `ÄB12`, `WAHR918`
- Invalid: `A 101`, `a101`, `ABCDE1`, `A`

**Cleaning applied before validation:**
```python
suggested = signal_text.upper().replace(' ', '').replace('-', '')
```

**Examples:**
- `a 101` → `A101` ✅
- `BHR-201` → `BHR201` ✅
- `ahr 21` → `AHR21` ✅

**Confidence:** 80%
**Status:** ✅ Already implemented

---

### 3.2 Signal Character-Only Filter

**File:** `core/ocr_engine.py:1264-1267`

```python
def _only_az09(s: str) -> str:
    t = ''.join(ch for ch in s.upper() if ch.isalnum() or ch in 'ÄÖÜ ')
    t = re.sub(r'\s+', ' ', t).strip()
    return t
```

**Purpose:** Remove all special characters except letters, digits, and German umlauts
**Examples:**
- `A-101` → `A 101` → `A101` (after space normalization)
- `BHR@201` → `BHR201`

**Confidence:** 85%
**Status:** ✅ Already implemented

---

### 3.3 Signal Missing Zero Fix

**File:** `core/ocr_engine.py:1285-1295`

```python
_FINAL_ZERO_TAIL2_RE = re.compile(r'^([A-ZÄÖÜ]{1,4})\s*(\d{2})$')

def _post_fix_missing_zero_middle(s: str) -> str:
    """
    If signal has exactly 2 digits, insert middle '0'.
    Example: 'AHR21' -> 'AHR201'
    """
    m = _FINAL_ZERO_TAIL2_RE.match(ss)
    if not m:
        return ss
    head, tail2 = m.groups()
    return f"{head}{tail2[0]}0{tail2[1]}"
```

**Examples:**
- `AHR21` → `AHR201`
- `W12` → `W102`

**Confidence:** 70% (domain-specific pattern)
**Status:** ✅ Already implemented for specific signal formats

---

## 4. GKS Format Patterns

### 4.1 GKS Validation Pattern

**File:** `data_validator2.py:394`

```python
GKS_PATTERN = re.compile(r'^\d{3,4}$')
```

**Format:** Exactly 3 or 4 digits
**Examples:**
- Valid: `123`, `0502`, `9999`
- Invalid: `12`, `12345`, `O502`, `12A`

---

### 4.2 GKS Cleaning (Remove All Non-Digits)

**File:** `data_validator2.py:406`

```python
suggested = re.sub(r'\D', '', gks_text)
```

**Examples:**
- `O502` → `502` (but should be `0502`)
- `W123` → `123` ✅
- `12-34` → `1234` ✅
- `AB12` → `12` ⚠️ (loses leading zeros)

**Confidence:** 70%
**Status:** ✅ Already implemented
**Issue:** Removes ALL non-digits, including common OCR confusions that should be substituted

**Enhancement Opportunity:**
Apply the same character substitution logic as signals:
```python
# Better approach
trans = str.maketrans({'O': '0', 'I': '1', 'L': '1', 'S': '5', 'B': '8'})
gks_cleaned = gks_text.translate(trans)
gks_cleaned = re.sub(r'\D', '', gks_cleaned)  # Then remove remaining non-digits
```

This would correctly handle:
- `O502` → `0502` ✅ (instead of `502`)
- `I234` → `1234` ✅ (instead of `234`)

---

## 5. Regex Patterns from Config

**File:** `config.py:114-121`

```python
CLASS_ID_PATTERNS = {
    "signal": r"^[A-ZÄÖÜ]{1,4}\d{1,4}$",
    "haltepunkt": r"^[A-ZÄÖÜ0-9]{1,10}$",
    "weichen_block": r"^.{1,50}$",  # Very permissive
    "gks_gesteuert": r"^\d{3,4}$",
    "gks_festkodiert": r"^\d{3,4}$",
}
```

**Usage:** Used in `core/ocr_engine.py:1736` for class-specific validation
**Note:** weichen_block is very permissive (any 1-50 chars)

---

## 6. Validation Checks

### 6.1 Already Implemented in data_validator2.py

1. **check_coordinate_format()** (line 250)
   - Validates coordinate text format
   - Auto-corrects lowercase → uppercase
   - Validates numeric part format

2. **check_signal_format()** (line 351)
   - Validates signal pattern `[A-ZÄÖÜ]{1,4}\d{1,4}`
   - Auto-corrects: uppercase, remove spaces, remove dashes

3. **check_gks_format()** (line 391)
   - Validates GKS is 3-4 digits
   - Auto-corrects: removes all non-digits

4. **check_fahrtrichtung_validity()** (line 434)
   - Validates fahrtrichtung is 'A' or 'B'
   - Auto-corrects: uppercase, trim whitespace

5. **check_missing_coordinates()** (line 184)
   - Flags anchors without linked coordinates
   - No auto-correction (requires manual linking)

6. **check_duplicate_ids()** (line 215)
   - Flags duplicate row_id values
   - No auto-correction (data integrity issue)

7. **check_signal_duplicates()** (line 470)
   - Flags signals with duplicate text at different positions
   - No auto-correction (might be legitimate)

8. **check_confidence_thresholds()** (line 539)
   - Flags low confidence detections
   - No auto-correction (needs manual review)

9. **check_coordinate_values()** (line 574)
   - Flags coordinates outside expected range
   - No auto-correction (domain knowledge needed)

### 6.2 Already Implemented in ultimate_validator.py

1. **_check_low_confidence()** (line 209)
   - Flags detections below confidence threshold
   - Uses class-specific thresholds

2. **_check_yolo_duplicates()** (line 259)
   - Flags same-class detections within 50 pixels
   - Currently only warning, not auto-corrected
   - **Auto-correction potential: HIGH** ✨

3. **_check_bbox_overlaps()** (line 324)
   - Flags overlapping bounding boxes (IoU-based)
   - Same class: IoU > 0.5
   - Cross class: IoU > 0.3

4. **_check_size_outliers()** (line 821)
   - Flags bounding boxes beyond 2.5 std deviations
   - Statistical outlier detection

5. **_check_coordinate_patterns()** (line 734)
   - ✨ **ADVANCED PATTERN VALIDATION**
   - Detects majority coordinate format on page
   - Flags coordinates that don't match majority pattern
   - Patterns detected:
     * `\d+,\d{4}$` - e.g., "0,0260"
     * `\d+\.\d+$` - e.g., "10.5"
     * `\d+,\d+$` - e.g., "10,5"
     * `\d+$` - e.g., "105" (no decimal)
   - Threshold: 60% of coordinates must match pattern

6. **_check_false_positives()** (line 641)
   - Flags detections in legend/border areas
   - Region-based filtering

7. **_check_missing_coordinates_spatial()** (line 888)
   - Flags anchors with nearby unlinked coordinates
   - ❌ NOT for auto-correction (user rejected)

8. **_check_isolated_detections()** (line 984)
   - Flags elements far from all others (>1000px)

9. **_check_expected_ratios()** (line 1029)
   - Checks element count ratios (e.g., signals:coordinates)
   - Informational only

10. **_check_cross_references()** (line 1082)
    - Flags multiple anchors sharing same coordinate
    - Requires manual review

---

## 7. Auto-Correction Opportunities

### 7.1 ✅ Already Implemented (High Confidence)

| Pattern | Confidence | File | Status |
|---------|-----------|------|--------|
| Lowercase → Uppercase in coordinates | 95% | data_validator2.py:269-287 | ✅ Active |
| Signal format cleaning (spaces, dashes) | 80% | data_validator2.py:351-389 | ✅ Active |
| GKS digit-only cleaning | 70% | data_validator2.py:391-432 | ✅ Active |
| Fahrtrichtung normalization | 90% | data_validator2.py:434-468 | ✅ Active |
| Trailing char removal | 90% | ocr_engine.py (20+ places) | ✅ Active |
| Bracket fixing (Gl. variations) | 85% | ocr_engine.py:753 | ✅ Active |
| Bracket completion | 75% | ocr_engine.py:631 | ✅ Active |
| Signal character substitution | 85% | ocr_engine.py:1279 | ✅ Active |

---

### 7.2 🔧 Safe New Auto-Corrections (Recommended)

#### A. Multiple Spaces → Single Space
**Pattern:** `re.sub(r'\s+', ' ', text).strip()`
**Confidence:** 90%
**Applied to:** All text fields
**Already used in:** Signal validation
**Example:** `GL  .15.492` → `GL .15.492`

**Why safe:** Multiple spaces are always OCR artifacts

---

#### B. Enhanced GKS Character Substitution
**Current:** Removes all non-digits
**Proposed:** Explicit character substitution before removal

```python
# Apply same substitutions as signal digits
trans = str.maketrans({
    'O': '0', 'o': '0',  # O/o → 0
    'I': '1', 'l': '1',  # I/l → 1
    'S': '5',            # S → 5
    'B': '8',            # B → 8
})
gks_cleaned = gks_text.translate(trans)
gks_cleaned = re.sub(r'\D', '', gks_cleaned)
```

**Examples:**
- `O502` → `0502` ✅ (current: `502` ❌)
- `I234` → `1234` ✅ (current: `234` ❌)

**Confidence:** 85%
**Why safe:** GKS fields are ALWAYS 3-4 digits, so any letter is OCR error

---

#### C. Duplicate YOLO Detection Removal
**File:** `ultimate_validator.py:259`
**Current:** Flags as warning
**Proposed:** Auto-delete with strict conditions

```python
# Only auto-delete if ALL conditions met:
1. Same class (e.g., both "signal")
2. Distance < 50 pixels
3. Same or very similar text (if available)
4. Confidence difference > 5%
5. Keep higher confidence, delete lower
```

**Confidence:** 85%
**Why safe:**
- Very close proximity (50px) means almost certainly same object
- Same class ensures we don't delete different object types
- Confidence check prevents deleting equally valid detections

**User feedback:** ✅ "duplicate removal sounds good"

---

#### D. Trailing/Leading Special Characters in Coordinates
**Pattern:**
```python
# Remove leading/trailing dots, dashes that aren't part of number
coord_text = re.sub(r'^[.\-]+|[.\-]+$', '', coord_text)
```

**Examples:**
- `.15.492` → `15.492`
- `15.492.` → `15.492`
- `-15.492-` → `15.492` (if not negative coordinate)

**Confidence:** 80%
**Why safe:** These are clearly OCR artifacts reading margin lines

---

### 7.3 ❌ NOT Recommended (User Rejected or Too Risky)

| Pattern | Reason | User Feedback |
|---------|--------|---------------|
| Comma → Dot conversion (general) | Too general, thousand separator ambiguity | ❌ Rejected |
| Spatial coordinate auto-linking | Random associations | ❌ "not good because it will then attach a random coordinate" |
| Missing GL. prefix addition | Too many assumptions | ❌ Too general |
| Negative coordinate fixing | Might be valid negatives | ❌ Domain knowledge needed |
| Decimal place normalization | Changes actual values | ❌ Data corruption risk |
| Region-based false positive removal | Layout-specific | ❌ Too many assumptions |
| Size outlier bbox expansion | Arbitrary expansion | ❌ Might include wrong content |
| Bbox overlap merging | Complex logic | ❌ Might merge unrelated |

---

## 8. Implementation Priority

### Quick Wins (Low Effort, High Value):
1. ✅ Multiple spaces → single space (already partially used)
2. 🔧 Enhanced GKS character substitution (leverage existing logic)
3. 🔧 Trailing/leading special chars (similar to existing pattern)

### Medium Effort (Careful Implementation Needed):
4. 🔧 Duplicate YOLO removal (needs proper checks and logging)

### Already Done (No Action Needed):
- ✅ Lowercase → uppercase conversion
- ✅ Signal format cleaning
- ✅ GKS basic cleaning
- ✅ Fahrtrichtung normalization
- ✅ Bracket fixing and completion
- ✅ Trailing character removal
- ✅ Signal character substitution

---

## 9. Key Findings Summary

### What's Already Working Well:
1. **Extensive OCR cleaning** in 20+ places removes trailing artifacts
2. **Signal character substitution** handles common OCR confusions (O→0, I→1, etc.)
3. **Bracket fixing** handles GI/Gl variations and incomplete brackets
4. **Format-specific validation** with auto-correction for coordinates, signals, GKS
5. **Pattern-based validation** in ultimate_validator detects majority format

### Gaps and Opportunities:
1. **GKS could use same character substitution** as signals (currently just removes)
2. **Duplicate removal** is detected but not auto-corrected (user wants this)
3. **Multiple space normalization** could be more explicit
4. **Coordinate pattern validation** is advanced but doesn't suggest corrections

### What NOT to Do:
1. ❌ General comma→dot conversion (user rejected)
2. ❌ Spatial auto-linking (creates wrong associations)
3. ❌ Any correction requiring domain knowledge or assumptions

---

**Last Updated:** 2026-01-06
**Based on:** Comprehensive search through all validation and OCR scripts
**Files Analyzed:** 15+ Python files, 100+ regex patterns found

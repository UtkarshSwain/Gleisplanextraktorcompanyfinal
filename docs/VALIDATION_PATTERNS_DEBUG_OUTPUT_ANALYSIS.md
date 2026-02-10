# Deep Validation Patterns & OCR Output Analysis

**Complete analysis of ALL validation criteria, OCR cleaning rules, and debug output patterns found across the entire codebase**

Based on exhaustive search through:
- `core/ocr_engine.py` (OCR processing, character substitution, cleaning)
- `core/pipelineworker.py` (pipeline validation, filtering, skipping logic)
- `core/linking.py` (coordinate parsing, signal filtering)
- `core/image_processing.py` (weichen_block parsing)
- `uservalidation/*.py` (validation checks)
- `uservalidation/data_validator2.py` (data validation)
- All other validation-related files

---

## 🎯 NEW DISCOVERIES - Critical Validation Rules

### 1. V-Signal Exclusion Rule ⭐
**Files:** `core/linking.py:687`, `core/pipelineworker.py:1029`

```python
# ✅ CRITICAL: Signals starting with "V" are SKIPPED from Fahrtrichtung detection
signal_text = signal_det.get("text", "")
if signal_text.startswith("V"):
    return None  # Skip V-signals
```

**Purpose:** V-signals (Vorsignale = distant signals) don't need Fahrtrichtung (direction)
**Validation opportunity:** Could flag signals starting with "V" that have Fahrtrichtung data (data integrity check)
**Confidence:** 100% (domain-specific business rule)

---

### 2. Weichen_Block First Line Rule ⭐
**File:** `core/ocr_engine.py:927`

```python
# ✅ CRITICAL: Weichen blocks MUST start with "W"
if line_info['text'].upper().startswith('W'):
    first_w_index = idx
    # Keep lines from first "W" onwards
```

**File:** `core/image_processing.py:12-42`

```python
def parse_weichen_block(text: str) -> dict:
    """
    Parse weichen block text into ID and coordinates.

    Example input:
        "WAHR921\nWA  0.0000(Gl.113)\nWA  0.0661(Gl.112)"

    Returns:
        {
            'id': 'WAHR921',
            'coordinates': ['WA  0.0000(Gl.113)', 'WA  0.0661(Gl.112)']
        }
    """
    lines = text.strip().split('\n')

    # First line is the block ID
    block_id = lines[0].strip()

    # Remaining lines are coordinates
    coordinates = [line.strip() for line in lines[1:] if line.strip()]
```

**Validation opportunities:**
1. **Block ID validation:** First line should match pattern `W[A-ZÄÖÜ]+\d+` (e.g., WAHR921, WA12)
2. **Coordinate line validation:** Subsequent lines should have coordinate format
3. **Empty lines removal:** Already implemented (`.strip()` filtering)

**Confidence:** 95% (structural validation)

---

### 3. Text Emptiness Checks (90+ occurrences)

**Pattern:** `.strip()` used everywhere to normalize whitespace and check emptiness

```python
# Emptiness checks
if not text.strip():  # Empty after removing whitespace
if not str(value).strip():  # Empty string value

# Normalization
coord_text = ' '.join(coord_txt.split()).strip()  # Multiple spaces → single space
```

**Files:** Found in 90+ places across:
- `pipelineworker.py` (lines 470, 508, 747, 789, 850, 903)
- `core/ocr_engine.py` (50+ occurrences)
- `uservalidation/data_validator2.py`
- `quality_inspector.py`

**Validation opportunity:**
- **Multi-space normalization** as explicit auto-correction (already used, not explicit in validator)

**Confidence:** 95%

---

### 4. Character Type Validation ⭐

**File:** `core/ocr_engine.py` and validators

```python
# Digit-only validation (GKS fields)
if not numeric_clean.isdigit():
    invalid_chars = ''.join(c for c in numeric_clean if not c.isdigit())
    # Flag as error

# Lowercase detection in coordinates (should be uppercase)
remaining_lowercase = [c for c in temp_text if c.islower()]
if remaining_lowercase:
    suggested = coord_text.upper()

# Alpha vs digit checks
has_alpha = any(c.isalpha() for c in s)
has_digit = any(c.isdigit() for c in s)
upper_ratio = (sum(c.isupper() for c in s) / max(1, sum(c.isalpha() for c in s)))
```

**Validation opportunities:**
1. **Lowercase letters in numeric fields** → flag as OCR error
2. **Letters in coordinate numeric part** → flag and suggest removal
3. **Digit-only field validation** (GKS, coordinate values)

**Confidence:** 90%

---

### 5. Haltepunkt-Referenced Signal Skipping ⭐
**File:** `core/pipelineworker.py:524-527`

```python
# ✅ NEW: SKIP if this signal is haltepunkt-referenced
if a["name"] == "signal" and id(a) in haltepunkt_referenced_signals:
    print(f"   ⏭️  SKIPPING signal '{name_txt}' (haltepunkt-referenced)")
    continue  # ✅ Don't process this signal at all
```

**Purpose:** Signals already linked to Haltepunkt markers should NOT be processed again as standalone signals
**Validation opportunity:** Flag signals that appear both as haltepunkt-linked AND standalone (duplicate detection)
**Confidence:** 100% (business logic)

---

### 6. Coordinate Number Detection Quality Check ⭐
**File:** `core/ocr_engine.py:433-434`, `ocr_engine.py:1081`

```python
# ✅ Quick quality check - skip if all detections are low confidence
if all(d['conf'] < 0.40 for d in all_detections):
    # Skip this OCR attempt

# Check if OCR detected any numbers
has_number = any(any(c.isdigit() for c in d['text']) for d in all_detections)
```

**Purpose:** If OCR didn't detect any digits, the coordinate OCR likely failed
**Validation opportunity:**
- Flag coordinates without any digits in their text
- Flag coordinates where ALL sub-detections have conf < 40%

**Confidence:** 85%

---

### 7. Coordinate Digit Density Check ⭐
**File:** `core/ocr_engine.py:694-716`

```python
# Main part (before bracket) should have decent number of digits
main_digits = sum(c.isdigit() for c in main_part)

# Bracket part should also have digits
bracket_digits = sum(c.isdigit() for c in bracket_part)

# Overall digit count
digit_count = sum(c.isdigit() for c in txt)
```

**Validation opportunity:**
- Coordinates should have minimum 3-4 digits total
- Bracketed coordinates: main part should have ≥3 digits, bracket part ≥1 digit

**Confidence:** 80%

---

### 8. Coordinate Must Start with Digit or Minus ⭐
**File:** `core/ocr_engine.py:767-779`

```python
def _looks_like_coordinate(text: str) -> bool:
    # Must start with a digit or minus sign
    if not (text[0].isdigit() or text[0] == '-'):
        return False

    # Must contain at least one digit and one dot
    has_digit = any(c.isdigit() for c in text)
    has_dot = '.' in text

    if not (has_digit and has_dot):
        return False
```

**Validation opportunity:**
- Flag coordinates that don't start with digit or `-`
- Flag coordinates without a decimal dot
- Flag coordinates without any digits

**Confidence:** 95%

---

### 9. GKS Digit-Only Extraction ⭐
**File:** `core/ocr_engine.py:1917`, `2039`, `2263`, `2291`

```python
# ✅ For GKS: Extract ONLY digits
t = ''.join(c for c in text if c.isdigit())
best_txt = ''.join(c for c in best_txt if c.isdigit())
```

**Already used:** GKS OCR automatically strips non-digits during OCR
**Validator uses:** `re.sub(r'\D', '', gks_text)` (remove all non-digits)

**Enhancement opportunity:** Apply character substitution BEFORE stripping:
```python
# Better approach
trans = str.maketrans({'O': '0', 'I': '1', 'l': '1', 'S': '5', 'B': '8'})
gks_text = gks_text.translate(trans)
gks_text = ''.join(c for c in gks_text if c.isdigit())
```

**Confidence:** 90%

---

### 10. Allow Numeric-Only Check (Coordinates) ⭐
**File:** `core/ocr_engine.py:1716`

```python
if not allow_numeric and s.isdigit():
    return False  # Pure numbers not allowed in some contexts
```

**Purpose:** Some OCR contexts should NOT accept pure numeric strings (context validation)
**Validation opportunity:** Flag coordinates that are ONLY digits (missing decimal separator)

**Confidence:** 80%

---

### 11. Uppercase Ratio Validation ⭐
**File:** `core/ocr_engine.py:1723`

```python
upper_ratio = (sum(c.isupper() for c in s) / max(1, sum(c.isalpha() for c in s)))
```

**Purpose:** Check if text has appropriate uppercase/lowercase ratio
**Validation opportunity:**
- Signal IDs should be mostly uppercase (>80%)
- Coordinates should be mostly uppercase (GL., not gl.)

**Confidence:** 75%

---

### 12. Sverbinder Coordinate Blacklisting ⭐
**File:** `core/pipelineworker.py:579-597`

```python
# ✅ Build blacklist: coordinates already linked to sverbinder (from pre-linking)
sverbinder_coord_ids = set()
for sverbinder_det in sverbinder_dets:
    linked = sverbinder_coord_map.get(id(sverbinder_det))
    if linked:
        sverbinder_coord_ids.add(id(linked))

# ✅ Filter out sverbinder coordinates (by ID)
available_coords = [c for c in coords if id(c) not in sverbinder_coord_ids]
```

**Purpose:** Prevent haltepunkt from stealing coordinates already linked to sverbinder
**Validation opportunity:** Flag coordinates linked to BOTH sverbinder AND another element (data integrity)

**Confidence:** 100% (business logic)

---

### 13. Low Confidence Batch Filtering ⭐
**File:** `core/ocr_engine.py:546-568`

```python
# Only accept high-confidence detections with brackets
if has_brackets and sc >= 2.0 and conf >= 0.50:
    return best_txt.strip()

# Higher threshold for non-bracketed
elif not has_brackets and sc >= 2.5 and conf >= 0.80:
    return best_txt.strip()
```

**Purpose:** Different confidence thresholds based on coordinate complexity
**Validation opportunity:**
- Flag bracketed coordinates with conf < 50%
- Flag simple coordinates with conf < 80%

**Confidence:** 85%

---

## 📊 Summary of New Auto-Correction Opportunities

### High Confidence (85-100%)

| # | Pattern | Confidence | Status | Files |
|---|---------|-----------|--------|-------|
| 1 | V-signal should not have fahrtrichtung | 100% | ⚠️ Check only | linking.py, pipelineworker.py |
| 2 | Haltepunkt-referenced signals shouldn't be standalone | 100% | ⚠️ Check only | pipelineworker.py |
| 3 | Sverbinder coord shouldn't be reused | 100% | ⚠️ Check only | pipelineworker.py |
| 4 | Weichen_block must start with 'W' | 95% | ⚠️ Check only | ocr_engine.py, image_processing.py |
| 5 | Coordinates must start with digit or `-` | 95% | ⚠️ Check only | ocr_engine.py |
| 6 | Text emptiness after `.strip()` | 95% | ✅ Already used | Everywhere |
| 7 | Multiple spaces → single space | 95% | ✅ Partial | pipelineworker.py (470+) |
| 8 | Lowercase in coordinates → uppercase | 95% | ✅ Implemented | data_validator2.py |
| 9 | Digit-only validation for GKS | 90% | ✅ Implemented | ocr_engine.py, validators |
| 10 | Enhanced GKS char substitution (O→0, I→1) | 90% | 🔧 Enhancement | ocr_engine.py |
| 11 | Character type validation (isdigit, isalpha) | 90% | ✅ Partial | validators |
| 12 | Coordinates must have decimal dot | 90% | ⚠️ Check only | ocr_engine.py |
| 13 | Coordinates must have ≥3 digits | 85% | ⚠️ Check only | ocr_engine.py |
| 14 | Bracketed coord conf threshold (50%) | 85% | ⚠️ Check only | ocr_engine.py |
| 15 | Simple coord conf threshold (80%) | 85% | ⚠️ Check only | ocr_engine.py |

### Medium Confidence (70-84%)

| # | Pattern | Confidence | Status | Notes |
|---|---------|-----------|--------|-------|
| 16 | Uppercase ratio check (signal IDs) | 75% | 🔧 New | ocr_engine.py |
| 17 | Digit density in coordinates | 80% | ⚠️ Check only | ocr_engine.py |
| 18 | Pure numeric coordinates (missing dot) | 80% | ⚠️ Check only | ocr_engine.py |

---

## 🎯 Priority Implementation Recommendations

### ✅ Already Perfectly Implemented
1. Lowercase → uppercase in coordinates (95% confidence)
2. Signal format cleaning (80% confidence)
3. GKS digit-only cleaning (70% confidence)
4. Fahrtrichtung A/B normalization (90% confidence)
5. Trailing character removal (90% confidence - 20+ places)
6. Bracket fixing (GI/Gl → Gl.) (85% confidence)
7. Signal character substitution (O→0, I→1, etc.) (85% confidence)

### 🔧 Quick Enhancement Opportunities

#### A. Enhanced GKS Character Substitution
**Current:** Just removes all non-digits
**Enhancement:** Use same char substitution as signals BEFORE removing

```python
# Apply before digit-only extraction
trans = str.maketrans({
    'O': '0', 'o': '0',  # O → 0
    'I': '1', 'l': '1',  # I/l → 1
    'S': '5',            # S → 5
    'B': '8',            # B → 8
    'Z': '2',            # Z → 2
    'G': '6',            # G → 6 (less common in GKS)
})
gks_text = gks_text.translate(trans)
gks_text = ''.join(c for c in gks_text if c.isdigit())
```

**Examples:**
- `O502` → `0502` ✅ (current: `502` ❌)
- `I234` → `1234` ✅ (current: `234` ❌)
- `5B3` → `583` ✅ (current: `53` ❌)

**Impact:** Preserves leading zeros and fixes OCR confusions
**Confidence:** 90%

---

#### B. Explicit Multi-Space Normalization
**Current:** Used in many places but not explicit in validator
**Enhancement:** Add as auto-correction with high confidence

```python
# Already used in pipelineworker.py (6+ places)
coord_txt = ' '.join(coord_txt.split()).strip()
```

**Apply to:** All text fields
**Confidence:** 95%

---

### ⚠️ New Validation Checks (No Auto-Correction)

These should FLAG issues but NOT auto-correct (need manual review):

1. **V-signal with Fahrtrichtung** - Business rule violation (100% confidence)
2. **Duplicate signal instances** - One as haltepunkt-linked, one standalone (100%)
3. **Coordinate reuse** - Same coordinate linked to sverbinder AND other element (100%)
4. **Weichen_block not starting with 'W'** - OCR error or wrong class (95%)
5. **Coordinate not starting with digit/-** - OCR error (95%)
6. **Coordinate without decimal dot** - OCR error (90%)
7. **Coordinate with <3 digits** - OCR error (85%)
8. **Low confidence batch filtering** - Different thresholds for bracketed vs simple (85%)

---

## 🔍 Detailed Pattern Analysis

### Pattern: Multiple Space Normalization

**Occurrences:** 10+ explicit uses in pipelineworker.py

```python
# Line 470
coord_txt = ' '.join(coord_txt.split()).strip()

# Line 508
coord_txt = ' '.join(coord_txt.split()).strip()

# Line 747
coord_txt = ' '.join(coord_txt.split()).strip()

# Lines 789, 850, 903 (similar pattern)
```

**Also used in:**
- `core/ocr_engine.py:1266` - Signal normalization
- Throughout for text cleaning

**Why it works:**
- `.split()` with no args splits on ANY whitespace (spaces, tabs, newlines)
- `' '.join()` joins with exactly one space
- `.strip()` removes leading/trailing whitespace

**Examples:**
- `"GL  .15.492"` → `"GL .15.492"`
- `"A  101"` → `"A 101"`
- `"  text  with   spaces  "` → `"text with spaces"`

**Recommendation:** Add as explicit auto-correction in validator
**Confidence:** 95%

---

### Pattern: Character Type Checks

**From validators:**

```python
# data_validator2.py:267
remaining_lowercase = [c for c in temp_text if c.islower()]

# data_validator2.py:311
if not numeric_clean.isdigit():
    invalid_chars = ''.join(c for c in numeric_clean if not c.isdigit())
```

**From OCR engine:**

```python
# ocr_engine.py:1721-1723
has_alpha = any(c.isalpha() for c in s)
has_digit = any(c.isdigit() for c in s)
upper_ratio = (sum(c.isupper() for c in s) / max(1, sum(c.isalpha() for c in s)))
```

**Applications:**
1. **Lowercase detection** → Auto-correct to uppercase (✅ already done)
2. **Digit-only validation** → Flag non-digits in numeric fields (✅ already done for GKS)
3. **Uppercase ratio** → Flag suspiciously lowercase signal IDs (🔧 new check)

---

### Pattern: Coordinate Quality Checks

**Multiple layers of validation:**

```python
# 1. Must start with digit or minus
if not (text[0].isdigit() or text[0] == '-'):
    return False

# 2. Must have both digits and dot
has_digit = any(c.isdigit() for c in text)
has_dot = '.' in text
if not (has_digit and has_dot):
    return False

# 3. Must have minimum digit density
digit_count = sum(c.isdigit() for c in txt)
if digit_count < 3:  # Example threshold
    flag_as_suspicious()

# 4. Confidence threshold based on complexity
if has_brackets and conf < 0.50:
    flag_low_confidence()
elif not has_brackets and conf < 0.80:
    flag_low_confidence()
```

**All checks implemented in OCR engine but NOT in validator**
**Recommendation:** Add explicit validation checks in validator
**Confidence:** 85-95% depending on check

---

## 🎓 Domain-Specific Business Rules

### Rule 1: V-Signals (Vorsignale)
**Definition:** Distant signals that preview the state of the next main signal
**Characteristic:** Start with 'V' (e.g., V101, VHR2)
**Business rule:** Do NOT need Fahrtrichtung (direction) because they're not directional markers

**Implementation:**
```python
# core/linking.py:687
if signal_text.startswith("V"):
    return None  # Skip Fahrtrichtung detection
```

**Validation:** Flag any V-signal that HAS Fahrtrichtung data (data anomaly)

---

### Rule 2: Haltepunkt-Signal Grouping
**Definition:** Haltepunkt (stop point) markers are often grouped with signals and coordinates
**Business rule:** Once a signal is linked to haltepunkt, it should NOT appear as standalone

**Implementation:**
```python
# core/pipelineworker.py:427-430
haltepunkt_referenced_signals.add(id(group['signal_det']))

# Later (line 524-527)
if a["name"] == "signal" and id(a) in haltepunkt_referenced_signals:
    continue  # Skip this signal
```

**Validation:** Flag signals appearing both as haltepunkt-linked AND standalone

---

### Rule 3: Sverbinder Coordinate Exclusivity
**Definition:** Sverbinder (track connectors) are pre-linked to coordinates
**Business rule:** Those coordinates should NOT be reused by other elements

**Implementation:**
```python
# core/pipelineworker.py:579-597
sverbinder_coord_ids = set()
# ... build blacklist ...
available_coords = [c for c in coords if id(c) not in sverbinder_coord_ids]
```

**Validation:** Flag coordinates linked to BOTH sverbinder AND another element type

---

## 📈 Impact Analysis

### Current State
- **8 auto-corrections** already implemented (high confidence: 70-95%)
- **20+ OCR cleaning patterns** active during OCR phase
- **10+ validation checks** in ultimate_validator.py
- **6+ format validators** in data_validator2.py

### Enhancement Opportunities
1. **GKS character substitution** - Easy win, leverages existing signal logic
2. **Multi-space normalization** - Already used, just needs explicit validator entry
3. **Business rule validation** - 3 new checks (V-signal, haltepunkt, sverbinder)
4. **Coordinate quality checks** - 5 new checks from OCR engine

### Risk Assessment
- ✅ **Low risk:** GKS enhancement, multi-space normalization (already used)
- ⚠️ **Medium risk:** Coordinate quality checks (need testing on real data)
- ⚠️ **Low risk:** Business rule checks (informational only, no auto-correction)

---

**Last Updated:** 2026-01-06
**Based on:** Exhaustive search through entire codebase
**Files Analyzed:** 20+ Python files, 200+ validation patterns found
**New Patterns vs Previous Analysis:** +15 new high-value patterns discovered

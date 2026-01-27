# Validation Criteria and Auto-Correction Possibilities

This document lists all validation checks currently implemented in the system and suggests potential auto-corrections that could be implemented.

## Legend
- ✅ **Currently Implemented with Auto-Correction**
- 🔧 **Can Be Auto-Corrected** (not yet implemented)
- ⚠️ **Requires Manual Review** (too complex or risky for auto-correction)
- 📊 **Information Only** (no correction needed)

---

## 1. OCR Format Validation (data_validator2.py)

### 1.1 Coordinate Format Checking (`check_coordinate_format`)

#### ✅ Lowercase Letters → Uppercase Conversion
**Current Value:** `gl.15.492`
**Auto-Correction:** `GL.15.492`
**Confidence:** 95%
**Status:** ✅ Already implemented
**Logic:** Convert all lowercase letters to uppercase (except 'l' in 'Gl.' patterns)

#### 🔧 Comma → Dot Conversion in Coordinates
**Current Value:** `15,492`
**Potential Correction:** `15.492`
**Confidence:** 90%
**Status:** 🔧 Can be implemented
**Logic:** Replace comma decimal separators with dots in coordinate numeric parts

#### ⚠️ Invalid Numeric Format
**Example:** `AB.15.492` (letters in numeric part)
**Status:** ⚠️ Requires manual review
**Reason:** Unclear what the correct value should be - could be OCR error

#### 🔧 Missing or Incorrect Brackets
**Current Value:** `15.492 GL` or `15.492(GL`
**Potential Correction:** `15.492(GL)`
**Confidence:** 75%
**Status:** 🔧 Can be implemented
**Logic:** Ensure brackets are properly paired around suffix

### 1.2 Missing Coordinates (`check_missing_coordinates`)

#### ⚠️ Anchor Without Coordinate Link
**Status:** ⚠️ Requires manual review
**Reason:** Cannot automatically determine which coordinate should be linked

---

## 2. YOLO Detection Quality (ultimate_validator.py)

### 2.1 Low Confidence Detections (`_check_low_confidence`)

#### ⚠️ Detection Below Confidence Threshold
**Example:** Signal detected with 65% confidence (threshold: 80%)
**Status:** ⚠️ Requires manual review
**Reason:** Low confidence means OCR might be wrong; manual verification needed

**Potential Future Enhancement:** Could suggest re-running OCR with different parameters

### 2.2 Duplicate Detections (`_check_yolo_duplicates`)

#### 🔧 Duplicate Detections (Same Class, Close Position)
**Example:** Two "signal" detections within 50 pixels of each other
**Potential Correction:** Keep the detection with higher confidence, delete the other
**Confidence:** 85%
**Status:** 🔧 Can be implemented
**Logic:**
- Calculate distance between all same-class detections
- If distance < 50 pixels:
  - Compare confidence scores
  - Keep higher confidence detection
  - Delete lower confidence detection

**Parameters to consider:**
- `distance_threshold`: 50 pixels (default)
- `confidence_difference_min`: 0.05 (only auto-delete if confidence diff > 5%)

### 2.3 Bounding Box Overlaps (`_check_bbox_overlaps`)

#### 🔧 High Overlap Between Same Class
**Example:** Two coordinate boxes with 60% IoU (Intersection over Union)
**Potential Correction:** Merge or keep higher confidence detection
**Confidence:** 70%
**Status:** 🔧 Can be implemented with caution
**Logic:**
- Calculate IoU for same-class pairs
- If IoU > 0.5:
  - Check if text content is identical → Merge
  - Check if text content differs → Keep both but flag for review
  - If one has much higher confidence → Delete lower one

#### ⚠️ Moderate Overlap Between Different Classes
**Example:** Signal box overlapping with coordinate box (30% IoU)
**Status:** ⚠️ Requires manual review
**Reason:** Cross-class overlaps might be legitimate (signal and its coordinate)

### 2.4 Size Outliers (`_check_size_outliers`)

#### 🔧 Extremely Small or Large Bounding Boxes
**Example:** Signal bbox area 50 pixels (avg: 2000 pixels, std dev > 2.5)
**Potential Correction:**
- **Small boxes:** Could be OCR error → Re-run OCR with expanded bbox
- **Large boxes:** Could include multiple elements → Suggest splitting

**Confidence:** 60% (requires careful handling)
**Status:** 🔧 Can be implemented with manual confirmation
**Logic:**
- Calculate mean and std dev of bbox areas per class
- Flag outliers beyond 2.5 standard deviations
- For small outliers: Offer to expand bbox by 20% and re-run OCR
- For large outliers: Suggest manual review

---

## 3. Class Relationships (`_check_class_relationships`)

### 3.1 Coordinate Out of Acceptable Range

#### 🔧 Coordinate Value Out of Expected Range
**Example:** Coordinate value `-0.325` when expected range is `0.000` to `50.000`
**Potential Correction:**
- If negative sign is OCR error: Remove negative sign
- If value is off by factor of 10: Suggest decimal point correction

**Confidence:** 70%
**Status:** 🔧 Can be implemented
**Logic:**
- Check if removing `-` brings value into range → Auto-correct
- Check if moving decimal point brings value into range → Suggest correction
- Example: `-32.5` → `32.5` (high confidence)
- Example: `325` → `32.5` (medium confidence, needs review)

---

## 4. Missing Text (`_check_missing_text`)

#### ⚠️ Element Missing Required Text
**Example:** Signal without anchor_text
**Status:** ⚠️ Requires manual review
**Potential Future Enhancement:** Trigger re-OCR automatically

---

## 5. Coordinate Patterns (`_check_coordinate_patterns`)

### 5.1 Inconsistent Format Patterns

#### 🔧 Missing Track Prefix (Gl.)
**Current Value:** `15.492`
**Potential Correction:** `GL.15.492` (if other coordinates on same page have GL. prefix)
**Confidence:** 80%
**Status:** 🔧 Can be implemented
**Logic:**
- Analyze format patterns on same page
- If 80%+ of coordinates have `GL.` prefix
- And current coordinate is just numbers
- → Suggest adding `GL.` prefix

#### 🔧 Inconsistent Decimal Places
**Current Values:** `GL.15.492`, `GL.15.5`, `GL.15.49`
**Potential Correction:** Normalize to same decimal places (most common format)
**Confidence:** 65%
**Status:** 🔧 Can be implemented
**Logic:**
- Find most common decimal place count on page
- Pad or truncate others to match
- Example: If most have 3 decimals, convert `15.5` → `15.500`

---

## 6. False Positives (`_check_false_positives`)

#### ⚠️ Element Detected Outside Plausible Area
**Example:** Signal detected in legend area, title block, or border
**Status:** ⚠️ Requires manual review (or auto-delete with high confidence)
**Potential Auto-Correction:** Delete detections in known non-content areas
**Confidence:** 90% (if clear borders/regions are defined)
**Status:** 🔧 Can be implemented with region mapping

**Logic:**
- Define excluded regions: top margin (0-100px), bottom margin (last 150px), legend areas
- If detection centroid falls in excluded region
- AND detection class is content-related (signal, coordinate, etc.)
- → Auto-delete or flag for review

---

## 7. Missing Coordinates (Spatial) (`_check_missing_coordinates_spatial`)

#### ❌ Anchor Has Nearby Coordinate Not Yet Linked (NOT RECOMMENDED)
**Example:** Signal at (500, 300) with unlinked coordinate at (520, 300)
**Status:** ❌ NOT RECOMMENDED
**Problem:** Will attach random coordinates - might link wrong coordinate to wrong anchor
**Risk:** High

**Why this is risky:**
- Multiple coordinates might be nearby
- No way to know which coordinate belongs to which anchor
- Could create wrong associations that are hard to fix
- Manual linking ensures correct relationships

**Decision:** Keep as informational warning only, require manual linking

---

## 8. Isolated Detections (`_check_isolated_detections`)

#### ⚠️ Element Far From All Others
**Example:** Signal 1500 pixels away from any other detection
**Status:** ⚠️ Requires manual review
**Potential Enhancement:** Could suggest deletion if very low confidence + isolated

---

## 9. Expected Ratios (`_check_expected_ratios`)

#### 📊 Unexpected Element Count Ratios
**Example:** 50 signals but only 10 coordinates (expected ratio: 1:1 to 1:1.5)
**Status:** 📊 Information only
**Purpose:** Flags dataset-level issues, not individual corrections

---

## 10. Cross References (`_check_cross_references`)

#### 🔧 Multiple Anchors Sharing Same Coordinate
**Example:** Signal "S1" and Signal "S2" both linked to coordinate "15.492"
**Potential Correction:**
- Check if coordinate value should be duplicated for both
- Check if one link is incorrect

**Confidence:** 60%
**Status:** 🔧 Can be implemented with caution
**Logic:**
- If anchors are very close to each other → Likely correct (shared coordinate)
- If anchors are far apart → One link probably wrong → Suggest relinking

---

## Summary: Auto-Correction Implementation Priority

### ✅ Safe & Recommended Auto-Corrections

These are **specific, high-confidence** corrections that won't cause problems:

1. ✅ **Lowercase → Uppercase** (Already implemented)
   - Confidence: 95%
   - Risk: Very low
   - Example: `gl.15.492` → `GL.15.492`

2. 🔧 **Comma → Dot in coordinates** (Recommended)
   - Confidence: 90%
   - Risk: Very low (coordinate format is well-defined)
   - Example: `15,492` → `15.492`

3. 🔧 **Duplicate detection removal** (Recommended)
   - Confidence: 85% (if both have similar confidence)
   - Risk: Low (only remove if same class + very close position + similar text)
   - Example: Two identical "signal" detections at same position
   - Safety: Keep higher confidence, delete lower confidence

4. 🔧 **Coordinate bracket fixing** (Recommended with caution)
   - Confidence: 75%
   - Risk: Low (pattern-based)
   - Example: `15.492(GL` → `15.492(GL)`
   - Only apply if clearly missing closing bracket

### ⚠️ NOT Recommended (Too General or Risky)

These were initially suggested but are **too risky** due to their generality:

5. ❌ **Spatial coordinate auto-linking**
   - **Problem:** Will attach random coordinates
   - **Risk:** High - might link wrong coordinate to wrong anchor
   - **Decision:** Manual linking only

6. ❌ **Missing GL. prefix addition**
   - **Problem:** Too general - assumes all coordinates need GL. prefix
   - **Risk:** Medium - might add prefix where not needed
   - **Decision:** Too many assumptions, manual review better

7. ❌ **Negative coordinate fixing**
   - **Problem:** Assumes negative is always wrong
   - **Risk:** Medium - might correct valid negative coordinates
   - **Decision:** Need domain knowledge, manual review better

8. ❌ **Decimal place normalization**
   - **Problem:** Might change actual coordinate values
   - **Risk:** High - could introduce data errors
   - **Decision:** Manual review only

9. ❌ **False positive removal in regions**
   - **Problem:** Need accurate region mapping per layout
   - **Risk:** High - might delete valid detections
   - **Decision:** Too layout-specific, manual review better

10. ❌ **Size outlier bbox expansion**
    - **Problem:** Arbitrary bbox expansion might include wrong content
    - **Risk:** Medium-High
    - **Decision:** Manual bbox adjustment better

11. ❌ **Bbox overlap merging**
    - **Problem:** Complex logic, might merge unrelated elements
    - **Risk:** High
    - **Decision:** Manual review only

12. ❌ **Cross-reference fixing**
    - **Problem:** Cannot determine intent automatically
    - **Risk:** High
    - **Decision:** Manual review only

---

## Implementation Notes

### Auto-Correction Confidence Levels
- **≥95%**: Apply automatically without confirmation
- **80-94%**: Apply automatically but log for review
- **60-79%**: Suggest to user, require confirmation
- **<60%**: Show as informational, don't offer auto-correction

### Safety Mechanisms
1. **Undo Support**: All auto-corrections must be undoable
2. **Logging**: Keep detailed log of what was changed and why
3. **Batch Review**: Allow user to review all proposed corrections before applying
4. **Confidence Display**: Always show confidence score for each proposed fix
5. **Preview**: Show before/after for each correction

### Code Structure for New Auto-Corrections
```python
# In data_validator2.py or ultimate_validator.py

def check_[validation_name](self) -> List[ValidationIssue]:
    issues = []

    for _, row in self.df.iterrows():
        # Validation logic
        if problem_detected:
            suggested_value = calculate_correction(row)
            confidence = calculate_confidence_score()

            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='error'/'warning'/'info',
                category='format'/'spatial'/'quality',
                field='coord_text'/'anchor_text'/etc,
                message="Human-readable problem description",
                current_value=row[field],
                suggested_value=suggested_value,
                auto_correctable=(confidence >= 0.60),  # Only if confidence ≥ 60%
                confidence=confidence,
                context={'extra': 'metadata'}
            ))

    return issues
```

---

## Final Recommendations

### Implement These (Safe & Useful):
1. ✅ Lowercase → Uppercase (already done)
2. 🔧 Comma → Dot conversion
3. 🔧 Duplicate removal (same class + close position)
4. 🔧 Bracket fixing (with caution)

### Do NOT Implement (Too Risky):
- ❌ Auto-linking coordinates (random associations)
- ❌ Missing prefix addition (too many assumptions)
- ❌ Negative fixing (might be valid negatives)
- ❌ Decimal normalization (changes data)
- ❌ Region-based removal (layout-specific)
- ❌ Size outlier expansion (arbitrary)
- ❌ Overlap merging (complex)
- ❌ Cross-reference fixing (can't determine intent)

**Philosophy:** Only implement **specific, low-risk** corrections. When in doubt, flag for manual review.

---

**Last Updated:** 2026-01-06
**Maintainer:** Claude Code
**Project:** Gleisplanextraktorv3

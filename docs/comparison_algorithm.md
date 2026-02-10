# Gleisplan Comparison Algorithm Documentation

## Overview

The Gleisplanextraktor comparison engine uses a **Hungarian Algorithm** (also known as the Kuhn-Munkres algorithm) to optimally match elements between two track layout versions. This document describes the algorithm, parameters, and design decisions.

---

## 1. Why Hungarian Algorithm?

### The Problem with Greedy Matching

The original greedy matching approach had a critical flaw when handling **duplicate elements** (multiple elements of the same class at similar coordinates):

```
Greedy Algorithm:
for each old_element:
    for each new_element:
        if score > best_score:
            match = new_element
```

**Issue:** When multiple elements have the same `coord_text` (e.g., two `sverbinder` at km 0.054):
- All pairs get similar scores (~0.85)
- Greedy picks the first match it finds
- Order-dependent → **wrong pairings** or **false DELETED/ADDED**

### The Hungarian Solution

The Hungarian algorithm finds the **globally optimal assignment** that maximizes total matching score:

```python
from scipy.optimize import linear_sum_assignment

# Build cost matrix (negative scores for minimization)
cost_matrix[i, j] = -score(old_i, new_j)

# Find optimal assignment
row_ind, col_ind = linear_sum_assignment(cost_matrix)
```

**Benefits:**

| Aspect | Greedy | Hungarian |
|--------|--------|-----------|
| Duplicate handling | Order-dependent | **Optimal** |
| False DELETED/ADDED | Common | **Eliminated** |
| Time complexity | O(n²) | O(n³) |
| Correctness | Local optimum | **Global optimum** |

---

## 2. Matching Architecture

### Two-Phase Matching

```
Phase 1: UUID Matching
├── Elements with same detection_id = guaranteed match
└── No scoring needed (perfect match)

Phase 2: Spatial/Semantic Fallback (Hungarian)
├── Group elements by class
├── Build cost matrix per class
├── Run Hungarian algorithm
└── Accept matches with score > 0.7
```

### Class-Specific Strategies

| Class Type | Classes | Primary Identifier | Strategy |
|------------|---------|-------------------|----------|
| **OCR** | signal, gks_gesteuert, gks_festkodiert | `anchor_text` | Text similarity + coord proximity |
| **Coordinate** | coordinate | `coord_text` | Exact/fuzzy text match |
| **Non-OCR Symbol** | sverbinder, gm_block, isolierstoß, etc. | `coord_text` / `coord_value` | Coordinate proximity + spatial position |

---

## 3. Scoring Parameters

### 3.1 OCR Classes (signal, gks_*)

**Base Score:**
- GKS elements: `0.6` (exact anchor_text match required)
- Signals: `0.7 × text_similarity` (fuzzy match allowed, threshold 0.9)

**Coordinate Bonus (tiered):**

| coord_diff | Bonus | Description |
|------------|-------|-------------|
| < 1m | +0.15 | Essentially identical |
| < 5m | +0.12 | Very close |
| < 10m | +0.10 | Close |
| < 20m | +0.08 | Near |
| < 50m | +0.06 | Medium |
| < 100m | +0.04 | Far |
| < 500m | +0.02 | Very far |
| ≥ 500m | +0.00 | No bonus |

**Spatial Bonus (tiered, pixels):**

| Distance | Bonus | Description |
|----------|-------|-------------|
| < 50px | +0.30 | Very close |
| < 100px | +0.26 | Close |
| < 150px | +0.22 | Near |
| < 250px | +0.18 | Medium |
| < 400px | +0.14 | Far |
| < 600px | +0.12 | Very far |
| ≥ 600px | +0.10 | Minimum (ensures threshold) |

**Score Range:** 0.70 - 1.0

**Note:** OCR classes have **no hard coordinate cutoff** because they have unique identifiers (signal names, GKS numbers). Same name = same element regardless of distance.

---

### 3.2 Non-OCR Symbol Classes

**Classes:** sverbinder, gm_block, isolierstoß, haltepunkt, prellbock, haltetafel, weichenende, weichengruppenende

**Coordinate Score (tiered):**

| coord_diff | Score | Description |
|------------|-------|-------------|
| < 1m | +0.85 | Essentially same position |
| < 10m | +0.82 | Very close |
| < 20m | +0.78 | Close |
| < 40m | +0.74 | Medium distance |
| < 70m | +0.72 | Far |
| < 100m | +0.70 | Edge of tolerance |
| **≥ 100m** | **0.0** | **Hard cutoff - different elements** |

**Spatial Bonus (tiered, pixels):**

| Distance | Bonus | Description |
|----------|-------|-------------|
| < 50px | +0.15 | Very close |
| < 100px | +0.10 | Close |
| < 200px | +0.05 | Medium |
| < 350px | +0.02 | Far |
| ≥ 350px | +0.00 | No bonus |

**Score Range:** 0.70 - 1.0 (with 100m hard cutoff)

**Design Decision:** Non-OCR classes have auto-generated names (e.g., "sverbinder 1", "GM") that are not unique identifiers. Therefore, `coord_value` is the primary identifier, and elements >100m apart are considered **different elements**.

---

### 3.3 Haltepunkt Special Handling

Haltepunkt has special logic to extract signal names from brackets:

```
Format: "haltepunkt {counter} ({signal_name})"
Example: "haltepunkt 1 (MB456)" → signal_name = "MB456"
```

**Matching Rules:**
1. Both have signal names and they match → Score 0.9 + spatial bonus
2. Both have signal names and they differ → **No match (0.0)**
3. One or neither has signal name → Fall through to standard matching

---

### 3.4 Coordinate Class

**Matching:** Direct `coord_text` comparison

| Condition | Score |
|-----------|-------|
| Exact match | 1.0 |
| Similarity ≥ 0.9 | text_similarity |
| Similarity < 0.9 | 0.0 |

---

## 4. Global Parameters

### Matching Threshold

```python
MATCH_THRESHOLD = 0.7
```

All matches with score < 0.7 are rejected. This ensures only confident matches are accepted.

### Coordinate Tolerance

```python
COORD_MATCH_TOLERANCE = 0.1  # km (±50m, 100m total range)
```

For non-OCR elements, elements with `coord_value` difference > 100m are considered different elements.

### Page Tolerance

```python
if abs(page1 - page2) > 1:
    return 0.0  # Elements on non-adjacent pages cannot match
```

Elements can only match if they are on the same page or adjacent pages.

---

## 5. Change Detection

After matching, changes are classified:

| Change Type | Condition | Severity Levels |
|-------------|-----------|-----------------|
| **ADDED** | Element in new, not in old | MAJOR |
| **DELETED** | Element in old, not in new | MAJOR |
| **MOVED** | Same ID, `coord_value` changed | MINOR (<5m), MODERATE (5-20m), MAJOR (>20m) |
| **MODIFIED** | Same ID, other fields changed | Depends on field |
| **UNCHANGED** | No meaningful changes | MINOR |

### Severity Thresholds

| Severity | Coordinate Change | Spatial Movement |
|----------|-------------------|------------------|
| MAJOR | > 20m | > 100px |
| MODERATE | 5-20m | 50-100px |
| MINOR | < 5m | < 50px |

---

## 6. Algorithm Complexity

### Time Complexity

| Phase | Complexity | Description |
|-------|------------|-------------|
| UUID Matching | O(n) | Set intersection |
| Cost Matrix Build | O(n × m) | Per class |
| Hungarian Algorithm | O(max(n,m)³) | Per class |
| Total | O(k × max(n,m)³) | k = number of classes |

### Space Complexity

| Component | Complexity |
|-----------|------------|
| Cost Matrix | O(n × m) per class |
| Grouped Elements | O(n) |

---

## 7. Example: Duplicate Matching

### Scenario

Layout 1 (Old):
- sverbinder_A @ coord 0.0537 (x=100, y=200)
- sverbinder_B @ coord 0.0537 (x=500, y=200)

Layout 2 (New):
- sverbinder_C @ coord 0.0537 (x=120, y=210)
- sverbinder_D @ coord 0.0537 (x=480, y=190)

### Cost Matrix

```
                sverbinder_C    sverbinder_D
sverbinder_A       -0.95           -0.75      (A closer to C)
sverbinder_B       -0.75           -0.95      (B closer to D)
```

### Hungarian Assignment

```
Optimal: A→C (0.95), B→D (0.95)
Total: 1.90 ✓

Greedy might get: A→D (0.75), B→C (0.75)
Total: 1.50 ✗
```

---

## 8. Debug Output

Enable debug mode to trace matching:

```python
engine = LayoutComparisonEngine(debug=True)
```

Debug output format:

```
[DEBUG] Hungarian matching for class 'sverbinder':
    Old elements: 2, New elements: 2
    Score[0,0]: 0.950 | Old: sverbinder 1 → New: sverbinder 3
    Score[0,1]: 0.750 | Old: sverbinder 1 → New: sverbinder 4
    Score[1,0]: 0.750 | Old: sverbinder 2 → New: sverbinder 3
    Score[1,1]: 0.950 | Old: sverbinder 2 → New: sverbinder 4
    Hungarian assignment: [(0, 0), (1, 1)]
    ✓ MATCHED (score=0.950): 'sverbinder 1' @ 0.054 → 'sverbinder 3' @ 0.054
    ✓ MATCHED (score=0.950): 'sverbinder 2' @ 0.054 → 'sverbinder 4' @ 0.054
```

---

## 9. Configuration Reference

### Default Configuration

```python
{
    # Change detection thresholds
    'coordinate_tolerance': 0.0001,  # 0.1m (10cm) - for detecting changes
    'spatial_distance_threshold': 200,  # pixels
    'min_coordinate_change': 0.5,  # meters
    'significant_coordinate_change': 10.0,  # meters
    'min_spatial_movement': 10,  # pixels
    'min_angle_change': 10.0,  # degrees

    # Matching weights (not currently used - hardcoded for reliability)
    'weight_uuid': 1.0,
    'weight_text': 0.6,
    'weight_spatial': 0.4,
    'text_similarity_threshold': 0.85,
}
```

### Class-Specific Configuration

```python
'critical_fields': {
    'signal': {'identifier': 'anchor_text', 'tracked_fields': ['coord_value', 'fahrtrichtung']},
    'gks_gesteuert': {'identifier': 'anchor_text', 'tracked_fields': ['coord_value']},
    'gks_festkodiert': {'identifier': 'anchor_text', 'tracked_fields': ['coord_value']},
    'coordinate': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
    'gm_block': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
    'sverbinder': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
    'isolierstoß': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
    'haltepunkt': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
    'prellbock': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
    'haltetafel': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
    'weichenende': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
    'weichengruppenende': {'identifier': 'coord_text', 'tracked_fields': ['coord_value']},
}
```

---

## 10. Summary

The comparison algorithm provides:

1. **Optimal matching** via Hungarian algorithm
2. **Class-specific strategies** for OCR vs non-OCR elements
3. **Tiered scoring** for fine-grained differentiation
4. **Robust edge case handling** (NaN, None, empty strings)
5. **Debug output** for troubleshooting
6. **Configurable thresholds** for different use cases

Key design decisions:
- **OCR classes:** No distance cutoff (unique identifiers)
- **Non-OCR classes:** 100m hard cutoff (coordinate-based identity)
- **Threshold 0.7:** Balances precision and recall
- **Tiered scoring:** Enables Hungarian to find optimal pairings

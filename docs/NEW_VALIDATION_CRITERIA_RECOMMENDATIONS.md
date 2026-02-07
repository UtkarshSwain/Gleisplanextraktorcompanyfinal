# New Validation Criteria Recommendations

**For Quality Inspector (Qualitätsprüfung) and Data Validation (Datenvalidierung)**

Based on deep code analysis - patterns found in pipelineworker.py, ocr_engine.py, linking.py

---

## 📊 Currently Implemented

### Quality Inspector (quality_inspector.py)
✅ **4 Risk Factors:**
1. Low confidence (conf < 0.6) - "Unsichere Texterkennung"
2. Missing coordinate - "Koordinate fehlt"
3. Missing text - "Bezeichnung fehlt"
4. Potential duplicate (distance < 50px) - "Evtl. doppelt erkannt"
5. Size anomaly - "Auffällige Größe"

### Data Validation (data_validator2.py)
✅ **9 Checks:**
1. check_missing_coordinates()
2. check_coordinate_format() - with auto-correct (uppercase)
3. check_signal_format() - with auto-correct (spaces, dashes)
4. check_gks_format() - with auto-correct (remove non-digits)
5. check_fahrtrichtung_validity() - with auto-correct (A/B)
6. check_confidence_thresholds()
7. check_coordinate_values()
8. ~~check_duplicate_ids()~~ - DISABLED
9. ~~check_signal_duplicates()~~ - DISABLED

---

## 🆕 Recommended New Checks

### For Quality Inspector (Quick Pre-Checks)

#### Priority 1: High Impact, Easy Implementation

| # | Check | Risk Factor Text | Weight | Confidence | Implementation |
|---|-------|------------------|--------|------------|----------------|
| 1 | **Empty text after strip** | "Leere Bezeichnung" | 20% | 100% | `not str(anchor_text).strip()` |
| 2 | **Multiple spaces in text** | "Formatierungsfehler" | 5% | 95% | `'  ' in text` (2+ spaces) |
| 3 | **Coordinate missing decimal** | "Koordinate ohne Komma" | 15% | 90% | `'.' not in coord_text` |
| 4 | **Coordinate not starting with digit** | "Ungültige Koordinate" | 20% | 95% | `not coord_text[0].isdigit() and coord_text[0] != '-'` |
| 5 | **GKS with letters** | "GKS enthält Buchstaben" | 15% | 90% | `not gks_text.isdigit()` after basic cleaning |

#### Priority 2: Domain-Specific Business Rules

| # | Check | Risk Factor Text | Weight | Confidence | Implementation |
|---|-------|------------------|--------|------------|----------------|
| 6 | **V-signal with Fahrtrichtung** | "V-Signal mit Richtung" | 10% | 100% | `anchor_text.startswith('V') and fahrtrichtung` |
| 7 | **Weichen_block not starting with W** | "Weichenblock ungültig" | 15% | 95% | `cls == 'weichen_block' and not anchor_text.startswith('W')` |
| 8 | **Very low uppercase ratio** | "Zu viele Kleinbuchstaben" | 10% | 75% | Signal IDs should be mostly uppercase |

#### Priority 3: Advanced Quality Checks

| # | Check | Risk Factor Text | Weight | Confidence | Implementation |
|---|-------|------------------|--------|------------|----------------|
| 9 | **Low digit count in coordinate** | "Koordinate zu kurz" | 10% | 85% | `sum(c.isdigit() for c in coord) < 3` |
| 10 | **Bracketed coord low conf** | "Eingeklammert, unsicher" | 15% | 85% | `'(' in coord_text and conf < 0.5` |
| 11 | **Simple coord low conf** | "Einfache Koord., unsicher" | 15% | 85% | `'(' not in coord_text and conf < 0.8` |

---

### For Data Validation (Comprehensive Post-OCR)

#### Priority 1: Format & Structure Validation

| # | Check Name | Category | Severity | Auto-Fix? | Confidence |
|---|-----------|----------|----------|-----------|------------|
| 1 | **check_empty_text_fields()** | missing_data | error | ❌ No | 100% |
| 2 | **check_multiple_spaces()** | format | warning | ✅ Yes (95%) | 95% |
| 3 | **check_coordinate_structure()** | format | error | ❌ No | 90% |
| 4 | **check_weichen_block_structure()** | format | error | ❌ No | 95% |
| 5 | **check_gks_enhanced()** | format | warning | ✅ Yes (90%) | 90% |

#### Priority 2: Business Rule Validation

| # | Check Name | Category | Severity | Auto-Fix? | Confidence |
|---|-----------|----------|----------|-----------|------------|
| 6 | **check_v_signal_rules()** | business_rule | warning | ❌ No | 100% |
| 7 | **check_haltepunkt_signal_duplicates()** | duplicate | warning | ❌ No | 100% |
| 8 | **check_coordinate_reuse()** | data_integrity | warning | ❌ No | 90% |

#### Priority 3: Advanced OCR Quality

| # | Check Name | Category | Severity | Auto-Fix? | Confidence |
|---|-----------|----------|----------|-----------|------------|
| 9 | **check_coordinate_quality()** | ocr_quality | warning | ❌ No | 85% |
| 10 | **check_character_types()** | format | warning | ✅ Partial | 85% |
| 11 | **check_uppercase_ratio()** | format | warning | ❌ No | 75% |

---

## 📝 Detailed Implementation Specs

### Quality Inspector - New Risk Factors

#### 1. Empty Text After Strip
```python
# In _calculate_risk_score(), add after Factor 2:

# Factor 5: Empty Text After Normalization (20% weight)
if cls in ['signal', 'gks_gesteuert', 'gks_festkodiert', 'weichen_block']:
    anchor_text = str(row.get('anchor_text', '')).strip()
    if not anchor_text:
        risk += 0.20
        factors.append('Leere Bezeichnung')
```

**Impact:** Catches OCR failures that result in empty strings
**User-friendly text:** "Leere Bezeichnung" = Empty label/name

---

#### 2. Multiple Spaces (Formatting Error)
```python
# Factor 6: Excessive Whitespace (5% weight)
coord_text = str(row.get('coord_text', ''))
anchor_text = str(row.get('anchor_text', ''))

if '  ' in coord_text or '  ' in anchor_text:  # Two or more spaces
    risk += 0.05
    factors.append('Formatierungsfehler')
```

**Impact:** Flags OCR artifacts (multiple spaces)
**User-friendly text:** "Formatierungsfehler" = Formatting error
**Auto-fix:** Can be auto-corrected to single space

---

#### 3. Coordinate Missing Decimal
```python
# Factor 7: Coordinate Without Decimal (15% weight)
if pd.notna(row.get('coord_text')):
    coord_text = str(row.get('coord_text', '')).strip()
    if coord_text and '.' not in coord_text:
        risk += 0.15
        factors.append('Koordinate ohne Komma')
```

**Impact:** Coordinates should always have decimal separator
**User-friendly text:** "Koordinate ohne Komma" = Coordinate without decimal
**Note:** Uses "Komma" (comma) because German uses comma as decimal separator

---

#### 4. Coordinate Not Starting with Digit
```python
# Factor 8: Invalid Coordinate Start (20% weight)
if pd.notna(row.get('coord_text')):
    coord_text = str(row.get('coord_text', '')).strip()
    if coord_text and not (coord_text[0].isdigit() or coord_text[0] == '-'):
        risk += 0.20
        factors.append('Ungültige Koordinate')
```

**Impact:** Coordinates MUST start with digit or minus sign
**User-friendly text:** "Ungültige Koordinate" = Invalid coordinate

---

#### 5. GKS with Letters
```python
# Factor 9: GKS Contains Letters (15% weight)
if cls in ['gks_gesteuert', 'gks_festkodiert']:
    gks_text = str(row.get('anchor_text', '')).strip()
    if gks_text:
        # Remove common OCR confusions first
        cleaned = gks_text.replace(' ', '').replace('-', '')
        if not cleaned.isdigit():
            risk += 0.15
            factors.append('GKS enthält Buchstaben')
```

**Impact:** GKS should be pure digits (3-4 digits)
**User-friendly text:** "GKS enthält Buchstaben" = GKS contains letters

---

#### 6. V-Signal with Fahrtrichtung (Business Rule)
```python
# Factor 10: V-Signal Business Rule Violation (10% weight)
if cls == 'signal':
    anchor_text = str(row.get('anchor_text', '')).strip().upper()
    fahrtrichtung = row.get('fahrtrichtung')

    if anchor_text.startswith('V') and pd.notna(fahrtrichtung):
        risk += 0.10
        factors.append('V-Signal mit Richtung')
```

**Impact:** Vorsignale (distant signals) shouldn't have direction
**User-friendly text:** "V-Signal mit Richtung" = V-signal with direction
**Domain rule:** Found in linking.py:687, pipelineworker.py:1029

---

#### 7. Weichen_Block Not Starting with W
```python
# Factor 11: Weichen Block Invalid (15% weight)
if cls == 'weichen_block':
    anchor_text = str(row.get('anchor_text', '')).strip().upper()
    if anchor_text and not anchor_text.startswith('W'):
        risk += 0.15
        factors.append('Weichenblock ungültig')
```

**Impact:** Weichen blocks MUST start with 'W'
**User-friendly text:** "Weichenblock ungültig" = Switch block invalid
**Found in:** ocr_engine.py:927, image_processing.py:12

---

#### 8. Very Low Uppercase Ratio
```python
# Factor 12: Low Uppercase Ratio in Signals (10% weight)
if cls == 'signal':
    anchor_text = str(row.get('anchor_text', '')).strip()
    if anchor_text:
        alpha_chars = [c for c in anchor_text if c.isalpha()]
        if alpha_chars:
            uppercase_ratio = sum(c.isupper() for c in alpha_chars) / len(alpha_chars)
            if uppercase_ratio < 0.6:  # Less than 60% uppercase
                risk += 0.10
                factors.append('Zu viele Kleinbuchstaben')
```

**Impact:** Signal IDs should be mostly uppercase
**User-friendly text:** "Zu viele Kleinbuchstaben" = Too many lowercase letters
**Found in:** ocr_engine.py:1723

---

#### 9. Low Digit Count in Coordinate
```python
# Factor 13: Too Few Digits in Coordinate (10% weight)
if pd.notna(row.get('coord_text')):
    coord_text = str(row.get('coord_text', '')).strip()
    digit_count = sum(c.isdigit() for c in coord_text)
    if digit_count < 3:
        risk += 0.10
        factors.append('Koordinate zu kurz')
```

**Impact:** Coordinates should have at least 3 digits
**User-friendly text:** "Koordinate zu kurz" = Coordinate too short
**Found in:** ocr_engine.py:694-716

---

#### 10. Bracketed Coordinate Low Confidence
```python
# Factor 14: Bracketed Coordinate with Low Confidence (15% weight)
if pd.notna(row.get('coord_text')):
    coord_text = str(row.get('coord_text', '')).strip()
    conf = row.get('conf', 1.0)

    if '(' in coord_text and ')' in coord_text:
        if conf < 0.5:
            risk += 0.15
            factors.append('Eingeklammert, unsicher')
```

**Impact:** Bracketed coordinates need at least 50% confidence
**User-friendly text:** "Eingeklammert, unsicher" = Bracketed, uncertain
**Found in:** ocr_engine.py:546

---

#### 11. Simple Coordinate Low Confidence
```python
# Factor 15: Simple Coordinate with Low Confidence (15% weight)
if pd.notna(row.get('coord_text')):
    coord_text = str(row.get('coord_text', '')).strip()
    conf = row.get('conf', 1.0)

    if '(' not in coord_text:  # Simple coordinate
        if conf < 0.8:
            risk += 0.15
            factors.append('Einfache Koord., unsicher')
```

**Impact:** Simple coordinates need at least 80% confidence
**User-friendly text:** "Einfache Koord., unsicher" = Simple coord., uncertain
**Found in:** ocr_engine.py:553

---

## 📋 Data Validation - New Checks

### 1. check_empty_text_fields()

```python
def check_empty_text_fields(self) -> List[ValidationIssue]:
    """
    Check for empty text fields after normalization.

    More strict than missing_coordinates - catches empty strings.
    """
    issues = []

    # Classes that MUST have text
    TEXT_REQUIRED = ['signal', 'gks_gesteuert', 'gks_festkodiert', 'weichen_block']

    for cls in TEXT_REQUIRED:
        df_class = self.df[self.df['cls'] == cls]

        for _, row in df_class.iterrows():
            anchor_text = str(row.get('anchor_text', '')).strip()

            if not anchor_text:
                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='error',
                    category='missing_data',
                    field='anchor_text',
                    message=f"{cls}: Bezeichnung ist leer (nach Bereinigung)",
                    current_value='',
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=1.0,
                    context={
                        'position': (float(row['xc']), float(row['yc'])),
                        'suggestion': 'Text wurde nicht erkannt oder ist nach Bereinigung leer',
                        'can_jump': True
                    }
                ))

    return issues
```

**Why:** More strict than existing missing check - catches empty strings after `.strip()`
**Confidence:** 100%

---

### 2. check_multiple_spaces()

```python
def check_multiple_spaces(self) -> List[ValidationIssue]:
    """
    Check for multiple consecutive spaces (OCR artifact).

    Auto-correctable: Can normalize to single space.
    """
    issues = []

    for _, row in self.df.iterrows():
        # Check anchor_text
        anchor_text = str(row.get('anchor_text', ''))
        if '  ' in anchor_text:  # Two or more spaces
            suggested = ' '.join(anchor_text.split())

            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='warning',
                category='format',
                field='anchor_text',
                message=f"{row['cls']}: Mehrere Leerzeichen in Bezeichnung",
                current_value=anchor_text,
                suggested_value=suggested,
                auto_correctable=True,
                confidence=0.95,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': f"'{anchor_text}' → '{suggested}'",
                    'can_jump': True
                }
            ))

        # Check coord_text
        coord_text = str(row.get('coord_text', ''))
        if '  ' in coord_text:
            suggested = ' '.join(coord_text.split())

            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='warning',
                category='format',
                field='coord_text',
                message=f"{row['cls']}: Mehrere Leerzeichen in Koordinate",
                current_value=coord_text,
                suggested_value=suggested,
                auto_correctable=True,
                confidence=0.95,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': f"'{coord_text}' → '{suggested}'",
                    'can_jump': True
                }
            ))

    return issues
```

**Why:** OCR often produces multiple spaces, already normalized in pipelineworker.py
**Confidence:** 95%
**Auto-fix:** Yes

---

### 3. check_coordinate_structure()

```python
def check_coordinate_structure(self) -> List[ValidationIssue]:
    """
    Check coordinate structure:
    1. Must start with digit or minus
    2. Must contain decimal dot
    3. Must have at least 3 digits
    """
    issues = []

    coords = self.df[self.df['coord_text'].notna()]

    for _, row in coords.iterrows():
        coord_text = str(row.get('coord_text', '')).strip()

        if not coord_text:
            continue

        # Check 1: Must start with digit or minus
        if not (coord_text[0].isdigit() or coord_text[0] == '-'):
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='error',
                category='format',
                field='coord_text',
                message=f"Koordinate startet nicht mit Ziffer: '{coord_text}'",
                current_value=coord_text,
                suggested_value=None,
                auto_correctable=False,
                confidence=0.95,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': 'Koordinaten müssen mit einer Ziffer oder "-" beginnen',
                    'can_jump': True
                }
            ))

        # Check 2: Must contain decimal dot
        if '.' not in coord_text:
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='error',
                category='format',
                field='coord_text',
                message=f"Koordinate ohne Dezimalpunkt: '{coord_text}'",
                current_value=coord_text,
                suggested_value=None,
                auto_correctable=False,
                confidence=0.90,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': 'Koordinaten sollten einen Dezimalpunkt haben (z.B. 15.492)',
                    'can_jump': True
                }
            ))

        # Check 3: Must have at least 3 digits
        digit_count = sum(c.isdigit() for c in coord_text)
        if digit_count < 3:
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='warning',
                category='format',
                field='coord_text',
                message=f"Koordinate hat nur {digit_count} Ziffern: '{coord_text}'",
                current_value=coord_text,
                suggested_value=None,
                auto_correctable=False,
                confidence=0.85,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': f'Koordinaten sollten mindestens 3 Ziffern haben (aktuell: {digit_count})',
                    'can_jump': True
                }
            ))

    return issues
```

**Why:** Combines 3 critical coordinate checks from ocr_engine.py
**Confidence:** 85-95% depending on check

---

### 4. check_weichen_block_structure()

```python
def check_weichen_block_structure(self) -> List[ValidationIssue]:
    """
    Check weichen_block structure:
    1. Must start with 'W'
    2. First line is block ID
    3. Subsequent lines are coordinates
    """
    issues = []

    weichen = self.df[self.df['cls'] == 'weichen_block']

    for _, row in weichen.iterrows():
        anchor_text = str(row.get('anchor_text', '')).strip()

        if not anchor_text:
            continue

        # Check: Must start with 'W'
        if not anchor_text.upper().startswith('W'):
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='error',
                category='format',
                field='anchor_text',
                message=f"Weichenblock startet nicht mit 'W': '{anchor_text}'",
                current_value=anchor_text,
                suggested_value=None,
                auto_correctable=False,
                confidence=0.95,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': 'Weichenblöcke müssen mit "W" beginnen (z.B. WAHR921, WA12)',
                    'can_jump': True
                }
            ))

    return issues
```

**Why:** Critical business rule from ocr_engine.py:927 and image_processing.py
**Confidence:** 95%

---

### 5. check_gks_enhanced()

```python
def check_gks_enhanced(self) -> List[ValidationIssue]:
    """
    Enhanced GKS validation with character substitution suggestions.

    Checks for common OCR confusions (O→0, I→1) and suggests fixes.
    """
    issues = []

    GKS_PATTERN = re.compile(r'^\d{3,4}$')

    gks_rows = self.df[self.df['cls'].isin(['gks_gesteuert', 'gks_festkodiert'])]

    for _, row in gks_rows.iterrows():
        gks_text = str(row.get('anchor_text', '')).strip()

        if not gks_text:
            continue

        # Apply character substitution (like signals do)
        trans = str.maketrans({
            'O': '0', 'o': '0',
            'I': '1', 'l': '1', 'L': '1',
            'S': '5',
            'B': '8',
            'Z': '2'
        })
        suggested = gks_text.translate(trans)
        suggested = re.sub(r'\D', '', suggested)  # Remove remaining non-digits

        # Check if it matches pattern after substitution
        if GKS_PATTERN.match(suggested) and suggested != gks_text:
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='warning',
                category='format',
                field='anchor_text',
                message=f"GKS: OCR-Verwechslung erkannt",
                current_value=gks_text,
                suggested_value=suggested,
                auto_correctable=True,
                confidence=0.90,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': f"'{gks_text}' → '{suggested}' (O→0, I→1, etc.)",
                    'can_jump': True
                }
            ))
        elif not GKS_PATTERN.match(suggested):
            # Still doesn't match after substitution
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='error',
                category='format',
                field='anchor_text',
                message=f"GKS: Ungültiges Format (muss 3-4 Ziffern sein)",
                current_value=gks_text,
                suggested_value=suggested if suggested != gks_text else None,
                auto_correctable=False,
                confidence=0.80,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': f'GKS muss 3-4 Ziffern haben (aktuell: "{gks_text}")',
                    'can_jump': True
                }
            ))

    return issues
```

**Why:** Enhances existing GKS check with character substitution from signals
**Confidence:** 90%
**Auto-fix:** Yes (for O→0, I→1 confusions)

---

### 6. check_v_signal_rules()

```python
def check_v_signal_rules(self) -> List[ValidationIssue]:
    """
    Check V-signal business rules:
    V-signals (Vorsignale) should NOT have Fahrtrichtung.
    """
    issues = []

    signals = self.df[self.df['cls'] == 'signal']

    for _, row in signals.iterrows():
        anchor_text = str(row.get('anchor_text', '')).strip().upper()
        fahrtrichtung = row.get('fahrtrichtung')

        if anchor_text.startswith('V') and pd.notna(fahrtrichtung):
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='warning',
                category='business_rule',
                field='fahrtrichtung',
                message=f"V-Signal '{anchor_text}' hat Fahrtrichtung '{fahrtrichtung}' (ungewöhnlich)",
                current_value=fahrtrichtung,
                suggested_value=None,
                auto_correctable=False,
                confidence=1.0,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': 'Vorsignale (V-Signale) haben normalerweise keine Fahrtrichtung',
                    'can_jump': True,
                    'business_rule': 'V-signals are skipped in Fahrtrichtung detection (linking.py:687)'
                }
            ))

    return issues
```

**Why:** Domain-specific business rule from linking.py:687, pipelineworker.py:1029
**Confidence:** 100%

---

### 7. check_haltepunkt_signal_duplicates()

```python
def check_haltepunkt_signal_duplicates(self) -> List[ValidationIssue]:
    """
    Check for signals that appear both as haltepunkt-linked AND standalone.

    This shouldn't happen based on pipelineworker.py logic.
    """
    issues = []

    # Find haltepunkt entries with signal names
    haltepunkte = self.df[self.df['cls'] == 'haltepunkt']

    for _, halt_row in haltepunkte.iterrows():
        halt_text = str(halt_row.get('anchor_text', ''))

        # Extract signal name from "haltepunkt N (SIGNAL_NAME)"
        import re
        match = re.search(r'\(([^)]+)\)$', halt_text)

        if match:
            signal_name = match.group(1).strip()

            # Check if this signal also exists as standalone
            standalone_signals = self.df[
                (self.df['cls'] == 'signal') &
                (self.df['anchor_text'] == signal_name) &
                (self.df['page'] == halt_row['page'])
            ]

            if len(standalone_signals) > 0:
                issues.append(ValidationIssue(
                    row_id=halt_row['row_id'],
                    severity='warning',
                    category='duplicate',
                    field='anchor_text',
                    message=f"Signal '{signal_name}' erscheint als Haltepunkt UND eigenständig",
                    current_value=halt_text,
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=1.0,
                    context={
                        'position': (float(halt_row['xc']), float(halt_row['yc'])),
                        'suggestion': 'Signal sollte entweder Haltepunkt-verknüpft ODER eigenständig sein',
                        'can_jump': True,
                        'duplicate_row_ids': standalone_signals['row_id'].tolist()
                    }
                ))

    return issues
```

**Why:** Business logic from pipelineworker.py:524-527 (haltepunkt-referenced signals are skipped)
**Confidence:** 100%

---

### 8. check_coordinate_reuse()

```python
def check_coordinate_reuse(self) -> List[ValidationIssue]:
    """
    Check if same coordinate text is linked to multiple different elements.

    Special case: Sverbinder coordinates should be exclusive.
    """
    issues = []

    # Build map: coord_text -> [row_ids]
    coord_map = {}

    for _, row in self.df.iterrows():
        coord_text = str(row.get('coord_text', '')).strip()

        if coord_text:
            if coord_text not in coord_map:
                coord_map[coord_text] = []
            coord_map[coord_text].append({
                'row_id': row['row_id'],
                'cls': row['cls'],
                'anchor_text': row.get('anchor_text', ''),
                'position': (float(row['xc']), float(row['yc']))
            })

    # Check for reuse
    for coord_text, usages in coord_map.items():
        if len(usages) > 1:
            # Check if sverbinder is involved
            has_sverbinder = any(u['cls'] == 'sverbinder' for u in usages)

            if has_sverbinder:
                # Sverbinder coordinates should be exclusive
                severity = 'warning'
                message = f"Koordinate '{coord_text}' wird von Sverbinder UND anderen Elementen verwendet"
            else:
                # Other cases might be legitimate
                severity = 'info'
                message = f"Koordinate '{coord_text}' wird von {len(usages)} Elementen geteilt"

            # Report on first usage
            first_usage = usages[0]
            other_classes = [u['cls'] for u in usages[1:]]

            issues.append(ValidationIssue(
                row_id=first_usage['row_id'],
                severity=severity,
                category='data_integrity',
                field='coord_text',
                message=message,
                current_value=coord_text,
                suggested_value=None,
                auto_correctable=False,
                confidence=0.90,
                context={
                    'position': first_usage['position'],
                    'suggestion': f"Diese Koordinate wird auch verwendet von: {', '.join(other_classes)}",
                    'can_jump': True,
                    'shared_with_row_ids': [u['row_id'] for u in usages[1:]],
                    'has_sverbinder': has_sverbinder
                }
            ))

    return issues
```

**Why:** Business logic from pipelineworker.py:579-597 (sverbinder coordinate blacklisting)
**Confidence:** 90%

---

### 9. check_coordinate_quality()

```python
def check_coordinate_quality(self) -> List[ValidationIssue]:
    """
    Check coordinate OCR quality based on confidence thresholds:
    - Bracketed coordinates: need ≥50% confidence
    - Simple coordinates: need ≥80% confidence
    """
    issues = []

    coords = self.df[self.df['coord_text'].notna()]

    for _, row in coords.iterrows():
        coord_text = str(row.get('coord_text', '')).strip()
        conf = row.get('conf', 1.0)

        if not coord_text:
            continue

        # Check if bracketed
        has_brackets = '(' in coord_text and ')' in coord_text

        if has_brackets and conf < 0.50:
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='warning',
                category='ocr_quality',
                field='conf',
                message=f"Eingeklammerte Koordinate mit niedriger Konfidenz: {conf:.0%}",
                current_value=str(conf),
                suggested_value=None,
                auto_correctable=False,
                confidence=0.85,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': f'Eingeklammerte Koordinaten sollten ≥50% Konfidenz haben (aktuell: {conf:.0%})',
                    'can_jump': True,
                    'coord_text': coord_text
                }
            ))
        elif not has_brackets and conf < 0.80:
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='warning',
                category='ocr_quality',
                field='conf',
                message=f"Einfache Koordinate mit niedriger Konfidenz: {conf:.0%}",
                current_value=str(conf),
                suggested_value=None,
                auto_correctable=False,
                confidence=0.85,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'suggestion': f'Einfache Koordinaten sollten ≥80% Konfidenz haben (aktuell: {conf:.0%})',
                    'can_jump': True,
                    'coord_text': coord_text
                }
            ))

    return issues
```

**Why:** Different thresholds from ocr_engine.py:546-553
**Confidence:** 85%

---

## 📊 Implementation Priority Summary

### Immediate (High Impact, Low Effort):
1. ✅ Empty text fields check
2. ✅ Multiple spaces normalization (auto-fix)
3. ✅ V-signal business rule
4. ✅ Coordinate structure checks (start with digit, has dot)

### Short-term (Medium Effort):
5. ✅ Weichen_block structure validation
6. ✅ Enhanced GKS with char substitution
7. ✅ Coordinate quality thresholds

### Medium-term (More Complex):
8. ✅ Haltepunkt signal duplicate detection
9. ✅ Coordinate reuse checking
10. ✅ Character type validation
11. ✅ Uppercase ratio checks

---

## 🎯 Expected Impact

### Quality Inspector Improvements:
- **11 new risk factors** (from 5 to 16 total)
- **More granular risk assessment** (better prioritization)
- **Domain-specific rules** (V-signals, weichen_blocks)
- **Better user guidance** with clear German labels

### Data Validation Improvements:
- **9 new checks** (from 9 to 18 total)
- **3 with auto-correction** (multiple spaces, enhanced GKS, char types)
- **3 business rule checks** (V-signals, haltepunkt, sverbinder)
- **Better OCR quality assessment** (coordinate thresholds)

### User Benefits:
- ✅ Catch more OCR errors automatically
- ✅ Better prioritization of manual review
- ✅ More auto-correction opportunities
- ✅ Domain-specific validation (railway rules)
- ✅ Clearer error messages in German

---

**Last Updated:** 2026-01-06
**Based on:** Deep analysis of pipelineworker.py, ocr_engine.py, linking.py, image_processing.py
**Implementation Status:** Ready for implementation

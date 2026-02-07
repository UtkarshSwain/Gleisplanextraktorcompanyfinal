# Manual Correction Action Mapping

**Mapping validation issues to manual correction methods**

Based on available tools in workspace_widget.py:
- Manuelles OCR (Horizontal)
- Manuelles OCR (Angular)
- Koordinate manuell verknüpfen
- Bbox resize
- Manual table edit
- Delete detection

---

## 🎯 Manual Action Types

```python
MANUAL_ACTIONS = {
    'manual_ocr_horizontal': {
        'button': 'btn_manual_ocr',
        'label': '📏 Manuelles OCR (Horizontal)',
        'description': 'Text horizontal neu erkennen',
        'steps': '1. Element auswählen\n2. Rechteck auf dem Bild ziehen'
    },
    'manual_ocr_angular': {
        'button': 'btn_manual_ocr_angular',
        'label': '📐 Manuelles OCR (Angular)',
        'description': 'Text schräg neu erkennen',
        'steps': '1. Element auswählen\n2. Basislinie zeichnen\n3. Höhe festlegen'
    },
    'manual_link': {
        'button': 'btn_manual_link',
        'label': '📌 Koordinate manuell verknüpfen',
        'description': 'Koordinate manuell zuordnen',
        'steps': '1. Ankerelement klicken\n2. Koordinate klicken'
    },
    'bbox_resize': {
        'button': None,  # Direct interaction on image
        'label': '🔲 Erkennungsbereich anpassen',
        'description': 'Bounding Box anpassen',
        'steps': '1. Element auswählen\n2. Ecken/Kanten ziehen'
    },
    'manual_edit': {
        'button': None,  # Direct table editing
        'label': '✏️ Text manuell korrigieren',
        'description': 'Direkt in Tabelle bearbeiten',
        'steps': '1. Zelle doppelklicken\n2. Text eingeben'
    },
    'delete': {
        'button': None,  # Context menu or delete key
        'label': '🗑️ Erkennung löschen',
        'description': 'Element entfernen (Falscherkennung)',
        'steps': '1. Element auswählen\n2. Entf-Taste oder Rechtsklick → Löschen'
    },
    'review': {
        'button': None,
        'label': '🔍 Manuell prüfen',
        'description': 'Manuelle Überprüfung erforderlich',
        'steps': '1. Element im Plan ansehen\n2. Korrektur entscheiden'
    }
}
```

---

## 📋 Validation Issue → Manual Action Mapping

| Validation Issue | Auto-Fix? | Manual Action | Why This Action? |
|-----------------|-----------|---------------|------------------|
| **Empty text after strip** | ❌ | `manual_ocr_horizontal` or `delete` | OCR failed → Re-recognize or remove if false positive |
| **Weichen not starting with W** | ❌ | `manual_ocr_horizontal` or `bbox_resize` | Wrong text → Re-OCR or adjust detection area |
| **Coordinate invalid start** | ✅ Partial | `manual_ocr_horizontal` | If auto-fix fails, re-recognize |
| **Coordinate missing decimal** | ❌ | `manual_ocr_horizontal` or `manual_edit` | OCR error → Re-recognize or edit |
| **Coordinate too few digits** | ❌ | `bbox_resize` or `manual_ocr_horizontal` | Detection area too small or OCR incomplete |
| **GKS with letters** | ✅ YES | `manual_edit` | If auto-fix fails, manual edit |
| **Multiple spaces** | ✅ YES | `manual_edit` | If auto-fix fails, manual edit |
| **Missing coordinate** | ❌ | `manual_link` | No coordinate linked → Manual linking |
| **V-signal with Fahrtrichtung** | ❌ | `manual_edit` or `review` | Business rule violation → Edit or review |
| **Low confidence** | ❌ | `manual_ocr_horizontal` or `bbox_resize` | Poor OCR → Re-recognize or adjust area |

---

## 🔧 Implementation: ValidationIssue with Suggested Actions

### Enhanced ValidationIssue Context

```python
# Add to context dict in ValidationIssue
context = {
    'position': (float(row['xc']), float(row['yc'])),  # For jumping
    'can_jump': True,  # Enable jump button

    # ✅ NEW: Manual correction suggestions
    'suggested_action': 'manual_ocr_horizontal',  # Primary action
    'alternative_actions': ['bbox_resize', 'delete'],  # Alternative actions
    'action_description': 'Text wurde nicht erkannt. Verwenden Sie "Manuelles OCR (Horizontal)" um den Text neu zu erkennen.',
    'action_steps': MANUAL_ACTIONS['manual_ocr_horizontal']['steps'],

    # Additional context
    'suggestion': 'Detailed explanation of the issue...',
    'element_type': row['cls'],
}
```

---

## 📝 Implementation Examples

### 1. Empty Text Fields (No Auto-Fix)

```python
def check_empty_text_fields(self) -> List[ValidationIssue]:
    """Check for empty text fields with manual correction suggestions"""
    issues = []

    TEXT_REQUIRED = ['signal', 'gks_gesteuert', 'gks_festkodiert', 'weichen_block']

    for cls in TEXT_REQUIRED:
        df_class = self.df[self.df['cls'] == cls]

        for _, row in df_class.iterrows():
            anchor_text = str(row.get('anchor_text', '')).strip()

            if not anchor_text:
                # Determine suggested action based on element type
                if cls == 'weichen_block':
                    # Weichen blocks often rotated
                    suggested = 'manual_ocr_angular'
                    alternatives = ['manual_ocr_horizontal', 'bbox_resize', 'delete']
                    action_desc = 'Weichenblock-Text wurde nicht erkannt. Versuchen Sie "Manuelles OCR (Angular)" für schrägen Text.'
                else:
                    # Most elements are horizontal
                    suggested = 'manual_ocr_horizontal'
                    alternatives = ['bbox_resize', 'delete']
                    action_desc = f'{cls}-Text wurde nicht erkannt. Verwenden Sie "Manuelles OCR (Horizontal)" um den Text neu zu erkennen.'

                issues.append(ValidationIssue(
                    row_id=row['row_id'],
                    severity='error',
                    category='missing_data',
                    field='anchor_text',
                    message=f"{cls}: Bezeichnung ist leer (OCR fehlgeschlagen)",
                    current_value='',
                    suggested_value=None,
                    auto_correctable=False,
                    confidence=1.0,
                    context={
                        'position': (float(row['xc']), float(row['yc'])),
                        'can_jump': True,

                        # ✅ Manual correction suggestions
                        'suggested_action': suggested,
                        'alternative_actions': alternatives,
                        'action_description': action_desc,
                        'action_steps': MANUAL_ACTIONS[suggested]['steps'],

                        'suggestion': 'Text ist leer. Entweder OCR fehlgeschlagen oder Falscherkennung.',
                        'element_type': cls
                    }
                ))

    return issues
```

---

### 2. Weichen Block Structure (No Auto-Fix)

```python
def check_weichen_block_structure(self) -> List[ValidationIssue]:
    """Check weichen_block structure with manual correction suggestions"""
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
                    'can_jump': True,

                    # ✅ Manual correction suggestions
                    'suggested_action': 'manual_ocr_angular',  # Weichen often rotated
                    'alternative_actions': ['manual_ocr_horizontal', 'bbox_resize', 'manual_edit'],
                    'action_description': 'Weichenblock muss mit "W" beginnen. Verwenden Sie "Manuelles OCR (Angular)" für schrägen Text oder "Manuelles OCR (Horizontal)".',
                    'action_steps': MANUAL_ACTIONS['manual_ocr_angular']['steps'],

                    'suggestion': 'Weichenblöcke müssen mit "W" beginnen (z.B. WAHR921, WA12). Möglicherweise wurde der Text falsch erkannt.',
                    'element_type': 'weichen_block',
                    'expected_pattern': 'W[A-ZÄÖÜ]+[0-9]+'
                }
            ))

    return issues
```

---

### 3. Coordinate Structure (Partial Auto-Fix)

```python
def check_coordinate_structure(self) -> List[ValidationIssue]:
    """
    Check coordinate structure with auto-fix for leading chars,
    manual suggestions for others
    """
    issues = []

    coords = self.df[self.df['coord_text'].notna()]

    for _, row in coords.iterrows():
        coord_text = str(row.get('coord_text', '')).strip()

        if not coord_text:
            continue

        # Check 1: Must start with digit or minus
        if not (coord_text[0].isdigit() or coord_text[0] == '-'):
            # Try auto-fix: Remove leading non-digit chars
            suggested = re.sub(r'^[^0-9-]+', '', coord_text)

            # Validate the fix
            can_auto_fix = False
            if suggested and (suggested[0].isdigit() or suggested[0] == '-') and '.' in suggested:
                can_auto_fix = True
                confidence = 0.80
                action_desc = f'Führende Zeichen entfernen: "{coord_text}" → "{suggested}"'
                manual_action = 'manual_edit'  # Fallback if user rejects
            else:
                confidence = 0.0
                action_desc = 'Koordinate startet nicht mit Ziffer. Verwenden Sie "Manuelles OCR (Horizontal)" um die Koordinate neu zu erkennen.'
                manual_action = 'manual_ocr_horizontal'

            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='error',
                category='format',
                field='coord_text',
                message=f"Koordinate startet nicht mit Ziffer: '{coord_text}'",
                current_value=coord_text,
                suggested_value=suggested if can_auto_fix else None,
                auto_correctable=can_auto_fix,
                confidence=confidence,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'can_jump': True,

                    # ✅ Manual correction suggestions (if auto-fix fails/rejected)
                    'suggested_action': manual_action,
                    'alternative_actions': ['bbox_resize', 'manual_edit'],
                    'action_description': action_desc,
                    'action_steps': MANUAL_ACTIONS[manual_action]['steps'],

                    'suggestion': 'Koordinaten müssen mit einer Ziffer oder "-" beginnen',
                    'element_type': row.get('cls', 'coordinate')
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
                    'can_jump': True,

                    # ✅ Manual correction suggestions
                    'suggested_action': 'manual_ocr_horizontal',
                    'alternative_actions': ['bbox_resize', 'manual_edit'],
                    'action_description': 'Koordinate hat keinen Dezimalpunkt. Verwenden Sie "Manuelles OCR (Horizontal)" oder korrigieren Sie manuell.',
                    'action_steps': MANUAL_ACTIONS['manual_ocr_horizontal']['steps'],

                    'suggestion': 'Koordinaten sollten einen Dezimalpunkt haben (z.B. 15.492)',
                    'element_type': row.get('cls', 'coordinate')
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
                    'can_jump': True,

                    # ✅ Manual correction suggestions
                    'suggested_action': 'bbox_resize',  # Detection area likely too small
                    'alternative_actions': ['manual_ocr_horizontal'],
                    'action_description': f'Koordinate hat nur {digit_count} Ziffern. Vergrößern Sie die Erkennungsfläche mit "Bbox Resize" oder verwenden Sie "Manuelles OCR".',
                    'action_steps': MANUAL_ACTIONS['bbox_resize']['steps'],

                    'suggestion': f'Koordinaten sollten mindestens 3 Ziffern haben (aktuell: {digit_count}). Möglicherweise wurde nicht der gesamte Text erkannt.',
                    'element_type': row.get('cls', 'coordinate'),
                    'digit_count': digit_count
                }
            ))

    return issues
```

---

### 4. Missing Coordinates (No Auto-Fix)

```python
def check_missing_coordinates(self) -> List[ValidationIssue]:
    """Check for anchors without coordinates - suggest manual linking"""
    issues = []

    LINKABLE_CLASSES = ['signal', 'gks_gesteuert', 'gks_festkodiert', 'isolierstoß']

    for cls in LINKABLE_CLASSES:
        df_class = self.df[self.df['cls'] == cls]

        missing = df_class[df_class['coord_text'].isna() | (df_class['coord_text'] == '')]

        for _, row in missing.iterrows():
            issues.append(ValidationIssue(
                row_id=row['row_id'],
                severity='error',
                category='missing_data',
                field='coord_text',
                message=f"{cls} '{row.get('anchor_text', '?')}': Keine Koordinate verknüpft",
                current_value=None,
                suggested_value=None,
                auto_correctable=False,
                confidence=1.0,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'can_jump': True,

                    # ✅ Manual correction suggestions
                    'suggested_action': 'manual_link',  # Primary: Manual linking
                    'alternative_actions': ['review'],  # Maybe coordinate doesn't exist
                    'action_description': f'{cls} hat keine Koordinate. Verwenden Sie "Koordinate manuell verknüpfen" um eine Koordinate zuzuordnen.',
                    'action_steps': MANUAL_ACTIONS['manual_link']['steps'],

                    'suggestion': f'{cls}-Elemente sollten mit einer Koordinate verknüpft sein. Entweder wurde die automatische Verknüpfung nicht gefunden, oder es gibt keine Koordinate im Plan.',
                    'element_type': cls,
                    'anchor_text': row.get('anchor_text', '?')
                }
            ))

    return issues
```

---

### 5. V-Signal Business Rule (No Auto-Fix)

```python
def check_v_signal_rules(self) -> List[ValidationIssue]:
    """Check V-signal business rules with review suggestion"""
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
                suggested_value=None,  # Could suggest None, but let user decide
                auto_correctable=False,
                confidence=1.0,
                context={
                    'position': (float(row['xc']), float(row['yc'])),
                    'can_jump': True,

                    # ✅ Manual correction suggestions
                    'suggested_action': 'review',  # User needs to decide
                    'alternative_actions': ['manual_edit'],  # Could manually remove Fahrtrichtung
                    'action_description': f'V-Signal "{anchor_text}" hat Fahrtrichtung "{fahrtrichtung}". Vorsignale haben normalerweise keine Fahrtrichtung. Prüfen Sie, ob dies korrekt ist.',
                    'action_steps': 'Überprüfen Sie das Signal im Plan und entscheiden Sie:\n- Ist es wirklich ein Vorsignal? → Fahrtrichtung löschen\n- Ist es ein Hauptsignal? → Signalname korrigieren',

                    'suggestion': 'Vorsignale (V-Signale) haben normalerweise keine Fahrtrichtung. Dies könnte ein Fehler in der Erkennung oder Verknüpfung sein.',
                    'element_type': 'signal',
                    'signal_name': anchor_text,
                    'business_rule': 'V-signals are skipped in Fahrtrichtung detection (linking.py:687)'
                }
            ))

    return issues
```

---

## 🎨 UI Enhancement: Action Buttons in Validation Dialog

### Add to validation_dialog2.py

```python
def _populate_issues_table(self, table: QtWidgets.QTableWidget, issues: List[ValidationIssue]):
    """Populate issues table with action buttons"""

    table.setRowCount(len(issues))
    table.setColumnCount(9)  # ✅ Added +1 column for action button

    table.setHorizontalHeaderLabels([
        "Dringlichkeit", "Kategorie", "Typ", "ID", "Feld",
        "Problem-Beschreibung", "Aktueller Wert", "Prüfbedarf",
        "🔧 Aktion"  # ✅ NEW COLUMN
    ])

    for row_idx, issue in enumerate(issues):
        # ... existing column population ...

        # ✅ NEW: Action button column
        if issue.context and issue.context.get('suggested_action'):
            action_widget = self._create_action_button(issue)
            table.setCellWidget(row_idx, 8, action_widget)
        else:
            table.setItem(row_idx, 8, QtWidgets.QTableWidgetItem('-'))

def _create_action_button(self, issue: ValidationIssue) -> QtWidgets.QWidget:
    """Create action button/menu for manual correction"""

    widget = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(widget)
    layout.setContentsMargins(2, 2, 2, 2)

    suggested = issue.context.get('suggested_action')
    alternatives = issue.context.get('alternative_actions', [])

    # Primary action button
    if suggested:
        action_info = MANUAL_ACTIONS.get(suggested, {})
        btn = QtWidgets.QPushButton(action_info.get('label', suggested))
        btn.setToolTip(issue.context.get('action_description', ''))
        btn.clicked.connect(lambda: self._trigger_manual_action(issue, suggested))
        layout.addWidget(btn)

    # Alternative actions menu
    if alternatives:
        menu_btn = QtWidgets.QPushButton("⋮")
        menu_btn.setFixedWidth(30)
        menu_btn.setToolTip("Weitere Korrektur-Optionen")

        menu = QtWidgets.QMenu()
        for alt_action in alternatives:
            action_info = MANUAL_ACTIONS.get(alt_action, {})
            action = menu.addAction(action_info.get('label', alt_action))
            action.triggered.connect(lambda checked, a=alt_action: self._trigger_manual_action(issue, a))

        menu_btn.setMenu(menu)
        layout.addWidget(menu_btn)

    return widget

def _trigger_manual_action(self, issue: ValidationIssue, action: str):
    """
    Trigger manual correction action

    Actions:
    - manual_ocr_horizontal: Jump to element, show instruction to use OCR button
    - manual_ocr_angular: Jump to element, show instruction
    - manual_link: Jump to element, show instruction to use link button
    - bbox_resize: Jump to element, show instruction
    - manual_edit: Jump to element, focus table cell
    - review: Jump to element
    - delete: Jump to element, ask confirmation
    """

    action_info = MANUAL_ACTIONS.get(action, {})

    # 1. Jump to the problematic element
    if issue.context and issue.context.get('can_jump'):
        position = issue.context.get('position')
        if position:
            self.jump_to_detection.emit(issue.row_id, position)

    # 2. Show instruction dialog
    msg = QtWidgets.QMessageBox(self)
    msg.setWindowTitle(f"Manuelle Korrektur: {action_info.get('label', action)}")
    msg.setIcon(QtWidgets.QMessageBox.Information)

    description = issue.context.get('action_description', action_info.get('description', ''))
    steps = issue.context.get('action_steps', action_info.get('steps', ''))

    msg.setText(f"<b>{description}</b>")
    msg.setInformativeText(f"<pre>{steps}</pre>")

    # 3. For certain actions, provide additional functionality
    if action == 'delete':
        msg.setIcon(QtWidgets.QMessageBox.Warning)
        msg.setText(f"<b>Element löschen?</b>")
        msg.setInformativeText(f"Möchten Sie dieses Element wirklich löschen?\n\n{issue.message}")
        msg.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)

        if msg.exec_() == QtWidgets.QMessageBox.Yes:
            # Emit signal to parent to delete element
            # (parent workspace should handle this)
            pass
    elif action in ['manual_ocr_horizontal', 'manual_ocr_angular', 'manual_link']:
        # Show instruction and highlight the button
        msg.setInformativeText(
            f"{steps}\n\n"
            f"<b>Hinweis:</b> Klicken Sie auf den Button '{action_info.get('label')}' "
            f"in der Werkzeugleiste, um fortzufahren."
        )
        msg.exec_()
    else:
        msg.exec_()
```

---

## 📊 Summary: Complete Mapping

| Check | Auto-Fix | Manual Action | Button Label | When to Use |
|-------|----------|---------------|--------------|-------------|
| Empty text | ❌ | `manual_ocr_horizontal` | 📏 Manuelles OCR (Horizontal) | After auto-fix fails or for initial OCR failure |
| Weichen not W | ❌ | `manual_ocr_angular` | 📐 Manuelles OCR (Angular) | Weichen blocks often rotated |
| Coord invalid start | ✅ 80% | `manual_ocr_horizontal` | 📏 Manuelles OCR (Horizontal) | If auto-fix rejected/failed |
| Coord no decimal | ❌ | `manual_ocr_horizontal` | 📏 Manuelles OCR (Horizontal) | OCR didn't recognize full number |
| Coord few digits | ❌ | `bbox_resize` | 🔲 Erkennungsbereich anpassen | Detection area too small |
| GKS letters | ✅ 90% | `manual_edit` | ✏️ Text manuell korrigieren | If auto-fix fails |
| Multiple spaces | ✅ 95% | `manual_edit` | ✏️ Text manuell korrigieren | If auto-fix fails |
| Missing coord | ❌ | `manual_link` | 📌 Koordinate manuell verknüpfen | No auto-linking possible |
| V-signal rule | ❌ | `review` | 🔍 Manuell prüfen | Business decision needed |
| Low confidence | ❌ | `manual_ocr_horizontal` | 📏 Manuelles OCR (Horizontal) | Poor OCR quality |

---

**Last Updated:** 2026-01-06
**Status:** Ready for implementation
**UI Enhancement:** Action buttons in validation dialog with instructions

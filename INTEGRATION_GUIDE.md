# OCR Adjustment Dialog Integration Guide

This guide explains how the new OCR adjustment system integrates with the workspace.

## Files Created

1. `ui/ocr_adjustment_dialog.py` - Contains three classes:
   - `OCRAdjustmentTracker` - Tracks and learns from user adjustments
   - `OCRAdjustmentDialog` - Visual preview dialog with before/after
   - `AutoLearningSuggestionDialog` - Smart suggestions after pattern detection

## Integration Points

### 1. workspace_widget.py Modifications Needed

**Add import (line ~22):**
```python
from ui.ocr_adjustment_dialog import OCRAdjustmentDialog, OCRAdjustmentTracker, AutoLearningSuggestionDialog
```

**Add tracker instance in __init__ (line ~128):**
```python
# OCR adjustment tracking for auto-learning
self.ocr_adjustment_tracker = OCRAdjustmentTracker()
```

### 2. Modify on_ocr_bbox_resized Method

The current `on_ocr_bbox_resized` method (line ~2433) needs to:
1. Calculate adjustment delta (offset_x, offset_y, width_delta, height_delta)
2. Run OCR on new region
3. Show OCRAdjustmentDialog with before/after preview
4. Based on user choice:
   - Apply to current instance only
   - Apply to all instances of same symbol class
   - Save to template for future plans

### 3. Helper Methods to Add

Three new methods need to be added to WorkspaceWidget class:

1. `_apply_ocr_adjustment_to_rows(row_ids, offset_x, offset_y, width_delta, height_delta)`
   - Applies adjustment to specified rows
   - Re-runs OCR on each
   - Updates tree and graphics

2. `_save_ocr_adjustment_to_template(symbol_class, offset_x, offset_y, width_delta, height_delta)`
   - Saves adjustment to SymbolDefinition.text_region_offset
   - Uses NewSymbolDetector to persist

3. `_show_auto_learning_suggestion(symbol_class)`
   - Shows suggestion dialog after 3+ similar adjustments
   - If accepted, saves to template

## How It Works

### User Flow:

1. User resizes OCR region bbox
2. System calculates adjustment (how much it moved/changed)
3. Dialog shows:
   - Before/After preview images
   - Old OCR text vs New OCR text
   - Adjustment details in pixels
4. User chooses:
   - ☐ Apply to all instances in current plan
   - ☐ Save to template (for future plans)
5. System applies adjustment and records it for learning
6. After 3 adjustments in same direction, system suggests making it permanent

### Auto-Learning:

- Tracks all manual adjustments
- After 3+ adjustments, calculates average offset
- Shows suggestion dialog: "I noticed you often adjust [symbol] by X pixels. Make this automatic?"
- If accepted, saves to template permanently

## Testing

1. Load a plan with template-matched symbols
2. Resize an OCR region
3. Dialog should appear with before/after preview
4. Choose options and apply
5. Verify adjustment is applied
6. Resize 2 more times in similar direction
7. Suggestion dialog should appear offering to make it permanent

## Configuration Storage

- **Adjustments log**: `config/ocr_adjustments.json`
- **Template settings**: `custom_symbols.json` (text_region_offset field)

## Notes

- Works only for template-matched symbols (custom symbols)
- YOLO-detected symbols don't have adjustable OCR regions (they use different OCR methods)
- Bilingual UI (German/English) for train technicians

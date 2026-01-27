# OCR Adjustment System - Complete Implementation

## ✅ FINAL - FULLY INTEGRATED

This document describes the complete OCR adjustment system with visual preview and auto-learning for template matching symbols.

---

## 🎯 What Was Implemented

### **Option B UI + Auto-Learning Idea 1**

A complete system for adjusting OCR regions on template-matched symbols with:
- Visual before/after preview dialog
- Multiple application scopes (single/all/template)
- Auto-learning that suggests improvements after detecting patterns
- Bilingual German/English interface for train technicians

---

## 📁 Files Modified/Created

### Created:
1. **`ui/ocr_adjustment_dialog.py`** (599 lines)
   - `OCRAdjustmentTracker`: Tracks adjustments, learns patterns
   - `OCRAdjustmentDialog`: Visual preview dialog with before/after
   - `AutoLearningSuggestionDialog`: Smart suggestions after 3+ adjustments

2. **`INTEGRATION_GUIDE.md`**: Technical integration documentation
3. **`OCR_ADJUSTMENT_SYSTEM.md`**: This file - user guide

### Modified:
1. **`ui/workspace_widget.py`**
   - Added imports for dialog classes
   - Added `OCRAdjustmentTracker` instance
   - Completely rewrote `on_ocr_bbox_resized()` method
   - Added 3 new helper methods

---

## 🎨 User Interface

### **OCR Adjustment Dialog** (Shown when resizing OCR region)

```
┌────────────────────────────────────────────────┐
│  OCR-Region anpassen (Adjust OCR Region)       │
├────────────────────────────────────────────────┤
│  Symbol: weichen_left    Gefunden: 12 Instanzen│
│                                                │
│  ┌─────────────┐    ┌─────────────┐          │
│  │   VORHER    │    │   NACHHER   │          │
│  │   [image]   │    │   [image]   │          │
│  │ "WB142"     │    │ "VMB142"    │          │
│  │ ❌ Text     │    │ ✅ Text     │          │
│  │   nicht OK  │    │   richtig   │          │
│  └─────────────┘    └─────────────┘          │
│                                                │
│  📏 Änderung:                                  │
│     ◀ 15 Pixel nach links (left)              │
│     ▼ 5 Pixel nach unten (down)               │
│                                                │
│  Was möchten Sie tun?                          │
│  (What would you like to do?)                  │
│                                                │
│  ( ) Nur diese Instanz ändern                  │
│      (Only this instance)                      │
│                                                │
│  (•) Alle 12 Instanzen in diesem Plan ändern  │
│      (All 12 instances in current plan)        │
│                                                │
│  [✓] Dauerhaft speichern für alle zukünftigen │
│      Pläne (Save permanently for future plans) │
│                                                │
│         [Abbrechen]      [Übernehmen]         │
│         [Cancel]         [Apply]               │
└────────────────────────────────────────────────┘
```

### **Auto-Learning Suggestion** (After 3+ similar adjustments)

```
┌────────────────────────────────────────────────┐
│  💡 Verbesserungsvorschlag                     │
│     (Improvement Suggestion)                   │
├────────────────────────────────────────────────┤
│  Ich habe bemerkt, dass Sie OCR-Regionen       │
│  für "weichen_left" oft anpassen.              │
│                                                │
│  (I noticed you often adjust OCR regions for   │
│  "weichen_left")                               │
│                                                │
│  Gelernte Anpassung aus 5 Beispielen:          │
│  (Learned adjustment from 5 examples:)         │
│                                                │
│  ← 14px links  ↓ 6px unten                    │
│                                                │
│  Vertrauensstufe: 50% (Basiert auf 5 Plänen)  │
│  Confidence Level: 50% (Based on 5 plans)      │
│                                                │
│  ████████████░░░░░░  50%                       │
│                                                │
│  Soll ich dies automatisch für alle            │
│  zukünftigen Pläne machen?                     │
│  (Should I do this automatically for all       │
│   future plans?)                               │
│                                                │
│      [Nein, nicht jetzt]    [Ja, immer]       │
│      [No, not now]          [Yes, always]      │
└────────────────────────────────────────────────┘
```

---

## 🔄 Complete Workflow

### **Step-by-Step Process:**

1. **User resizes OCR region bbox**
   - Drags handles to adjust position/size
   - Releases mouse button

2. **System processes adjustment**
   - Calculates delta: offset_x, offset_y, width_delta, height_delta
   - Runs OCR on NEW region
   - Extracts old crop for comparison
   - Counts instances of this symbol

3. **Dialog appears with preview**
   - Shows before/after images
   - Displays old vs new OCR text
   - Shows adjustment in pixels with arrows
   - Offers 3 options:
     * Apply to this instance only
     * Apply to all instances in plan (default)
     * Save to template (default checked)

4. **User makes choice and confirms**

5. **System applies adjustment**
   - Updates selected row(s)
   - Re-runs OCR for each
   - Updates visualizations
   - Records adjustment for learning

6. **Auto-learning tracking**
   - Every adjustment is logged to `config/ocr_adjustments.json`
   - After 3 adjustments: Calculates average offset
   - After 3, 8, 13, 18... adjustments: Shows suggestion dialog

7. **If suggestion accepted**
   - Saves to template permanently
   - Future plans auto-apply this adjustment
   - Confirmation message shown

---

## 📊 Data Storage

### **Adjustment Log** (`config/ocr_adjustments.json`)

```json
{
  "weichen_left": {
    "history": [
      {
        "offset_x": -15,
        "offset_y": 5,
        "width_delta": 0,
        "height_delta": 0,
        "timestamp": "2026-01-11T10:30:15.123456"
      },
      {
        "offset_x": -13,
        "offset_y": 7,
        "width_delta": 0,
        "height_delta": 0,
        "timestamp": "2026-01-11T11:45:22.654321"
      }
    ],
    "learned_offset_x": -14,
    "learned_offset_y": 6,
    "learned_width_delta": 0,
    "learned_height_delta": 0,
    "confidence": 0.2,
    "sample_count": 2
  }
}
```

### **Template Storage** (`custom_symbols.json`)

When saved to template:
```json
{
  "symbols": [
    {
      "name": "weichen_left",
      "text_region_offset": {
        "dx": -14,
        "dy": 6,
        "width": 0,
        "height": 0
      },
      ...
    }
  ]
}
```

---

## 🧪 Testing Instructions

### **Test 1: Basic Adjustment**

1. Load a plan with template-matched symbols
2. Click on a symbol's OCR region (dashed magenta box)
3. Drag a corner handle to resize
4. Release mouse button
5. **Expected:** Dialog appears with before/after preview
6. Select "Alle Instanzen in diesem Plan" + check "Dauerhaft speichern"
7. Click "Übernehmen"
8. **Expected:** All instances updated, confirmation shown

### **Test 2: Auto-Learning**

1. Adjust OCR for same symbol class 3 times
2. On 3rd adjustment, after clicking "Übernehmen"
3. **Expected:** Suggestion dialog appears
4. Shows learned offset with confidence %
5. Click "Ja, immer"
6. **Expected:** Saved to template, confirmation shown

### **Test 3: Template Persistence**

1. Adjust OCR and save to template
2. Close and reopen application
3. Load a NEW plan with same symbol type
4. **Expected:** OCR regions use adjusted offset automatically

---

## 🎓 For Train Technicians (Non-Programmers)

### **Simple Guide:**

**When OCR text is in wrong position:**

1. **Find the blue dashed box** around the wrong text
2. **Click and drag the corners** to move it to correct position
3. **Release** - a window pops up showing old vs new
4. **Check the boxes** if it looks good:
   - ✓ "Alle Instanzen" = Fix all same symbols in this plan
   - ✓ "Dauerhaft speichern" = Remember for future plans
5. **Click "Übernehmen"** (Apply)
6. Done! ✅

**If you do this 3 times for same symbol:**
- System learns and asks: "Make this automatic?"
- Click "Ja, immer" (Yes, always)
- Now all future plans use this setting automatically!

---

## 🔧 Technical Details

### **Method Flow:**

1. `on_ocr_bbox_resized()` - Main callback
   - Calculates adjustment delta
   - Runs OCR on new region
   - Shows OCRAdjustmentDialog
   - Processes user choices

2. `_apply_ocr_adjustment_to_rows()` - Applies to multiple rows
   - Loops through row_ids
   - Applies offset to each OCR region
   - Re-runs OCR
   - Updates tree widget
   - Re-renders page

3. `_save_ocr_adjustment_to_template()` - Persists to template
   - Loads NewSymbolDetector
   - Updates SymbolDefinition.text_region_offset
   - Saves config to disk/database
   - Shows confirmation message

4. `_show_auto_learning_suggestion()` - Shows smart suggestion
   - Gets learned data from tracker
   - Shows AutoLearningSuggestionDialog
   - If accepted, saves to template
   - Marks as applied

### **OCRAdjustmentTracker:**

- `record_adjustment()`: Logs each adjustment
- `get_learned_adjustment()`: Returns average offset if 3+ samples
- `should_show_suggestion()`: Returns true on 3, 8, 13, 18... adjustments
- `apply_learned_to_template()`: Marks as applied (stops suggesting)

---

## ✨ Key Features

1. **Visual Feedback**: Before/after images show what changed
2. **Flexible Scope**: Choose single, all in plan, or permanent
3. **Smart Learning**: System learns from your behavior
4. **Non-Intrusive**: Only suggests, never forces changes
5. **Bilingual**: German + English for international teams
6. **Template-Specific**: Each symbol can have different offsets
7. **Undo Support**: Save state before applying
8. **Confidence Tracking**: Shows how confident the learning is

---

## 🚀 Benefits

### **For Users:**
- Fix OCR position issues once, apply everywhere
- Visual confirmation before applying changes
- System learns and suggests improvements
- Works across all future plans

### **For Train Technicians:**
- Simple visual interface
- Clear before/after comparison
- German language support
- No programming knowledge needed

### **For System:**
- Reduces manual corrections over time
- Improves OCR accuracy progressively
- User-driven adaptation without retraining
- Persistent across sessions

---

## 📝 Notes

- **Only works for template-matched symbols** (custom symbols)
- **YOLO symbols use different OCR** (not adjustable via this system)
- **Adjustments are per-symbol-class**, not per-instance
- **Auto-learning requires 3+ samples** before suggesting
- **Suggestions shown at intervals**: 3, 8, 13, 18, 23... adjustments
- **Config stored in**: `config/ocr_adjustments.json`
- **Template stored in**: `custom_symbols.json` (and database if available)

---

## 🎉 Status: READY FOR USE

The system is fully integrated, tested, and ready for production use. Train technicians can start using it immediately to improve OCR accuracy for template-matched symbols.

For smart learning across the entire system (not just template matching), this provides the foundation. The tracking and learning mechanisms can be extended to other components in future updates.

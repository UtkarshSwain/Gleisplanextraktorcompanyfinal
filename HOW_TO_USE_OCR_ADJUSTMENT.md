# How to Use OCR Adjustment Feature - Step-by-Step Guide

## 🎯 Quick Answer

**The OCR adjustment feature only works for TEMPLATE-MATCHED SYMBOLS (custom symbols).**

You need to:
1. Run template matching (with or without YOLO)
2. Look for **dashed boxes** around text near symbols
3. **Click on a dashed box** to select it (handles appear)
4. **Drag the corner/edge handles** to adjust position/size
5. **Release** → Adjustment dialog appears

---

## 📋 Step-by-Step Instructions

### **Step 1: Load a Plan and Run Template Matching**

1. Load your PDF plan
2. Make sure template matching is enabled:
   - Check "Template-Matching aktivieren" in settings
   - Or run combined YOLO + Template matching
3. Click **"Run Pipeline"**

### **Step 2: Identify OCR Regions**

After pipeline runs, you should see:

```
┌─────────────────────────────────────┐
│                                     │
│   ┌────┐         ┌- - - - - -┐    │  ← Dashed box = OCR region
│   │ W1 │ ←text→  ┊  VMB142   ┊    │
│   └────┘         └- - - - - -┘    │
│   ↑ Symbol       ↑ OCR Region     │
│   (solid box)    (dashed box)     │
│                                     │
└─────────────────────────────────────┘
```

**Look for:**
- **Solid boxes** = Symbol bounding boxes (magenta for custom symbols)
- **Dashed boxes** = OCR regions (same color as symbol, dashed line)
- **Text labels** above dashed boxes showing OCR text

**Colors:**
- Magenta (255, 0, 255) = Template-matched custom symbols
- Other colors = YOLO-detected symbols (OCR adjustment NOT available)

### **Step 3: Select an OCR Region**

**Click on the dashed box** (OCR region) to select it.

**What happens:**
- Dashed box border highlights
- **8 small square handles appear** at corners and edges:
  ```
  ■─────────■─────────■
  │                   │
  │   VMB142          │
  ■                   ■
  │                   │
  ■─────────■─────────■

  ■ = Resize handles (appear on selection)
  ```

**If handles don't appear:**
- OCR region might not be selectable (check it's a custom symbol)
- Try clicking directly on the dashed line
- Check console for debug output: "🔧 Showing OCR region handles for row_id..."

### **Step 4: Drag a Handle to Adjust**

**Click and drag any handle:**
- **Corner handles** (■ at corners): Resize from that corner
- **Edge handles** (■ on sides): Resize from that edge
- Move the handle to adjust OCR region position/size

**Example adjustments:**
- Text cut off on left? → Drag left edge handle to the left
- Text too far right? → Drag entire box by moving corners
- Text too tall? → Drag top/bottom edges

**While dragging:**
- OCR region updates in real-time
- Minimum size enforced (10x10 pixels)

### **Step 5: Release Mouse Button**

When you release the mouse button, **the dialog appears automatically:**

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
│  │ ❌ Failed   │    │ ✅ Success  │          │
│  └─────────────┘    └─────────────┘          │
│                                                │
│  📏 Änderung: ◀ 15px links, ▼ 5px unten      │
│                                                │
│  ( ) Nur diese Instanz                         │
│  (•) Alle 12 Instanzen in diesem Plan         │
│  [✓] Dauerhaft speichern (alle Pläne)         │
│                                                │
│         [Abbrechen]      [Übernehmen]         │
└────────────────────────────────────────────────┘
```

### **Step 6: Review and Apply**

1. **Check before/after images** - Is new OCR text correct?
2. **Choose scope:**
   - Single instance only
   - **All instances in plan** (recommended, default)
   - Save to template for future plans (recommended, default checked)
3. **Click "Übernehmen" (Apply)**

**Result:**
- Selected instances update immediately
- OCR re-runs for each instance
- Adjustment recorded for auto-learning

### **Step 7: Repeat (Optional)**

After 3 similar adjustments, you'll see:

```
┌────────────────────────────────────────────────┐
│  💡 Verbesserungsvorschlag                     │
│                                                │
│  System has learned from 3 adjustments:        │
│  ← 14px left, ↓ 6px down                      │
│                                                │
│  Make this automatic for all future plans?     │
│                                                │
│      [Nein, nicht jetzt]    [Ja, immer]       │
└────────────────────────────────────────────────┘
```

Click **"Ja, immer"** to save as permanent default.

---

## 🔍 Troubleshooting

### **"I don't see any dashed boxes"**

**Possible causes:**

1. **No template matching run**
   - Solution: Enable template matching and run pipeline

2. **No custom symbols defined**
   - Solution: Add custom symbols first (with text enabled)
   - Check: `custom_symbols.json` exists and has symbols with `has_text: true`

3. **Symbols detected but no OCR region data**
   - Check console for: "OCR data: ocr_x1=..."
   - If missing, OCR didn't run during pipeline
   - Check symbol definition has `text_position` set

4. **YOLO-only detection**
   - OCR regions only appear for **template-matched symbols**
   - YOLO symbols use different OCR method (not adjustable this way)

### **"Handles don't appear when I click"**

**Solutions:**

1. **Click directly on the dashed line**, not inside the box
2. Make sure it's a custom symbol (magenta color)
3. Check console output for selection messages
4. Try clicking on a different OCR region
5. Ensure `ResizableOCRBBoxItem` is being created (check console)

### **"Dialog doesn't appear after dragging"**

**Possible causes:**

1. **Handle released without actual change**
   - System checks if bbox changed before showing dialog
   - Try dragging further

2. **Error occurred**
   - Check console for error messages
   - Check terminal for Python traceback

3. **Dialog hidden behind another window**
   - Check taskbar for modal dialog

### **"No OCR text appears in dialog"**

**This is normal if:**
- Old OCR region had no text detected
- New OCR region finds text successfully
- Shows as improvement (❌ → ✅)

---

## 📸 Visual Guide

### **What to Look For:**

```
TEMPLATE-MATCHED SYMBOL (✅ Works):
┌────────────────────────────┐
│  ┏━━━┓         ┏╍╍╍╍╍╍┓   │
│  ┃ W ┃ ←left→  ╏VMB142╏   │  ← Dashed OCR region
│  ┗━━━┛         ┗╍╍╍╍╍╍┛   │
│  Magenta       Magenta     │
│  Solid         Dashed      │
└────────────────────────────┘

YOLO SYMBOL (❌ Doesn't work):
┌────────────────────────────┐
│  ┏━━━┓                     │
│  ┃ W ┃  VMB142             │  ← Text label only
│  ┗━━━┛                     │     (no dashed box)
│  Green/Blue                │
│  (YOLO class)              │
└────────────────────────────┘
```

### **Selection & Handles:**

```
UNSELECTED:
┏ ╍ ╍ ╍ ╍ ╍ ┓
╏  VMB142   ╏
┗ ╍ ╍ ╍ ╍ ╍ ┛

SELECTED (after clicking):
■─────────■─────────■
│                   │
│    VMB142         │
■                   ■
│                   │
■─────────■─────────■
↑ Drag these handles
```

---

## ✅ Quick Checklist

Before asking "where is the adjustment feature?":

- [ ] Template matching is enabled
- [ ] Pipeline has been run
- [ ] Custom symbols are defined with `has_text: true`
- [ ] Symbols were detected (magenta boxes visible)
- [ ] Dashed boxes appear near symbols
- [ ] Click on **dashed box** (not solid symbol box)
- [ ] Look for 8 small square handles
- [ ] Drag a handle and release

---

## 🎓 Summary

**The feature works like this:**

1. **Template matching** detects custom symbols
2. **OCR runs** and stores region coordinates
3. **Dashed boxes** show OCR regions visually
4. **Click dashed box** → handles appear
5. **Drag handle** → adjust position/size
6. **Release** → dialog shows before/after
7. **Apply** → updates all instances
8. **After 3x** → system suggests making it permanent

**If you don't see dashed boxes**, the most likely reason is:
- Template matching hasn't run yet, OR
- No custom symbols with text defined, OR
- Symbols detected by YOLO only (not template matching)

---

## 🚀 Next Steps

1. Load a plan
2. Run template matching pipeline
3. Look for magenta dashed boxes
4. Click one and try adjusting!

The feature is **fully operational** - it just needs template-matched symbols with OCR regions to work on.

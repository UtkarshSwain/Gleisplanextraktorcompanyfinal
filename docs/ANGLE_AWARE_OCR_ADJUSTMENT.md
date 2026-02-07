# Angle-Aware OCR Adjustment

## 🎯 Overview

The OCR adjustment system is now **angle-aware for X offset only**. This means:
- **X offset** rotates based on symbol angle (follows symbol orientation)
- **Y offset** stays constant (always vertical in image coordinates)

---

## 🔄 How It Works

### **Adjustment Formula:**

```python
angle_rad = radians(symbol_angle)

# X offset rotates with symbol
rotated_offset_x = offset_x * cos(angle)
rotated_offset_y_from_x = offset_x * sin(angle)

# Y offset stays vertical
final_offset_x = rotated_offset_x
final_offset_y = rotated_offset_y_from_x + offset_y
```

### **What This Means:**

**X Offset** = "Along symbol orientation"
- At 0°: Moves horizontally (right/left)
- At 90°: Moves vertically (down/up)
- At 180°: Moves horizontally opposite
- At 270°: Moves vertically opposite

**Y Offset** = "Always vertical"
- At any angle: Moves up/down in image coordinates
- Does NOT rotate with symbol

---

## 📊 Examples

### **Example 1: Symbol at 0° (Horizontal)**

**Adjustment:** offset_x = +15, offset_y = +5

```
Symbol at 0°:
┌──┐
│ W│ →→→→→→ [TEXT]
└──┘
   ↓ +5px (Y offset, vertical)

Result:
- Move 15px right (X offset horizontal at 0°)
- Move 5px down (Y offset always vertical)
- Final: (15, 5)
```

### **Example 2: Symbol at 90° (Vertical)**

**Adjustment:** offset_x = +15, offset_y = +5

```
Symbol at 90°:
┌─┐
│W│
│ │
└─┘
 ↓
 ↓  [TEXT]
 ↓
+15px (X offset rotated to vertical)

Result:
- X offset +15 becomes: 0px right, +15px down (rotated 90°)
- Y offset +5: 0px right, +5px down (stays vertical)
- Final: (0, 20)
```

### **Example 3: Symbol at 180° (Upside down)**

**Adjustment:** offset_x = +15, offset_y = +5

```
Symbol at 180°:
    ┌──┐
[TEXT] ←←←←←← │W │
               └──┘
                ↓ +5px (Y offset, vertical)

Result:
- X offset +15 becomes: -15px (rotated 180°, reversed)
- Y offset +5: +5px down (stays vertical)
- Final: (-15, 5)
```

### **Example 4: Symbol at 270° (Vertical flipped)**

**Adjustment:** offset_x = +15, offset_y = +5

```
Symbol at 270°:
 ↑
 ↑  [TEXT]
 ↑
┌─┐
│ │
│W│
└─┘
-15px (X offset rotated to vertical up)

Result:
- X offset +15 becomes: 0px right, -15px up (rotated 270°)
- Y offset +5: 0px right, +5px down (stays vertical)
- Final: (0, -10)
```

---

## 🎨 Visual Summary

```
Angle:        0°          90°         180°        270°
Symbol:     ┌──┐        ┌─┐         ┌──┐        ┌─┐
            │W │        │W│         │ W│        │ │
            └──┘        │ │         └──┘        │W│
                        └─┘                     └─┘

X offset +15:
Direction:   →→→        ↓↓↓         ←←←         ↑↑↑
            (right)    (down)      (left)       (up)

Y offset +5:
Direction:   ↓↓↓        ↓↓↓         ↓↓↓         ↓↓↓
            (down)     (down)      (down)      (down)
            ALWAYS VERTICAL - NEVER ROTATES
```

---

## 💡 Why This Design?

### **X Offset Rotates:**
- Text position is often **relative to symbol orientation**
- "Right of symbol" means:
  - At 0°: Actually right
  - At 90°: Below
  - At 180°: Left
  - At 270°: Above
- X offset follows this natural relationship

### **Y Offset Stays Constant:**
- Vertical adjustment is often **absolute** (image space)
- Fine-tuning vertical position of text
- Independent of symbol rotation
- Easier to understand and predict

---

## 🧪 Testing Angle-Aware Adjustment

### **Test 1: Horizontal Symbol (0°)**

1. Find a symbol at 0° angle
2. Adjust OCR region 20px to the right
3. **Expected:** Moves 20px right
4. Apply to all instances
5. **Check:** Other 0° symbols move right ✅

### **Test 2: Vertical Symbol (90°)**

1. Find a symbol at 90° angle
2. Same adjustment (+20px X)
3. **Expected:** Moves 20px DOWN (not right!)
4. Apply to all instances
5. **Check:** Other 90° symbols move down ✅

### **Test 3: Mixed Angles**

1. Adjust OCR for symbol at 0°: +15px X, +5px Y
2. Apply to all instances of that symbol class
3. **Expected results:**
   - 0° symbols: Move (15, 5)
   - 90° symbols: Move (0, 20)
   - 180° symbols: Move (-15, 5)
   - 270° symbols: Move (0, -10)

---

## 📐 Mathematical Details

### **Rotation Formula:**

For a 2D rotation, the standard formula is:
```
new_x = old_x * cos(θ) - old_y * sin(θ)
new_y = old_x * sin(θ) + old_y * cos(θ)
```

**Our implementation (X offset only):**
```python
# Only offset_x rotates, offset_y stays as-is
rotated_x = offset_x * cos(angle)
rotated_y = offset_x * sin(angle) + offset_y

# Breakdown:
# - offset_x contributes to both X and Y based on rotation
# - offset_y only contributes to Y (vertical component)
```

### **Special Cases:**

| Angle | cos(θ) | sin(θ) | X Offset → | Y Offset |
|-------|--------|--------|------------|----------|
| 0°    | 1      | 0      | (offset_x, 0) | offset_y |
| 90°   | 0      | 1      | (0, offset_x) | offset_y |
| 180°  | -1     | 0      | (-offset_x, 0) | offset_y |
| 270°  | 0      | -1     | (0, -offset_x) | offset_y |

---

## 🔍 Debug Output

When applying adjustments, the console shows:

```
🔄 Angle-aware adjustment for row 1234:
   Symbol angle: 90.0°
   Original offset: (15, 5)
   Rotated offset: (0.0, 20.0)
```

This helps verify the rotation is working correctly.

---

## ⚙️ Configuration

The angle-aware adjustment works automatically:
- Reads `angle` field from dataframe
- If no angle present, assumes 0°
- Applies rotation formula transparently
- No user configuration needed

---

## 🎯 Use Cases

### **Use Case 1: Railway Track Plans**
- Tracks can be horizontal, vertical, or diagonal
- Text labels need to follow track orientation
- X offset = "distance along track"
- Y offset = "perpendicular distance from track"

### **Use Case 2: Signal Symbols**
- Signals face different directions
- Text ID is always in front of signal
- X offset rotates with signal direction
- Y offset adjusts vertical alignment

### **Use Case 3: Switch/Weichen Symbols**
- Switches can be rotated 0°, 90°, 180°, 270°
- Text label follows switch orientation
- Consistent adjustment across all orientations

---

## ✅ Benefits

1. **Natural adjustment** - "Right of symbol" works regardless of rotation
2. **Consistent behavior** - Same adjustment works for all angles
3. **Less manual work** - One adjustment fixes all orientations
4. **Intuitive** - Matches how humans think about orientation
5. **Flexible** - Y offset allows fine-tuning independent of rotation

---

## 🚀 Future Enhancements

Possible future improvements:
- [ ] Make Y offset optionally rotatable (user choice)
- [ ] Support arbitrary angles (not just 0°, 90°, 180°, 270°)
- [ ] Angle-aware width/height adjustments
- [ ] Per-angle adjustment profiles
- [ ] Visual rotation preview in dialog

---

## 📝 Notes

- Only works for **template-matched symbols** (custom symbols)
- Angle must be stored in `angle` column of dataframe
- Rotation uses standard trigonometry (cos/sin)
- Y offset intentionally NOT rotated (by design)
- Width/height deltas currently NOT rotated

---

## 🎉 Status

**✅ IMPLEMENTED and READY**

The angle-aware X offset adjustment is fully functional and integrated into the OCR adjustment dialog system.

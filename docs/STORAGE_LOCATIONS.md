# OCR Adjustment System - Storage Locations

## 📊 Storage Summary

The OCR adjustment system uses **DUAL STORAGE**: PostgreSQL (primary) + Local Files (fallback)

---

## 🗄️ Storage Breakdown

### **1. OCR Adjustment Learning Data** ⚡ NEW

**Storage Location:** `config/ocr_adjustments.json` (**LOCAL FILE ONLY**)

**What's Stored:**
- User's manual OCR region adjustments
- Adjustment history (offset_x, offset_y, width_delta, height_delta)
- Learned averages per symbol class
- Confidence levels
- Sample counts

**Example:**
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
      }
    ],
    "learned_offset_x": -14,
    "learned_offset_y": 6,
    "learned_width_delta": 0,
    "learned_height_delta": 0,
    "confidence": 0.3,
    "sample_count": 3
  }
}
```

**Persistence:** Local only (not in PostgreSQL)

**Why Local Only?**
- Fast access (no DB queries)
- Learning data is user/machine-specific
- Not shared across users
- Easy to reset/clear

---

### **2. Symbol Template Definitions** (includes OCR adjustments)

**Storage Location:** **DUAL - PostgreSQL + Local Files**

#### **A. PostgreSQL Database (Primary)**

**Table:** `custom_symbols`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS custom_symbols (
    id SERIAL PRIMARY KEY,
    symbol_name TEXT UNIQUE NOT NULL,
    config_json JSONB NOT NULL,        -- Symbol configuration
    templates_data BYTEA,               -- Pickled numpy arrays (templates, contours, hu_moments)
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

**What's Stored in `config_json`:**
```json
{
  "name": "weichen_left",
  "detection_method": "template",
  "similarity_threshold": 0.75,
  "has_text": true,
  "text_position": ["left"],
  "text_region_offset": {        ← OCR ADJUSTMENT SAVED HERE!
    "dx": -14,
    "dy": 6,
    "width": 0,
    "height": 0
  },
  "color": [255, 0, 255],
  "example_count": 5
}
```

**What's Stored in `templates_data` (BYTEA):**
- Pickled numpy arrays:
  - `templates`: Template images for matching
  - `contours`: Contour data for shape matching
  - `hu_moments`: Hu moments for rotation-invariant matching

**Functions:**
- `save_custom_symbol(symbol_name, config, templates_data)` - Save/update
- `get_all_custom_symbols()` - Load all
- `get_custom_symbol(symbol_name)` - Load one
- `delete_custom_symbol(symbol_name)` - Delete

#### **B. Local Files (Fallback)**

**Location:** Project root directory

**Files:**
1. **`custom_symbols.json`** - Symbol metadata
   ```json
   {
     "weichen_left": {
       "detection_method": "template",
       "text_region_offset": {
         "dx": -14,
         "dy": 6,
         "width": 0,
         "height": 0
       },
       ...
     }
   }
   ```

2. **`custom_symbol_templates/`** - Template images
   ```
   custom_symbol_templates/
   ├── weichen_left/
   │   ├── template_0.npy
   │   ├── template_1.npy
   │   ├── contour_0.npy
   │   ├── contour_1.npy
   │   ├── hu_moments_0.npy
   │   └── hu_moments_1.npy
   ├── signal_main/
   │   └── ...
   ```

---

## 🔄 How Storage Works

### **Loading Priority (Startup):**

```
1. Check if PostgreSQL is available
   ↓
2. If YES:
   - Load all symbols from PostgreSQL
   - Use database data (includes OCR adjustments)
   ↓
3. If NO or empty:
   - Fall back to local files
   - Load from custom_symbols.json + .npy files
   ↓
4. Load OCR learning data from config/ocr_adjustments.json (always local)
```

### **Saving Priority:**

```
When user saves OCR adjustment to template:
   ↓
1. Update SymbolDefinition.text_region_offset in memory
   ↓
2. Call detector._save_config()
   ↓
3a. If PostgreSQL available:
    - Save to PostgreSQL (custom_symbols table)
   ↓
3b. Always save to local files:
    - Update custom_symbols.json
    - Update .npy files if needed
   ↓
4. Record adjustment in config/ocr_adjustments.json (local)
```

---

## 📂 Complete File Structure

```
Gleisplanextraktorv3/
├── config/
│   └── ocr_adjustments.json           ← OCR Learning Data (LOCAL ONLY)
│
├── custom_symbols.json                ← Symbol Metadata (DUAL: DB + Local)
│
├── custom_symbol_templates/           ← Template Images (DUAL: DB + Local)
│   ├── weichen_left/
│   │   ├── template_0.npy
│   │   └── ...
│   └── signal_main/
│       └── ...
│
└── (PostgreSQL Database)              ← Primary Storage (if available)
    └── custom_symbols table
        ├── config_json (JSONB)        ← Includes text_region_offset
        └── templates_data (BYTEA)     ← Pickled numpy arrays
```

---

## 🎯 Where Each Data Type Goes

| Data Type | PostgreSQL | Local Files | Notes |
|-----------|------------|-------------|-------|
| **OCR Learning History** | ❌ No | ✅ Yes | `config/ocr_adjustments.json` |
| **Template OCR Offsets** | ✅ Yes | ✅ Yes | `text_region_offset` in config |
| **Symbol Templates (images)** | ✅ Yes (BYTEA) | ✅ Yes (.npy) | Numpy arrays |
| **Symbol Metadata** | ✅ Yes (JSONB) | ✅ Yes (.json) | Detection settings |
| **Workspace Data** | ✅ Yes | ❌ No | Edited detections |
| **Validation Results** | ✅ Yes | ❌ No | User validation log |

---

## 🔍 Why This Dual Storage Design?

### **Advantages:**

1. **Reliability:** If PostgreSQL is down, system works with local files
2. **Portability:** Can copy project folder to another machine
3. **Performance:** Local files are fast for small datasets
4. **Git-friendly:** Local JSON files can be version-controlled
5. **Multi-user:** PostgreSQL allows sharing templates across users

### **Trade-offs:**

1. **Sync Issues:** If multiple users edit locally, can conflict
2. **Disk Space:** Data stored twice (DB + files)
3. **Complexity:** Two codepaths to maintain

---

## 🚀 For Your Use Case

### **Current Setup:**

✅ **OCR Adjustment Learning** → Local file (`config/ocr_adjustments.json`)
- Per-user learning
- Fast access
- No DB overhead

✅ **Template OCR Offsets** → PostgreSQL (primary) + Local files (fallback)
- Shared across users (if using DB)
- Persistent and backed up
- Falls back to local if DB unavailable

### **Recommendation:**

**If you have PostgreSQL running:**
- System automatically uses PostgreSQL for template storage
- OCR adjustments saved to templates go to PostgreSQL
- Learning history stays local

**If PostgreSQL is NOT running:**
- System automatically falls back to local files
- Everything still works perfectly
- Just not shared across multiple machines

---

## 📝 How to Check What's Being Used

### **Check if PostgreSQL is being used:**

Look for this in console output:
```
Loaded 5 custom symbols from PostgreSQL  ← Using DB
```

or

```
Loaded 5 custom symbol definitions from local files  ← Using Local
```

### **Check Database Status:**

```python
from database_sqlite import is_db_available
print(f"SQLite available: {is_db_available()}")
```

### **Manual Check:**

1. **PostgreSQL:** Query `custom_symbols` table
   ```sql
   SELECT symbol_name, config_json->>'text_region_offset'
   FROM custom_symbols;
   ```

2. **Local Files:** Check `custom_symbols.json`
   ```bash
   cat custom_symbols.json | jq '.weichen_left.text_region_offset'
   ```

3. **Learning Data:** Check `config/ocr_adjustments.json`
   ```bash
   cat config/ocr_adjustments.json | jq '.weichen_left'
   ```

---

## 🔄 Migration/Backup

### **Export from PostgreSQL to Local:**

System does this automatically when saving!

### **Import from Local to PostgreSQL:**

Just edit local files and call:
```python
from core.symbol_detector import NewSymbolDetector
detector = NewSymbolDetector()
# Loads from local
detector._save_config_to_db()  # Saves to PostgreSQL
```

### **Backup Strategy:**

1. **PostgreSQL:** Use `pg_dump` for database backup
2. **Local Files:**
   - Commit `custom_symbols.json` to git
   - Backup `custom_symbol_templates/` folder
   - Backup `config/ocr_adjustments.json`

---

## ✅ Summary

**TL;DR:**

- **OCR Learning Data** → `config/ocr_adjustments.json` (local only)
- **Template Settings (incl. OCR offsets)** → PostgreSQL + Local files (dual storage)
- **System uses PostgreSQL if available**, falls back to local files
- **Both storage methods work perfectly**, choice is automatic

Your OCR adjustment system is **production-ready** and **works with or without PostgreSQL**! 🎉

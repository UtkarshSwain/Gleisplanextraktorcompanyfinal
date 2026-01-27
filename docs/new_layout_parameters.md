# New Layout Requirements Checklist

## 1. INFORMATION TO GATHER BEFORE STARTING

### A. Document Analysis
| Requirement | Description | Example (Layout A) | Your Layout B |
|-------------|-------------|-------------------|---------------|
| **Document size** | Paper format | A0, A1 | ? |
| **Scan DPI** | Resolution of scans | 500 DPI | ? |
| **Color scheme** | B/W, color, blueprint | B/W | ? |
| **Orientation** | Portrait/Landscape | Landscape | ? |
| **Text language** | Primary language | German | ? |
| **Font types** | Fonts used | Technical sans-serif | ? |

### B. Element Inventory
List ALL visual elements that need detection:

```
Layout B Elements:
├── Signals
│   ├── Class name: ________________
│   ├── Visual description: ________________
│   ├── Has text/ID: Yes/No
│   ├── Text format: ________________ (e.g., "AA123")
│   └── Approximate count per page: ________________
│
├── Markers/Coordinates
│   ├── Class name: ________________
│   ├── Coordinate format: ________________ (e.g., "123.456" or "123,456")
│   └── Position relative to elements: ________________
│
├── [Element Type 3]
│   ├── Class name: ________________
│   └── ...
│
└── [Add more as needed]
```

### C. Spatial Relationships
For each element that links to a coordinate:

| Element | Coordinate Position | Distance (approx) |
|---------|---------------------|-------------------|
| Signal → Coordinate | Below | 20-50 pixels |
| Marker → Text | Right | 10-30 pixels |
| ... | ... | ... |

---

## 2. YOLO MODEL PARAMETERS

### A. Training Dataset Configuration

```yaml
# dataset.yaml for Layout Type B

path: /path/to/layout_b_dataset
train: images/train
val: images/val
test: images/test  # optional

# Number of classes - MUST match your element inventory
nc: 8  # Example: 8 classes for Layout B

# Class names - MUST match annotation labels exactly
names:
  0: primary_signal
  1: secondary_signal
  2: km_marker
  3: track_number
  4: switch_indicator
  5: crossing_marker
  6: text_annotation
  7: coordinate
```

### B. Training Hyperparameters

```python
from ultralytics import YOLO

# Load base model (OBB = Oriented Bounding Box)
model = YOLO('yolov8l-obb.pt')  # Large model for accuracy

# Training parameters
training_params = {
    # === CRITICAL PARAMETERS ===
    'data': 'path/to/dataset.yaml',
    'epochs': 120,              # Start with 120, can increase if not converged
    'imgsz': 1024,              # MUST match your tile size / 2
                                 # If tile_size=2048, use imgsz=1024
    'batch': 8,                 # Reduce if GPU OOM (out of memory)

    # === TASK SPECIFICATION ===
    'task': 'obb',              # Oriented Bounding Box - REQUIRED for rotated text

    # === OPTIMIZATION ===
    'optimizer': 'AdamW',       # Usually best for detection
    'lr0': 0.001,               # Initial learning rate
    'lrf': 0.01,                # Final learning rate factor
    'momentum': 0.937,
    'weight_decay': 0.0005,

    # === AUGMENTATION ===
    'augment': True,
    'degrees': 15.0,            # Rotation augmentation (±15°)
    'translate': 0.1,           # Translation augmentation
    'scale': 0.5,               # Scale augmentation
    'fliplr': 0.5,              # Horizontal flip probability
    'mosaic': 1.0,              # Mosaic augmentation
    'mixup': 0.1,               # Mixup augmentation

    # === REGULARIZATION ===
    'dropout': 0.0,             # Dropout (usually 0 for detection)

    # === EARLY STOPPING ===
    'patience': 20,             # Stop if no improvement for 20 epochs

    # === OUTPUT ===
    'project': 'runs/layout_b',
    'name': 'v1',
    'exist_ok': True,
    'save': True,
    'save_period': 10,          # Save checkpoint every 10 epochs
}

# Start training
results = model.train(**training_params)
```

### C. Inference/Prediction Parameters

These go in your layout profile (`profiles/layout_type_b.yaml`):

```yaml
detection:
  # === TILING (for large documents) ===
  tile_size: 2048         # Tile size in pixels
                          # Rule: Should be 2x your training imgsz
  overlap_pct: 40         # % overlap between tiles
                          # Higher = better boundary detection, slower
  tile_halo: 320          # Extra context around tiles

  # === DOCUMENT SETTINGS ===
  dpi: 500                # Must match your training data DPI
                          # Common: 300 (standard), 500 (high quality)

  # === MODEL INPUT ===
  pred_imgsz: 1024        # MUST match training imgsz exactly

  # === CONFIDENCE FILTERING ===
  conf: 0.005             # Initial confidence (very low)
                          # Per-class thresholds do the real filtering

  # === NMS (Non-Maximum Suppression) ===
  iou: 0.35               # IoU threshold for NMS
                          # Lower = more aggressive duplicate removal
                          # Higher = allows more overlapping boxes

  # === DETECTION LIMITS ===
  max_det: 1500           # Max detections per image
                          # Increase if you have very dense layouts

  # === NMS MODE ===
  agnostic_nms: false     # false = class-specific NMS (recommended)
                          # true = treat all classes same in NMS

  # === PRECISION ===
  half: false             # false for CPU, true for GPU with FP16

  # === TEST-TIME AUGMENTATION ===
  use_tta: true           # Enable for +0.5-1% accuracy
  tta_scales: [1.0]       # Scale factors (1.0 = no scaling)
  tta_flips: [0, 1]       # 0=none, 1=horizontal, 2=vertical
  tta_min_votes: 1        # Min votes to keep detection
```

---

## 3. PER-CLASS PARAMETERS

For each class in your layout:

```yaml
classes:
  primary_signal:
    # === DETECTION THRESHOLDS ===
    confidence_threshold: 0.7   # How confident to accept detection
                                # Start at 0.5, adjust based on:
                                # - Higher if many false positives
                                # - Lower if missing detections

    nms_threshold: 0.35         # NMS IoU for this class
                                # Lower if duplicates, higher if missing

    # === OCR SETTINGS ===
    requires_ocr: true          # Does this element have text?
    fixed_text: null            # Set if text is always same (e.g., "GM")
    id_pattern: "^[A-Z]{2}\\d{3}$"  # Regex to validate extracted text

    # === VISUALIZATION ===
    color: [255, 0, 0]          # RGB color for display
```

### Confidence Threshold Guidelines

| Scenario | Suggested Starting Value |
|----------|-------------------------|
| High mAP (>0.98), few FPs | 0.5 - 0.6 |
| Medium mAP (0.95-0.98) | 0.6 - 0.75 |
| Lower mAP or many FPs | 0.75 - 0.85 |
| Critical element (no misses) | 0.3 - 0.5 |

### NMS Threshold Guidelines

| Scenario | Suggested Value |
|----------|-----------------|
| Elements often overlap | 0.5 - 0.6 |
| Elements never overlap | 0.25 - 0.35 |
| Getting duplicates | Decrease by 0.05 |
| Missing valid detections | Increase by 0.05 |

---

## 4. OCR PARAMETERS

```yaml
ocr:
  # === ENGINE SELECTION ===
  engine: paddleocr           # "paddleocr", "easyocr", "tesseract"

  # === PREPROCESSING ===
  denoise_strength: 4         # 0-10, higher = more denoising
                              # Increase for noisy scans
  sharpen_amount: 1.3         # 1.0 = no sharpening
                              # Increase for blurry text
  use_preprocessing: true
  use_adaptive_threshold: true
  use_morph_operations: true

  # === PER-CLASS OCR CONFIDENCE ===
  confidence_thresholds:
    primary_signal: 0.5       # OCR confidence to accept text
    km_marker: 0.6
    default: 0.45

  # === CROP PADDING (for cardinal/horizontal text) ===
  cardinal_detection_padding:
    primary_signal: 4         # Pixels to add around detection for OCR
    km_marker: 6
    # Increase if text is being cut off

  # === CROP EXPANSION ===
  cardinal_expansion_factor:
    primary_signal: [1.0, 1.0]  # [width_factor, height_factor]
    km_marker: [1.2, 1.0]       # Expand width for longer text

  # === FOR ROTATED/ANGULAR TEXT ===
  angular_detection_padding:
    primary_signal: 8           # More padding for rotated crops
  angular_expansion_factor:
    primary_signal: [1.0, 1.1]
```

---

## 5. LINKING RULES

Define how elements connect spatially:

```yaml
linking_rules:
  primary_signal:
    mode: below               # Where to look for coordinate
                              # Options: below, above, either, inside, right_or_below
    dx_multiplier: 1.0        # Search distance multiplier (X)
    dy_multiplier: 1.0        # Search distance multiplier (Y)
    max_distance: null        # Max pixel distance (null = auto)
    prefer_horizontal: false  # Prefer horizontal matches
    search_left: false        # Also search left side
    tilted_ok: false          # Allow tilted elements
    block: false              # Contains multiple coords (like weichen_block)
```

### Mode Selection Guide

| Mode | Use When |
|------|----------|
| `below` | Coordinate always below element |
| `above` | Coordinate always above element |
| `either` | Coordinate can be above or below |
| `inside` | Coordinate inside element box |
| `right_or_below` | Coordinate to right or below |

---

## 6. VALIDATION PATTERNS

```yaml
validation:
  # Regex for coordinate text
  coordinate_pattern: '^\d{1,3}\.\d{3}$'  # e.g., "123.456"

  # Classes where numbers-only text is OK
  numeric_ok_classes:
    - km_marker
    - track_number

  # ID patterns per class
  id_patterns:
    primary_signal: "^[A-Z]{2}\\d{3}$"    # e.g., "AB123"
    secondary_signal: "^[A-Z]\\d{2}$"     # e.g., "A12"
```

---

## 7. QUICK REFERENCE: MINIMUM REQUIRED INFO

To add a new layout, you MUST provide:

### Mandatory
- [ ] List of classes to detect
- [ ] Training images (20-50 minimum)
- [ ] Annotated bounding boxes (OBB format)
- [ ] Scan DPI setting
- [ ] Coordinate text format (e.g., "XX.XXX")

### Recommended
- [ ] Per-class confidence thresholds (or accept defaults)
- [ ] Linking rules for element→coordinate relationships
- [ ] ID validation patterns
- [ ] Sample documents for testing

### Optional (system has defaults)
- [ ] OCR preprocessing parameters
- [ ] TTA settings
- [ ] NMS thresholds

# Training Guide: Adding Support for New Track Layout Types

This guide explains how to add support for a completely different track layout type (e.g., Layout Type B) to the Gleisplanextraktor system.

## Overview

Adding a new layout type involves 5 main steps:

1. **Analysis**: Understand the new layout's visual elements
2. **Annotation**: Create training data with bounding boxes
3. **Training**: Train/fine-tune a YOLO model
4. **Configuration**: Create a layout profile
5. **Validation**: Test and refine

## Step 1: Layout Analysis

### 1.1 Collect Sample Documents
- Gather 20-50 representative PDF/images of the new layout type
- Ensure variety: different sections, scales, conditions

### 1.2 Identify Visual Elements
Create a list of all elements that need detection:

```
Element Inventory for Layout Type B:
├── Primary Signals
│   ├── Type 1: [description, visual characteristics]
│   └── Type 2: [description, visual characteristics]
├── Markers
│   ├── Kilometer markers: [format: XX.XXX]
│   └── Track IDs: [format: T-###]
├── Text Labels
│   └── Annotations: [font style, typical locations]
└── Infrastructure
    ├── Switches: [visual pattern]
    └── Crossings: [visual pattern]
```

### 1.3 Document Relationships
Map how elements relate spatially:
- Signal → always has coordinate label below
- Marker → text label to the right
- etc.

## Step 2: Data Annotation

### 2.1 Prepare Images
```bash
# Convert PDFs to images at consistent DPI
python -c "
from pdf2image import convert_from_path
import os

pdf_path = 'path/to/layout_b_samples'
output_dir = 'training_data/layout_b/images'
os.makedirs(output_dir, exist_ok=True)

for pdf_file in os.listdir(pdf_path):
    if pdf_file.endswith('.pdf'):
        images = convert_from_path(
            os.path.join(pdf_path, pdf_file),
            dpi=500,
            fmt='png'
        )
        for i, img in enumerate(images):
            img.save(f'{output_dir}/{pdf_file[:-4]}_page{i}.png')
"
```

### 2.2 Tile Large Images
For A0/A1 layouts, tile into manageable pieces:
```bash
python scripts/tile_images.py \
    --input training_data/layout_b/images \
    --output training_data/layout_b/tiles \
    --tile-size 2048 \
    --overlap 0.2
```

### 2.3 Annotate with Label Studio or CVAT
Use OBB (Oriented Bounding Box) format for rotated elements:

```yaml
# classes.yaml for Layout Type B
names:
  0: primary_signal
  1: secondary_signal
  2: km_marker
  3: track_id
  4: text_label
  5: switch
  6: crossing
```

Export annotations in YOLO OBB format:
```
# label format: class x_center y_center width height rotation
0 0.5234 0.3421 0.0234 0.0156 45.0
```

### 2.4 Dataset Structure
```
training_data/layout_b/
├── images/
│   ├── train/
│   │   ├── doc001_page0_tile_0_0.png
│   │   └── ...
│   └── val/
│       └── ...
├── labels/
│   ├── train/
│   │   ├── doc001_page0_tile_0_0.txt
│   │   └── ...
│   └── val/
│       └── ...
└── dataset.yaml
```

## Step 3: Model Training

### 3.1 Option A: Train From Scratch
For completely different layouts:

```python
from ultralytics import YOLO

# Start with pretrained backbone
model = YOLO('yolov8l-obb.pt')

# Train on your data
results = model.train(
    data='training_data/layout_b/dataset.yaml',
    epochs=120,
    imgsz=1024,
    batch=8,
    name='layout_b_v1',
    patience=20,
    # OBB-specific settings
    task='obb',
)
```

### 3.2 Option B: Fine-tune Existing Model
If layouts share some elements with Layout Type A:

```python
from ultralytics import YOLO

# Start with your Layout A model
model = YOLO('yolomodel/layout_a_best.pt')

# Fine-tune on combined dataset
results = model.train(
    data='training_data/combined/dataset.yaml',
    epochs=50,  # Fewer epochs for fine-tuning
    imgsz=1024,
    batch=8,
    name='layout_ab_combined_v1',
    freeze=10,  # Freeze first 10 layers
)
```

### 3.3 Option C: Multi-Task Learning
Train one model for multiple layout types:

```python
# Combine classes from both layouts
# Use class prefixes: a_signal, b_primary_signal
# Or train with layout-specific heads
```

### 3.4 Evaluate Model
```python
# Validate on test set
metrics = model.val(data='training_data/layout_b/dataset.yaml')
print(f"mAP50: {metrics.box.map50}")
print(f"mAP50-95: {metrics.box.map}")

# Per-class performance
for i, name in enumerate(model.names.values()):
    print(f"{name}: mAP50={metrics.box.maps[i]:.3f}")
```

## Step 4: Create Layout Profile

### 4.1 Copy Template
```bash
cp profiles/layout_type_b_template.yaml profiles/layout_type_b.yaml
```

### 4.2 Configure Based on Training Results
```yaml
# profiles/layout_type_b.yaml

name: "layout_type_b"
version: "1.0"
description: "New railway company track layout format"

model_path: "yolomodel/layout_b_v1/weights/best.pt"

model_classes:
  - primary_signal
  - secondary_signal
  - km_marker
  - track_id
  - text_label
  - switch
  - crossing

classes:
  primary_signal:
    # Set based on validation results
    # If mAP50 is 0.95, start with confidence_threshold around 0.7
    confidence_threshold: 0.7
    nms_threshold: 0.35
    requires_ocr: true
    id_pattern: "^[A-Z]{2}\\d{3}$"  # Based on observed patterns

  km_marker:
    confidence_threshold: 0.5
    nms_threshold: 0.3
    requires_ocr: true
    # Coordinate format for this layout
    id_pattern: "^\\d{1,3}\\.\\d{3}$"  # e.g., "123.456"

# ... configure all classes based on your analysis
```

### 4.3 Test OCR Configuration
```python
from core.layout_profile import LayoutProfileManager
from core.ocr_engine import paddleocr_recognize

# Load profile
manager = LayoutProfileManager()
profile = manager.load_profile("layout_type_b")

# Test OCR on sample crops
for sample in sample_crops:
    result = paddleocr_recognize(sample, profile.ocr)
    print(f"Detected: {result}")
    # Adjust ocr.denoise_strength, sharpen_amount based on results
```

## Step 5: Integration & Validation

### 5.1 Update Pipeline to Use Profiles
```python
# In pipelineworker.py, add profile support:
from core.layout_profile import LayoutProfileManager, LayoutProfile

class PipelineWorker(QThread):
    def __init__(self, ..., profile: Optional[LayoutProfile] = None):
        self.profile = profile or LayoutProfileManager().load_profile("layout_type_a")

    def _get_class_threshold(self, class_name: str) -> float:
        return self.profile.get_class_threshold(class_name)
```

### 5.2 Run Validation Pipeline
```python
# scripts/validate_layout.py
def validate_layout_extraction(pdf_path, profile_name, ground_truth):
    manager = LayoutProfileManager()
    profile = manager.load_profile(profile_name)

    # Run extraction
    results = extract_with_profile(pdf_path, profile)

    # Compare to ground truth
    metrics = calculate_metrics(results, ground_truth)
    print(f"Precision: {metrics['precision']:.2%}")
    print(f"Recall: {metrics['recall']:.2%}")
    print(f"F1: {metrics['f1']:.2%}")
```

### 5.3 Iterate and Refine
Based on validation results:
1. Adjust confidence thresholds for classes with low precision
2. Adjust NMS thresholds for overlapping detections
3. Refine OCR preprocessing for text recognition issues
4. Update linking rules for spatial relationship errors

## Advanced: Layout Auto-Detection

### Automatic Layout Type Detection
```python
from core.layout_profile import LayoutProfileManager

manager = LayoutProfileManager()

def detect_and_process(pdf_path):
    # Extract title block text (first page, bottom-right corner)
    title_text = extract_title_block(pdf_path)

    # Auto-detect layout type
    profile = manager.detect_layout(
        image=None,
        title_block_text=title_text
    )

    if profile:
        print(f"Detected layout type: {profile.name}")
    else:
        print("Unknown layout - using default")
        profile = manager.load_profile("layout_type_a")

    return process_with_profile(pdf_path, profile)
```

## Appendix: Methods for Text Extraction from New Layouts

### Method 1: PaddleOCR (Recommended)
Best for: German/Latin text, rotated text, varying fonts
```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(use_angle_cls=True, lang='german')
result = ocr.ocr(image, cls=True)
```

### Method 2: EasyOCR
Best for: Multi-language, simple layouts
```python
import easyocr
reader = easyocr.Reader(['de', 'en'])
result = reader.readtext(image)
```

### Method 3: Tesseract + Custom Training
Best for: Very specific fonts, when you have labeled text data
```bash
# Train custom Tesseract model
tesstrain.sh --lang deu_custom --training_text my_text.txt
```

### Method 4: TrOCR (Transformer-based)
Best for: Handwritten or degraded text
```python
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
processor = TrOCRProcessor.from_pretrained("microsoft/trocr-large-printed")
model = VisionEncoderDecoderModel.from_pretrained("microsoft/trocr-large-printed")
```

### Method 5: Custom CNN + CTC Loss
Best for: Very specific character sets, maximum accuracy
- Train character-level classifier
- Use CTC loss for sequence prediction

## Quick Reference: Adding New Layout Checklist

- [ ] Collect 20-50 sample documents
- [ ] Identify all visual element types
- [ ] Document element relationships
- [ ] Annotate training data (OBB format)
- [ ] Train/fine-tune YOLO model
- [ ] Evaluate model performance (target: mAP50 > 0.95)
- [ ] Create layout profile YAML
- [ ] Configure class thresholds based on mAP
- [ ] Configure OCR parameters
- [ ] Configure linking rules
- [ ] Add detection fingerprints
- [ ] Run validation pipeline
- [ ] Iterate until metrics meet targets
- [ ] Document any special handling requirements

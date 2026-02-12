# RailDoc Studio - Gleisplanextraktor v3
## Comprehensive Codebase Analysis for Master's Thesis Presentation

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Pattern](#2-architecture-pattern)
3. [Project Structure](#3-project-structure)
4. [Design Patterns Used](#4-design-patterns-used)
5. [Core Processing Pipeline](#5-core-processing-pipeline)
6. [Detection Classes](#6-detection-classes)
7. [Central Data Structure](#7-central-data-structure)
8. [Threading Model](#8-threading-model)
9. [Key Files by Importance](#9-key-files-by-importance)
10. [Database Schema](#10-database-schema)
11. [Error Handling Strategies](#11-error-handling-strategies)
12. [Angle-Aware Processing](#12-angle-aware-processing)
13. [Technology Stack](#13-technology-stack)
14. [Key Innovations](#14-key-innovations)
15. [Application Flow](#15-application-flow)
16. [Module Interactions](#16-module-interactions)
17. [Configuration Management](#17-configuration-management)
18. [UI Components Hierarchy](#18-ui-components-hierarchy)
19. [Image Processing Pipeline](#19-image-processing-pipeline)
20. [Validation System](#20-validation-system)

---

## 1. Project Overview

**RailDoc Studio - Gleisplanextraktor v3** is an intelligent railway document analysis system that automatically detects and extracts symbols, coordinates, and text from railway track layout plans (Gleispläne).

### Key Capabilities

- **Automatic Symbol Detection**: Uses YOLOv8-OBB for detecting 13 different railway symbol classes
- **Text Recognition**: PaddleOCR/Tesseract for extracting signal names, coordinates, and identifiers
- **Intelligent Linking**: Associates symbols with their corresponding coordinates
- **Human-in-the-Loop Validation**: Uncertain detections are flagged for user review
- **Custom Symbol Support**: Add new symbols without retraining the neural network
- **Export Functionality**: Excel export for technicians and engineers

---

## 2. Architecture Pattern

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  PRESENTATION LAYER (PyQt5)                  │
│                                                              │
│   MainWindow → SetupWindow → AuditingWindow → Workspace     │
│                                                              │
│   (User interface components, event handling, visualization) │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               │ Signals/Slots
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  BUSINESS LOGIC LAYER                        │
│                                                              │
│   PipelineWorker → YOLO Detection → OCR Engine → Linking    │
│                                                              │
│   Validation → Symbol Detection → Track Detection            │
│                                                              │
│   (Core algorithms, data processing, business rules)         │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               │ Read/Write
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                  DATA/PERSISTENCE LAYER                      │
│                                                              │
│   SQLite Database (track_layouts.db)                        │
│   Pandas DataFrame (in-memory detection results)            │
│   Image Files (PDF/PNG/JPG)                                 │
│   Configuration Files (JSON/YAML)                           │
│                                                              │
│   (Data storage, retrieval, and serialization)              │
└─────────────────────────────────────────────────────────────┘
```

### Benefits of This Architecture

| Benefit | Description |
|---------|-------------|
| **Separation of Concerns** | Each layer has a distinct responsibility |
| **Testability** | Business logic can be tested independently of UI |
| **Maintainability** | Changes in one layer don't affect others |
| **Scalability** | Easy to add new features or swap components |

---

## 3. Project Structure

```
Gleisplanextraktorv3/
│
├── main.py                        # Application entry point
├── config.py                      # Central configuration (17KB)
├── validation_config.py           # Shared validation rules
├── database_sqlite.py             # SQLite database management (36KB)
├── excelexport.py                 # Excel export functionality (148KB)
├── export_utils.py                # Export utilities
├── track_detection.py             # Railway track skeleton detection
├── table_editor.py                # Table editing utilities
├── requirements.txt               # Python dependencies
├── track_layouts.db               # SQLite database (1.7MB)
│
├── core/                          # Core Processing Pipeline
│   ├── pipelineworker.py         # Main orchestration thread (~2000 lines)
│   ├── yolo_detection.py         # YOLOv8-OBB object detection (~400 lines)
│   ├── ocr_engine.py             # PaddleOCR/Tesseract text recognition (~3000 lines)
│   ├── linking.py                # Symbol-coordinate association (~2500 lines)
│   ├── image_processing.py       # Image transformation utilities (~600 lines)
│   ├── symbol_detector.py        # Custom/template-based symbol detection (~1000 lines)
│   └── pipeline_integration.py   # Integration layer
│
├── ui/                            # User Interface (PyQt5)
│   ├── workspace_widget.py       # Main editing workspace (349KB - largest file)
│   ├── auditing_window.py        # Multi-tab management window
│   ├── setup_window.py           # PDF/image selection & analysis start
│   ├── graphics_view.py          # Interactive image viewer with zooming
│   ├── quality_inspector.py      # Quality metrics display
│   ├── tree_widget.py            # Detection results table
│   ├── resizable_bbox.py         # Interactive bounding box editing
│   ├── confidence_inspector.py   # Confidence analysis UI
│   ├── database_dialogs.py       # Database management dialogs
│   ├── new_symbol_dialog.py      # Custom symbol creation (70KB)
│   ├── ocr_adjustment_dialog.py  # OCR parameter tuning
│   ├── layout_wizard_dialog.py   # Layout setup wizard
│   ├── threshold_dialog.py       # Image threshold configuration
│   ├── bbox_context_menu.py      # Right-click menu for boxes
│   ├── draggable_tab_bar.py      # Tab widget with drag-to-pop
│   └── themes.py                 # Dark/Light theme definitions
│
├── uservalidation/               # Validation & Correction System
│   ├── ultimate_validator.py     # Combined OCR + YOLO validation
│   ├── validation_dialog2.py     # Results display dialog
│   ├── data_validator2.py        # Enhanced data validation
│   ├── missing_detection_analyzer.py  # Finds missing symbols
│   └── validation_dialog_helper.py    # Validation UI helper
│
├── utils/                         # Utility Functions
│   ├── helpers.py                # Angle detection, NMS, color masks
│   ├── dpi_utils.py              # DPI-aware window sizing
│   ├── rotation_utils.py         # Angle/rotation helpers
│   └── uuid_utils.py             # Deterministic UUID generation
│
├── pdfcomparison/                # PDF Version Comparison Module
│   ├── comparison_engine.py      # Layout change detection
│   └── dialogs.py                # Comparison UI dialogs
│
├── config/                        # Configuration Files
│   └── ocr_adjustments.json      # OCR learning patterns
│
├── profiles/                      # Layout Type Profiles
│   ├── layout_type_a.yaml
│   └── layout_type_b_template.yaml
│
└── docs/                          # Documentation
    ├── USER_MANUAL.md
    ├── OCR_ADJUSTMENT_SYSTEM.md
    ├── DPI_IMPLEMENTATION_STATUS.md
    └── [additional documentation files]
```

---

## 4. Design Patterns Used

### 4.1 Observer Pattern (PyQt Signals/Slots)

**Purpose**: Thread-safe communication between components

```python
# Subject emits signals
class PipelineWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int)      # 0-100%
    status = QtCore.pyqtSignal(str)        # Status messages
    done = QtCore.pyqtSignal(...)          # Results

    def run(self):
        self.progress.emit(35)
        self.status.emit("Processing page 2...")

# Observer listens
class SetupWindow(QWidget):
    def __init__(self):
        self.worker.progress.connect(self.on_progress)
        self.worker.done.connect(self.on_processing_complete)

    def on_progress(self, value):
        self.progress_bar.setValue(value)
```

### 4.2 Strategy Pattern (Angle-Aware OCR)

**Purpose**: Select algorithm at runtime based on detection angle

```python
def process_detection(detection, angle):
    # Strategy selection based on angle
    if is_cardinal(angle):  # Within ±15° of 0°/90°/180°/270°
        crop = rotated_crop_from_det(detection)
        params = CARDINAL_PARAMS
    else:  # Angular detection
        crop = perspective_crop_from_det(detection)
        params = ANGULAR_PARAMS

    # Class-specific OCR strategy
    if class_name == 'signal':
        return ocr_signal_name(crop, params)
    elif class_name in ['gks_gesteuert', 'gks_festkodiert']:
        return ocr_coordinate_unified(crop, params)
    else:
        return ocr_anchor_name(crop, params)
```

### 4.3 Factory Pattern

**Purpose**: Object creation abstraction

```python
def get_paddleocr_instance():
    """Lazy initialization factory for PaddleOCR"""
    global _paddle_instance
    if _paddle_instance is None:
        _paddle_instance = PaddleOCR(
            use_angle_cls=True,
            lang='de',
            show_log=False
        )
    return _paddle_instance
```

### 4.4 Template Method Pattern

**Purpose**: Define algorithm skeleton with customizable steps

```python
class UltimateValidator:
    def validate_all(self, df):
        """Template method - defines the validation sequence"""
        issues = []
        issues.extend(self.validate_ocr(df))
        issues.extend(self.validate_yolo(df))
        issues.extend(self.validate_linking(df))
        issues.extend(self.validate_template_matching(df))
        return issues

    def validate_ocr(self, df):
        # Subclasses can override
        pass
```

### 4.5 MVC Pattern (Model-View-Controller)

**Purpose**: Separation of data, presentation, and control logic

```
┌─────────────────────────────────────────────────────────┐
│                    WorkspaceWidget                       │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  MODEL: Pandas DataFrame                                 │
│    - Detection results (id, class, confidence, etc.)    │
│    - Stored in self.df                                  │
│                                                          │
│  VIEW: InteractiveGraphicsView + AuditingTreeWidget     │
│    - Graphics view shows image with bounding boxes      │
│    - Tree widget shows tabular detection data           │
│                                                          │
│  CONTROLLER: Signal handlers (slots)                    │
│    - on_cell_edited(row, col, value)                    │
│    - on_bbox_moved(detection_id, new_coords)            │
│    - on_validate_clicked()                              │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 4.6 Singleton-like Pattern

**Purpose**: Global configuration access

```python
# config.py - Acts as a singleton configuration module
CLASS_THRESH = {
    'signal': 0.40,
    'gm_block': 0.22,
    'haltetafel': 0.81,
    # ...
}

LINK_RULES = {
    'signal': {'mode': 'below', 'dx_multiplier': 1.0},
    'weichen_block': {'mode': 'inside', 'block': True},
    # ...
}

# Used throughout the codebase
from config import CLASS_THRESH, LINK_RULES
```

### 4.7 Command Pattern (Undo/Redo Support)

**Purpose**: Track user edits for reversibility

```python
# Each edit stored as a command in the database
class ManualCorrection:
    layout_id: int
    row_id: int
    column_name: str
    old_value: str
    new_value: str
    correction_type: str
    corrected_by: str = 'user'
    created_at: datetime
```

### 4.8 Data Transfer Object (DTO) Pattern

**Purpose**: Structured data passing between components

```python
# Detection dictionary - passed between pipeline stages
detection = {
    'name': 'signal',
    'cls': 0,
    'conf': 0.95,
    'x1': 100, 'y1': 50, 'x2': 150, 'y2': 100,
    'obb_cx': 125, 'obb_cy': 75,
    'obb_w': 50, 'obb_h': 50,
    'angle': 0.2,
    'anchor_text': 'A123',
    'coord_text': '0.1234 Gl.113',
    'detection_status': 'confirmed'
}
```

### Design Patterns Summary Table

| Pattern | Location | Purpose |
|---------|----------|---------|
| **Observer** | PyQt Signals/Slots everywhere | Thread-safe UI updates |
| **Strategy** | OCR engine, angle processing | Runtime algorithm selection |
| **Factory** | OCR instances, workers | Object creation abstraction |
| **Template Method** | UltimateValidator | Validation framework |
| **MVC** | WorkspaceWidget | Separation of concerns |
| **Singleton** | config.py globals | Central configuration |
| **Command** | manual_corrections table | Undo/redo support |
| **DTO** | Detection dictionaries | Data transfer |
| **Decorator** | db_cursor context manager | Resource management |
| **Composite** | ValidationIssue collections | Uniform handling |

---

## 5. Core Processing Pipeline

### Pipeline Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      INPUT: PDF/Image File                        │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    1. IMAGE PREPROCESSING                         │
│                                                                   │
│  • PDF → PIL Images (pdf2image)                                  │
│  • Color conversion: Colored pixels → Black (for YOLO)           │
│  • Resolution: 500 DPI for A0 layouts                            │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    2. TILING STRATEGY                             │
│                                                                   │
│  Large Image (e.g., 15000 × 10000 pixels)                        │
│       │                                                           │
│       ▼                                                           │
│  ┌─────┬─────┬─────┬─────┐                                       │
│  │Tile1│Tile2│Tile3│Tile4│  2048×2048 tiles                      │
│  ├─────┼─────┼─────┼─────┤  40% overlap                          │
│  │Tile5│Tile6│Tile7│Tile8│  320px halo (context)                 │
│  └─────┴─────┴─────┴─────┘                                       │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    3. YOLO DETECTION                              │
│                                                                   │
│  For each tile:                                                   │
│    • YOLOv8-OBB prediction (imgsz=1024)                          │
│    • Extract: cx, cy, w, h, theta (rotation)                     │
│    • Confidence filtering (two-stage)                            │
│    • Coordinate transformation (tile → global)                   │
│                                                                   │
│  After all tiles:                                                 │
│    • Non-Maximum Suppression (NMS) across tiles                  │
│    • Merge overlapping detections                                │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│              4. PARALLEL OCR (ThreadPoolExecutor)                 │
│                                                                   │
│  ┌────────────────────────────────────────────────────────┐      │
│  │  Thread Pool: max(2, min(16, cpu_count())) workers     │      │
│  │                                                         │      │
│  │  Detection 1 ──► OCR Worker 1 ──► "A123"               │      │
│  │  Detection 2 ──► OCR Worker 2 ──► "0.1234"             │      │
│  │  Detection 3 ──► OCR Worker 3 ──► "GKS004"             │      │
│  │  Detection 4 ──► OCR Worker 4 ──► "Gl.113"             │      │
│  │  ...                                                    │      │
│  └────────────────────────────────────────────────────────┘      │
│                                                                   │
│  Per detection:                                                   │
│    • Extract crop (rotated or perspective based on angle)        │
│    • Class-specific preprocessing                                │
│    • PaddleOCR recognition                                       │
│    • Text post-processing                                        │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    5. LINKING ENGINE                              │
│                                                                   │
│  Symbol ←──────────────────────────────────────→ Coordinate      │
│                                                                   │
│  • Class-specific linking rules (LINK_RULES)                     │
│  • Direction detection (Fahrtrichtung):                          │
│    - GKS-based: Find nearby GKS → infer direction                │
│    - Track skeleton: Perpendicular raycast                       │
│    - Numeric comparison: Ascending/descending coordinates        │
│  • Weichen block special handling (multi-line coordinates)       │
│  • Duplicate merging                                             │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    6. RESULTS DATAFRAME                           │
│                                                                   │
│  Convert List[dict] → pandas.DataFrame                           │
│                                                                   │
│  Columns: id, cls, name, conf, ax1, ay1, ax2, ay2,              │
│           obb_cx, obb_cy, obb_w, obb_h, angle,                   │
│           anchor_text, coord_text, coord_value,                  │
│           fahrtrichtung, detection_status, ...                   │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    7. USER VALIDATION                             │
│                                                                   │
│  • Display in WorkspaceWidget                                    │
│  • User reviews uncertain detections                             │
│  • Manual corrections → stored in database                       │
│  • Quality metrics calculation                                   │
└──────────────────────────────────┬───────────────────────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    8. EXPORT                                      │
│                                                                   │
│  • Excel (.xlsx) with openpyxl                                   │
│  • Three presets: Techniker, Basic, Technical                    │
│  • Filtering by class                                            │
└──────────────────────────────────────────────────────────────────┘
```

### Confidence Two-Stage Filtering

```
Detection Confidence
        │
        ▼
   conf >= CLASS_THRESH[class]?
        │
    ┌───┴───┐
    │ YES   │ NO
    ▼       ▼
CONFIRMED   conf >= UNCERTAIN_THRESH[class]?
    │               │
    │           ┌───┴───┐
    │           │ YES   │ NO
    │           ▼       ▼
    │       UNCERTAIN   DISCARDED
    │           │
    └─────┬─────┘
          │
          ▼
    User Review
    (Uncertain items flagged)
```

---

## 6. Detection Classes

### The 13 Object Classes

| ID | Class Name | German | Description | Confidence Threshold |
|----|------------|--------|-------------|---------------------|
| 0 | `signal` | Signal | Railway signals (A123, etc.) | 0.40 |
| 1 | `gm_block` | GM Block | Ground marker blocks | 0.22 |
| 2 | `gks_festkodiert` | GKS Festkodiert | Fixed-coded GKS markers | 0.50 |
| 3 | `gks_gesteuert` | GKS Gesteuert | Controlled GKS markers | 0.50 |
| 4 | `weichen_block` | Weichenblock | Switch/turnout blocks | 0.45 |
| 5 | `isolierstoß` | Isolierstoß | Insulated rail joints | 0.35 |
| 6 | `haltepunkt` | Haltepunkt | Stop points/stations | 0.60 |
| 7 | `sverbinder` | S-Verbinder | S-connectors | 0.40 |
| 8 | `coordinate` | Koordinate | Coordinate markers | 0.30 |
| 9 | `prellbock` | Prellbock | Buffer stops | 0.55 |
| 10 | `haltetafel` | Haltetafel | Stop signs/boards | 0.81 |
| 11 | `weichenende` | Weichenende | Switch ends | 0.45 |
| 12 | `weichengruppenende` | Weichengruppenende | Switch group ends | 0.45 |

### Class-Specific Processing

```python
# Classes that don't need OCR
NO_OCR_CLASSES = ['coordinate', 'isolierstoß']

# Classes requiring coordinate linking
CLASSES_REQUIRING_COORDINATES = [
    'signal', 'gm_block', 'gks_festkodiert', 'gks_gesteuert',
    'haltepunkt', 'sverbinder', 'prellbock', 'haltetafel',
    'weichenende', 'weichengruppenende', 'isolierstoß'
]

# Classes requiring text extraction
CLASSES_REQUIRING_TEXT = ['signal', 'gks_gesteuert', 'gks_festkodiert']
```

---

## 7. Central Data Structure

### Detection DataFrame Schema

```python
DataFrame Columns:
│
├── IDENTITY
│   ├── id              # Deterministic UUID (based on layout name)
│   ├── cls             # YOLO class ID (0-12)
│   └── name            # Class name string
│
├── SPATIAL - ANCHOR/SYMBOL BOX
│   ├── ax1, ay1        # Top-left corner (pixels)
│   ├── ax2, ay2        # Bottom-right corner (pixels)
│   ├── obb_cx, obb_cy  # Oriented bounding box center
│   ├── obb_w, obb_h    # OBB width and height
│   ├── obb_rot_w       # Rotated width
│   ├── obb_rot_h       # Rotated height
│   ├── angle           # Normalized angle [-45°, 45°]
│   └── angle_raw       # Raw angle from YOLO
│
├── SPATIAL - COORDINATE LINK BOX
│   ├── cx1, cy1        # Linked coordinate box top-left
│   └── cx2, cy2        # Linked coordinate box bottom-right
│
├── OCR RESULTS
│   ├── anchor_text     # Symbol identifier ("A123", "GKS004")
│   ├── coord_text      # Coordinate as text ("0.1234 Gl.113")
│   ├── coord_value     # Parsed numeric value (0.1234)
│   ├── gi_gl           # Track reference ("GI", "GL")
│   └── weichen_coordinates  # Multi-line weichen block data
│
├── CONTEXT
│   ├── fahrtrichtung   # Direction (up/down/left/right)
│   ├── color           # Detected color (red/yellow/none)
│   └── page            # PDF page number
│
├── QUALITY METRICS
│   ├── conf            # Detection confidence (0.0-1.0)
│   ├── detection_status # 'confirmed' or 'uncertain'
│   └── is_custom_symbol # True if template-matched
│
└── METADATA
    ├── notes           # User annotations
    ├── layout_name     # Source layout identifier
    └── [correction tracking fields]
```

### Example Detection Record

```python
{
    'id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    'cls': 0,
    'name': 'signal',
    'conf': 0.95,
    'ax1': 1234, 'ay1': 567, 'ax2': 1298, 'ay2': 631,
    'obb_cx': 1266, 'obb_cy': 599,
    'obb_w': 64, 'obb_h': 64,
    'angle': 0.05,
    'anchor_text': 'A123',
    'coord_text': '0.1234 Gl.113',
    'coord_value': 0.1234,
    'gi_gl': 'Gl',
    'fahrtrichtung': 'up',
    'color': 'none',
    'page': 1,
    'detection_status': 'confirmed',
    'is_custom_symbol': False,
    'notes': ''
}
```

---

## 8. Threading Model

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         MAIN THREAD                              │
│                                                                  │
│   PyQt5 Event Loop                                              │
│   ├── UI Rendering                                              │
│   ├── User Input Handling                                       │
│   └── Signal/Slot Dispatch                                      │
│                                                                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
              Signals ↑   │   ↓ Start/Stop
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                    PipelineWorker (QThread)                      │
│                                                                  │
│   Background Processing                                          │
│   ├── YOLO Detection                                            │
│   ├── Custom Symbol Detection                                   │
│   └── Track Skeleton Detection                                  │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │              ThreadPoolExecutor (OCR)                    │   │
│   │                                                          │   │
│   │   Workers: max(2, min(16, os.cpu_count()))              │   │
│   │                                                          │   │
│   │   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │   │
│   │   │ Worker 1 │ │ Worker 2 │ │ Worker 3 │ │ Worker N │  │   │
│   │   │  OCR     │ │  OCR     │ │  OCR     │ │  OCR     │  │   │
│   │   └──────────┘ └──────────┘ └──────────┘ └──────────┘  │   │
│   │                                                          │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Signal Communication

```python
class PipelineWorker(QtCore.QThread):
    # Signals for thread-safe communication
    progress = QtCore.pyqtSignal(int)           # Progress percentage
    status = QtCore.pyqtSignal(str)             # Status message
    page_processed = QtCore.pyqtSignal(...)     # Per-page results
    done = QtCore.pyqtSignal(                   # Final results
        object,  # DataFrame
        object,  # page_base_pix dict
        object,  # page_dfs dict
        object,  # page_bgr_arrays dict
        object,  # track_skeleton
        object,  # exception (if any)
        bool,    # has_uncertain
        object,  # learned_patterns
        object   # additional data
    )

    def run(self):
        try:
            # Emit progress updates
            self.progress.emit(10)
            self.status.emit("Loading image...")

            # ... processing ...

            self.progress.emit(100)
            self.done.emit(results...)
        except Exception as e:
            self.done.emit(None, None, None, None, None, e, ...)
```

### Thread Safety Considerations

| Aspect | Implementation |
|--------|----------------|
| **UI Updates** | Always via signals (never direct from worker) |
| **Data Sharing** | DataFrame copied, not shared |
| **Cancellation** | `requestInterruption()` + periodic checks |
| **OCR Parallel** | Thread-safe PaddleOCR instance per worker |

---

## 9. Key Files by Importance

### Critical Files

| File | Size | Lines | Responsibility |
|------|------|-------|----------------|
| `ui/workspace_widget.py` | 349 KB | ~8000+ | Main editing interface, graphics view, detection table |
| `excelexport.py` | 148 KB | ~3500 | Excel export with multiple presets |
| `core/ocr_engine.py` | ~100 KB | ~3000 | OCR with class-specific preprocessing |
| `core/linking.py` | ~80 KB | ~2500 | Symbol-coordinate association algorithms |
| `core/pipelineworker.py` | ~70 KB | ~2000 | Pipeline orchestration thread |
| `database_sqlite.py` | 36 KB | ~1000 | SQLite persistence layer |
| `config.py` | 17 KB | ~500 | Central configuration |

### Module Dependencies

```
main.py
    │
    ├── ui/setup_window.py
    │       │
    │       └── core/pipelineworker.py
    │               │
    │               ├── core/yolo_detection.py
    │               ├── core/ocr_engine.py
    │               ├── core/linking.py
    │               ├── core/image_processing.py
    │               └── core/symbol_detector.py
    │
    └── ui/auditing_window.py
            │
            └── ui/workspace_widget.py
                    │
                    ├── ui/graphics_view.py
                    ├── ui/tree_widget.py
                    ├── ui/resizable_bbox.py
                    └── uservalidation/ultimate_validator.py
```

---

## 10. Database Schema

### SQLite Database: `track_layouts.db`

```sql
-- Layout registry (master table)
CREATE TABLE track_layouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layout_name TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Saved analysis results (serialized DataFrame)
CREATE TABLE workspaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layout_id INTEGER UNIQUE,
    edited_data_json TEXT NOT NULL,        -- JSON-serialized DataFrame
    track_skeleton TEXT,                    -- Base64-encoded skeleton image
    image_dimensions TEXT,                  -- JSON: {width, height}
    last_modified TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(layout_id) REFERENCES track_layouts(id) ON DELETE CASCADE
);

-- Validation results history
CREATE TABLE validation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layout_id INTEGER NOT NULL,
    validation_type TEXT,                   -- 'ocr', 'yolo', 'linking', etc.
    severity TEXT CHECK (severity IN ('ERROR', 'WARNING', 'INFO')),
    message TEXT,
    row_id INTEGER,                         -- Detection row reference
    details TEXT,                           -- JSON: additional context
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(layout_id) REFERENCES track_layouts(id) ON DELETE CASCADE
);

-- Quality metrics per layout
CREATE TABLE quality_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layout_id INTEGER NOT NULL,
    metric_name TEXT,                       -- 'avg_confidence', 'missing_coords', etc.
    metric_value REAL,
    metric_data TEXT,                       -- JSON: detailed breakdown
    computed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(layout_id) REFERENCES track_layouts(id) ON DELETE CASCADE
);

-- User corrections history (for undo/redo and learning)
CREATE TABLE manual_corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    layout_id INTEGER NOT NULL,
    row_id INTEGER NOT NULL,                -- Detection row
    column_name TEXT,                       -- Which field was edited
    old_value TEXT,
    new_value TEXT,
    correction_type TEXT,                   -- 'manual', 'auto_suggested', etc.
    corrected_by TEXT DEFAULT 'user',
    correction_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(layout_id) REFERENCES track_layouts(id) ON DELETE CASCADE
);

-- Custom symbol library
CREATE TABLE custom_symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    config TEXT,                            -- JSON: detection parameters
    templates TEXT,                         -- Serialized template images
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

### Database Access Pattern

```python
from contextlib import contextmanager

@contextmanager
def db_cursor(commit=False):
    """Context manager for safe database access"""
    conn = sqlite3.connect('track_layouts.db')
    conn.row_factory = sqlite3.Row  # Dict-like access
    try:
        cursor = conn.cursor()
        yield cursor
        if commit:
            conn.commit()
    finally:
        conn.close()

# Usage
with db_cursor(commit=True) as cursor:
    cursor.execute("INSERT INTO track_layouts (layout_name) VALUES (?)", (name,))
```

---

## 11. Error Handling Strategies

### 1. Thread-Safe Error Propagation

```python
class PipelineWorker(QtCore.QThread):
    done = QtCore.pyqtSignal(..., object, ...)  # exception parameter

    def run(self):
        try:
            # Processing logic
            result = self.process_page()
            self.done.emit(result, ..., None, ...)  # No exception
        except Exception as e:
            # Error propagates through signal
            self.done.emit(None, ..., e, ...)

# In UI
def on_processing_done(self, df, ..., exception, ...):
    if exception:
        QMessageBox.critical(self, "Error", str(exception))
        return
    # Continue with results
```

### 2. Graceful Degradation (Fallback Chain)

```python
def perform_ocr(crop, class_name):
    """OCR with multiple fallbacks"""
    # Primary: PaddleOCR
    try:
        text, conf = paddleocr_recognize(crop)
        if conf > 0.5:
            return text, conf
    except Exception as e:
        log_debug('ocr', f"PaddleOCR failed: {e}")

    # Fallback 1: Tesseract
    try:
        text, conf = tesseract_recognize(crop)
        if conf > 0.3:
            return text, conf
    except Exception as e:
        log_debug('ocr', f"Tesseract failed: {e}")

    # Fallback 2: Return empty
    return "", 0.0
```

### 3. Validation-Based Error Reporting

```python
class ValidationIssue:
    detection_id: str
    severity: str  # 'ERROR', 'WARNING', 'INFO'
    category: str  # 'ocr', 'linking', 'confidence'
    message: str
    suggestion: str

def validate_all(df):
    """Collect issues instead of throwing exceptions"""
    issues = []

    for idx, row in df.iterrows():
        if row['conf'] < CLASS_THRESH[row['name']]:
            issues.append(ValidationIssue(
                detection_id=row['id'],
                severity='WARNING',
                category='confidence',
                message=f"Low confidence: {row['conf']:.2f}",
                suggestion="Review this detection manually"
            ))

    return issues  # Let UI display all issues
```

### 4. Debug Logging System

```python
# config.py
DEBUG_SIGNALS = False
DEBUG_OCR = False
DEBUG_LINKING = False
DEBUG_YOLO = False
# ... other debug flags

_DEBUG_FILE = None

def debug_print(category: str, message: str):
    """Centralized debug output"""
    flag_name = f"DEBUG_{category.upper()}"
    if not globals().get(flag_name, False):
        return

    global _DEBUG_FILE
    if _DEBUG_FILE is None:
        _DEBUG_FILE = open('debug.txt', 'w', encoding='utf-8')

    timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
    _DEBUG_FILE.write(f"[{timestamp}][{category.upper()}] {message}\n")
    _DEBUG_FILE.flush()
```

---

## 12. Angle-Aware Processing

### Problem Statement

Railway layout symbols can be rotated at various angles. Standard OCR fails on rotated text.

### Solution: Angle-Based Strategy Selection

```
Detection Angle (from YOLO OBB)
            │
            ▼
    ┌───────────────────┐
    │ Angle Normalization│
    │ [-90°,90°] → [-45°,45°]│
    └─────────┬─────────┘
              │
              ▼
    ┌─────────────────────────────────┐
    │         Is Cardinal?            │
    │  (within ±15° of 0°/90°/180°/270°)│
    └─────────┬───────────────────────┘
              │
      ┌───────┴───────┐
      │               │
      ▼               ▼
  CARDINAL        ANGULAR
      │               │
      ▼               ▼
┌─────────────┐ ┌─────────────┐
│ rotated_crop│ │perspective_ │
│ _from_det() │ │crop_from_det│
└─────────────┘ └─────────────┘
      │               │
      ▼               ▼
┌─────────────┐ ┌─────────────┐
│CARDINAL_PARAMS│ │ANGULAR_PARAMS│
│ - padding: 8  │ │ - padding: 12│
│ - expansion: 1│ │ - expansion: 2│
└─────────────┘ └─────────────┘
```

### Angle Normalization Algorithm

```python
def normalize_angle(raw_angle):
    """
    YOLO OBB outputs angle in [-90°, 90°]
    We normalize to [-45°, 45°] for consistent processing
    """
    angle = raw_angle
    width, height = obb_w, obb_h

    # If angle > 45°, rotate by -90° and swap dimensions
    if angle > 45:
        angle -= 90
        width, height = height, width
    elif angle < -45:
        angle += 90
        width, height = height, width

    return angle, width, height
```

### Cardinal vs Angular Parameters

```python
# config.py
CARDINAL_PARAMS = {
    'detection_padding': 8,
    'expansion_factor': 1.0,
    'preprocessing': 'standard',
    'crop_method': 'rotated'
}

ANGULAR_PARAMS = {
    'detection_padding': 12,
    'expansion_factor': 1.5,
    'preprocessing': 'aggressive',
    'crop_method': 'perspective'
}
```

---

## 13. Technology Stack

### Core Technologies

| Category | Technology | Version | Purpose |
|----------|------------|---------|---------|
| **GUI Framework** | PyQt5 | 5.15+ | Cross-platform desktop UI |
| **Object Detection** | YOLOv8-OBB | ultralytics 8.4.6 | Oriented bounding box detection |
| **Deep Learning** | PyTorch | 2.1.2 | Neural network backend |
| **OCR - Primary** | PaddleOCR | 2.7.0 | Text recognition (German) |
| **OCR - Fallback** | Tesseract | pytesseract 0.3.13 | Backup OCR engine |
| **Image Processing** | OpenCV | 4.6.0 | Image manipulation |
| **Data Processing** | Pandas | 2.3.3 | DataFrame operations |
| **Database** | SQLite | Built-in | Local persistence |
| **PDF Processing** | PyMuPDF | 1.23.26 | PDF rendering |
| **Excel Export** | openpyxl | 3.1.5 | XLSX file creation |

### Full Dependencies (requirements.txt)

```
# Deep Learning & Computer Vision
ultralytics==8.4.6          # YOLOv8
torch==2.1.2                # PyTorch
torchvision==0.16.2         # Vision utilities
paddleocr==2.7.0.3          # PaddleOCR
paddlepaddle==2.6.2         # Paddle framework
opencv-python==4.6.0.66     # OpenCV
opencv-contrib-python==4.6.0.66
scikit-image==0.26.0        # Image processing

# OCR & Text
easyocr==1.7.2              # Alternative OCR
pytesseract==0.3.13         # Tesseract wrapper

# PDF & Document
PyMuPDF==1.23.26            # PDF rendering
pdf2image==1.17.0           # PDF to image
openpyxl==3.1.5             # Excel files

# Data Processing
pandas==2.3.3               # DataFrames
numpy==1.26.4               # Numeric arrays
scipy==1.17.0               # Scientific computing

# Configuration
PyYAML==6.0.3               # YAML parsing

# Utilities
Pillow==12.1.0              # PIL imaging
shapely==2.1.2              # Geometric operations
tqdm==4.67.1                # Progress bars
```

---

## 14. Key Innovations

### 1. Tiling Strategy for Large Images

**Problem**: A0 railway layouts at 500 DPI = 15000×10000+ pixels. YOLO can't process this directly.

**Solution**: Intelligent tiling with overlap

```
┌────────────────────────────────────────────────┐
│                                                │
│   ┌────────┬────────┬────────┐                │
│   │ Tile 1 │ Tile 2 │ Tile 3 │  2048×2048    │
│   │   ↔40% overlap↔          │                │
│   ├────────┼────────┼────────┤                │
│   │ Tile 4 │ Tile 5 │ Tile 6 │  +320px halo  │
│   │        │        │        │  (context)     │
│   └────────┴────────┴────────┘                │
│                                                │
│   After detection:                            │
│   • Transform coordinates: tile → global      │
│   • NMS across all tiles                      │
│   • Merge duplicates from overlap zones       │
│                                                │
└────────────────────────────────────────────────┘
```

### 2. Oriented Bounding Box (OBB) Detection

**Problem**: Standard AABB fails for rotated symbols

**Solution**: YOLOv8-OBB outputs (cx, cy, w, h, θ)

```
Standard AABB:              OBB:
┌─────────────┐             ╱╲
│  ╱╲         │            ╱  ╲
│ ╱  ╲        │           ╱    ╲
│╱    ╲       │          ╱      ╲
│      ╲      │         ╱________╲
│       ╲     │
└─────────────┘         Tight fit = better OCR crops
Wasted space
```

### 3. Two-Stage Confidence Filtering

**Problem**: Single threshold loses valid detections OR includes too much noise

**Solution**: Confirmed + Uncertain categories

```python
CLASS_THRESH = {'signal': 0.40, ...}          # Confirmed threshold
UNCERTAIN_MULTIPLIER = 0.5                     # Uncertain = 0.5 × thresh

# Result:
# conf >= 0.40 → CONFIRMED (green)
# 0.20 <= conf < 0.40 → UNCERTAIN (yellow, flagged for review)
# conf < 0.20 → DISCARDED
```

### 4. Custom Symbol Detection Without Retraining

**Problem**: Adding new symbol types requires expensive YOLO retraining

**Solution**: Template matching + contour matching system

```python
class NewSymbolDetector:
    def detect(self, image, symbol_definitions):
        results = []
        for symbol in symbol_definitions:
            if symbol.method == 'template':
                matches = cv2.matchTemplate(image, symbol.template, cv2.TM_CCOEFF_NORMED)
                # Filter by threshold
            elif symbol.method == 'contour':
                # Hu moments matching
                pass
        return results
```

### 5. Track Skeleton-Based Direction Detection

**Problem**: Determine signal direction (Fahrtrichtung) automatically

**Solution**: Detect track centerlines and use perpendicular raycasting

```
Track Skeleton Detection:
1. Binarize image
2. Distance transform (find track width)
3. Filter by track width (6-20px)
4. Skeletonize to 1-pixel lines

Direction Detection:
• From signal position, cast rays perpendicular to tracks
• Determine which side has ascending/descending coordinates
• Infer up/down/left/right direction
```

### 6. Class-Specific OCR Preprocessing

**Problem**: One-size-fits-all preprocessing fails for different symbol types

**Solution**: Tailored preprocessing per class

```python
def preprocess_for_class(image, class_name):
    if class_name in ['gks_gesteuert', 'gks_festkodiert']:
        # GKS: Remove frame lines, dilate digits
        image = remove_horizontal_lines(image)
        image = cv2.dilate(image, kernel_3x3)
    elif class_name == 'signal':
        # Signal: Light sharpening only
        image = sharpen(image, amount=1.3)
    elif class_name == 'weichen_block':
        # Weichen: Handle multi-line text
        image = enhance_contrast(image, clip=3.0)
    return image
```

---

## 15. Application Flow

### Startup Sequence

```
main.py
    │
    ├── Configure PIL (disable decompression bomb check)
    │
    ├── QApplication setup
    │   ├── High DPI scaling enabled
    │   └── Fusion style (cross-platform)
    │
    ├── Database initialization (init_db())
    │
    └── MainWindow()
            │
            └── SetupAndRunWindow (central widget)
                    │
                    └── [User interaction begins]
```

### User Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. SELECT INPUT                                                  │
│    • Click "PDF auswählen" or "Bild auswählen"                  │
│    • Preview displayed in graphics view                         │
│    • Page navigation for multi-page PDFs                        │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. CONFIGURE ANALYSIS                                           │
│    • Select YOLO model (dropdown)                               │
│    • Select OCR engine (PaddleOCR/EasyOCR/Tesseract)           │
│    • Optional: Load layout profile                              │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. RUN ANALYSIS                                                  │
│    • Click "Analyse starten"                                    │
│    • Progress bar updates (0-100%)                              │
│    • Status log shows current operation                         │
│    • [Runs in background thread]                                │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. REVIEW RESULTS (AuditingWindow)                              │
│    • Each layout opens as a tab                                 │
│    • Left: Image with detection overlays                        │
│    • Right: Detection table (sortable, filterable)              │
│    • Uncertain detections highlighted in yellow                 │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. EDIT & CORRECT                                               │
│    • Click detection → highlights in both views                 │
│    • Edit text directly in table cells                          │
│    • Drag bounding box handles to resize                        │
│    • Right-click → context menu (delete, re-OCR, etc.)         │
│    • Run validation → see issues and suggestions                │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. EXPORT                                                        │
│    • Click "Excel Export"                                       │
│    • Choose preset (Techniker/Basic/Technical)                  │
│    • Filter by class if needed                                  │
│    • Save .xlsx file                                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 16. Module Interactions

### Signal Flow Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          SetupAndRunWindow                            │
│                                                                       │
│  [Start Analysis Button]                                             │
│         │                                                             │
│         ▼                                                             │
│  Creates PipelineWorker(file_path, model, ocr_engine)                │
│         │                                                             │
│         │ worker.progress.connect(self.update_progress)              │
│         │ worker.status.connect(self.update_status)                  │
│         │ worker.done.connect(self.on_processing_done)               │
│         │                                                             │
│         ▼                                                             │
│  worker.start()  ─────────────────────────────────────────────┐      │
│                                                                │      │
└────────────────────────────────────────────────────────────────│──────┘
                                                                 │
                                                                 ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          PipelineWorker                               │
│                                                                       │
│  def run(self):                                                      │
│      self.progress.emit(10)  ────────────────────► Progress Bar      │
│      self.status.emit("Loading...")  ────────────► Status Label      │
│                                                                       │
│      # YOLO Detection                                                │
│      detections = run_yolo_on_page(image)                           │
│      self.progress.emit(40)                                          │
│                                                                       │
│      # OCR                                                           │
│      for det in detections:                                          │
│          det['text'] = ocr_for_class(det)                           │
│      self.progress.emit(70)                                          │
│                                                                       │
│      # Linking                                                       │
│      linked = link_detections(detections)                           │
│      self.progress.emit(90)                                          │
│                                                                       │
│      # Done                                                          │
│      self.done.emit(df, images, ...)  ───────────────────────┐      │
│                                                               │      │
└───────────────────────────────────────────────────────────────│──────┘
                                                                │
                                                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        on_processing_done()                           │
│                                                                       │
│  def on_processing_done(self, df, images, ...):                      │
│      # Create AuditingWindow                                         │
│      self.auditing_window = AuditingWindow()                        │
│      self.auditing_window.add_layout_tab(df, images)                │
│      self.auditing_window.show()                                    │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                                                                │
                                                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                          AuditingWindow                               │
│                                                                       │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                      WorkspaceWidget                            │  │
│  │                                                                 │  │
│  │  ┌─────────────────────┐  ┌──────────────────────────────────┐│  │
│  │  │InteractiveGraphicsView│  │    AuditingTreeWidget           ││  │
│  │  │                     │  │                                  ││  │
│  │  │  [Click on box]     │  │  [Click on row]                 ││  │
│  │  │       │             │  │       │                         ││  │
│  │  │       ▼             │  │       ▼                         ││  │
│  │  │  item_selected ─────────────► select_row()               ││  │
│  │  │                     │  │                                  ││  │
│  │  │  ◄──────────────────────── row_clicked                   ││  │
│  │  │  zoom_to_detection  │  │                                  ││  │
│  │  │                     │  │                                  ││  │
│  │  └─────────────────────┘  └──────────────────────────────────┘│  │
│  │                                                                 │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 17. Configuration Management

### Configuration Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                    config.py (Highest Priority)                  │
│                                                                  │
│  Hard-coded defaults for:                                       │
│  • CLASS_THRESH (confidence thresholds)                         │
│  • NMS_THRESH (non-max suppression)                             │
│  • LINK_RULES (linking parameters)                              │
│  • Processing parameters (TILE_SIZE, DPI, etc.)                 │
│  • Debug flags                                                   │
│                                                                  │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              validation_config.py (Shared Rules)                 │
│                                                                  │
│  Validation-specific configuration:                             │
│  • CLASSES_REQUIRING_COORDINATES                                │
│  • CLASSES_REQUIRING_TEXT                                       │
│  • Risk weighting factors                                       │
│  • Risk thresholds (HIGH/MEDIUM/LOW)                           │
│                                                                  │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│            config/ocr_adjustments.json (Learned Patterns)        │
│                                                                  │
│  {                                                               │
│    "0|234": "0.234",      // OCR correction patterns            │
│    "Gl,113": "Gl.113",    // Common OCR errors                  │
│    ...                                                           │
│  }                                                               │
│                                                                  │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              profiles/*.yaml (Layout-Specific)                   │
│                                                                  │
│  layout_type_a.yaml:                                            │
│    legend_position: right                                       │
│    legend_width_percent: 15                                     │
│    coordinate_format: "0.000"                                   │
│    ...                                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Configuration Parameters

```python
# config.py excerpts

# Processing
TILE_SIZE = 2048              # Match training resolution
OVERLAP_PCT = 0.40            # 40% overlap between tiles
TILE_HALO = 320               # Extra context pixels
DPI = 500                     # A0 scanning resolution
PRED_IMGSZ = 1024             # YOLO prediction size

# Legend Exclusion
EXCLUDE_LEGEND_STRIP = True
LEGEND_STRIP_WIDTH_PERCENT = 12
LEGEND_STRIP_MAX_PIXELS = 4200

# Confidence Thresholds (per class)
CLASS_THRESH = {
    'signal': 0.40,
    'gm_block': 0.22,
    'gks_festkodiert': 0.50,
    'gks_gesteuert': 0.50,
    'weichen_block': 0.45,
    'isolierstoß': 0.35,
    'haltepunkt': 0.60,
    'sverbinder': 0.40,
    'coordinate': 0.30,
    'prellbock': 0.55,
    'haltetafel': 0.81,
    'weichenende': 0.45,
    'weichengruppenende': 0.45,
}

# Linking Rules (per class)
LINK_RULES = {
    'signal': {'mode': 'below', 'dx_multiplier': 1.0},
    'weichen_block': {'mode': 'inside', 'block': True},
    'weichenende': {'mode': 'either', 'dx_multiplier': 3.0, 'prefer_horizontal': True},
    'prellbock': {'mode': 'right_or_below', 'dx_multiplier': 2.0},
    # ...
}
```

---

## 18. UI Components Hierarchy

### Complete Widget Tree

```
QApplication
│
└── MainWindow (QMainWindow)
    │
    ├── QMenuBar
    │   └── "Ansicht" Menu
    │       ├── "Dunkles Thema" (Dark theme toggle)
    │       └── "Helles Thema" (Light theme toggle)
    │
    └── Central Widget (QStackedWidget or direct)
        │
        ├── SetupAndRunWindow (QWidget) ─────── [Initial View]
        │   │
        │   ├── QToolBar
        │   │   ├── "PDF auswählen" Button
        │   │   ├── "Bild auswählen" Button
        │   │   ├── Model Selection (QComboBox)
        │   │   ├── OCR Engine Selection (QComboBox)
        │   │   └── "Analyse starten" Button
        │   │
        │   ├── QGraphicsView (PDF Preview)
        │   │   └── QGraphicsScene
        │   │       └── QGraphicsPixmapItem
        │   │
        │   ├── Page Navigation
        │   │   ├── "◄" Button (Previous)
        │   │   ├── QLabel ("Page 1 of 3")
        │   │   └── "►" Button (Next)
        │   │
        │   ├── QProgressBar
        │   │
        │   ├── QTextEdit (Status Log)
        │   │
        │   └── "Workspace laden" Button
        │
        └── AuditingWindow (QMainWindow) ─────── [After Processing]
            │
            ├── QMenuBar
            │   ├── "Datei" Menu
            │   │   ├── "Speichern"
            │   │   ├── "Laden"
            │   │   └── "Exportieren"
            │   │
            │   ├── "Ansicht" Menu
            │   │   ├── Zoom controls
            │   │   └── Theme toggle
            │   │
            │   ├── "Werkzeuge" Menu
            │   │   ├── "Validierung"
            │   │   └── "Qualitätsprüfung"
            │   │
            │   └── "Datenbank" Menu
            │       ├── "Workspace öffnen"
            │       └── "Workspace speichern"
            │
            ├── QToolBar
            │   ├── Zoom In/Out/Reset
            │   ├── "Validieren" Button
            │   ├── "Qualität" Button
            │   ├── "Excel Export" Button
            │   ├── Filter/Search (QLineEdit)
            │   └── Undo/Redo Buttons
            │
            ├── QStatusBar
            │   ├── Row Count Label
            │   ├── Selection Count Label
            │   └── Status Message Label
            │
            └── DraggableTabWidget (QTabWidget) ─── [Multi-Layout Tabs]
                │
                └── WorkspaceWidget (QWidget) ─── [Per Layout Tab]
                    │
                    └── QSplitter (Horizontal)
                        │
                        ├── Left Panel: InteractiveGraphicsView
                        │   │
                        │   └── QGraphicsScene
                        │       │
                        │       ├── QGraphicsPixmapItem (Base image)
                        │       │
                        │       └── Detection Overlays (per detection)
                        │           │
                        │           ├── ResizablePolygonBBoxItem (OBB)
                        │           │   ├── Polygon outline
                        │           │   ├── 4 drag handles (corners)
                        │           │   └── Label (class + confidence)
                        │           │
                        │           └── ResizableBBoxItem (AABB fallback)
                        │               ├── Rectangle outline
                        │               └── 8 drag handles
                        │
                        └── Right Panel: QSplitter (Vertical)
                            │
                            ├── AuditingTreeWidget (QTreeWidget)
                            │   │
                            │   └── Columns:
                            │       ├── Class
                            │       ├── Anchor Text / Nummer
                            │       ├── Koordinatentext
                            │       ├── Koordinatenwert
                            │       ├── GI/GL
                            │       ├── Konfidenz
                            │       ├── Fahrtrichtung
                            │       ├── Farbe
                            │       └── Risk Indicator (●●●)
                            │
                            └── QStatusBar (Summary stats)
```

---

## 19. Image Processing Pipeline

### Preprocessing Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORIGINAL IMAGE                                │
│                    (PDF page or image file)                      │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                COLOR TO BLACK CONVERSION                         │
│                                                                  │
│  convert_colors_to_black_for_yolo(image):                       │
│    1. Convert BGR → HSV                                         │
│    2. Create mask where saturation > threshold                  │
│    3. Set masked pixels to black                                │
│                                                                  │
│  Purpose: YOLO trained on black symbols, colored symbols        │
│           would be missed without this conversion               │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                      TILING                                      │
│                                                                  │
│  tile_image(image, tile_size=2048, overlap=0.4):                │
│    • Split into overlapping tiles                               │
│    • Add 320px halo for context                                 │
│    • Return list of (tile, offset_x, offset_y)                  │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                      ┌───────────┴───────────┐
                      │   For each tile...    │
                      └───────────┬───────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    YOLO PREDICTION                               │
│                                                                  │
│  model.predict(tile, imgsz=1024, conf=0.25):                    │
│    • Returns OBB results: cx, cy, w, h, theta                   │
│    • Transform coordinates: tile → global                       │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                      └───────────┬───────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              NON-MAXIMUM SUPPRESSION (NMS)                       │
│                                                                  │
│  nms_across_tiles(all_detections):                              │
│    • IoU-based suppression                                      │
│    • Class-specific thresholds                                  │
│    • Merge duplicates from overlap zones                        │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                      ┌───────────┴───────────┐
                      │ For each detection... │
                      └───────────┬───────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CROP EXTRACTION                               │
│                                                                  │
│  if is_cardinal(angle):                                         │
│      crop = rotated_crop_from_det(image, detection)             │
│  else:                                                           │
│      crop = perspective_crop_from_det(image, detection)         │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│              CLASS-SPECIFIC PREPROCESSING                        │
│                                                                  │
│  preprocess_for_paddleocr(crop, class_name):                    │
│                                                                  │
│    if class_name in ['gks_gesteuert', 'gks_festkodiert']:       │
│      • Grayscale conversion                                     │
│      • CLAHE contrast enhancement                               │
│      • Remove horizontal/vertical frame lines                   │
│      • Morphological dilation                                   │
│                                                                  │
│    elif class_name == 'signal':                                 │
│      • Grayscale conversion                                     │
│      • Light sharpening (amount=1.3)                           │
│                                                                  │
│    elif class_name == 'coordinate':                             │
│      • Adaptive thresholding                                    │
│      • Noise removal                                            │
│                                                                  │
│    else:                                                         │
│      • Basic grayscale + CLAHE                                  │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OCR RECOGNITION                               │
│                                                                  │
│  paddleocr.ocr(preprocessed_crop):                              │
│    • Returns: [(box, (text, confidence)), ...]                  │
│    • Post-process text (apply learned patterns)                 │
│    • Return (final_text, confidence)                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 20. Validation System

### Validation Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    UltimateValidator                             │
│                                                                  │
│  def validate_all(self, df):                                    │
│      issues = []                                                 │
│      issues.extend(self.validate_ocr(df))                       │
│      issues.extend(self.validate_yolo(df))                      │
│      issues.extend(self.validate_linking(df))                   │
│      issues.extend(self.validate_coordinates(df))               │
│      return issues                                               │
│                                                                  │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  OCR Validation │   │ YOLO Validation │   │Link Validation  │
│                 │   │                 │   │                 │
│ • Empty text    │   │ • Low confidence│   │ • Missing coord │
│ • Invalid format│   │ • Overlapping   │   │ • Wrong link    │
│ • OCR errors    │   │ • Class mismatch│   │ • Direction err │
└─────────────────┘   └─────────────────┘   └─────────────────┘
```

### Risk Assessment

```python
# validation_config.py

RISK_WEIGHTS = {
    'low_confidence': 0.40,           # 40% weight
    'missing_coordinate': 0.30,       # 30% weight
    'haltepunkt_signal_mismatch': 0.25,
    'empty_text': 0.20,
    'invalid_format': 0.15,
    'duplicate_detection': 0.10,
    'other': 0.05
}

RISK_THRESHOLDS = {
    'HIGH': 0.20,     # Risk score > 0.20 → Red (Sofort prüfen)
    'MEDIUM': 0.10,   # 0.10 < score <= 0.20 → Yellow (Bald prüfen)
    'LOW': 0.0        # score <= 0.10 → Green (Gut erkannt)
}
```

### Visual Risk Indicators

```
┌────────────────────────────────────────────────────────────────┐
│                    Detection Table                              │
├────────┬────────────┬──────────┬──────────┬───────────────────┤
│ Class  │ Text       │ Coord    │ Conf     │ Risk              │
├────────┼────────────┼──────────┼──────────┼───────────────────┤
│ signal │ A123       │ 0.1234   │ 0.95     │ 🟢 (Low risk)     │
│ signal │ A124       │ 0.1235   │ 0.65     │ 🟡 (Medium risk)  │
│ signal │ ???        │ -        │ 0.35     │ 🔴 (High risk)    │
└────────┴────────────┴──────────┴──────────┴───────────────────┘
```

---

## Summary

### Architecture Strengths

| Strength | Implementation |
|----------|----------------|
| **Modularity** | Clear separation: core, ui, validation, utils |
| **Extensibility** | Custom symbols without retraining |
| **Robustness** | Graceful degradation, validation feedback |
| **Performance** | Threading, tiling, parallel OCR |
| **User Experience** | Human-in-the-loop for uncertain detections |

### Technology Highlights

| Technology | Purpose | Benefit |
|------------|---------|---------|
| **YOLOv8-OBB** | Detection | Handles rotated symbols |
| **PaddleOCR** | Text recognition | High accuracy for German |
| **PyQt5** | GUI | Cross-platform, professional UI |
| **Pandas** | Data handling | Efficient DataFrame operations |
| **SQLite** | Persistence | Lightweight, no server needed |

### Key Metrics

- **13 detection classes** covering railway symbols
- **mAP50 ≥ 0.96** for most classes
- **Parallel OCR** with up to 16 workers
- **500 DPI** support for A0 layouts
- **Two-stage confidence** for quality control

---

*Generated for Master's Thesis Presentation*
*RailDoc Studio - Gleisplanextraktor v3*

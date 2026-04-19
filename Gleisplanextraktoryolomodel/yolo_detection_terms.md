# YOLO Detection Terms & Definitions

This document explains all technical terms used in the YOLO prediction parameters for the Gleisplanextraktor.

---

## Core Detection Parameters

| Term | Definition |
|------|------------|
| **`imgsz` / `pred_imgsz`** | Image size fed to YOLO model. Images are resized to this resolution (e.g., 1024×1024) before inference. Larger = more detail but slower. |
| **`conf` / `confidence_threshold`** | Minimum confidence score (0.0-1.0) for a detection to be kept. Lower = more detections (including false positives). |
| **`iou`** | Intersection over Union threshold for NMS. Controls how much overlap is allowed between boxes before one is suppressed. |

---

## NMS (Non-Maximum Suppression)

| Term | Definition |
|------|------------|
| **NMS** | Algorithm that removes duplicate/overlapping detections. Keeps the highest-confidence box and removes others that overlap above the IoU threshold. |
| **`nms_threshold`** | IoU threshold for NMS. **Lower = stricter** (removes more overlaps). E.g., 0.30 means boxes overlapping >30% are merged. |
| **`prefer_larger_nms`** | When two boxes overlap, prefer keeping the larger one (useful for symbols that vary in size). |

---

## IoU (Intersection over Union)

```
IoU = Area of Overlap / Area of Union

┌─────────┐
│    A    │
│   ┌─────┼────┐
│   │█████│    │   IoU = █████ / (A + B - █████)
└───┼─────┘    │
    │     B    │
    └──────────┘
```

| IoU Value | Meaning |
|-----------|---------|
| 0.0 | No overlap |
| 0.5 | 50% overlap (common threshold) |
| 1.0 | Perfect overlap (identical boxes) |

---

## Tiling Parameters

| Term | Definition |
|------|------------|
| **`tile_size`** | Size of each tile cut from the full image (e.g., 2048×2048 pixels). Large images are split into tiles for processing. |
| **`overlap_pct`** | Percentage overlap between adjacent tiles. Higher overlap (e.g., 60%) catches objects at tile edges but increases processing time. |
| **`tile_halo`** | Extra pixels added around each tile's detection zone. Detections in the halo are used for merging but not as primary outputs. |

```
┌────────────────────────────────────┐
│            TILE 1                  │
│                    ┌───────────────┼────────────────┐
│                    │   OVERLAP     │    TILE 2      │
│                    │    ZONE       │                │
└────────────────────┼───────────────┘                │
                     │                                │
                     └────────────────────────────────┘
```

---

## Halo Parameters (Antwerp-specific)

| Term | Definition |
|------|------------|
| **`use_halo_expansion`** | Adds extra context pixels around tiles to avoid cutting symbols at edges. |
| **`use_centroid_halo`** | Only keeps detections whose center point falls within a safe zone (not near tile edges). |
| **`halo_ratio`** | Percentage from tile edge to define the "unsafe" zone (e.g., 0.12 = 12% from each edge). |
| **`halo_conf_boost`** | Confidence boost applied to detections safely inside the halo zone. |

```
┌──────────────────────────────────┐
│ ░░░░░░░ HALO ZONE ░░░░░░░░░░░░░ │  ← Detections here are suspicious
│ ░░░┌──────────────────────┐░░░░ │
│ ░░░│                      │░░░░ │
│ ░░░│     SAFE ZONE        │░░░░ │  ← Detections here are trusted
│ ░░░│     (centroid OK)    │░░░░ │
│ ░░░│                      │░░░░ │
│ ░░░└──────────────────────┘░░░░ │
│ ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
└──────────────────────────────────┘
```

---

## Filtering Parameters

| Term | Definition |
|------|------------|
| **`use_ink_filter`** | Rejects detections with too little "ink" (actual content). Filters out empty/white regions. |
| **`ink_threshold`** | Minimum percentage of dark pixels required (e.g., 0.012 = 1.2% ink). |
| **`filter_contained_boxes`** | Removes smaller boxes fully contained inside larger boxes. |
| **`contained_box_threshold`** | Overlap ratio to consider a box "contained" (e.g., 0.80 = 80% inside). |

---

## TTA (Test-Time Augmentation)

| Term | Definition |
|------|------------|
| **TTA** | Runs inference multiple times with augmented versions of the image, then merges results. Improves accuracy at cost of speed. |
| **`tta_scales`** | Scale factors to try (e.g., `[1.0]` = original size only, `[0.8, 1.0, 1.2]` = 3 scales). |
| **`tta_flips`** | Flip modes: `0`=none, `1`=horizontal, `2`=vertical, `3`=both. |
| **`tta_min_votes`** | Minimum number of augmented runs that must detect an object for it to be kept. |

---

## OBB (Oriented Bounding Box)

| Term | Definition |
|------|------------|
| **OBB** | Rotated bounding box that fits the object tightly at any angle (vs axis-aligned boxes). |
| **`obb_only`** | Only output OBB format (no axis-aligned boxes). |
| **`use_native_obb_polygons`** | Use YOLO's native 4-point polygon output instead of converting to angle+dimensions. |

```
Axis-Aligned (AABB)              Oriented (OBB)
┌─────────────┐                      ╱╲
│  ╱╲         │                     ╱  ╲
│ ╱  ╲        │                    ╱    ╲
│╱    ╲       │                   ╱      ╲
│      ╲      │                  ╱────────╲
└─────────────┘                  (tighter fit)
```

---

## Cropping Parameters

| Term | Definition |
|------|------------|
| **`crop_top/bottom/left/right`** | Pixels to remove from each edge before processing. Removes headers, footers, margins. |
| **`exclude_legend_strip`** | Remove the legend/title block strip (usually on right side of plan). |
| **`legend_strip_width_percent`** | Width of legend strip as percentage of image width. |

---

## DPI & Resolution

| Term | Definition |
|------|------------|
| **DPI** | Dots Per Inch - scan resolution. Higher DPI = more detail. Wien=500, Antwerp=800. |
| **`zoom_size`** | Display zoom size for UI rendering (doesn't affect detection). |

---

## Class-Specific Thresholds

| Term | Definition |
|------|------------|
| **`CLASS_CONF`** | Per-class confidence thresholds. Some classes need lower thresholds (e.g., `isolierstoß: 0.09`) because they're harder to detect. |
| **`NMS_THRESH`** | Per-class NMS thresholds. Stricter for classes that shouldn't overlap (e.g., `coordinate: 0.25`). |
| **`uncertain_thresh_multiplier`** | Multiplier to calculate "uncertain" detection threshold (e.g., 0.5 × normal threshold). |

---

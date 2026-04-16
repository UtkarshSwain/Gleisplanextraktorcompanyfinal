"""
Configuration models for layout-specific parameters.
This module defines the data structures for profile-based configuration.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class DetectionConfig:
    """YOLO detection parameters"""
    tile_size: int = 2048
    overlap_pct: int = 40
    dpi: int = 500
    pred_imgsz: int = 1024
    tile_halo: int = 320
    obb_only: bool = True
    exclude_legend_strip: bool = True
    legend_strip_width_percent: int = 12
    legend_strip_max_pixels: int = 4200
    use_tta: bool = True
    tta_scales: List[float] = field(default_factory=lambda: [1.0])
    tta_flips: List[int] = field(default_factory=lambda: [0, 1])
    tta_min_votes: int = 1


@dataclass
class LayoutConfig:
    """Complete layout configuration combining all sub-configs"""
    detection: DetectionConfig = field(default_factory=DetectionConfig)

    # Class-specific confidence thresholds (overrides from profile)
    confidence_thresholds: Dict[str, float] = field(default_factory=dict)

    # Profile metadata
    profile_name: str = "default"
    profile_description: str = "Default configuration"

    def get_confidence_threshold(self, class_name: str, default: float = 0.5) -> float:
        """Get confidence threshold for a specific class."""
        return self.confidence_thresholds.get(class_name, default)

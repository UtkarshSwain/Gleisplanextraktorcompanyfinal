# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
DPI-Aware Sizing Utilities for RailDoc Studio
Provides functions for adaptive sizing across different screen DPI settings.

This module enables the application to scale properly on monitors with different
DPI/resolution settings (100%, 125%, 150%, 200% scaling).
"""

from PyQt5 import QtWidgets, QtCore, QtGui
from typing import Tuple
import math

# Standard Windows DPI at 100% scaling
_BASE_DPI = 96.0


def get_primary_screen() -> QtGui.QScreen:
    """
    Get primary screen object.

    Returns:
        QScreen object for the primary display
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        raise RuntimeError("QApplication must be created before using DPI utilities")
    return app.primaryScreen()


def get_screen_geometry() -> QtCore.QRect:
    """
    Get available screen geometry (excluding taskbar/system UI).

    Returns:
        QRect representing available screen space
    """
    screen = get_primary_screen()
    return screen.availableGeometry()


def get_dpi_scale_factor() -> float:
    """
    Get DPI scale factor relative to 96 DPI baseline.

    Returns:
        Scale factor (1.0 = 96 DPI/100%, 1.25 = 120 DPI/125%,
                      1.5 = 144 DPI/150%, 2.0 = 192 DPI/200%)
    """
    screen = get_primary_screen()
    logical_dpi = screen.logicalDotsPerInchX()
    return logical_dpi / _BASE_DPI


def scale_value(value: float) -> int:
    """
    Scale a pixel value based on current DPI.

    Very small values (1-2px) are not scaled to preserve borders and minimal spacing.

    Args:
        value: Base pixel value (designed for 96 DPI)

    Returns:
        Scaled pixel value as integer
    """
    if value <= 2:
        # Don't scale very small values like 1px borders
        return int(value)

    scale_factor = get_dpi_scale_factor()
    return int(value * scale_factor)


def scale_size(width: int, height: int) -> Tuple[int, int]:
    """
    Scale a size tuple based on current DPI.

    Args:
        width: Base width in pixels
        height: Base height in pixels

    Returns:
        Tuple of (scaled_width, scaled_height)
    """
    factor = get_dpi_scale_factor()
    return (int(width * factor), int(height * factor))


def scale_font_size(base_pt: int) -> int:
    """
    Scale font point size based on DPI.

    Uses square root scaling for more gradual font size increases,
    preventing text from becoming too large at high DPI settings.

    Args:
        base_pt: Base font size in points

    Returns:
        Scaled font size in points (minimum 8pt)
    """
    factor = get_dpi_scale_factor()
    # Use square root for more conservative font scaling
    adjusted_factor = math.sqrt(factor)
    return max(8, int(base_pt * adjusted_factor))


def get_screen_percentage_size(width_pct: float, height_pct: float) -> Tuple[int, int]:
    """
    Get window size as percentage of available screen space.

    Args:
        width_pct: Width as percentage (0.0-1.0, e.g., 0.8 = 80%)
        height_pct: Height as percentage (0.0-1.0, e.g., 0.9 = 90%)

    Returns:
        Tuple of (width, height) in pixels
    """
    geometry = get_screen_geometry()
    return (
        int(geometry.width() * width_pct),
        int(geometry.height() * height_pct)
    )


def get_adaptive_window_size(
    base_width: int,
    base_height: int,
    max_screen_pct: float = 0.9,
    min_width: int = 400,
    min_height: int = 300
) -> Tuple[int, int]:
    """
    Calculate adaptive window size that scales with DPI but respects screen bounds.

    This function:
    1. Scales the base dimensions by current DPI factor
    2. Constrains result to not exceed max_screen_pct of screen size
    3. Ensures minimum dimensions are respected

    Args:
        base_width: Base width at 96 DPI (100% scaling)
        base_height: Base height at 96 DPI (100% scaling)
        max_screen_pct: Maximum percentage of screen to use (0.0-1.0)
        min_width: Minimum window width in pixels
        min_height: Minimum window height in pixels

    Returns:
        Tuple of (width, height) in pixels

    Example:
        # For a window designed at 1000x800 on a 1920x1080 screen at 125% DPI:
        # - DPI scaling: 1000*1.25=1250, 800*1.25=1000
        # - Screen constraint: max 90% = 1728x972
        # - Result: 1250x972 (height constrained to screen)
        w, h = get_adaptive_window_size(1000, 800, max_screen_pct=0.9)
    """
    # Scale by DPI
    scaled_w, scaled_h = scale_size(base_width, base_height)

    # Get screen bounds
    geometry = get_screen_geometry()
    max_w = int(geometry.width() * max_screen_pct)
    max_h = int(geometry.height() * max_screen_pct)

    # Apply all constraints
    final_w = max(min_width, min(scaled_w, max_w))
    final_h = max(min_height, min(scaled_h, max_h))

    return (final_w, final_h)


def center_window(window: QtWidgets.QWidget):
    """
    Center window on primary screen.

    Args:
        window: QWidget or QMainWindow to center
    """
    geometry = get_screen_geometry()
    window_geometry = window.frameGeometry()
    center_point = geometry.center()
    window_geometry.moveCenter(center_point)
    window.move(window_geometry.topLeft())


def get_scaled_font(
    base_point_size: int = 10,
    weight: int = QtGui.QFont.Normal,
    family: str = ""
) -> QtGui.QFont:
    """
    Get DPI-scaled QFont.

    Args:
        base_point_size: Base font size in points
        weight: Font weight (QFont.Normal, QFont.Bold, etc.)
        family: Font family (empty string = system default)

    Returns:
        QFont configured for current DPI

    Example:
        # Create a bold 12pt font that scales with DPI
        font = get_scaled_font(12, QtGui.QFont.Bold)
        widget.setFont(font)
    """
    font = QtGui.QFont(family) if family else QtGui.QFont()
    font.setPointSize(scale_font_size(base_point_size))
    font.setWeight(weight)
    return font


def get_column_width_for_content(
    header_text: str,
    sample_content: str = "",
    min_width: int = 50,
    padding_factor: float = 1.2
) -> int:
    """
    Calculate column width based on content and DPI.

    Args:
        header_text: Column header text
        sample_content: Sample content for width estimation
        min_width: Minimum column width
        padding_factor: Extra space multiplier (1.2 = 20% padding)

    Returns:
        Recommended column width in pixels
    """
    font_metrics = QtGui.QFontMetrics(QtGui.QFont())

    header_width = font_metrics.horizontalAdvance(header_text)
    content_width = font_metrics.horizontalAdvance(sample_content) if sample_content else 0

    base_width = max(header_width, content_width)
    scaled_width = scale_value(int(base_width * padding_factor))

    return max(min_width, scaled_width)


# Convenience functions for common UI element sizes
def get_standard_button_height() -> int:
    """Get standard button height scaled for current DPI."""
    return scale_value(32)


def get_standard_button_width() -> int:
    """Get standard button width scaled for current DPI."""
    return scale_value(100)


def get_standard_icon_size() -> int:
    """Get standard icon size scaled for current DPI."""
    return scale_value(24)


def get_standard_spacing() -> int:
    """Get standard spacing between UI elements scaled for current DPI."""
    return scale_value(8)


def get_standard_margin() -> int:
    """Get standard margin around containers scaled for current DPI."""
    return scale_value(12)


# Debug function to print DPI information
def print_dpi_info():
    """
    Print current DPI information for debugging.
    Useful for testing on different displays.
    """
    try:
        screen = get_primary_screen()
        geometry = get_screen_geometry()
        scale_factor = get_dpi_scale_factor()

        print("=" * 60)
        print("DPI Information:")
        print("=" * 60)
        print(f"Logical DPI: {screen.logicalDotsPerInchX():.1f}")
        print(f"Physical DPI: {screen.physicalDotsPerInchX():.1f}")
        print(f"Device Pixel Ratio: {screen.devicePixelRatio():.2f}")
        print(f"Scale Factor: {scale_factor:.2f}")
        print()
        print("Screen Geometry:")
        print(f"  Width: {geometry.width()}px")
        print(f"  Height: {geometry.height()}px")
        print()
        print("Example Scaled Values:")
        print(f"  100px → {scale_value(100)}px")
        print(f"  200px → {scale_value(200)}px")
        print(f"  12pt font → {scale_font_size(12)}pt")
        print("=" * 60)
    except Exception as e:
        print(f"Error getting DPI info: {e}")

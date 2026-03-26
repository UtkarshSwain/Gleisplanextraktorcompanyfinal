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



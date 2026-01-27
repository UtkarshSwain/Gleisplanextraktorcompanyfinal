"""
Rotation transformation utilities for OCR regions and coordinates.

Provides consistent rotation transformations across the codebase.
"""

# Rotation angle range constants
ANGLE_RANGE_0 = (0, 45)
ANGLE_RANGE_90 = (45, 135)
ANGLE_RANGE_180 = (135, 225)
ANGLE_RANGE_270 = (225, 315)
ANGLE_RANGE_360 = (315, 360)


def normalize_angle(angle: float) -> float:
    """Normalize angle to 0-360 range."""
    return angle % 360


def get_rotation_quadrant(angle: float) -> int:
    """
    Get rotation quadrant (0, 90, 180, 270) for a given angle.

    Args:
        angle: Angle in degrees

    Returns:
        0, 90, 180, or 270
    """
    norm_angle = normalize_angle(angle)

    if ANGLE_RANGE_90[0] <= norm_angle < ANGLE_RANGE_90[1]:
        return 90
    elif ANGLE_RANGE_180[0] <= norm_angle < ANGLE_RANGE_180[1]:
        return 180
    elif ANGLE_RANGE_270[0] <= norm_angle < ANGLE_RANGE_270[1]:
        return 270
    else:  # 0° or 315-360°
        return 0


def transform_offset_forward(dx: float, dy: float, width: float, height: float, angle: float):
    """
    Transform offset and dimensions FROM 0° reference TO target rotation.

    Used when APPLYING a template offset to a rotated symbol.

    Args:
        dx: X offset from symbol center (at 0°)
        dy: Y offset from symbol center (at 0°)
        width: Region width (at 0°)
        height: Region height (at 0°)
        angle: Target rotation angle in degrees

    Returns:
        tuple: (transformed_dx, transformed_dy, transformed_width, transformed_height)
    """
    quadrant = get_rotation_quadrant(angle)

    if quadrant == 90:
        # Rotate 90° clockwise: (dx, dy) → (dy, -dx)
        return dy, -dx, height, width
    elif quadrant == 180:
        # Rotate 180°: (dx, dy) → (-dx, -dy)
        return -dx, -dy, width, height
    elif quadrant == 270:
        # Rotate 270° clockwise: (dx, dy) → (-dy, dx)
        return -dy, dx, height, width
    else:  # 0°
        return dx, dy, width, height


def transform_offset_reverse(dx: float, dy: float, width: float, height: float, angle: float):
    """
    Transform offset and dimensions FROM current rotation TO 0° reference.

    Used when SAVING a user adjustment to template (reverse transformation).

    Args:
        dx: X offset from symbol center (at current rotation)
        dy: Y offset from symbol center (at current rotation)
        width: Region width (at current rotation)
        height: Region height (at current rotation)
        angle: Current rotation angle in degrees

    Returns:
        tuple: (reference_dx, reference_dy, reference_width, reference_height)
    """
    quadrant = get_rotation_quadrant(angle)

    if quadrant == 90:
        # Reverse 90°: (dx, dy) @ 90° → (-dy, dx) @ 0°
        return -dy, dx, height, width
    elif quadrant == 180:
        # Reverse 180°: (dx, dy) @ 180° → (-dx, -dy) @ 0°
        return -dx, -dy, width, height
    elif quadrant == 270:
        # Reverse 270°: (dx, dy) @ 270° → (dy, -dx) @ 0°
        return dy, -dx, height, width
    else:  # 0°
        return dx, dy, width, height


def transform_edge_deltas(delta_x1: float, delta_y1: float,
                          delta_x2: float, delta_y2: float,
                          source_angle: float, target_angle: float):
    """
    Transform edge deltas from source rotation to target rotation.

    Used when applying OCR region adjustment from one symbol to another
    with different rotation.

    Args:
        delta_x1: Left edge movement
        delta_y1: Top edge movement
        delta_x2: Right edge movement
        delta_y2: Bottom edge movement
        source_angle: Angle of the reference symbol
        target_angle: Angle of the target symbol

    Returns:
        tuple: (transformed_dx1, transformed_dy1, transformed_dx2, transformed_dy2)
    """
    source_quad = get_rotation_quadrant(source_angle)
    target_quad = get_rotation_quadrant(target_angle)

    # Calculate relative rotation
    relative_rotation = (target_quad - source_quad) % 360

    if relative_rotation == 90:
        # 90° rotation: x1→y2, x2→y1, y1→x1, y2→x2
        return delta_y1, -delta_x2, delta_y2, -delta_x1
    elif relative_rotation == 180:
        # 180° rotation: x1→x2, x2→x1, y1→y2, y2→y1 (flip)
        return -delta_x2, -delta_y2, -delta_x1, -delta_y1
    elif relative_rotation == 270:
        # 270° rotation: x1→y1, x2→y2, y1→x2, y2→x1
        return -delta_y2, delta_x1, -delta_y1, delta_x2
    else:  # 0° - no transformation
        return delta_x1, delta_y1, delta_x2, delta_y2


def validate_region_bounds(x1: float, y1: float, x2: float, y2: float,
                          img_width: int, img_height: int) -> tuple:
    """
    Validate and clamp OCR region to image bounds.

    Args:
        x1, y1, x2, y2: Region coordinates
        img_width: Image width
        img_height: Image height

    Returns:
        tuple: (clamped_x1, clamped_y1, clamped_x2, clamped_y2, is_valid)
        is_valid is False if region is too small or completely out of bounds
    """
    # Clamp to image bounds
    x1 = max(0, min(x1, img_width))
    y1 = max(0, min(y1, img_height))
    x2 = max(0, min(x2, img_width))
    y2 = max(0, min(y2, img_height))

    # Ensure x2 > x1 and y2 > y1
    if x2 <= x1:
        x2 = min(x1 + 10, img_width)
    if y2 <= y1:
        y2 = min(y1 + 10, img_height)

    # Check if region is valid (at least 10x10 pixels)
    width = x2 - x1
    height = y2 - y1
    is_valid = width >= 10 and height >= 10

    return x1, y1, x2, y2, is_valid

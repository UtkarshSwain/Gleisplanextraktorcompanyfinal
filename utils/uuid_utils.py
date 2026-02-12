# ============================================================================
# RailDoc Studio - Intelligente Eisenbahndokument-Analyse
# Gleisplan-Modul v1.0
#
# Entwickelt von: Utkarsh Swain
# Siemens Mobility GmbH
# © 2026
# ============================================================================
"""
Utilities for generating deterministic UUIDs for layout elements.
"""

import hashlib
import re
import os

def generate_deterministic_uuid(element_data: dict, pdf_identifier: str = None) -> str:
    """
    Generate a deterministic UUID based on element properties.
    
    The UUID will be the same for the same element across different PDF versions,
    allowing for accurate comparison. The UUID is generated using SHA-256 hash
    of a fingerprint created from element properties.
    
    Args:
        element_data: Dictionary containing element properties with keys:
            - cls: Element class (e.g., 'signal', 'coordinate')
            - page: Page number
            - obb_cx, obb_cy: Center coordinates (or cx1, cy1 as fallback)
            - anchor_text: Optional text label
            - coord_text: Optional coordinate text
        
        pdf_identifier: Optional base identifier (e.g., layout name without version).
            This ensures elements from the same layout family get consistent UUIDs.
    
    Returns:
        UUID string in format: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
        
    Example:
        >>> element = {
        ...     'cls': 'signal',
        ...     'page': 1,
        ...     'obb_cx': 1234.5,
        ...     'obb_cy': 567.8,
        ...     'anchor_text': 'Hp 0/Hp 1'
        ... }
        >>> uuid = generate_deterministic_uuid(element, 'SgSl0603_10_01-001')
        >>> print(uuid)
        'a1b2c3d4-e5f6-7890-abcd-ef1234567890'
    """
    # Build a unique fingerprint from element properties
    fingerprint_parts = []
    
    # 1. PDF identifier (optional - use base name without version)
    if pdf_identifier:
        fingerprint_parts.append(str(pdf_identifier))
    
    # 2. Element class (required)
    cls = element_data.get('cls') or ''
    fingerprint_parts.append(str(cls))
    
    # 3. Page number (required)
    page = element_data.get('page') or 0
    fingerprint_parts.append(str(page))
    
    # 4. Position (rounded to reduce floating point differences)
    # Use center coordinates, rounded to nearest 10 pixels
    # This allows for small position variations while maintaining UUID consistency
    cx = element_data.get('obb_cx') or element_data.get('cx1') or 0
    cy = element_data.get('obb_cy') or element_data.get('cy1') or 0
    
    # Convert to float if needed (handle None, string, etc.)
    try:
        cx = float(cx) if cx is not None else 0.0
        cy = float(cy) if cy is not None else 0.0
    except (ValueError, TypeError):
        cx = 0.0
        cy = 0.0
    # Round to nearest 10 pixels to handle minor position variations
# This tolerance allows for:
# - Small PDF rendering differences between versions
# - Minor layout shifts (< 10px)
# - Floating point precision issues
# While still distinguishing nearby elements (>= 10px apart)
    # Round to nearest 10 pixels to handle minor position variations
    cx_rounded = round(cx / 10) * 10
    cy_rounded = round(cy / 10) * 10
    
    fingerprint_parts.append(f"{cx_rounded:.0f}")
    fingerprint_parts.append(f"{cy_rounded:.0f}")
    
    # 5. Anchor text (if available - helps distinguish similar elements)
    anchor_text = element_data.get('anchor_text') or ''
    anchor_text = str(anchor_text).strip()
    if anchor_text:
        # Normalize text (remove extra whitespace, convert to lowercase)
        anchor_text_normalized = ' '.join(anchor_text.lower().split())
        fingerprint_parts.append(anchor_text_normalized)
    
    # 6. Coordinate text (if available)
    coord_text = element_data.get('coord_text') or ''
    coord_text = str(coord_text).strip()
    if coord_text:
        # Normalize coordinate text
        coord_text_normalized = ' '.join(coord_text.lower().split())
        fingerprint_parts.append(coord_text_normalized)

        # 7. Size/angle tiebreaker (for elements without text)
    # This prevents UUID collisions for nearby elements of same class
    if not anchor_text and not coord_text:
        # Use element dimensions and angle to distinguish
        width = element_data.get('obb_w', 0) or 0
        height = element_data.get('obb_h', 0) or 0
        angle = element_data.get('angle', 0) or 0
        
        # Convert to float and round
        try:
            width = round(float(width), 1)
            height = round(float(height), 1)
            angle = round(float(angle), 1)
        except (ValueError, TypeError):
            width = 0.0
            height = 0.0
            angle = 0.0
        
        # Add to fingerprint if non-zero
        if width > 0 or height > 0:
            fingerprint_parts.append(f"size:{width}x{height}")
        if angle != 0:
            fingerprint_parts.append(f"angle:{angle}")

    # Create fingerprint string (pipe-separated for clarity)
    fingerprint = '|'.join(fingerprint_parts)
    
    # Generate UUID from fingerprint using SHA-256 hash
    hash_object = hashlib.sha256(fingerprint.encode('utf-8'))
    hash_hex = hash_object.hexdigest()
    
    # Convert to UUID format (UUID5-like)
    # Take first 32 hex characters and format as standard UUID
    uuid_hex = hash_hex[:32]
    uuid_str = (
        f"{uuid_hex[:8]}-"
        f"{uuid_hex[8:12]}-"
        f"{uuid_hex[12:16]}-"
        f"{uuid_hex[16:20]}-"
        f"{uuid_hex[20:32]}"
    )
    
    return uuid_str

def extract_base_layout_name(pdf_path: str) -> str:
    """
    Extract base layout name without version suffix.
    
    Handles various version patterns:
    - _D_000, _E_000 (standard format)
    - _D_0001 (4-digit version)
    - _v1, _v2 (simple version)
    - _rev1, _rev2 (revision)
    
    Examples:
        'SgSl0603_10_01-001_gn-bl_pdf_PM2_A6Z00060265232_D_000.pdf' 
        → 'SgSl0603_10_01-001_gn-bl_pdf_PM2_A6Z00060265232'
        
        'layout_v2.pdf' → 'layout'
        'plan_rev3.pdf' → 'plan'
    
    Args:
        pdf_path: Full path to PDF file
    
    Returns:
        Base layout name without version suffix
    """
    filename = os.path.basename(pdf_path)
    
    # Remove .pdf extension (case-insensitive)
    name = re.sub(r'\.pdf$', '', filename, flags=re.IGNORECASE)
    
    # Try multiple version patterns (in order of specificity)
    version_patterns = [
        r'_[A-Z]_\d{3,4}$',      # _D_000, _E_0001 (most specific)
        r'_v\d+$',                # _v1, _v2
        r'_rev\d+$',              # _rev1, _rev2
        r'_version\d+$',          # _version1
        r'_\d{3,4}$',             # _001, _0001 (generic, least specific)
    ]
    
    for pattern in version_patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            base_name = name[:match.start()]
            return base_name
    
    # No version suffix found - return as-is
    return name
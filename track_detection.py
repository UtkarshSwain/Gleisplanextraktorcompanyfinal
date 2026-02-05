"""
track_detection.py - Main track (Gleis) centerline detection for Gleisplan files
Supports both PDF files and image arrays (PNG, JPEG, TIFF, etc.)
Integrated with existing YOLO OCR extraction pipeline
"""

import numpy as np
import cv2
from skimage.morphology import skeletonize
from typing import Optional, Tuple, Callable, Union

def render_tile_gray(page, scale: float, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    """Render a tile in grayscale using PyMuPDF (PDF only)"""
    import fitz
    clip = fitz.Rect(x0/scale, y0/scale, x1/scale, y1/scale)
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, colorspace=fitz.csGRAY)
    tile = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return tile


def extract_tile_from_image(gray_image: np.ndarray, x0: int, y0: int, x1: int, y1: int) -> np.ndarray:
    """Extract a tile from a grayscale image array"""
    return gray_image[y0:y1, x0:x1].copy()

def binarize(tile_gray: np.ndarray, lines_are_dark: bool = True) -> np.ndarray:
    """Binarize tile with morphological opening"""
    _, bw = cv2.threshold(tile_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    fg = 255 - bw if lines_are_dark else bw
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3,3), np.uint8), iterations=1)
    return fg

def distance_mask(fg: np.ndarray, rmin: int = 6, rmax: int = 20) -> np.ndarray:
    """Create mask for thick lines via distance transform"""
    dist = cv2.distanceTransform(fg, cv2.DIST_L2, 5)
    return ((dist >= rmin) & (dist <= rmax)).astype(np.uint8) * 255

def filter_title_block_tracks(track_skeleton: np.ndarray, 
                              exclusion_margin_width_percent: int = 10,
                              exclusion_margin_height_percent: int = 20) -> np.ndarray:
    """
    Remove track lines detected in bottom-right corner (title block area).
    
    UPDATED: Uses different margins for width and height to handle wide images.
    
    Args:
        track_skeleton: Binary track skeleton image (H x W)
        exclusion_margin_width_percent: Percentage of WIDTH to exclude from right edge
                                       Default 10% (smaller for wide images)
        exclusion_margin_height_percent: Percentage of HEIGHT to exclude from bottom edge
                                        Default 20% (larger for narrow images)
    
    Returns:
        Filtered track skeleton with title block region cleared
    """
    if track_skeleton is None or track_skeleton.size == 0:
        return track_skeleton
    
    height, width = track_skeleton.shape
    
    # Calculate exclusion zone (asymmetric margins)
    exclude_width = int(width * exclusion_margin_width_percent / 100)
    exclude_height = int(height * exclusion_margin_height_percent / 100)
    
    # Create filtered copy
    filtered_skeleton = track_skeleton.copy()
    
    # Clear bottom-right corner
    filtered_skeleton[height - exclude_height:, width - exclude_width:] = 0
    
    print(f" Title block filter: Excluded bottom-right corner")
    print(f"Image size: {width}x{height}px")
    print(f"Exclusion zone: {exclude_width}x{exclude_height}px ({exclusion_margin_width_percent}% width, {exclusion_margin_height_percent}% height)")
    print(f"Cleared region: x=[{width - exclude_width}, {width}], y=[{height - exclude_height}, {height}]")
    
    # Count removed pixels
    removed_pixels = np.sum(track_skeleton[height - exclude_height:, width - exclude_width:] > 0)
    if removed_pixels > 0:
        print(f"Removed {removed_pixels} pixels from title block region")
    else:
        print(f"No track pixels found in title block region")
    
    return filtered_skeleton

def detect_main_tracks(
    pdf_path: Optional[str] = None,
    page_idx: int = 0,
    dpi: int = 500,
    tile_size: int = 2048,
    overlap: int = 30,
    radius_min: int = 6,
    radius_max: int = 20,
    lines_are_dark: bool = True,
    min_track_area: int = 5000,
    min_aspect_ratio: float = 2.0,
    max_solidity: float = 0.3,
    filter_title_block: bool = True,
    title_block_margin_width: int = 8,
    title_block_margin_height: int = 25,
    progress_callback: Optional[Callable[[str], None]] = None,
    image_array: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, int, int]:
    """
    Detect main track centerlines in a Gleisplan (PDF or image).

    Args:
        pdf_path: Path to PDF file (optional if image_array provided)
        page_idx: Page index (0-based, PDF only)
        dpi: Rendering DPI (PDF only, images use native resolution)
        tile_size: Tile size for processing
        overlap: Tile overlap in pixels
        radius_min: Minimum track width (half of target stroke)
        radius_max: Maximum track width
        lines_are_dark: True if tracks are dark on light background
        min_track_area: Minimum area for track components
        min_aspect_ratio: Minimum aspect ratio (elongated components)
        max_solidity: Maximum solidity (sparse components)
        filter_title_block: Whether to filter title block region (default True)
        title_block_margin_width: Percentage margin for right edge (default 10%)
        title_block_margin_height: Percentage margin for bottom edge (default 20%)
        progress_callback: Optional callback for progress updates
        image_array: BGR or grayscale image array (optional, alternative to pdf_path)

    Returns:
        (skeleton_mask, width_px, height_px)
        - skeleton_mask: binary uint8 array (255=centerline, 0=background)
        - width_px, height_px: dimensions
    """

    doc = None  # Will be set only for PDF
    use_image = image_array is not None

    if use_image:
        # Convert BGR to grayscale if needed
        if len(image_array.shape) == 3:
            gray_image = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)
        else:
            gray_image = image_array

        h_px, w_px = gray_image.shape
        if progress_callback:
            progress_callback(f"[track] Image size: {w_px} x {h_px} pixels")
    else:
        # PDF mode
        if pdf_path is None:
            raise ValueError("Either pdf_path or image_array must be provided")

        import fitz
        scale = dpi / 72.0
        doc = fitz.open(pdf_path)
        page = doc[page_idx]

        w_px = int(page.rect.width * scale + 0.5)
        h_px = int(page.rect.height * scale + 0.5)

        if progress_callback:
            progress_callback(f"[track] Page size @ {dpi} DPI: {w_px} x {h_px} pixels")

    # Pass 1: Build thick-line mask
    mask = np.zeros((h_px, w_px), dtype=np.uint8)

    y_tiles = (h_px + tile_size - 1) // tile_size
    x_tiles = (w_px + tile_size - 1) // tile_size
    total_tiles = y_tiles * x_tiles
    tile_count = 0

    for y in range(0, h_px, tile_size):
        y0 = max(0, y - overlap)
        y1 = min(h_px, y + tile_size + overlap)

        for x in range(0, w_px, tile_size):
            x0 = max(0, x - overlap)
            x1 = min(w_px, x + tile_size + overlap)

            if use_image:
                tile = extract_tile_from_image(gray_image, x0, y0, x1, y1)
            else:
                tile = render_tile_gray(page, dpi / 72.0, x0, y0, x1, y1)

            fg = binarize(tile, lines_are_dark=lines_are_dark)
            thick = distance_mask(fg, rmin=radius_min, rmax=radius_max)
            
            # Write core region (non-overlap)
            core_x0 = x - x0
            core_y0 = y - y0
            core_x1 = core_x0 + min(tile_size, w_px - x)
            core_y1 = core_y0 + min(tile_size, h_px - y)
            
            mask[y:y+core_y1-core_y0, x:x+core_x1-core_x0] = np.maximum(
                mask[y:y+core_y1-core_y0, x:x+core_x1-core_x0],
                thick[core_y0:core_y1, core_x0:core_x1]
            )
            
            tile_count += 1
            if progress_callback and tile_count % 10 == 0:
                progress_callback(f"[track] Processing: {tile_count}/{total_tiles} tiles")
    
    #  FILTER TITLE BLOCK BEFORE COMPONENT ANALYSIS (with asymmetric margins)
    if filter_title_block:
        if progress_callback:
            progress_callback(f"[track] Filtering title block region...")
        mask = filter_title_block_tracks(
            mask, 
            exclusion_margin_width_percent=title_block_margin_width,
            exclusion_margin_height_percent=title_block_margin_height
        )
    
    if progress_callback:
        progress_callback(f"[track] Analyzing components...")
    
    # Connected components analysis
    bin_mask = (mask > 0).astype(np.uint8)
    bin_mask = cv2.morphologyEx(bin_mask, cv2.MORPH_CLOSE, np.ones((3,3), np.uint8), iterations=1)
    
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        bin_mask, connectivity=8, ltype=cv2.CV_32S
    )
    
    if num_labels <= 1:
        if progress_callback:
            progress_callback("[track]  No thick components found")
        if doc is not None:
            doc.close()
        return np.zeros((h_px, w_px), dtype=np.uint8), w_px, h_px
    
    # Filter: keep elongated, sparse components (tracks, not title blocks)
    main_mask = np.zeros_like(mask, dtype=np.uint8)
    num_tracks_found = 0
    
    for label_idx in range(1, num_labels):
        area = stats[label_idx, cv2.CC_STAT_AREA]
        
        if area < min_track_area:
            continue
        
        x = stats[label_idx, cv2.CC_STAT_LEFT]
        y = stats[label_idx, cv2.CC_STAT_TOP]
        w = stats[label_idx, cv2.CC_STAT_WIDTH]
        h = stats[label_idx, cv2.CC_STAT_HEIGHT]
        bbox_area = w * h
        
        aspect_ratio = max(w, h) / max(min(w, h), 1)
        solidity = area / max(bbox_area, 1)
        
        is_elongated = aspect_ratio >= min_aspect_ratio
        is_sparse = solidity <= max_solidity
        
        if is_elongated and is_sparse:
            component = (labels == label_idx).astype(np.uint8) * 255
            main_mask = cv2.bitwise_or(main_mask, component)
            num_tracks_found += 1
    
    if progress_callback:
        if num_tracks_found > 0:
            progress_callback(f"[track]  Found {num_tracks_found} track section(s)")
        else:
            progress_callback(f"[track]  No tracks found (try adjusting parameters)")
    
    del labels
    
    # Skeletonize
    if num_tracks_found > 0:
        if progress_callback:
            progress_callback(f"[track] Computing centerlines...")
        skel = skeletonize((main_mask > 0).astype(bool)).astype(np.uint8) * 255
    else:
        skel = np.zeros_like(main_mask, dtype=np.uint8)
    
    if doc is not None:
        doc.close()

    return skel, w_px, h_px
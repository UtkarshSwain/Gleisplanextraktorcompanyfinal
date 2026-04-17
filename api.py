"""
FastAPI REST API for Railway Symbol Detection
Provides endpoints for PDF processing and YOLO-based symbol detection
"""

import os
import io
import tempfile
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import numpy as np
import cv2
from PIL import Image

# Disable PIL decompression bomb limit for large railway PDFs
Image.MAX_IMAGE_PIXELS = None

# PDF processing
from pdf2image import convert_from_bytes

# Core imports
from ultralytics import YOLO
import config
from core.yolo_detection import run_yolo_on_page
from core.config_models import LayoutConfig

# Initialize FastAPI
app = FastAPI(
    title="Railway Symbol Detection API",
    description="YOLO-based symbol detection for railway track layouts",
    version=config.__version__
)

# Global model instance and config
model: Optional[YOLO] = None
layout_config: Optional[LayoutConfig] = None


# Response Models
class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_path: str
    version: str


class ClassesResponse(BaseModel):
    classes: List[str]
    num_classes: int


class Detection(BaseModel):
    class_name: str
    confidence: float
    bbox: List[float]  # [x1, y1, x2, y2, x3, y3, x4, y4] for OBB
    page: int


class DetectionResponse(BaseModel):
    success: bool
    num_pages: int
    num_detections: int
    detections: List[Detection]
    message: Optional[str] = None


# Helper function
def pil_to_bgr(pil_img: Image.Image) -> np.ndarray:
    """Convert PIL Image to BGR numpy array"""
    return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)


# Startup event
@app.on_event("startup")
async def load_model():
    """Load YOLO model and configuration on startup"""
    global model, layout_config

    model_path = os.environ.get("YOLO_MODEL_PATH", "yolomodel/best.pt")

    if not os.path.exists(model_path):
        print(f"Warning: Model not found at {model_path}")
        print("API will start but /detect endpoint will fail until model is provided")
        return

    try:
        # Load YOLO model
        model = YOLO(model_path)
        config.set_classes_from_model(model)
        print(f"Model loaded successfully from {model_path}")
        print(f"Classes: {config.CLASSES}")

        # Create default layout configuration
        layout_config = LayoutConfig()
        print("Layout configuration initialized")

    except Exception as e:
        print(f"Error loading model: {e}")
        model = None
        layout_config = None


# API Endpoints
@app.get("/", response_model=dict)
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Railway Symbol Detection API",
        "version": config.__version__,
        "endpoints": [
            "/health",
            "/classes",
            "/detect"
        ]
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check API health and model status"""
    model_path = os.environ.get("YOLO_MODEL_PATH", "yolomodel/best.pt")

    return HealthResponse(
        status="healthy" if model is not None else "degraded",
        model_loaded=model is not None,
        model_path=model_path,
        version=config.__version__
    )


@app.get("/classes", response_model=ClassesResponse)
async def get_classes():
    """Get list of detectable symbol classes"""
    return ClassesResponse(
        classes=config.CLASSES,
        num_classes=len(config.CLASSES)
    )


@app.post("/detect", response_model=DetectionResponse)
async def detect_symbols(
    file: UploadFile = File(...),
    dpi: Optional[int] = None
):
    """
    Detect railway symbols in uploaded PDF

    Args:
        file: PDF file to process
        dpi: DPI for PDF rendering (default from config.DPI)

    Returns:
        Detection results with bounding boxes for each symbol
    """
    global model, layout_config

    # Validate model is loaded
    if model is None or layout_config is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded. Check YOLO_MODEL_PATH environment variable."
        )

    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported"
        )

    try:
        # Read PDF content
        content = await file.read()

        # Convert PDF to images using pdf2image
        dpi_value = dpi if dpi is not None else config.DPI
        pil_images = convert_from_bytes(content, dpi=dpi_value)

        if not pil_images:
            raise HTTPException(
                status_code=400,
                detail="Failed to extract images from PDF"
            )

        # Run detection on each page
        all_detections = []

        for page_idx, pil_img in enumerate(pil_images):
            # Convert PIL to BGR numpy array
            page_bgr = pil_to_bgr(pil_img)

            # DEBUG: Save the rendered image to your mounted yolomodel folder
            # so you can verify on your host machine if it is blank/white.
            debug_path = f"/app/yolomodel/debug_page_{page_idx + 1}.jpg"
            cv2.imwrite(debug_path, page_bgr)

            # Run YOLO detection
            detections = run_yolo_on_page(
                model=model,
                page_bgr=page_bgr
            )

            # Parse detections
            for det in detections:
                # Extract detection info (keys from yolo_detection.py)
                class_name = det.get('name', 'unknown')
                confidence = det.get('conf', 0.0)

                # Get OBB coordinates from 'poly' key (list of 4 points)
                if 'poly' in det:
                    poly = det['poly']  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                    bbox = [coord for point in poly for coord in point]  # Flatten to [x1,y1,x2,y2,...]
                elif 'x1' in det:
                    # Fallback to regular bbox
                    x1, y1, x2, y2 = det['x1'], det['y1'], det['x2'], det['y2']
                    bbox = [x1, y1, x2, y1, x2, y2, x1, y2]
                else:
                    continue  # Skip if no bbox

                detection = Detection(
                    class_name=class_name,
                    confidence=confidence,
                    bbox=bbox,
                    page=page_idx + 1
                )
                all_detections.append(detection)

        return DetectionResponse(
            success=True,
            num_pages=len(pil_images),
            num_detections=len(all_detections),
            detections=all_detections,
            message=f"Processed {len(pil_images)} pages successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error processing PDF: {error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing PDF: {str(e)}"
        )


# Error handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle unexpected errors"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"Internal server error: {str(exc)}"
        }
    )


if __name__ == "__main__":
    # Run with: python api.py
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )

# API Improvements Guide
## Making Your Gleisplan API Production-Ready

This guide shows you how to improve your FastAPI implementation with industry best practices.

---

## Table of Contents
1. [Testing Setup](#1-testing-setup)
2. [Batch Processing](#2-batch-processing-endpoint)
3. [Visualization Endpoint](#3-visualization-endpoint)
4. [Better Logging](#4-better-logging-with-loguru)
5. [Statistics & Monitoring](#5-statistics-endpoint)
6. [Running Everything](#6-how-to-use)

---

## 1. Testing Setup

### Installation
```bash
# Install test dependencies
pip install -r requirements-dev.txt
```

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ --cov=. --cov-report=html

# Run specific test class
pytest tests/test_api.py::TestHealthEndpoints -v

# Run and stop on first failure
pytest tests/ -x
```

### What the Tests Do
- ✅ Test all endpoints (/, /health, /version, /classes, /detect)
- ✅ Validate response structures
- ✅ Test error handling (wrong file types, missing files)
- ✅ Check API documentation (Swagger/ReDoc)
- ✅ Verify model loading status

---

## 2. Batch Processing Endpoint

**Add to api.py:**

```python
from typing import List
from fastapi import UploadFile, File

@app.post("/detect/batch")
async def detect_symbols_batch(
    files: List[UploadFile] = File(...)
):
    """
    Detect symbols in multiple PDFs at once

    Args:
        files: List of PDF files to process

    Returns:
        List of detection results for each file
    """
    global model, layout_config

    if model is None or layout_config is None:
        raise HTTPException(
            status_code=503,
            detail="Model not loaded"
        )

    results = []

    for file in files:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            results.append({
                "filename": file.filename,
                "success": False,
                "error": "Only PDF files are supported"
            })
            continue

        try:
            # Read and process PDF
            content = await file.read()
            pil_images = convert_from_bytes(content, dpi=config.DPI)

            # Run detection
            all_detections = []
            for page_idx, pil_img in enumerate(pil_images):
                page_bgr = pil_to_bgr(pil_img)
                detections = run_yolo_on_page(model=model, page_bgr=page_bgr)

                for det in detections:
                    all_detections.append({
                        "class_name": det.get('name', 'unknown'),
                        "confidence": det.get('conf', 0.0),
                        "page": page_idx + 1
                    })

            results.append({
                "filename": file.filename,
                "success": True,
                "num_pages": len(pil_images),
                "num_detections": len(all_detections),
                "detections": all_detections
            })

        except Exception as e:
            results.append({
                "filename": file.filename,
                "success": False,
                "error": str(e)
            })

    return {
        "total_files": len(files),
        "successful": sum(1 for r in results if r.get("success", False)),
        "failed": sum(1 for r in results if not r.get("success", True)),
        "results": results
    }
```

**Test it:**
```bash
# Upload multiple PDFs
curl -X POST "http://localhost:8000/detect/batch" \
  -F "files=@plan1.pdf" \
  -F "files=@plan2.pdf" \
  -F "files=@plan3.pdf"
```

---

## 3. Visualization Endpoint

**Add to api.py:**

```python
from fastapi.responses import StreamingResponse
import io

@app.post("/detect/visualize")
async def detect_and_visualize(
    file: UploadFile = File(...),
    dpi: Optional[int] = None,
    confidence_threshold: float = 0.5
):
    """
    Detect symbols and return annotated images

    Args:
        file: PDF file to process
        dpi: DPI for rendering (default from config)
        confidence_threshold: Minimum confidence to display (0-1)

    Returns:
        ZIP file with annotated images for each page
    """
    global model, layout_config

    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files supported")

    try:
        content = await file.read()
        dpi_value = dpi if dpi is not None else config.DPI
        pil_images = convert_from_bytes(content, dpi=dpi_value)

        # Create ZIP in memory
        import zipfile
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for page_idx, pil_img in enumerate(pil_images):
                page_bgr = pil_to_bgr(pil_img)

                # Run detection
                detections = run_yolo_on_page(model=model, page_bgr=page_bgr)

                # Draw bounding boxes
                annotated = page_bgr.copy()
                for det in detections:
                    conf = det.get('conf', 0.0)
                    if conf < confidence_threshold:
                        continue

                    class_name = det.get('name', 'unknown')

                    # Get polygon points
                    if 'poly' in det:
                        poly = det['poly']  # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                        pts = np.array(poly, dtype=np.int32)

                        # Draw polygon
                        cv2.polylines(annotated, [pts], True, (0, 255, 0), 3)

                        # Add label
                        label = f"{class_name} {conf:.2f}"
                        cv2.putText(
                            annotated,
                            label,
                            (int(poly[0][0]), int(poly[0][1]) - 10),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.0,
                            (0, 255, 0),
                            2
                        )

                # Convert back to image
                annotated_pil = Image.fromarray(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))

                # Save to ZIP
                img_bytes = io.BytesIO()
                annotated_pil.save(img_bytes, format='PNG')
                zip_file.writestr(f"page_{page_idx + 1}_annotated.png", img_bytes.getvalue())

        # Prepare ZIP for download
        zip_buffer.seek(0)

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=detections_{file.filename}.zip"}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
```

**Test it:**
```bash
# Get annotated images
curl -X POST "http://localhost:8000/detect/visualize" \
  -F "file=@plan.pdf" \
  -F "confidence_threshold=0.7" \
  --output detections.zip
```

---

## 4. Better Logging with Loguru

**Replace print statements in api.py:**

```python
# At the top of api.py
from loguru import logger
import sys

# Configure logging
logger.remove()  # Remove default handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)
logger.add(
    "logs/api_{time:YYYY-MM-DD}.log",
    rotation="00:00",  # Rotate daily
    retention="30 days",
    compression="zip",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    level="DEBUG"
)

# Replace all print() statements:
# Before:
print(f"Model loaded successfully from {model_path}")

# After:
logger.info(f"Model loaded successfully from {model_path}")
logger.success(f"API started successfully")
logger.warning(f"Model not found at {model_path}")
logger.error(f"Error loading model: {e}")
logger.debug(f"Processing page {page_idx + 1}/{len(pil_images)}")
```

**Add request logging middleware:**

```python
from fastapi import Request
import time

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all API requests"""
    start_time = time.time()

    # Log request
    logger.info(f"Request: {request.method} {request.url.path}")

    # Process request
    response = await call_next(request)

    # Log response
    process_time = time.time() - start_time
    logger.info(
        f"Response: {request.method} {request.url.path} "
        f"Status={response.status_code} Time={process_time:.3f}s"
    )

    return response
```

**Benefits:**
- ✅ Colored console output for easy debugging
- ✅ Automatic file rotation (daily)
- ✅ Compressed old logs (saves space)
- ✅ Different log levels (DEBUG, INFO, WARNING, ERROR)
- ✅ Request timing and status tracking

---

## 5. Statistics Endpoint

**Add to api.py:**

```python
from datetime import datetime
from collections import defaultdict

# Global stats (in production, use Redis or database)
api_stats = {
    "start_time": datetime.now(),
    "total_requests": 0,
    "detect_requests": 0,
    "total_detections": 0,
    "errors": 0,
    "classes_detected": defaultdict(int)
}

@app.middleware("http")
async def track_stats(request: Request, call_next):
    """Track API statistics"""
    api_stats["total_requests"] += 1

    if request.url.path.startswith("/detect"):
        api_stats["detect_requests"] += 1

    try:
        response = await call_next(request)
        return response
    except Exception as e:
        api_stats["errors"] += 1
        raise

@app.get("/stats")
async def get_statistics():
    """Get API usage statistics"""
    uptime = (datetime.now() - api_stats["start_time"]).total_seconds()

    return {
        "uptime_seconds": uptime,
        "uptime_formatted": f"{uptime // 3600:.0f}h {(uptime % 3600) // 60:.0f}m",
        "total_requests": api_stats["total_requests"],
        "detect_requests": api_stats["detect_requests"],
        "total_detections": api_stats["total_detections"],
        "errors": api_stats["errors"],
        "requests_per_hour": api_stats["total_requests"] / (uptime / 3600) if uptime > 0 else 0,
        "top_detected_classes": dict(
            sorted(
                api_stats["classes_detected"].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
        ),
        "model_loaded": model is not None
    }
```

**Update detection endpoint to track stats:**

```python
# In detect_symbols() function, after successful detection:
api_stats["total_detections"] += len(all_detections)
for det in all_detections:
    api_stats["classes_detected"][det.class_name] += 1
```

**Test it:**
```bash
curl http://localhost:8000/stats
```

**Example Response:**
```json
{
  "uptime_seconds": 3600,
  "uptime_formatted": "1h 0m",
  "total_requests": 150,
  "detect_requests": 45,
  "total_detections": 2340,
  "errors": 2,
  "requests_per_hour": 150.0,
  "top_detected_classes": {
    "signal": 850,
    "weiche": 420,
    "text": 1070
  },
  "model_loaded": true
}
```

---

## 6. How to Use

### Step 1: Install Dev Dependencies
```bash
cd Gleisplanextraktorv3
pip install -r requirements-dev.txt
```

### Step 2: Run Tests
```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
# Open htmlcov/index.html to see coverage report
```

### Step 3: Format Code
```bash
# Format code with black
black api.py

# Sort imports
isort api.py

# Check code quality
flake8 api.py
```

### Step 4: Run API with Logging
```bash
# Run API
python api.py

# Or with uvicorn
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

### Step 5: Test New Endpoints
```bash
# Test batch processing
curl -X POST "http://localhost:8000/detect/batch" \
  -F "files=@plan1.pdf" \
  -F "files=@plan2.pdf"

# Get visualization
curl -X POST "http://localhost:8000/detect/visualize" \
  -F "file=@plan.pdf" \
  --output annotated.zip

# Check statistics
curl http://localhost:8000/stats

# Check logs
tail -f logs/api_$(date +%Y-%m-%d).log
```

---

## 7. Docker Integration

### Update Dockerfile to include tests
```dockerfile
# Add testing stage
FROM python:3.10-slim as test

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

COPY . .
RUN pytest tests/ -v
```

### Update GitHub Actions to run tests
```yaml
# In .github/workflows/docker-publish.yml
- name: Run tests
  run: |
    pip install -r requirements-dev.txt
    pytest tests/ -v --cov=. --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
  with:
    file: ./coverage.xml
```

---

## Summary of Improvements

| Feature | Status | Priority | Learning Value |
|---------|--------|----------|----------------|
| Tests | ✅ Created | High | **★★★★★** Learn pytest basics |
| Batch Processing | 📝 Template provided | Medium | **★★★☆☆** Practical endpoint design |
| Visualization | 📝 Template provided | High | **★★★★☆** Image processing + API |
| Better Logging | 📝 Template provided | High | **★★★★★** Production best practice |
| Statistics | 📝 Template provided | Low | **★★★☆☆** Monitoring basics |
| Docker Tests | 📝 Template provided | Medium | **★★★★☆** CI/CD integration |

---

## Next Steps

1. **Start Small**: Pick ONE improvement to implement
2. **Test It**: Make sure it works
3. **Commit**: `git add . && git commit -m "Add [feature]"`
4. **Push**: Let GitHub Actions build it
5. **Move On**: Pick the next improvement

**Recommended Order:**
1. Install pytest and run tests (5 minutes)
2. Add better logging with loguru (15 minutes)
3. Add statistics endpoint (20 minutes)
4. Add batch processing (30 minutes)
5. Add visualization endpoint (45 minutes)

---

*Created: April 2026*
*For: Phase 1 Polish - Production-Ready API*

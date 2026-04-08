# Railway Symbol Detection API - Docker Image
# Multi-stage build for optimized image size

FROM python:3.10-slim AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    YOLO_MODEL_PATH=/app/yolomodel/best.pt \
    POPPLER_PATH=/usr/bin \
    TESSERACT_PATH=/usr/bin/tesseract

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV dependencies
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # PDF processing
    poppler-utils \
    # OCR
    tesseract-ocr \
    tesseract-ocr-deu \
    tesseract-ocr-eng \
    # Utilities
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements-docker.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-docker.txt

# Copy application code
# Core modules
COPY config.py validation_config.py ./
COPY core/ ./core/
COPY utils/ ./utils/

# API and database
COPY api.py database_sqlite.py ./

# Profile configurations (if needed)
COPY profiles/ ./profiles/
COPY config/ ./config/

# Patch PyQt5 imports (replace with dummy imports for headless operation)
RUN sed -i 's/^from PyQt5.*$/# PATCHED: PyQt5 not available in Docker/' core/*.py && \
    sed -i 's/^from PyQt5.*$/# PATCHED: PyQt5 not available in Docker/' utils/*.py && \
    sed -i 's/^import sip$/# PATCHED: sip not available/' utils/*.py 2>/dev/null || true

# Create model directory (mount externally)
RUN mkdir -p /app/yolomodel

# Expose API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run FastAPI application
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

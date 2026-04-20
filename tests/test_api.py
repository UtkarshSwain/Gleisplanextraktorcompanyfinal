"""
API Tests for Gleisplan Symbol Detection
Tests all endpoints for correct behavior
"""

import pytest
from fastapi.testclient import TestClient
from api import app
import io
from PIL import Image
import numpy as np


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def sample_pdf_bytes():
    """Create a simple PDF-like bytes for testing"""
    # Create a simple image and convert to bytes
    img = Image.new('RGB', (100, 100), color='white')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes.getvalue()


class TestHealthEndpoints:
    """Test health and info endpoints"""

    def test_root_endpoint(self, client):
        """Test root endpoint returns API info"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "endpoints" in data
        assert isinstance(data["endpoints"], list)

    def test_health_check(self, client):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "model_loaded" in data
        assert "model_path" in data
        assert "version" in data
        # Status should be either "healthy" or "degraded"
        assert data["status"] in ["healthy", "degraded"]

    def test_version_endpoint(self, client):
        """Test version endpoint"""
        response = client.get("/version")
        assert response.status_code == 200
        data = response.json()
        assert "api_version" in data
        assert "model_loaded" in data
        assert "build" in data
        assert data["build"] == "docker-automated"

    def test_classes_endpoint(self, client):
        """Test classes endpoint returns symbol classes"""
        response = client.get("/classes")
        assert response.status_code == 200
        data = response.json()
        assert "classes" in data
        assert "num_classes" in data
        assert isinstance(data["classes"], list)
        assert data["num_classes"] == len(data["classes"])


class TestDetectionEndpoint:
    """Test detection endpoint"""

    def test_detect_without_file(self, client):
        """Test detection fails without file"""
        response = client.post("/detect")
        assert response.status_code == 422  # Unprocessable Entity

    def test_detect_with_non_pdf(self, client):
        """Test detection rejects non-PDF files"""
        # Create a fake image file
        fake_file = io.BytesIO(b"not a pdf")
        response = client.post(
            "/detect",
            files={"file": ("test.txt", fake_file, "text/plain")}
        )
        # Should return 400 (bad file) or 503 (model not loaded)
        assert response.status_code in [400, 503]
        if response.status_code == 400:
            assert "PDF" in response.json()["detail"]

    def test_detect_endpoint_structure(self, client, sample_pdf_bytes):
        """Test detection endpoint response structure"""
        # Note: This will fail if model is not loaded, which is expected in tests
        response = client.post(
            "/detect",
            files={"file": ("test.pdf", io.BytesIO(sample_pdf_bytes), "application/pdf")}
        )

        # Should either succeed (200) or fail with 503 (model not loaded)
        assert response.status_code in [200, 503]

        if response.status_code == 503:
            # Model not loaded is expected in test environment
            assert "Model not loaded" in response.json()["detail"]
        else:
            # If model is loaded, check response structure
            data = response.json()
            assert "success" in data
            assert "num_pages" in data
            assert "num_detections" in data
            assert "detections" in data
            assert isinstance(data["detections"], list)


class TestAPIDocumentation:
    """Test API documentation endpoints"""

    def test_openapi_schema(self, client):
        """Test OpenAPI schema is available"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

    def test_docs_endpoint(self, client):
        """Test Swagger UI is available"""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    def test_redoc_endpoint(self, client):
        """Test ReDoc is available"""
        response = client.get("/redoc")
        assert response.status_code == 200


class TestErrorHandling:
    """Test error handling"""

    def test_404_for_unknown_endpoint(self, client):
        """Test 404 for unknown endpoints"""
        response = client.get("/unknown-endpoint")
        assert response.status_code == 404

    def test_method_not_allowed(self, client):
        """Test wrong HTTP method"""
        # GET on a POST-only endpoint
        response = client.get("/detect")
        assert response.status_code == 405  # Method Not Allowed


if __name__ == "__main__":
    # Run tests with: pytest tests/test_api.py -v
    pytest.main([__file__, "-v", "--tb=short"])

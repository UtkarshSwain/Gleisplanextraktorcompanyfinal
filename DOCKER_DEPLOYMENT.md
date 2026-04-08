# Docker Deployment Guide

This guide explains how to build, run, and deploy the Railway Symbol Detection API using Docker and GitHub Actions CI/CD.

## Prerequisites

- Docker Desktop installed ([download here](https://www.docker.com/products/docker-desktop))
- YOLO model weights file (`best.pt`)
- Git and GitHub account (for CI/CD)

## Quick Start

### 1. Build Docker Image Locally

```bash
# Navigate to project directory
cd Gleisplanextraktorv3

# Build the Docker image
docker build -t railway-detection-api:latest .
```

### 2. Run the Container

```bash
# Run with model mounted from local directory
docker run -d \
  --name railway-api \
  -p 8000:8000 \
  -v "$(pwd)/yolomodel:/app/yolomodel" \
  railway-detection-api:latest
```

**Windows PowerShell:**
```powershell
docker run -d --name railway-api -p 8000:8000 -v "${PWD}/yolomodel:/app/yolomodel" railway-detection-api:latest
```

### 3. Test the API

Open your browser or use curl:

```bash
# Health check
curl http://localhost:8000/health

# Get detectable classes
curl http://localhost:8000/classes

# Detect symbols in PDF
curl -X POST http://localhost:8000/detect \
  -F "file=@your_gleisplan.pdf" \
  -F "dpi=500"
```

**Swagger UI:** http://localhost:8000/docs

### 4. Stop the Container

```bash
docker stop railway-api
docker rm railway-api
```

## CI/CD Pipeline

### How It Works

The GitHub Actions workflow (`.github/workflows/docker-publish.yml`) automatically:

1. **On every push to main/master:**
   - Runs syntax checks
   - Builds Docker image
   - Pushes to GitHub Container Registry (GHCR)
   - Runs security scan with Trivy

2. **On pull requests:**
   - Runs tests only
   - Builds image (doesn't push)

3. **On version tags (e.g., v1.0.0):**
   - Creates versioned image tags
   - Marks as release

### Setting Up CI/CD

#### 1. Enable GitHub Actions

- Go to your repository on GitHub
- Navigate to **Settings > Actions > General**
- Enable "Allow all actions and reusable workflows"

#### 2. Enable GitHub Container Registry

- Go to **Settings > Actions > General > Workflow permissions**
- Select "Read and write permissions"
- Check "Allow GitHub Actions to create and approve pull requests"

#### 3. Push Your Code

```bash
# Add all Docker files
git add Dockerfile requirements-docker.txt api.py .dockerignore
git add .github/workflows/docker-publish.yml

# Commit
git commit -m "Add Docker deployment and CI/CD pipeline

- FastAPI REST API for headless symbol detection
- Multi-stage Dockerfile with optimizations
- GitHub Actions workflow for automated builds
- Push to GitHub Container Registry"

# Push to trigger CI/CD
git push origin feature/docker-deployment
```

#### 4. View Build Status

- Go to **Actions** tab on GitHub
- Click on the latest workflow run
- Monitor build progress

### Using Images from GHCR

Once the CI/CD pipeline runs, your image will be available at:

```
ghcr.io/utkarshswain/gleisplanextraktorcompanyfinal:latest
```

Pull and run:

```bash
# Login to GHCR (one-time setup)
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Pull image
docker pull ghcr.io/utkarshswain/gleisplanextraktorcompanyfinal:latest

# Run from GHCR
docker run -d \
  --name railway-api \
  -p 8000:8000 \
  -v "$(pwd)/yolomodel:/app/yolomodel" \
  ghcr.io/utkarshswain/gleisplanextraktorcompanyfinal:latest
```

## Production Deployment

### Option 1: Railway.app (Free Tier Available)

1. Go to [railway.app](https://railway.app)
2. Connect your GitHub repository
3. Deploy from Docker image
4. Add environment variables:
   - `YOLO_MODEL_PATH=/app/yolomodel/best.pt`
5. Upload model via Railway CLI or mount volume

### Option 2: Render.com (Free Tier Available)

1. Go to [render.com](https://render.com)
2. Create new "Web Service"
3. Connect GitHub repo
4. Set environment to "Docker"
5. Deploy

### Option 3: Fly.io (Free Tier Available)

```bash
# Install flyctl
brew install flyctl  # macOS
# or download from https://fly.io/docs/hands-on/install-flyctl/

# Login and deploy
flyctl auth login
flyctl launch
flyctl deploy
```

### Option 4: Your Own Server

```bash
# SSH to your server
ssh user@your-server.com

# Pull and run
docker pull ghcr.io/utkarshswain/gleisplanextraktorcompanyfinal:latest
docker run -d \
  --name railway-api \
  -p 8000:8000 \
  --restart unless-stopped \
  -v /path/to/models:/app/yolomodel \
  ghcr.io/utkarshswain/gleisplanextraktorcompanyfinal:latest
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `YOLO_MODEL_PATH` | `/app/yolomodel/best.pt` | Path to YOLO model weights |
| `POPPLER_PATH` | `/usr/bin` | Path to poppler utilities |
| `TESSERACT_PATH` | `/usr/bin/tesseract` | Path to Tesseract OCR |

## API Endpoints

### `GET /`
Root endpoint with API information

### `GET /health`
Health check and model status
```json
{
  "status": "healthy",
  "model_loaded": true,
  "model_path": "/app/yolomodel/best.pt",
  "version": "2.0.0"
}
```

### `GET /classes`
List of detectable symbol classes
```json
{
  "classes": ["signal", "gm_block", "gks_festkodiert", ...],
  "num_classes": 13
}
```

### `POST /detect`
Detect symbols in uploaded PDF

**Request:**
- Form data: `file` (PDF file)
- Optional: `dpi` (integer, default from config)

**Response:**
```json
{
  "success": true,
  "num_pages": 1,
  "num_detections": 42,
  "detections": [
    {
      "class_name": "signal",
      "confidence": 0.95,
      "bbox": [x1, y1, x2, y2, x3, y3, x4, y4],
      "page": 1
    }
  ],
  "message": "Processed 1 pages successfully"
}
```

## Troubleshooting

### Model not loading
```bash
# Check if model file exists in container
docker exec railway-api ls -lh /app/yolomodel/

# Check logs
docker logs railway-api
```

### Permission errors
```bash
# Ensure model directory is readable
chmod -R 755 yolomodel/
```

### Out of memory
```bash
# Increase Docker memory limit
# Docker Desktop > Settings > Resources > Memory

# Or limit container memory
docker run --memory="4g" ...
```

### PDF conversion fails
```bash
# Verify poppler is installed
docker exec railway-api which pdftoppm

# Check logs for specific error
docker logs railway-api -f
```

## Development

### Building with custom base image
```dockerfile
# Modify Dockerfile to use specific Python version
FROM python:3.11-slim AS base
```

### Adding new dependencies
```bash
# Edit requirements-docker.txt
echo "new-package>=1.0.0" >> requirements-docker.txt

# Rebuild
docker build -t railway-detection-api:dev .
```

### Testing locally without Docker
```bash
# Install dependencies
pip install -r requirements-docker.txt

# Run API
python api.py
```

## Security

### Secrets in GitHub Actions

Never commit secrets. Use GitHub Secrets instead:
1. Go to **Settings > Secrets and variables > Actions**
2. Add secrets like API keys, tokens
3. Reference in workflow: `${{ secrets.MY_SECRET }}`

### Scanning for vulnerabilities

The CI/CD pipeline includes Trivy security scanning. View results in:
- **Security > Code scanning** on GitHub

## Next Steps

- [ ] Set up monitoring (Prometheus/Grafana)
- [ ] Add rate limiting
- [ ] Implement authentication
- [ ] Add model versioning
- [ ] Set up automated testing with sample PDFs

## Support

For issues related to:
- Docker: Check Docker logs (`docker logs railway-api`)
- CI/CD: Check Actions tab on GitHub
- API: Check Swagger UI at `/docs`

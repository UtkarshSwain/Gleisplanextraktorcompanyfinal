# Learning Resources & Career Development
## Connected to Gleisplan Prototype

*For Utkarsh Swain - Post-Masterarbeit Skill Development*

---

## Table of Contents
1. [MLOps & Deployment](#1-mlops--deployment-highest-priority)
2. [Deep Learning Advanced](#2-deep-learning-advanced)
3. [LLM & Document AI](#3-llm--document-ai)
4. [Cloud & Infrastructure](#4-cloud--infrastructure)
5. [Data & Experiment Management](#5-data--experiment-management)
6. [Prototype Improvements](#6-prototype-specific-improvements)
7. [Learning Method](#7-learning-method)
8. [Quick Reference Commands](#8-quick-reference-commands)

---

## 1. MLOps & Deployment (Highest Priority)

> **Why Priority #1:** AI + Deployment skills = €€€ (very rare combination in Germany)

### 1.1 Docker

| | |
|---|---|
| **Official Tutorial** | https://docs.docker.com/get-started/ |
| **Video (optional)** | TechWorld with Nana - Docker Tutorial (YouTube, 3hrs) |
| **Cheatsheet** | https://docs.docker.com/get-started/docker_cheatsheet.pdf |

**Apply to Prototype:**
```dockerfile
# Your first Dockerfile for Gleisplan
FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY models/ ./models/
COPY src/ ./src/

CMD ["python", "src/main.py"]
```

**Practice Tasks:**
- [ ] Write Dockerfile for your detection pipeline
- [ ] Build image: `docker build -t gleisplan-detector:v1 .`
- [ ] Run container: `docker run -v /path/to/pdfs:/data gleisplan-detector:v1`
- [ ] Push to Docker Hub (free account)

---

### 1.2 FastAPI

| | |
|---|---|
| **Official Tutorial** | https://fastapi.tiangolo.com/tutorial/ |
| **Full Course** | https://fastapi.tiangolo.com/learn/ |
| **Video** | "FastAPI Full Course" by Sanjeev Thiyagarajan (YouTube, 19hrs - pick sections) |

**Apply to Prototype:**
```python
# api.py - Your detection API
from fastapi import FastAPI, UploadFile, File
from typing import List
import uvicorn

app = FastAPI(title="Gleisplan Symbol Detection API")

@app.post("/detect")
async def detect_symbols(file: UploadFile = File(...)):
    """Upload PDF, return detected symbols as JSON"""
    # Your YOLO inference code here
    return {"symbols": [...], "count": 42}

@app.post("/compare")
async def compare_versions(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...)
):
    """Compare two Gleispläne using Hungarian Algorithm"""
    # Your comparison code here
    return {"changes": [...], "added": [], "removed": []}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "model_loaded": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

**Practice Tasks:**
- [ ] Create `/detect` endpoint - upload PDF, return JSON
- [ ] Create `/compare` endpoint - compare two PDFs
- [ ] Add Swagger docs (automatic with FastAPI)
- [ ] Test with `curl` and Postman

---

### 1.3 GitHub Actions (CI/CD)

| | |
|---|---|
| **Quickstart** | https://docs.github.com/en/actions/quickstart |
| **Full Docs** | https://docs.github.com/en/actions |
| **ML-specific** | https://github.com/iterative/setup-cml (CML for ML pipelines) |

**Apply to Prototype:**
```yaml
# .github/workflows/test-and-build.yml
name: Test and Build

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest tests/ -v

  build:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build Docker image
        run: docker build -t gleisplan-detector:${{ github.sha }} .
      - name: Push to Registry
        run: |
          echo ${{ secrets.DOCKER_PASSWORD }} | docker login -u ${{ secrets.DOCKER_USERNAME }} --password-stdin
          docker push gleisplan-detector:${{ github.sha }}
```

**Practice Tasks:**
- [ ] Create workflow that runs pytest on every push
- [ ] Add Docker build step
- [ ] Add automated model inference test (run on sample PDF)

---

### 1.4 MLflow

| | |
|---|---|
| **Quickstart** | https://mlflow.org/docs/latest/quickstarts/mlflow-tracing-quickstart.html |
| **Tracking Guide** | https://mlflow.org/docs/latest/tracking.html |
| **Model Registry** | https://mlflow.org/docs/latest/model-registry.html |

**Apply to Prototype:**
```python
# track_experiments.py
import mlflow
import mlflow.pytorch

# Set experiment
mlflow.set_experiment("gleisplan-yolo-training")

with mlflow.start_run(run_name="yolov8-obb-500dpi"):
    # Log parameters
    mlflow.log_param("dpi", 500)
    mlflow.log_param("model", "yolov8m-obb")
    mlflow.log_param("epochs", 100)
    mlflow.log_param("batch_size", 16)
    mlflow.log_param("augmentation", "mosaic+mixup")
    
    # Log metrics (from your evaluation)
    mlflow.log_metric("mAP50", 0.9993)
    mlflow.log_metric("e2e_accuracy", 0.9708)
    mlflow.log_metric("linking_accuracy", 0.9925)
    mlflow.log_metric("inference_time_sec", 10.6 * 60)
    
    # Log model
    mlflow.pytorch.log_model(model, "yolo-model")
    
    # Log artifacts (confusion matrix, sample outputs)
    mlflow.log_artifact("confusion_matrix.png")
    mlflow.log_artifact("sample_detection.png")
```

**Practice Tasks:**
- [ ] Install: `pip install mlflow`
- [ ] Log your existing 2 models (B/W and Color)
- [ ] Run MLflow UI: `mlflow ui` → http://localhost:5000
- [ ] Compare runs visually

---

## 2. Deep Learning Advanced

### 2.1 PyTorch (Foundation)

| | |
|---|---|
| **60-Minute Blitz** | https://pytorch.org/tutorials/beginner/deep_learning_60min_blitz.html |
| **Full Course (Free)** | https://www.learnpytorch.io/ |
| **Official Tutorials** | https://pytorch.org/tutorials/ |

**Why It Matters for You:**
- Ultralytics YOLO is built on PyTorch
- Understanding lets you customize training loops
- Debug inference issues at tensor level
- Fine-tune models properly

**Apply to Prototype:**
```python
# Understand what YOLO does internally
import torch
from ultralytics import YOLO

# Load your model
model = YOLO("your_model.pt")

# Access PyTorch model directly
pytorch_model = model.model

# Inspect layers
for name, layer in pytorch_model.named_modules():
    print(f"{name}: {layer.__class__.__name__}")

# Custom inference with hooks (for debugging)
activations = {}
def get_activation(name):
    def hook(model, input, output):
        activations[name] = output.detach()
    return hook

# Register hook on detection head
pytorch_model.model[-1].register_forward_hook(get_activation('detection_head'))
```

**Practice Tasks:**
- [ ] Complete 60-minute blitz
- [ ] Implement simple CNN for MNIST from scratch
- [ ] Load your YOLO model, inspect architecture
- [ ] Write custom data loader for your Gleisplan images

---

### 2.2 ONNX + TensorRT (Model Optimization)

| | |
|---|---|
| **ONNX Runtime** | https://onnxruntime.ai/docs/ |
| **Ultralytics Export** | https://docs.ultralytics.com/modes/export/ |
| **TensorRT Guide** | https://docs.nvidia.com/deeplearning/tensorrt/developer-guide/ |

**Apply to Prototype:**
```python
# Export YOLO to ONNX
from ultralytics import YOLO

model = YOLO("your_model.pt")

# Export to ONNX
model.export(format="onnx", imgsz=1280, half=False)

# Export to TensorRT (requires NVIDIA GPU)
model.export(format="engine", imgsz=1280, half=True)  # FP16 for speed
```

```python
# Benchmark comparison
import time
import onnxruntime as ort

# ONNX inference
session = ort.InferenceSession("your_model.onnx")

# Warm-up
for _ in range(10):
    session.run(None, {"images": image_array})

# Benchmark
start = time.time()
for _ in range(100):
    session.run(None, {"images": image_array})
print(f"ONNX: {(time.time() - start) / 100 * 1000:.2f} ms/image")
```

**Practice Tasks:**
- [ ] Export both models to ONNX
- [ ] Benchmark PyTorch vs ONNX inference time
- [ ] Test accuracy is maintained after export
- [ ] (If GPU available) Export to TensorRT

---

### 2.3 Transformers & Attention

| | |
|---|---|
| **Best Video Ever** | Andrej Karpathy "Let's build GPT" - https://www.youtube.com/watch?v=kCc8FmEb1nY |
| **Hugging Face Course** | https://huggingface.co/learn/nlp-course |
| **Attention Paper** | "Attention Is All You Need" - https://arxiv.org/abs/1706.03762 |
| **Visual Explanation** | https://jalammar.github.io/illustrated-transformer/ |

**Why It Matters:**
- Document AI is moving to transformers (LayoutLM, Donut)
- Your OCR linking could use attention mechanisms
- Understanding attention = understanding modern AI

**Future Prototype Application:**
```python
# Document understanding with LayoutLMv3
from transformers import AutoProcessor, AutoModelForTokenClassification

processor = AutoProcessor.from_pretrained("microsoft/layoutlmv3-base")
model = AutoModelForTokenClassification.from_pretrained(
    "microsoft/layoutlmv3-base",
    num_labels=12  # Your 12 symbol classes
)

# Process Gleisplan image
encoding = processor(
    image,
    return_tensors="pt",
)

# Get predictions
outputs = model(**encoding)
```

---

## 3. LLM & Document AI

### 3.1 LangChain + RAG

| | |
|---|---|
| **Official Tutorials** | https://python.langchain.com/docs/tutorials/ |
| **RAG Tutorial** | https://python.langchain.com/docs/tutorials/rag/ |
| **Video Course** | "LangChain for LLM Application Development" (DeepLearning.AI, free) |

**Apply to Prototype:**
```python
# Build Q&A system for Gleispläne
from langchain.vectorstores import Chroma
from langchain.embeddings import OpenAIEmbeddings
from langchain.chat_models import ChatOpenAI
from langchain.chains import RetrievalQA

# Your extracted data from PostgreSQL
documents = [
    {"content": "Signal HS1 at coordinate (1200, 450), linked to text 'HS1'"},
    {"content": "Weiche W12 at coordinate (800, 320), linked to text 'W12'"},
    # ... all your extracted symbols
]

# Create vector store
vectorstore = Chroma.from_documents(documents, OpenAIEmbeddings())

# Create QA chain
qa_chain = RetrievalQA.from_chain_type(
    llm=ChatOpenAI(model="gpt-4"),
    retriever=vectorstore.as_retriever()
)

# Query
answer = qa_chain.run("What signals are near Weiche W12?")
```

**Practice Tasks:**
- [ ] Install: `pip install langchain langchain-openai chromadb`
- [ ] Export your PostgreSQL data as documents
- [ ] Build simple RAG system for your extractions
- [ ] Test queries about your Gleispläne

---

### 3.2 Document AI Models

| | |
|---|---|
| **LayoutLMv3** | https://huggingface.co/microsoft/layoutlmv3-base |
| **Donut** | https://huggingface.co/naver-clova-ix/donut-base |
| **PaddleOCR LayoutParser** | https://github.com/PaddlePaddle/PaddleOCR/blob/release/2.6/ppstructure/docs/quickstart_en.md |
| **DocTR** | https://github.com/mindee/doctr |

**Comparison for Your Use Case:**

| Model | Pros | Cons | Fit for Gleisplan |
|-------|------|------|-------------------|
| **LayoutLMv3** | Best for documents with text | Needs fine-tuning | Medium |
| **Donut** | End-to-end, no OCR needed | Newer, less tested | Worth trying |
| **Your YOLO+OCR** | Already works at 97% | Custom, not standard | Current solution |

**Future Enhancement:**
```python
# Try Donut for comparison
from transformers import DonutProcessor, VisionEncoderDecoderModel

processor = DonutProcessor.from_pretrained("naver-clova-ix/donut-base")
model = VisionEncoderDecoderModel.from_pretrained("naver-clova-ix/donut-base")

# Generate structured output
pixel_values = processor(image, return_tensors="pt").pixel_values
outputs = model.generate(pixel_values)
result = processor.batch_decode(outputs, skip_special_tokens=True)
```

---

## 4. Cloud & Infrastructure

### 4.1 AWS SageMaker

| | |
|---|---|
| **Workshop (Free)** | https://sagemaker-workshop.com/ |
| **Official Docs** | https://docs.aws.amazon.com/sagemaker/ |
| **Deploy PyTorch** | https://docs.aws.amazon.com/sagemaker/latest/dg/pytorch.html |

**Apply to Prototype:**
```python
# Deploy YOLO to SageMaker endpoint
import sagemaker
from sagemaker.pytorch import PyTorchModel

role = "arn:aws:iam::YOUR_ACCOUNT:role/SageMakerRole"

model = PyTorchModel(
    model_data="s3://your-bucket/models/yolo-gleisplan.tar.gz",
    role=role,
    framework_version="2.0",
    py_version="py310",
    entry_point="inference.py"
)

predictor = model.deploy(
    instance_type="ml.g4dn.xlarge",  # Same GPU you used for training
    initial_instance_count=1
)

# Now you have a scalable API endpoint!
result = predictor.predict({"image": image_base64})
```

**Practice Tasks:**
- [ ] Package your model for SageMaker
- [ ] Create inference.py with model_fn and predict_fn
- [ ] Deploy to endpoint
- [ ] Test inference from your laptop

---

### 4.2 Kubernetes (Basics Only)

| | |
|---|---|
| **Official Tutorial** | https://kubernetes.io/docs/tutorials/kubernetes-basics/ |
| **Minikube** | https://minikube.sigs.k8s.io/docs/start/ |
| **K8s for ML** | https://www.kubeflow.org/docs/started/ |

**When to Learn:** After Docker is solid. Don't rush this.

**Basic Deployment:**
```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: gleisplan-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: gleisplan-api
  template:
    metadata:
      labels:
        app: gleisplan-api
    spec:
      containers:
      - name: api
        image: your-registry/gleisplan-detector:v1
        ports:
        - containerPort: 8000
        resources:
          limits:
            nvidia.com/gpu: 1
```

---

## 5. Data & Experiment Management

### 5.1 DVC (Data Version Control)

| | |
|---|---|
| **Get Started** | https://dvc.org/doc/start |
| **Tutorial** | https://dvc.org/doc/start/data-management |
| **With Git** | https://dvc.org/doc/use-cases/versioning-data-and-models |

**Apply to Prototype:**
```bash
# Initialize DVC in your project
cd gleisplan-project
dvc init

# Track your training data
dvc add data/training_images/
dvc add data/annotations/

# Track models
dvc add models/yolo_bw.pt
dvc add models/yolo_color.pt

# Commit to Git
git add data/.gitignore data/training_images.dvc models/yolo_bw.pt.dvc
git commit -m "Track training data and models with DVC"

# Push data to remote storage
dvc remote add -d s3remote s3://your-bucket/dvc-storage
dvc push
```

**Practice Tasks:**
- [ ] Install: `pip install dvc dvc-s3`
- [ ] Track your training dataset
- [ ] Track your trained models
- [ ] Push to S3 (use your existing bucket)

---

### 5.2 Weights & Biases (Alternative to MLflow)

| | |
|---|---|
| **Quickstart** | https://docs.wandb.ai/quickstart |
| **PyTorch Integration** | https://docs.wandb.ai/guides/integrations/pytorch |
| **YOLO Integration** | Built into Ultralytics! |

**Apply to Prototype:**
```python
# Ultralytics has built-in W&B support!
from ultralytics import YOLO

# Just set environment variable
import os
os.environ["WANDB_PROJECT"] = "gleisplan-detection"

# Train with automatic logging
model = YOLO("yolov8m-obb.pt")
model.train(
    data="gleisplan.yaml",
    epochs=100,
    # W&B logs automatically!
)
```

**Practice Tasks:**
- [ ] Create free W&B account: https://wandb.ai/
- [ ] `pip install wandb && wandb login`
- [ ] Retrain model with W&B logging
- [ ] View training curves in dashboard

---

## 6. Prototype-Specific Improvements

### 6.1 Logging (Replace print statements)

| | |
|---|---|
| **Loguru** | https://github.com/Delgan/loguru |
| **Standard logging** | https://docs.python.org/3/howto/logging.html |

```python
# Replace all print() with loguru
from loguru import logger

# Configure
logger.add("gleisplan_{time}.log", rotation="10 MB")

# Use instead of print()
logger.info("Processing PDF: {}", pdf_path)
logger.debug("Detected {} symbols", len(detections))
logger.warning("Low confidence detection: {}", symbol)
logger.error("OCR failed for region: {}", region)
```

---

### 6.2 Configuration Management

| | |
|---|---|
| **Hydra** | https://hydra.cc/docs/intro/ |
| **Simple YAML** | https://pyyaml.org/wiki/PyYAMLDocumentation |

```yaml
# config.yaml - Replace all magic numbers
preprocessing:
  dpi: 500
  clahe_clip_limit: 2.0
  
detection:
  model_bw: "models/yolo_bw.pt"
  model_color: "models/yolo_color.pt"
  confidence_threshold: 0.5
  iou_threshold: 0.45

ocr:
  engine: "paddleocr"  # or "tesseract", "easyocr"
  angle_threshold: 15  # degrees
  
linking:
  max_distance: 50  # pixels
  direction_tolerance: 30  # degrees

export:
  format: "excel"  # or "json"
  output_dir: "outputs/"
```

```python
# Load config
import yaml

with open("config.yaml") as f:
    config = yaml.safe_load(f)

dpi = config["preprocessing"]["dpi"]
```

---

### 6.3 Error Handling

```python
# Proper error handling for production
class GleisplanError(Exception):
    """Base exception for Gleisplan processing"""
    pass

class PDFLoadError(GleisplanError):
    """Failed to load PDF"""
    pass

class DetectionError(GleisplanError):
    """YOLO detection failed"""
    pass

class OCRError(GleisplanError):
    """OCR extraction failed"""
    pass

# Usage
def process_pdf(pdf_path: str) -> dict:
    try:
        image = load_pdf(pdf_path)
    except Exception as e:
        logger.error(f"Failed to load PDF: {e}")
        raise PDFLoadError(f"Cannot load {pdf_path}") from e
    
    try:
        detections = run_yolo(image)
    except Exception as e:
        logger.error(f"Detection failed: {e}")
        raise DetectionError("YOLO inference failed") from e
    
    return detections
```

---

## 7. Learning Method

### The 70/30 Rule
- **70%** building prototype improvements
- **30%** pure learning/tutorials

Everything connects back to your real project.

### Build, Don't Watch
- Tutorials → understanding syntax
- Real learning → implementing for your prototype
- Break things → fix them → actual understanding

### One Thing at a Time
```
Week 1-2: Docker only
Week 3-4: FastAPI only
Week 5: Combine Docker + FastAPI
Week 6: Add CI/CD
```

### Recommended Sequence

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: Deployable ML (4-6 weeks)                        │
│  Docker → FastAPI → GitHub Actions                         │
│  Result: Your prototype runs as containerized API          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: Reproducible ML (2-3 weeks)                      │
│  MLflow/W&B → DVC                                          │
│  Result: All experiments tracked, data versioned           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: Optimized ML (2-3 weeks)                         │
│  PyTorch deeper → ONNX/TensorRT                            │
│  Result: Faster inference, production-ready models         │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  PHASE 4: Next-Gen Document AI (4+ weeks)                  │
│  LangChain/RAG → Transformers → Document AI                │
│  Result: Modern AI capabilities, LLM integration           │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Quick Reference Commands

### Docker
```bash
# Build
docker build -t gleisplan:v1 .

# Run
docker run -p 8000:8000 -v $(pwd)/data:/data gleisplan:v1

# Push
docker push your-username/gleisplan:v1

# Compose
docker-compose up -d
```

### FastAPI
```bash
# Run dev server
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Test endpoint
curl -X POST "http://localhost:8000/detect" -F "file=@plan.pdf"
```

### MLflow
```bash
# Start UI
mlflow ui --port 5000

# Run with tracking
MLFLOW_TRACKING_URI=http://localhost:5000 python train.py
```

### DVC
```bash
# Initialize
dvc init

# Track data
dvc add data/

# Push to remote
dvc push

# Pull data
dvc pull
```

### YOLO Export
```bash
# Python
yolo export model=your_model.pt format=onnx imgsz=1280

# CLI
yolo detect predict model=your_model.onnx source=image.png
```

### Git + DVC Workflow
```bash
# After training new model
dvc add models/new_model.pt
git add models/new_model.pt.dvc
git commit -m "Add new model trained on extended dataset"
dvc push
git push
```

---

## Bookmarks to Save

| Category | Resource | URL |
|----------|----------|-----|
| Docker | Official Docs | https://docs.docker.com/ |
| FastAPI | Tutorial | https://fastapi.tiangolo.com/tutorial/ |
| MLflow | Tracking | https://mlflow.org/docs/latest/tracking.html |
| PyTorch | Tutorials | https://pytorch.org/tutorials/ |
| Hugging Face | Course | https://huggingface.co/learn |
| LangChain | Docs | https://python.langchain.com/docs/ |
| Ultralytics | Docs | https://docs.ultralytics.com/ |
| W&B | Quickstart | https://docs.wandb.ai/quickstart |
| DVC | Get Started | https://dvc.org/doc/start |
| AWS SageMaker | Workshop | https://sagemaker-workshop.com/ |

---

## Notes

- All code examples are templates - adapt to your actual file structure
- Focus on one skill at a time
- Every tutorial should end with a prototype improvement
- Document your learnings in a personal wiki/notes

---

*Created: March 2025*
*For: Utkarsh Swain - Gleisplan Prototype Development*

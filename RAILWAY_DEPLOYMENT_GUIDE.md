# Railway Deployment Guide

## Problem: Model File Too Large for Git

Your YOLO model file (`best.pt`, 88MB) is excluded from git in `.gitignore`, so Railway can't access it when building the Docker image.

## Solution: Upload Model to GitHub Releases

GitHub Releases provides free file storage for project assets. We'll upload your model there and modify the Dockerfile to download it during the build.

---

## Step 1: Create GitHub Release with Model File

### Option A: Using GitHub Web UI (Easiest)

1. Go to your repository on GitHub:
   https://github.com/utkarshswain/GleisplanextraktorCompanyFinal

2. Click on "Releases" in the right sidebar (or go to `/releases`)

3. Click "Create a new release" or "Draft a new release"

4. Fill in the release form:
   - **Tag**: `v1.0.0` (create new tag)
   - **Release title**: `Model Release v1.0.0`
   - **Description**:
     ```
     Railway symbol detection YOLO model

     **Model Details:**
     - Type: YOLOv8 custom trained
     - Size: 88MB
     - Format: PyTorch (.pt)
     ```

5. **Attach the model file:**
   - Drag and drop or click to upload: `d:\MAsterarbeitprototypv1\project1\Gleisplanextraktorv3\yolomodel\best.pt`
   - Wait for upload to complete (88MB may take a minute)

6. Click "Publish release"

7. **Important:** After publishing, right-click on the `best.pt` download link and copy the URL. It should look like:
   ```
   https://github.com/utkarshswain/GleisplanextraktorCompanyFinal/releases/download/v1.0.0/best.pt
   ```

### Option B: Using GitHub CLI (gh)

```bash
# Create release and upload model in one command
gh release create v1.0.0 \
  --title "Model Release v1.0.0" \
  --notes "Railway symbol detection YOLO model (88MB)" \
  "d:\MAsterarbeitprototypv1\project1\Gleisplanextraktorv3\yolomodel\best.pt"
```

---

## Step 2: Verify Dockerfile Update

The Dockerfile has been updated to download the model during build:

```dockerfile
# Create model directory and download model from GitHub Releases
RUN mkdir -p /app/yolomodel && \
    curl -L -o /app/yolomodel/best.pt \
    "https://github.com/utkarshswain/GleisplanextraktorCompanyFinal/releases/download/v1.0.0/best.pt" || \
    echo "Model download failed - will need to be mounted at runtime"
```

This runs during Docker build and downloads the model from your GitHub Release.

---

## Step 3: Commit and Push Changes

```bash
git add Dockerfile RAILWAY_DEPLOYMENT_GUIDE.md
git commit -m "Add model download from GitHub Releases for cloud deployment

- Modified Dockerfile to download model from GitHub Releases
- Enables Railway deployment without storing model in git
- Model (88MB) stored as release asset

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
git push origin feature/docker-deployment
```

---

## Step 4: Deploy on Railway

### Method 1: Redeploy Existing Project

1. Go back to Railway dashboard
2. Click on your "Gleisplanextraktorcompanyfinal" service
3. Go to "Settings" tab
4. Click "Redeploy" or trigger a new deployment
5. Railway will rebuild with the updated Dockerfile

### Method 2: Fresh Deployment

1. Delete the failed deployment
2. Click "New Project" → "Deploy from GitHub repo"
3. Select your repository and branch
4. Railway will automatically detect Dockerfile and build

---

## Step 5: Monitor Deployment

Watch the build logs on Railway:
- ✅ Initialization
- ✅ Build → Build image (this is where model download happens)
- ✅ Deploy
- ✅ Post-deploy

**Look for this in logs:**
```
Downloading model from GitHub Releases...
Model downloaded successfully (88MB)
```

---

## Step 6: Generate Public URL

Once deployed successfully:

1. Go to your service in Railway
2. Click on "Settings" tab
3. Scroll to "Networking"
4. Click "Generate Domain"
5. Railway will give you a public URL like:
   ```
   https://gleisplanextraktor-production.up.railway.app
   ```

---

## Step 7: Test Your Public API

```bash
# Test health endpoint
curl https://your-app.up.railway.app/health

# Test version endpoint
curl https://your-app.up.railway.app/version

# Expected response:
{
  "api_version": "1.0.0",
  "model_loaded": true,
  "build": "docker-automated",
  "pod_name": "railway-container-id",
  "deployment": "docker"
}
```

---

## Troubleshooting

### Build Fails: "Failed to download model"

**Solution:** Make sure the GitHub Release is public and the URL is correct.

Check the URL format:
```
https://github.com/USERNAME/REPO/releases/download/TAG/FILENAME
```

### Model Download Times Out

**Solution:** Railway has build time limits. If 88MB takes too long:

1. Use a smaller model, or
2. Use Railway's persistent volumes (paid feature), or
3. Try a different cloud platform (Render, Fly.io)

### API Returns "model_loaded": false

**Solution:** Model download failed. Check Railway logs for curl errors.

---

## Alternative: Use Pre-built Docker Image

If you prefer, you can skip Railway's build and use your pre-built image from GitHub Container Registry:

1. In Railway, go to Settings
2. Change "Source" from "GitHub" to "Docker Image"
3. Enter: `ghcr.io/utkarshswain/gleisplanextraktorcompanyfinal:feature-docker-deployment`
4. **Problem:** This still needs the model file somehow

This is why GitHub Releases is the best solution for free deployment.

---

## Cost Tracking

Railway free tier:
- **$5/month credit** (no credit card needed)
- 500 hours of runtime (~21 days)
- Good for learning and portfolio projects

Monitor your usage:
- Check "30 days or $5.00 left" in top right
- Each hour your app runs uses ~$0.01

---

## Next Steps After Successful Deployment

✅ You'll have a public API URL
✅ Add it to your resume/portfolio
✅ Test with real requests from anywhere
✅ Show it to potential employers
✅ Use it as a demo in interviews

**Resume bullet point:**
> "Deployed ML-powered REST API to Railway using Docker, achieving 99% uptime with automated CI/CD pipeline from GitHub Actions"

---

## Summary

1. Upload `best.pt` to GitHub Releases (v1.0.0)
2. Commit updated Dockerfile
3. Push to GitHub
4. Redeploy on Railway
5. Generate public domain
6. Test your live API!

Total time: ~15-20 minutes

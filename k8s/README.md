# Kubernetes Deployment Guide
## Railway Symbol Detection API on Kubernetes

---

## What is This?

These files deploy your FastAPI application to Kubernetes with:
- **2 replicas** for high availability
- **Automatic health checks** and restarts
- **Load balancing** between instances
- **Resource limits** to prevent one container hogging resources

---

## Prerequisites

✅ Docker Desktop with Kubernetes enabled
✅ `kubectl` command-line tool (comes with Docker Desktop)
✅ Your Docker image pushed to GHCR

---

## Quick Start

### 1. Verify Kubernetes is Running

```bash
kubectl cluster-info
```

You should see:
```
Kubernetes control plane is running at https://kubernetes.docker.internal:6443
```

### 2. Deploy the API

```bash
# Apply all Kubernetes manifests
kubectl apply -f k8s/

# Or apply individually
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

### 3. Check Deployment Status

```bash
# See all pods
kubectl get pods

# Expected output:
# NAME                            READY   STATUS    RESTARTS   AGE
# gleisplan-api-xxxxxxxxx-xxxxx   1/1     Running   0          30s
# gleisplan-api-xxxxxxxxx-xxxxx   1/1     Running   0          30s

# See service
kubectl get services

# Expected output:
# NAME                     TYPE           CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
# gleisplan-api-service    LoadBalancer   10.96.x.x      localhost     80:xxxxx/TCP   30s
```

### 4. Access the API

```bash
# Get the service URL
kubectl get service gleisplan-api-service

# On Docker Desktop, it will be available at:
curl http://localhost/health
curl http://localhost/version
```

---

## Kubernetes Concepts Explained

### Deployment
**What:** Describes how to run your application
**Contains:**
- Docker image to use
- Number of replicas (copies)
- Resource limits (CPU, RAM)
- Health checks
- Environment variables

**Why:** If a pod crashes, Deployment automatically starts a new one

### Service
**What:** Network access to your pods
**Types:**
- `ClusterIP`: Internal only (default)
- `NodePort`: Accessible on specific port
- `LoadBalancer`: Accessible from outside (what we use)

**Why:** Pods have dynamic IPs; Service provides stable endpoint

### Pod
**What:** Running instance of your container
**Note:** You don't create pods directly; Deployment creates them

---

## Useful kubectl Commands

### Viewing Resources

```bash
# List all deployments
kubectl get deployments

# List all pods
kubectl get pods

# List all services
kubectl get services

# Get detailed info about a pod
kubectl describe pod <pod-name>

# View pod logs
kubectl logs <pod-name>

# Follow logs (like docker logs -f)
kubectl logs -f <pod-name>
```

### Managing Deployments

```bash
# Scale to 3 replicas
kubectl scale deployment gleisplan-api --replicas=3

# Update image (rolling update)
kubectl set image deployment/gleisplan-api api=ghcr.io/utkarshswain/gleisplanextraktorcompanyfinal:new-tag

# Restart all pods
kubectl rollout restart deployment gleisplan-api

# Check rollout status
kubectl rollout status deployment gleisplan-api
```

### Debugging

```bash
# Get shell inside a pod
kubectl exec -it <pod-name> -- /bin/bash

# Check events
kubectl get events --sort-by=.metadata.creationTimestamp

# Port forward to a specific pod
kubectl port-forward <pod-name> 8000:8000
```

### Cleanup

```bash
# Delete all resources
kubectl delete -f k8s/

# Or delete individually
kubectl delete deployment gleisplan-api
kubectl delete service gleisplan-api-service
```

---

## How It Works

```
┌─────────────────────────────────────────────────────────┐
│ User Request (http://localhost/detect)                  │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  Service (port 80)   │  ← Load Balancer
            │  gleisplan-api-svc   │
            └──────────┬───────────┘
                       │
        ┌──────────────┴──────────────┐
        │                             │
        ▼                             ▼
┌───────────────────┐         ┌───────────────────┐
│ Pod 1             │         │ Pod 2             │
│ ┌───────────────┐ │         │ ┌───────────────┐ │
│ │ Container     │ │         │ │ Container     │ │
│ │ (port 8000)   │ │         │ │ (port 8000)   │ │
│ │ FastAPI + YOLO│ │         │ │ FastAPI + YOLO│ │
│ └───────────────┘ │         │ └───────────────┘ │
└───────────────────┘         └───────────────────┘
```

**What happens:**
1. Request comes to Service on port 80
2. Service picks one of the 2 pods (round-robin)
3. Pod processes request and returns response
4. If Pod 1 crashes, Pod 2 still handles requests
5. Kubernetes automatically starts a new Pod 1

---

## Health Checks

Your API has 2 types of health checks:

### Liveness Probe
**Question:** "Is the pod alive?"
**Action:** Calls `/health` every 10 seconds
**If fails:** Restart the pod

### Readiness Probe
**Question:** "Is the pod ready to serve traffic?"
**Action:** Calls `/health` every 5 seconds
**If fails:** Stop sending traffic to this pod (but don't restart)

---

## Resource Management

### Requests vs Limits

```yaml
resources:
  requests:  # Guaranteed minimum
    memory: "2Gi"
    cpu: "1000m"  # 1 CPU core
  limits:    # Maximum allowed
    memory: "4Gi"
    cpu: "2000m"  # 2 CPU cores
```

**requests:** Kubernetes reserves this much
**limits:** Pod can't use more than this

**CPU Units:**
- `1000m` = 1 CPU core
- `500m` = 0.5 CPU core
- `2000m` = 2 CPU cores

---

## Updating Your Application

### Method 1: GitHub Actions → GHCR → K8s

```bash
# After GitHub Actions builds new image:
kubectl set image deployment/gleisplan-api \
  api=ghcr.io/utkarshswain/gleisplanextraktorcompanyfinal:feature-docker-deployment

# K8s does rolling update (zero downtime!)
```

### Method 2: Force Restart

```bash
# If same image tag but new content:
kubectl rollout restart deployment gleisplan-api
```

---

## Differences from Docker

| Docker | Kubernetes |
|--------|------------|
| `docker run` | `kubectl apply` |
| 1 container | Multiple pods (replicas) |
| Manual restart if crash | Auto-restart |
| Manual port binding | Service load balancer |
| `docker logs` | `kubectl logs` |
| `docker exec` | `kubectl exec` |

---

## Troubleshooting

### Pods not starting?

```bash
kubectl describe pod <pod-name>
# Look at "Events" section at bottom
```

Common issues:
- Image pull error: Check GHCR image is public
- CrashLoopBackOff: Check logs with `kubectl logs`
- Pending: Not enough resources

### Can't access service?

```bash
# Check service has endpoints
kubectl get endpoints gleisplan-api-service

# Port forward directly to a pod
kubectl port-forward <pod-name> 8000:8000
```

### Model not found?

The `hostPath` volume might not work on all systems. Alternative:
1. Build model into Docker image
2. Or use Kubernetes PersistentVolume

---

## Next Steps

1. **Try scaling:** `kubectl scale deployment gleisplan-api --replicas=3`
2. **Update the app:** Push new code, let GitHub Actions build, then update K8s
3. **Add monitoring:** Learn about Prometheus + Grafana
4. **Learn more:** https://kubernetes.io/docs/tutorials/

---

## Comparison: Docker vs Kubernetes

### With Docker (what you had):
```bash
docker run -p 8000:8000 myapi
# If it crashes → manually restart
# Only 1 instance
```

### With Kubernetes (what you have now):
```bash
kubectl apply -f k8s/
# If it crashes → auto-restart
# 2 instances running (automatic load balancing)
# Health checks included
# Easy to scale to 10+ instances
```

---

*Created: April 2026*
*For: Kubernetes Learning - Local Development*

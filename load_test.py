"""
Simple load generator to test Kubernetes auto-scaling
Sends many requests to stress the API and trigger HPA
"""

import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor

API_URL = "http://localhost/health"
NUM_WORKERS = 30  # Number of parallel workers (reasonable amount)
DURATION_SECONDS = 120  # Run for 2 minutes

print(f"🚀 Starting load test against {API_URL}")
print(f"Workers: {NUM_WORKERS}")
print(f"Duration: {DURATION_SECONDS} seconds")
print("\nWatch auto-scaling with: kubectl get hpa -w")
print("Watch pods with: kubectl get pods -w\n")

request_count = 0
start_time = time.time()

def send_request(worker_id):
    """Send a single request"""
    global request_count
    try:
        response = requests.get(API_URL, timeout=5)
        request_count += 1
        if request_count % 100 == 0:
            elapsed = time.time() - start_time
            rps = request_count / elapsed
            print(f"✓ {request_count} requests sent ({rps:.1f} req/sec)")
        return response.status_code
    except Exception as e:
        print(f"✗ Request failed: {e}")
        return None

def worker(worker_id):
    """Worker that continuously sends requests"""
    end_time = start_time + DURATION_SECONDS
    while time.time() < end_time:
        send_request(worker_id)
        # No delay - send as fast as possible!

# Start load test
print("📊 Load test starting...\n")

with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
    futures = [executor.submit(worker, i) for i in range(NUM_WORKERS)]

    # Wait for all workers to complete
    for future in futures:
        future.result()

elapsed = time.time() - start_time
print(f"\n✅ Load test complete!")
print(f"Total requests: {request_count}")
print(f"Duration: {elapsed:.1f} seconds")
print(f"Average: {request_count / elapsed:.1f} req/sec")
print("\nCheck final pod count: kubectl get pods")

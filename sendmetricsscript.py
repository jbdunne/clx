import requests
import random
import time
import json
from datetime import datetime
import socket

# === CONFIG ===
PRIVATE_KEY = "keygoeshere"  # Replace with your key
APP_NAME = "k8s-infra-metrics"
SUBSYSTEM_NAME = "production"
METRICS_URL = "https://ng-api-http.cx498.coralogix.com/metrics"  # Metrics endpoint

# === CONSTANTS ===
TARGET_BYTES_PER_DAY = 1.5 * 1024 * 1024  # 1.5 MB/day
ESTIMATED_AVG_METRIC_BYTE_SIZE = 300  # Smaller than logs (metrics are compact)
TARGET_METRICS_PER_DAY = TARGET_BYTES_PER_DAY / ESTIMATED_AVG_METRIC_BYTE_SIZE
SECONDS_PER_DAY = 24 * 60 * 60
AVERAGE_METRICS_PER_BATCH = 10
AVERAGE_WAIT_SECONDS = SECONDS_PER_DAY / (TARGET_METRICS_PER_DAY / AVERAGE_METRICS_PER_BATCH)
MIN_WAIT_SECONDS = 10
SLEEP_JITTER_SECONDS = AVERAGE_WAIT_SECONDS * 0.5
SLEEP_MIN_SECONDS = max(MIN_WAIT_SECONDS, AVERAGE_WAIT_SECONDS - SLEEP_JITTER_SECONDS)
SLEEP_MAX_SECONDS = AVERAGE_WAIT_SECONDS + SLEEP_JITTER_SECONDS

# K8s/Docker Simulation Data
K8S_NAMESPACES = ["default", "kube-system", "monitoring"]
K8S_PODS = ["nginx-123", "redis-456", "app-backend-789"]
NODES = ["node-1", "node-2"]

# === Metric Generators ===
def generate_metrics_payload():
    """Generates a batch of metrics in Coralogix format."""
    timestamp = int(datetime.utcnow().timestamp() * 1000)  # Milliseconds
    metrics = []
    
    for _ in range(random.randint(3, 8)):  # 3-8 metrics per batch
        metric = {
            "name": random.choice(["cpu_usage", "memory_usage", "network_bytes", "disk_io"]),
            "value": round(random.uniform(0.1, 99.9), 2),
            "timestamp": timestamp,
            "labels": {
                "namespace": random.choice(K8S_NAMESPACES),
                "pod": random.choice(K8S_PODS),
                "node": random.choice(NODES),
                "app": APP_NAME,
                "subsystem": SUBSYSTEM_NAME,
            }
        }
        metrics.append(metric)
    
    return {
        "application": APP_NAME,
        "subsystem": SUBSYSTEM_NAME,
        "metrics": metrics
    }

# === Main Sending Loop ===
def main():
    daily_sent_bytes = 0
    start_time = time.time()

    print(f"Starting metrics shipping. Target: {TARGET_BYTES_PER_DAY / 1024 / 1024:.2f} MB/day")
    print(f"Avg wait between batches: {AVERAGE_WAIT_SECONDS:.2f}s")

    while True:
        if time.time() - start_time >= SECONDS_PER_DAY:
            daily_sent_bytes = 0
            start_time = time.time()
            print("\n--- New Day: Reset Daily Byte Count ---")

        payload = generate_metrics_payload()
        
        try:
            batch_size = len(json.dumps(payload).encode('utf-8'))
        except Exception as e:
            print(f"Error calculating batch size: {e}")
            time.sleep(5)
            continue

        if daily_sent_bytes + batch_size > TARGET_BYTES_PER_DAY:
            remaining_time = max(0, SECONDS_PER_DAY - (time.time() - start_time))
            print(f"Approaching daily limit. Waiting {remaining_time:.2f}s.")
            time.sleep(remaining_time + 5)
            daily_sent_bytes = 0
            start_time = time.time()
            continue

        try:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {PRIVATE_KEY}"  # Metrics API often uses Bearer auth
            }
            response = requests.post(METRICS_URL, json=payload, headers=headers)
            print(f"Shipped {len(payload['metrics'])} metrics ({batch_size} bytes). Status: {response.status_code}")
            daily_sent_bytes += batch_size
        except Exception as e:
            print(f"Shipping failed: {e}")

        sleep_time = random.uniform(SLEEP_MIN_SECONDS, SLEEP_MAX_SECONDS)
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()

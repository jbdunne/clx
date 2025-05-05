import requests
import random
import time
import json
from datetime import datetime

# === CONFIG ===
# Coralogix Private Key - Re-inserted the key used in the user's successful curl requests
PRIVATE_KEY = "keygoeshere"
APP_NAME = "demo-app"
SUBSYSTEM_NAME = "demo-subsystem"
# Coralogix Logs Ingestion URL for your region
# This URL worked with the provided key in the user's curl attempts.
URL = "https://ingress.cx498.coralogix.com/api/v1/logs"

# === CONSTANTS ===
# Target data volume per day: 1 MB
TARGET_BYTES_PER_DAY = 1 * 1024 * 1024  # 1 MB in bytes

# Estimated average size of a single log entry payload in bytes
# This is a rough estimate. The actual size will vary.
# We'll calculate the exact batch size before sending.
ESTIMATED_AVG_LOG_BYTE_SIZE = 200

# Based on the target daily volume and estimated log size,
# calculate the approximate number of logs to send per day.
# This helps in determining the average delay needed.
TARGET_LOGS_PER_DAY = TARGET_BYTES_PER_DAY / ESTIMATED_AVG_LOG_BYTE_SIZE

# Total seconds in a day
SECONDS_PER_DAY = 24 * 60 * 60

# Average number of logs to send per batch to maintain some variability
AVERAGE_LOGS_PER_BATCH = (5 + 15) / 2 # Based on the random.randint(5, 15)

# Approximate number of batches per day to hit the target log count
# Ensure we don't divide by zero if TARGET_LOGS_PER_DAY or AVERAGE_LOGS_PER_BATCH are zero
TARGET_BATCHES_PER_DAY = TARGET_LOGS_PER_DAY / AVERAGE_LOGS_PER_BATCH if AVERAGE_LOGS_PER_BATCH > 0 else 0

# Average time to wait between sending batches to hit the target rate
# This is the key value we need to adjust to meet the 1MB/day target.
# We subtract a small buffer for the actual sending time, though it's usually negligible.
MIN_WAIT_SECONDS = 10 # Ensure a minimum wait time to avoid flooding
AVERAGE_WAIT_SECONDS = SECONDS_PER_DAY / TARGET_BATCHES_PER_DAY if TARGET_BATCHES_PER_DAY > 0 else SECONDS_PER_DAY

# Ensure a minimum wait time
AVERAGE_WAIT_SECONDS = max(AVERAGE_WAIT_SECONDS, MIN_WAIT_SECONDS)


# Define the range for random sleep time around the average wait time
# Adjust these values to control the variability and fine-tune the rate.
# The range should be wide enough for visual interest but centered around AVERAGE_WAIT_SECONDS.
SLEEP_JITTER_SECONDS = AVERAGE_WAIT_SECONDS * 0.5 # 50% jitter
SLEEP_MIN_SECONDS = max(MIN_WAIT_SECONDS, AVERAGE_WAIT_SECONDS - SLEEP_JITTER_SECONDS)
SLEEP_MAX_SECONDS = AVERAGE_WAIT_SECONDS + SLEEP_JITTER_SECONDS


# === Simple OTEL-style log generator ===
def generate_log():
    """Generates a single log entry with random data."""
    trace_id = ''.join(random.choices('abcdef0123456789', k=32))
    span_id = ''.join(random.choices('abcdef0123456789', k=16))
    # Severity levels: 1=Debug, 2=Verbose, 3=Info, 4=Warning, 5=Error, 6=Critical
    severity = random.choice([1, 2, 3, 4, 5, 6])
    message = random.choice([
        "processing request",
        "fetching data from upstream service",
        "database query successful",
        "response sent to client",
        "error encountered in processing",
        "retrying failed operation",
        "user login successful",
        "background task completed",
        "cache refresh initiated",
        "configuration reloaded"
    ])
    log = {
        "text": f"{datetime.utcnow().isoformat()}Z {message} trace_id={trace_id} span_id={span_id}",
        "severity": severity,
        # Add other relevant fields for better context in Coralogix
        "resource": {
            "application": APP_NAME,
            "subsystem": SUBSYSTEM_NAME
        },
        "attributes": {
            "trace_id": trace_id,
            "span_id": span_id
        }
    }
    return log

# === Main sending loop ===
def main():
    """Generates and sends logs to Coralogix with a controlled rate."""
    daily_sent_bytes = 0
    start_time = time.time()

    print(f"Starting log generation. Target daily volume: {TARGET_BYTES_PER_DAY / 1024 / 1024:.2f} MB")
    print(f"Average wait time between batches: {AVERAGE_WAIT_SECONDS:.2f} seconds (range: {SLEEP_MIN_SECONDS:.2f} - {SLEEP_MAX_SECONDS:.2f} seconds)")

    while True:
        # Reset daily counter if a day has passed (approximately)
        if time.time() - start_time >= SECONDS_PER_DAY:
            daily_sent_bytes = 0
            start_time = time.time()
            print("\n--- New Day - Daily byte count reset ---")

        # Randomize number of logs per batch (e.g., 5 to 15)
        # Keep this range reasonable to avoid overly large single payloads
        num_logs = random.randint(5, 15)
        logs = [generate_log() for _ in range(num_logs)]

        payload = {
            "privateKey": PRIVATE_KEY,
            "applicationName": APP_NAME,
            "subsystemName": SUBSYSTEM_NAME,
            "logEntries": logs
        }

        # Calculate actual batch size in bytes
        try:
            batch_payload_string = json.dumps(payload)
            batch_size = len(batch_payload_string.encode('utf-8'))
        except Exception as e:
            print(f"Error calculating batch size: {e}. Skipping batch.")
            # Sleep before next attempt to prevent rapid error looping
            time.sleep(min(MIN_WAIT_SECONDS, 5)) # Sleep for a short time on error
            continue


        # Check if sending this batch would exceed the daily target
        if daily_sent_bytes + batch_size > TARGET_BYTES_PER_DAY:
            # Calculate remaining time in the day
            elapsed_time_today = time.time() - start_time
            remaining_time_today = max(0, SECONDS_PER_DAY - elapsed_time_today)

            if remaining_time_today > 0:
                 # If close to the limit, wait until the next day starts or for a longer period
                print(f"Daily byte limit ({TARGET_BYTES_PER_DAY / 1024 / 1024:.2f} MB) approached. Sent {daily_sent_bytes / 1024 / 1024:.2f} MB so far.")
                print(f"Waiting for {remaining_time_today:.2f} seconds until the next day starts.")
                time.sleep(remaining_time_today + 5) # Wait until next day plus a buffer
                daily_sent_bytes = 0 # Reset counter after waiting for the day to pass
                start_time = time.time() # Reset start time
                print("\n--- New Day - Daily byte count reset ---")
                continue # Skip sending this batch and generate a new one for the new day
            else:
                 # If already past the day boundary but still exceeding the limit
                 # (shouldn't happen with the reset logic, but as a safeguard)
                print(f"Daily byte limit ({TARGET_BYTES_PER_DAY / 1024 / 1024:.2f} MB) exceeded. Sent {daily_sent_bytes / 1024 / 1024:.2f} MB.")
                print("Waiting for a significant period before checking again.")
                time.sleep(600) # Wait 10 minutes
                continue


        # Send logs
        try:
            response = requests.post(URL, json=payload, headers={"Content-Type": "application/json"})
            print(f"Sent {num_logs} logs ({batch_size} bytes). Response: {response.status_code}. Total sent today: { (daily_sent_bytes + batch_size) / 1024:.2f} KB")
            daily_sent_bytes += batch_size

            # Check for non-200 responses and print error details
            if response.status_code != 200:
                print(f"Error sending logs. Status Code: {response.status_code}")
                try:
                    print(f"Response Body: {response.json()}")
                except json.JSONDecodeError:
                    print(f"Response Body: {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"Error sending logs: {e}")
        except Exception as e:
            print(f"An unexpected error occurred: {e}")


        # Sleep randomly between sends to spread out the traffic and create variability
        sleep_seconds = random.uniform(SLEEP_MIN_SECONDS, SLEEP_MAX_SECONDS)
        print(f"Sleeping for {sleep_seconds:.2f} seconds...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    main()

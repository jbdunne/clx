import requests
import random
import time
import json
from datetime import datetime, timedelta
import uuid
import socket
import ipaddress

# === CONFIG ===
PRIVATE_KEY = "keygoeshere"
APP_NAME = "aws-cloudtrail"
SUBSYSTEM_NAME = "production"
URL = "https://ingress.cx498.coralogix.com/api/v1/logs"

# === CONSTANTS ===
TARGET_BYTES_PER_DAY = 1.5 * 1024 * 1024  # 1.5 MB in bytes (middle of 1-2MB range)
ESTIMATED_AVG_LOG_BYTE_SIZE = 500  # CloudTrail logs are typically larger than simple logs
TARGET_LOGS_PER_DAY = TARGET_BYTES_PER_DAY / ESTIMATED_AVG_LOG_BYTE_SIZE
SECONDS_PER_DAY = 24 * 60 * 60
AVERAGE_LOGS_PER_BATCH = 10  # Typical CloudTrail events per API call
TARGET_BATCHES_PER_DAY = TARGET_LOGS_PER_DAY / AVERAGE_LOGS_PER_BATCH
AVERAGE_WAIT_SECONDS = SECONDS_PER_DAY / TARGET_BATCHES_PER_DAY
MIN_WAIT_SECONDS = 10
SLEEP_JITTER_SECONDS = AVERAGE_WAIT_SECONDS * 0.5
SLEEP_MIN_SECONDS = max(MIN_WAIT_SECONDS, AVERAGE_WAIT_SECONDS - SLEEP_JITTER_SECONDS)
SLEEP_MAX_SECONDS = AVERAGE_WAIT_SECONDS + SLEEP_JITTER_SECONDS

# AWS Account and User Data
AWS_ACCOUNT_ID = "123456789012"
AWS_REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
AWS_SERVICES = ["ec2", "s3", "iam", "lambda", "rds", "cloudformation", "dynamodb"]
AWS_USERS = [
    "arn:aws:iam::{}:user/admin".format(AWS_ACCOUNT_ID),
    "arn:aws:iam::{}:user/developer".format(AWS_ACCOUNT_ID),
    "arn:aws:iam::{}:user/ci-cd".format(AWS_ACCOUNT_ID),
    "arn:aws:sts::{}:assumed-role/Admin/session".format(AWS_ACCOUNT_ID)
]

# Common CloudTrail event names
EVENT_NAMES = {
    "ec2": ["RunInstances", "StopInstances", "TerminateInstances", "DescribeInstances"],
    "s3": ["CreateBucket", "DeleteBucket", "PutObject", "GetObject"],
    "iam": ["CreateUser", "DeleteUser", "AttachUserPolicy", "ListUsers"],
    "lambda": ["CreateFunction", "InvokeFunction", "DeleteFunction"],
    "rds": ["CreateDBInstance", "DeleteDBInstance", "DescribeDBInstances"],
    "cloudformation": ["CreateStack", "DeleteStack", "UpdateStack"],
    "dynamodb": ["CreateTable", "DeleteTable", "PutItem", "Query"]
}

# Generate some realistic source IPs
def generate_realistic_ip():
    # AWS IP ranges or common corporate/public IPs
    aws_ips = [
        "54.240.197.{}/32".format(random.randint(1, 255)),
        "52.95.{}.{}/32".format(random.randint(0, 255), random.randint(0, 255)),
        "203.0.113.{}/32".format(random.randint(1, 254)),  # TEST-NET-3
        "198.51.100.{}/32".format(random.randint(1, 254))  # TEST-NET-2
    ]
    return random.choice(aws_ips)

# Generate CloudTrail event
def generate_cloudtrail_event():
    event_time = datetime.utcnow().isoformat() + "Z"
    event_id = str(uuid.uuid4())
    aws_region = random.choice(AWS_REGIONS)
    service = random.choice(AWS_SERVICES)
    event_name = random.choice(EVENT_NAMES[service])
    user_arn = random.choice(AWS_USERS)
    user_agent = random.choice([
        "aws-cli/1.29.29 Python/3.9.11 Darwin/22.6.0 botocore/1.31.29",
        "Boto3/1.28.29 Python/3.10.12 Linux/5.15.0-1042-aws botocore/1.31.29",
        "console.amazonaws.com",
        "CloudFormation"
    ])
    source_ip = generate_realistic_ip()
    
    # Event structure based on actual CloudTrail schema
    event = {
        "eventVersion": "1.08",
        "userIdentity": {
            "type": "IAMUser" if "user/" in user_arn else "AssumedRole",
            "principalId": "AIDA" + ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890', k=16)),
            "arn": user_arn,
            "accountId": AWS_ACCOUNT_ID,
            "accessKeyId": "AKIA" + ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890', k=16)),
            "sessionContext": {
                "sessionIssuer": {
                    "type": "Role" if "assumed-role" in user_arn else "IAMUser",
                    "arn": user_arn
                }
            }
        },
        "eventTime": event_time,
        "eventSource": "{}.amazonaws.com".format(service),
        "eventName": event_name,
        "awsRegion": aws_region,
        "sourceIPAddress": source_ip,
        "userAgent": user_agent,
        "requestID": str(uuid.uuid4()),
        "eventID": event_id,
        "readOnly": event_name.startswith(("Describe", "List", "Get")),
        "resources": [],
        "eventType": "AwsApiCall",
        "managementEvent": True,
        "recipientAccountId": AWS_ACCOUNT_ID,
        "eventCategory": "Management",
        "tlsDetails": {
            "tlsVersion": "TLSv1.2",
            "cipherSuite": "ECDHE-RSA-AES128-GCM-SHA256",
            "clientProvidedHostHeader": "{}.{}.amazonaws.com".format(service, aws_region)
        }
    }
    
    # Add some request parameters for certain events
    if service == "ec2" and event_name == "RunInstances":
        event["requestParameters"] = {
            "instancesSet": {
                "items": [
                    {
                        "imageId": "ami-" + ''.join(random.choices('0123456789abcdef', k=8)),
                        "instanceType": random.choice(["t2.micro", "t3.medium", "m5.large"]),
                        "minCount": 1,
                        "maxCount": 1
                    }
                ]
            }
        }
    elif service == "s3" and event_name == "CreateBucket":
        event["requestParameters"] = {
            "bucketName": "my-bucket-" + ''.join(random.choices('0123456789', k=12)),
            "x-amz-acl": "private"
        }
    
    # Add some response elements for successful events
    if random.random() > 0.1:  # 90% success rate
        event["responseElements"] = {"_return": True}
    else:
        event["errorCode"] = random.choice(["AccessDenied", "UnauthorizedOperation", "ThrottlingException"])
        event["errorMessage"] = "User is not authorized to perform this action"
    
    return {
        "text": json.dumps(event),
        "severity": 3,  # Info level for all CloudTrail events
        "resource": {
            "application": APP_NAME,
            "subsystem": SUBSYSTEM_NAME,
            "aws_account": AWS_ACCOUNT_ID,
            "aws_region": aws_region
        },
        "attributes": {
            "event_id": event_id,
            "event_name": event_name,
            "event_source": event["eventSource"],
            "user_arn": user_arn
        }
    }

# === Main sending loop ===
def main():
    """Generates and sends CloudTrail logs to Coralogix with a controlled rate."""
    daily_sent_bytes = 0
    start_time = time.time()

    print(f"Starting CloudTrail log generation. Target daily volume: {TARGET_BYTES_PER_DAY / 1024 / 1024:.2f} MB")
    print(f"Average wait time between batches: {AVERAGE_WAIT_SECONDS:.2f} seconds (range: {SLEEP_MIN_SECONDS:.2f} - {SLEEP_MAX_SECONDS:.2f} seconds)")

    while True:
        # Reset daily counter if a day has passed
        if time.time() - start_time >= SECONDS_PER_DAY:
            daily_sent_bytes = 0
            start_time = time.time()
            print("\n--- New Day - Daily byte count reset ---")

        # Randomize number of logs per batch (3-15 events)
        num_logs = random.randint(3, 15)
        logs = [generate_cloudtrail_event() for _ in range(num_logs)]

        payload = {
            "privateKey": PRIVATE_KEY,
            "applicationName": APP_NAME,
            "subsystemName": SUBSYSTEM_NAME,
            "logEntries": logs
        }

        # Calculate actual batch size
        try:
            batch_payload_string = json.dumps(payload)
            batch_size = len(batch_payload_string.encode('utf-8'))
        except Exception as e:
            print(f"Error calculating batch size: {e}. Skipping batch.")
            time.sleep(min(MIN_WAIT_SECONDS, 5))
            continue

        # Check daily limit
        if daily_sent_bytes + batch_size > TARGET_BYTES_PER_DAY:
            elapsed_time_today = time.time() - start_time
            remaining_time_today = max(0, SECONDS_PER_DAY - elapsed_time_today)
            
            if remaining_time_today > 0:
                print(f"Daily byte limit approached. Sent {daily_sent_bytes / 1024 / 1024:.2f} MB so far.")
                print(f"Waiting for {remaining_time_today:.2f} seconds until the next day starts.")
                time.sleep(remaining_time_today + 5)
                daily_sent_bytes = 0
                start_time = time.time()
                print("\n--- New Day - Daily byte count reset ---")
                continue
            else:
                print(f"Daily byte limit exceeded. Sent {daily_sent_bytes / 1024 / 1024:.2f} MB.")
                time.sleep(600)
                continue

        # Send logs
        try:
            response = requests.post(URL, json=payload, headers={"Content-Type": "application/json"})
            print(f"Sent {num_logs} CloudTrail events ({batch_size} bytes). Response: {response.status_code}. Total sent today: { (daily_sent_bytes + batch_size) / 1024:.2f} KB")
            daily_sent_bytes += batch_size

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

        # Sleep with variability
        sleep_seconds = random.uniform(SLEEP_MIN_SECONDS, SLEEP_MAX_SECONDS)
        
        # Add some burstiness - occasionally sleep shorter or longer
        if random.random() < 0.1:  # 10% chance
            sleep_seconds *= random.uniform(0.2, 3.0)
        
        print(f"Sleeping for {sleep_seconds:.2f} seconds...")
        time.sleep(sleep_seconds)

if __name__ == "__main__":
    main()

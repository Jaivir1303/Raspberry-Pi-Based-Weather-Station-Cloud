import os
from influxdb_client import InfluxDBClient
from datetime import datetime

# InfluxDB Cloud connection details using the new environment variable and URL
token = os.getenv("INFLUXDB_TOKENCLOUD")
org = "BTP Project"
bucket = "Weather Data"
url = "https://eu-central-1-1.aws.cloud2.influxdata.com"

client = InfluxDBClient(url=url, token=token, org=org)
delete_api = client.delete_api()

# Define the time range: delete from the beginning up to 2026-01-01T00:00:00Z
start = "1970-01-01T00:00:00Z"
stop = "2026-01-01T00:00:00Z"

# Predicate to target the "environment" measurement. If you wish to delete all data, you can leave the predicate empty.
predicate = '_measurement="environment"'

print(f"Deleting data from {start} to {stop} with predicate: {predicate}")
delete_api.delete(start, stop, predicate, bucket=bucket, org=org)
print("Deletion completed.")

client.close()


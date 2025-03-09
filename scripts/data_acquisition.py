import asyncio
import websockets
import json
import time
import os
import statistics
from datetime import datetime
import pytz
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ---------------------------
# Configuration & InfluxDB Cloud Setup
# ---------------------------
AGGREGATION_INTERVAL = 30  # seconds for faster updates

# Sensor-specific anomaly thresholds (z-score thresholds)
THRESHOLDS = {
    "temperature": 2.0,    # Small changes are meaningful
    "humidity": 2.5,       # Medium sensitivity
    "pressure": 1.8,       # Very stable sensor, stricter threshold
    "AQI": 3.5,            # Air quality (gas resistance) fluctuates, needs higher threshold
    "uv_data": 3.5,        # Adjusted to prevent false positives
    "ambient_light": 3.0   # Large variations due to day-night cycle
}

# InfluxDB Cloud connection details using the new environment variable and URL
token = os.getenv("INFLUXDB_TOKENCLOUD")
org = "BTP Project"
bucket = "Weather Data"
url = "https://eu-central-1-1.aws.cloud2.influxdata.com"

client = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

# WebSocket URL (remains unchanged)
WEBSOCKET_URL = "ws://localhost:6789"

# ---------------------------
# Global storage for historical aggregated averages (for anomaly detection)
# ---------------------------
historical_data = {
    "temperature": [],
    "humidity": [],
    "pressure": [],
    "AQI": [],
    "uv_data": [],
    "ambient_light": []
}

# ---------------------------
# Aggregation Function
# ---------------------------
def aggregate_buffer(buffer):
    """
    Compute aggregated average, minimum, and maximum for each sensor from the buffer.
    """
    aggregated = {}
    sensors = ["temperature", "humidity", "pressure", "AQI", "uv_data", "ambient_light"]
    for sensor in sensors:
        values = [item[sensor] for item in buffer if sensor in item]
        if values:
            aggregated[f"{sensor}_avg"] = sum(values) / len(values)
            aggregated[f"{sensor}_min"] = min(values)
            aggregated[f"{sensor}_max"] = max(values)
        else:
            aggregated[f"{sensor}_avg"] = None
            aggregated[f"{sensor}_min"] = None
            aggregated[f"{sensor}_max"] = None
    # Set aggregated timestamp as current local time (keep it as a datetime object)
    local_tz = pytz.timezone("Asia/Kolkata")
    aggregated["timestamp"] = datetime.now(local_tz)
    return aggregated

# ---------------------------
# Anomaly Detection Function (Z-Score Method)
# ---------------------------
def detect_anomalies(aggregated):
    """
    Uses historical aggregated averages to compute a z-score for each sensor.
    Flags the sensor as anomalous if its z-score exceeds its specific threshold.
    """
    anomalies = {}
    sensors = ["temperature", "humidity", "pressure", "AQI", "uv_data", "ambient_light"]
    for sensor in sensors:
        current_value = aggregated.get(f"{sensor}_avg")
        history = historical_data[sensor]
        if history and len(history) >= 2:
            hist_mean = sum(history) / len(history)
            hist_std = statistics.stdev(history) if len(history) > 1 else 0.0001
            z_score = (current_value - hist_mean) / hist_std if hist_std != 0 else 0
            threshold = THRESHOLDS.get(sensor, 2.0)  # default to 2.0 if not specified
            anomalies[f"{sensor}_anomaly"] = abs(z_score) > threshold
        else:
            anomalies[f"{sensor}_anomaly"] = False  # Not enough history to decide
    return anomalies

# ---------------------------
# Main Data Acquisition & Processing Loop
# ---------------------------
async def fetch_and_process_data():
    buffer = []
    start_time = time.time()
    try:
        async with websockets.connect(WEBSOCKET_URL) as websocket:
            while True:
                message = await websocket.recv()
                data = json.loads(message)
                # Ensure timestamp is present for each raw reading
                data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                buffer.append(data)
                
                # Process the buffered data when aggregation interval has passed
                if time.time() - start_time >= AGGREGATION_INTERVAL:
                    aggregated = aggregate_buffer(buffer)
                    anomalies = detect_anomalies(aggregated)
                    # Combine aggregated data with anomaly flags
                    aggregated_record = {**aggregated, **anomalies}
                    
                    # Update historical data with the current batch's averages
                    for sensor in historical_data.keys():
                        aggregated_value = aggregated.get(f"{sensor}_avg")
                        if aggregated_value is not None:
                            historical_data[sensor].append(aggregated_value)
                            # Limit history length to the last 10 batches
                            if len(historical_data[sensor]) > 10:
                                historical_data[sensor].pop(0)
                    
                    # Prepare the InfluxDB point with aggregated values and anomaly flags
                    point = Point("environment") \
                        .tag("location", "office") \
                        .field("temperature_avg", aggregated_record.get("temperature_avg", 0)) \
                        .field("temperature_min", aggregated_record.get("temperature_min", 0)) \
                        .field("temperature_max", aggregated_record.get("temperature_max", 0)) \
                        .field("humidity_avg", aggregated_record.get("humidity_avg", 0)) \
                        .field("humidity_min", aggregated_record.get("humidity_min", 0)) \
                        .field("humidity_max", aggregated_record.get("humidity_max", 0)) \
                        .field("pressure_avg", aggregated_record.get("pressure_avg", 0)) \
                        .field("pressure_min", aggregated_record.get("pressure_min", 0)) \
                        .field("pressure_max", aggregated_record.get("pressure_max", 0)) \
                        .field("AQI_avg", aggregated_record.get("AQI_avg", 0)) \
                        .field("AQI_min", aggregated_record.get("AQI_min", 0)) \
                        .field("AQI_max", aggregated_record.get("AQI_max", 0)) \
                        .field("uv_data_avg", aggregated_record.get("uv_data_avg", 0)) \
                        .field("uv_data_min", aggregated_record.get("uv_data_min", 0)) \
                        .field("uv_data_max", aggregated_record.get("uv_data_max", 0)) \
                        .field("ambient_light_avg", aggregated_record.get("ambient_light_avg", 0)) \
                        .field("ambient_light_min", aggregated_record.get("ambient_light_min", 0)) \
                        .field("ambient_light_max", aggregated_record.get("ambient_light_max", 0)) \
                        .field("temperature_anomaly", int(aggregated_record.get("temperature_anomaly"))) \
                        .field("humidity_anomaly", int(aggregated_record.get("humidity_anomaly"))) \
                        .field("pressure_anomaly", int(aggregated_record.get("pressure_anomaly"))) \
                        .field("AQI_anomaly", int(aggregated_record.get("AQI_anomaly"))) \
                        .field("uv_data_anomaly", int(aggregated_record.get("uv_data_anomaly"))) \
                        .field("ambient_light_anomaly", int(aggregated_record.get("ambient_light_anomaly"))) \
                        .time(aggregated_record["timestamp"])
                    
                    # Write the aggregated record to InfluxDB Cloud
                    write_api.write(bucket=bucket, org=org, record=point)
                    
                    # Clear the buffer and reset the timer for the next aggregation cycle
                    buffer.clear()
                    start_time = time.time()
                
                # Yield control briefly
                await asyncio.sleep(0.1)
    except Exception as e:
        print(f"Error in data processing: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(fetch_and_process_data())


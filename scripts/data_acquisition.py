import asyncio
import websockets
import json
import time
import os
from datetime import datetime, timedelta
import pytz
from collections import deque
import statistics
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# ---------------------------
# Configuration & InfluxDB Cloud Setup
# ---------------------------
AGGREGATION_INTERVAL = 30  # seconds per batch

# Pure‑delta thresholds (per 30 s batch)
DELTA_THRESH = {
    'temperature': 0.15,  # °C
    'humidity':    0.85,  # %
    'pressure':    0.18   # hPa
}

# UV‑based “Sunlight Exposure” settings
UV_SMOOTH_WINDOW    = 21          # rolling median window (~10.5 min)
UV_ON_THRESHOLD     = 0.85        # uv_data_avg units
UV_MIN_ON_MINS      = 20          # require ≥20 min
UV_MIN_ON_SAMPLES   = int((UV_MIN_ON_MINS * 60) / AGGREGATION_INTERVAL)
UV_DELTA_THRESH     = 2.0         # raw UV jump per batch

# Ambient‑light “On/Off” settings
LIGHT_CUTOFF        = 20.0        # lux
LIGHT_DELTA_THRESH  = 15.0        # lux jump per batch

# InfluxDB Cloud connection
token    = os.getenv("INFLUXDB_TOKENCLOUD")
org      = "BTP Project"
bucket   = "Weather Data"
url      = "https://eu-central-1-1.aws.cloud2.influxdata.com"
client   = InfluxDBClient(url=url, token=token, org=org)
write_api = client.write_api(write_options=SYNCHRONOUS)

WEBSOCKET_URL = "ws://localhost:6789"

# ---------------------------
# Streaming State
# ---------------------------
prev_avg = {
    'temperature':   None,
    'humidity':      None,
    'pressure':      None,
    'uv_data':       None,
    'ambient_light': None
}
uv_deque         = deque(maxlen=UV_SMOOTH_WINDOW)
uv_run_len       = 0
last_light_on_ts  = None
last_light_off_ts = None
MIN_EVENT_SPACING = AGGREGATION_INTERVAL  # seconds
ambient_prev_on   = False

# ---------------------------
# Aggregation Helper
# ---------------------------
def aggregate_buffer(buffer):
    """
    Compute avg/min/max for each sensor over buffered interval.
    """
    agg = {}
    sensors = ["temperature","humidity","pressure","AQI","uv_data","ambient_light"]
    for s in sensors:
        vals = [item[s] for item in buffer if s in item]
        if vals:
            agg[f"{s}_avg"] = sum(vals)/len(vals)
            agg[f"{s}_min"] = min(vals)
            agg[f"{s}_max"] = max(vals)
        else:
            agg[f"{s}_avg"] = 0
            agg[f"{s}_min"] = 0
            agg[f"{s}_max"] = 0

    # timestamp in IST
    tz = pytz.timezone("Asia/Kolkata")
    agg["timestamp"] = datetime.now(tz)
    return agg

# ---------------------------
# Main Loop
# ---------------------------
async def fetch_and_process_data():
    global uv_run_len, ambient_prev_on, last_light_on_ts, last_light_off_ts
    buffer   = []
    start_ts = time.time()

    try:
        async with websockets.connect(WEBSOCKET_URL) as ws:
            while True:
                raw = await ws.recv()
                data = json.loads(raw)
                data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                buffer.append(data)

                # time to aggregate?
                if time.time() - start_ts >= AGGREGATION_INTERVAL:
                    agg = aggregate_buffer(buffer)
                    now_ts = agg["timestamp"]

                    # pull averages
                    t_avg  = agg["temperature_avg"]
                    h_avg  = agg["humidity_avg"]
                    p_avg  = agg["pressure_avg"]
                    uv_avg = agg["uv_data_avg"]
                    lt_avg = agg["ambient_light_avg"]

                    # 1) Pure‑delta anomalies for T/H/P
                    temp_anom = hum_anom = pres_anom = False
                    if prev_avg['temperature'] is not None:
                        if abs(t_avg - prev_avg['temperature']) > DELTA_THRESH['temperature']:
                            temp_anom = True
                        if abs(h_avg - prev_avg['humidity']) > DELTA_THRESH['humidity']:
                            hum_anom = True
                        if abs(p_avg - prev_avg['pressure']) > DELTA_THRESH['pressure']:
                            pres_anom = True

                    # compute UV/light delta
                    uv_delta    = uv_avg - prev_avg['uv_data']       if prev_avg['uv_data']       is not None else 0
                    light_delta = lt_avg - prev_avg['ambient_light'] if prev_avg['ambient_light'] is not None else 0

                    # update prev_avg
                    prev_avg['temperature']   = t_avg
                    prev_avg['humidity']      = h_avg
                    prev_avg['pressure']      = p_avg
                    prev_avg['uv_data']       = uv_avg
                    prev_avg['ambient_light'] = lt_avg

                    # 2) Sunlight Exposure (UV) event
                    uv_deque.append(uv_avg)
                    uv_smooth = statistics.median(uv_deque)
                    if uv_smooth >= UV_ON_THRESHOLD:
                        uv_run_len += 1
                    else:
                        uv_run_len = 0
                    sustained_uv = (uv_run_len == UV_MIN_ON_SAMPLES)
                    delta_uv     = (uv_delta >= UV_DELTA_THRESH)
                    uv_event     = int(sustained_uv or delta_uv)

                    # 3) Ambient Light On/Off events
                    on_mask    = lt_avg >= LIGHT_CUTOFF
                    rise_edge  = on_mask and not ambient_prev_on
                    delta_on   = (light_delta >= LIGHT_DELTA_THRESH)
                    raw_on     = rise_edge or delta_on
                    raw_off    = ((not on_mask) and ambient_prev_on) or (light_delta <= -LIGHT_DELTA_THRESH)

                    light_on_event = 0
                    if raw_on and (
                        last_light_on_ts is None or
                        (now_ts - last_light_on_ts).total_seconds() >= MIN_EVENT_SPACING
                    ):
                        light_on_event  = 1
                        last_light_on_ts = now_ts

                    light_off_event = 0
                    if raw_off and (
                        last_light_off_ts is None or
                        (now_ts - last_light_off_ts).total_seconds() >= MIN_EVENT_SPACING
                    ):
                        light_off_event  = 1
                        last_light_off_ts = now_ts

                    ambient_prev_on = on_mask

                    # 4) Build & write InfluxDB point
                    pt = Point("environment").tag("location","office")
                    # agg fields
                    pt.field("temperature_avg", t_avg).field("temperature_min", agg["temperature_min"]).field("temperature_max", agg["temperature_max"])
                    pt.field("humidity_avg",    h_avg).field("humidity_min",    agg["humidity_min"]).field("humidity_max",    agg["humidity_max"])
                    pt.field("pressure_avg",    p_avg).field("pressure_min",    agg["pressure_min"]).field("pressure_max",    agg["pressure_max"])
                    # raw IAQ
                    pt.field("AQI_avg",         agg["AQI_avg"]).field("AQI_min",         agg["AQI_min"]).field("AQI_max",         agg["AQI_max"])
                    # UV/light raw
                    pt.field("uv_data_avg",     uv_avg).field("uv_data_min",     agg["uv_data_min"]).field("uv_data_max",     agg["uv_data_max"])
                    pt.field("ambient_light_avg", lt_avg).field("ambient_light_min", agg["ambient_light_min"]).field("ambient_light_max", agg["ambient_light_max"])
                    # anomaly/events
                    pt.field("temperature_anomaly", int(temp_anom)).field("humidity_anomaly", int(hum_anom)).field("pressure_anomaly", int(pres_anom))
                    pt.field("sunlight_exposure",   uv_event).field("light_on_event",    light_on_event).field("light_off_event",   light_off_event)
                    pt.time(agg["timestamp"])
                    write_api.write(bucket=bucket, org=org, record=pt)

                    # reset
                    buffer.clear()
                    start_ts = time.time()

                await asyncio.sleep(0.1)

    except Exception as e:
        print(f"Error in data processing: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(fetch_and_process_data())

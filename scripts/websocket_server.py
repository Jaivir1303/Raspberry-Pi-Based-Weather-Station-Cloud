import asyncio
import websockets
import json
import time
import board
import busio
import adafruit_bme680
import adafruit_bh1750
import sys
import os

# Add the parent directory to sys.path to import from drivers
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from drivers.DFRobot_LTR390UV import DFRobot_LTR390UV_I2C
from drivers.ltr390_constants import *  # Import all constants

# Initialize I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

# Initialize BME680 (address 0x77) for temperature, humidity, pressure, AQI
bme680 = adafruit_bme680.Adafruit_BME680_I2C(i2c, address=0x77)

# Initialize LTR390 for UV sensing (address 0x1C)
ltr390 = DFRobot_LTR390UV_I2C(1, 0x1C)

# Begin sensor operation and check if initialization is successful
if not ltr390.begin():
    print("Failed to initialize LTR390UV sensor")
else:
    print("LTR390UV sensor initialized successfully")

# Set the sensor to UVS mode (for UV detection)
ltr390.set_mode(0x0A)  # UVS mode as per the library

# Set measurement rate and gain for UV sensor
ltr390.set_ALS_or_UVS_meas_rate(e18bit, e100ms)  # 18-bit resolution and 100ms sampling
ltr390.set_ALS_or_UVS_gain(eGain3)  # Set gain to 3 (default)

# Initialize BH1750 for ambient light sensing (address 0x23)
bh1750 = adafruit_bh1750.BH1750(i2c, address=0x23)

# Function to gather sensor data
def get_sensor_data():
    # BME680 sensor readings
    temperature = bme680.temperature
    humidity = bme680.humidity
    pressure = bme680.pressure
    gas = bme680.gas  # Air Quality Index (AQI)

    # LTR390 sensor readings (UVS Data)
    uvs_data = ltr390.read_original_data()

    # BH1750 sensor readings (ambient light in lux)
    ambient_light = bh1750.lux

    # Prepare the data in JSON format
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "temperature": temperature,
        "humidity": humidity,
        "pressure": pressure,
        "AQI": gas,
        "uv_data": uvs_data,
        "ambient_light": ambient_light  # Include ambient light data
    }
    return json.dumps(data)

# WebSocket handler
async def sensor_data(websocket, path):
    while True:
        data = get_sensor_data()
        await websocket.send(data)
        await asyncio.sleep(1)  # Send data every second

# Start the WebSocket server on localhost:6789
start_server = websockets.serve(sensor_data, "localhost", 6789)

asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()

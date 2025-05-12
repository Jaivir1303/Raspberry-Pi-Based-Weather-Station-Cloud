import streamlit as st
import pandas as pd
import numpy as np
from influxdb_client import InfluxDBClient
import pytz
import os
import random
import pickle           # ← NEW
import pathlib          # ← NEW
from datetime import timedelta   # ← NEW

# utils/data_processing_influx.py  – replace load_arima_models()
@st.cache_resource
def load_arima_models():
    """
    Load the three pretrained ARIMA models saved with joblib.dump().
    """
    import joblib
    base_dir = pathlib.Path(__file__).resolve().parent.parent / "drivers" / "models"
    models, missing = {}, []

    for key, fname in [
        ("temperature", "temperature_arima_model.pkl"),
        ("humidity",    "humidity_arima_model.pkl"),
        ("pressure",    "pressure_arima_model.pkl"),
    ]:
        fpath = base_dir / fname
        try:
            models[key] = joblib.load(fpath)
        except Exception as e:
            st.warning(f"Could not load {fname}: {e}")
            models[key] = None
            missing.append(key)

    if missing:
        st.info(f"Models missing/unreadable: {', '.join(missing)}")

    return models

def get_arima_model(sensor_key: str):
    """Return the cached ARIMA model (or None) for a given sensor key."""
    if "arima_models" not in st.session_state:
        st.session_state["arima_models"] = load_arima_models()
    return st.session_state["arima_models"].get(sensor_key)


# ────────────────────────────────────────────────────────────────
# Helper: fetch recent raw data for forecasting  (fixed tz handling)
# ────────────────────────────────────────────────────────────────
def fetch_recent_for_forecast(client, hours: int = 6) -> pd.DataFrame:
    query_api = client.query_api()
    flux = f'''
      from(bucket:"Weather Data")
        |> range(start: -{hours}h)
        |> filter(fn:(r)=> r._measurement=="environment")
        |> filter(fn:(r)=> r._field =~ /temperature_avg|humidity_avg|pressure_avg/)
        |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
        |> sort(columns:["_time"])
    '''
    df = query_api.query_data_frame(flux)
    if df.empty:
        return df
    if isinstance(df.columns[0], str) and df.columns[0].startswith("table"):
        df = df.drop(columns=[df.columns[0]])
    df = df.rename(columns={"_time": "Timestamp"})

    # --- FIXED LINE -----------------------------------------------------
    df["Timestamp"] = (
        pd.to_datetime(df["Timestamp"], utc=True)   # ensure/retain UTC
          .dt.tz_convert("Asia/Kolkata")            # convert to IST
    )
    # --------------------------------------------------------------------

    return df.reset_index(drop=True)


# ────────────────────────────────────────────────────────────────
# ★ NEW ―― forecast generator (uses recent data fetched above)
# ────────────────────────────────────────────────────────────────
def _future_ts(last_ts: pd.Timestamp, n_steps: int, step_sec: int = 30):
    return [last_ts + timedelta(seconds=step_sec * (i + 1)) for i in range(n_steps)]


def generate_forecast(df_recent: pd.DataFrame,
                      horizon_steps: int = 30,
                      step_sec: int = 30) -> pd.DataFrame | None:
    if df_recent.empty:
        return None

    forecasts = {}
    for key, col in [("temperature", "temperature_avg"),
                     ("humidity",    "humidity_avg"),
                     ("pressure",    "pressure_avg")]:
        model = get_arima_model(key)
        if model is None:
            forecasts[f"{key}_fc"] = [np.nan] * horizon_steps
            continue
        try:
            vals = model.forecast(steps=horizon_steps).tolist()

            # bias-correction so first forecast joins last observation
            anchor = df_recent[col].iloc[-1]
            offset = anchor - vals[0]
            vals   = [v + offset for v in vals]

            forecasts[f"{key}_fc"] = vals
        except Exception as e:
            st.warning(f"Forecast error ({key}): {e}")
            forecasts[f"{key}_fc"] = [np.nan] * horizon_steps

    fc_df = pd.DataFrame({
        "Timestamp": [
            df_recent["Timestamp"].iloc[-1] + timedelta(seconds=step_sec * (i + 1))
            for i in range(horizon_steps)
        ]
    })
    for col, vals in forecasts.items():
        fc_df[col] = vals
    return fc_df


# ────────────────────────────────────────────────────────────────
# (Everything below is 100 % identical to your provided file,
#  except for a longer HTTP timeout in get_influxdb_client)
# ────────────────────────────────────────────────────────────────

# ---------------------------
# IAQ Generator Class
# ---------------------------
class IAQGenerator:
    def __init__(self, min_iaq=110, max_iaq=170, delta=2, initial_iaq=140):
        self.min_iaq = min_iaq
        self.max_iaq = max_iaq
        self.delta = delta
        self.current_iaq = initial_iaq

    def get_next_iaq(self):
        change = random.uniform(-self.delta, self.delta)
        new_iaq = self.current_iaq + change
        new_iaq = max(self.min_iaq, min(new_iaq, self.max_iaq))
        new_iaq = round(new_iaq, 2)
        self.current_iaq = new_iaq
        return new_iaq

# ---------------------------
# Function to Get InfluxDB Client
# ---------------------------
@st.cache_resource
def get_influxdb_client():
    token = os.getenv('INFLUXDB_TOKENCLOUD')
    org = "BTP Project"
    url = "https://eu-central-1-1.aws.cloud2.influxdata.com"
    # 60-second timeout, gzip on — safe but doesn’t change data
    client = InfluxDBClient(url=url, token=token, org=org,
                            timeout=60_000, enable_gzip=True)
    return client

# ---------------------------
# Function to Update DataFrame from InfluxDB  (UNCHANGED)
# ---------------------------
def update_df_from_db(client):
    if 'last_fetch_time' not in st.session_state or st.session_state['last_fetch_time'] is None:
        st.session_state['last_fetch_time'] = pd.Timestamp('1970-01-01T00:00:00Z')

    query_api = client.query_api()
    local_tz = pytz.timezone('Asia/Kolkata')
    query = f'''
    from(bucket: "Weather Data")
      |> range(start: {st.session_state['last_fetch_time'].isoformat()})
      |> filter(fn: (r) => r._measurement == "environment")
      |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
      |> sort(columns: ["_time"])
    '''
    df_new = query_api.query_data_frame(query)
    if not df_new.empty:
        if isinstance(df_new.columns[0], str) and df_new.columns[0].startswith('table'):
            df_new = df_new.drop(columns=[df_new.columns[0]])
        df_new = df_new.rename(columns={'_time': 'Timestamp'})
        df_new['Timestamp'] = pd.to_datetime(df_new['Timestamp']).dt.tz_convert(local_tz)
        if 'df' not in st.session_state or st.session_state.df.empty:
            st.session_state.df = df_new
        else:
            st.session_state.df = pd.concat([st.session_state.df, df_new]).drop_duplicates().reset_index(drop=True)
        st.session_state['last_fetch_time'] = df_new['Timestamp'].max()
        st.session_state['data_fetched'] = True

# ---------------------------
# Function to Get Old Data
# ---------------------------
def get_old_data(df, minutes=30):
    if df.empty:
        return None
    time_diff = pd.Timedelta(minutes=minutes)
    old_timestamp = df['Timestamp'].iloc[-1] - time_diff
    old_data = df[df['Timestamp'] <= old_timestamp]
    return old_data.iloc[-1] if not old_data.empty else None

# ---------------------------
# Descriptive Functions  (UNCHANGED)
# ---------------------------
def calculate_uv_index(uv_raw):
    return uv_raw / 100

def temperature_description(temp):
    if temp >= 30:
        return "Hot 🔥"
    elif temp >= 20:
        return "Warm 🌤️"
    elif temp >= 10:
        return "Cool 🌥️"
    else:
        return "Cold ❄️"

def humidity_description(humidity):
    if humidity >= 70:
        return "High Humidity 💦"
    elif humidity >= 40:
        return "Comfortable 😊"
    else:
        return "Dry 🍃"

def aqi_description(aqi):
    if aqi >= 301:
        return "Hazardous ☠️"
    elif aqi >= 201:
        return "Very Unhealthy 😷"
    elif aqi >= 151:
        return "Unhealthy 🙁"
    elif aqi >= 101:
        return "Unhealthy for Sensitive Groups 😕"
    elif aqi >= 51:
        return "Moderate 😐"
    else:
        return "Good 😊"

def uv_description(uv_index):
    if uv_index >= 11:
        return "Extreme ⚠️"
    elif uv_index >= 8:
        return "Very High 🛑"
    elif uv_index >= 6:
        return "High 🔆"
    elif uv_index >= 3:
        return "Moderate 🌞"
    else:
        return "Low 🌙"

def ambient_light_description(lux):
    if lux >= 10000:
        return "Bright Sunlight ☀️"
    elif lux >= 1000:
        return "Daylight 🌤️"
    elif lux >= 500:
        return "Overcast ☁️"
    elif lux >= 100:
        return "Indoor Lighting 💡"
    else:
        return "Dim Light 🌙"

def pressure_description(pressure):
    if pressure >= 1020:
        return "High Pressure 🌞"
    elif pressure >= 1000:
        return "Normal Pressure 🌤️"
    else:
        return "Low Pressure 🌧️"

def calculate_dew_point(temp, humidity):
    a = 17.27
    b = 237.7
    alpha = ((a * temp) / (b + temp)) + np.log(humidity / 100.0)
    return (b * alpha) / (a - alpha)

def dew_point_description(dew_point):
    if dew_point >= 24:
        return "Severely Uncomfortable 🥵"
    elif dew_point >= 20:
        return "Uncomfortable 😓"
    elif dew_point >= 16:
        return "Somewhat Comfortable 🙂"
    elif dew_point >= 10:
        return "Comfortable 😊"
    else:
        return "Dry 🍃"

def calculate_heat_index(temp, humidity):
    temp_f = temp * 9/5 + 32
    hi = 0.5 * (temp_f + 61.0 + ((temp_f - 68.0) * 1.2) + (humidity * 0.094))
    if hi >= 80:
        hi = (-42.379 + 2.04901523 * temp_f + 10.14333127 * humidity
              - 0.22475541 * temp_f * humidity - 0.00683783 * temp_f**2
              - 0.05481717 * humidity**2 + 0.00122874 * temp_f**2 * humidity
              + 0.00085282 * temp_f * humidity**2 - 0.00000199 * temp_f**2 * humidity**2)
        if (humidity < 13) and (80 <= temp_f <= 112):
            adj = ((13 - humidity) / 4) * np.sqrt((17 - abs(temp_f - 95.)) / 17)
            hi -= adj
        elif (humidity > 85) and (80 <= temp_f <= 87):
            adj = ((humidity - 85) / 10) * ((87 - temp_f) / 5)
            hi += adj
    return (hi - 32) * 5/9

def heat_index_description(heat_index):
    if heat_index >= 54:
        return "Extreme Danger ☠️"
    elif heat_index >= 41:
        return "Danger 🔥"
    elif heat_index >= 32:
        return "Extreme Caution 😓"
    elif heat_index >= 27:
        return "Caution 😐"
    else:
        return "Comfortable 😊"

# ---------------------------
# IAQ Functions  (UNCHANGED)
# ---------------------------
@st.cache_resource
def get_iaq_generator():
    return IAQGenerator()

def calculate_iaq(r_gas, humidity):
    if 'iaq_generator' not in st.session_state:
        st.session_state.iaq_generator = get_iaq_generator()
    if 'last_gas_resistance' not in st.session_state:
        st.session_state.last_gas_resistance = None
    if 'last_iaq' not in st.session_state:
        st.session_state.last_iaq = 140
    if r_gas != st.session_state.last_gas_resistance:
        iaq = st.session_state.iaq_generator.get_next_iaq()
        st.session_state.last_iaq = iaq
        st.session_state.last_gas_resistance = r_gas
    else:
        iaq = st.session_state.last_iaq
    return iaq

def update_iaq_values(df):
    if 'iaq_values' not in st.session_state:
        st.session_state.iaq_values = []
    n_existing = len(st.session_state.iaq_values)
    for i in range(n_existing, len(df)):
        r_gas = df.loc[i, 'gas_resistance']
        humidity = df.loc[i, 'humidity']
        iaq = calculate_iaq(r_gas, humidity)
        st.session_state.iaq_values.append(iaq)

# ---------------------------
# Event Counting Helper (UNCHANGED)
# ---------------------------
def count_events(df, col_name, minutes=30):
    if df.empty or col_name not in df.columns:
        return 0
    time_threshold = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    recent = df[df['Timestamp'] >= time_threshold]
    return int(recent[col_name].sum())

# ---------------------------
# Theme CSS Function (Extended with anomaly & event styling)
# ---------------------------
def get_theme_css(theme):
    """
    Returns CSS styles based on the selected theme, including
    styled checkbox toggles as button‐like controls.
    """
    if theme == "Light":
        background_color = "#FFFFFF"
        text_color = "#000000"
        title_color = "#000000"
        container_background_color = "#F0F0F0"
        metric_label_color = "#555555"
        metric_value_color = "#000000"
        metric_delta_positive_color = "#008000"
        metric_delta_negative_color = "#FF0000"
        metric_delta_neutral_color = "#000000"
        metric_description_color = "#333333"
        sidebar_background_color = "#F8F8F8"
        sidebar_text_color = "#000000"
        sidebar_link_color = "#0000EE"
        selectbox_background_color = "#FFFFFF"
        selectbox_text_color = "#000000"
        button_background_color = "#FFFFFF"
        button_text_color = "#000000"
        button_border_color = "#000000"
    else:
        background_color = "#0E1117"
        text_color = "#FFFFFF"
        title_color = "#FFFFFF"
        container_background_color = "#1E1E1E"
        metric_label_color = "#AAAAAA"
        metric_value_color = "#FFFFFF"
        metric_delta_positive_color = "#00FF00"
        metric_delta_negative_color = "#FF4500"
        metric_delta_neutral_color = "#FFFFFF"
        metric_description_color = "#DDDDDD"
        sidebar_background_color = "#1E1E1E"
        sidebar_text_color = "#FFFFFF"
        sidebar_link_color = "#1E90FF"
        selectbox_background_color = "#1E1E1E"
        selectbox_text_color = "#FFFFFF"
        button_background_color = "#1E1E1E"
        button_text_color = "#FFFFFF"
        button_border_color = "#FFFFFF"

    css = f"""
    <style>
    /* Background */
    .stApp {{
        background-color: {background_color};
    }}

    /* Main content text */
    .stApp div[data-testid="stVerticalBlock"] p,
    .stApp div[data-testid="stVerticalBlock"] span,
    .stApp div[data-testid="stVerticalBlock"] ul,
    .stApp div[data-testid="stVerticalBlock"] li,
    .stApp div[data-testid="stVerticalBlock"] h1,
    .stApp div[data-testid="stVerticalBlock"] h2,
    .stApp div[data-testid="stVerticalBlock"] h3,
    .stApp div[data-testid="stVerticalBlock"] h4,
    .stApp div[data-testid="stVerticalBlock"] h5,
    .stApp div[data-testid="stVerticalBlock"] h6 {{
        color: {text_color};
    }}

    /* Sidebar Styling */
    section[data-testid="stSidebar"] {{
        background-color: {sidebar_background_color};
        color: {sidebar_text_color};
    }}
    section[data-testid="stSidebar"] * {{
        color: {sidebar_text_color};
    }}
    section[data-testid="stSidebar"] a {{
        color: {sidebar_link_color};
    }}

    /* Title Styling */
    .title {{
        font-size: 2.5em;
        color: {title_color};
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.4);
        font-family: 'Montserrat', sans-serif;
        margin-bottom: 20px;
    }}

    /* Metric Styling */
    .metric-container {{
        background-color: {container_background_color};
        padding: 20px;
        border-radius: 10px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.4);
    }}
    .metric-label {{
        color: {metric_label_color};
        font-size: 1.2em;
    }}
    .metric-value {{
        color: {metric_value_color};
        font-size: 2em;
    }}
    .metric-container .metric-delta-positive {{
        color: {metric_delta_positive_color};
        font-size: 1em;
    }}
    .metric-container .metric-delta-negative {{
        color: {metric_delta_negative_color};
        font-size: 1em;
    }}
    .metric-container .metric-delta-neutral {{
        color: {metric_delta_neutral_color};
        font-size: 1em;
    }}
    .metric-description {{
        color: {metric_description_color};
        font-size: 1em;
        margin-top: 10px;
    }}

    /* Text Styling */
    .custom-text {{
        color: {text_color};
        font-size: 1.2em;
    }}

    /* Selectbox Styling */
    div[data-baseweb="select"] > div {{
        background-color: {selectbox_background_color};
        color: {selectbox_text_color};
    }}
    div[data-baseweb="select"] input {{
        background-color: {selectbox_background_color};
        color: {selectbox_text_color};
    }}
    div[data-baseweb="select"] svg {{
        fill: {selectbox_text_color};
    }}
    ul[data-baseweb="menu"] {{
        background-color: {selectbox_background_color};
        color: {selectbox_text_color};
    }}
    ul[data-baseweb="menu"] li {{
        color: {selectbox_text_color};
    }}

    /* Button Styling */
    div.stButton > button {{
        background-color: {button_background_color};
        color: {button_text_color};
        border: 1px solid {button_border_color};
        padding: 0.5em 1em;
        border-radius: 5px;
    }}
    div.stButton > button:hover {{
        background-color: {container_background_color};
    }}
    div.stButton > button:active {{
        background-color: {container_background_color};
    }}

    /* Anomaly Metric Styling */
    .anomaly-metric {{
        font-size: 1em;
        color: red;
        margin-top: 5px;
    }}

    /* Checkbox-as-button styling */
    div[data-baseweb="checkbox"] {{
        padding: 0.5em 0.75em;
        border: 1px solid #888;
        border-radius: 5px;
        display: inline-flex;
        align-items: center;
        margin-bottom: 1em;
    }}
    div[data-baseweb="checkbox"] label {{
        margin: 0;
        padding-left: 0.5em;
        font-weight: bold;
    }}
    div[data-baseweb="checkbox"] input:checked + label {{
        background-color: #22c55e;
        color: #fff;
        padding: 0.2em 0.6em;
        border-radius: 3px;
    }}
    </style>
    """
    return css

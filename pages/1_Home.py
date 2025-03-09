import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from utils.data_processing_influx import (
    get_influxdb_client,
    update_df_from_db,
    calculate_uv_index,
    temperature_description,
    humidity_description,
    aqi_description,
    uv_description,
    ambient_light_description,
    pressure_description,
    calculate_dew_point,
    dew_point_description,
    calculate_heat_index,
    heat_index_description,
    calculate_iaq,
    get_theme_css
)
from utils.sidebar import render_sidebar
import numpy as np

# Set page configuration
st.set_page_config(
    page_title="Home",
    page_icon="🏠",
    layout="wide",
)

# Automatic refresh every 5 seconds
st_autorefresh(interval=5000, key="data_refresh")

# Render the sidebar
render_sidebar()

# Get the selected theme from session state
theme = st.session_state.get('theme', 'Dark')
css_styles = get_theme_css(theme)
st.markdown(css_styles, unsafe_allow_html=True)

# Title with custom styling
st.markdown("<h1 class='title'>Real-Time Weather Data Dashboard</h1>", unsafe_allow_html=True)

# Initialize session state variables if not already done
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None

# Get InfluxDB client
client = get_influxdb_client()

# Update data
update_df_from_db(client)

# Helper function: get data from a specified time ago (using aggregated fields)
def get_data_minutes_ago(df, minutes):
    if df.empty:
        return None
    target_time = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    data = df[df['Timestamp'] <= target_time]
    return data.iloc[-1] if not data.empty else None

# Helper function: count anomalies in a given column for the last X minutes
def anomaly_count(df, col_name, minutes=30):
    if df.empty or col_name not in df.columns:
        return 0
    time_threshold = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    recent_df = df[df['Timestamp'] >= time_threshold]
    return int(recent_df[col_name].sum())

if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df
    latest_data = df.iloc[-1]
    data_30_min_ago = get_data_minutes_ago(df, 30)

    # Use aggregated fields for delta calculations.
    # Define iaq_current regardless of whether data_30_min_ago is available.
    iaq_current = calculate_iaq(latest_data['AQI_avg'], latest_data['humidity_avg'])
    
    if data_30_min_ago is not None:
        temp_delta = latest_data['temperature_avg'] - data_30_min_ago['temperature_avg']
        humidity_delta = latest_data['humidity_avg'] - data_30_min_ago['humidity_avg']
        pressure_delta = latest_data['pressure_avg'] - data_30_min_ago['pressure_avg']
        iaq_past = calculate_iaq(data_30_min_ago['AQI_avg'], data_30_min_ago['humidity_avg'])
        iaq_delta = iaq_current - iaq_past
        uv_index = calculate_uv_index(latest_data['uv_data_avg'])
        uv_index_delta = uv_index - calculate_uv_index(data_30_min_ago['uv_data_avg'])
        light_delta = latest_data['ambient_light_avg'] - data_30_min_ago['ambient_light_avg']
    else:
        temp_delta = humidity_delta = pressure_delta = iaq_delta = uv_index_delta = light_delta = None

    # Compute anomaly counts for Temperature, Humidity, Pressure, IAQ, UV, and Ambient Light
    temp_anomaly_count = anomaly_count(df, 'temperature_anomaly', minutes=30)
    humidity_anomaly_count = anomaly_count(df, 'humidity_anomaly', minutes=30)
    pressure_anomaly_count = anomaly_count(df, 'pressure_anomaly', minutes=30)
    iaq_anomaly_count = anomaly_count(df, 'AQI_anomaly', minutes=30)
    uv_anomaly_count = anomaly_count(df, 'uv_data_anomaly', minutes=30)
    light_anomaly_count = anomaly_count(df, 'ambient_light_anomaly', minutes=30)

    st.subheader("Latest Sensor Readings")

    def determine_delta_class(delta_value):
        if delta_value is not None:
            if delta_value > 0:
                return "metric-delta-positive"
            elif delta_value < 0:
                return "metric-delta-negative"
            else:
                return "metric-delta-neutral"
        else:
            return "metric-delta-neutral"

    # First row: Temperature & Humidity
    col1, col2 = st.columns(2)
    with col1:
        delta_str = f"{temp_delta:+.2f} °C" if temp_delta is not None else "N/A"
        delta_class = determine_delta_class(temp_delta)
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Temperature</div>
                <div class="metric-value">{latest_data['temperature_avg']:.2f} °C</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {temp_anomaly_count}</div>
                <div class="metric-description">{temperature_description(latest_data['temperature_avg'])}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col2:
        delta_str = f"{humidity_delta:+.2f} %" if humidity_delta is not None else "N/A"
        delta_class = determine_delta_class(humidity_delta)
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Humidity</div>
                <div class="metric-value">{latest_data['humidity_avg']:.2f} %</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {humidity_anomaly_count}</div>
                <div class="metric-description">{humidity_description(latest_data['humidity_avg'])}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Second row: Pressure & Indoor Air Quality (IAQ)
    col3, col4 = st.columns(2)
    with col3:
        delta_str = f"{pressure_delta:+.2f} hPa" if pressure_delta is not None else "N/A"
        delta_class = determine_delta_class(pressure_delta)
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Pressure</div>
                <div class="metric-value">{latest_data['pressure_avg']:.2f} hPa</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {pressure_anomaly_count}</div>
                <div class="metric-description">{pressure_description(latest_data['pressure_avg'])}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col4:
        delta_str = f"{iaq_delta:+.2f}" if iaq_delta is not None else "N/A"
        delta_class = determine_delta_class(iaq_delta)
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Indoor Air Quality (IAQ)</div>
                <div class="metric-value">{iaq_current:.2f}</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {iaq_anomaly_count}</div>
                <div class="metric-description">{aqi_description(iaq_current)}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Third row: UV Index & Ambient Light
    col5, col6 = st.columns(2)
    with col5:
        delta_str = f"{uv_index_delta:+.2f}" if uv_index_delta is not None else "N/A"
        delta_class = determine_delta_class(uv_index_delta)
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">UV Index</div>
                <div class="metric-value">{calculate_uv_index(latest_data['uv_data_avg']):.2f}</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {uv_anomaly_count}</div>
                <div class="metric-description">{uv_description(calculate_uv_index(latest_data['uv_data_avg']))}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col6:
        delta_str = f"{light_delta:+.2f} lux" if light_delta is not None else "N/A"
        delta_class = determine_delta_class(light_delta)
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Ambient Light</div>
                <div class="metric-value">{latest_data['ambient_light_avg']:.2f} lux</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {light_anomaly_count}</div>
                <div class="metric-description">{ambient_light_description(latest_data['ambient_light_avg'])}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Fourth row: Dew Point & Heat Index (no anomalies)
    col7, col8 = st.columns(2)
    with col7:
        dew_point = calculate_dew_point(latest_data['temperature_avg'], latest_data['humidity_avg'])
        dew_point_delta = dew_point - calculate_dew_point(data_30_min_ago['temperature_avg'], data_30_min_ago['humidity_avg']) if data_30_min_ago is not None else None
        delta_str = f"{dew_point_delta:+.2f} °C" if dew_point_delta is not None else "N/A"
        delta_class = determine_delta_class(dew_point_delta)
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Dew Point</div>
                <div class="metric-value">{dew_point:.2f} °C</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="metric-description">{dew_point_description(dew_point)}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col8:
        heat_index = calculate_heat_index(latest_data['temperature_avg'], latest_data['humidity_avg'])
        heat_index_delta = heat_index - calculate_heat_index(data_30_min_ago['temperature_avg'], data_30_min_ago['humidity_avg']) if data_30_min_ago is not None else None
        delta_str = f"{heat_index_delta:+.2f} °C" if heat_index_delta is not None else "N/A"
        delta_class = determine_delta_class(heat_index_delta)
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Heat Index</div>
                <div class="metric-value">{heat_index:.2f} °C</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="metric-description">{heat_index_description(heat_index)}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.write(f"**Timestamp:** {latest_data['Timestamp']}")
else:
    st.warning("No data available yet.")


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
    get_theme_css,
)
from utils.sidebar import render_sidebar
import numpy as np


# ────────────────────────────────────────────────────────────────────
# Page config & auto‑refresh
# ────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Home", page_icon="🏠", layout="wide")
st_autorefresh(interval=30000, key="data_refresh")

# Sidebar & theme
render_sidebar()
theme = st.session_state.get("theme", "Dark")
st.markdown(get_theme_css(theme), unsafe_allow_html=True)

# Title
st.markdown("<h1 class='title'>Real‑Time Weather Data Dashboard</h1>", unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────
# Session‑state initialisation
# ────────────────────────────────────────────────────────────────────
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None

client = get_influxdb_client()
update_df_from_db(client)

# ────────────────────────────────────────────────────────────────────
# Helpers (no anomaly helpers any more)
# ────────────────────────────────────────────────────────────────────
def get_data_minutes_ago(df, minutes):
    if df.empty:
        return None
    target_time = df["Timestamp"].iloc[-1] - pd.Timedelta(minutes=minutes)
    data = df[df["Timestamp"] <= target_time]
    return data.iloc[-1] if not data.empty else None


def determine_delta_class(delta_value):
    if delta_value is None:
        return "metric-delta-neutral"
    if delta_value > 0:
        return "metric-delta-positive"
    if delta_value < 0:
        return "metric-delta-negative"
    return "metric-delta-neutral"


# ────────────────────────────────────────────────────────────────────
# Main display
# ────────────────────────────────────────────────────────────────────
if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df
    latest_data = df.iloc[-1]
    data_30_min_ago = get_data_minutes_ago(df, 30)

    iaq_current = calculate_iaq(latest_data["AQI_avg"], latest_data["humidity_avg"])

    if data_30_min_ago is not None:
        temp_delta = latest_data["temperature_avg"] - data_30_min_ago["temperature_avg"]
        humidity_delta = latest_data["humidity_avg"] - data_30_min_ago["humidity_avg"]
        pressure_delta = latest_data["pressure_avg"] - data_30_min_ago["pressure_avg"]
        iaq_delta = iaq_current - calculate_iaq(
            data_30_min_ago["AQI_avg"], data_30_min_ago["humidity_avg"]
        )
        uv_index = calculate_uv_index(latest_data["uv_data_avg"])
        uv_index_delta = uv_index - calculate_uv_index(data_30_min_ago["uv_data_avg"])
        light_delta = latest_data["ambient_light_avg"] - data_30_min_ago["ambient_light_avg"]
    else:
        temp_delta = humidity_delta = pressure_delta = iaq_delta = uv_index_delta = light_delta = None

    st.subheader("Latest Sensor Readings")

    # 1) Temperature & Humidity
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Temperature</div>
                <div class="metric-value">{latest_data['temperature_avg']:.2f} °C</div>
                <div class="{determine_delta_class(temp_delta)}">
                    Change: {f"{temp_delta:+.2f} °C" if temp_delta is not None else "N/A"}
                </div>
                <div class="metric-description">
                    {temperature_description(latest_data['temperature_avg'])}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Humidity</div>
                <div class="metric-value">{latest_data['humidity_avg']:.2f} %</div>
                <div class="{determine_delta_class(humidity_delta)}">
                    Change: {f"{humidity_delta:+.2f} %" if humidity_delta is not None else "N/A"}
                </div>
                <div class="metric-description">
                    {humidity_description(latest_data['humidity_avg'])}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 2) Pressure & IAQ
    col3, col4 = st.columns(2)
    with col3:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Pressure</div>
                <div class="metric-value">{latest_data['pressure_avg']:.2f} hPa</div>
                <div class="{determine_delta_class(pressure_delta)}">
                    Change: {f"{pressure_delta:+.2f} hPa" if pressure_delta is not None else "N/A"}
                </div>
                <div class="metric-description">
                    {pressure_description(latest_data['pressure_avg'])}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col4:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Indoor Air Quality (IAQ)</div>
                <div class="metric-value">{iaq_current:.2f}</div>
                <div class="{determine_delta_class(iaq_delta)}">
                    Change: {f"{iaq_delta:+.2f}" if iaq_delta is not None else "N/A"}
                </div>
                <div class="metric-description">
                    {aqi_description(iaq_current)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 3) UV Index & Ambient Light
    col5, col6 = st.columns(2)
    with col5:
        uv_index_now = calculate_uv_index(latest_data["uv_data_avg"])
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">UV Index</div>
                <div class="metric-value">{uv_index_now:.2f}</div>
                <div class="{determine_delta_class(uv_index_delta)}">
                    Change: {f"{uv_index_delta:+.2f}" if uv_index_delta is not None else "N/A"}
                </div>
                <div class="metric-description">
                    {uv_description(uv_index_now)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col6:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Ambient Light</div>
                <div class="metric-value">{latest_data['ambient_light_avg']:.2f} lux</div>
                <div class="{determine_delta_class(light_delta)}">
                    Change: {f"{light_delta:+.2f} lux" if light_delta is not None else "N/A"}
                </div>
                <div class="metric-description">
                    {ambient_light_description(latest_data['ambient_light_avg'])}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # 4) Dew Point & Heat Index
    col7, col8 = st.columns(2)
    with col7:
        dew_point_now = calculate_dew_point(
            latest_data["temperature_avg"], latest_data["humidity_avg"]
        )
        dew_point_delta = (
            dew_point_now
            - calculate_dew_point(
                data_30_min_ago["temperature_avg"], data_30_min_ago["humidity_avg"]
            )
            if data_30_min_ago is not None
            else None
        )
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Dew Point</div>
                <div class="metric-value">{dew_point_now:.2f} °C</div>
                <div class="{determine_delta_class(dew_point_delta)}">
                    Change: {f"{dew_point_delta:+.2f} °C" if dew_point_delta is not None else "N/A"}
                </div>
                <div class="metric-description">
                    {dew_point_description(dew_point_now)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col8:
        heat_index_now = calculate_heat_index(
            latest_data["temperature_avg"], latest_data["humidity_avg"]
        )
        heat_index_delta = (
            heat_index_now
            - calculate_heat_index(
                data_30_min_ago["temperature_avg"], data_30_min_ago["humidity_avg"]
            )
            if data_30_min_ago is not None
            else None
        )
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Heat Index</div>
                <div class="metric-value">{heat_index_now:.2f} °C</div>
                <div class="{determine_delta_class(heat_index_delta)}">
                    Change: {f"{heat_index_delta:+.2f} °C" if heat_index_delta is not None else "N/A"}
                </div>
                <div class="metric-description">
                    {heat_index_description(heat_index_now)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write(f"**Timestamp:** {latest_data['Timestamp']}")
else:
    st.warning("No data available yet.")

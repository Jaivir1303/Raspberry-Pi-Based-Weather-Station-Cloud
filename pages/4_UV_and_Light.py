import streamlit as st
import pandas as pd
import numpy as np
from utils.data_processing_influx import (
    get_influxdb_client,
    update_df_from_db,
    calculate_uv_index,
    uv_description,
    get_theme_css
)
from utils.sidebar import render_sidebar
from streamlit_autorefresh import st_autorefresh
import plotly.express as px

# ---------------------------
# Helper Function: Count Anomalies
# ---------------------------
def anomaly_count(df, col_name, minutes=30):
    if df.empty or col_name not in df.columns:
        return 0
    time_threshold = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    recent_df = df[df['Timestamp'] >= time_threshold]
    return int(recent_df[col_name].sum())

# ---------------------------
# Streamlit Page Config
# ---------------------------
st.set_page_config(
    page_title="UV and Light",
    page_icon="☀️",
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
st.markdown("<h1 class='title'>UV and Light</h1>", unsafe_allow_html=True)

# Initialize session state variables if not already done
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None

# InfluxDB client
client = get_influxdb_client()
update_df_from_db(client)

if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df.copy()
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # ---------------------------------------------
    # Rename Aggregated Columns + Anomaly Columns
    # ---------------------------------------------
    rename_map = {
        'uv_data_avg': 'uv_data',
        'ambient_light_avg': 'ambient_light',
        'uv_data_anomaly': 'uv_anomaly',
        'ambient_light_anomaly': 'light_anomaly'
    }
    for old_col, new_col in rename_map.items():
        if old_col in df.columns:
            df.rename(columns={old_col: new_col}, inplace=True)

    # Ensure numeric
    metrics = ['uv_data', 'ambient_light']
    for metric in metrics:
        if metric not in df.columns:
            st.warning(f"Missing expected column '{metric}' in aggregated data.")
            st.stop()
        df[metric] = pd.to_numeric(df[metric], errors='coerce')

    df.dropna(subset=metrics, inplace=True)
    if df.empty:
        st.warning("No valid UV or Light data in aggregator.")
        st.stop()

    # Calculate UV Index
    df['UV_Index'] = df['uv_data'].apply(calculate_uv_index)

    # Latest row
    latest_data = df.iloc[-1]

    # UV Category
    uv_category = uv_description(latest_data['UV_Index'])

    # Color based on UV Index
    def get_uv_color(uv_index):
        if uv_index >= 11:
            return "#FF0000"  # Extreme
        elif uv_index >= 8:
            return "#FF4500"  # Very High
        elif uv_index >= 6:
            return "#FFA500"  # High
        elif uv_index >= 3:
            return "#FFFF00"  # Moderate
        else:
            return "#00FF00"  # Low

    category_color = get_uv_color(latest_data['UV_Index'])

    # ---------------------------
    # Metric Containers + Anomalies
    # ---------------------------
    st.subheader("Current UV Index and Ambient Light")

    # Compute anomaly counts (last 30 min)
    uv_anomaly_count = anomaly_count(df, 'uv_anomaly', 30)
    light_anomaly_count = anomaly_count(df, 'light_anomaly', 30)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">UV Index</div>
                <div class="metric-value">{latest_data['UV_Index']:.2f}</div>
                <div class="metric-category" style="color: {category_color};">{uv_category}</div>
                <div class="anomaly-metric">Anomalies (30min): {uv_anomaly_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Ambient Light</div>
                <div class="metric-value">{latest_data['ambient_light']:.2f} lux</div>
                <div class="anomaly-metric">Anomalies (30min): {light_anomaly_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # ---------------------------
    # Plot Theme Settings
    # ---------------------------
    if theme == "Light":
        plot_bgcolor = 'rgb(240,240,240)'
        paper_bgcolor = 'rgb(240,240,240)'
        font_color = 'black'
        axis_color = "#000000"
    else:
        plot_bgcolor = 'rgb(17,17,17)'
        paper_bgcolor = 'rgb(17,17,17)'
        font_color = 'white'
        axis_color = "#FFFFFF"

    # ---------------------------
    # Time Range Slider
    # ---------------------------
    min_time = df['Timestamp'].min()
    max_time = df['Timestamp'].max()
    time_range = st.slider(
        'Select Time Range',
        min_value=min_time.to_pydatetime(),
        max_value=max_time.to_pydatetime(),
        value=(min_time.to_pydatetime(), max_time.to_pydatetime()),
        format="YYYY-MM-DD HH:mm"
    )
    mask = (df['Timestamp'] >= time_range[0]) & (df['Timestamp'] <= time_range[1])
    df_filtered = df.loc[mask]

    # ---------------------------
    # UV Index Over Time
    # ---------------------------
    st.subheader("UV Index Over Time")

    if df_filtered.empty:
        st.warning("No data available for the selected time range.")
    else:
        fig_uv = px.line(df_filtered, x='Timestamp', y='UV_Index', color_discrete_sequence=['#FFA500'])
        fig_uv.update_traces(mode='lines', name='UV Index')

        # Overlay anomaly markers for UV
        if 'uv_anomaly' in df_filtered.columns:
            uv_anom = df_filtered[df_filtered['uv_anomaly'] == 1]
            if not uv_anom.empty:
                fig_uv.add_scatter(
                    x=uv_anom['Timestamp'],
                    y=uv_anom['UV_Index'],
                    mode='markers',
                    name='UV Anomaly',
                    marker=dict(color='red', size=8, symbol='x')
                )

        fig_uv.update_layout(
            xaxis_title='Time',
            yaxis_title='UV Index',
            plot_bgcolor=plot_bgcolor,
            paper_bgcolor=paper_bgcolor,
            font=dict(color=font_color),
            xaxis=dict(
                tickformat='%H:%M',
                titlefont=dict(color=font_color),
                tickfont=dict(color=font_color),
                linecolor=axis_color,
                showgrid=False
            ),
            yaxis=dict(
                titlefont=dict(color=font_color),
                tickfont=dict(color=font_color),
                linecolor=axis_color,
                showgrid=False
            )
        )
        st.plotly_chart(fig_uv, use_container_width=True)

    # ---------------------------
    # Ambient Light Over Time
    # ---------------------------
    st.subheader("Ambient Light Over Time")

    if df_filtered.empty:
        st.warning("No data available for the selected time range.")
    else:
        fig_light = px.line(df_filtered, x='Timestamp', y='ambient_light', color_discrete_sequence=['#00FFFF'])
        fig_light.update_traces(mode='lines', name='Ambient Light')

        # Overlay anomaly markers for Light
        if 'light_anomaly' in df_filtered.columns:
            light_anom = df_filtered[df_filtered['light_anomaly'] == 1]
            if not light_anom.empty:
                fig_light.add_scatter(
                    x=light_anom['Timestamp'],
                    y=light_anom['ambient_light'],
                    mode='markers',
                    name='Light Anomaly',
                    marker=dict(color='red', size=8, symbol='x')
                )

        fig_light.update_layout(
            xaxis_title='Time',
            yaxis_title='Ambient Light (lux)',
            plot_bgcolor=plot_bgcolor,
            paper_bgcolor=paper_bgcolor,
            font=dict(color=font_color),
            xaxis=dict(
                tickformat='%H:%M',
                titlefont=dict(color=font_color),
                tickfont=dict(color=font_color),
                linecolor=axis_color,
                showgrid=False
            ),
            yaxis=dict(
                titlefont=dict(color=font_color),
                tickfont=dict(color=font_color),
                linecolor=axis_color,
                showgrid=False
            )
        )
        st.plotly_chart(fig_light, use_container_width=True)

    # ---------------------------
    # Health Advisory
    # ---------------------------
    st.subheader("Health Advisory")
    uv_index_val = latest_data['UV_Index']
    uv_advisory = ""

    if uv_index_val >= 11:
        uv_advisory = "⚠️ **Extreme UV exposure risk! Avoid sun exposure and seek shade.**"
    elif uv_index_val >= 8:
        uv_advisory = "🛑 **Very High UV exposure risk! Wear protective clothing, sunglasses, and apply sunscreen.**"
    elif uv_index_val >= 6:
        uv_advisory = "🔆 **High UV exposure risk! Reduce time in the sun during midday hours and seek shade.**"
    elif uv_index_val >= 3:
        uv_advisory = "🌞 **Moderate UV exposure risk! Stay in shade near midday when the sun is strongest.**"
    else:
        uv_advisory = "🌙 **Low UV exposure risk. Enjoy your time outside!**"

    st.markdown(uv_advisory)
else:
    st.warning("No data available yet.")


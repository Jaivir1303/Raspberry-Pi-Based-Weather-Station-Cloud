import streamlit as st
import pandas as pd
import numpy as np
from utils.data_processing_influx import (
    get_influxdb_client,
    update_df_from_db,
    get_theme_css
)
from utils.sidebar import render_sidebar
from streamlit_autorefresh import st_autorefresh
import plotly.express as px

# Set page configuration
st.set_page_config(
    page_title="Weather Metrics",
    page_icon="🌡️",
    layout="wide",
)

# Automatic refresh every 5 seconds
st_autorefresh(interval=5000, key="data_refresh")

# Render the sidebar
render_sidebar()

# Get the selected theme from session_state
theme = st.session_state.get('theme', 'Dark')
css_styles = get_theme_css(theme)
st.markdown(css_styles, unsafe_allow_html=True)

# Title
st.markdown("<h1 class='title'>Weather Metrics</h1>", unsafe_allow_html=True)

# Initialize session state if not present
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None

# InfluxDB client
client = get_influxdb_client()
update_df_from_db(client)

# Helper: get data from a specified time ago (30 mins) using aggregated fields
def get_data_minutes_ago(df, minutes=30):
    if df.empty:
        return None
    cutoff_time = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    older_data = df[df['Timestamp'] <= cutoff_time]
    return older_data.iloc[-1] if not older_data.empty else None

# Helper: count anomalies in last X minutes
def anomaly_count(df, col_name, minutes=30):
    if df.empty or col_name not in df.columns:
        return 0
    time_threshold = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    recent_df = df[df['Timestamp'] >= time_threshold]
    return int(recent_df[col_name].sum())

if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df.copy()
    # We expect columns like temperature_avg, humidity_avg, pressure_avg, plus anomalies
    # e.g. temperature_anomaly, humidity_anomaly, pressure_anomaly

    # Clean out rows where these fields are missing
    needed_cols = ['temperature_avg', 'humidity_avg', 'pressure_avg']
    df.dropna(subset=needed_cols, inplace=True)

    # Last row
    latest_data = df.iloc[-1]
    old_data = get_data_minutes_ago(df, 30)

    # Calculate deltas for temperature, humidity, pressure
    if old_data is not None:
        temp_delta = latest_data['temperature_avg'] - old_data['temperature_avg']
        humidity_delta = latest_data['humidity_avg'] - old_data['humidity_avg']
        pressure_delta = latest_data['pressure_avg'] - old_data['pressure_avg']
    else:
        temp_delta = humidity_delta = pressure_delta = None

    # Anomaly counts
    temp_anomaly_count = anomaly_count(df, 'temperature_anomaly', 30)
    humidity_anomaly_count = anomaly_count(df, 'humidity_anomaly', 30)
    pressure_anomaly_count = anomaly_count(df, 'pressure_anomaly', 30)

    # Display metric containers
    st.subheader("Current Weather Metrics")

    def delta_class(value):
        if value is None:
            return "metric-delta-neutral"
        elif value > 0:
            return "metric-delta-positive"
        elif value < 0:
            return "metric-delta-negative"
        else:
            return "metric-delta-neutral"

    col1, col2, col3 = st.columns(3)
    with col1:
        dc = delta_class(temp_delta)
        delta_str = f"{temp_delta:+.2f} °C" if temp_delta is not None else "N/A"
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Temperature</div>
                <div class="metric-value">{latest_data['temperature_avg']:.2f} °C</div>
                <div class="{dc}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {temp_anomaly_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col2:
        dc = delta_class(humidity_delta)
        delta_str = f"{humidity_delta:+.2f} %" if humidity_delta is not None else "N/A"
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Humidity</div>
                <div class="metric-value">{latest_data['humidity_avg']:.2f} %</div>
                <div class="{dc}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {humidity_anomaly_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col3:
        dc = delta_class(pressure_delta)
        delta_str = f"{pressure_delta:+.2f} hPa" if pressure_delta is not None else "N/A"
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Pressure</div>
                <div class="metric-value">{latest_data['pressure_avg']:.2f} hPa</div>
                <div class="{dc}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {pressure_anomaly_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st.subheader("Weather Metrics Over Time")

    # Plot theme
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

    # -----------------------
    # Temperature Graph
    # -----------------------
    st.markdown("#### Temperature Over Time")
    fig_temp = px.line(df, x='Timestamp', y='temperature_avg', color_discrete_sequence=['red'])
    fig_temp.update_traces(mode='lines', name='Temperature (°C)')
    
    # Overlay anomaly markers
    temp_anom = df[df['temperature_anomaly'] == 1]
    if not temp_anom.empty:
        fig_temp.add_scatter(
            x=temp_anom['Timestamp'],
            y=temp_anom['temperature_avg'],
            mode='markers',
            name='Temp Anomaly',
            marker=dict(color='orange', size=8, symbol='x')
        )

    fig_temp.update_layout(
        xaxis_title='Time',
        yaxis_title='Temperature (°C)',
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
            showgrid=False,
            autorange=True
        ),
        legend=dict(
            font=dict(color=font_color)
        )
    )
    st.plotly_chart(fig_temp, use_container_width=True)

    # -----------------------
    # Humidity Graph
    # -----------------------
    st.markdown("#### Humidity Over Time")
    fig_hum = px.line(df, x='Timestamp', y='humidity_avg', color_discrete_sequence=['blue'])
    fig_hum.update_traces(mode='lines', name='Humidity (%)')
    
    # Overlay anomaly markers
    hum_anom = df[df['humidity_anomaly'] == 1]
    if not hum_anom.empty:
        fig_hum.add_scatter(
            x=hum_anom['Timestamp'],
            y=hum_anom['humidity_avg'],
            mode='markers',
            name='Humidity Anomaly',
            marker=dict(color='orange', size=8, symbol='x')
        )

    fig_hum.update_layout(
        xaxis_title='Time',
        yaxis_title='Humidity (%)',
        plot_bgcolor=plot_bgcolor,
        paper_bgcolor=paper_bgcolor,
        font=dict(color=font_color),
        xaxis=dict(
            tickformat="%H:%M",
            titlefont=dict(color=font_color),
            tickfont=dict(color=font_color),
            linecolor=axis_color,
            showgrid=False
        ),
        yaxis=dict(
            titlefont=dict(color=font_color),
            tickfont=dict(color=font_color),
            linecolor=axis_color,
            showgrid=False,
            autorange=True
        ),
        legend=dict(
            font=dict(color=font_color)
        )
    )
    st.plotly_chart(fig_hum, use_container_width=True)

    # -----------------------
    # Pressure Graph
    # -----------------------
    st.markdown("#### Pressure Over Time")
    fig_pres = px.line(df, x='Timestamp', y='pressure_avg', color_discrete_sequence=['green'])
    fig_pres.update_traces(mode='lines', name='Pressure (hPa)')
    
    # Overlay anomaly markers
    pres_anom = df[df['pressure_anomaly'] == 1]
    if not pres_anom.empty:
        fig_pres.add_scatter(
            x=pres_anom['Timestamp'],
            y=pres_anom['pressure_avg'],
            mode='markers',
            name='Pressure Anomaly',
            marker=dict(color='orange', size=8, symbol='x')
        )

    fig_pres.update_layout(
        xaxis_title='Time',
        yaxis_title='Pressure (hPa)',
        plot_bgcolor=plot_bgcolor,
        paper_bgcolor=paper_bgcolor,
        font=dict(color=font_color),
        xaxis=dict(
            tickformat="%H:%M",
            titlefont=dict(color=font_color),
            tickfont=dict(color=font_color),
            linecolor=axis_color,
            showgrid=False
        ),
        yaxis=dict(
            titlefont=dict(color=font_color),
            tickfont=dict(color=font_color),
            linecolor=axis_color,
            showgrid=False,
            autorange=True
        ),
        legend=dict(
            font=dict(color=font_color)
        )
    )
    st.plotly_chart(fig_pres, use_container_width=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # Display correlation among aggregated fields
    st.subheader("Correlation Values")
    corr_cols = ['temperature_avg', 'humidity_avg', 'pressure_avg']
    corr_df = df.dropna(subset=corr_cols)
    corr_matrix = corr_df[corr_cols].corr()

    st.table(corr_matrix.style.background_gradient(cmap='coolwarm').format(precision=2))

else:
    st.warning("No data available yet.")


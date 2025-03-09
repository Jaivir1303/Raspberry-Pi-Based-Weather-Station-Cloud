import pandas as pd
import streamlit as st
import plotly.graph_objs as go
import time
from streamlit_autorefresh import st_autorefresh
from utils.data_processing_influx import get_influxdb_client, update_df_from_db, get_theme_css
from utils.sidebar import render_sidebar

# ---------------------------
# Utility Function for Manual Ranges
# ---------------------------
def axis_range(series, padding_ratio=0.1, min_padding=0.5):
    """
    Returns a [min, max] range for the given series,
    with some padding to avoid the trace hitting the border.
    """
    if series.empty:
        # If no data, return a default range
        return [0, 1]
    val_min = float(series.min())
    val_max = float(series.max())
    if val_min == val_max:
        # If data is constant or near-constant, pick an arbitrary small range
        return [val_min - 1, val_min + 1]
    
    span = val_max - val_min
    padding = max(span * padding_ratio, min_padding)
    return [val_min - padding, val_max + padding]

# ---------------------------
# Streamlit Page Config
# ---------------------------
st.set_page_config(
    page_title="Real-Time Weather Data Dashboard",
    page_icon="🌤️",
    layout="wide",
)

# Automatically refresh every 5 seconds
st_autorefresh(interval=5000, key="data_refresh")

# Render the sidebar
render_sidebar()

# Get the selected theme from session state
theme = st.session_state.get('theme', 'Dark')
css_styles = get_theme_css(theme)
st.markdown(css_styles, unsafe_allow_html=True)

# Main title with custom styling
st.markdown("<h1 class='title'>Real-Time Weather Data Dashboard</h1>", unsafe_allow_html=True)

# Initialize session state variables if not already done
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None  # Will default to 1970-01-01 in the function

# InfluxDB client
client = get_influxdb_client()

# Update data from InfluxDB Cloud
update_df_from_db(client)

# ---------------------------
# Helper Functions
# ---------------------------
def anomaly_count(df, col_name, minutes=30):
    if df.empty or col_name not in df.columns:
        return 0
    time_threshold = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    recent_df = df[df['Timestamp'] >= time_threshold]
    return int(recent_df[col_name].sum())

def get_old_data(df, minutes=30):
    if df.empty:
        return None
    time_diff = pd.Timedelta(minutes=minutes)
    old_timestamp = df['Timestamp'].iloc[-1] - time_diff
    old_data = df[df['Timestamp'] <= old_timestamp]
    if not old_data.empty:
        return old_data.iloc[-1]
    else:
        return None

# ---------------------------
# Main Logic
# ---------------------------
if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df
    latest_data = df.iloc[-1]
    old_data = get_old_data(df, minutes=30)
    
    # Calculate deltas using aggregated values
    if old_data is not None:
        temp_delta = latest_data['temperature_avg'] - old_data['temperature_avg']
        humidity_delta = latest_data['humidity_avg'] - old_data['humidity_avg']
        pressure_delta = latest_data['pressure_avg'] - old_data['pressure_avg']
    else:
        temp_delta = humidity_delta = pressure_delta = None

    # Compute anomaly counts over last 30 minutes
    temp_anomaly_count = anomaly_count(df, 'temperature_anomaly', minutes=30)
    humidity_anomaly_count = anomaly_count(df, 'humidity_anomaly', minutes=30)
    pressure_anomaly_count = anomaly_count(df, 'pressure_anomaly', minutes=30)

    # Display metrics
    col1, col2, col3 = st.columns(3)
    
    # Temperature Metric
    with col1:
        delta_str = f"{temp_delta:+.2f} °C" if temp_delta is not None else "N/A"
        if temp_delta is not None:
            if temp_delta > 0:
                delta_class = "metric-delta-positive"
            elif temp_delta < 0:
                delta_class = "metric-delta-negative"
            else:
                delta_class = "metric-delta-neutral"
        else:
            delta_class = "metric-delta-neutral"
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Temperature</div>
                <div class="metric-value">{latest_data['temperature_avg']:.2f} °C</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {temp_anomaly_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    # Humidity Metric
    with col2:
        delta_str = f"{humidity_delta:+.2f} %" if humidity_delta is not None else "N/A"
        if humidity_delta is not None:
            if humidity_delta > 0:
                delta_class = "metric-delta-positive"
            elif humidity_delta < 0:
                delta_class = "metric-delta-negative"
            else:
                delta_class = "metric-delta-neutral"
        else:
            delta_class = "metric-delta-neutral"
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Humidity</div>
                <div class="metric-value">{latest_data['humidity_avg']:.2f} %</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {humidity_anomaly_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    # Pressure Metric
    with col3:
        delta_str = f"{pressure_delta:+.2f} hPa" if pressure_delta is not None else "N/A"
        if pressure_delta is not None:
            if pressure_delta > 0:
                delta_class = "metric-delta-positive"
            elif pressure_delta < 0:
                delta_class = "metric-delta-negative"
            else:
                delta_class = "metric-delta-neutral"
        else:
            delta_class = "metric-delta-neutral"
        st.markdown(
            f"""
            <div class="metric-container">
                <div class="metric-label">Pressure</div>
                <div class="metric-value">{latest_data['pressure_avg']:.2f} hPa</div>
                <div class="{delta_class}">Change: {delta_str}</div>
                <div class="anomaly-metric">Anomalies (30min): {pressure_anomaly_count}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    # Plot: Temperature, Humidity, Pressure
    st.subheader("Temperature, Humidity, and Pressure Over Time")
    
    # Plot theme
    if theme == "Light":
        plot_bgcolor = 'rgb(240,240,240)'
        paper_bgcolor = 'rgb(240,240,240)'
        font_color = 'black'
    else:
        plot_bgcolor = 'rgb(17,17,17)'
        paper_bgcolor = 'rgb(17,17,17)'
        font_color = 'white'
    
    fig = go.Figure()

    # Temperature trace
    fig.add_trace(go.Scatter(
        x=df['Timestamp'],
        y=df['temperature_avg'],
        mode='lines',
        name='Temperature (°C)',
        line=dict(color='red'),
        yaxis='y1'
    ))
    # Temperature anomaly markers -> align with y1
    temp_anom = df[df['temperature_anomaly'] == 1]
    if not temp_anom.empty:
        fig.add_trace(go.Scatter(
            x=temp_anom['Timestamp'],
            y=temp_anom['temperature_avg'],
            mode='markers',
            name='Temp Anomaly',
            marker=dict(color='orange', size=10, symbol='x'),
            yaxis='y1'
        ))

    # Humidity trace
    fig.add_trace(go.Scatter(
        x=df['Timestamp'],
        y=df['humidity_avg'],
        mode='lines',
        name='Humidity (%)',
        line=dict(color='blue'),
        yaxis='y2'
    ))
    # Humidity anomaly markers -> align with y2
    hum_anom = df[df['humidity_anomaly'] == 1]
    if not hum_anom.empty:
        fig.add_trace(go.Scatter(
            x=hum_anom['Timestamp'],
            y=hum_anom['humidity_avg'],
            mode='markers',
            name='Humidity Anomaly',
            marker=dict(color='orange', size=10, symbol='x'),
            yaxis='y2'
        ))

    # Pressure trace
    fig.add_trace(go.Scatter(
        x=df['Timestamp'],
        y=df['pressure_avg'],
        mode='lines',
        name='Pressure (hPa)',
        line=dict(color='green'),
        yaxis='y3'
    ))
    # Pressure anomaly markers -> align with y3
    pres_anom = df[df['pressure_anomaly'] == 1]
    if not pres_anom.empty:
        fig.add_trace(go.Scatter(
            x=pres_anom['Timestamp'],
            y=pres_anom['pressure_avg'],
            mode='markers',
            name='Pressure Anomaly',
            marker=dict(color='orange', size=10, symbol='x'),
            yaxis='y3'
        ))
    
    # ---------------------------
    # Manual Range for Each Axis
    # ---------------------------
    temp_minmax = axis_range(df['temperature_avg'])
    hum_minmax = axis_range(df['humidity_avg'])
    pres_minmax = axis_range(df['pressure_avg'])

    # Update layout
    fig.update_layout(
        xaxis=dict(
            domain=[0.1, 0.9],
            title='Time',
            titlefont=dict(color=font_color),
            tickfont=dict(color=font_color)
        ),
        yaxis=dict(
            title="Temperature (°C)",
            titlefont=dict(color='red'),
            tickfont=dict(color='red'),
            anchor="free",
            position=0.05,
            range=temp_minmax  # manual range for temperature
        ),
        yaxis2=dict(
            title="Humidity (%)",
            titlefont=dict(color='blue'),
            tickfont=dict(color='blue'),
            anchor="x",
            overlaying="y",
            side="left",
            position=0,
            range=hum_minmax  # manual range for humidity
        ),
        yaxis3=dict(
            title="Pressure (hPa)",
            titlefont=dict(color='green'),
            tickfont=dict(color='green'),
            anchor="free",
            overlaying="y",
            side="right",
            position=0.95,
            range=pres_minmax  # manual range for pressure
        ),
        legend=dict(
            x=0,
            y=1.1,
            orientation="h",
            font=dict(color=font_color)
        ),
        plot_bgcolor=plot_bgcolor,
        paper_bgcolor=paper_bgcolor,
        font=dict(color=font_color),
        margin=dict(l=40, r=40, t=40, b=40)
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # Display timestamp
    st.write(f"**Last Updated:** {latest_data['Timestamp']}")
    
    # Footer
    st.markdown("<div style='text-align: center; color: gray;'>Data is updated in real-time from the sensors.</div>", unsafe_allow_html=True)
else:
    st.warning("No data available yet.")


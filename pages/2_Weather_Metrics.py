import streamlit as st
import pandas as pd
import numpy as np
from utils.data_processing_influx import get_influxdb_client, update_df_from_db, get_theme_css
from utils.sidebar import render_sidebar
from streamlit_autorefresh import st_autorefresh
import plotly.express as px

# ---------------------------
# Page Config & Refresh
# ---------------------------
st.set_page_config(
    page_title="Weather Metrics",
    page_icon="🌡️",
    layout="wide",
)
st_autorefresh(interval=30000, key="data_refresh")  # every 30s

# ---------------------------
# Sidebar & Theme
# ---------------------------
render_sidebar()
theme = st.session_state.get('theme', 'Dark')
st.markdown(get_theme_css(theme), unsafe_allow_html=True)

# Prepare colors based on theme
axis_color    = "#000000" if theme == "Light" else "#FFFFFF"
bgcolor       = "rgb(240,240,240)" if theme == "Light" else "rgb(17,17,17)"
anomaly_style = "color:black;"     if theme == "Light" else ""

# ---------------------------
# Title
# ---------------------------
st.markdown("<h1 class='title'>Weather Metrics</h1>", unsafe_allow_html=True)

# ---------------------------
# Fetch Data
# ---------------------------
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None

client = get_influxdb_client()
update_df_from_db(client)

# ---------------------------
# Helpers
# ---------------------------
def get_data_minutes_ago(df, minutes=30):
    cutoff = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    older = df[df['Timestamp'] <= cutoff]
    return older.iloc[-1] if not older.empty else None

def anomaly_count(df, col, minutes):
    cutoff = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    return int(df[df['Timestamp'] >= cutoff][col].sum()) if col in df.columns else 0

def total_and_rate(df, col):
    total = int(df[col].sum()) if col in df.columns else 0
    hours = max((df['Timestamp'].iloc[-1] - df['Timestamp'].iloc[0]).total_seconds()/3600, 1)
    rate = total / hours * 24
    return total, rate

# ---------------------------
# Main
# ---------------------------
if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df.copy()
    df.dropna(subset=['temperature_avg','humidity_avg','pressure_avg'], inplace=True)
    latest = df.iloc[-1]
    past30 = get_data_minutes_ago(df, 30)

    # deltas
    temp_delta = (latest['temperature_avg'] - past30['temperature_avg']) if past30 is not None else None
    hum_delta  = (latest['humidity_avg']    - past30['humidity_avg'])    if past30 is not None else None
    pres_delta = (latest['pressure_avg']    - past30['pressure_avg'])    if past30 is not None else None

    # counts & rates
    cnt2_t, rate_t = total_and_rate(df, 'temperature_anomaly')
    cnt2_h, rate_h = total_and_rate(df, 'humidity_anomaly')
    cnt2_p, rate_p = total_and_rate(df, 'pressure_anomaly')

    # ---------------------------
    # Metric Cards
    # ---------------------------
    col1, col2, col3 = st.columns(3)
    for box, label, col_avg, delta, unit, cnt2, rate in [
        (col1, "Temperature", "temperature_avg", temp_delta, "°C", cnt2_t, rate_t),
        (col2, "Humidity",    "humidity_avg",    hum_delta,    "%",  cnt2_h, rate_h),
        (col3, "Pressure",    "pressure_avg",    pres_delta,   "hPa",cnt2_p, rate_p),
    ]:
        # choose delta class & text
        if delta is None:
            d_cls, d_txt = "metric-delta-neutral", "N/A"
        else:
            d_txt = f"{delta:+.2f} {unit}"
            d_cls = ("metric-delta-positive"
                     if delta>0 else
                     "metric-delta-negative"
                     if delta<0 else
                     "metric-delta-neutral")

        box.markdown(f"""
        <div class="metric-container">
          <div class="metric-label"  style="font-size:1.2em;">{label}</div>
          <div class="metric-value"  style="font-size:2.5em;">{latest[col_avg]:.2f} {unit}</div>
          <div class="{d_cls}"       style="font-size:1.1em;">Change: {d_txt}</div>
          <div style="font-size:1.1em; margin-top:8px; {anomaly_style}">
            <strong>Anomalies (Last 2 hrs):</strong> {cnt2}<br>
            <strong>Anomaly Rate:</strong> {rate:.1f}/day
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ---------------------------
    # Checkbox below cards, aligned right
    # ---------------------------
    st.markdown("---")
    left, right = st.columns([4,1])
    with right:
        show_anoms = st.checkbox("Show anomaly markers", value=True)

    # ---------------------------
    # Individual Graphs
    # ---------------------------
    for title, ycol, color, ancol in [
        ("Temperature Over Time", "temperature_avg", "red",   "temperature_anomaly"),
        ("Humidity Over Time",    "humidity_avg",    "blue",  "humidity_anomaly"),
        ("Pressure Over Time",    "pressure_avg",    "green", "pressure_anomaly"),
    ]:
        st.markdown(f"#### {title}")
        fig = px.line(df, x='Timestamp', y=ycol, color_discrete_sequence=[color])
        fig.update_traces(mode='lines', name=title)

        if show_anoms and ancol in df.columns:
            ev = df[df[ancol]==1]
            if not ev.empty:
                fig.add_scatter(
                    x=ev['Timestamp'],
                    y=ev[ycol],
                    mode='markers',
                    name="Anomaly",
                    marker=dict(color='orange', size=8, symbol='x', opacity=0.7),
                    yaxis="y"
                )

        fig.update_layout(
            xaxis=dict(
                title="Time",
                linecolor=axis_color,
                tickfont=dict(color=axis_color),
                titlefont=dict(color=axis_color),
                showgrid=False,
                tickformat="%H:%M"
            ),
            yaxis=dict(
                title=title.split()[0],
                linecolor=axis_color,
                tickfont=dict(color=axis_color),
                titlefont=dict(color=axis_color),
                showgrid=False
            ),
            plot_bgcolor=bgcolor,
            paper_bgcolor=bgcolor,
            font=dict(color=axis_color),
            margin=dict(l=20, r=20, t=30, b=20),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("No data available yet.")

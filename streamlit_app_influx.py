import pandas as pd 
import streamlit as st
import plotly.graph_objs as go
import time
from streamlit_autorefresh import st_autorefresh
from utils.data_processing_influx import get_influxdb_client, update_df_from_db, get_theme_css
from utils.sidebar import render_sidebar
# --- Silence statsmodels “No supported index” warnings ---
import warnings
from statsmodels.tools.sm_exceptions import ValueWarning
warnings.filterwarnings("ignore", category=ValueWarning)
warnings.filterwarnings("ignore", category=FutureWarning,
                        message="No supported index is available")

# ---------------------------
# Utility Function for Manual Ranges
# ---------------------------
def axis_range(series, padding_ratio=0.1, min_padding=0.5):
    if series.empty:
        return [0, 1]
    vmin, vmax = series.min(), series.max()
    if vmin == vmax:
        return [vmin - 1, vmax + 1]
    span = vmax - vmin
    pad = max(span * padding_ratio, min_padding)
    return [float(vmin - pad), float(vmax + pad)]

# ---------------------------
# Page Config & Sidebar/Theme
# ---------------------------
st.set_page_config(
    page_title="Real-Time Weather Data Dashboard",
    page_icon="🌤️",
    layout="wide"
)
st_autorefresh(interval=30000, key="data_refresh")
render_sidebar()
theme = st.session_state.get("theme", "Dark")
st.markdown(get_theme_css(theme), unsafe_allow_html=True)

# Style checkbox as button‐like toggle
st.markdown("""
<style>
div[data-baseweb="checkbox"] {
    padding: 0.5em 0.75em;
    border: 1px solid #888;
    border-radius: 5px;
    display: inline-flex;
    align-items: center;
    margin-bottom: 1em;
}
div[data-baseweb="checkbox"] label {
    margin: 0;
    padding-left: 0.5em;
    font-weight: bold;
}
div[data-baseweb="checkbox"] input:checked + label {
    background-color: #22c55e;
    color: #fff;
    padding: 0.2em 0.6em;
    border-radius: 3px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Title & Data Fetch
# ---------------------------
st.markdown("<h1 class='title'>Real-Time Weather Data Dashboard</h1>", unsafe_allow_html=True)
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None

client = get_influxdb_client()
update_df_from_db(client)

# ---------------------------
# Helpers
# ---------------------------
def anomaly_count(df, col, minutes):
    if df.empty or col not in df.columns:
        return 0
    cutoff = df["Timestamp"].iloc[-1] - pd.Timedelta(minutes=minutes)
    return int(df[df["Timestamp"] >= cutoff][col].sum())

def total_rate(df, col):
    total = int(df[col].sum())
    span_h = max((df["Timestamp"].iloc[-1] - df["Timestamp"].iloc[0]).total_seconds()/3600, 1)
    rate = total / span_h * 24
    return total, rate

def get_old(df, mins=30):
    cutoff = df["Timestamp"].iloc[-1] - pd.Timedelta(minutes=mins)
    old = df[df["Timestamp"] <= cutoff]
    return old.iloc[-1] if not old.empty else None

# ---------------------------
# Main
# ---------------------------
if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df.copy()
    latest = df.iloc[-1]
    old30 = get_old(df, 30)

    # deltas
    temp_delta = latest["temperature_avg"] - old30["temperature_avg"] if old30 is not None else None
    hum_delta  = latest["humidity_avg"]    - old30["humidity_avg"]    if old30 is not None else None
    pres_delta = latest["pressure_avg"]    - old30["pressure_avg"]    if old30 is not None else None

    # build metric containers
    col1, col2, col3 = st.columns(3)
    for col_box, label, avg_field, delta, anom_col in [
        (col1, "Temperature", "temperature_avg", temp_delta, "temperature_anomaly"),
        (col2, "Humidity",    "humidity_avg",    hum_delta,  "humidity_anomaly"),
        (col3, "Pressure",    "pressure_avg",    pres_delta, "pressure_anomaly"),
    ]:
        cnt2, rate = total_rate(df, anom_col)
        # choose black in Light mode, white in Dark
        cnt_color = "black" if theme == "Light" else "white"

        unit = "°C" if label=="Temperature" else "%" if label=="Humidity" else "hPa"
        d_str = f"{delta:+.2f} {unit}" if delta is not None else "N/A"
        d_class = (
            "metric-delta-positive" if delta and delta>0 else
            "metric-delta-negative" if delta and delta<0 else
            "metric-delta-neutral"
        )

        col_box.markdown(f"""
        <div class="metric-container">
          <div class="metric-label" style="font-size:1.6em;">{label}</div>
          <div class="metric-value" style="font-size:2.8em;">{latest[avg_field]:.2f} {unit}</div>
          <div class="{d_class}" style="font-size:1.4em;">Change: {d_str}</div>
          <div style="font-size:1.0em; margin-top:8px; color:{cnt_color};">
            <strong>Anomalies (Last 2 hrs):</strong> {cnt2}&nbsp;&nbsp;
            <strong>Rate:</strong> {rate:.1f}/day
          </div>
        </div>
        """, unsafe_allow_html=True)

    # ——— Extra vertical space before the graph title ———
    st.markdown("<br><br>", unsafe_allow_html=True)

    # plot + toggle
    plot_col, toggle_col = st.columns([6,2])
    with plot_col:
        st.subheader("Temperature, Humidity & Pressure Over Time")
    with toggle_col:
        show_anoms = st.checkbox("Show anomaly markers", value=True)

    plot_bg = "rgb(240,240,240)" if theme=="Light" else "rgb(17,17,17)"
    font_c  = "black" if theme=="Light" else "white"

    fig = go.Figure([
        go.Scatter(x=df["Timestamp"], y=df["temperature_avg"], mode="lines",
                   name="Temperature (°C)", line=dict(color="red"), yaxis="y1"),
        go.Scatter(x=df["Timestamp"], y=df["humidity_avg"], mode="lines",
                   name="Humidity (%)",    line=dict(color="blue"), yaxis="y2"),
        go.Scatter(x=df["Timestamp"], y=df["pressure_avg"], mode="lines",
                   name="Pressure (hPa)",  line=dict(color="green"), yaxis="y3"),
    ])

    if show_anoms:
        for col_field, color, yax, name in [
            ("temperature_anomaly","orange","y1","Temp Anomaly"),
            ("humidity_anomaly",   "orange","y2","Humidity Anomaly"),
            ("pressure_anomaly",   "orange","y3","Pressure Anomaly"),
        ]:
            an = df[df[col_field]==1]
            if not an.empty:
                fig.add_trace(go.Scatter(
                    x=an["Timestamp"],
                    y=an[col_field.replace("_anomaly","_avg")],
                    mode="markers",
                    name=name,
                    marker=dict(color=color, size=10, symbol="x", opacity=0.6),
                    yaxis=yax,
                    hovertemplate="Time: %{x}<br>Value: %{y:.2f}<extra></extra>"
                ))

    fig.update_layout(
        xaxis=dict(domain=[0.1,0.9], title="Time",
                   tickfont=dict(color=font_c), titlefont=dict(color=font_c)),
        yaxis=dict(title="Temp (°C)",    titlefont=dict(color="red"),
                   tickfont=dict(color="red"), anchor="free",
                   position=0.05, range=axis_range(df["temperature_avg"])),
        yaxis2=dict(title="Humidity (%)", titlefont=dict(color="blue"),
                    tickfont=dict(color="blue"), overlaying="y",
                    side="left", position=0, range=axis_range(df["humidity_avg"])),
        yaxis3=dict(title="Pressure (hPa)",titlefont=dict(color="green"),
                    tickfont=dict(color="green"), overlaying="y",
                    side="right",position=0.95,range=axis_range(df["pressure_avg"])),
        plot_bgcolor=plot_bg, paper_bgcolor=plot_bg,
        legend=dict(x=0, y=1.1, orientation="h", font=dict(color=font_c)),
        font=dict(color=font_c),
        margin=dict(l=40, r=40, t=40, b=40)
    )

    st.plotly_chart(fig, use_container_width=True)
    st.write(f"**Last Updated:** {latest['Timestamp']}")
    st.markdown(
        "<div style='text-align:center;color:gray;'>Data is updated in real-time from the sensors.</div>",
        unsafe_allow_html=True
    )

else:
    st.warning("No data available yet.")

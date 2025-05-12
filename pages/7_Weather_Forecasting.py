import streamlit as st
import pandas as pd
import plotly.graph_objs as go
from streamlit_autorefresh import st_autorefresh
from datetime import timedelta

from utils.data_processing_influx import (
    get_influxdb_client,
    fetch_recent_for_forecast,
    generate_forecast,
    get_theme_css,
)
from utils.sidebar import render_sidebar


# ────────────────────────────────────────────────────────────────
# Config & theme
# ────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Predictive Modelling", page_icon="📈", layout="wide")
st_autorefresh(interval=30_000, key="forecast_refresh")  # refresh every 30 s

render_sidebar()
theme = st.session_state.get("theme", "Dark")
st.markdown(get_theme_css(theme), unsafe_allow_html=True)

axis_c   = "#000000" if theme == "Light" else "#FFFFFF"
bg_color = "rgb(240,240,240)" if theme == "Light" else "rgb(17,17,17)"

# ────────────────────────────────────────────────────────────────
# User controls
# ────────────────────────────────────────────────────────────────
st.markdown("<h1 class='title'>Short-Term Weather Forecast</h1>", unsafe_allow_html=True)
horizon_choice = st.radio("Forecast Horizon", ["15 min", "30 min"], horizontal=True)
steps   = 30 if horizon_choice == "15 min" else 60          # 30 s per step
history_hours = 2                                           # show last 2 h

# numeric minutes for text
horizon_minutes = 15 if horizon_choice.startswith("15") else 30

# ────────────────────────────────────────────────────────────────
# Data fetch & forecast
# ────────────────────────────────────────────────────────────────
client    = get_influxdb_client()
recent_df = fetch_recent_for_forecast(client, hours=history_hours)

if recent_df.empty:
    st.warning("No data available yet — sensors haven’t written to the database.")
    st.stop()

fc_df = generate_forecast(recent_df, horizon_steps=steps)
if fc_df is None:
    st.warning("Forecast couldn’t be generated (models missing).")
    st.stop()

latest = recent_df.iloc[-1]

# ────────────────────────────────────────────────────────────────
# Helper: build metric card + chart for one variable
# ────────────────────────────────────────────────────────────────
def render_block(label, col_name, fc_col, color, unit):
    cur   = latest[col_name]
    pred  = fc_df[fc_col].iloc[-1]
    delta = pred - cur
    cls   = ("metric-delta-positive" if delta > 0 else
             "metric-delta-negative" if delta < 0 else
             "metric-delta-neutral")

    # metric card
    st.markdown(f"""
    <div class="metric-container">
      <div class="metric-label"  style="font-size:1.2em;">{label}</div>
      <div class="metric-value"  style="font-size:2.5em;">{cur:.2f} {unit}</div>
      <div class="{cls}"         style="font-size:1.1em;">
        Forecast&nbsp;(after&nbsp;{horizon_minutes}&nbsp;min): {pred:.2f} {unit}<br>
        Change&nbsp;(after&nbsp;{horizon_minutes}&nbsp;min): {delta:+.2f} {unit}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=recent_df["Timestamp"], y=recent_df[col_name],
        mode="lines", name=label, line=dict(color=color)))
    fig.add_trace(go.Scatter(
        x=fc_df["Timestamp"], y=fc_df[fc_col],
        mode="lines", name=f"{label} Forecast",
        line=dict(color=color, dash="dash")))

    # Now marker
    now_dt = latest["Timestamp"].to_pydatetime()
    fig.add_shape(type="line", x0=now_dt, x1=now_dt, y0=0, y1=1,
                  xref="x", yref="paper",
                  line=dict(color="gray", width=1, dash="dot"))
    fig.add_annotation(x=now_dt, y=1, yref="paper", showarrow=False,
                       text="Now", xanchor="left",
                       font=dict(color=axis_c))

    # y-range helper
    rng = pd.concat([recent_df[col_name], fc_df[fc_col]])
    pad = 0.1 * max(rng.max() - rng.min(), 1e-6)
    yrange = [rng.min() - pad, rng.max() + pad]

    fig.update_layout(
        xaxis=dict(title="Time", tickfont=dict(color=axis_c),
                   titlefont=dict(color=axis_c)),
        yaxis=dict(title=f"{label} ({unit})", titlefont=dict(color=color),
                   tickfont=dict(color=color), range=yrange),
        plot_bgcolor=bg_color, paper_bgcolor=bg_color,
        font=dict(color=axis_c),
        legend=dict(orientation="h", yanchor="bottom",
                    y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=10, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)


# ────────────────────────────────────────────────────────────────
# Render three blocks
# ────────────────────────────────────────────────────────────────
render_block("Temperature", "temperature_avg", "temperature_fc", "red", "°C")
st.markdown("---")
render_block("Humidity",    "humidity_avg",    "humidity_fc",    "blue", "%")
st.markdown("---")
render_block("Pressure",    "pressure_avg",    "pressure_fc",    "green", "hPa")

# footer
st.write(f"**Last Updated:** {latest['Timestamp']}")
st.caption("Models: ARIMA (2,1,2) for Temp/Pressure · ARIMA (2,0,2) for Humidity")

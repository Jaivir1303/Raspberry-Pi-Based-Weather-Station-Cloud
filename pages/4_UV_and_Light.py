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

# ---------------------------
# Page Config & Auto-Refresh
# ---------------------------
st.set_page_config(
    page_title="UV and Light",
    page_icon="☀️",
    layout="wide",
)
st_autorefresh(interval=30000, key="uv_light_refresh")  # refresh every 30s now

render_sidebar()
theme = st.session_state.get("theme", "Dark")
st.markdown(get_theme_css(theme), unsafe_allow_html=True)

# Style the checkbox like a button
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
.event-summary {
    font-size: 0.85em;
    margin-top: 0.3em;
    opacity: 0.9;
    color: inherit;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# Title & Data Fetch
# ---------------------------
st.markdown("<h1 class='title'>UV and Light</h1>", unsafe_allow_html=True)
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None

client = get_influxdb_client()
update_df_from_db(client)

# ---------------------------
# Helper: count recent events & get durations
# ---------------------------
def count_recent(df, col, minutes=30):
    if df.empty or col not in df.columns:
        return 0
    cutoff = df['Timestamp'].iloc[-1] - pd.Timedelta(minutes=minutes)
    return int(df[df['Timestamp'] >= cutoff][col].sum())

def get_event_stats(df, column, threshold):
    if df.empty or column not in df.columns:
        return {"durations": [], "last_time": None}
    
    # Create a mask for the condition (e.g., light on, sunlight exposure)
    mask = df[column] >= threshold
    
    # Find when state changes (on->off or off->on)
    state_changes = mask != mask.shift(1)
    runs = state_changes.cumsum()
    
    durations = []
    last_time = None
    
    # Group by runs to find contiguous periods
    for _, grp in df.groupby(runs):
        if grp[column].iloc[0] >= threshold:  # Only consider "on" periods
            start_time = grp['Timestamp'].iloc[0]
            end_time = grp['Timestamp'].iloc[-1]
            duration_mins = (end_time - start_time).total_seconds() / 60
            durations.append({"start": start_time, "end": end_time, "duration": duration_mins})
    
    # Get today's events - make sure to use timezone-aware or both naive
    if durations:
        # Get timezone-naive representation of today's start
        today = pd.Timestamp.now().floor('D')
        
        # If our timestamps are timezone-aware, make today timezone-aware too
        if durations[0]["start"].tzinfo is not None:
            today = today.tz_localize(durations[0]["start"].tzinfo)
            
        today_events = [d for d in durations if d["start"] >= today]
    else:
        today_events = []
    
    # Find the last event time
    if today_events:
        last_time = today_events[-1]["end"]
    
    return {"durations": today_events, "last_time": last_time}

# ---------------------------
# Main
# ---------------------------
if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df.copy()
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Rename for simplicity
    rename_map = {
        'uv_data_avg': 'uv_data',
        'ambient_light_avg': 'ambient_light',
        'uv_data_anomaly': 'uv_anomaly',
        'ambient_light_anomaly': 'light_anomaly'
    }
    df.rename(columns=rename_map, inplace=True)

    # Clean & derive
    df = df.dropna(subset=['uv_data','ambient_light'])
    df['UV_Index'] = df['uv_data'].apply(calculate_uv_index)
    latest = df.iloc[-1]

    # Get event statistics - ensure we're using the same threshold for both UV graph and metrics
    light_stats = get_event_stats(df, 'ambient_light', 20)
    
    # IMPORTANT: Use the same threshold (0.85) for UV metrics as used in the graph bands
    sun_stats = get_event_stats(df, 'uv_smooth', 0.85)  
    
    # If we don't have uv_smooth in the main dataframe yet, calculate it
    if 'uv_smooth' not in df.columns:
        df['uv_smooth'] = (
            df['uv_data']
               .rolling(window=21, center=True, min_periods=1)
               .median()
        )
        sun_stats = get_event_stats(df, 'uv_smooth', 0.85)
    
    # Format durations for display with safer default values
    light_duration = sum(e["duration"] for e in light_stats["durations"]) if light_stats["durations"] else 0
    sun_duration = sum(e["duration"] for e in sun_stats["durations"]) if sun_stats["durations"] else 0
    
    # Convert durations to hours and minutes format
    def format_duration(minutes):
        hours = int(minutes) // 60
        mins = int(minutes) % 60
        if hours > 0:
            return f"{hours} hours {mins} mins"
        else:
            return f"{mins} mins"
    
    light_duration_formatted = format_duration(light_duration)
    sun_duration_formatted = format_duration(sun_duration)
    shade_duration_formatted = format_duration(24*60 - sun_duration)
    light_off_duration_formatted = format_duration(24*60 - light_duration)
    
    light_count = len(light_stats["durations"])
    sun_count = len(sun_stats["durations"])
    
    # Check for events from today
    today = pd.Timestamp.now().floor('D')
    
    # Get timezone from DataFrame if available
    if not df.empty and hasattr(df['Timestamp'].iloc[0], 'tzinfo') and df['Timestamp'].iloc[0].tzinfo:
        today = today.tz_localize(df['Timestamp'].iloc[0].tzinfo)
    
    # For the last time of UV events, use the same detection logic as the graph
    last_sun_time = sun_stats["last_time"].strftime("%H:%M") if sun_stats["last_time"] else "N/A"
    last_light_time = light_stats["last_time"].strftime("%H:%M") if light_stats["last_time"] else "N/A"

    uv_cat = uv_description(latest['UV_Index'])
    def uv_color(i):
        if i>=11: return "#FF0000"
        if i>=8:  return "#FF4500"
        if i>=6:  return "#FFA500"
        if i>=3:  return "#FFFF00"
        return "#00FF00"
    cat_color = uv_color(latest['UV_Index'])

    # Layout - metrics row first, without toggle
    st.subheader("Current UV Index and Ambient Light")
    
    # Metrics row with updated info
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""
          <div class="metric-container">
            <div class="metric-label">UV Index</div>
            <div class="metric-value">{latest['UV_Index']:.2f}</div>
            <div class="metric-category" style="color:{cat_color};">{uv_cat}</div>
            <div class="event-summary">☀️ Sunlight exposure: {sun_duration_formatted} today (last at {last_sun_time})</div>
            <div class="event-summary">🌙 Shade duration: {shade_duration_formatted} today</div>
          </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
          <div class="metric-container">
            <div class="metric-label">Ambient Light</div>
            <div class="metric-value">{latest['ambient_light']:.2f} lux</div>
            <div class="event-summary">🔦 Light on: {light_duration_formatted} today (last at {last_light_time})</div>
            <div class="event-summary">🌑 Light off: {light_off_duration_formatted} today</div>
          </div>
        """, unsafe_allow_html=True)
        
    # Time‐range slider
    mn, mx = df['Timestamp'].min(), df['Timestamp'].max()
    start, end = st.slider(
        "Select Time Range",
        min_value=mn.to_pydatetime(),
        max_value=mx.to_pydatetime(),
        value=(mn.to_pydatetime(), mx.to_pydatetime()),
        format="YYYY-MM-DD HH:mm"
    )
    
    # Place toggle after slider, aligned to the right
    col1, col2 = st.columns([3, 1])
    with col2:
        show_events = st.checkbox("Show event overlays", value=True)
    
    mask = (df['Timestamp'] >= start) & (df['Timestamp'] <= end)
    dff = df.loc[mask]

    # Prepare shading intervals and markers if asked
    uv_bands = []
    light_bands = []
    uv_markers = []
    light_markers = []
    
    if show_events and not dff.empty:
        # UV smoothing & mask
        dff['uv_smooth'] = (
            dff['uv_data']
               .rolling(window=21, center=True, min_periods=1)
               .median()
        )
        uv_mask = dff['uv_smooth'] >= 0.85
        # find contiguous runs
        runs = (uv_mask != uv_mask.shift(1)).cumsum()
        for _, grp in dff.groupby(runs):
            if grp['uv_smooth'].iloc[0] >= 0.85:
                uv_bands.append({
                  "type":"rect",
                  "xref":"x","yref":"paper",
                  "x0":grp['Timestamp'].iloc[0],
                  "x1":grp['Timestamp'].iloc[-1],
                  "y0":0,"y1":1,
                  "fillcolor":"rgba(255,165,0,0.2)",
                  "line_width":0
                })
                # Add start marker (sun symbol)
                uv_markers.append({
                    "x": grp['Timestamp'].iloc[0],
                    "y": grp['UV_Index'].iloc[0],
                    "text": "☀️",
                    "showarrow": False,
                    "font": {"size": 16}
                })
                # Add end marker (moon symbol)
                uv_markers.append({
                    "x": grp['Timestamp'].iloc[-1],
                    "y": grp['UV_Index'].iloc[-1],
                    "text": "🌙",
                    "showarrow": False,
                    "font": {"size": 16}
                })

        # Ambient light mask
        light_mask = dff['ambient_light'] >= 20
        runs2 = (light_mask != light_mask.shift(1)).cumsum()
        for _, grp in dff.groupby(runs2):
            if grp['ambient_light'].iloc[0] >= 20:
                light_bands.append({
                  "type":"rect",
                  "xref":"x","yref":"paper",
                  "x0":grp['Timestamp'].iloc[0],
                  "x1":grp['Timestamp'].iloc[-1],
                  "y0":0,"y1":1,
                  "fillcolor":"rgba(0,255,255,0.15)",
                  "line_width":0
                })
                # Add start marker (torch/light on)
                light_markers.append({
                    "x": grp['Timestamp'].iloc[0],
                    "y": grp['ambient_light'].iloc[0],
                    "text": "🔦",
                    "showarrow": False,
                    "font": {"size": 16}
                })
                # Add end marker (light off)
                light_markers.append({
                    "x": grp['Timestamp'].iloc[-1],
                    "y": grp['ambient_light'].iloc[-1],
                    "text": "🌑",
                    "showarrow": False,
                    "font": {"size": 16}
                })

    # Draw UV chart
    import plotly.express as px
    import plotly.graph_objects as go
    plot_bg = "rgb(240,240,240)" if theme=="Light" else "rgb(17,17,17)"
    font_c  = "black" if theme=="Light" else "white"
    axis_c  = "#000" if theme=="Light" else "#FFF"

    st.subheader("UV Index Over Time")
    if dff.empty:
        st.warning("No data in that range.")
    else:
        fig_uv = px.line(dff, x='Timestamp', y='UV_Index', color_discrete_sequence=['#FFA500'])
        fig_uv.update_traces(mode='lines', name='UV Index')
        
        # Add custom legend entries for markers
        if show_events:
            fig_uv.update_layout(shapes=uv_bands)
            fig_uv.update_layout(annotations=uv_markers)
            
            # Add legend for UV markers
            fig_uv.add_trace(go.Scatter(
                x=[None], y=[None],
                mode='markers',
                marker=dict(size=10, color='rgba(0,0,0,0)'),
                name='☀️ Sunlight begins',
                showlegend=True
            ))
            fig_uv.add_trace(go.Scatter(
                x=[None], y=[None],
                mode='markers',
                marker=dict(size=10, color='rgba(0,0,0,0)'),
                name='🌙 Sunlight ends',
                showlegend=True
            ))
        
        fig_uv.update_layout(
            xaxis_title='Time',
            yaxis_title='UV Index',
            plot_bgcolor=plot_bg, paper_bgcolor=plot_bg,
            font=dict(color=font_c),
            xaxis=dict(tickformat='%H:%M', linecolor=axis_c, tickfont=dict(color=font_c)),
            yaxis=dict(linecolor=axis_c, tickfont=dict(color=font_c)),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_uv, use_container_width=True)

    # Draw Ambient Light chart
    st.subheader("Ambient Light Over Time")
    if dff.empty:
        st.warning("No data in that range.")
    else:
        fig_l = px.line(dff, x='Timestamp', y='ambient_light', color_discrete_sequence=['#00FFFF'])
        fig_l.update_traces(mode='lines', name='Ambient Light')
        
        if show_events:
            fig_l.update_layout(shapes=light_bands)
            fig_l.update_layout(annotations=light_markers)
            
            # Add legend for light markers
            fig_l.add_trace(go.Scatter(
                x=[None], y=[None],
                mode='markers',
                marker=dict(size=10, color='rgba(0,0,0,0)'),
                name='🔦 Light turned on',
                showlegend=True
            ))
            fig_l.add_trace(go.Scatter(
                x=[None], y=[None],
                mode='markers',
                marker=dict(size=10, color='rgba(0,0,0,0)'),
                name='🌑 Light turned off',
                showlegend=True
            ))
        
        fig_l.update_layout(
            xaxis_title='Time',
            yaxis_title='Ambient Light (lux)',
            plot_bgcolor=plot_bg, paper_bgcolor=plot_bg,
            font=dict(color=font_c),
            xaxis=dict(tickformat='%H:%M', linecolor=axis_c, tickfont=dict(color=font_c)),
            yaxis=dict(linecolor=axis_c, tickfont=dict(color=font_c)),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_l, use_container_width=True)

    # Health advisory remains unchanged
    st.subheader("Health Advisory")
    uv_val = latest['UV_Index']
    if uv_val >= 11:
        msg = "⚠️ **Extreme UV… avoid sun.**"
    elif uv_val >= 8:
        msg = "🛑 **Very High UV… sunscreen!**"
    elif uv_val >= 6:
        msg = "🔆 **High UV… seek shade.**"
    elif uv_val >= 3:
        msg = "🌞 **Moderate UV… be careful.**"
    else:
        msg = "🌙 **Low UV… have fun!**"
    st.markdown(msg)

else:
    st.warning("No data available yet.")

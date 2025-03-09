import streamlit as st
import pandas as pd
import numpy as np
from utils.data_processing_influx import (
    get_influxdb_client,
    update_df_from_db,
    update_iaq_values,
    get_theme_css
)
from utils.sidebar import render_sidebar
from streamlit_autorefresh import st_autorefresh
import plotly.express as px

# Set page configuration
st.set_page_config(
    page_title="Air Quality",
    page_icon="🌬️",
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

# Title with custom styling
st.markdown("<h1 class='title'>Air Quality</h1>", unsafe_allow_html=True)

# Initialize session state variables if not already done
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None

# InfluxDB client and update DataFrame from DB
client = get_influxdb_client()
update_df_from_db(client)

if st.session_state.data_fetched and not st.session_state.df.empty:
    # Work on a copy of the DataFrame
    df = st.session_state.df.copy()
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    
    # Sort by Timestamp and reset index (to align with our stored IAQ values)
    df = df.sort_values('Timestamp').reset_index(drop=True)
    
    # -------------------------------------------
    # Use Aggregated Columns
    # 'AQI_avg' => gas_resistance
    # 'humidity_avg' => humidity
    # -------------------------------------------
    rename_map = {
        'AQI_avg': 'gas_resistance',
        'humidity_avg': 'humidity'
    }
    # Rename columns only if they exist
    for old_col, new_col in rename_map.items():
        if old_col in df.columns:
            df.rename(columns={old_col: new_col}, inplace=True)
    
    # Ensure required metrics are numeric
    metrics = ['gas_resistance', 'humidity']
    for metric in metrics:
        if metric not in df.columns:
            st.warning(f"Missing expected column '{metric}' in aggregated data.")
            st.stop()
        df[metric] = pd.to_numeric(df[metric], errors='coerce')
    
    # Drop rows with missing values in required metrics
    df = df.dropna(subset=metrics).reset_index(drop=True)
    
    # -------------------------------
    # Update IAQ values only for new rows
    # -------------------------------
    from utils.data_processing_influx import update_iaq_values  # ensure the function is imported
    update_iaq_values(df)
    # Assign the stored IAQ values to the DataFrame (they are in sorted order)
    df['IAQ'] = st.session_state.iaq_values[:len(df)]
    
    # For plotting, use the filtered dataframe (if needed, add further filtering)
    df_clean = df.copy()
    
    # Gas Resistance and IAQ metrics (the gas resistance container uses the last raw value)
    latest_data = df_clean.iloc[-1]
    
    # IAQ Category (visual)
    def get_iaq_category(iaq_value):
        if iaq_value <= 50:
            return "Excellent", "#00FF00"
        elif iaq_value <= 100:
            return "Good", "#7FFF00"
        elif iaq_value <= 150:
            return "Lightly Polluted", "#FFFF00"
        elif iaq_value <= 200:
            return "Moderately Polluted", "#FF7F00"
        elif iaq_value <= 300:
            return "Heavily Polluted", "#FF0000"
        else:
            return "Severely Polluted", "#8B0000"
    
    iaq_category, category_color = get_iaq_category(latest_data['IAQ'])
    
    # Display current IAQ
    st.subheader("Current Indoor Air Quality")
    st.markdown(
        f"""
        <div class="metric-container">
            <div class="metric-label">IAQ</div>
            <div class="metric-value">{latest_data['IAQ']:.2f}</div>
            <div class="metric-category" style="color: {category_color};">{iaq_category}</div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Plot theme settings
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
    
    # IAQ Over Time
    st.subheader("IAQ Over Time")
    min_time = df_clean['Timestamp'].min()
    max_time = df_clean['Timestamp'].max()
    time_range = st.slider(
        'Select Time Range',
        min_value=min_time.to_pydatetime(),
        max_value=max_time.to_pydatetime(),
        value=(min_time.to_pydatetime(), max_time.to_pydatetime()),
        format="YYYY-MM-DD HH:mm"
    )
    mask = (df_clean['Timestamp'] >= time_range[0]) & (df_clean['Timestamp'] <= time_range[1])
    df_filtered = df_clean.loc[mask]
    
    if df_filtered.empty:
        st.warning("No data available for the selected time range.")
    else:
        fig_iaq = px.line(df_filtered, x='Timestamp', y='IAQ', color_discrete_sequence=['cyan'])
        fig_iaq.update_layout(
            xaxis_title='Time',
            yaxis_title='IAQ',
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
                showgrid=False
            )
        )
        st.plotly_chart(fig_iaq, use_container_width=True)
    
    # Gas Resistance Over Time
    st.subheader("Gas Resistance Over Time")
    if df_filtered.empty:
        st.warning("No data available for the selected time range.")
    else:
        fig_gas = px.line(df_filtered, x='Timestamp', y='gas_resistance', color_discrete_sequence=['magenta'])
        fig_gas.update_layout(
            xaxis_title='Time',
            yaxis_title='Gas Resistance (Ω)',
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
                showgrid=False
            )
        )
        st.plotly_chart(fig_gas, use_container_width=True)
    
    # Additional Info
    st.subheader("Understanding IAQ")
    st.markdown("""
    **Indoor Air Quality (IAQ)** is a measure of the air quality within and around buildings 
    as it relates to the health and comfort of building occupants.

    **Categories:**

    - **Excellent (0-50):** Air quality is considered satisfactory, and air pollution poses little or no risk.
    - **Good (51-100):** Air quality is acceptable; however, some pollutants may slightly affect very few hypersensitive individuals.
    - **Lightly Polluted (101-150):** Sensitive individuals may experience health effects. The general public is not likely to be affected.
    - **Moderately Polluted (151-200):** Everyone may begin to experience health effects; sensitive groups may experience more serious health effects.
    - **Heavily Polluted (201-300):** Health warnings of emergency conditions. The entire population is more likely to be affected.
    - **Severely Polluted (301+):** Emergency conditions. The entire population is likely to be affected more seriously.

    **Note:** The IAQ values here are estimations based on aggregated gas resistance and humidity. 
    For more accurate assessments, professional-grade sensors and calibrated algorithms are recommended.
    """)
else:
    st.warning("No data available yet.")


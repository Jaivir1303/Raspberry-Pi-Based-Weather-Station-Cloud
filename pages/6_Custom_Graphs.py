import streamlit as st
import pandas as pd
from utils.data_processing_influx import (
    get_influxdb_client,
    update_df_from_db,
    get_theme_css
)
from utils.sidebar import render_sidebar
import plotly.express as px
from streamlit_autorefresh import st_autorefresh

# Set page configuration
st.set_page_config(
    page_title="Custom Graphs",
    page_icon="📊",
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
st.markdown("<h1 class='title'>Custom Graphs</h1>", unsafe_allow_html=True)

# Initialize session state variables if not already done
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None  # Will default to 1970-01-01 in the function

# Get InfluxDB client
client = get_influxdb_client()

# Add manual refresh button
if st.button("Refresh Data"):
    update_df_from_db(client)

# Ensure data is updated
if not st.session_state.data_fetched:
    update_df_from_db(client)

# Display analysis tools
if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df.copy()
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Define mapping of friendly metric names to aggregated column names
    friendly_to_column = {
        "Time": "Timestamp",
        "Temperature (°C)": "temperature_avg",
        "Humidity (%)": "humidity_avg",
        "Pressure (hPa)": "pressure_avg",
        "Gas Resistance (Ω)": "AQI_avg",
        "UV Index": "uv_data_avg",
        "Ambient Light (lux)": "ambient_light_avg"
    }

    # Ensure data is numeric for the aggregated columns
    # (Skip "Time")
    for friendly, col in friendly_to_column.items():
        if col != "Timestamp":
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Drop rows with NaN values in all metric columns (except Time)
    metrics_cols = [v for k, v in friendly_to_column.items() if v != "Timestamp"]
    df = df.dropna(subset=metrics_cols)

    # Add 'Time' as an option for X-axis (already included in friendly_to_column)
    x_axis_options = list(friendly_to_column.keys())
    # For Y-axis, exclude the metric chosen for X if not "Time"
    # We'll do this after selection

    st.markdown("### Select Metrics and Plot Type")

    col1, col2 = st.columns(2)
    with col1:
        metric_x = st.selectbox('Select X-axis Metric', x_axis_options)
    with col2:
        if metric_x == "Time":
            metrics_y_options = [m for m in friendly_to_column.keys() if m != "Time"]
        else:
            metrics_y_options = [m for m in friendly_to_column.keys() if m not in [metric_x, "Time"]]
        metric_y = st.selectbox('Select Y-axis Metric', metrics_y_options)

    plot_type = st.selectbox('Select Plot Type', ['Line Plot', 'Scatter Plot', 'Bar Chart', 'Correlation Plot'])

    # Time period selection
    min_time = df['Timestamp'].min().to_pydatetime()
    max_time = df['Timestamp'].max().to_pydatetime()
    time_range = st.slider(
        'Select Time Range',
        min_value=min_time,
        max_value=max_time,
        value=(min_time, max_time),
        format="YYYY-MM-DD HH:mm"
    )

    # Filter data based on time range
    mask = (df['Timestamp'] >= time_range[0]) & (df['Timestamp'] <= time_range[1])
    df_filtered = df.loc[mask]

    if df_filtered.empty:
        st.warning("No data available for the selected time range.")
    else:
        st.subheader(f"{plot_type} of {metric_y} vs {metric_x}")

        # Plot theme settings
        if theme == "Light":
            plot_bgcolor = 'rgb(240,240,240)'
            paper_bgcolor = 'rgb(240,240,240)'
            font_color = 'black'
        else:
            plot_bgcolor = 'rgb(17,17,17)'
            paper_bgcolor = 'rgb(17,17,17)'
            font_color = 'white'

        # Set x-axis data and label based on selection
        if metric_x == "Time":
            x_data = df_filtered["Timestamp"]
            x_title = "Time"
        else:
            x_data = df_filtered[friendly_to_column[metric_x]]
            x_title = metric_x

        y_data = df_filtered[friendly_to_column[metric_y]]
        y_title = metric_y

        # Generate the plot based on selected type
        if plot_type == 'Scatter Plot':
            fig = px.scatter(df_filtered, x=x_data, y=y_data)
            fig.update_traces(mode='markers')
        elif plot_type == 'Line Plot':
            fig = px.line(df_filtered, x=x_data, y=y_data)
        elif plot_type == 'Bar Chart':
            fig = px.bar(df_filtered, x=x_data, y=y_data)
        elif plot_type == 'Correlation Plot':
            # For correlation plot, plot a scatter plot with trendline
            fig = px.scatter(df_filtered, x=x_data, y=y_data, trendline="ols")
        else:
            st.error("Invalid plot type selected.")
            fig = None

        if fig:
            fig.update_layout(
                xaxis_title=x_title,
                yaxis_title=y_title,
                plot_bgcolor=plot_bgcolor,
                paper_bgcolor=paper_bgcolor,
                font=dict(color=font_color),
                xaxis=dict(
                    tickfont=dict(color=font_color),
                    titlefont=dict(color=font_color),
                    gridcolor='gray',
                    showgrid=True
                ),
                yaxis=dict(
                    tickfont=dict(color=font_color),
                    titlefont=dict(color=font_color),
                    gridcolor='gray',
                    showgrid=True
                )
            )
            st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No data available yet.")


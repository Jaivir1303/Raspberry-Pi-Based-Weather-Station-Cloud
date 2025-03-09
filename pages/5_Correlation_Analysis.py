import streamlit as st
import pandas as pd
from utils.data_processing_influx import (
    get_influxdb_client,
    update_df_from_db,
    get_theme_css
)
from utils.sidebar import render_sidebar
import plotly.express as px

# Set page configuration
st.set_page_config(
    page_title="Correlation Analysis",
    page_icon="🔍",
    layout="wide",
)

# Render the sidebar
render_sidebar()

# Get the selected theme from session state
theme = st.session_state.get('theme', 'Dark')
css_styles = get_theme_css(theme)
st.markdown(css_styles, unsafe_allow_html=True)

# Title with custom styling
st.markdown("<h1 class='title'>Correlation Analysis</h1>", unsafe_allow_html=True)

# Initialize session state variables if not already done
if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()
    st.session_state.data_fetched = False
    st.session_state.last_fetch_time = None  # Will default to 1970-01-01 in the function

# Get InfluxDB client and update data
client = get_influxdb_client()
update_df_from_db(client)

if st.session_state.data_fetched and not st.session_state.df.empty:
    df = st.session_state.df.copy()
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Internal aggregated column names (from the database)
    # Expected columns: temperature_avg, humidity_avg, pressure_avg, AQI_avg, uv_data_avg, ambient_light_avg
    # We map them to professional names:
    professional_names = {
        'temperature_avg': "Temperature (°C)",
        'humidity_avg': "Relative Humidity (%)",
        'pressure_avg': "Pressure (hPa)",
        'AQI_avg': "Indoor Air Quality Sensor (Gas Resistance, Ω)",
        'uv_data_avg': "UV Sensor (Raw)",
        'ambient_light_avg': "Ambient Light (lux)"
    }

    # Rename the columns if they exist
    for old_col, new_col in professional_names.items():
        if old_col in df.columns:
            df.rename(columns={old_col: new_col}, inplace=True)

    # Define the list of metrics using the professional names
    metrics = list(professional_names.values())

    # Ensure the selected metrics are numeric
    for metric in metrics:
        df[metric] = pd.to_numeric(df[metric], errors='coerce')

    # Drop rows with NaN values in the selected metrics
    df = df.dropna(subset=metrics)

    st.markdown("### Select Metrics for Correlation Analysis")

    # Multiselect for metrics (friendly names)
    selected_metrics = st.multiselect('Select Metrics', metrics, default=metrics)

    if len(selected_metrics) < 2:
        st.warning("Please select at least two metrics for correlation analysis.")
    else:
        # Filter data to selected metrics
        df_selected = df[selected_metrics]

        # Calculate correlation matrix
        corr_matrix = df_selected.corr()

        st.markdown("### Correlation Heatmap")

        # Plot theme settings based on selected theme
        if theme == "Light":
            background_color = '#FFFFFF'
            paper_bgcolor = '#FFFFFF'
            font_color = 'black'
            colorscale = 'Bluered'
        else:
            background_color = '#0E1117'
            paper_bgcolor = '#0E1117'
            font_color = 'white'
            colorscale = 'Bluered'

        # Generate heatmap using Plotly Express
        fig = px.imshow(
            corr_matrix,
            text_auto=True,
            aspect="auto",
            color_continuous_scale=colorscale,
            color_continuous_midpoint=0,
        )

        # Update layout for theme and set tick labels as the selected friendly names
        fig.update_layout(
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(len(selected_metrics))),
                ticktext=selected_metrics,
                side='bottom',
                ticks='outside',
                tickfont=dict(color=font_color),
                titlefont=dict(color=font_color),
                gridcolor='gray',
                showgrid=False,
            ),
            yaxis=dict(
                tickmode='array',
                tickvals=list(range(len(selected_metrics))),
                ticktext=selected_metrics,
                ticks='outside',
                tickfont=dict(color=font_color),
                titlefont=dict(color=font_color),
                gridcolor='gray',
                showgrid=False,
            ),
            plot_bgcolor=background_color,
            paper_bgcolor=paper_bgcolor,
            font=dict(color=font_color),
            margin=dict(l=100, r=100, t=50, b=50),
            coloraxis_colorbar=dict(
                title="Correlation",
                tickfont=dict(color=font_color),
                titlefont=dict(color=font_color),
            ),
        )

        st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("No data available yet.")


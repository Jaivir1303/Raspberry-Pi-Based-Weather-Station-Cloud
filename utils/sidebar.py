# utils/sidebar.py

import streamlit as st
import time

def render_sidebar():
    # Set default theme to 'Dark' if not already set
    if 'theme' not in st.session_state:
        st.session_state['theme'] = 'Dark'

    # CSS Styling
    st.markdown(
        """
        <style>
       /* Sidebar adjustment */
    [data-testid="stSidebar"] {
        min-width: 280px !important;
        max-width: 280px !important;
        width: 280px !important;
        position: fixed !important;
        left: 0;
        top: 0;  /* Adjusted to 0 for proper alignment */
        height: 100%;
        background-color: rgb(14, 17, 23);
        z-index: 1;
        padding-top: 20px;
        box-shadow: 0 0 10px rgba(0, 0, 0, 0.5);
        overflow: hidden;
    }

    /* Adjust Sidebar Content */
    [data-testid="stSidebar"] .css-ng1t4o {  /* Adjusted selector */
        width: 250px !important;
        padding: 20px;
        background-color: rgb(10, 10, 15);
        border-radius: 12px;
        border: 1px solid rgb(70, 70, 70);
        box-sizing: border-box;
        position: relative;
    }

    /* Expand Main Content Width */
    .main .block-container {
        margin-left: 290px !important;  /* Adjust for sidebar width */
        padding-right: 20px;
        padding-top: 30px;
        max-width: calc(100% - 290px) !important;
    }

    /* Sidebar Text Styling */
    .css-ng1t4o h2 {
        font-family: 'Montserrat', sans-serif;
        font-size: 1.3em;
        font-weight: 600;
        color: #ffffff;
        margin-bottom: 12px;
    }

    .css-ng1t4o p {
        font-family: 'Montserrat', sans-serif;
        font-size: 1em;
        color: #c0c0c0;
        margin-bottom: 8px;
    }

    .css-ng1t4o b {
        font-family: 'Montserrat', sans-serif;
        font-weight: 600;
        color: #ffffff;
    }
        </style>
        """,
    unsafe_allow_html=True
    )

    # Sidebar Content
    st.sidebar.markdown(
        f"""
        <div style="padding: 15px; background-color: transparent; border-radius: 10px;">
            <h2>Dashboard Information</h2>
            <p>This dashboard displays real-time weather data.</p>
            <p><b>Data Source</b>: Multiple Sensors</p>
            <p><b>Last Updated</b>: {time.strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Checkbox to toggle wide layout
    wide_layout = st.sidebar.checkbox("Show Wide Layout", key="unique_wide_layout_key")

    # Adjust layout based on checkbox
    if wide_layout:
        st.markdown(
            """
            <style>
            .main .block-container {
                margin-left: 0 !important;
                padding-left: 20px;
                padding-right: 20px;
                max-width: 100% !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            """
            <style>
            .main .block-container {
                margin-left: 290px !important;
                padding-right: 20px;
                max-width: calc(100% - 290px) !important;
            }
            </style>
            """,
            unsafe_allow_html=True
        )
    st.sidebar.title("Navigation")
    st.sidebar.markdown("---")
    


    # Map theme options to indices
    theme_options = ["Dark", "Light"]
    default_index = theme_options.index(st.session_state['theme'])

    # Add a theme toggle
    theme = st.sidebar.selectbox("Select Theme", theme_options, index=default_index)
    st.session_state['theme'] = theme

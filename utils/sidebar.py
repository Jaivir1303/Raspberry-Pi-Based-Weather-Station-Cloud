# utils/sidebar.py
import streamlit as st


def render_sidebar():
    # ------------------------------------------------------------------ #
    # 1 )  Make sure we have a theme in session‑state
    # ------------------------------------------------------------------ #
    if "theme" not in st.session_state:
        st.session_state["theme"] = "Dark"

    # ------------------------------------------------------------------ #
    # 2 )  GLOBAL CSS  ── fixes only for the two issues asked             #
    # ------------------------------------------------------------------ #
    st.markdown(
        """
        <style>
        /* ────────────────────────────────────────────────────────────────
           A. SIDEBAR‑COLLAPSE TOGGLE  (Issue #1)
           Move Streamlit’s built‑in hamburger / chevron button so that it
           sits vertically centred on the sidebar and is never hidden by
           the Streamlit header.
        ──────────────────────────────────────────────────────────────── */
        /* The button carries data‑testids that begin with “baseButton‑header”.
           Target both the open and closed states.                             */
        [data-testid="baseButton-header"] {
            position: absolute !important;          /* relative to sidebar   */
            top: 50%   !important;                  /* centre vertically     */
            left: 100% !important;                  /* just outside sidebar  */
            transform: translate(-50%, -50%) !important;
            z-index: 10000       !important;
            width: 36px          !important;
            height: 36px         !important;
            border-radius: 50%   !important;
            background: rgba(38,39,48,0.92) !important;
            border: 1px solid rgba(255,255,255,0.3) !important;
            display: flex        !important;
            align-items: center  !important;
            justify-content: center !important;
            box-shadow: 0 2px 8px rgba(0,0,0,0.45) !important;
        }

        /* Keep it visible when the sidebar is collapsed */
        section[data-testid="stSidebar"] {
            position: relative !important;
        }

        /* ────────────────────────────────────────────────────────────────
           B. THEME RADIO → BUTTON LOOK & FEEL  (Issue #2)
           Re‑skin the two radio options so they appear as polished buttons
        ──────────────────────────────────────────────────────────────── */
        /* Container: radio inside sidebar should lay out options inline */
        div[data-testid="stSidebar"] div[data-testid="stRadio"] > div {
            display: flex          !important;
            gap: 12px              !important;
            justify-content: center;
            margin: 18px 0 4px 0   !important;
        }

        /* Hide actual <input> circles */
        div[data-testid="stSidebar"] div[data-testid="stRadio"] input {
            display: none;
        }

        /* Base style for both labels (= our buttons) */
        div[data-testid="stSidebar"] div[data-testid="stRadio"] label {
            user-select: none;
            min-width: 88px;
            padding: 9px 22px;
            border-radius: 6px;
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all .15s ease-in-out;
            box-shadow: inset 0 0 0 1px rgba(0,0,0,.18);
        }

        /* Dark‑button */
        div[data-testid="stSidebar"] div[data-testid="stRadio"] > div:nth-child(2) label {
            background: #202124;
            color: #f1f1f1;
            border: 1px solid #3c4043;
        }

        /* Light‑button */
        div[data-testid="stSidebar"] div[data-testid="stRadio"] > div:nth-child(3) label {
            background: #ffffff;
            color: #202124;
            border: 1px solid #d0d0d0;
        }

        /* Hover state */
        div[data-testid="stSidebar"] div[data-testid="stRadio"] label:hover {
            filter: brightness(1.05);
            transform: translateY(-1px);
        }

        /* Checked (active) state */
        div[data-testid="stSidebar"] div[data-testid="stRadio"] input:checked + label {
            box-shadow: 0 0 0 2px #4c8bf5, 0 4px 10px rgba(0,0,0,0.25);
            transform: translateY(-2px);
        }

        /* ────────────────────────────────────────────────────────────────
           C. LIGHT THEME FIX
           When 'Light' is chosen, ensure inner boxes also go light so text
           stays visible.
        ──────────────────────────────────────────────────────────────── */
        body.light [data-testid="stSidebar"]          { background: #f8f8f8 !important; }
        body.light [data-testid="stSidebar"] h2,
        body.light [data-testid="stSidebar"] p,
        body.light [data-testid="stSidebar"] b        { color:#333 !important; }
        body.light [data-testid="stSidebar"] .css-ng1t4o,
        body.light [data-testid="stSidebar"] .css-1d391kg,
        body.light [data-testid="stSidebar"] div.css-1868di4.e1i5pmia4 {
            background: #ffffff !important;
            border: 1px solid #e0e0e0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------------ #
    # 3 )  STANDARD SIDEBAR CONTENT (unchanged functionality)            #
    # ------------------------------------------------------------------ #
    st.sidebar.markdown(
        """
        <div style="padding: 15px; text-align:center;">
            <h2>Dashboard Information</h2>
            <p>This dashboard displays real‑time weather data from multiple sensors.</p>
            <p><b>Data Source</b>: Multiple Sensors</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # radio (styled by CSS above)
    theme_choice = st.sidebar.radio(
        "Select Theme",
        ["Dark", "Light"],
        index=["Dark", "Light"].index(st.session_state["theme"]),
        key="theme_radio",
        horizontal=True,
    )
    st.session_state["theme"] = theme_choice

    # make <body> carry a class “light” when Light is picked
    if theme_choice == "Light":
        st.markdown("<style>body{background:#ffffff;} body{transition:background .2s;} body{}</style>", unsafe_allow_html=True)
        st.markdown("<script>document.body.classList.add('light');</script>", unsafe_allow_html=True)
    else:
        st.markdown("<script>document.body.classList.remove('light');</script>", unsafe_allow_html=True)

    # spacer
    st.sidebar.markdown("<br>", unsafe_allow_html=True)

    # optional wide‑layout switch (as before)
    wide = st.sidebar.checkbox("Show Wide Layout", key="unique_wide_layout_key")
    if wide:
        st.markdown(
            """
            <style>
            .main .block-container{
                margin-left:0!important;max-width:100%!important;
                padding-left:20px;padding-right:20px;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
            .main .block-container{
                margin-left:290px!important;
                max-width:calc(100% - 290px)!important;
                padding-right:20px;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

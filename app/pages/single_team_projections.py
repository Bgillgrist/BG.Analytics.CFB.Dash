import streamlit as st
import pandas as pd
from utils.db import read_df

# Pull game data from Neon and find all unique teams
game_data = read_df("""
    SELECT *
    FROM public.game_data
    WHERE startdate IS NOT NULL
        AND homeclassification IN ('fbs', 'fcs')
        AND awayclassification IN ('fbs', 'fcs')
""")
teams = sorted(
    pd.concat([game_data["hometeam"], game_data["awayteam"]]).dropna().unique()
)

st.markdown(
    """
    <style>
        /* Move ONLY the selectbox upward */
        div[data-testid="stSelectbox"] {
            margin-top: -3rem;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# Centered dropdown
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    selected_team = st.selectbox(
        "",
        options=teams,
        index=None,
        placeholder="Select a team"
    )

# Title
team_label = selected_team if selected_team else ""

st.markdown(
    f"""
    <h1 style='text-align:left; margin-top:-1.5rem; margin-bottom:0.25rem;'>
        Single Team Projections for: {team_label}
    </h1>
    """,
    unsafe_allow_html=True
)
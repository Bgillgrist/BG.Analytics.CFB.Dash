import streamlit as st
import pandas as pd
import numpy as np
from utils.db import read_df

# ----------------------------
# Styling
# ----------------------------
st.markdown(
    """
    <style>
      /* Move ONLY the selectbox upward */
      div[data-testid="stSelectbox"] { margin-top: -3rem; }
    </style>
    """,
    unsafe_allow_html=True
)

# ----------------------------
# Small helpers
# ----------------------------

def get_team_hex(team: str | None) -> str:
    if not team:
        return "#4C78A8"
    df = read_df(
        """
        SELECT "Color1"
        FROM public.team_map
        WHERE cfb_name = :team
        LIMIT 1
        """,
        params={"team": team},
    )
    return df["Color1"].iloc[0] if not df.empty else "#4C78A8"

# ----------------------------
# Data for dropdown
# ----------------------------
game_data = read_df(
    """
    SELECT *
    FROM public.game_data
    WHERE startdate IS NOT NULL
      AND homeclassification IN ('fbs', 'fcs')
      AND awayclassification IN ('fbs', 'fcs')
    """
)
teams = sorted(pd.concat([game_data["hometeam"], game_data["awayteam"]]).dropna().unique())

# ----------------------------
# Header: dropdown + title
# ----------------------------
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    selected_team = st.selectbox("", options=teams, index=None, placeholder="Select a team")

team_hex = get_team_hex(selected_team)
team_label = selected_team or ""

st.markdown(
    f"""
    <h1 style='text-align:left; margin-top:-1.5rem; margin-bottom:0.25rem;'>
      Report Card for: {team_label}
    </h1>
    """,
    unsafe_allow_html=True,
)
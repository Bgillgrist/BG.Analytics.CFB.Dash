import streamlit as st
from utils.db import read_df

st.set_page_config(page_title="CFB Dashboard (Neon)", layout="wide")

st.title("CFB Dashboard (Neon-backed)")
st.caption("If you see data below, your Streamlit app is successfully connected to Neon.")

# 1) Connectivity check
count_df = read_df("SELECT COUNT(*) AS game_rows FROM public.game_data;")
st.metric("Rows in public.game_data", int(count_df.loc[0, "game_rows"]))

# 2) Show a sample
sample = read_df("""
    SELECT startdate, hometeam, awayteam, homepoints, awaypoints
    FROM public.game_data
    ORDER BY startdate DESC
    LIMIT 15;
""")
st.dataframe(sample, use_container_width=True)
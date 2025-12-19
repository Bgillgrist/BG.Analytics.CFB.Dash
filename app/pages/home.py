import streamlit as st
from utils.db import read_df

st.set_page_config(page_title="BG.Analytics CFB Home", layout="wide")

##############################
# Conference finder for filter
conf_sql = """
WITH confs AS (
  SELECT DISTINCT homeconference AS conf
  FROM public.game_data
  WHERE homeconference IS NOT NULL AND homeconference <> ''
  UNION
  SELECT DISTINCT awayconference AS conf
  FROM public.game_data
  WHERE awayconference IS NOT NULL AND awayconference <> ''
)
SELECT conf
FROM confs
ORDER BY conf;
"""
conf_df = read_df(conf_sql)
conferences = conf_df["conf"].tolist() if not conf_df.empty else []

FILTER_OPTIONS = ["All", "FBS", "FCS"] + conferences
##############################

col_left, col_right = st.columns([4, 3])

with col_left:
    st.markdown(
        """
        <div style="font-size:2.2rem; font-weight:800; margin-bottom:0.5rem;">
            What is it?
        </div>
        """,
        unsafe_allow_html=True
    )

    st.write(
        """

        This dashboard was created by Brennan Gillgrist, a sports data scientist 
        who aims to give College Football fans a better way to track their team's 
        performance and projections throughout the season. Within the dashboard you 
        will find a variety of single-team and league-wide analytics so you can 
        remove any personal bias you may have and view both your team and the whole 
        league from a different point of view.

        Make sure to look around and follow me on Instagram 
        **[@BG.Analytics](https://www.instagram.com/bg.analytics/)** for more content!
        """
    )

with col_right:
    st.markdown(
        """
        <div style="font-size:2.2rem; font-weight:800; margin-bottom:0.5rem;">
            Upcoming Games:
        </div>
        """,
        unsafe_allow_html=True
    )

    ##############################
    # Filter and dropdown logic
    selected_filter = st.selectbox(
        "Filter (applies to Upcoming Games)",
        FILTER_OPTIONS,
        index=0,
        label_visibility="collapsed",
    )

    extra_where = ""
    params = {}

    if selected_filter in ("FBS", "FCS"):
        extra_where = """
        AND (
            LOWER(homeclassification) = LOWER(:cls)
            OR LOWER(awayclassification) = LOWER(:cls)
        )
        """
        params["cls"] = selected_filter

    elif selected_filter != "All":
        extra_where = """
          AND (
            homeconference = :conf
            OR awayconference = :conf
          )
        """
        params["conf"] = selected_filter

    sql = f"""
    SELECT
        TO_CHAR(startdate::date, 'MM/DD/YYYY') AS game_date,
        hometeam AS home,
        awayteam AS away
    FROM public.game_data
    WHERE
        (homepoints IS NULL OR awaypoints IS NULL)
        AND startdate::date >= CURRENT_DATE
        {extra_where}
    ORDER BY startdate ASC
    LIMIT 25;
    """
    ##############################

    df = read_df(sql, params=params)

    df = df.rename(columns={"game_date": "Date", "home": "Home", "away": "Away"})
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=385
    )

import streamlit as st
import requests
import pandas as pd
import os
from utils.db import read_df

st.set_page_config(page_title="BG.Analytics CFB Home", layout="wide")

##############################
#Find Secret Variables
def get_secret_or_env(key: str) -> str:
    # Streamlit Cloud
    if key in st.secrets:
        return st.secrets[key]
    # Local terminal env var
    val = os.getenv(key)
    if val:
        return val
    raise RuntimeError(f"Missing {key}. Set it in Streamlit secrets or in your terminal env vars.")

##############################
# Grab Instagram data
@st.cache_data(ttl=3600)
def fetch_ig_insights_30d():

    ig_user_id = get_secret_or_env("IG_USER_ID")
    token = get_secret_or_env("META_PAGE_ACCESS_TOKEN")

    url = f"https://graph.facebook.com/v24.0/{ig_user_id}/insights"
    params = {
        "metric": "follower_count,reach,views,accounts_engaged",
        "period": "day",
        "access_token": token,
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])

    def _series_sum(metric_name: str) -> float:
        metric = next((m for m in data if m.get("name") == metric_name), None)
        if not metric:
            return 0.0
        values = metric.get("values", [])
        # sum last 30 daily values (some tokens return more history)
        return float(sum(v.get("value", 0) for v in values[-30:]))

    def _latest(metric_name: str) -> float:
        metric = next((m for m in data if m.get("name") == metric_name), None)
        if not metric:
            return 0.0
        values = metric.get("values", [])
        if not values:
            return 0.0
        return float(values[-1].get("value", 0))

    followers = int(_latest("follower_count"))         # snapshot-ish
    reach_30d = int(_series_sum("reach"))              # last 30 daily values
    views_30d = int(_series_sum("views"))              # last 30 daily values
    engaged_30d = int(_series_sum("accounts_engaged")) # last 30 daily values

    return followers, reach_30d, views_30d, engaged_30d

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

    # Accolates to build credibility
    st.markdown(
        """
        <div style="font-size:2.2rem; font-weight:800; margin-bottom:0.5rem;">
            Why Trust It?
        </div>
        """,
        unsafe_allow_html=True
    )

    st.write(
        """

        @BG.Analytics has been trusted by over 100 different College Football 
        fan pages to provide game predictions and season-long projections for 
        their teams. We provide College Football analytics to over 1 Million 
        fans every month!

        """
    )

    try:
        followers, reach_30d, views_30d, engaged_30d = fetch_ig_insights_30d()

        st.markdown("#### Live Instagram Stats (Last 30 Days)")
        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Followers", f"{followers:,}")
        c2.metric("Accounts Engaged (30d)", f"{engaged_30d:,}")
        c3.metric("Pages Reached (30d)", f"{reach_30d:,}")
        c4.metric("Views (30d)", f"{views_30d:,}")
        

    except Exception as e:
        st.info("Instagram stats are temporarily unavailable.")
        # Optional: show the error while you're building
        st.caption(f"Debug: {e}")

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

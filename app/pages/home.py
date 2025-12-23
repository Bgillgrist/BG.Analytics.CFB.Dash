import streamlit as st
import requests
import time
import datetime as dt
from utils.db import read_df

IG_USER_ID = st.secrets["IG_USER_ID"]
META_PAGE_ACCESS_TOKEN = st.secrets["META_PAGE_ACCESS_TOKEN"]

st.set_page_config(page_title="BG.Analytics CFB Home", layout="wide")

@st.cache_data(ttl=3600)
def fetch_ig_metrics_30d(ig_user_id: str, token: str) -> tuple[int, int, int, dict]:
    """
    Returns: (accounts_engaged_30d, total_interactions_30d, views_30d, debug_window)
    """
    # Last n days
    until = int(time.time())
    since = until - 30 * 24 * 60 * 60

    url = f"https://graph.facebook.com/v24.0/{ig_user_id}/insights"
    params = {
        "metric": "accounts_engaged,total_interactions,views",
        "metric_type": "total_value",
        "period": "day",
        "since": since,
        "until": until,
        "access_token": token,
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", [])

    def _total(metric_name: str) -> int:
        metric = next((m for m in data if m.get("name") == metric_name), None)
        tv = (metric or {}).get("total_value") or {}
        return int(tv.get("value", 0))

    debug_window = {
        "since_unix": since,
        "until_unix": until,
        "since_readable": dt.datetime.fromtimestamp(since).strftime("%Y-%m-%d %H:%M:%S"),
        "until_readable": dt.datetime.fromtimestamp(until).strftime("%Y-%m-%d %H:%M:%S"),
        "raw_names_returned": [m.get("name") for m in data],
    }

    return _total("accounts_engaged"), _total("total_interactions"), _total("views"), debug_window

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
        accounts_engaged_30d, total_interactions_30d, views_30d, win = fetch_ig_metrics_30d(IG_USER_ID, META_PAGE_ACCESS_TOKEN)

        st.markdown(
            """
            <div style="font-size:1.5rem; font-weight:800; margin-bottom:0.5rem;">
                Instagram Statistcs (Past 30 Days):
            </div>
            """,
            unsafe_allow_html=True
        )
        st.caption(f"Window used: {win['since_readable']} → {win['until_readable']}")
        c1, c2, c3 = st.columns(3)
        c1.metric("Accounts Engaged", f"{accounts_engaged_30d:,}")
        c2.metric("Interactions", f"{total_interactions_30d:,}")
        c3.metric("Views", f"{views_30d:,}")

    except Exception as e:
        st.info("Instagram stats are temporarily unavailable.")

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

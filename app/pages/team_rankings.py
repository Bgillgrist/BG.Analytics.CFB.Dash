import streamlit as st
import pandas as pd
from utils.db import read_df

st.title("Team Rankings", )

# =============================
# Hard-coded personal rankings
# =============================
PERSONAL_TOP25 = [
    (1, "Indiana"), (2, "Miami"), (3, "Oregon"), (4, "Ole Miss"), (5, "Georgia"),
    (6, "Texas Tech"), (7, "Notre Dame"), (8, "Alabama"), (9, "Oklahoma"), (10, "Texas A&M"),
    (11, "BYU"), (12, "Utah"), (13, "Iowa"), (14, "Texas"), (15, "USC"),
    (16, "Vanderbilt"), (17, "Washington"), (18, "James Madison"), (19, "Michigan"), (20, "SMU"),
    (21, "Tulane"), (22, "Illinois"), (23, "TCU"), (24, "North Texas"), (25, "Penn State"),
]
personal_df = pd.DataFrame(PERSONAL_TOP25, columns=["rank", "team"]).sort_values("rank")

# =============================
# Helpers
# =============================

@st.cache_data(ttl=300)
def get_team_map() -> pd.DataFrame:
    """
    team_map columns:
      - cfb_name  (canonical team name)
      - Logo      (image URL)
    """
    return read_df("""
        SELECT
            cfb_name,
            "Logo"
        FROM team_map
    """)

def attach_logo(df: pd.DataFrame, team_col: str) -> pd.DataFrame:
    """
    Joins any dataframe to team_map using cfb_name.
    """
    team_map = get_team_map()

    out = df.merge(
        team_map,
        left_on=team_col,
        right_on="cfb_name",
        how="left"
    )

    out["display_team"] = out[team_col]
    return out

def render_top25_grid(df: pd.DataFrame, title: str):
    """
    Renders a 5x5 grid for Top 25 teams.
    Requires columns: rank, display_team, Logo
    """
    st.subheader(title)

    df = df.sort_values("rank").head(25).copy()

    slots = []
    for r in range(1, 26):
        if (df["rank"] == r).any():
            slots.append(df.loc[df["rank"] == r].iloc[0])
        else:
            slots.append(pd.Series({"rank": r, "display_team": "", "Logo": None}))

    for i in range(0, 25, 5):
        cols = st.columns(5, gap="small")
        for j in range(5):
            item = slots[i + j]
            with cols[j]:
                st.markdown(
                    f"""
                    <div style="
                        border:1px solid rgba(255,255,255,0.12);
                        border-radius:12px;
                        padding:10px;
                        min-height:96px;
                        text-align:center;
                    ">
                        <div style="font-size:12px; opacity:0.7;">#{int(item['rank'])}</div>
                    """,
                    unsafe_allow_html=True,
                )

                if isinstance(item.get("Logo"), str):
                    st.image(item["Logo"], width=48)

                st.markdown(
                    f"<div style='font-weight:600; line-height:1.1;'>{item['display_team']}</div></div>",
                    unsafe_allow_html=True,
                )

# =============================
# Dropdown values
# =============================
rankings_years_df = read_df("""
    SELECT DISTINCT season AS year
    FROM rankings
    ORDER BY year DESC
""")
rankings_years = rankings_years_df["year"].tolist()

POLL_TYPE_MAP = {
    "CFP Rankings": "Playoff Committee Rankings",
    "AP Poll": "AP Top 25",
    "FBS Coaches Poll": "Coaches Poll",
}

rating_models = read_df("""
    SELECT DISTINCT rating_model
    FROM team_ratings
    ORDER BY rating_model
""")["rating_model"].tolist()

# =============================
# Layout
# =============================
topA, topB = st.columns(2, gap="large")

# -------------------------------------------------
# TOP LEFT — Professional Polls (Grid)
# -------------------------------------------------
with topA:
    poll_ui = st.selectbox("Poll", list(POLL_TYPE_MAP.keys()))
    poll = POLL_TYPE_MAP[poll_ui]
    year = st.selectbox("Year", rankings_years)

    weeks = read_df("""
        SELECT DISTINCT week
        FROM rankings
        WHERE poll = :poll AND season = :year
        ORDER BY week
    """, {"poll": poll, "year": year})["week"].tolist()

    week = st.selectbox("Week", weeks, index=len(weeks) - 1)

    prof_df = read_df("""
        SELECT rank, school AS team
        FROM rankings
        WHERE poll = :poll AND season = :year AND week = :week
        ORDER BY rank
    """, {"poll": poll, "year": year, "week": week})

    prof_df = attach_logo(prof_df, "team")

    render_top25_grid(prof_df, "Professional Polls")

# -------------------------------------------------
# TOP RIGHT — Personal Rankings (Grid)
# -------------------------------------------------
with topB:
    pers_df = attach_logo(personal_df, "team")

    render_top25_grid(pers_df, "@BG.Analytics Personal Rankings")

# -------------------------------------------------
# BOTTOM — Statistical Ratings (List)
# -------------------------------------------------
st.markdown("---")
_, center, _ = st.columns([1, 2, 1])

with center:
    st.subheader("Statistical Ratings")

    model = st.selectbox("Rating Model", rating_models)

    asof_dates = read_df("""
        SELECT DISTINCT asof_date
        FROM team_ratings
        WHERE rating_model = :model
        ORDER BY asof_date
    """, {"model": model})["asof_date"].tolist()

    asof = st.selectbox("As-of Date", asof_dates, index=len(asof_dates) - 1)

    stat_raw = read_df("""
        SELECT team, rating_value
        FROM team_ratings
        WHERE rating_model = :model AND asof_date = :asof
    """, {"model": model, "asof": asof})

    stat_raw["rank"] = stat_raw["rating_value"].rank(
        method="first", ascending=False
    ).astype(int)

    stat_df = stat_raw.sort_values("rank")
    stat_df = attach_logo(stat_df, "team")

    st.data_editor(
        stat_df[["rank", "Logo", "display_team", "rating_value"]].head(25)
        .rename(columns={"display_team": "Team", "rating_value": "Rating"}),
        use_container_width=True,
        hide_index=True,
        disabled=True,
        column_config={
            "Logo": st.column_config.ImageColumn("Logo", width="small"),
            "rank": st.column_config.NumberColumn("Rank", width="small"),
            "Team": st.column_config.TextColumn("Team"),
            "Rating": st.column_config.NumberColumn("Rating", format="%.2f"),
        },
    )
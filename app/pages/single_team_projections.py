import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import plotly.graph_objects as go
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
def donut(probability: float, team_color: str) -> go.Figure:
    """Probability expected on 0–1 scale."""
    prob = float(np.clip(probability, 0.0, 1.0))
    percent = round(prob * 100, 1)

    fig = go.Figure(
        data=[
            go.Pie(
                values=[prob, 1 - prob],
                hole=0.5,
                marker_colors=[team_color, "#eee"],
                sort=False,
                direction="clockwise",
                textinfo="none",
            )
        ]
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(t=0, b=0, l=0, r=0),
        width=225,
        height=225,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[
            dict(
                text=f"<b>{percent:.1f}%</b>",
                x=0.5,
                y=0.5,
                font_size=20,
                showarrow=False,
            )
        ],
    )
    return fig


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


def build_win_distribution(team_games: pd.DataFrame, team: str, n_sims: int = 20000) -> pd.DataFrame:
    """Returns dist_df with columns: Wins (str), Probability (float) for 0–13 regular-season wins."""
    tg = team_games.copy()
    tg["startdate"] = pd.to_datetime(tg["startdate"], utc=True)

    season = int(tg["season"].max())
    tg = tg[tg["season"] == season].copy()

    tg["team_points"] = np.where(tg["hometeam"] == team, tg["homepoints"], tg["awaypoints"])
    tg["opp_points"] = np.where(tg["hometeam"] == team, tg["awaypoints"], tg["homepoints"])
    tg["completed"] = tg["team_points"].notna() & tg["opp_points"].notna()
    tg["is_win"] = tg["completed"] & (tg["team_points"] > tg["opp_points"])

    tg_reg = tg[tg["seasontype"].str.lower() == "regular"].copy()
    current_wins = int(tg_reg.loc[tg_reg["completed"], "is_win"].sum())

    remaining = tg_reg[~tg_reg["completed"]].copy()
    probs = remaining["teamwinprob"].fillna(0.5).astype(float).to_numpy()

    if probs.size == 0:
        dist = pd.Series(0.0, index=range(0, 14))
        dist.loc[current_wins] = 1.0
    else:
        sims = (np.random.rand(n_sims, probs.size) < probs).sum(axis=1) + current_wins
        dist = (
            pd.Series(sims)
            .value_counts(normalize=True)
            .reindex(range(0, 14), fill_value=0)
        )

    dist_df = dist.reset_index()
    dist_df.columns = ["Wins", "Probability"]
    dist_df["Wins"] = dist_df["Wins"].astype(int).astype(str)
    return dist_df


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
      Single Team Projections for: {team_label}
    </h1>
    """,
    unsafe_allow_html=True,
)


# ----------------------------
# Main content (only after team selected)
# ----------------------------
if selected_team:
    now = pd.Timestamp.now(tz="UTC")

    # Team games + win probabilities
    team_games = read_df(
        """
        SELECT
            g.*,
            CASE
                WHEN g.hometeam = :team THEN p.homewinprob
                WHEN g.awayteam = :team THEN p.awaywinprob
                ELSE NULL
            END AS teamwinprob
        FROM public.game_data g
        LEFT JOIN public.game_predictions p
          ON p.gameid = g.id::text
        WHERE g.startdate IS NOT NULL
          AND (g.hometeam = :team OR g.awayteam = :team)
          AND g.homeclassification IN ('fbs','fcs')
          AND g.awayclassification IN ('fbs','fcs')
        """,
        params={"team": selected_team},
    )

    team_games["startdate"] = pd.to_datetime(team_games["startdate"], utc=True)

    # Upcoming games
    upcoming_games = team_games[team_games["startdate"] > now].sort_values("startdate")

    # Win distribution (regular season, current season)
    dist_df = build_win_distribution(team_games, selected_team, n_sims=20000)

    # Layout: table + bar chart
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader(f"Upcoming Games for {selected_team}")
        st.dataframe(
            upcoming_games.assign(Date=upcoming_games["startdate"].dt.strftime("%m/%d/%Y"))[
                ["Date", "hometeam", "awayteam"]
            ].rename(columns={"hometeam": "Home Team", "awayteam": "Away Team"}),
            hide_index=True,
            use_container_width=True,
        )

    with right_col:
        st.subheader("Projected Regular-Season Win Distribution")
        chart = (
            alt.Chart(dist_df)
            .mark_bar(color=team_hex)
            .encode(
                x=alt.X("Wins:N", title="Final Regular-Season Wins", sort=[str(i) for i in range(14)]),
                y=alt.Y("Probability:Q", title="Probability"),
                tooltip=["Wins:N", alt.Tooltip("Probability:Q", format=".1%")],
            )
        )
        st.altair_chart(chart, use_container_width=True)

    # Bottom: donuts (placeholders for now)
    pie1col, pie2col, pie3col, pie4col = st.columns(4)

    bowl_prob = float(dist_df.loc[dist_df["Wins"].astype(int) >= 6, "Probability"].sum())

    with pie1col:
        bowl_prob = float(dist_df.loc[dist_df["Wins"].astype(int) >= 6, "Probability"].sum())

        # Create an inner 3-column layout to center content
        _l, mid, _r = st.columns([1, 15, 1])

        with mid:
            st.markdown(
                "<div style='text-align:center; font-size:18px; font-weight:600;'>Bowl Eligibility Odds</div>",
                unsafe_allow_html=True
            )
            st.plotly_chart(
                donut(bowl_prob, team_hex),
                use_container_width=True,     # fill the *mid* column, not the whole pie1col
                config={"displayModeBar": False}
            )

    with pie2col:
        st.markdown(
            "<div style='text-align:center; font-size:18px; font-weight:600;'>Placeholder</div>",
            unsafe_allow_html=True,
        )

    with pie3col:
        st.markdown(
            "<div style='text-align:center; font-size:18px; font-weight:600;'>Placeholder</div>",
            unsafe_allow_html=True,
        )

    with pie4col:
        st.markdown(
            "<div style='text-align:center; font-size:18px; font-weight:600;'>Placeholder</div>",
            unsafe_allow_html=True,
        )
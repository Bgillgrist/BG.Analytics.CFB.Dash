import streamlit as st
import pandas as pd
import numpy as np
from utils.db import read_df
import altair as alt

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

# Get Hex Code of the Team
team_hex_df = read_df(
    """
    SELECT "Color1"
    FROM public.team_map
    WHERE cfb_name = :team
    LIMIT 1
    """,
    params={"team": selected_team}
)

team_hex = team_hex_df["Color1"].iloc[0] if not team_hex_df.empty else "#4C78A8"

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

# Run everything when a team is selected:
now = pd.Timestamp.now(tz="UTC")
if selected_team:

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
        params={"team": selected_team}
    )

    team_games["startdate"] = pd.to_datetime(team_games["startdate"], utc=True)

    upcoming_games = team_games[
        team_games["startdate"] > now
    ].sort_values("startdate")

    # Create two columns for the side by side
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader(f"Upcoming Games for {selected_team}")
        st.dataframe(
            upcoming_games
            .assign(
                Date=pd.to_datetime(upcoming_games["startdate"]).dt.strftime("%m/%d/%Y")
            )[["Date", "hometeam", "awayteam"]]
            .rename(columns={
                "hometeam": "Home Team",
                "awayteam": "Away Team"
            }),
            hide_index=True,
            use_container_width=True
        )

    # Season Simulation Bar Chart

    with right_col:
        st.subheader("Projected Regular-Season Win Distribution")

        tg = team_games.copy()

        tg["startdate"] = pd.to_datetime(tg["startdate"], utc=True)
        season = int(tg["season"].max())
        tg = tg[tg["season"] == season].copy()

        tg["team_points"] = np.where(tg["hometeam"] == selected_team, tg["homepoints"], tg["awaypoints"])
        tg["opp_points"]  = np.where(tg["hometeam"] == selected_team, tg["awaypoints"], tg["homepoints"])
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
            N = 20000
            sims = (np.random.rand(N, probs.size) < probs).sum(axis=1) + current_wins
            dist = (
                pd.Series(sims)
                .value_counts(normalize=True)
                .reindex(range(0, 14), fill_value=0)
            )

        dist_df = dist.reset_index()
        dist_df.columns = ["Wins", "Probability"]
        dist_df["Wins"] = dist_df["Wins"].astype(str)

        chart = (
            alt.Chart(dist_df)
            .mark_bar(color=team_hex)
            .encode(
                x=alt.X("Wins:N", title="Final Regular-Season Wins", sort=[str(i) for i in range(14)]),
                y=alt.Y("Probability:Q", title="Probability")
            )
        )

        st.altair_chart(chart, use_container_width=True)
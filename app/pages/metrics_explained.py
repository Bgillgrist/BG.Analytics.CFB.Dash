import streamlit as st
import textwrap
import pandas as pd
import plotly.graph_objects as go

H1_SIZE = "2.8rem"   # main page header
H2_SIZE = "1.8rem"   # block header inside
BODY_SIZE = "1.15rem"

st.markdown(textwrap.dedent(f"""
<div style="font-size:{H1_SIZE}; font-weight:900; margin-bottom:1rem;">
  1. What are Power Ratings and why do we use them?
</div>

<div style="font-size:2.3rem; font-weight:900; margin-bottom:1rem;">
  The Why:
</div>

<!-- ========================= -->
<!-- GROUP 1 WRAPPER (Blocks 1–2) -->
<!-- ========================= -->
<div style="
  border-left: 10px solid #000000;
  padding-left: 1.25rem;
  margin-bottom: 1.75rem;
">

  <!-- Block 1 -->
  <div style="
    border-left: 4px solid #FC0000;
    padding-left: 1rem;
    margin-bottom: 1.25rem;
    font-size: {BODY_SIZE};
    font-weight: 500;
    line-height: 1.7;
  ">
    <div style="font-size:{H2_SIZE}; font-weight:800; margin-bottom:0.5rem;">
      The Main Idea
    </div>
    Power Ratings are a way to measure how good a team <strong>actually</strong> is,
    not just what the team’s record shows.
    <br><br>
    We know that not all teams with the same record are built the same, so we create Power
    Ratings to put all teams on even ground to accurately compare two teams regardless of
    their conference or situation.
    <br><br>
    To understand how this works, we first need to answer one question:
    <br>
    <em>What does it mean for a team to be “better” than another team?</em>
  </div>

  <!-- Block 2 -->
  <div style="
    border-left: 4px solid #FC7E00;
    padding-left: 1rem;
    margin-bottom: 0.25rem;
    font-size: {BODY_SIZE};
    font-weight: 500;
    line-height: 1.7;
  ">
    <div style="font-size:{H2_SIZE}; font-weight:800; margin-bottom:0.5rem;">
      How do we determine which of two teams is better?
    </div>
    There are many different ways to do this that I hear from people. The main one 
    is usually "Head to Head" results but I think its clear that no one really holds 
    head to head as the standard because we all know that upsets can happen. An FCS team beating 
    a good FBS team obviouly wouldn't mean that they are better.
    <br><br>
    Some people would look to specific stats like average MOV or maybe even a more 
    advanced metric like the BCS Rankings, but these metrics will never 
    contain every piece of information about a team necessary to determine which 
    team is better.
    <br><br>
    So what do we do? Is there a way to determine this? In short, no. No single game 
    result or metric will every be able to truly answer this question. I believe the 
    only way to determine which team is "better" would be to have the two teams play 
    a large number of games (at least 30) on a neutral field and pick the team that wins 
    &gt; 50% of those games. Obviously this will never happen so what do we do? The best way 
    is to create an "estimate".
    <br><br>
    Since the goal is to create power ratings that would correctly predict the team that wins at 
    least 16/30 hypothetical future games, we want to create our power ratings that have the best 
    predictive performance on future outcomes. The first thing that comes to mind are Vegas models 
    however the ratings used in their models are not publicaly available to use. Therefore, we must 
    create our own ratings but how do we do that?
  </div>

</div>  <!-- END GROUP 1 -->

<!-- ========================= -->
<!-- GROUP 2 WRAPPER (Block 3 only) -->
<!-- ========================= -->
<div style="font-size:2.3rem; font-weight:900; margin-bottom:1rem;">
  The What:
</div>

<div style="
  border-left: 10px solid #000000;
  padding-left: 1.25rem;
  margin-bottom: 1.75rem;
">

  <!-- Block 3 -->
  <div style="
    border-left: 4px solid #FCFC00;
    padding-left: 1rem;
    margin-bottom: 0.25rem;
    font-size: {BODY_SIZE};
    font-weight: 500;
    line-height: 1.7;
  ">
    <div style="font-size:{H2_SIZE}; font-weight:800; margin-bottom:0.5rem;">
      What is the Power Rating and how is it formed?
    </div>
    Let's first define the scale of power ratings. Power ratings are centered around 0 (0 being the 
    rating of the most average team in the league). A team above 0 will be better than average 
    and a team below 0 is worse than average.
    <br><br>
    To fully understand the power rating, we must understand it on a play by play basis. Every play, 
    both teams can play at any rating and if the offense plays at a higher rating than the defense 
    then the play is likely an offensive success and the same way around for the defense. Even the 
    worst team in the league can have a great play at a high level and the same for the best team 
    in the league could have a terrible play. After every play is completed and the game is over, 
    one team will have a higher overall "game" rating and this is the team that wins the game. 
    For example: Let's say that Alabama and Auburn just finished a football game. Alabama played 
    the whole game at a high level and their "game" rating was +22 (22 points better than an average 
    team would've done). Meanwhile, Auburn played at a lower level with a rating of +16. This means 
    that the game outcome resulted in Alabama winning by 6 points (the difference between the ratings). 
    These "game" ratings are just one observation in a season long sample of games that we will 
    use to estimate the average rating. As we learned, teams will not play at the same level every 
    single game. Alabama might be +22 vs Auburn but only be +15 vs another team in their schedule. 
    As we watch the entire season play out, we end up with 12 data points of "game" ratings and the 
    true "Power Rating" is usually very close to the average of these game ratings. 
    <br><br>
    Upsets occur when a team with a higher average "Power Rating" plays at a lower level than their 
    opponent and ends up losing the game. Maybe Alabama (+19.2 avearge) had a bad day vs Oklahoma 
    State (+13.5 average) and Alabama only played as a +14 that day while Oklahoma State played up 
    to a +17 and won the game by 3. Does this mean that Oklahoma State is the true better team? Or 
    was the single game rating just high enough to upset Alabama? The question that must be asked every 
    game is: <br><em>Did the team win because they played good, or because their opponent played bad?</em>
    <br><br>
    Power Ratings are constantly updated throughout the season to "Estimate" the true rating of the team 
    by combining many different stats from each game This doesn't guarentee that the higher teams 
    will always beat the lower teams but it does give us an estimate of which team would most likely 
    win &gt; 50% of the 30 hypothetical neutral site matchups. 
  </div>

</div>  <!-- END GROUP 2 -->
"""), unsafe_allow_html=True)

games = pd.DataFrame([
    {"game": 1, "team": "Alabama", "opp": "Florida State",    "team_rating": 11, "opp_rating": 25, "result": "L"},
    {"game": 2, "team": "Alabama", "opp": "UL Monroe", "team_rating": 35, "opp_rating": -38, "result": "W"},
    {"game": 3, "team": "Alabama", "opp": "Wisconsin",   "team_rating": 28, "opp_rating": 4, "result": "W"},
    {"game": 4, "team": "Alabama", "opp": "Georgia",  "team_rating": 18, "opp_rating": 15, "result": "W"},
    {"game": 5, "team": "Alabama", "opp": "Vanderbilt",    "team_rating": 23, "opp_rating": 7, "result": "W"},
    {"game": 6, "team": "Alabama", "opp": "Missouri", "team_rating": 14, "opp_rating": 11, "result": "W"},
    {"game": 7, "team": "Alabama", "opp": "Tennessee",   "team_rating": 27, "opp_rating": 10, "result": "W"},
    {"game": 8, "team": "Alabama", "opp": "South Carolina",  "team_rating": 19, "opp_rating": 12, "result": "W"},
    {"game": 9, "team": "Alabama", "opp": "LSU",    "team_rating": 24, "opp_rating": 13, "result": "W"},
    {"game": 10, "team": "Alabama", "opp": "Oklahoma", "team_rating": 10, "opp_rating": 12, "result": "L"},
    {"game": 11, "team": "Alabama", "opp": "E Illinois",   "team_rating": 27, "opp_rating": -29, "result": "W"},
    {"game": 12, "team": "Alabama", "opp": "Auburn",  "team_rating": 14, "opp_rating": 7, "result": "W"},
])

TEAM_COLOR = "#FC0000"

OPP_COLORS = {
    "Texas": "#1f77b4",
    "Ole Miss": "#0033A0",
    "Auburn": "#0C2340",
    "Georgia": "#BA0C2F",
}

def record_through(game_n: int):
    subset = games[games["game"] <= game_n]
    wins = int((subset["result"] == "W").sum())
    losses = int((subset["result"] == "L").sum())
    avg_rating = float(subset["team_rating"].mean()) if len(subset) else 0.0
    return wins, losses, avg_rating

def build_fig(row):
    y_level = 1
    opp_color = OPP_COLORS.get(row["opp"], "#888888")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=[-40, 40],
        y=[y_level, y_level],
        mode="lines",
        line=dict(width=3),
        hoverinfo="skip",
        showlegend=False
    ))

    fig.add_trace(go.Scatter(
        x=[row["team_rating"]],
        y=[y_level],
        mode="markers+text",
        marker=dict(size=18, color=TEAM_COLOR),
        text=[row["team"]],
        textposition="top center",
        name=row["team"]
    ))

    fig.add_trace(go.Scatter(
        x=[row["opp_rating"]],
        y=[y_level],
        mode="markers+text",
        marker=dict(size=18, color=opp_color),
        text=[row["opp"]],
        textposition="bottom center",
        name=row["opp"]
    ))

    fig.update_yaxes(visible=False, range=[0.5, 1.5])
    fig.update_xaxes(
        title="Game Power Rating (spread-like scale)",
        range=[-40, 40],
        zeroline=True,
        zerolinewidth=2
    )
    fig.update_layout(height=350, margin=dict(l=20, r=20, t=10, b=40))
    return fig

# -----------------------------
# UI
st.markdown("<div style='font-size:2.0rem; font-weight:900;'>Power Ratings: Game-by-Game Visual</div>", unsafe_allow_html=True)

max_game = int(games["game"].max())

if "game_idx" not in st.session_state:
    st.session_state.game_idx = 1

colL, colR = st.columns([2, 1])

with colR:
    st.markdown("### Controls")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("⏮ Start", use_container_width=True):
            st.session_state.game_idx = 1
            st.rerun()
    with c2:
        if st.button("⏭ End", use_container_width=True):
            st.session_state.game_idx = max_game
            st.rerun()

    c3, c4 = st.columns(2)
    with c3:
        if st.button("◀ Prev", use_container_width=True):
            st.session_state.game_idx = max(1, st.session_state.game_idx - 1)
            st.rerun()
    with c4:
        if st.button("Next ▶", use_container_width=True):
            st.session_state.game_idx = min(max_game, st.session_state.game_idx + 1)
            st.rerun()

    st.markdown("---")
    st.session_state.game_idx = st.slider("Game", 1, max_game, st.session_state.game_idx)

with colL:
    # Single render per run (no loops = no duplicate element keys)
    game_n = st.session_state.game_idx
    row = games.loc[games["game"] == game_n].iloc[0]
    wins, losses, avg = record_through(game_n)

    outcome = "wins" if row["result"] == "W" else "loses"

    st.markdown(
        f"""
        <div style="font-size:1.2rem; font-weight:700; margin-top:0.25rem;">
          Game {row['game']}: {row['team']} vs {row['opp']}. {row['team']} {outcome}.
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div style="display:flex; gap:20px; align-items:flex-start; margin-top:10px; margin-bottom:10px;">
          <div style="padding:10px 14px; border:1px solid #ddd; border-radius:12px;">
            <div style="font-size:0.9rem; color:#666;">Record</div>
            <div style="font-size:2.0rem; font-weight:900;">{wins}-{losses}</div>
          </div>
          <div style="padding:10px 14px; border:1px solid #ddd; border-radius:12px;">
            <div style="font-size:0.9rem; color:#666;">Average Rating</div>
            <div style="font-size:2.0rem; font-weight:900;">{avg:.1f}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    fig = build_fig(row)
    st.plotly_chart(fig, use_container_width=True, key="power_rating_stepper_chart")
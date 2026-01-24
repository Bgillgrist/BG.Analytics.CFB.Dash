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
  border-left: 10px solid #777777;
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
  border-left: 10px solid #777777;
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

TEAM_COLOR = "#9e1b32"

def record_through(game_n: int):
    subset = games[games["game"] <= game_n]
    wins = int((subset["result"] == "W").sum())
    losses = int((subset["result"] == "L").sum())
    avg_rating = float(subset["team_rating"].mean()) if len(subset) else 0.0
    return wins, losses, avg_rating

def build_fig(row):
    y_level = 1
    opp_color = "#888888"

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
        title="Game Power Rating",
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

st.markdown(textwrap.dedent(f"""
<div style="font-size:2.3rem; font-weight:900; margin-bottom:1rem;">
  Considerations:
</div>

<!-- ========================= -->
<!-- GROUP 1 WRAPPER (Blocks 1–2) -->
<!-- ========================= -->
<div style="
  border-left: 10px solid #777777;
  padding-left: 1.25rem;
  margin-bottom: 1.75rem;
">

  <!-- Block 1 -->
  <div style="
    border-left: 4px solid #00ff00;
    padding-left: 1rem;
    margin-bottom: 1.25rem;
    font-size: {BODY_SIZE};
    font-weight: 500;
    line-height: 1.7;
  ">
    <div style="font-size:{H2_SIZE}; font-weight:800; margin-bottom:0.5rem;">
      The "Game Rating" Question
    </div>
    The visual above is helpful for seeing how a team wins a game, however it is important to note 
    that it is not always visually apparent to the viewer what level the two teams were playing at. 
    A game ending 27-24 in FBS is not at the same end of the spectrum as a game ending 27-24 in FCS. 
    Therefore, in every game we don't always know if team A beat team B because team A played at a high 
    level, or of team B played at a low level. Furthermore, just because a team wins a game doesn't 
    mean they played good and just because a team loses a game doesn't mean they played bad. Sometimes 
    the other team was just better or worse. Creating models and comparing outcomes between teams on 
    different levels (conference, division, ect.) allows us to figure out where on the scale specific 
    games lie and thus helps us find where the team lies overall for the season.
  </div>

  <!-- Block 2 -->
  <div style="
    border-left: 4px solid #0000ff;
    padding-left: 1rem;
    margin-bottom: 0.25rem;
    font-size: {BODY_SIZE};
    font-weight: 500;
    line-height: 1.7;
  ">
    <div style="font-size:{H2_SIZE}; font-weight:800; margin-bottom:0.5rem;">
      Sample Size
    </div>
    The biggest issue with this method is the lack of data. Even by the end of the season, 12 games 
    is hardly enought to conclude exactly where a team should lie on the power ratings scale. This 
    may not be intuitive but imagine you are shooting free throws. The goal is for you to determine 
    what your true FT% is. If you shot 12 free throws and made all 12 of them, would you then conclude 
    that you shoot at 100% FT%? Obviously not. 12 is a laughably low sample size and the same is true 
    for CFB games. Since we never get to play out a large number of games, we must use a few other methods 
    to try to make up for the lack of data.
    <br><br>
    Method 1: Scale all power ratings back toward some overall average. Let's say Ohio State just finished 
    5 games and they beat every opponent (who were all average teams) by 70 points. Is it reasonable 
    to conclude that Ohio State is better than the average team by over 70 points? Possible, but 
    unlikely. We can scale back Ohio State's rating a bit to the Big 10 average rating to make it 
    more realistic until more games are completed. As the season progresses, the weight of the conference 
    average slowly has less importance as we learn more about the team.
    <br><br>
    Method 2: Using Preseason and Historical data. While everyone complains about the presence of 
    preseason information in power ratings, preseason + historical data provide valuable information 
    in predicting the outcomes of future games and while there are always outliers, on average we find 
    it more useful to include this data than to exclude it. Teams with many 5 star recruits, highly rated 
    transfers, and elite returning production will often perform better than their counterparts who 
    are missing the elite talent. While not a rule (2025 Indiana), we do find that these teams often 
    perform at a higher caliper than teams missing these players. By slowly decreasing the importance 
    of this preseason data throughout the season, we can create a power rating model that updates throughout 
    the season as more data comes in and predicts the outcomes of future games at a high rate.<br>
    <em>See below another visual that displays how preseason and current season data combine together 
    to create a more accurate power ratings model:</em>
  </div>

</div>
"""), unsafe_allow_html=True)
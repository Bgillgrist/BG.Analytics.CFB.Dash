"""On-demand betting edge analysis."""
import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from utils import betting
    from cfb_betting.domain import MODELS, TIERS, recommendations, utc
except ModuleNotFoundError:
    st.error("Install the dashboard requirements, including the bundled betting package, to use this page.")
    st.stop()

NAVY = "#0C2C56"
st.markdown('<div style="color:#64748b;font-size:.8rem;letter-spacing:.12em">BETTING / CURRENT ANALYSIS</div>', unsafe_allow_html=True)
st.title("Best Bets")
st.caption("Compare every available side and sportsbook. Edge classifications describe model estimates; history shows how they perform.")

try:
    seasons = betting.load_seasons()
except Exception:
    st.error("Betting data could not be loaded. Check the database connection and try again.")
    st.stop()
if seasons.empty:
    st.info("No FBS-vs-FBS games are available.")
    st.stop()

season = st.selectbox("Season", seasons.season.astype(int).tolist())
try:
    data = betting.load_data(season)
    refresh_ready = betting.can_refresh()
except Exception:
    st.error("Saved betting analysis could not be loaded. Check the database connection and try again.")
    st.stop()

left, right, reload = st.columns([1,1,2])
train_clicked = left.button("Run analysis", type="primary", disabled=not refresh_ready, width="stretch")
refresh_clicked = right.button("Refresh odds", disabled=not refresh_ready, width="stretch")
if reload.button("Reload saved results"):
    betting.load_data.clear()
    st.rerun()
if not refresh_ready:
    st.info("Set CFBD_API_KEY in Streamlit secrets to enable analysis and odds refresh. Saved results remain available.")
st.caption("Run analysis trains and tests all four models. Refresh odds reuses saved models. Filters never start training; updates happen only when requested.")

if train_clicked or refresh_clicked:
    with st.status("Training and classifying bets…" if train_clicked else "Refreshing quotes…", expanded=True) as status:
        progress_line = st.empty()
        try:
            result = betting.execute(season, retrain=train_clicked, progress=progress_line.write)
        except ValueError as error:
            status.update(label="Analysis could not be completed", state="error")
            st.error(str(error))
        except Exception:
            status.update(label="Analysis did not complete", state="error")
            st.error("The run failed. Your last successful results are preserved. Check CFBD access and the database, then retry.")
        else:
            status.update(label=f"Saved {result['classifications']:,} classifications across {result['games']:,} games", state="complete")
            data = betting.load_data(season)

runs = data["runs"]
success = runs.loc[runs.status.eq("success")] if not runs.empty else runs
if not success.empty:
    latest = success.iloc[-1]
    st.caption(f"Latest successful run: {pd.Timestamp(latest.completed_at).tz_convert('America/New_York'):%b %d, %Y at %I:%M %p %Z} · "
               f"Models trained: {pd.Timestamp(latest.trained_at).tz_convert('America/New_York'):%b %d, %Y at %I:%M %p %Z}")
if not runs.empty and runs.iloc[-1].status == "failed":
    st.warning("The most recent attempt failed. The tables below use the last successful saved results.")
if not data["scopes"].empty and "quote_issues" in data["scopes"]:
    latest_scopes = data["scopes"].sort_values(["as_of", "completed_at"]).drop_duplicates("game_id", keep="last")
    quote_issues = [issue for issues in latest_scopes.quote_issues for issue in (issues or [])]
    if quote_issues:
        with st.expander(f"{len(quote_issues)} ambiguous sportsbook markets excluded"):
            st.dataframe(pd.DataFrame(quote_issues), hide_index=True, width="stretch")
            st.caption("CFBD supplied conflicting quotes for the same sportsbook and market. Both sides are unavailable for that book; verified quotes from other books remain eligible.")

candidates = betting.current_candidates(data)
if candidates.empty:
    st.info("No classified upcoming bets are saved. Run analysis to create them; games without usable odds or predictions remain unavailable.")
else:
    one, two, three = st.columns([2,1,1])
    model = one.selectbox("Model", list(MODELS), index=1, format_func=MODELS.get)
    market = two.selectbox("Market", ["All", "Spread", "Moneyline"])
    top_n = three.selectbox("Show", [10, 5, 20, 50, "All"], format_func=lambda value: f"Top {value}" if isinstance(value,int) else "All results")
    one, two, three = st.columns(3)
    providers = one.multiselect("Sportsbooks", sorted(candidates.provider.unique()))
    conferences = two.multiselect("Conferences", sorted(candidates.conference.dropna().unique()))
    teams = three.multiselect("Teams", sorted(set(candidates.team) | set(candidates.opponent)))
    one, two, three = st.columns(3)
    weeks = one.multiselect("Weeks", sorted(candidates.week.dropna().astype(int).unique()))
    tiers = two.multiselect("Classifications", TIERS, default=TIERS[1:])
    phases = three.multiselect("Season type", sorted(candidates.season_type.unique()))
    filtered = betting.filter_rows(candidates, models=[model], markets=None if market=="All" else [market.lower()],
        providers=providers, conferences=conferences, teams=teams, weeks=weeks)
    if phases:
        filtered = filtered.loc[filtered.season_type.isin(phases)]
    selected = recommendations(filtered)
    if tiers:
        selected = selected.loc[selected.classification.isin(tiers)]
    total = len(selected)
    shown = selected if top_n == "All" else selected.head(int(top_n))
    strong = selected.classification.isin(["Strong", "Very strong"]).sum()
    first, second, third = st.columns(3)
    first.metric("Matching bets", total)
    second.metric("Strong / very strong", int(strong))
    third.metric("Largest estimated edge", f"{selected.edge_pp.max():+.1f} pp" if total else "—")
    if candidates.quote_age_hours.max() >= 24:
        st.warning("Some quotes are more than 24 hours old. Use Refresh odds before treating them as current offers.")
    st.caption("One pick per game and market for the selected model. Odds timestamps show CFBD retrieval time, not when a sportsbook last changed its price.")
    if shown.empty:
        st.info("No bets match these filters.")
    else:
        st.dataframe(betting.display_frame(shown), hide_index=True, width="stretch",
                     column_config=betting.table_config(), key="best_bets_table")
    with st.expander("Compare all sportsbooks and models"):
        games = candidates[["game_id", "home_team", "away_team"]].drop_duplicates("game_id")
        names = dict(zip(games.game_id, games.away_team + " at " + games.home_team))
        game_id = st.selectbox("Game details", list(names), format_func=names.get)
        game_candidates = candidates.loc[candidates.game_id.eq(game_id)]
        unavailable = [f"{label} · {market_name}" for name,label in MODELS.items()
                       for market_name in ("spread", "moneyline")
                       if game_candidates.loc[game_candidates.model.eq(name) & game_candidates.market.eq(market_name)].empty]
        if unavailable:
            st.info("Quotes or predictions unavailable: " + "; ".join(unavailable))
        st.dataframe(betting.display_frame(game_candidates),
                     hide_index=True, width="stretch", column_config=betting.table_config(), key="betting_game_quotes")
    all_games = data["games"].copy()
    future = (pd.to_datetime(all_games.kickoff, utc=True, errors="coerce").gt(utc())
              & ~all_games.completed.fillna(False) & ~all_games.cancelled.fillna(False))
    missing = all_games.loc[future & ~all_games.game_id.isin(candidates.game_id)]
    if len(missing):
        with st.expander(f"{len(missing)} upcoming games have unavailable quotes or predictions"):
            st.dataframe(missing[["away_team", "home_team", "week", "kickoff", "kickoff_known"]], hide_index=True, width="stretch")

with st.expander("How edge classifications work"):
    st.markdown("**Spread:** probability of covering, excluding pushes, minus 50%. **Moneyline:** win probability minus the offered price’s break-even probability. A percentage-point edge is not a percentage return.")
    st.dataframe(pd.DataFrame({"Classification": TIERS,
        "Edge (percentage points)": ["≤ 0", "> 0 to < 2", "2 to < 5", "5 to < 10", "≥ 10"]}), hide_index=True, width="stretch")
    st.caption("The 50% spread baseline is an analytical assumption. Spread prices are unavailable, so spread profitability is not calculated. Moneyline expected returns assume the quoted price.")

with st.expander("Model validation"):
    if not data["metrics"]:
        st.info("Validation results will appear after a successful training run.")
    else:
        st.dataframe(betting.validation_frame(data["metrics"]), hide_index=True, width="stretch")
        rows = [dict(model=MODELS[name], **row) for name,value in data["metrics"].items() for row in value.get("reliability",[])]
        if rows:
            figure = px.line(pd.DataFrame(rows), x="predicted", y="actual", color="model", markers=True,
                             labels={"predicted":"Predicted win probability","actual":"Observed win rate","model":"Model"})
            figure.add_shape(type="line", x0=0,y0=0,x1=1,y1=1,line=dict(color="#94a3b8",dash="dash"))
            figure.update_xaxes(tickformat=".0%", range=[0,1])
            figure.update_yaxes(tickformat=".0%", range=[0,1])
            st.plotly_chart(figure, width="stretch")
        st.caption("Expanding chronological holdouts. Calibration uses earlier out-of-sample predictions. Historical odds timing and source revisions are not verified; validation does not establish an actionable betting return.")

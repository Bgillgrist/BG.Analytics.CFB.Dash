"""Actual saved-forecast performance, separate from reconstructed research."""

import pandas as pd
import streamlit as st

from utils import model_data, model_charts
from utils.predictive_performance import (
    breakdown, calibration, csv_bytes, filter_games, metrics, select_forecasts, team_rows, zip_csvs,
)

st.caption("MODEL PERFORMANCE / MAIN GAME MODEL")
st.title("Predictive Performance")
st.write("Measure how the main game model predicts winners, scoring margins, and total points.")

try:
    available = model_data.load_seasons()
except Exception:
    st.error("Game seasons could not be loaded. Check the database connection and try again.")
    st.stop()
if available.empty:
    st.info("No FBS-vs-FBS games are available yet.")
    st.stop()
played = available.loc[available.games.gt(available.unfinished)]
default_season = int((played if not played.empty else available).iloc[0].season)
first, second, third = st.columns(3)
seasons = first.multiselect("Seasons", available.season.astype(int).tolist(), default=[default_season])
source = second.selectbox("Forecast source", ["Saved pregame", "Historical research"])
horizon = third.selectbox("Forecast cutoff", [0, 24, 168], format_func={0: "Before kickoff", 24: "24 hours before", 168: "Seven days before"}.get)
if not seasons:
    st.info("Select at least one season.")
    st.stop()
if source == "Historical research":
    st.warning("Historical research uses existing backfills and their intended as-of dates. These were recreated later and are separate from the saved pregame track record. Source revisions and historical odds timing are unverified.")
else:
    st.caption("One successful manual/nightly forecast per game, saved strictly before the selected cutoff. "
               "Missing or TBD kickoff times cannot establish pregame eligibility. Current corrected final scores are used.")
try:
    games, forecasts = model_data.load_performance(seasons)
    audit = select_forecasts(games, forecasts, source, horizon)
except Exception:
    st.error("Prediction snapshots could not be prepared. Check the database connection and prediction tables, then try again.")
    st.stop()
if audit.empty:
    st.info("No FBS-vs-FBS games match these seasons.")
    st.stop()
first, second, third = st.columns(3)
teams = first.multiselect("Teams", sorted(set(audit.home_team.dropna()) | set(audit.away_team.dropna())))
conferences = second.multiselect("Conferences", sorted(set(audit.home_conference.dropna()) | set(audit.away_conference.dropna())))
versions = third.multiselect("Model versions", sorted(audit.model_version.dropna().unique()))
first, second = st.columns(2)
weeks = first.multiselect("Weeks", sorted(audit.week.dropna().astype(int).unique()))
phases = second.multiselect("Season type", sorted(audit.season_type.dropna().unique()))
filtered = filter_games(audit, teams=teams, conferences=conferences, versions=versions, weeks=weeks, phases=phases)
st.caption("Empty filters include all values. Team and conference filters match either participant. "
           "Model-version filters apply after the forecast is selected; they never select an older forecast. "
           "The stored combined version label does not identify spread and total input usage separately.")
tabs = st.tabs(["Overview", "Win Probabilities", "Margins & Totals", "Breakdowns", "Game Audit"])
with tabs[0]:
    for column, label, count in zip(st.columns(3), ["Scheduled games", "Completed valid results", "Graded forecasts"],
                                  [len(filtered), filtered.valid_result.sum(), filtered.evaluation_status.eq("Graded").sum()]):
        column.metric(label, f"{int(count):,}")
    exclusions = filtered.groupby("evaluation_status").size().rename("games").reset_index()
    st.dataframe(exclusions, hide_index=True, width="stretch", key="performance_coverage")
    model_charts.summary(filtered)
    model_charts.trend_chart(filtered, "performance")
    with st.expander("Metrics and comparison benchmarks"):
        st.dataframe(metrics(filtered), hide_index=True, width="stretch")
        st.caption("Benchmarks use the same games with valid model probabilities. A constant 50% forecast has Brier score 0.25 and log loss 0.693. "
                   "Always-home accuracy is the observed home win rate. Missing model outputs have separate metric counts.")
with tabs[1]:
    model_charts.probability_charts(filtered)
with tabs[2]:
    model_charts.error_charts(filtered)
with tabs[3]:
    kind = st.selectbox("Break down by", ["Season", "Week", "Team", "Conference", "Model version", "Setting", "Prediction confidence"])
    grouping = {"Season": ["season"], "Week": ["season", "season_type", "week"], "Team": ["team"],
                "Conference": ["conference"], "Model version": ["model_version"], "Setting": ["setting"], "Prediction confidence": ["confidence_band"]}
    participant = kind in ("Team", "Conference", "Setting")
    grouped = breakdown(team_rows(filtered) if participant else filtered, grouping[kind])
    st.dataframe(grouped, hide_index=True, width="stretch")
    if participant:
        st.caption("Participant breakdowns count each team appearance. Within-conference games contribute twice to that conference; neutral games contribute twice to Neutral. These rows must not be summed as unique league games. Metrics retain the home-team prediction convention.")
with tabs[4]:
    st.dataframe(filtered, hide_index=True, width="stretch", key="performance_audit")
    st.caption("The audit includes pending games and exclusions. Errors are predicted minus actual; an unavailable prediction remains blank.")

with st.expander("Download analysis CSVs"):
    frames = dict(game_audit=filtered, summary_metrics=metrics(filtered), calibration=calibration(filtered))
    frames["breakdowns"] = pd.concat([
        breakdown(filtered, ["season"]).assign(breakdown_type="season"),
        breakdown(filtered, ["season", "season_type", "week"]).assign(breakdown_type="week"),
        breakdown(team_rows(filtered), ["team"]).assign(breakdown_type="team"),
        breakdown(team_rows(filtered), ["conference"]).assign(breakdown_type="conference"),
        breakdown(filtered, ["model_version"]).assign(breakdown_type="model_version"),
        breakdown(team_rows(filtered), ["setting"]).assign(breakdown_type="setting"),
        breakdown(filtered, ["confidence_band"]).assign(breakdown_type="confidence"),
    ], ignore_index=True)
    for name, frame in frames.items():
        frame["source"] = source
        frame["horizon_hours"] = horizon
        st.download_button(name.replace("_", " ").title(), csv_bytes(frame), f"{name}.csv", "text/csv", key=f"performance_export_{name}")
    st.download_button("All analysis CSVs (ZIP)", zip_csvs(frames), "predictive_performance.zip", "application/zip")

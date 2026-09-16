"""Saved pregame classifications and separately labeled research simulations."""
import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from utils import betting
    from cfb_betting.domain import MODELS, TIERS, performance, utc
except ModuleNotFoundError:
    st.error("Install the dashboard requirements, including the bundled betting package, to use this page.")
    st.stop()

st.markdown('<div style="color:#64748b;font-size:.8rem;letter-spacing:.12em">BETTING / PERFORMANCE</div>', unsafe_allow_html=True)
st.title("Betting History")
st.caption("Each game, model, and market is graded once using its last saved pregame classification and exact line.")

try:
    seasons = betting.load_seasons()
except Exception:
    st.error("Betting history could not be loaded. Check the database connection and try again.")
    st.stop()
if seasons.empty:
    st.info("No game history is available.")
    st.stop()
first, second, third = st.columns([1,2,1])
season = first.selectbox("Season", seasons.season.astype(int).tolist())
source_label = second.selectbox("Record", ["Last saved pregame", "Historical research"])
market_label = third.selectbox("Market", ["Spread", "Moneyline"])
source = "live" if source_label == "Last saved pregame" else "research"
if source == "research":
    st.warning("Research simulation using untimestamped historical lines. Quote availability at prediction time cannot be verified. These results are separate from the saved pregame record.")
else:
    st.caption("On-demand updates may be hours or days before kickoff. Snapshot age is shown for every pick; this record does not claim to use closing lines.")
try:
    data = betting.load_data(season, source)
except Exception:
    st.error("Saved betting history could not be loaded. Check the database connection and try again.")
    st.stop()

history = betting.history(data, source)
if history.empty and data["candidates"].empty:
    st.info("No saved pregame classifications are available for this season." if source=="live"
            else "Historical research has not been generated for this season. Run the shared backtest command to populate it.")
    st.stop()
if history.empty:
    options = data["candidates"].merge(data["games"], on="game_id")
    history = options.iloc[:0].assign(result=pd.Series(dtype=str), units=pd.Series(dtype=float))
else:
    options = history

first, second, third = st.columns(3)
models = first.multiselect("Models", list(MODELS), default=list(MODELS), format_func=MODELS.get)
tiers = second.multiselect("Classifications", TIERS, default=TIERS)
weeks = third.multiselect("Weeks", sorted(options.week.dropna().astype(int).unique()))
first, second, third = st.columns(3)
providers = first.multiselect("Sportsbooks", sorted(options.provider.unique()))
phases = second.multiselect("Season type", sorted(options.season_type.unique()))
versions = third.multiselect("Model versions", sorted(options.model_version.unique()))
# Canonical selections happen before filters: filtering never selects a different historical bet.
filtered = betting.filter_rows(history, models=models, markets=[market_label.lower()], providers=providers, weeks=weeks, tiers=tiers)
if phases:
    filtered = filtered.loc[filtered.season_type.isin(phases)]
if versions:
    filtered = filtered.loc[filtered.model_version.isin(versions)]
completed_games = data["games"].loc[data["games"].completed.fillna(False)]
covered_games = history.loc[history.result.isin(["W","L","Push"])].game_id.nunique()
first, second, third = st.columns(3)
first.metric("Games with saved results", covered_games)
second.metric("Completed games missing a record", max(0,len(completed_games)-covered_games))
third.metric("Forecasts in this view", len(filtered))
st.caption("Coverage counts unique games across available models and markets. Each model is evaluated separately. Empty filters mean all values.")

performance_tab, games_tab, timeline_tab = st.tabs(["Classification performance", "Graded picks", "Classification timeline"])
with performance_tab:
    if filtered.empty:
        st.info("No records match these filters.")
    else:
        summary = performance(filtered, ("model","model_version","market","classification"))
        summary["model"] = summary.model.map(MODELS)
        for column in ["hit_rate","rate_lower","rate_upper","predicted_probability","baseline","excess_hit_rate","roi","roi_lower","roi_upper"]:
            summary[column] *= 100
        columns=["model","model_version","classification","picks","wins","losses","pushes","pending","voids","hit_rate",
                 "rate_lower","rate_upper","predicted_probability","baseline","excess_hit_rate"]
        if market_label=="Moneyline":
            columns += ["units","roi","roi_lower","roi_upper"]
        configs={column:st.column_config.NumberColumn(column.replace("_"," ").title(),format="%.1f%%")
                 for column in ["hit_rate","rate_lower","rate_upper","predicted_probability","baseline","roi","roi_lower","roi_upper"]}
        configs["excess_hit_rate"]=st.column_config.NumberColumn("Observed minus baseline (pp)",format="%+.1f")
        configs["units"]=st.column_config.NumberColumn("Paper units",format="%+.2f")
        st.dataframe(summary[columns], hide_index=True, width="stretch",column_config=configs,key="betting_history_summary")
        st.caption("Hit-rate intervals: 95% Wilson intervals, excluding pushes and voids. ROI intervals: 95% bootstrap by season/week, shown when at least two weeks are available. Small samples and correlated games limit certainty.")
        weekly=performance(filtered,("model","market","season","season_type","week"))
        if not weekly.empty:
            weekly["phase_order"] = weekly.season_type.map({"regular": 0, "postseason": 1}).fillna(2)
            weekly = weekly.sort_values(["season", "phase_order", "week", "model"])
            weekly["Week"]=weekly.season_type + " " + weekly.week.astype(str)
            weekly["Model"]=weekly.model.map(MODELS)
            figure=px.line(weekly,x="Week",y="hit_rate",color="Model",markers=True,
                          labels={"hit_rate":"Cover rate" if market_label=="Spread" else "Win rate"})
            figure.update_yaxes(tickformat=".0%",range=[0,1])
            if market_label=="Spread":
                figure.add_hline(y=.5,line_dash="dash",line_color="#94a3b8")
            st.plotly_chart(figure,width="stretch")
        if market_label=="Moneyline":
            settled=filtered.loc[filtered.result.isin(["W","L","Push"])].sort_values(["kickoff","game_id"]).copy()
            settled["Cumulative units"]=settled.groupby(["model","model_version"]).units.cumsum()
            settled["Model"]=settled.model.map(MODELS)
            if not settled.empty:
                st.plotly_chart(px.line(settled,x="kickoff",y="Cumulative units",color="Model",markers=True,
                    line_group="model_version",labels={"kickoff":"Game kickoff"}),width="stretch")
            st.caption("One unit risked per pick. Returns use saved moneyline prices. A valuable underdog can win less than half the time, so compare prices and returns alongside win rate.")
        else:
            st.caption("Cover rate excludes pushes. Spread ROI is unavailable because spread prices are not collected.")
with games_tab:
    st.dataframe(betting.display_frame(filtered), hide_index=True,width="stretch",
                 column_config=betting.table_config(),key="betting_history_picks")
    if not data["outcomes"].empty:
        with st.expander("Final-score audit"):
            audited=data["outcomes"].loc[data["outcomes"].game_id.isin(filtered.game_id)]
            st.dataframe(audited,hide_index=True,width="stretch")
with timeline_tab:
    names=data["games"].loc[data["games"].game_id.isin(data["candidates"].game_id)].drop_duplicates("game_id")
    labels=dict(zip(names.game_id,names.away_team+" at "+names.home_team))
    game_id=st.selectbox("Timeline game",list(labels),format_func=labels.get)
    rows=data["candidates"].loc[data["candidates"].game_id.eq(game_id)].copy()
    runs=data["runs"].copy()
    runs["run_id"]=runs.run_id.astype(str)
    rows=rows.merge(runs[["run_id","as_of","completed_at","model_version"]],on="run_id",suffixes=("","_run"))
    game=data["games"].loc[data["games"].game_id.eq(game_id)].iloc[0]
    timestamps=pd.to_datetime(rows.completed_at if source=="live" else rows.as_of,utc=True)
    rows=rows.loc[timestamps.lt(pd.Timestamp(game.kickoff))].sort_values(["as_of","model","market","provider"])
    rows=betting.filter_rows(rows,models=models,markets=[market_label.lower()])
    st.dataframe(betting.display_frame(rows),hide_index=True,width="stretch",column_config=betting.table_config())
    st.caption("Earlier classifications are retained for inspection and are not added again to the performance totals.")

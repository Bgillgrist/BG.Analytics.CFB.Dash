"""Guided research models with session comparisons and R-friendly exports."""

from dataclasses import asdict
import hashlib

import plotly.express as px
import streamlit as st

from utils import model_builder as builder, model_charts, model_data
from utils.predictive_performance import csv_bytes, zip_csvs

st.caption("MODEL PERFORMANCE / RESEARCH WORKSPACE")
st.title("Model Builder")
st.write("Build a game model, test it against later seasons, and take the data and predictions into R.")
st.caption("FBS-vs-FBS only. Experiments stay in this session. Download them before leaving; they do not change production predictions.")
try:
    available = model_data.load_seasons()
    metric_catalog = model_data.load_metric_catalog()
except Exception:
    st.error("Modeling sources could not be loaded. Check the database connection and try again.")
    st.stop()
if available.empty or len(available) < 2:
    st.info("At least two seasons of FBS-vs-FBS games are needed for chronological evaluation.")
    st.stop()
seasons = sorted(available.season.astype(int).tolist())
first, second = st.columns(2)
target = first.selectbox("Prediction target", list(builder.TARGETS), format_func=builder.TARGETS.get)
family = second.selectbox("Model family", ["Linear", "Random forest", "XGBoost"],
                          format_func=lambda value: ("Logistic regression" if target == "win" else "Ridge regression") if value == "Linear" else value)
name = st.text_input("Experiment name", value=f"{builder.TARGETS[target]} · {family}")
first, second = st.columns(2)
start = first.selectbox("Starting training season", seasons[:-1])
completed = available.loc[available.unfinished.eq(0) & available.season.gt(start) &
                          available.season.lt(builder.now_utc().tz_convert("America/New_York").year)]
default_eval = int(completed.season.max()) if not completed.empty else next(year for year in seasons if year > start)
evaluation = second.multiselect("Evaluation seasons", [year for year in seasons if year > start], default=[default_eval], key=f"builder_eval_{start}")
st.caption("Each evaluation season is predicted by a model trained on earlier seasons only. Earlier games within the test season may update pregame features. "
           "Repeatedly choosing settings against the same seasons makes those seasons development data; reserve a later season for a final assessment.")

preset = st.radio("Feature preset", ["Base", "Advanced"], horizontal=True)
advanced = []
windows = []
if preset == "Advanced":
    advanced = st.multiselect("Advanced game metrics", metric_catalog, default=[name for name in builder.DEFAULT_METRICS if name in metric_catalog], format_func=builder.metric_label)
    windows = st.multiselect("Pregame averaging windows", list(builder.WINDOWS), default=list(builder.WINDOWS), format_func=builder.WINDOWS.get)
    st.caption("Every numeric advanced game metric is available. Values are means of earlier game rows, in original units. Each metric includes a nonmissing contributing-game count. Last five uses the current season only.")
market = st.checkbox("Allow sportsbook spread and total inputs", value=False)
if market:
    st.warning("Market-assisted research: stored historical lines do not record collection times. Results cannot establish the performance of a tradable historical strategy.")
catalog = builder.feature_catalog(advanced, windows, market)
feature_key = hashlib.sha256(repr((preset, advanced, windows, market)).encode()).hexdigest()[:12]
features = st.multiselect("Predictor features", catalog.feature.tolist(), default=catalog.feature.tolist(),
                         format_func=builder.feature_label, key=f"builder_features_{feature_key}")
with st.expander("Feature definitions and data limitations"):
    st.dataframe(catalog.assign(selected=catalog.feature.isin(features)), hide_index=True, width="stretch")
    st.caption("Historical ratings and advanced stats must precede the game date. Upcoming features are also capped at the fitting date. "
               "Same-day games and ratings are excluded. Annual talent and corrected historical source values are not publication-timestamped. "
               "Only earlier FBS-vs-FBS games enter advanced averages. Probability models are uncalibrated; inspect their calibration charts.")

params = {}
with st.expander("Model settings", expanded=False):
    if family == "Linear":
        params["regularization"] = st.number_input("Regularization strength", min_value=.001, max_value=1000., value=1., format="%.3f")
        st.caption("Larger values shrink coefficients more. Missing values use training medians and indicators; inputs are standardized within each fold.")
    else:
        first, second = st.columns(2)
        params["trees"] = first.number_input("Number of trees", min_value=50, max_value=500, value=200 if family == "Random forest" else 300, step=50)
        params["depth"] = second.number_input("Maximum tree depth", min_value=1, max_value=12, value=6 if family == "Random forest" else 3)
        if family == "XGBoost":
            params["learning_rate"] = st.number_input("Learning rate", min_value=.005, max_value=.3, value=.03, format="%.3f")
        st.caption("Deterministic seed 42 and one worker. Forests use training medians; XGBoost handles missing values directly. No automated tuning is run.")
config = builder.ExperimentConfig(name=name.strip() or "Untitled experiment", target=target, family=family,
    features=tuple(features), start_season=int(start), evaluation_seasons=tuple(evaluation),
    advanced_metrics=tuple(advanced), windows=tuple(windows), market=market, params=params)
experiments = st.session_state.setdefault("model_builder_experiments", {})

if st.button("Run experiment", type="primary", disabled=not features or not evaluation):
    with st.status("Preparing and evaluating experiment…", expanded=True) as status:
        progress = st.empty()
        try:
            inputs = model_data.load_builder_inputs(start, max(evaluation), advanced, market)
            dataset = builder.build_dataset(inputs, advanced, windows)
        except Exception:
            status.update(label="Data preparation failed", state="error")
            st.error("Modeling inputs could not be prepared. Check source coverage and duplicate records. Completed session experiments remain available.")
        else:
            try:
                identifier = builder.experiment_key(dataset, config)
                if identifier not in experiments:
                    experiments[identifier] = builder.run_experiment(dataset, config, progress.write)
                st.session_state["builder_selected_experiment"] = identifier
                status.update(label="Experiment ready", state="complete")
            except ValueError as error:
                status.update(label="Experiment could not be evaluated", state="error")
                st.error(str(error))
            except Exception:
                status.update(label="Experiment failed", state="error")
                st.error("Model fitting did not complete. Check model runtime and source data. Completed session experiments remain available.")

if not experiments:
    st.info("Choose features and evaluation seasons, then run an experiment. Training starts only when you press the button.")
    st.stop()
st.divider()
selected = st.selectbox("Completed experiment", list(experiments), key="builder_selected_experiment",
    format_func=lambda identifier: f"{experiments[identifier]['config']['name']} · {identifier[:8]}")
result = experiments[selected]
saved = result["config"]
if asdict(config) != saved:
    st.info("The controls differ from this completed experiment. Results and downloads below retain the settings shown in Experiment details.")
st.subheader(saved["name"])
st.caption(f"{builder.TARGETS[saved['target']]} · {saved['family']} · {len(saved['features'])} requested features · "
           f"{len(result['predictions']):,} held-out games · Data prepared {result['as_of']}")
if saved["market"]:
    st.warning("These results include market-assisted research inputs with unverified historical collection times.")
tabs = st.tabs(["Results", "Diagnostics", "Feature importance", "Compare experiments", "Upcoming games", "Experiment details", "Download CSVs"])
with tabs[0]:
    model_charts.summary(result["predictions"], saved["target"])
    st.dataframe(result["metrics"], hide_index=True, width="stretch")
    st.caption("Training-mean benchmarks are calculated separately within each fold, then scored on the same held-out games. Unrelated targets remain blank.")
    model_charts.trend_chart(result["predictions"], "builder_results", saved["target"])
with tabs[1]:
    if saved["target"] == "win":
        model_charts.probability_charts(result["predictions"])
    else:
        model_charts.error_charts(result["predictions"], saved["target"])
    st.dataframe(result["predictions"], hide_index=True, width="stretch", key="builder_test_predictions")
with tabs[2]:
    importance = result["importance"]
    top = importance.groupby("feature", as_index=False).importance.mean()
    top = top.loc[top.importance.abs().sort_values(ascending=False).head(25).index].sort_values("importance")
    st.plotly_chart(px.bar(top, x="importance", y="feature", orientation="h", color_discrete_sequence=[model_charts.NAVY]), width="stretch")
    st.caption("Linear values are standardized coefficients, including missingness indicators. Tree values measure held-out score decrease after permutation, "
               "averaged across three deterministic shuffles. Charts average folds equally. Correlated predictors can share or mask importance; these values do not establish causation.")
    st.dataframe(importance, hide_index=True, width="stretch")
with tabs[3]:
    compare_target = st.selectbox("Comparison target", list(builder.TARGETS), index=list(builder.TARGETS).index(saved["target"]), format_func=builder.TARGETS.get)
    compared = builder.comparison(list(experiments.values()), compare_target)
    if compared.empty:
        st.info("No completed experiments for this target yet.")
    else:
        st.dataframe(compared, hide_index=True, width="stretch")
        st.caption("Lower comparison score is better. Every experiment is scored on the intersection of its held-out game IDs with the other experiments for this target. "
                   "Different training windows remain visible in Experiment details. No overlap produces unavailable scores.")
with tabs[4]:
    upcoming_season = st.selectbox("Upcoming season", sorted(seasons, reverse=True))
    st.caption("This separate fit uses all eligible completed games from the experiment’s starting season through the fitting cutoff. Historical evaluation stays fixed.")
    if st.button("Fit for upcoming games"):
        with st.status("Fitting for upcoming games…", expanded=True) as status:
            progress = st.empty()
            try:
                inputs = model_data.load_builder_inputs(saved["start_season"], max(max(saved["evaluation_seasons"]), upcoming_season), saved["advanced_metrics"], saved["market"])
                dataset = builder.build_dataset(inputs, saved["advanced_metrics"], saved["windows"])
                updated = builder.fit_upcoming(result, dataset, upcoming_season, progress.write)
            except ValueError as error:
                status.update(label="Upcoming predictions unavailable", state="error")
                st.error(str(error))
            except Exception:
                status.update(label="Upcoming fit failed", state="error")
                st.error("Upcoming inputs or model fitting failed. Existing experiment results and previous upcoming predictions remain available.")
            else:
                result = experiments[selected] = updated
                status.update(label="Upcoming predictions ready", state="complete")
    if not result["upcoming_predictions"].empty:
        st.caption(f"Separate fit: {result['upcoming_fit']['as_of']} · season {result['upcoming_fit']['season']} · {result['upcoming_fit']['training_games']:,} training games")
        st.dataframe(result["upcoming_predictions"], hide_index=True, width="stretch", key="builder_upcoming_predictions")
with tabs[5]:
    st.json(dict(settings=saved, data_hash=result["data_hash"], experiment_id=selected, as_of=result["as_of"], dependencies=result["dependencies"]))
    st.subheader("Missingness and fold membership")
    st.dataframe(result["missingness"], hide_index=True, width="stretch")
    st.dataframe(result["folds"], hide_index=True, width="stretch")
    st.caption("Features with no observed training values are removed independently in each fold. Remaining preprocessing is fitted using that fold’s training rows only.")
with tabs[6]:
    st.caption("UTF-8 CSVs use snake_case fields, 0–1 probabilities, and ISO timestamps. In R, read game_id as character. "
               "Use folds.csv to identify training/evaluation membership; the same game may train later folds. "
               "Upcoming fits include their own dataset and membership CSVs. Download before ending this session.")
    frames = builder.export_frames(result)
    for name, frame in frames.items():
        st.download_button(name.replace("_", " ").title(), csv_bytes(frame), f"{selected}_{name}.csv", "text/csv", key=f"builder_export_{name}")
    st.download_button("All experiment CSVs (ZIP)", zip_csvs(frames), f"experiment_{selected}.zip", "application/zip")

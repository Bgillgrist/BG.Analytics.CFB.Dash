"""Session-only chronological modeling. No database writes or production artifacts."""

from dataclasses import asdict, dataclass, field
from importlib.metadata import version
import hashlib
import json

import numpy as np
import pandas as pd

from utils.predictive_performance import add_errors, metrics as performance_metrics, prepare_games

VERSION = "research_builder_v1"
BASE_FEATURES = ["home_teamrankings_rating", "away_teamrankings_rating", "home_talent", "away_talent", "neutral_site"]
WINDOWS = {"season": "Season to date", "last5": "Last five games", "prior": "Previous season"}
TARGETS = {"win": "Home win probability", "margin": "Home scoring margin", "total": "Combined points"}
TARGET_COLUMNS = {"win": "actual_home_win", "margin": "actual_home_margin", "total": "actual_total"}
OUTPUT_COLUMNS = {"win": "home_win_probability", "margin": "predicted_home_margin", "total": "predicted_total"}
DEFAULT_METRICS = [f"{side}_{metric}" for side in ("offense", "defense")
                   for metric in ("ppa", "successrate", "explosiveness", "passingplays_ppa", "rushingplays_ppa", "stuffrate")]
MIN_TRAIN = 30


def metric_label(name):
    from utils.scatterplot import metric_label as readable_metric
    return readable_metric(name)


def feature_label(name):
    labels = {"home_teamrankings_rating": "Home · TeamRankings rating", "away_teamrankings_rating": "Away · TeamRankings rating",
              "home_talent": "Home · Talent", "away_talent": "Away · Talent", "neutral_site": "Neutral site",
              "avg_spread": "Market · Home spread", "avg_over_under": "Market · Total points"}
    if name in labels:
        return labels[name]
    for side in ("home", "away"):
        for window, label in WINDOWS.items():
            prefix = f"{side}_{window}_"
            if name.startswith(prefix):
                metric = name[len(prefix):]
                description = "Games with stats" if metric == "games" else metric_label(metric.removesuffix("_n"))
                if metric.endswith("_n"):
                    description += " · Contributing games"
                return f"{side.title()} · {label} · {description}"
    return name


@dataclass
class ExperimentConfig:
    name: str
    target: str
    family: str
    features: tuple
    start_season: int
    evaluation_seasons: tuple
    advanced_metrics: tuple = ()
    windows: tuple = ("season", "last5", "prior")
    market: bool = False
    params: dict = field(default_factory=dict)


def now_utc(value=None):
    timestamp = pd.Timestamp.now(tz="UTC") if value is None else pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def day_cutoff(value):
    return now_utc(value).tz_convert("America/New_York").normalize().tz_localize(None)


def fingerprint(frame):
    ordered = frame.reindex(sorted(frame.columns), axis=1)
    if "game_id" in ordered:
        ordered = ordered.sort_values("game_id")
    return hashlib.sha256(ordered.to_json(orient="split", date_format="iso", index=False, double_precision=15).encode()).hexdigest()


def metric_unit(metric):
    if metric.endswith(("rate", "success", "_havoc_total", "_havoc_frontseven", "_havoc_db")):
        return "fraction (0–1)"
    if metric.endswith("ppa"):
        return "points added (source PPA units)"
    if metric.endswith(("plays", "drives")):
        return "count per game"
    return "source units, unchanged"


def feature_catalog(advanced_metrics=(), windows=(), market=False):
    rows = []
    for name in BASE_FEATURES:
        rows.append(dict(feature=name, source_column=name, unit="0/1" if name == "neutral_site" else "source rating units",
                         window="Pregame", aggregation="latest available", description=name.replace("_", " ")))
    for side in ("home", "away"):
        for window in windows:
            rows.append(dict(feature=f"{side}_{window}_games", source_column="game_id", unit="games",
                             window=WINDOWS[window], aggregation="count", description="Prior games with advanced-stat rows"))
            for metric in advanced_metrics:
                for suffix, aggregation, unit in [("", "mean", metric_unit(metric)), ("_n", "nonmissing count", "games")]:
                    rows.append(dict(feature=f"{side}_{window}_{metric}{suffix}", source_column=metric, unit=unit,
                                     window=WINDOWS[window], aggregation=aggregation,
                                     description=f"{side.title()} {WINDOWS[window].lower()}: {metric}; earlier dates only"))
    if market:
        for name in ("avg_spread", "avg_over_under"):
            rows.append(dict(feature=name, source_column=name, unit="points", window="Untimestamped stored market lines",
                             aggregation="sportsbook mean", description="Research only: historical collection timing is unknown"))
    return pd.DataFrame(rows)


def build_dataset(inputs, advanced_metrics=(), windows=("season", "last5", "prior"), as_of=None):
    """Generalized version of the shared engine's strict pregame date rules.

    Same-day games and ratings are excluded, even when a kickoff time is known.
    Numeric metrics remain in original units. No season aggregates are read.
    """
    as_of = now_utc(as_of)
    games = prepare_games(inputs["games"])
    game_days = games.kickoff.dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
    games["feature_cutoff"] = game_days.clip(upper=day_cutoff(as_of))
    games["neutral_site"] = games.neutralsite.astype(float)
    ratings = inputs["ratings"].copy()
    ratings["pull_date"] = pd.to_datetime(ratings.pull_date, errors="coerce", format="mixed").dt.tz_localize(None).dt.normalize()
    ratings["rating"] = pd.to_numeric(ratings.rating, errors="coerce").replace([np.inf, -np.inf], np.nan)
    ratings = ratings.drop_duplicates()
    if ratings.duplicated(["season", "team", "pull_date"]).any():
        raise ValueError("Conflicting historical rating rows. Resolve duplicates before modeling.")
    rating_groups = {key: group.sort_values("pull_date") for key, group in ratings.groupby(["season", "team"])}
    talent = inputs["talent"].drop_duplicates().copy()
    if talent.duplicated(["season", "team"]).any():
        raise ValueError("Conflicting annual talent rows. Resolve duplicates before modeling.")
    talent_values = talent.set_index(["season", "team"]).talent.to_dict()
    history = inputs["stats"].copy()
    history["game_id"] = history.game_id.astype(str)
    if history.duplicated(["game_id", "team"]).any():
        raise ValueError("Duplicate team-game advanced statistics.")
    history = history.merge(games[["game_id", "season", "kickoff", "completed", "kickoff_known", "cancelled", "home_team", "away_team"]],
                            on=["game_id", "season"], validate="many_to_one")
    history = history.loc[history.completed & history.kickoff_known & ~history.cancelled &
                          (history.team.eq(history.home_team) | history.team.eq(history.away_team))].copy()
    history["day"] = history.kickoff.dt.tz_convert("America/New_York").dt.normalize().dt.tz_localize(None)
    for metric in advanced_metrics:
        history[metric] = pd.to_numeric(history[metric], errors="coerce").replace([np.inf, -np.inf], np.nan)
    histories = {team: group.sort_values(["day", "kickoff", "game_id"]) for team, group in history.groupby("team")}
    additions = []
    for game in games.itertuples():
        row = {}
        for side in ("home", "away"):
            team = getattr(game, f"{side}_team")
            row[f"{side}_talent"] = talent_values.get((game.season, team), np.nan)
            rating = rating_groups.get((game.season, team), ratings.iloc[:0])
            earlier = rating.loc[rating.pull_date.lt(game.feature_cutoff)]
            row[f"{side}_teamrankings_rating"] = earlier.iloc[-1].rating if len(earlier) else np.nan
            row[f"{side}_rating_date"] = earlier.iloc[-1].pull_date if len(earlier) else pd.NaT
            past = histories.get(team, history.iloc[:0])
            past = past.loc[past.day.lt(game.feature_cutoff)]
            current = past.loc[past.season.eq(game.season)]
            samples = {"season": current, "last5": current.tail(5), "prior": past.loc[past.season.eq(game.season - 1)]}
            for window in windows:
                sample = samples[window]
                row[f"{side}_{window}_games"] = len(sample)
                for metric in advanced_metrics:
                    row[f"{side}_{window}_{metric}"] = sample[metric].mean()
                    row[f"{side}_{window}_{metric}_n"] = sample[metric].count()
        additions.append(row)
    output = pd.concat([games.reset_index(drop=True), pd.DataFrame(additions)], axis=1)
    odds = inputs.get("odds", pd.DataFrame())
    if not odds.empty:
        odds = odds.copy()
        odds["game_id"] = odds.game_id.astype(str)
        output = output.merge(odds, on="game_id", how="left", validate="one_to_one")
    for feature in feature_catalog(advanced_metrics, windows, market=True).feature:
        if feature not in output:
            output[feature] = np.nan
        output[feature] = pd.to_numeric(output[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
    output.attrs["as_of"] = as_of.isoformat()
    return output


def runtime_versions():
    return {name: version(name) for name in ("numpy", "pandas", "scikit-learn", "xgboost")}


def experiment_key(dataset, config):
    payload = dict(version=VERSION, data_hash=fingerprint(dataset), config=asdict(config), dependencies=runtime_versions(),
                   eligibility_day=str(day_cutoff(dataset.attrs.get("as_of"))))
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def pipeline(config):
    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression, Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    params = config.params
    win = config.target == "win"
    steps = []
    if config.family in ("Linear", "Random forest"):
        steps.append(("impute", SimpleImputer(strategy="median", add_indicator=config.family == "Linear")))
    if config.family == "Linear":
        steps.append(("scale", StandardScaler()))
        strength = float(params.get("regularization", 1.0))
        model = LogisticRegression(C=1/strength, max_iter=2000, random_state=42) if win else Ridge(alpha=strength)
    elif config.family == "Random forest":
        cls = RandomForestClassifier if win else RandomForestRegressor
        model = cls(n_estimators=int(params.get("trees", 200)), max_depth=int(params.get("depth", 6)),
                    min_samples_leaf=5, random_state=42, n_jobs=1)
    elif config.family == "XGBoost":
        try:
            from xgboost import XGBClassifier, XGBRegressor
        except Exception as error:
            raise ValueError("XGBoost could not start. Check the XGBoost/OpenMP runtime, or select a linear model or random forest.") from error
        cls = XGBClassifier if win else XGBRegressor
        model = cls(n_estimators=int(params.get("trees", 300)), max_depth=int(params.get("depth", 3)),
                    learning_rate=float(params.get("learning_rate", .03)), subsample=.8, colsample_bytree=.8,
                    min_child_weight=5, random_state=42, n_jobs=1,
                    objective="binary:logistic" if win else "reg:squarederror")
    else:
        raise ValueError("Unknown model family.")
    return Pipeline([*steps, ("model", model)])


def fit_model(train, config):
    target = TARGET_COLUMNS[config.target]
    if len(train) < MIN_TRAIN or train[target].nunique() < 2:
        raise ValueError(f"At least {MIN_TRAIN} training games and two distinct target values are required for every fold.")
    usable = [name for name in config.features if train[name].notna().any()]
    if not usable:
        raise ValueError("No selected feature has observed values in this training fold.")
    model = pipeline(config)
    model.fit(train[usable], train[target].astype(int) if config.target == "win" else train[target])
    return model, usable


def predict(model, frame, features, target):
    return model.predict_proba(frame[features])[:, 1] if target == "win" else model.predict(frame[features])


def prediction_frame(frame, values, target, fold, experiment_id):
    columns = ["game_id", "season", "season_type", "week", "kickoff", "home_team", "away_team",
               "home_conference", "away_conference", "neutralsite", *TARGET_COLUMNS.values()]
    result = frame[columns].copy()
    result[OUTPUT_COLUMNS[target]] = values
    result["fold"] = str(fold)
    result["experiment_id"] = experiment_id
    result["target"] = target
    return add_errors(result)


def importance(model, train, test, features, config, fold):
    fitted = model.named_steps["model"]
    if config.family == "Linear":
        names = model[:-1].get_feature_names_out(features)
        values = np.asarray(fitted.coef_).reshape(-1)
        method = "standardized_coefficient"
    else:
        from sklearn.inspection import permutation_importance
        scoring = "neg_brier_score" if config.target == "win" else "neg_mean_absolute_error"
        result = permutation_importance(model, test[features], test[TARGET_COLUMNS[config.target]],
            n_repeats=3, random_state=42, n_jobs=1, scoring=scoring)
        names, values = features, result.importances_mean
        method = "held_out_permutation_score_decrease"
    return pd.DataFrame(dict(feature=names, importance=values, method=method, fold=str(fold)))


def completed_before_cutoff(dataset, cutoff):
    days = dataset.kickoff.dt.tz_convert("America/New_York").dt.tz_localize(None).dt.normalize()
    return dataset.valid_result & dataset.kickoff_known & days.lt(day_cutoff(cutoff))


def run_experiment(dataset, config, progress=lambda message: None):
    if config.target not in TARGETS or not config.features:
        raise ValueError("Choose a target and at least one feature.")
    if not set(config.features) <= set(dataset.columns):
        raise ValueError("Selected features are missing from the prepared dataset.")
    if not config.evaluation_seasons or min(config.evaluation_seasons) <= config.start_season:
        raise ValueError("Evaluation seasons must follow the starting training season.")
    as_of = dataset.attrs.get("as_of", now_utc().isoformat())
    identifier = experiment_key(dataset, config)
    eligible = completed_before_cutoff(dataset, as_of) & dataset.season.ge(config.start_season)
    sample = dataset.loc[eligible].sort_values(["kickoff", "game_id"]).copy()
    predictions, folds, importances, missingness = [], [], [], []
    for season in sorted(set(config.evaluation_seasons)):
        train, test = sample.loc[sample.season.lt(season)], sample.loc[sample.season.eq(season)]
        if test.empty:
            raise ValueError(f"No eligible completed games for evaluation season {season}.")
        progress(f"Evaluating {season}: training on {len(train):,} earlier games")
        model, usable = fit_model(train, config)
        predictions.append(prediction_frame(test, predict(model, test, usable, config.target), config.target, season, identifier))
        for role, group in [("train", train), ("evaluation", test)]:
            folds.append(pd.DataFrame(dict(game_id=group.game_id, fold=str(season), role=role, experiment_id=identifier)))
        missingness.extend(dict(feature=name, fold=str(season), training_missing_fraction=train[name].isna().mean(),
            evaluation_missing_fraction=test[name].isna().mean(), used=name in usable) for name in config.features)
        importances.append(importance(model, train, test, usable, config, season))
        # A training-only constant benchmark, evaluated on exactly the same games.
        predictions[-1]["training_mean_baseline"] = train[TARGET_COLUMNS[config.target]].mean()
    heldout = pd.concat(predictions, ignore_index=True)
    result_metrics = performance_metrics(heldout)
    baseline = heldout.copy()
    baseline[OUTPUT_COLUMNS[config.target]] = baseline.training_mean_baseline
    baseline_metrics = performance_metrics(baseline).rename(columns={"value": "training_mean_baseline"})
    result_metrics = result_metrics.merge(baseline_metrics[["metric", "training_mean_baseline"]], on="metric")
    result = dict(experiment_id=identifier, config=asdict(config), as_of=as_of, data_hash=fingerprint(dataset),
                  dependencies=runtime_versions(), dataset=dataset.copy(), predictions=heldout,
                  folds=pd.concat(folds, ignore_index=True), metrics=result_metrics,
                  importance=pd.concat(importances, ignore_index=True), missingness=pd.DataFrame(missingness),
                  feature_dictionary=feature_catalog(config.advanced_metrics, config.windows, config.market),
                  upcoming_predictions=pd.DataFrame())
    return result


def fit_upcoming(result, dataset, season, progress=lambda message: None):
    config = ExperimentConfig(**result["config"])
    as_of = dataset.attrs["as_of"]
    eligible = completed_before_cutoff(dataset, as_of) & dataset.season.ge(config.start_season)
    train = dataset.loc[eligible].sort_values(["kickoff", "game_id"])
    upcoming = dataset.loc[dataset.season.eq(season) & dataset.kickoff_known & ~dataset.completed & ~dataset.cancelled
                           & dataset.kickoff.gt(now_utc(as_of))].sort_values(["kickoff", "game_id"]).copy()
    if upcoming.empty:
        raise ValueError("No eligible upcoming games are available for this season.")
    progress(f"Refitting on {len(train):,} past games for {len(upcoming):,} upcoming games")
    model, usable = fit_model(train, config)
    future = prediction_frame(upcoming, predict(model, upcoming, usable, config.target), config.target, "upcoming", result["experiment_id"])
    future["fit_cutoff"] = as_of
    future["fit_data_hash"] = fingerprint(dataset)
    membership = pd.concat([pd.DataFrame(dict(game_id=train.game_id, role="final_train")),
                            pd.DataFrame(dict(game_id=upcoming.game_id, role="upcoming"))], ignore_index=True)
    membership["fold"] = "upcoming"
    membership["experiment_id"] = result["experiment_id"]
    return dict(result, upcoming_predictions=future, upcoming_dataset=dataset.copy(), upcoming_folds=membership,
                upcoming_fit=dict(as_of=as_of, data_hash=fingerprint(dataset), training_games=len(train),
                                  usable_features=usable, season=int(season)))


def comparison(results, target):
    chosen = [result for result in results if result["config"]["target"] == target]
    if not chosen:
        return pd.DataFrame()
    common = set.intersection(*(set(result["predictions"].game_id) for result in chosen))
    metric = {"win": "brier_score", "margin": "margin_mae", "total": "total_mae"}[target]
    rows = []
    for result in chosen:
        sample = result["predictions"]
        score = performance_metrics(sample.loc[sample.game_id.isin(common)]).set_index("metric").loc[metric]
        rows.append(dict(experiment_id=result["experiment_id"], name=result["config"]["name"], family=result["config"]["family"],
            market_assisted=result["config"]["market"], evaluation_games=len(sample), common_games=len(common),
            outside_common_games=len(sample)-len(common), metric=metric, value=score.value))
    return pd.DataFrame(rows).sort_values(["value", "experiment_id"], na_position="last")


def export_frames(result):
    definitions = pd.DataFrame([
        dict(feature="actual_home_win", unit="0/1", description="1 when home points exceed away points"),
        dict(feature="actual_home_margin", unit="points", description="Home points minus away points; positive favors home"),
        dict(feature="actual_total", unit="points", description="Home points plus away points"),
        dict(feature="home_win_probability", unit="probability (0–1)", description="Predicted home win probability"),
        dict(feature="predicted_home_margin", unit="points", description="Predicted home margin; negative of the betting-display home spread"),
        dict(feature="predicted_total", unit="points", description="Predicted combined points"),
    ])
    settings = dict(**result["config"], experiment_id=result["experiment_id"], data_hash=result["data_hash"],
                    as_of=result["as_of"], builder_version=VERSION, dependencies=result["dependencies"],
                    upcoming_fit=result.get("upcoming_fit"),
                    research_note="Historical source revisions and market collection timing are not verified. Classifier probabilities are uncalibrated.")
    frames = {key: result[key].copy() for key in ("dataset", "folds", "predictions", "upcoming_predictions", "metrics", "importance", "missingness")}
    frames["feature_dictionary"] = pd.concat([result["feature_dictionary"], definitions], ignore_index=True)
    frames["feature_dictionary"]["selected_predictor"] = frames["feature_dictionary"].feature.isin(result["config"]["features"])
    frames["settings"] = pd.DataFrame([dict(setting=key, value=json.dumps(value, sort_keys=True, default=str)) for key, value in settings.items()])
    for key in ("upcoming_dataset", "upcoming_folds"):
        if key in result:
            frames[key] = result[key].copy()
    for key, frame in frames.items():
        frame["experiment_id"] = result["experiment_id"]
        frame["data_hash"] = result.get("upcoming_fit", {}).get("data_hash", result["data_hash"]) if key.startswith("upcoming") else result["data_hash"]
    return frames

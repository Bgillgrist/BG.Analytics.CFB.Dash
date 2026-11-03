"""Pure snapshot selection, predictive diagnostics, and portable CSV exports."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pandas as pd

PREDICTIONS = ["home_win_probability", "predicted_home_margin", "predicted_total"]


def numeric(frame, column):
    return pd.to_numeric(frame.get(column, pd.Series(np.nan, index=frame.index)), errors="coerce").replace([np.inf, -np.inf], np.nan)


def prepare_games(games):
    result = games.copy()
    result["game_id"] = result.game_id.astype(str)
    if result.game_id.duplicated().any():
        raise ValueError("Duplicate game IDs in the source schedule.")
    result["kickoff"] = pd.to_datetime(result.kickoff, utc=True, errors="coerce", format="mixed")
    for name in ("completed", "starttimetbd", "neutralsite", "cancelled"):
        result[name] = result.get(name, pd.Series(False, index=result.index)).fillna(False).eq(True)
    result["kickoff_known"] = result.kickoff.notna() & ~result.starttimetbd
    result["homepoints"] = numeric(result, "homepoints")
    result["awaypoints"] = numeric(result, "awaypoints")
    result["valid_result"] = (result.completed & ~result.cancelled & result.homepoints.ge(0)
                              & result.awaypoints.ge(0) & result.homepoints.ne(result.awaypoints))
    result["actual_home_margin"] = (result.homepoints - result.awaypoints).where(result.valid_result)
    result["actual_total"] = (result.homepoints + result.awaypoints).where(result.valid_result)
    result["actual_home_win"] = result.actual_home_margin.gt(0).astype(float).where(result.valid_result)
    return result


def add_errors(frame):
    result = frame.copy()
    for name in PREDICTIONS:
        result[name] = numeric(result, name)
    result["home_win_probability"] = result.home_win_probability.where(result.home_win_probability.between(0, 1))
    for prediction, actual, output in [("predicted_home_margin", "actual_home_margin", "margin_error"),
                                        ("predicted_total", "actual_total", "total_error")]:
        result[output] = result[prediction] - numeric(result, actual)
    probability = result.home_win_probability
    result["winner_correct"] = probability.gt(.5).eq(numeric(result, "actual_home_win")).astype(float).where(
        probability.notna() & probability.ne(.5) & numeric(result, "actual_home_win").notna())
    result["confidence"] = probability.where(probability.ge(.5), 1 - probability)
    result["confidence_band"] = pd.cut(result.confidence, [.5, .6, .7, .8, .9, 1],
        labels=["50–60%", "60–70%", "70–80%", "80–90%", "90–100%"], include_lowest=True).astype("string")
    return result


def select_forecasts(games, forecasts, source="Saved pregame", horizon_hours=0):
    """Return every schedule game with at most one forecast, including exclusion reasons.

    Select before filtering model versions/teams. A post-kickoff saved row cannot
    masquerade as a pregame forecast just because its run_date was backdated.
    """
    result = prepare_games(games)
    rows = forecasts.copy()
    selected = pd.DataFrame(columns=["game_id", *PREDICTIONS, "run_id", "model_version"])
    if not rows.empty:
        rows["game_id"] = rows.game_id.astype(str)
        rows = rows.merge(result[["game_id", "kickoff", "kickoff_known"]], on="game_id", validate="many_to_one")
        for column in ("forecast_completed_at", "run_created_at", "prediction_created_at", "run_date"):
            rows[column] = pd.to_datetime(rows[column], utc=True, errors="coerce", format="mixed")
        cutoff = rows.kickoff - pd.Timedelta(hours=horizon_hours)
        eligible = rows.status.eq("success") & rows.kickoff_known
        if source == "Historical research":
            eligible &= rows.run_type.eq("backfill") & rows.run_date.lt(cutoff)
            ordering = ["run_date", "forecast_completed_at", "run_created_at", "run_id"]
        else:
            eligible &= (rows.run_type.isin(["nightly", "manual"]) & rows.forecast_completed_at.lt(cutoff)
                         & rows.run_created_at.lt(cutoff) & rows.prediction_created_at.lt(cutoff)
                         & rows.run_date.lt(cutoff))
            ordering = ["forecast_completed_at", "run_created_at", "run_id"]
        rows["run_id"] = rows.run_id.astype(str)
        selected = rows.loc[eligible].sort_values(ordering, na_position="first").drop_duplicates("game_id", keep="last")
        selected = selected.drop(columns=["kickoff", "kickoff_known"])
    result = result.merge(selected, on="game_id", how="left", validate="one_to_one")
    result["eligible_forecast"] = result.run_id.notna()
    result["evaluation_status"] = np.select(
        [result.cancelled, ~result.completed, ~result.valid_result, ~result.kickoff_known, ~result.eligible_forecast],
        ["Cancelled", "Awaiting result", "Invalid final score", "Unknown kickoff", "No eligible forecast"], default="Graded")
    result["source"] = source
    result["horizon_hours"] = horizon_hours
    return add_errors(result)


def filter_games(frame, seasons=None, weeks=None, teams=None, conferences=None, versions=None, phases=None):
    result = frame.copy()
    for column, values in [("season", seasons), ("week", weeks), ("model_version", versions), ("season_type", phases)]:
        if values:
            result = result.loc[result[column].isin(values)]
    if teams:
        result = result.loc[result.home_team.isin(teams) | result.away_team.isin(teams)]
    if conferences:
        result = result.loc[result.home_conference.isin(conferences) | result.away_conference.isin(conferences)]
    return result


def graded(frame):
    return frame.loc[frame.evaluation_status.eq("Graded")].copy() if "evaluation_status" in frame else frame.copy()


def metrics(frame):
    """Each metric has its own valid observation count; bias = predicted - actual."""
    from sklearn.metrics import roc_auc_score
    sample = add_errors(graded(frame))
    rows = []
    def append(name, value, count):
        rows.append(dict(metric=name, value=float(value) if pd.notna(value) else np.nan, games=int(count)))
    win = sample.dropna(subset=["home_win_probability", "actual_home_win"])
    p, y = win.home_win_probability.to_numpy(), win.actual_home_win.to_numpy()
    clipped = np.clip(p, 1e-15, 1 - 1e-15)
    append("winner_accuracy", sample.winner_correct.mean(), sample.winner_correct.count())
    append("brier_score", np.mean((p-y)**2) if len(win) else np.nan, len(win))
    append("log_loss", -np.mean(y*np.log(clipped)+(1-y)*np.log1p(-clipped)) if len(win) else np.nan, len(win))
    append("roc_auc", roc_auc_score(y, p) if len(np.unique(y)) == 2 else np.nan, len(win))
    append("always_home_accuracy", y.mean() if len(win) else np.nan, len(win))
    append("constant_50_brier", .25 if len(win) else np.nan, len(win))
    append("constant_50_log_loss", np.log(2) if len(win) else np.nan, len(win))
    for target in ("margin", "total"):
        errors = sample[f"{target}_error"].dropna()
        append(f"{target}_mae", errors.abs().mean(), len(errors))
        append(f"{target}_rmse", np.sqrt((errors**2).mean()), len(errors))
        append(f"{target}_bias", errors.mean(), len(errors))
    return pd.DataFrame(rows)


def wilson(wins, count):
    if not count:
        return np.nan, np.nan
    z = 1.959963984540054
    p = wins / count
    center = (p + z*z/(2*count)) / (1 + z*z/count)
    radius = z*np.sqrt(p*(1-p)/count + z*z/(4*count*count)) / (1+z*z/count)
    return center-radius, center+radius


def calibration(frame):
    sample = add_errors(graded(frame)).dropna(subset=["home_win_probability", "actual_home_win"])
    rows = []
    for index in range(10):
        low, high = index / 10, (index + 1) / 10
        chosen = sample.loc[sample.home_win_probability.ge(low) &
                            (sample.home_win_probability.lt(high) if index < 9 else sample.home_win_probability.le(1))]
        if chosen.empty:
            continue
        lower, upper = wilson(chosen.actual_home_win.sum(), len(chosen))
        rows.append(dict(bin_lower=low, bin_upper=high, games=len(chosen),
                         mean_probability=chosen.home_win_probability.mean(), observed_win_rate=chosen.actual_home_win.mean(),
                         rate_lower=lower, rate_upper=upper))
    return pd.DataFrame(rows, columns=["bin_lower", "bin_upper", "games", "mean_probability", "observed_win_rate", "rate_lower", "rate_upper"])


def team_rows(frame):
    rows = []
    for side in ("home", "away"):
        copy = frame.copy()
        copy["team"] = copy[f"{side}_team"]
        copy["conference"] = copy[f"{side}_conference"]
        copy["setting"] = np.where(copy.neutralsite, "Neutral", side.title())
        rows.append(copy)
    return pd.concat(rows, ignore_index=True)


def breakdown(frame, columns):
    sample = graded(frame)
    rows = []
    for key, group in sample.groupby(columns, dropna=False, observed=True, sort=True):
        keys = key if isinstance(key, tuple) else (key,)
        row = dict(zip(columns, keys))
        row["games"] = len(group)
        for item in metrics(group).itertuples():
            row[item.metric] = item.value
            row[f"{item.metric}_games"] = item.games
        rows.append(row)
    return pd.DataFrame(rows)


def trends(frame):
    sample = graded(frame).sort_values(["kickoff", "game_id"])
    weekly, cumulative = [], []
    keys = ["season", "season_type", "week"]
    # Order week groups by their actual first kickoff, including postseason.
    groups = sorted(sample.groupby(keys, dropna=False), key=lambda pair: pair[1].kickoff.min())
    accumulated = []
    for key, group in groups:
        accumulated.append(group)
        label = f"{key[0]} {key[1]} W{key[2]}"
        for output, data in [(weekly, group), (cumulative, pd.concat(accumulated))]:
            output.append(dict(period=label, games=len(data), **metrics(data).set_index("metric").value.to_dict()))
    return pd.DataFrame(weekly), pd.DataFrame(cumulative)


def csv_bytes(frame):
    copy = frame.copy()
    for column in copy:
        if isinstance(copy[column].dtype, pd.DatetimeTZDtype):
            copy[column] = copy[column].dt.tz_convert("UTC").map(lambda value: value.isoformat() if pd.notna(value) else "")
    return copy.to_csv(index=False, na_rep="").encode("utf-8")


def zip_csvs(frames):
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, frame in frames.items():
            archive.writestr(f"{name}.csv", csv_bytes(frame))
    return stream.getvalue()

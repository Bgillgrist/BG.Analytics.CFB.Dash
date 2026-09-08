"""Read-only weekly game data and transparent BG opponent-adjusted rankings.

Transforms are independent of Streamlit so scoring and historical cutoffs can be
tested without a database or a running page.
"""

import numpy as np
import pandas as pd


OPPONENT_WEIGHT = 0.25
PRESETS = {
    "Overall": ("ppa", ["successrate", "explosiveness", "plays"]),
    "Passing": ("passingplays_ppa", ["passingplays_successrate", "passingplays_explosiveness"]),
    "Rushing": ("rushingplays_ppa", ["rushingplays_successrate", "rushingplays_explosiveness", "stuffrate", "lineyards"]),
}
METRIC_LABELS = {
    "ppa": "PPA/play", "totalppa": "Total PPA", "plays": "Plays", "drives": "Drives",
    "successrate": "Success rate", "explosiveness": "Explosiveness",
    "powersuccess": "Power success", "stuffrate": "Stuff rate", "lineyards": "Line yards/rush",
    "lineyardstotal": "Total line yards", "secondlevelyards": "Second-level yards/rush",
    "secondlevelyardstotal": "Total second-level yards", "openfieldyards": "Open-field yards/rush",
    "openfieldyardstotal": "Total open-field yards",
}
for _prefix, _label in [("standarddowns", "Standard-down"), ("passingdowns", "Passing-down"),
                         ("passingplays", "Passing"), ("rushingplays", "Rushing")]:
    for _suffix, _name in [("ppa", "PPA/play"), ("successrate", "success rate"), ("explosiveness", "explosiveness")]:
        METRIC_LABELS[f"{_prefix}_{_suffix}"] = f"{_label} {_name}"
    if _prefix.endswith("plays"):
        METRIC_LABELS[f"{_prefix}_totalppa"] = f"{_label} total PPA"

ELIGIBLE_SQL = """
    g.completed IS TRUE
    AND LOWER(g.homeclassification) = 'fbs'
    AND LOWER(g.awayclassification) = 'fbs'
    AND g.hometeam IS NOT NULL AND g.awayteam IS NOT NULL
    AND g.hometeam <> g.awayteam
    AND gs.team IN (g.hometeam, g.awayteam)
    AND gs.season = g.season
    AND (gs.offense_plays > 0 OR gs.defense_plays > 0)
"""


def load_available_weeks():
    from utils.db import read_df

    return read_df(f"""
        SELECT g.season::int AS season,
               LOWER(COALESCE(g.seasontype, 'regular')) AS season_type,
               g.week::int AS week, MAX(g.startdate) AS last_kickoff,
               COUNT(DISTINCT g.id)::int AS games
        FROM public.team_advanced_game_stats gs
        JOIN public.game_data g ON g.id = gs.game_id
        WHERE {ELIGIBLE_SQL} AND g.week IS NOT NULL
        GROUP BY g.season, LOWER(COALESCE(g.seasontype, 'regular')), g.week
        ORDER BY g.season DESC, MAX(g.startdate) DESC NULLS LAST, g.week DESC
    """)


def load_week(season, season_type, week):
    """Batch-load a week and its needed pregame rating snapshots. No writes."""
    from utils.db import read_df

    rows = read_df(f"""
        SELECT gs.*, g.season AS schedule_season, g.week AS schedule_week,
               LOWER(COALESCE(g.seasontype, 'regular')) AS schedule_season_type,
               g.completed, g.startdate, g.starttimetbd, g.neutralsite,
               g.hometeam, g.awayteam, g.homeclassification, g.awayclassification,
               g.homeconference, g.awayconference, g.homepoints, g.awaypoints
        FROM public.team_advanced_game_stats gs
        JOIN public.game_data g ON g.id = gs.game_id
        WHERE {ELIGIBLE_SQL}
          AND g.season = :season
          AND LOWER(COALESCE(g.seasontype, 'regular')) = :season_type
          AND g.week = :week
        ORDER BY g.startdate NULLS LAST, g.id, gs.team
    """, params={"season": int(season), "season_type": season_type, "week": int(week)})
    frame = prepare_games(rows)
    if frame.empty:
        return frame, None
    note = None
    try:
        runs = read_df("""
            SELECT team_rating_run_id::text AS rating_run_id, season, status, run_type,
                   completed_at, created_at
            FROM public.team_rating_runs
            WHERE season = :season AND status = 'success'
              AND run_type IN ('manual', 'nightly') AND completed_at IS NOT NULL
        """, params={"season": int(season)})
    except Exception:
        runs = pd.DataFrame()
        note = "Pregame BG rating history could not be loaded. Raw performances are still available."
    frame = attach_pregame_runs(frame, runs)
    run_ids = frame["rating_run_id"].dropna().unique().tolist()
    ratings = pd.DataFrame()
    if run_ids:
        try:
            ratings = read_df("""
                SELECT team_rating_run_id::text AS rating_run_id,
                       team, classification, power_rating
                FROM public.team_ratings
                WHERE team_rating_run_id = ANY(CAST(:run_ids AS uuid[]))
                  AND LOWER(classification) = 'fbs'
            """, params={"run_ids": run_ids})
        except Exception:
            note = "Pregame BG ratings could not be loaded. Raw performances are still available."
    return attach_opponent_ratings(frame, ratings), note


def numeric(series):
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def prepare_games(rows):
    """Resolve game identity from the schedule and retain valid FBS performances."""
    if rows.empty:
        return rows.copy()
    frame = rows.copy()
    eligible = (
        frame["completed"].eq(True)
        & frame["homeclassification"].str.lower().eq("fbs")
        & frame["awayclassification"].str.lower().eq("fbs")
        & frame["hometeam"].notna() & frame["awayteam"].notna()
        & frame["hometeam"].ne(frame["awayteam"])
        & (frame["team"].eq(frame["hometeam"]) | frame["team"].eq(frame["awayteam"]))
        & frame["game_id"].notna() & frame["season"].eq(frame["schedule_season"])
    )
    frame = frame.loc[eligible].copy()
    if frame.duplicated(["season", "game_id", "team"]).any():
        raise ValueError("Duplicate team-game advanced-stat rows were found.")
    for side in ("offense", "defense"):
        for suffix in METRIC_LABELS:
            column = f"{side}_{suffix}"
            frame[column] = numeric(frame[column]) if column in frame else np.nan
    frame = frame.loc[(frame["offense_plays"] > 0) | (frame["defense_plays"] > 0)].copy()
    home = frame["team"].eq(frame["hometeam"])
    frame["opponent"] = frame["awayteam"].where(home, frame["hometeam"])
    frame["conference"] = frame["homeconference"].where(home, frame["awayconference"]).fillna("Unknown")
    frame["venue"] = np.where(frame["neutralsite"].eq(True), "Neutral", np.where(home, "Home", "Away"))
    frame["points_for"] = numeric(frame["homepoints"].where(home, frame["awaypoints"]))
    frame["points_against"] = numeric(frame["awaypoints"].where(home, frame["homepoints"]))
    valid_score = frame["points_for"].notna() & frame["points_against"].notna()
    frame["result"] = pd.Series(None, index=frame.index, dtype="object")
    frame.loc[valid_score, "result"] = np.where(
        frame.loc[valid_score, "points_for"] > frame.loc[valid_score, "points_against"], "W",
        np.where(frame.loc[valid_score, "points_for"] < frame.loc[valid_score, "points_against"], "L", "T"))
    frame["final_score"] = pd.Series(None, index=frame.index, dtype="object")
    frame.loc[valid_score, "final_score"] = (
        frame.loc[valid_score, "points_for"].astype(int).astype(str) + "–"
        + frame.loc[valid_score, "points_against"].astype(int).astype(str))
    frame["kickoff"] = pd.to_datetime(frame["startdate"], utc=True, errors="coerce")
    # The existing game loader uses `start_time_tbd or starttimetbd`, which
    # persists an explicit False as NULL. A completed game's stored timestamp
    # is usable unless its time is explicitly marked TBD; NULL alone is not TBD.
    frame["reliable_kickoff"] = frame["kickoff"].notna() & ~frame["starttimetbd"].eq(True)
    frame["week"] = frame["schedule_week"]
    frame["season_type"] = frame["schedule_season_type"]
    return frame.reset_index(drop=True)


def attach_pregame_runs(frame, runs):
    """Choose one snapshot per game, strictly before its reliable kickoff."""
    eligible = runs.copy()
    if not eligible.empty:
        eligible = eligible.loc[eligible["status"].eq("success") & eligible["run_type"].isin(["manual", "nightly"])].copy()
        for field in ("completed_at", "created_at"):
            eligible[field] = pd.to_datetime(eligible[field], utc=True, errors="coerce")
        eligible["rating_run_id"] = eligible["rating_run_id"].astype(str)
        eligible = eligible.dropna(subset=["completed_at"]).sort_values(
            ["completed_at", "created_at", "rating_run_id"], na_position="first")
    selections = []
    for game in frame.drop_duplicates(["season", "game_id"]).itertuples(index=False):
        selected = None
        if game.reliable_kickoff and not eligible.empty:
            candidates = eligible.loc[eligible["season"].eq(game.season) & (eligible["completed_at"] < game.kickoff)]
            if not candidates.empty:
                selected = candidates.iloc[-1]
        selections.append({
            "season": game.season, "game_id": game.game_id,
            "rating_run_id": selected["rating_run_id"] if selected is not None else None,
            "rating_completed_at": selected["completed_at"] if selected is not None else pd.NaT,
            "adjustment_note": None if selected is not None else
                ("Reliable kickoff time unavailable" if not game.reliable_kickoff else "No saved pregame BG rating"),
        })
    return frame.merge(pd.DataFrame(selections), on=["season", "game_id"], how="left", validate="many_to_one")


def standardize(values):
    """Population z-scores, preserving missing values and small-sample limits."""
    values = numeric(values)
    result = pd.Series(np.nan, index=values.index, dtype="float64")
    valid = values.dropna()
    if len(valid) < 2:
        return result
    deviation = valid.std(ddof=0)
    result.loc[valid.index] = 0.0 if deviation == 0 else (valid - valid.mean()) / deviation
    return result


def attach_opponent_ratings(frame, ratings):
    if ratings.empty:
        result = frame.copy()
        result["opponent_bg_rating"] = np.nan
        result["opponent_strength_z"] = np.nan
    else:
        cohort = ratings.loc[ratings["classification"].str.lower().eq("fbs")].copy()
        cohort["rating_run_id"] = cohort["rating_run_id"].astype(str)
        if cohort.duplicated(["rating_run_id", "team"]).any():
            raise ValueError("Duplicate BG team ratings were found in a snapshot.")
        cohort["power_rating"] = numeric(cohort["power_rating"])
        cohort["opponent_strength_z"] = cohort.groupby("rating_run_id")["power_rating"].transform(standardize)
        cohort = cohort.rename(columns={"team": "opponent", "power_rating": "opponent_bg_rating"})
        result = frame.merge(cohort[["rating_run_id", "opponent", "opponent_bg_rating", "opponent_strength_z"]],
                             on=["rating_run_id", "opponent"], how="left", validate="many_to_one")
    missing = result["adjustment_note"].isna() & result["opponent_strength_z"].isna()
    result.loc[missing, "adjustment_note"] = "Opponent rating or FBS comparison population unavailable"
    return result


def rank_performances(frame, side, preset):
    metric = f"{side}_{PRESETS[preset][0]}"
    result = frame.loc[frame[f"{side}_plays"] > 0].copy()
    result["raw_ppa"] = numeric(result[metric])
    result["raw_rank"] = result["raw_ppa"].rank(method="min", ascending=side == "defense").astype("Int64")
    result["performance_z"] = standardize(result["raw_ppa"]) * (1 if side == "offense" else -1)
    result["adjusted_score"] = result["performance_z"] + OPPONENT_WEIGHT * result["opponent_strength_z"]
    result["adjusted_rank"] = result["adjusted_score"].rank(method="min", ascending=False).astype("Int64")
    missing_metric = result["raw_ppa"].isna()
    result.loc[missing_metric, "adjustment_note"] = "PPA unavailable for this view"
    small_sample = result["raw_ppa"].notna() & result["performance_z"].isna()
    result.loc[small_sample, "adjustment_note"] = "Fewer than two valid weekly performances"
    return result


def metric_label(side, suffix):
    label = METRIC_LABELS[suffix]
    if side == "defense":
        if suffix in ("plays", "drives"):
            return f"Defensive {label.lower()}"
        if suffix != "stuffrate":
            return label + " allowed"
    return label


def best_ascending(field, side):
    if field in ("raw_rank", "adjusted_rank", "team", "opponent", "conference", "game_id", "kickoff", "rating_completed_at"):
        return True
    if field in ("adjusted_score", "opponent_bg_rating"):
        return False
    suffix = field.removeprefix(f"{side}_")
    if suffix in ("plays", "drives"):
        return False
    if suffix == "stuffrate":
        return side == "offense"
    return side == "defense"


def sort_performances(frame, field, ascending):
    columns = list(dict.fromkeys([field, "raw_rank", "team", "opponent", "game_id"]))
    return frame.sort_values(columns, ascending=[ascending if col == field else True for col in columns],
                             na_position="last", kind="stable")


def filter_performances(frame, conferences=(), teams=()):
    result = frame
    if conferences:
        result = result.loc[result["conference"].isin(conferences)]
    if teams:
        result = result.loc[result["team"].isin(teams)]
    return result.copy()


def effective_mode(frame, requested):
    return "BG-adjusted" if requested == "BG-adjusted" and frame["adjusted_score"].notna().any() else "Raw PPA"

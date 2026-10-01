"""Read-only weekly game data and transparent BG opponent-adjusted rankings.

Transforms are independent of Streamlit so scoring and historical cutoffs can be
tested without a database or a running page.
"""

import numpy as np
import pandas as pd

from utils.report_card_grades import percentile_grade


# Bump when the page/helper contract or cached grade-baseline shape changes.
WEEKLY_API_VERSION = 2
OPPONENT_WEIGHT = 0.25
GRADE_COLUMNS = {
    "season_offense": "Season offense",
    "season_defense": "Season defense",
    "game_offense": "Game offense",
    "game_defense": "Game defense",
    "season_overall": "Season overall",
    "game_overall": "Game overall",
}
GRADE_CONTEXT_COLUMNS = {
    "peer_group": "Comparison scale",
    "rating_coverage": "Pregame rating coverage",
    "grade_status": "Grade availability",
}
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
    return load_pregame_ratings(frame, season)


def load_pregame_ratings(frame, season):
    """Attach historical opponent context in two batched, read-only queries."""
    from utils.db import read_df

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


def load_grade_baselines(season):
    """Load FBS season totals and every completed FBS matchup, including missing stats.

    Schedule rows survive the left join so missing advanced statistics cannot
    hide a gap in a team's pregame rating coverage.
    """
    from utils.db import read_df

    params = {"season": int(season)}
    season_stats = read_df("""
        SELECT s.team, s.conference, s.offense_ppa, s.defense_ppa
        FROM public.team_advanced_season_stats s
        WHERE s.season = :season AND EXISTS (
            SELECT 1 FROM public.game_data g
            WHERE g.season = s.season AND (
                (g.hometeam = s.team AND LOWER(g.homeclassification) = 'fbs') OR
                (g.awayteam = s.team AND LOWER(g.awayclassification) = 'fbs')
            )
        )
    """, params=params)
    game_stats = read_df("""
        SELECT g.id AS game_id, g.season, g.week,
               LOWER(COALESCE(g.seasontype, 'regular')) AS season_type,
               participants.team, participants.opponent, participants.conference,
               'fbs' AS classification, g.startdate, g.starttimetbd,
               gs.offense_ppa, gs.defense_ppa, gs.offense_plays, gs.defense_plays
        FROM public.game_data g
        CROSS JOIN LATERAL (VALUES
            (g.hometeam, g.awayteam, g.homeconference),
            (g.awayteam, g.hometeam, g.awayconference)
        ) AS participants(team, opponent, conference)
        LEFT JOIN public.team_advanced_game_stats gs
          ON gs.game_id = g.id AND gs.season = g.season AND gs.team = participants.team
        WHERE g.season = :season AND g.completed IS TRUE
          AND LOWER(g.homeclassification) = 'fbs'
          AND LOWER(g.awayclassification) = 'fbs'
          AND g.hometeam IS NOT NULL AND g.awayteam IS NOT NULL
          AND g.hometeam <> g.awayteam
        ORDER BY g.startdate NULLS LAST, g.id, participants.team
    """, params=params)
    if not game_stats.empty:
        if game_stats.duplicated(["season", "game_id", "team"]).any():
            raise ValueError("Duplicate team-game advanced-stat rows were found.")
        game_stats["kickoff"] = pd.to_datetime(game_stats["startdate"], utc=True, errors="coerce")
        game_stats["reliable_kickoff"] = game_stats["kickoff"].notna() & ~game_stats["starttimetbd"].eq(True)
        game_stats, note = load_pregame_ratings(game_stats, season)
        game_stats.attrs["rating_note"] = note
    return season_stats, game_stats


def grade_peer_groups(frame):
    """Use selected-season conferences; G5 denotes all identified non-P4 FBS teams."""
    conferences = frame["conference"].astype("string").fillna("").str.strip().str.casefold()
    teams = frame["team"].astype("string").fillna("").str.strip().str.casefold()
    groups = pd.Series("G5", index=frame.index, dtype="object")
    groups.loc[conferences.isin(["", "unknown"])] = None
    power = conferences.isin(["sec", "acc", "big ten", "big 10", "big 12"])
    groups.loc[power | teams.isin(["notre dame", "notre dame fighting irish"])] = "P4"
    return groups


def grade_metrics(frame, require_plays=False):
    """Three independent performance measures, all oriented higher-is-better."""
    values = {}
    for side in ("offense", "defense"):
        values[side] = numeric(frame[f"{side}_ppa"])
        if require_plays:
            values[side] = values[side].where(numeric(frame[f"{side}_plays"]) > 0)
    values["overall"] = values["offense"] - values["defense"]
    values["defense"] = -values["defense"]
    return pd.DataFrame(values, index=frame.index)


def adjusted_grade_scores(values, baseline, opponent_strength):
    """Use one season-wide reference distribution, even for selected-week values."""
    scores = pd.DataFrame(np.nan, index=values.index, columns=values.columns)
    for metric in values:
        reference = baseline[metric].dropna()
        if len(reference) < 2:
            continue
        deviation = reference.std(ddof=0)
        performance = (values[metric] - reference.mean()) / deviation if deviation else values[metric] * 0.0
        scores[metric] = performance + OPPONENT_WEIGHT * opponent_strength
    return scores


def peer_percentile_grades(scores, baseline, groups, baseline_groups):
    grades = pd.DataFrame(np.nan, index=scores.index, columns=scores.columns)
    for group in ("P4", "G5"):
        selected = groups.eq(group)
        for metric in scores:
            reference = baseline.loc[baseline_groups.eq(group), metric].dropna()
            if len(reference) >= 2:
                grades.loc[selected, metric] = scores.loc[selected, metric].map(
                    lambda value: percentile_grade(reference, value))
    return grades


def rating_coverage(frame):
    """Count schedule appearances independently of PPA/play-count availability."""
    return frame.assign(opponent_strength_z=numeric(frame["opponent_strength_z"])).groupby("team").agg(
        total=("opponent_strength_z", "size"), rated=("opponent_strength_z", "count"),
        strength=("opponent_strength_z", "mean"))


def grade_availability(row, scope, rated, total):
    if not total:
        return "No completed FBS games" if scope == "season" else "No qualifying game this week"
    if rated < total:
        return "Incomplete pregame ratings"
    if pd.isna(row["peer_group"]):
        return "Peer group unavailable"
    if row[[f"{scope}_{metric}" for metric in ("offense", "defense", "overall")]].isna().any():
        return "Missing PPA or fewer than two valid comparison observations"
    return ""


def build_grade_comparison(frame, season_stats, game_stats, mode="Raw PPA"):
    """One row per team with independently graded offense, defense and net PPA.

    Season values always use the latest stored totals. Adjusted season bonuses
    require complete FBS schedule coverage. Only the final adjusted percentiles
    are split into peer groups; both z-score components use FBS populations.
    """
    columns = ["team", "conference", "offense_ppa", "defense_ppa"]
    game_columns = [*columns, "offense_plays", "defense_plays", "opponent_strength_z"]
    season_stats = season_stats.reindex(columns=columns).reset_index(drop=True)
    game_stats = game_stats.reindex(columns=game_columns).reset_index(drop=True)
    frame = frame.reindex(columns=game_columns).reset_index(drop=True)
    season_values = grade_metrics(season_stats)
    game_values = grade_metrics(frame, require_plays=True)
    game_baseline = grade_metrics(game_stats, require_plays=True)
    if mode == "BG-adjusted":
        season_coverage = rating_coverage(game_stats)
        week_coverage = rating_coverage(frame)
        complete_strength = season_coverage["strength"].where(season_coverage["rated"].eq(season_coverage["total"]))
        season_scores = adjusted_grade_scores(season_values, season_values, season_stats["team"].map(complete_strength))
        baseline_scores = adjusted_grade_scores(game_baseline, game_baseline, numeric(game_stats["opponent_strength_z"]))
        game_scores = adjusted_grade_scores(game_values, game_baseline, numeric(frame["opponent_strength_z"]))
        season_groups = grade_peer_groups(season_stats)
        season_grades = peer_percentile_grades(season_scores, season_scores, season_groups, season_groups)
        game_grades = peer_percentile_grades(game_scores, baseline_scores, grade_peer_groups(frame), grade_peer_groups(game_stats))
    else:
        season_grades = season_values.apply(lambda values: values.map(lambda value: percentile_grade(values, value)))
        game_grades = pd.DataFrame({metric: game_values[metric].map(
            lambda value: percentile_grade(game_baseline[metric], value)) for metric in game_values})
    season_grades = pd.concat([season_stats[["team", "conference"]], season_grades.add_prefix("season_")], axis=1)
    game_grades = pd.concat([frame[["team"]], game_grades.add_prefix("game_")], axis=1)
    game_grades = game_grades.groupby("team", as_index=False).agg(
        {f"game_{metric}": lambda values: values.mean(skipna=False) for metric in game_values})
    result = season_grades.merge(game_grades, on="team", how="outer", validate="one_to_one")
    conferences = frame.drop_duplicates("team").set_index("team")["conference"]
    result["conference"] = result["team"].map(conferences).fillna(result["conference"]).fillna("Unknown")
    if mode == "BG-adjusted":
        result["peer_group"] = grade_peer_groups(result)
        coverage_labels, statuses = [], []
        for _, row in result.iterrows():
            labels, notes = [], []
            for scope, coverage in (("season", season_coverage), ("game", week_coverage)):
                counts = coverage.reindex([row["team"]]).fillna(0).iloc[0]
                rated, total = int(counts["rated"]), int(counts["total"])
                label = "Season" if scope == "season" else "Week"
                labels.append(f"{label} {rated}/{total}")
                note = grade_availability(row, scope, rated, total)
                if note:
                    notes.append(f"{label}: {note}")
            coverage_labels.append(" · ".join(labels))
            statuses.append(" · ".join(notes) or "Available")
        result["rating_coverage"] = coverage_labels
        result["grade_status"] = statuses
    return result.sort_values(["game_overall", "season_overall", "team"],
                              ascending=[False, False, True], na_position="last").reset_index(drop=True)


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

"""Read-only season snapshots and pure transformations for league predictions."""

from datetime import date

import pandas as pd


WIN_BUCKETS = [f"probability_{wins}_wins" for wins in range(14)]
CHANGE_METRICS = [
    "projected_wins", "playoff_prob", "conference_champion_prob", "national_champion_prob",
]
LABELS = {
    "team": "Team", "conference": "Conference",
    "projected_wins": "Projected wins", "projected_losses": "Projected losses",
    "projected_conference_wins": "Conference wins",
    "projected_conference_losses": "Conference losses",
    "conference_championship_game_prob": "Conference title game %",
    "conference_champion_prob": "Conference title %", "playoff_prob": "CFP %",
    "cfp_auto_bid_prob": "Automatic bid %", "cfp_at_large_prob": "At-large bid %",
    "cfp_bye_prob": "CFP bye %", "national_championship_game_prob": "National title game %",
    "national_champion_prob": "National title %", "bowl_eligible_prob": "Bowl eligible %",
    "projected_ap_ranking": "Projected AP rank", "projected_cfp_ranking": "Projected CFP rank",
    "resume_ranking": "Projected résumé rank", "strength_of_schedule": "Schedule strength",
    "remaining_strength_of_schedule": "Remaining schedule strength",
    "expected_number_of_wins": "Expected wins",
}
LABELS.update({column: f"Exactly {i} wins %" if i < 13 else "13+ wins %"
               for i, column in enumerate(WIN_BUCKETS)})
LABELS.update({f"probability_{i}_plus_wins": f"{i}+ wins %" for i in (8, 10, 11, 12)})
LABELS.update({f"{column}_change": LABELS[column].replace(" %", "") +
               (" change (wins)" if column == "projected_wins" else " change (pp)")
               for column in CHANGE_METRICS})
PROBABILITIES = {column for column in LABELS
                 if column.endswith("_prob") or column.startswith("probability_")}
RANKS = {"projected_ap_ranking", "projected_cfp_ranking", "resume_ranking"}
CHAMPIONSHIP_FIELDS = ["conference_championship_game_prob", "conference_champion_prob"]
PRESETS = {
    "Overview": ["projected_wins", "projected_losses", "projected_conference_wins",
                 "conference_champion_prob", "playoff_prob", "national_champion_prob", "bowl_eligible_prob"],
    "CFP Race": ["playoff_prob", "cfp_auto_bid_prob", "cfp_at_large_prob", "cfp_bye_prob",
                 "national_championship_game_prob", "national_champion_prob"],
    "Conference Race": ["projected_conference_wins", "projected_conference_losses",
                        *CHAMPIONSHIP_FIELDS, "playoff_prob"],
    "Win Outlook": ["projected_wins", "projected_losses", "bowl_eligible_prob",
                    *[f"probability_{i}_plus_wins" for i in (8, 10, 11, 12)]],
    "Rankings & Schedule": ["projected_ap_ranking", "projected_cfp_ranking", "resume_ranking",
                            "strength_of_schedule", "remaining_strength_of_schedule"],
}
WIN_NOTE = ("Projected wins/losses and win distributions include conference championship games "
            "and exclude simulated CFP wins. The final win bucket is 13 or more. "
            "Bowl eligibility uses the model’s regular-season six-win threshold.")


def load_runs() -> pd.DataFrame:
    from utils.db import read_df

    return read_df("""
        SELECT season_prediction_run_id, season, run_date, run_type, status,
               completed_at, created_at, model_version, simulations, row_count
        FROM public.season_prediction_runs
        WHERE status = 'success' AND run_type IN ('manual', 'nightly')
        ORDER BY season DESC, completed_at DESC NULLS LAST,
                 created_at DESC NULLS LAST, season_prediction_run_id DESC
    """)


def select_snapshot(runs: pd.DataFrame, season: int, cutoff=None) -> pd.Series | None:
    """Choose a coherent successful run; cutoff is an inclusive run-date limit."""
    if runs.empty:
        return None
    eligible = runs.loc[(runs["season"] == season) & (runs["status"] == "success") &
                        runs["run_type"].isin(["nightly", "manual"])].copy()
    if cutoff is not None:
        eligible = eligible.loc[pd.to_datetime(eligible["run_date"]).dt.date <= cutoff]
    if eligible.empty:
        return None
    for column in ("completed_at", "created_at"):
        eligible[column] = pd.to_datetime(eligible[column], utc=True)
    eligible["_id"] = eligible["season_prediction_run_id"].astype(str)
    return eligible.sort_values(["completed_at", "created_at", "_id"],
                                ascending=False, na_position="last").iloc[0].drop(labels="_id")


def comparison_snapshot(runs: pd.DataFrame, current: pd.Series, comparison_date: date | None) -> pd.Series | None:
    """Find a prior snapshot on or before the calendar date, within this season."""
    if comparison_date is None:
        return None
    cutoff = pd.Timestamp(comparison_date).date()
    if cutoff >= pd.Timestamp(current["run_date"]).date():
        return None
    return select_snapshot(runs, int(current["season"]), cutoff)


def model_changed(current: pd.Series, previous: pd.Series | None) -> bool:
    return previous is not None and current.get("model_version") != previous.get("model_version")


def load_snapshot(run_id: str) -> pd.DataFrame:
    from utils.db import read_df

    return prepare_snapshot(read_df("""
        SELECT sp.* FROM public.season_predictions_full sp
        WHERE sp.season_prediction_run_id = :run_id
          AND LOWER(sp.classification) = 'fbs'
        ORDER BY sp.team
    """, params={"run_id": str(run_id)}))


def independent_mask(conferences: pd.Series) -> pd.Series:
    return conferences.fillna("").str.contains("independent", case=False, regex=False)


def prepare_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if "classification" in result:
        result = result.loc[result["classification"].str.lower() == "fbs"].copy()
    for column in LABELS:
        if column not in ("team", "conference"):
            result[column] = pd.to_numeric(result.get(column, float("nan")), errors="coerce")
    if "conference" not in result:
        result["conference"] = "Unknown"
    result["conference"] = result["conference"].fillna("Unknown")
    result.loc[independent_mask(result["conference"]), CHAMPIONSHIP_FIELDS] = float("nan")
    for threshold in (8, 10, 11, 12):
        columns = WIN_BUCKETS[threshold:]
        result[f"probability_{threshold}_plus_wins"] = result[columns].sum(axis=1, min_count=len(columns))
    return result


def add_changes(current: pd.DataFrame, previous: pd.DataFrame | None) -> pd.DataFrame:
    result = current.drop(columns=[f"{c}_change" for c in CHANGE_METRICS], errors="ignore").copy()
    if previous is None or previous.empty:
        for column in CHANGE_METRICS:
            result[f"{column}_change"] = float("nan")
        return result
    historical = previous[["season", "team", *CHANGE_METRICS]].rename(
        columns={column: f"{column}_previous" for column in CHANGE_METRICS})
    result = result.merge(historical, on=["season", "team"], how="left", validate="one_to_one")
    for column in CHANGE_METRICS:
        scale = 1 if column == "projected_wins" else 100
        result[f"{column}_change"] = (result[column] - result[f"{column}_previous"]) * scale
    return result.drop(columns=[f"{c}_previous" for c in CHANGE_METRICS])


def sort_teams(frame: pd.DataFrame, field="playoff_prob", ascending=False) -> pd.DataFrame:
    columns = list(dict.fromkeys([field, "projected_wins", "team"]))
    directions = [ascending if column == field else column == "team" for column in columns]
    return frame.sort_values(columns, ascending=directions, na_position="last", kind="stable")


def filter_teams(frame, conferences=(), teams=(), metric=None, minimum=None, maximum=None):
    result = frame
    if conferences:
        result = result.loc[result["conference"].isin(conferences)]
    if teams:
        result = result.loc[result["team"].isin(teams)]
    if metric:
        if minimum is not None:
            result = result.loc[result[metric] >= minimum]
        if maximum is not None:
            result = result.loc[result[metric] <= maximum]
    return result.copy()


def conference_summary(frame: pd.DataFrame) -> pd.DataFrame:
    records = []
    for conference, members in frame.groupby("conference", dropna=False):
        ranked = sort_teams(members.dropna(subset=["conference_champion_prob"]), "conference_champion_prob")
        favorite = ranked.iloc[0] if len(ranked) else None
        runner = ranked.iloc[1] if len(ranked) > 1 else None
        is_independent = independent_mask(pd.Series([conference])).iloc[0]
        records.append({
            "conference": conference, "teams": len(members),
            "favorite": favorite["team"] if favorite is not None else ("Not applicable" if is_independent else None),
            "favorite_prob": favorite["conference_champion_prob"] if favorite is not None else float("nan"),
            "runner_up": runner["team"] if runner is not None else ("Not applicable" if is_independent else None),
            "runner_up_prob": runner["conference_champion_prob"] if runner is not None else float("nan"),
            "lead_pp": (favorite["conference_champion_prob"] - runner["conference_champion_prob"]) * 100
            if favorite is not None and runner is not None else float("nan"),
            "expected_cfp": members["playoff_prob"].sum(min_count=len(members)),
        })
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).sort_values(["expected_cfp", "conference"], ascending=[False, True], na_position="last")

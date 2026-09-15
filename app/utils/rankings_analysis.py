"""Pure comparisons for the rankings page; input frames are never modified."""

from datetime import date, timedelta

import numpy as np
import pandas as pd


def ranked_teams(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.reindex(columns=["team", "rank", "logo", "power_rating", "next_game_label"]).copy()
    for column in ("rank", "power_rating"):
        result[column] = pd.to_numeric(result[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    result = result.dropna(subset=["team", "rank"])
    result = result.loc[result["rank"].ge(1)]
    return result.sort_values(["rank", "team"], kind="stable").drop_duplicates("team").reset_index(drop=True)


def build_poll_comparison(poll: pd.DataFrame, ratings: pd.DataFrame) -> pd.DataFrame:
    official = ranked_teams(poll)
    official = official.loc[official["rank"].le(25), ["team", "rank", "logo"]]
    rated = ranked_teams(ratings)
    comparison = official.rename(columns={"rank": "poll_rank", "logo": "poll_logo"}).merge(
        rated.rename(columns={"rank": "rating_rank", "logo": "rating_logo"}),
        on="team", how="outer", validate="one_to_one",
    )
    comparison["logo"] = comparison["poll_logo"].combine_first(comparison["rating_logo"])
    comparison["in_poll"] = comparison["poll_rank"].notna()
    comparison["in_ratings"] = comparison["rating_rank"].le(25)
    comparison["gap"] = comparison["rating_rank"] - comparison["poll_rank"]
    comparison["gap_is_minimum"] = ~comparison["in_poll"] & comparison["in_ratings"]
    lower_bound = comparison["gap_is_minimum"]
    comparison.loc[lower_bound, "gap"] = comparison.loc[lower_bound, "rating_rank"] - 26
    # An absent source is unavailable, not evidence that every team is unranked.
    if official.empty or rated.empty:
        comparison["gap"] = np.nan
        comparison["gap_is_minimum"] = False
    comparison["abs_gap"] = comparison["gap"].abs()
    return comparison.loc[comparison["in_poll"] | comparison["in_ratings"]].sort_values(
        ["abs_gap", "rating_rank", "team"], ascending=[False, True, True], na_position="last",
    ).reset_index(drop=True)


def disagreement_shortlists(comparison: pd.DataFrame, limit: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    ordered = comparison.sort_values(["abs_gap", "rating_rank", "team"], ascending=[False, True, True])
    return ordered.loc[ordered["gap"].gt(0)].head(limit), ordered.loc[ordered["gap"].lt(0)].head(limit)


def build_bubble_watch(ratings: pd.DataFrame, poll: pd.DataFrame | None = None) -> pd.DataFrame:
    rated = ranked_teams(ratings)
    bubble = rated.loc[rated["rank"].between(26, 30)].copy()
    cutoff = rated.loc[rated["rank"].eq(25), "power_rating"]
    bubble["points_to_top25"] = cutoff.iloc[0] - bubble["power_rating"] if not cutoff.empty else np.nan
    official = ranked_teams(pd.DataFrame() if poll is None else poll)
    official = official.loc[official["rank"].le(25), ["team", "rank"]]
    return bubble.merge(official.rename(columns={"rank": "poll_rank"}), on="team", how="left")


def build_rank_movements(current: pd.DataFrame, previous: pd.DataFrame, *, poll: bool = False) -> pd.DataFrame:
    now, before = ranked_teams(current), ranked_teams(previous)
    if poll:
        now, before = now.loc[now["rank"].le(25)], before.loc[before["rank"].le(25)]
    fields = ["team", "rank", "logo", "power_rating"]
    movement = now[fields].rename(columns={field: f"current_{field}" for field in fields if field != "team"}).merge(
        before[fields].rename(columns={field: f"previous_{field}" for field in fields if field != "team"}),
        on="team", how="outer", validate="one_to_one",
    )
    movement["logo"] = movement["current_logo"].combine_first(movement["previous_logo"])
    movement["rank_change"] = movement["previous_rank"] - movement["current_rank"]
    movement["rating_change"] = movement["current_power_rating"] - movement["previous_power_rating"]
    current_top25 = movement["current_rank"].le(25)
    previous_top25 = movement["previous_rank"].le(25)
    movement["entered_top25"] = current_top25 & ~previous_top25
    movement["left_top25"] = previous_top25 & ~current_top25
    if not poll:
        # A missing ratings record is not a known previous/current rank below #25.
        movement["entered_top25"] &= movement["previous_rank"].notna()
        movement["left_top25"] &= movement["current_rank"].notna()
    if now.empty or before.empty:
        return movement.iloc[:0]
    return movement.sort_values(["current_rank", "previous_rank", "team"], na_position="last").reset_index(drop=True)


def movement_shortlists(movement: pd.DataFrame, limit: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    risers = movement.loc[movement["rank_change"].gt(0)].sort_values(
        ["rank_change", "current_rank", "team"], ascending=[False, True, True],
    ).head(limit)
    fallers = movement.loc[movement["rank_change"].lt(0)].sort_values(
        ["rank_change", "current_rank", "team"], ascending=[True, True, True],
    ).head(limit)
    return risers, fallers


def available_rating_dates(runs: pd.DataFrame) -> list[date]:
    dates = pd.to_datetime(runs.get("completed_date", pd.Series(dtype="object")), errors="coerce").dropna()
    return sorted(set(dates.dt.date))


def resolve_rating_date(runs: pd.DataFrame, requested: date | None) -> date | None:
    if requested is None:
        return None
    eligible = [day for day in available_rating_dates(runs) if day <= requested]
    return eligible[-1] if eligible else None


def comparison_date_bounds(runs: pd.DataFrame, current: date | None) -> tuple[date, date, date] | None:
    if current is None:
        return None
    earlier = [day for day in available_rating_dates(runs) if day < current]
    return (earlier[0], current - timedelta(days=1), earlier[-1]) if earlier else None


def valid_comparison_date(saved: date | None, bounds: tuple[date, date, date]) -> date:
    minimum, maximum, default = bounds
    return saved if saved is not None and minimum <= saved <= maximum else default


def blend_rating_snapshot(power_df: pd.DataFrame, teamrankings: pd.DataFrame, weight: float) -> pd.DataFrame:
    """Blend one snapshot with TeamRankings data already selected for its own date."""
    if power_df.empty:
        return power_df.copy()
    out = power_df.copy()
    out["raw_power_rating"] = pd.to_numeric(out["power_rating"], errors="coerce")
    out["teamrankings_blend_weight"] = float(weight)
    if weight <= 0 or teamrankings.empty:
        out["rank"] = out["raw_power_rating"].rank(method="first", ascending=False).astype(int)
        return out.sort_values(["rank", "team"]).reset_index(drop=True)

    out = out.merge(teamrankings, on="team", how="left")
    shared = out["raw_power_rating"].notna() & out["teamrankings_rating"].notna()
    bg_mean = out.loc[shared, "raw_power_rating"].mean()
    bg_std = out.loc[shared, "raw_power_rating"].std(ddof=0)
    tr_mean = out.loc[shared, "teamrankings_rating"].mean()
    tr_std = out.loc[shared, "teamrankings_rating"].std(ddof=0)
    if shared.sum() < 2 or pd.isna(bg_std) or pd.isna(tr_std) or bg_std == 0 or tr_std == 0:
        out["power_rating"] = out["raw_power_rating"]
        out["rank"] = out["power_rating"].rank(method="first", ascending=False).astype(int)
        return out.sort_values(["rank", "team"]).reset_index(drop=True)

    out["teamrankings_scaled_rating"] = ((out["teamrankings_rating"] - tr_mean) / tr_std) * bg_std + bg_mean
    out["power_rating"] = (1 - weight) * out["raw_power_rating"] + weight * out["teamrankings_scaled_rating"]
    out["power_rating"] = out["power_rating"].where(out["teamrankings_scaled_rating"].notna(), out["raw_power_rating"])
    out = out.sort_values(["power_rating", "team"], ascending=[False, True]).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out

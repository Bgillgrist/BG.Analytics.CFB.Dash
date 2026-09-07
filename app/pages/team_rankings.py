import html
from datetime import date
from io import BytesIO
import re
import urllib.request
import zipfile

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from utils.db import read_df


POLL_LABELS = {
    "AP Poll": "AP Top 25",
    "Coaches Poll": "Coaches Poll",
    "CFP Rankings": "Playoff Committee Rankings",
}

PREDICTED_HOME_MARGIN_COLUMNS = [
    "predicted_home_margin",
    "home_predicted_margin",
    "projected_home_margin",
    "home_projected_margin",
    "home_margin",
    "margin_home",
]

HOME_SPREAD_COLUMNS = [
    "home_spread",
    "homespread",
    "predicted_home_spread",
    "home_predicted_spread",
    "projected_home_spread",
    "home_projected_spread",
]

GENERIC_SPREAD_COLUMNS = [
    "predicted_spread",
    "projected_spread",
    "spread",
]

HOME_WIN_PROBABILITY_COLUMNS = [
    "homewinprob",
    "home_win_probability",
    "home_win_prob",
    "homewinprobability",
    "home_win_pct",
    "home_wp",
]

AWAY_WIN_PROBABILITY_COLUMNS = [
    "awaywinprob",
    "away_win_probability",
    "away_win_prob",
    "awaywinprobability",
    "away_win_pct",
    "away_wp",
]

WIN_PROBABILITY_SPREAD_SCALE = 14.0
COMPLETED_GAME_WEIGHT = 1.0
PROJECTED_GAME_WEIGHT = 0.45
MAX_MARGIN_SIGNAL = 42.0
REGULAR_SEASON_FILTER = "LOWER(COALESCE(seasontype, 'regular')) <> 'postseason'"


st.markdown(
    """
    <style>
      .rankings-page {
        color: #0f172a;
      }
      .rankings-header {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 18px;
        margin: 0 0 18px 0;
      }
      .rankings-kicker {
        text-transform: uppercase;
        letter-spacing: .08em;
        font-size: 12px;
        font-weight: 800;
        color: #64748b;
        margin-bottom: 4px;
      }
      .rankings-title {
        font-size: 42px;
        line-height: 1;
        font-weight: 900;
        margin: 0 0 4px 0;
        color: #0f172a;
      }
      .rankings-subtitle {
        font-size: 15px;
        color: #475569;
        margin-top: 8px;
        max-width: 900px;
      }
      .board {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        background: #ffffff;
        overflow: hidden;
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.08);
        margin-bottom: 18px;
      }
      .board-head {
        padding: 14px 16px;
        background: #0f172a;
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }
      .board-title {
        font-size: 19px;
        line-height: 1.1;
        font-weight: 900;
        margin: 0;
      }
      .board-meta {
        font-size: 12px;
        color: #cbd5e1;
        white-space: nowrap;
      }
      .ranking-list {
        display: grid;
        grid-template-columns: repeat(5, minmax(0, 1fr));
        gap: 8px;
        padding: 12px;
      }
      .compact-list {
        display: grid;
        gap: 0;
        padding: 6px 10px 10px 10px;
      }
      .power-rating-scroll {
        box-sizing: border-box;
        max-height: 1366px;
        overflow-y: auto;
      }
      .power-rating-scroll:focus-visible {
        outline: 2px solid #2563eb;
        outline-offset: -2px;
      }
      @media (max-width: 640px) {
        .power-rating-scroll {
          max-height: 70vh;
        }
      }
      .compact-row {
        display: grid;
        grid-template-columns: 38px 42px minmax(0, 1fr) auto;
        align-items: center;
        gap: 10px;
        min-height: 54px;
        border-bottom: 1px solid #edf2f7;
      }
      .compact-row:last-child {
        border-bottom: 0;
      }
      .compact-rank {
        width: 30px;
        height: 30px;
        border-radius: 999px;
        background: #0f172a;
        color: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 13px;
        font-weight: 900;
      }
      .compact-logo {
        width: 34px;
        height: 34px;
        border-radius: 999px;
        border: 1px solid #e2e8f0;
        background: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
      }
      .compact-logo img {
        max-width: 82%;
        max-height: 82%;
        object-fit: contain;
      }
      .compact-team {
        min-width: 0;
      }
      .compact-team-name {
        font-size: 14px;
        line-height: 1.1;
        font-weight: 850;
        color: #0f172a;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .compact-sub {
        font-size: 10px;
        line-height: 1.15;
        color: #64748b;
        margin-top: 3px;
      }
      .compact-value {
        text-align: right;
        font-size: 14px;
        font-weight: 900;
        color: #0f172a;
        white-space: nowrap;
      }
      .ranking-card {
        min-height: 118px;
        padding: 10px;
        display: grid;
        grid-template-rows: auto 1fr auto;
        gap: 7px;
        border: 1px solid #e7edf5;
        border-radius: 8px;
        background: #ffffff;
      }
      .card-topline {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
      }
      .rank-pill {
        width: 30px;
        height: 30px;
        border-radius: 999px;
        background: #0f172a;
        color: white;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 900;
        font-size: 13px;
        flex: 0 0 auto;
      }
      .card-metric {
        min-width: 0;
        text-align: right;
      }
      .card-metric-main {
        font-weight: 950;
        font-size: 14px;
        line-height: 1;
        color: #0f172a;
      }
      .card-metric-sub {
        font-size: 10px;
        color: #64748b;
        margin-top: 2px;
      }
      .logo-wrap {
        width: 50px;
        height: 50px;
        border-radius: 999px;
        border: 1px solid #e2e8f0;
        background: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        margin: 0 auto;
      }
      .logo-wrap img {
        max-width: 82%;
        max-height: 82%;
        object-fit: contain;
      }
      .team-name {
        font-weight: 850;
        font-size: 13px;
        line-height: 1.12;
        color: #0f172a;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        text-align: center;
      }
      .team-sub {
        font-size: 10px;
        line-height: 1.15;
        color: #64748b;
        margin-top: 3px;
        text-align: center;
      }
      .empty-board {
        padding: 28px 16px;
        color: #64748b;
        font-weight: 650;
      }
      .stat-strip {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 10px;
        margin: 16px 0;
      }
      .stat-tile {
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 12px 14px;
        background: #ffffff;
      }
      .stat-label {
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: .06em;
        font-weight: 850;
        color: #64748b;
      }
      .stat-value {
        font-size: 23px;
        font-weight: 950;
        color: #0f172a;
        line-height: 1.1;
        margin-top: 4px;
      }
      @media (max-width: 900px) {
        .rankings-header { display: block; }
        .rankings-title { font-size: 34px; }
        .ranking-list { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        .stat-strip { grid-template-columns: repeat(2, 1fr); }
      }
      @media (max-width: 560px) {
        .ranking-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .compact-row { grid-template-columns: 34px 38px minmax(0, 1fr) auto; gap: 8px; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def first_existing(columns: set[str], candidates: list[str]) -> str | None:
    return next((col for col in candidates if col in columns), None)


@st.cache_data(ttl=300)
def get_table_columns(table_name: str) -> set[str]:
    df = read_df(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
        """,
        {"table_name": table_name},
    )
    return set(df["column_name"]) if not df.empty else set()


@st.cache_data(ttl=300)
def get_team_directory() -> pd.DataFrame:
    team_map_columns = get_table_columns("team_map")
    logo_col = next((col for col in ["Logo", "logo", "logo_url"] if col in team_map_columns), None)
    map_id_col = next((col for col in ["Id", "id", "team_id", "TeamId"] if col in team_map_columns), None)
    map_name_col = next((col for col in ["cfb_name", "team", "school", "Team"] if col in team_map_columns), None)

    logo_sql = f"tm.{quote_identifier(logo_col)} AS logo" if logo_col and (map_id_col or map_name_col) else "NULL::text AS logo"
    if map_id_col:
        join_sql = f"LEFT JOIN public.team_map tm ON ranked.team_id = tm.{quote_identifier(map_id_col)}::text"
    elif map_name_col:
        join_sql = (
            f"LEFT JOIN public.team_map tm "
            f"ON LOWER(TRIM(ranked.team)) = LOWER(TRIM(tm.{quote_identifier(map_name_col)}::text))"
        )
    else:
        join_sql = ""

    return read_df(
        f"""
        WITH team_rows AS (
            SELECT homeid::text AS team_id, hometeam AS team, MAX(season) AS last_seen
            FROM public.game_data
            WHERE homeid IS NOT NULL
              AND hometeam IS NOT NULL
              AND homeclassification = 'fbs'
              AND {REGULAR_SEASON_FILTER}
            GROUP BY homeid, hometeam

            UNION ALL

            SELECT awayid::text AS team_id, awayteam AS team, MAX(season) AS last_seen
            FROM public.game_data
            WHERE awayid IS NOT NULL
              AND awayteam IS NOT NULL
              AND awayclassification = 'fbs'
              AND {REGULAR_SEASON_FILTER}
            GROUP BY awayid, awayteam
        ),
        ranked AS (
            SELECT
                team_id,
                team,
                ROW_NUMBER() OVER (PARTITION BY team ORDER BY last_seen DESC) AS rn
            FROM team_rows
        )
        SELECT
            ranked.team_id,
            ranked.team,
            {logo_sql}
        FROM ranked
        {join_sql}
        WHERE ranked.rn = 1
        ORDER BY ranked.team
        """
    )


@st.cache_data(ttl=300)
def get_available_polls() -> list[tuple[str, str]]:
    df = read_df("SELECT DISTINCT poll FROM public.rankings ORDER BY poll")
    existing = set(df["poll"]) if not df.empty else set()
    return [(label, poll) for label, poll in POLL_LABELS.items() if poll in existing]


@st.cache_data(ttl=300)
def get_poll_seasons(poll: str) -> list[int]:
    df = read_df(
        """
        SELECT DISTINCT season::int AS season
        FROM public.rankings
        WHERE poll = :poll
        ORDER BY season DESC
        """,
        {"poll": poll},
    )
    return df["season"].astype(int).tolist() if not df.empty else []


@st.cache_data(ttl=300)
def get_poll_weeks(poll: str, season: int) -> list[int]:
    df = read_df(
        """
        SELECT DISTINCT week::int AS week
        FROM public.rankings
        WHERE poll = :poll
          AND season = :season
        ORDER BY week
        """,
        {"poll": poll, "season": int(season)},
    )
    return df["week"].astype(int).tolist() if not df.empty else []


@st.cache_data(ttl=300)
def get_poll_rankings(poll: str, season: int, week: int) -> pd.DataFrame:
    df = read_df(
        """
        SELECT rank::int AS rank, school AS team
        FROM public.rankings
        WHERE poll = :poll
          AND season = :season
          AND week = :week
        ORDER BY rank
        """,
        {"poll": poll, "season": int(season), "week": int(week)},
    )
    return attach_assets(df)


@st.cache_data(ttl=300)
def get_teamrankings_snapshot(season: int, as_of_date: date | None) -> pd.DataFrame:
    if not isinstance(season, int):
        return pd.DataFrame()

    table_columns = get_table_columns("teamrankings_predictive_ratings")
    required_columns = {"season", "pull_date", "team", "rating"}
    if not required_columns.issubset(table_columns):
        return pd.DataFrame()

    date_filter = "AND pull_date <= :as_of_date" if as_of_date is not None else ""
    df = read_df(
        f"""
        SELECT DISTINCT ON (team)
            team,
            rank::int AS teamrankings_rank,
            rating::float AS teamrankings_rating,
            pull_date AS teamrankings_pull_date
        FROM public.teamrankings_predictive_ratings
        WHERE season = :season
          AND rating IS NOT NULL
          {date_filter}
        ORDER BY team, pull_date DESC
        """,
        {"season": int(season), "as_of_date": as_of_date},
    )
    if df.empty:
        return df
    df["teamrankings_rating"] = pd.to_numeric(df["teamrankings_rating"], errors="coerce")
    return df.dropna(subset=["team", "teamrankings_rating"])


def blend_power_with_teamrankings(
    power_df: pd.DataFrame,
    season: int | None,
    as_of_date: date | None,
    teamrankings_weight: float,
) -> pd.DataFrame:
    if power_df.empty or not isinstance(season, int):
        return power_df

    out = power_df.copy()
    out["raw_power_rating"] = pd.to_numeric(out["power_rating"], errors="coerce")
    out["teamrankings_blend_weight"] = float(teamrankings_weight)
    if teamrankings_weight <= 0:
        out["rank"] = out["raw_power_rating"].rank(method="first", ascending=False).astype(int)
        return out.sort_values(["rank", "team"]).reset_index(drop=True)

    teamrankings = get_teamrankings_snapshot(season, as_of_date)
    if teamrankings.empty:
        out["rank"] = out["raw_power_rating"].rank(method="first", ascending=False).astype(int)
        return out.sort_values(["rank", "team"]).reset_index(drop=True)

    out = out.merge(teamrankings, on="team", how="left")
    shared = out["raw_power_rating"].notna() & out["teamrankings_rating"].notna()
    if shared.sum() < 2:
        out["power_rating"] = out["raw_power_rating"]
        out["rank"] = out["power_rating"].rank(method="first", ascending=False).astype(int)
        return out.sort_values(["rank", "team"]).reset_index(drop=True)

    bg_mean = out.loc[shared, "raw_power_rating"].mean()
    bg_std = out.loc[shared, "raw_power_rating"].std(ddof=0)
    tr_mean = out.loc[shared, "teamrankings_rating"].mean()
    tr_std = out.loc[shared, "teamrankings_rating"].std(ddof=0)
    if pd.isna(bg_std) or pd.isna(tr_std) or bg_std == 0 or tr_std == 0:
        out["power_rating"] = out["raw_power_rating"]
        out["rank"] = out["power_rating"].rank(method="first", ascending=False).astype(int)
        return out.sort_values(["rank", "team"]).reset_index(drop=True)

    out["teamrankings_scaled_rating"] = (
        ((out["teamrankings_rating"] - tr_mean) / tr_std) * bg_std
    ) + bg_mean
    out["power_rating"] = (
        (1.0 - teamrankings_weight) * out["raw_power_rating"]
        + teamrankings_weight * out["teamrankings_scaled_rating"]
    )
    out["power_rating"] = out["power_rating"].where(
        out["teamrankings_scaled_rating"].notna(),
        out["raw_power_rating"],
    )
    out = out.sort_values(["power_rating", "team"], ascending=[False, True]).reset_index(drop=True)
    out["rank"] = np.arange(1, len(out) + 1)
    return out


@st.cache_data(ttl=300)
def get_power_rating_seasons() -> list[int]:
    df = read_df(
        f"""
        SELECT season
        FROM (
            SELECT DISTINCT season::int AS season
            FROM public.game_data
            WHERE season IS NOT NULL
              AND homeclassification = 'fbs'
              AND awayclassification = 'fbs'
              AND {REGULAR_SEASON_FILTER}

            UNION

            SELECT DISTINCT season::int AS season
            FROM public.team_rating_runs
            WHERE season IS NOT NULL
              AND status = 'success'
        ) seasons
        ORDER BY season DESC
        """
    )
    return df["season"].astype(int).tolist() if not df.empty else []


@st.cache_data(ttl=300)
def get_team_rating_run_dates(season: int) -> pd.DataFrame:
    if season < 2026:
        return pd.DataFrame()

    table_columns = get_table_columns("team_rating_runs")
    if not {"season", "status", "team_rating_run_id"}.issubset(table_columns):
        return pd.DataFrame()

    completed_expr = "completed_at" if "completed_at" in table_columns else "created_at"
    run_date_expr = "run_date" if "run_date" in table_columns else f"{completed_expr}::date"

    df = read_df(
        f"""
        SELECT
            {completed_expr}::date AS completed_date,
            MAX({completed_expr}) AS latest_completed_at,
            COUNT(*)::int AS run_count
        FROM public.team_rating_runs
        WHERE season = :season
          AND status = 'success'
          AND {completed_expr} IS NOT NULL
        GROUP BY {completed_expr}::date

        UNION

        SELECT
            {run_date_expr}::date AS completed_date,
            MAX({completed_expr}) AS latest_completed_at,
            COUNT(*)::int AS run_count
        FROM public.team_rating_runs
        WHERE season = :season
          AND status = 'success'
          AND {run_date_expr} IS NOT NULL
          AND {completed_expr} IS NULL
        GROUP BY {run_date_expr}::date
        ORDER BY completed_date DESC
        """,
        {"season": int(season)},
    )
    if df.empty:
        return df
    df["completed_date"] = pd.to_datetime(df["completed_date"], errors="coerce").dt.date
    return df.dropna(subset=["completed_date"])


def implied_margin_from_probability(probability: pd.Series) -> pd.Series:
    probs = probability.astype(float).clip(0.01, 0.99)
    return WIN_PROBABILITY_SPREAD_SCALE * np.log(probs / (1 - probs))


def get_prediction_margin_select(prediction_columns: set[str]) -> tuple[str, str]:
    for col in PREDICTED_HOME_MARGIN_COLUMNS:
        if col in prediction_columns:
            return f"p.{quote_identifier(col)}::float", col

    for col in HOME_SPREAD_COLUMNS:
        if col in prediction_columns:
            return f"(-1 * p.{quote_identifier(col)}::float)", col

    for col in GENERIC_SPREAD_COLUMNS:
        if col in prediction_columns:
            return f"(-1 * p.{quote_identifier(col)}::float)", col

    if first_existing(prediction_columns, HOME_WIN_PROBABILITY_COLUMNS):
        return "NULL::float", "winprob"

    if first_existing(prediction_columns, AWAY_WIN_PROBABILITY_COLUMNS):
        return "NULL::float", "winprob"

    return "NULL::float", "none"


def probability_sql(column: str) -> str:
    value_sql = f"p.{quote_identifier(column)}::float"
    return f"(CASE WHEN {value_sql} > 1 THEN {value_sql} / 100.0 ELSE {value_sql} END)"


def prediction_table_sql(table_name: str) -> str:
    return f"public.{quote_identifier(table_name)}"


def get_prediction_source() -> tuple[str, set[str]]:
    prediction_columns = get_table_columns("game_predictions_full")
    if "gameid" in prediction_columns:
        return "game_predictions_full", prediction_columns
    return "game_predictions", get_table_columns("game_predictions")


def prediction_row_order_sql(prediction_columns: set[str]) -> str:
    order_columns = [
        col
        for col in ["updated_at", "created_at", "game_prediction_id", "id"]
        if col in prediction_columns and col != "gameid"
    ]
    if not order_columns:
        return ""
    return ", " + ", ".join(f"p.{quote_identifier(col)} DESC NULLS LAST" for col in order_columns)


def latest_prediction_ctes(table_name: str, run_columns: set[str], prediction_columns: set[str]) -> str:
    status_filter = (
        "AND LOWER(COALESCE(r.status, 'success')) IN ('success', 'succeeded', 'complete', 'completed')"
        if "status" in run_columns
        else ""
    )
    order_columns = [
        col
        for col in ["completed_at", "created_at", "game_prediction_run_id"]
        if col in run_columns
    ]
    order_sql = ", ".join(f"r.{quote_identifier(col)} DESC NULLS LAST" for col in order_columns)
    if not order_sql:
        order_sql = "r.game_prediction_run_id DESC"

    return f"""
        WITH latest_run AS (
            SELECT r.game_prediction_run_id
            FROM public.game_prediction_runs r
            WHERE r.season = :season
              {status_filter}
              AND EXISTS (
                  SELECT 1
                  FROM {prediction_table_sql(table_name)} p
                  WHERE p.game_prediction_run_id = r.game_prediction_run_id
              )
            ORDER BY {order_sql}
            LIMIT 1
        ),
        latest_predictions AS (
            SELECT DISTINCT ON (p.gameid)
                p.*
            FROM {prediction_table_sql(table_name)} p
            JOIN latest_run lr
              ON p.game_prediction_run_id = lr.game_prediction_run_id
            ORDER BY p.gameid{prediction_row_order_sql(prediction_columns)}
        )
    """


@st.cache_data(ttl=300)
def get_power_rating_games(season: int) -> tuple[pd.DataFrame, str]:
    prediction_table, prediction_columns = get_prediction_source()
    run_columns = get_table_columns("game_prediction_runs")
    margin_sql, margin_source = get_prediction_margin_select(prediction_columns)

    has_game_predictions = bool(prediction_columns and "gameid" in prediction_columns)
    home_probability_col = first_existing(prediction_columns, HOME_WIN_PROBABILITY_COLUMNS)
    away_probability_col = first_existing(prediction_columns, AWAY_WIN_PROBABILITY_COLUMNS)
    if home_probability_col:
        homewinprob_sql = f"{probability_sql(home_probability_col)} AS homewinprob"
    elif away_probability_col:
        homewinprob_sql = f"(1 - {probability_sql(away_probability_col)}) AS homewinprob"
    else:
        homewinprob_sql = "NULL::float AS homewinprob"

    if (
        has_game_predictions
        and "game_prediction_run_id" in prediction_columns
        and {"season", "game_prediction_run_id"}.issubset(run_columns)
    ):
        prediction_join_sql = f"""
        {latest_prediction_ctes(prediction_table, run_columns, prediction_columns)}
        SELECT
            g.id,
            g.hometeam,
            g.awayteam,
            g.homepoints,
            g.awaypoints,
            g.homeclassification,
            g.awayclassification,
            {margin_sql} AS predicted_home_margin,
            {homewinprob_sql}
        FROM public.game_data g
        LEFT JOIN latest_predictions p
          ON p.gameid = g.id::text
        WHERE g.season = :season
          AND g.hometeam IS NOT NULL
          AND g.awayteam IS NOT NULL
          AND g.homeclassification = 'fbs'
          AND g.awayclassification = 'fbs'
          AND LOWER(COALESCE(g.seasontype, 'regular')) <> 'postseason'
        """
    elif has_game_predictions:
        prediction_join_sql = f"""
        SELECT
            g.id,
            g.hometeam,
            g.awayteam,
            g.homepoints,
            g.awaypoints,
            g.homeclassification,
            g.awayclassification,
            {margin_sql} AS predicted_home_margin,
            {homewinprob_sql}
        FROM public.game_data g
        LEFT JOIN {prediction_table_sql(prediction_table)} p
          ON p.gameid = g.id::text
        WHERE g.season = :season
          AND g.hometeam IS NOT NULL
          AND g.awayteam IS NOT NULL
          AND g.homeclassification = 'fbs'
          AND g.awayclassification = 'fbs'
          AND LOWER(COALESCE(g.seasontype, 'regular')) <> 'postseason'
        """
    else:
        prediction_join_sql = """
        SELECT
            g.id,
            g.hometeam,
            g.awayteam,
            g.homepoints,
            g.awaypoints,
            g.homeclassification,
            g.awayclassification,
            NULL::float AS predicted_home_margin,
            NULL::float AS homewinprob
        FROM public.game_data g
        WHERE g.season = :season
          AND g.hometeam IS NOT NULL
          AND g.awayteam IS NOT NULL
          AND g.homeclassification = 'fbs'
          AND g.awayclassification = 'fbs'
          AND LOWER(COALESCE(g.seasontype, 'regular')) <> 'postseason'
        """

    df = read_df(prediction_join_sql, {"season": int(season)})
    return df, margin_source


@st.cache_data(ttl=300)
def get_power_rankings(season: int) -> pd.DataFrame:
    games, margin_source = get_power_rating_games(season)
    if games.empty:
        return pd.DataFrame()

    games = games.copy()
    games["homepoints"] = pd.to_numeric(games["homepoints"], errors="coerce")
    games["awaypoints"] = pd.to_numeric(games["awaypoints"], errors="coerce")
    games["predicted_home_margin"] = pd.to_numeric(games["predicted_home_margin"], errors="coerce")
    games["homewinprob"] = pd.to_numeric(games["homewinprob"], errors="coerce")
    games["completed"] = games["homepoints"].notna() & games["awaypoints"].notna()

    games["margin_signal"] = np.where(
        games["completed"],
        games["homepoints"] - games["awaypoints"],
        games["predicted_home_margin"],
    )
    if margin_source == "winprob":
        missing_projection = ~games["completed"] & games["margin_signal"].isna() & games["homewinprob"].notna()
        games.loc[missing_projection, "margin_signal"] = implied_margin_from_probability(
            games.loc[missing_projection, "homewinprob"]
        )

    games = games.dropna(subset=["margin_signal", "hometeam", "awayteam"]).copy()
    if games.empty:
        return pd.DataFrame()

    games["margin_signal"] = games["margin_signal"].clip(-MAX_MARGIN_SIGNAL, MAX_MARGIN_SIGNAL)
    games["weight"] = np.where(games["completed"], COMPLETED_GAME_WEIGHT, PROJECTED_GAME_WEIGHT)

    teams = sorted(pd.concat([games["hometeam"], games["awayteam"]]).dropna().unique())
    if len(teams) < 2:
        return pd.DataFrame()

    team_to_idx = {team: idx for idx, team in enumerate(teams)}
    num_teams = len(teams)
    rows = []
    targets = []
    weights = []

    for game in games.itertuples(index=False):
        row = np.zeros(num_teams + 1)
        row[team_to_idx[game.hometeam]] = 1.0
        row[team_to_idx[game.awayteam]] = -1.0
        row[-1] = 1.0
        rows.append(row)
        targets.append(float(game.margin_signal))
        weights.append(float(game.weight))

    # Anchor the rating scale so the average FBS team is 0.0.
    anchor = np.zeros(num_teams + 1)
    anchor[:num_teams] = 1.0
    rows.append(anchor)
    targets.append(0.0)
    weights.append(1000.0)

    matrix = np.vstack(rows)
    target = np.array(targets)
    sqrt_weights = np.sqrt(np.array(weights))
    solution, *_ = np.linalg.lstsq(matrix * sqrt_weights[:, None], target * sqrt_weights, rcond=None)

    ratings = pd.DataFrame(
        {
            "team": teams,
            "power_rating": solution[:num_teams],
        }
    )
    ratings["hfa"] = float(solution[-1])
    ratings["rank"] = ratings["power_rating"].rank(method="first", ascending=False).astype(int)

    completed_counts = games[games["completed"]].groupby("hometeam").size().add(
        games[games["completed"]].groupby("awayteam").size(),
        fill_value=0,
    )
    projected_counts = games[~games["completed"]].groupby("hometeam").size().add(
        games[~games["completed"]].groupby("awayteam").size(),
        fill_value=0,
    )
    ratings["completed_games"] = ratings["team"].map(completed_counts).fillna(0).astype(int)
    ratings["projected_games"] = ratings["team"].map(projected_counts).fillna(0).astype(int)
    ratings["margin_source"] = margin_source

    ratings = attach_assets(ratings)
    return ratings.sort_values("rank")


@st.cache_data(ttl=300)
def get_snapshot_power_rankings(season: int, completed_date: date | None) -> pd.DataFrame:
    if season < 2026 or completed_date is None:
        return pd.DataFrame()

    run_columns = get_table_columns("team_rating_runs")
    rating_columns = get_table_columns("team_ratings")
    if not {"team_rating_run_id", "season", "status"}.issubset(run_columns):
        return pd.DataFrame()
    if not {"team_rating_run_id", "team"}.issubset(rating_columns):
        return pd.DataFrame()

    completed_expr = "r.completed_at" if "completed_at" in run_columns else "r.created_at"
    selected_date_expr = f"{completed_expr}::date"
    run_date_select = "r.run_date" if "run_date" in run_columns else f"{selected_date_expr} AS run_date"
    completed_select = "r.completed_at" if "completed_at" in run_columns else "r.created_at AS completed_at"
    created_select = "r.created_at" if "created_at" in run_columns else f"{completed_expr} AS created_at"
    model_select = "r.model_version" if "model_version" in run_columns else "NULL::text AS model_version"
    hfa_run_select = (
        "r.home_field_advantage"
        if "home_field_advantage" in run_columns
        else "NULL::float AS home_field_advantage"
    )
    margin_run_select = "r.margin_source" if "margin_source" in run_columns else "NULL::text AS margin_source"

    rating_selects = [
        "t.team",
        "t.rank::int AS rank" if "rank" in rating_columns else "NULL::int AS rank",
        (
            "COALESCE(t.power_rating, t.team_rating)::float AS power_rating"
            if {"power_rating", "team_rating"}.issubset(rating_columns)
            else "t.power_rating::float AS power_rating"
            if "power_rating" in rating_columns
            else "t.team_rating::float AS power_rating"
            if "team_rating" in rating_columns
            else "NULL::float AS power_rating"
        ),
        (
            "t.home_field_advantage::float AS hfa"
            if "home_field_advantage" in rating_columns
            else "sr.home_field_advantage::float AS hfa"
        ),
        (
            "t.completed_games::int AS completed_games"
            if "completed_games" in rating_columns
            else "NULL::int AS completed_games"
        ),
        (
            "t.projected_games::int AS projected_games"
            if "projected_games" in rating_columns
            else "NULL::int AS projected_games"
        ),
        "t.margin_source" if "margin_source" in rating_columns else "sr.margin_source",
        "sr.team_rating_run_id",
        "sr.run_date",
        "sr.completed_at",
        "sr.created_at",
        "sr.model_version",
    ]
    rank_order_sql = "t.rank" if "rank" in rating_columns else "NULL"

    df = read_df(
        f"""
        WITH selected_run AS (
            SELECT
                r.team_rating_run_id,
                {run_date_select},
                {completed_select},
                {created_select},
                {model_select},
                {hfa_run_select},
                {margin_run_select}
            FROM public.team_rating_runs r
            WHERE r.season = :season
              AND r.status = 'success'
              AND {selected_date_expr} <= :completed_date
            ORDER BY {completed_expr} DESC, r.team_rating_run_id DESC
            LIMIT 1
        )
        SELECT
            {", ".join(rating_selects)}
        FROM public.team_ratings t
        JOIN selected_run sr
          ON sr.team_rating_run_id = t.team_rating_run_id
        ORDER BY
            CASE WHEN {rank_order_sql} IS NULL THEN 1 ELSE 0 END,
            {rank_order_sql},
            power_rating DESC,
            t.team
        """,
        {"season": int(season), "completed_date": completed_date},
    )
    if df.empty:
        return df

    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    if df["rank"].isna().any():
        df = df.sort_values("power_rating", ascending=False).copy()
        df["rank"] = range(1, len(df) + 1)
    df["rank"] = df["rank"].astype(int)
    for column in ["completed_games", "projected_games"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)

    df = attach_assets(df)
    return df.sort_values("rank")


@st.cache_data(ttl=300)
def get_next_games(season: int, as_of_date: date | None) -> pd.DataFrame:
    game_columns = get_table_columns("game_data")
    required = {"season", "hometeam", "awayteam", "homepoints", "awaypoints"}
    if not required.issubset(game_columns):
        return pd.DataFrame()

    has_startdate = "startdate" in game_columns
    start_select = (
        "(startdate AT TIME ZONE 'America/New_York')::date AS game_date, startdate"
        if has_startdate
        else "NULL::date AS game_date, NULL::timestamp AS startdate"
    )
    date_filter = (
        "AND (startdate IS NULL OR (startdate AT TIME ZONE 'America/New_York')::date >= :as_of_date)"
        if has_startdate
        else ""
    )
    order_sql = "startdate NULLS LAST, team, opponent" if has_startdate else "team, opponent"

    df = read_df(
        f"""
        WITH games AS (
            SELECT
                hometeam AS home_team,
                awayteam AS away_team,
                {start_select}
            FROM public.game_data
            WHERE season = :season
              AND {REGULAR_SEASON_FILTER}
              AND hometeam IS NOT NULL
              AND awayteam IS NOT NULL
              AND homepoints IS NULL
              AND awaypoints IS NULL
              {date_filter}
        ),
        team_games AS (
            SELECT
                home_team AS team,
                away_team AS opponent,
                'vs' AS location,
                game_date,
                startdate
            FROM games

            UNION ALL

            SELECT
                away_team AS team,
                home_team AS opponent,
                'at' AS location,
                game_date,
                startdate
            FROM games
        ),
        ranked AS (
            SELECT
                *,
                ROW_NUMBER() OVER (PARTITION BY team ORDER BY {order_sql}) AS rn
            FROM team_games
        )
        SELECT team, opponent, location, game_date
        FROM ranked
        WHERE rn = 1
        """,
        {"season": int(season), "as_of_date": as_of_date or date.today()},
    )
    if df.empty:
        return df

    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    return df


def format_next_game(row: pd.Series | None) -> str:
    if row is None or row.empty:
        return "No upcoming"

    opponent = row.get("opponent", None)
    if pd.isna(opponent) or not str(opponent).strip():
        return "Next TBD"

    location = str(row.get("location", "vs")).strip() or "vs"
    game_date = row.get("game_date", None)
    date_label = ""
    if game_date is not None and not pd.isna(game_date):
        date_label = pd.to_datetime(game_date).strftime(" %b %-d")
    return f"{location} {opponent}{date_label}"


def add_rating_context(df: pd.DataFrame, season: int | None, as_of_date: date | None) -> pd.DataFrame:
    if df.empty:
        return df

    out = df.copy()
    next_games = get_next_games(season, as_of_date) if isinstance(season, int) else pd.DataFrame()
    if next_games.empty:
        out["next_game_label"] = "No upcoming"
        return out

    next_game_map = {row.team: format_next_game(pd.Series(row._asdict())) for row in next_games.itertuples(index=False)}
    out["next_game_label"] = out["team"].map(next_game_map).fillna("No upcoming")
    return out


def attach_assets(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    directory = get_team_directory()
    return df.merge(directory[["team", "logo"]], on="team", how="left")


def logo_html(url: str | None, team: str) -> str:
    safe_team = html.escape(str(team))
    if pd.isna(url) or not str(url).strip():
        initials = "".join(part[0] for part in str(team).split()[:3]).upper()
        return f"<div class='logo-wrap'><span style='font-weight:900;font-size:12px;'>{html.escape(initials)}</span></div>"
    return f"<div class='logo-wrap'><img src='{html.escape(str(url), quote=True)}' alt='{safe_team} logo' /></div>"


def compact_logo_html(url: str | None, team: str) -> str:
    safe_team = html.escape(str(team))
    if pd.isna(url) or not str(url).strip():
        initials = "".join(part[0] for part in str(team).split()[:3]).upper()
        return f"<div class='compact-logo'><span style='font-weight:900;font-size:10px;'>{html.escape(initials)}</span></div>"
    return f"<div class='compact-logo'><img src='{html.escape(str(url), quote=True)}' alt='{safe_team} logo' /></div>"


def format_decimal(value: float, digits: int = 1) -> str:
    return "NA" if pd.isna(value) else f"{value:.{digits}f}"


def format_date(value) -> str:
    if value is None or pd.isna(value):
        return "NA"
    parsed = pd.to_datetime(value, errors="coerce")
    return "NA" if pd.isna(parsed) else parsed.strftime("%b %-d, %Y")


def format_blend_meta(df: pd.DataFrame, teamrankings_weight: float) -> str:
    if teamrankings_weight <= 0:
        return "BG only"
    if (
        "teamrankings_scaled_rating" not in df.columns
        or df["teamrankings_scaled_rating"].notna().sum() < 2
    ):
        return "BG only"
    return f"{teamrankings_weight:.0%} TeamRankings blend"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return slug or "ratings"


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    box = draw.textbbox((0, 0), str(text), font=font)
    return box[2] - box[0], box[3] - box[1]


def draw_centered_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
) -> None:
    box = draw.textbbox((0, 0), str(text), font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text(
        (xy[0] - width / 2 - box[0], xy[1] - height / 2 - box[1]),
        text,
        font=font,
        fill=fill,
    )


def truncate_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    text = str(text)
    if text_size(draw, text, font)[0] <= max_width:
        return text
    suffix = "..."
    while text and text_size(draw, f"{text}{suffix}", font)[0] > max_width:
        text = text[:-1]
    return f"{text}{suffix}" if text else suffix


def team_initials(team: str) -> str:
    return "".join(part[0] for part in str(team).split()[:3]).upper()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_logo_bytes(url: str | None) -> bytes | None:
    if pd.isna(url) or not str(url).strip():
        return None
    try:
        request = urllib.request.Request(
            str(url),
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=6) as response:
            return response.read()
    except Exception:
        return None


def get_logo_image(url: str | None, size: int) -> Image.Image | None:
    logo_bytes = fetch_logo_bytes(url)
    if not logo_bytes:
        return None
    try:
        logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
    except Exception:
        return None

    logo.thumbnail((size, size), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2
    canvas.alpha_composite(logo, (x, y))
    return canvas


def draw_logo_badge(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    center: tuple[float, float],
    badge_size: int,
    logo_url: str | None,
    team: str,
    font: ImageFont.ImageFont,
) -> None:
    x = int(center[0] - badge_size / 2)
    y = int(center[1] - badge_size / 2)
    draw.ellipse((x, y, x + badge_size, y + badge_size), fill="#eef2f7", outline="#dbe4ee", width=2)

    logo = get_logo_image(logo_url, int(badge_size * 0.78))
    if logo is not None:
        lx = int(center[0] - logo.width / 2)
        ly = int(center[1] - logo.height / 2)
        image.paste(logo, (lx, ly), logo)
        return

    draw_centered_text(draw, center, team_initials(team), font, "#0f172a")


def image_to_png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def build_power_rankings_png(df: pd.DataFrame, title: str, meta: str) -> bytes:
    width = 1080
    height = 1080
    margin = 44
    gap = 12
    header_h = 118
    cols = 5
    rows = 5
    card_w = (width - margin * 2 - gap * (cols - 1)) // cols
    card_h = (height - margin * 2 - header_h - gap * (rows - 1)) // rows

    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)
    title_font = load_font(44, bold=True)
    meta_font = load_font(19)
    rank_font = load_font(23, bold=True)
    team_font = load_font(21, bold=True)
    sub_font = load_font(15)
    rating_font = load_font(24, bold=True)

    draw.text((margin, 34), title, font=title_font, fill="#0f172a")
    draw.text((margin, 86), meta, font=meta_font, fill="#64748b")
    draw.text((width - margin - 204, 48), "@BG.Analytics", font=load_font(24, bold=True), fill="#0f172a")

    for idx, item in enumerate(df.head(25).itertuples(index=False)):
        row = idx // cols
        col = idx % cols
        x = margin + col * (card_w + gap)
        y = margin + header_h + row * (card_h + gap)
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=16, fill="#ffffff", outline="#dbe4ee", width=2)

        rank = int(getattr(item, "rank"))
        team = str(getattr(item, "team"))
        logo_url = getattr(item, "logo", None)
        rating = float(getattr(item, "power_rating"))
        draw.ellipse((x + 14, y + 14, x + 52, y + 52), fill="#0f172a")
        draw_centered_text(draw, (x + 33, y + 33), str(rank), rank_font, "#ffffff")
        draw.text((x + card_w - 74, y + 18), f"{rating:+.1f}", font=rating_font, fill="#0f172a")

        draw_logo_badge(
            image,
            draw,
            (x + card_w / 2, y + 78),
            58,
            logo_url,
            team,
            load_font(18, bold=True),
        )

        team_label = truncate_text(draw, team, team_font, card_w - 22)
        draw_centered_text(draw, (x + card_w / 2, y + 122), team_label, team_font, "#0f172a")
        next_game = str(getattr(item, "next_game_label", "No upcoming"))
        next_game_label = truncate_text(draw, next_game, sub_font, card_w - 24)
        draw_centered_text(draw, (x + card_w / 2, y + 147), next_game_label, sub_font, "#64748b")

    return image_to_png_bytes(image)


def build_poll_comparison_df(poll_df: pd.DataFrame, power_df: pd.DataFrame) -> pd.DataFrame:
    poll_export_cols = [col for col in ["team", "rank", "logo"] if col in poll_df.columns]
    power_export_cols = [col for col in ["team", "rank", "power_rating", "logo"] if col in power_df.columns]
    poll_cols = (
        poll_df[poll_export_cols].rename(columns={"rank": "poll_rank", "logo": "poll_logo"}).copy()
        if poll_export_cols
        else pd.DataFrame()
    )
    power_cols = (
        power_df[power_export_cols].rename(columns={"rank": "rating_rank", "logo": "rating_logo"}).copy()
        if power_export_cols
        else pd.DataFrame()
    )
    if poll_cols.empty and power_cols.empty:
        return pd.DataFrame()
    if poll_cols.empty:
        poll_cols = pd.DataFrame(columns=["team", "poll_rank", "poll_logo"])
    if power_cols.empty:
        power_cols = pd.DataFrame(columns=["team", "rating_rank", "power_rating", "rating_logo"])

    comparison = poll_cols.merge(power_cols, on="team", how="outer")
    if "poll_logo" in comparison.columns and "rating_logo" in comparison.columns:
        comparison["logo"] = comparison["poll_logo"].combine_first(comparison["rating_logo"])
    elif "poll_logo" in comparison.columns:
        comparison["logo"] = comparison["poll_logo"]
    elif "rating_logo" in comparison.columns:
        comparison["logo"] = comparison["rating_logo"]
    else:
        comparison["logo"] = None
    comparison["poll_rank"] = pd.to_numeric(comparison["poll_rank"], errors="coerce")
    comparison["rating_rank"] = pd.to_numeric(comparison["rating_rank"], errors="coerce")
    comparison["poll_points"] = np.where(comparison["poll_rank"].notna(), 26 - comparison["poll_rank"], 0)
    comparison["rating_points"] = np.where(comparison["rating_rank"].notna(), 26 - comparison["rating_rank"], 0)
    comparison["poll_points"] = comparison["poll_points"].clip(0, 25).astype(int)
    comparison["rating_points"] = comparison["rating_points"].clip(0, 25).astype(int)
    comparison["gap"] = comparison["poll_points"] - comparison["rating_points"]
    comparison["abs_gap"] = comparison["gap"].abs()
    comparison = comparison[(comparison["poll_points"] > 0) | (comparison["rating_points"] > 0)]
    return comparison.sort_values(["abs_gap", "poll_points", "rating_points"], ascending=[False, False, False])


def build_poll_comparison_png(comparison: pd.DataFrame, poll_title: str, power_title: str, meta: str) -> bytes:
    width = 1080
    height = 1080
    margin = 44
    row_h = 72
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)

    title_font = load_font(40, bold=True)
    meta_font = load_font(18)
    section_font = load_font(26, bold=True)
    head_font = load_font(16, bold=True)
    row_font = load_font(20, bold=True)
    small_font = load_font(15)

    draw.text((margin, 34), "Poll vs BG Analytics", font=title_font, fill="#0f172a")
    draw.text((width - margin - 204, 48), "@BG.Analytics", font=load_font(24, bold=True), fill="#0f172a")
    draw.text((margin, 84), meta, font=meta_font, fill="#64748b")
    draw.text((margin, 112), "Top 5 overrated and underrated by shared Top 25 points", font=small_font, fill="#64748b")

    overrated = comparison[comparison["gap"] > 0].sort_values(
        ["gap", "poll_points", "rating_points"], ascending=[False, False, True]
    ).head(5)
    underrated = comparison[comparison["gap"] < 0].sort_values(
        ["gap", "rating_points", "poll_points"], ascending=[True, False, True]
    ).head(5)

    def draw_section(section: pd.DataFrame, heading: str, y: int, accent: str) -> int:
        draw.text((margin, y), heading, font=section_font, fill="#0f172a")
        y += 42
        draw.rounded_rectangle((margin, y, width - margin, y + 34), radius=8, fill="#0f172a")
        draw.text((margin + 64, y + 9), "Team", font=head_font, fill="#ffffff")
        draw.text((margin + 432, y + 9), poll_title, font=head_font, fill="#ffffff")
        draw.text((margin + 642, y + 9), power_title, font=head_font, fill="#ffffff")
        draw.text((width - margin - 120, y + 9), "Gap", font=head_font, fill="#ffffff")
        y += 42

        if section.empty:
            draw.rounded_rectangle((margin, y, width - margin, y + row_h - 8), radius=8, fill="#ffffff", outline="#dbe4ee")
            draw.text((margin + 18, y + 22), "No teams in this group.", font=row_font, fill="#64748b")
            return y + row_h

        for idx, item in enumerate(section.itertuples(index=False), start=1):
            row_y = y + (idx - 1) * row_h
            bg = "#ffffff" if idx % 2 else "#f1f5f9"
            draw.rounded_rectangle((margin, row_y, width - margin, row_y + row_h - 8), radius=8, fill=bg)
            draw_logo_badge(
                image,
                draw,
                (margin + 32, row_y + 31),
                42,
                getattr(item, "logo", None),
                str(item.team),
                load_font(13, bold=True),
            )

            team = truncate_text(draw, str(item.team), row_font, 320)
            poll_rank = "--" if pd.isna(item.poll_rank) else f"#{int(item.poll_rank)}"
            rating_rank = "--" if pd.isna(item.rating_rank) else f"#{int(item.rating_rank)}"
            poll_points = int(item.poll_points)
            rating_points = int(item.rating_points)
            gap = int(item.gap)

            draw.text((margin + 64, row_y + 14), team, font=row_font, fill="#0f172a")
            draw.text((margin + 64, row_y + 40), f"{'Over' if gap > 0 else 'Under'} by {abs(gap)} pts", font=small_font, fill=accent)

            draw.text((margin + 432, row_y + 14), poll_rank, font=row_font, fill="#0f172a")
            draw.text((margin + 432, row_y + 40), f"{poll_points} pts", font=small_font, fill="#64748b")

            draw.text((margin + 642, row_y + 14), rating_rank, font=row_font, fill="#0f172a")
            draw.text((margin + 642, row_y + 40), f"{rating_points} pts", font=small_font, fill="#64748b")

            gap_text = f"{gap:+d}"
            draw.text((width - margin - 116, row_y + 21), gap_text, font=load_font(24, bold=True), fill=accent)

        return y + len(section) * row_h

    next_y = draw_section(overrated, "Most Overrated By Poll", 152, "#b91c1c")
    draw_section(underrated, "Most Underrated By Poll", next_y + 34, "#047857")

    return image_to_png_bytes(image)


def build_png_zip(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def render_poll_list(df: pd.DataFrame, title: str, meta: str) -> None:
    rows = []
    for item in df.head(25).itertuples(index=False):
        team = html.escape(str(item.team))
        logo = compact_logo_html(getattr(item, "logo", None), item.team)
        rows.append(
            "<div class='compact-row'>"
            f"<div class='compact-rank'>{int(item.rank)}</div>"
            f"{logo}"
            "<div class='compact-team'>"
            f"<div class='compact-team-name' title='{team}'>{team}</div>"
            "<div class='compact-sub'>Official poll ranking</div>"
            "</div>"
            f"<div class='compact-value'>#{int(item.rank)}</div>"
            "</div>"
        )
    body = "".join(rows) if rows else "<div class='empty-board'>No rankings available.</div>"
    st.markdown(
        "<div class='board'>"
        "<div class='board-head'>"
        f"<div class='board-title'>{html.escape(title)}</div>"
        f"<div class='board-meta'>{html.escape(meta)}</div>"
        "</div>"
        f"<div class='compact-list'>{body}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_power_list(df: pd.DataFrame, title: str, meta: str) -> None:
    rows = []
    for item in df.itertuples(index=False):
        team = html.escape(str(item.team))
        logo = compact_logo_html(getattr(item, "logo", None), item.team)
        next_game = html.escape(str(getattr(item, "next_game_label", "No upcoming")))
        rows.append(
            "<div class='compact-row'>"
            f"<div class='compact-rank'>{int(item.rank)}</div>"
            f"{logo}"
            "<div class='compact-team'>"
            f"<div class='compact-team-name' title='{team}'>{team}</div>"
            f"<div class='compact-sub'>{next_game}</div>"
            "</div>"
            f"<div class='compact-value'>{item.power_rating:+.1f}</div>"
            "</div>"
        )
    body = "".join(rows) if rows else "<div class='empty-board'>No power ratings available.</div>"
    st.markdown(
        "<div class='board'>"
        "<div class='board-head'>"
        f"<div class='board-title'>{html.escape(title)}</div>"
        f"<div class='board-meta'>{html.escape(meta)}</div>"
        "</div>"
        f"<div class='compact-list power-rating-scroll' role='region' "
        f"aria-label='{html.escape(title)} rankings' tabindex='0'>{body}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_poll_board(df: pd.DataFrame, title: str, meta: str) -> None:
    rows = []
    for item in df.head(25).itertuples(index=False):
        team = html.escape(str(item.team))
        logo = logo_html(getattr(item, "logo", None), item.team)
        rows.append(
            "<div class='ranking-card'>"
            "<div class='card-topline'>"
            f"<div class='rank-pill'>{int(item.rank)}</div>"
            "<div class='card-metric'>"
            f"<div class='card-metric-main'>#{int(item.rank)}</div>"
            "<div class='card-metric-sub'>Rank</div>"
            "</div>"
            "</div>"
            f"{logo}"
            "<div>"
            f"<div class='team-name' title='{team}'>{team}</div>"
            "<div class='team-sub'>Official poll ranking</div>"
            "</div>"
            "</div>"
        )
    body = "".join(rows) if rows else "<div class='empty-board'>No rankings available.</div>"
    st.markdown(
        "<div class='board'>"
        "<div class='board-head'>"
        f"<div class='board-title'>{html.escape(title)}</div>"
        f"<div class='board-meta'>{html.escape(meta)}</div>"
        "</div>"
        f"<div class='ranking-list'>{body}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_power_board(df: pd.DataFrame, title: str, meta: str) -> None:
    rows = []
    for item in df.head(25).itertuples(index=False):
        team = html.escape(str(item.team))
        logo = logo_html(getattr(item, "logo", None), item.team)
        next_game = html.escape(str(getattr(item, "next_game_label", "No upcoming")))
        rows.append(
            "<div class='ranking-card'>"
            "<div class='card-topline'>"
            f"<div class='rank-pill'>{int(item.rank)}</div>"
            "<div class='card-metric'>"
            f"<div class='card-metric-main'>{item.power_rating:+.1f}</div>"
            "<div class='card-metric-sub'>Pts</div>"
            "</div>"
            "</div>"
            f"{logo}"
            "<div>"
            f"<div class='team-name' title='{team}'>{team}</div>"
            f"<div class='team-sub'>{next_game}</div>"
            "</div>"
            "</div>"
        )
    body = "".join(rows) if rows else "<div class='empty-board'>No power ratings available.</div>"
    st.markdown(
        "<div class='board'>"
        "<div class='board-head'>"
        f"<div class='board-title'>{html.escape(title)}</div>"
        f"<div class='board-meta'>{html.escape(meta)}</div>"
        "</div>"
        f"<div class='ranking-list'>{body}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


st.markdown(
    """
    <div class="rankings-page">
      <div class="rankings-header">
        <div>
          <h1 class="rankings-title">Team Rankings</h1>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

available_polls = get_available_polls()
poll_label_map = dict(available_polls)
poll_options = list(poll_label_map.keys()) or ["No polls available"]

control_a, control_b, control_c, control_d, control_e, control_f = st.columns(
    [1.1, 1, 1, 1, 1, 1.2]
)

with control_a:
    poll_label = st.selectbox(
        "Official Poll",
        poll_options,
        index=0,
        disabled=not bool(poll_label_map),
    )

poll = poll_label_map.get(poll_label)
poll_seasons = get_poll_seasons(poll) if poll else []
poll_season_options = poll_seasons or ["No seasons"]

with control_b:
    poll_season = st.selectbox(
        "Poll Season",
        poll_season_options,
        index=0,
        disabled=not bool(poll_seasons),
    )

poll_weeks = get_poll_weeks(poll, poll_season) if poll and isinstance(poll_season, int) else []
poll_week_options = poll_weeks or ["No weeks"]

with control_c:
    poll_week = st.selectbox(
        "Poll Week",
        poll_week_options,
        index=len(poll_weeks) - 1 if poll_weeks else 0,
        disabled=not bool(poll_weeks),
    )

power_seasons = get_power_rating_seasons()
power_default = (
    power_seasons.index(poll_season)
    if isinstance(poll_season, int) and poll_season in power_seasons
    else 0
)
power_season_options = power_seasons or ["No seasons"]

with control_d:
    power_season = st.selectbox(
        "Power Rating Season",
        power_season_options,
        index=power_default if power_seasons else 0,
        disabled=not bool(power_seasons),
    )

rating_run_dates = (
    get_team_rating_run_dates(power_season)
    if isinstance(power_season, int) and power_season >= 2026
    else pd.DataFrame()
)
latest_rating_date = (
    rating_run_dates["completed_date"].max()
    if not rating_run_dates.empty and "completed_date" in rating_run_dates.columns
    else None
)
earliest_rating_date = (
    rating_run_dates["completed_date"].min()
    if not rating_run_dates.empty and "completed_date" in rating_run_dates.columns
    else None
)

with control_e:
    if isinstance(power_season, int) and power_season >= 2026:
        if latest_rating_date is not None:
            selected_rating_date = st.date_input(
                "Ratings As Of",
                value=latest_rating_date,
                min_value=earliest_rating_date,
            )
        else:
            selected_rating_date = None
            st.date_input(
                "Ratings As Of",
                value=date.today(),
                disabled=True,
                help="No successful team-rating runs are available for this season yet.",
            )
    else:
        selected_rating_date = None
        st.date_input(
            "Ratings As Of",
            value=date(power_season if isinstance(power_season, int) else 2025, 12, 31),
            disabled=True,
            help="Seasons 2025 and earlier use the end-of-season calculation.",
        )

with control_f:
    teamrankings_blend_weight = st.slider(
        "TeamRankings Blend",
        min_value=0.0,
        max_value=1.0,
        value=0.5,
        step=0.05,
        help="0 = BG Power only. 1 = TeamRankings only, standardized to the BG Power scale.",
    )

poll_df = (
    get_poll_rankings(poll, poll_season, poll_week)
    if poll and isinstance(poll_season, int) and isinstance(poll_week, int)
    else pd.DataFrame()
)
if isinstance(power_season, int) and power_season >= 2026:
    power_df = get_snapshot_power_rankings(power_season, selected_rating_date)
else:
    power_df = get_power_rankings(power_season) if isinstance(power_season, int) else pd.DataFrame()
power_rating_as_of = (
    selected_rating_date
    if isinstance(power_season, int) and power_season >= 2026
    else date.today()
)
power_df = blend_power_with_teamrankings(
    power_df,
    power_season if isinstance(power_season, int) else None,
    power_rating_as_of,
    teamrankings_blend_weight,
)
power_df = add_rating_context(
    power_df,
    power_season if isinstance(power_season, int) else None,
    power_rating_as_of,
)

top_poll_team = poll_df.iloc[0]["team"] if not poll_df.empty else "NA"
top_power_team = power_df.iloc[0]["team"] if not power_df.empty else "NA"
avg_power_rating = power_df.head(25)["power_rating"].mean() if not power_df.empty else np.nan
avg_hfa = power_df["hfa"].iloc[0] if not power_df.empty and "hfa" in power_df.columns else np.nan
margin_source = (
    power_df["margin_source"].iloc[0]
    if not power_df.empty and "margin_source" in power_df.columns
    else "none"
)

st.markdown(
    f"""
    <div class="stat-strip">
      <div class="stat-tile">
        <div class="stat-label">Official No. 1</div>
        <div class="stat-value">{html.escape(str(top_poll_team))}</div>
      </div>
      <div class="stat-tile">
        <div class="stat-label">Power No. 1</div>
        <div class="stat-value">{html.escape(str(top_power_team))}</div>
      </div>
      <div class="stat-tile">
        <div class="stat-label">Solved HFA</div>
        <div class="stat-value">{format_decimal(avg_hfa)}</div>
      </div>
      <div class="stat-tile">
        <div class="stat-label">Top 25 Avg Rating</div>
        <div class="stat-value">{format_decimal(avg_power_rating)}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

poll_title = f"{poll_label or 'Official Poll'} Top 25"
poll_meta = f"{poll_season or ''} | Week {poll_week or ''}".strip(" |")
power_title = "BG Power Rating"
blend_meta = format_blend_meta(power_df, teamrankings_blend_weight)
if isinstance(power_season, int) and power_season >= 2026:
    snapshot_completed = (
        power_df["completed_at"].iloc[0]
        if not power_df.empty and "completed_at" in power_df.columns
        else selected_rating_date
    )
    power_meta = (
        f"{power_season or ''} | As of {format_date(snapshot_completed)} | {blend_meta}"
    ).strip(" |")
else:
    power_meta = (
        f"{power_season or ''} | End of season | MOV + {margin_source} | {blend_meta}"
    ).strip(" |")

list_a, list_b = st.columns(2)
with list_a:
    render_poll_list(poll_df, poll_title, poll_meta)
with list_b:
    render_power_list(power_df, power_title, power_meta)

with st.expander("Posting export"):
    comparison_df = build_poll_comparison_df(poll_df, power_df)
    if not power_df.empty and not comparison_df.empty:
        ratings_png = build_power_rankings_png(
            power_df,
            "BG Analytics Statistical Ratings",
            power_meta,
        )
        comparison_meta = f"{poll_meta} | {power_meta}"
        comparison_png = build_poll_comparison_png(
            comparison_df,
            poll_label or "Poll",
            "BG Rating",
            comparison_meta,
        )
        ratings_file = f"bg_statistical_ratings_{power_season}_{selected_rating_date or 'end_of_season'}.png"
        comparison_file = (
            f"poll_vs_bg_rating_{slugify(poll_label or 'poll')}_"
            f"{power_season}_{selected_rating_date or 'end_of_season'}.png"
        )

        preview_a, preview_b = st.columns(2)
        with preview_a:
            st.image(ratings_png, caption="BG Analytics statistical ratings")
            st.download_button(
                "Download statistical ratings PNG",
                data=ratings_png,
                file_name=ratings_file,
                mime="image/png",
            )
        with preview_b:
            st.image(comparison_png, caption="Poll vs BG Analytics comparison")
            st.download_button(
                "Download comparison PNG",
                data=comparison_png,
                file_name=comparison_file,
                mime="image/png",
            )

        st.download_button(
            "Download both PNGs",
            data=build_png_zip({ratings_file: ratings_png, comparison_file: comparison_png}),
            file_name=f"team_rankings_exports_{power_season}_{selected_rating_date or 'end_of_season'}.zip",
            mime="application/zip",
        )
    else:
        st.info("Select a poll and a BG rating with available teams to generate posting PNGs.")

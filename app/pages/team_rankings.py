import html
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.db import read_df
from utils.movement_graphic import movement_graphic_controls
from utils.rankings_analysis import (
    blend_rating_snapshot, build_bubble_watch, build_poll_comparison, build_rank_movements,
    comparison_date_bounds, disagreement_shortlists, movement_shortlists, ranked_teams,
    resolve_rating_date, valid_comparison_date,
)


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
      .analysis-grid, .analysis-metrics {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 16px;
        margin: 12px 0 22px;
      }
      .analysis-metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .analysis-panel {
        min-width: 0;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        background: #ffffff;
        color: #0f172a;
        overflow: hidden;
      }
      .analysis-panel h4 { margin: 0; padding: 14px 16px; font-size: 17px; background: #f8fafc; }
      .analysis-panel h4.analysis-red { border-top: 3px solid #b91c1c; }
      .analysis-panel h4.analysis-green { border-top: 3px solid #047857; }
      .analysis-row { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 12px; padding: 13px 16px; border-top: 1px solid #f1f5f9; }
      .analysis-name { font-weight: 800; overflow-wrap: anywhere; }
      .analysis-detail { color: #475569; font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
      .analysis-change { margin-top: 3px; font-size: 13px; font-weight: 750; }
      .analysis-red { color: #b91c1c; }
      .analysis-green { color: #047857; }
      .analysis-empty { margin: 0; padding: 16px; color: #64748b; }
      @media (max-width: 640px) {
        .analysis-grid, .analysis-metrics { grid-template-columns: minmax(0, 1fr); }
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
    teamrankings = get_teamrankings_snapshot(season, as_of_date) if teamrankings_weight > 0 else pd.DataFrame()
    return blend_rating_snapshot(power_df, teamrankings, teamrankings_weight)


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


def format_position(value, missing: str = "UR") -> str:
    return missing if pd.isna(value) else f"#{int(value)}"


def analysis_row_html(team, logo, detail: str, change: str = "", tone: str = "") -> str:
    return (
        f"<div class='analysis-row'>{compact_logo_html(logo, team)}<div>"
        f"<div class='analysis-name'>{html.escape(str(team))}</div>"
        f"<div class='analysis-detail'>{html.escape(detail)}</div>"
        f"<div class='analysis-change {tone}'>{html.escape(change)}</div></div></div>"
    )


def analysis_panel_html(title: str, rows: list[str], empty: str, tone: str = "") -> str:
    body = "".join(rows) if rows else f"<p class='analysis-empty'>{html.escape(empty)}</p>"
    return f"<section class='analysis-panel'><h4 class='{tone}'>{html.escape(title)}</h4>{body}</section>"


def render_analysis_pair(left: str, right: str) -> None:
    st.markdown(f"<div class='analysis-grid'>{left}{right}</div>", unsafe_allow_html=True)


def comparison_rows(frame: pd.DataFrame, poll_label: str, *, show_gap: bool = False) -> list[str]:
    rows = []
    for row in frame.itertuples(index=False):
        detail = (f"{poll_label} {format_position(row.poll_rank)} · Ratings {format_position(row.rating_rank, '—')}"
                  f" · Rating {format_decimal(row.power_rating)}")
        change, tone = "", ""
        if show_gap and pd.notna(row.gap):
            minimum = "At least " if row.gap_is_minimum else ""
            places = int(abs(row.gap))
            direction = "higher" if row.gap > 0 else "lower"
            change = f"{minimum}{places} {'place' if places == 1 else 'places'} {direction} in the poll"
            tone = "analysis-red" if row.gap > 0 else "analysis-green"
        rows.append(analysis_row_html(row.team, row.logo, detail, change, tone))
    return rows


def render_snapshot_analysis(poll_df, power_df, poll_label, same_season):
    official = ranked_teams(poll_df)
    poll_available = official["rank"].le(25).any()
    ratings_available = not ranked_teams(power_df).empty
    comparable = same_season and poll_available and ratings_available
    if not same_season:
        st.info("Select matching poll and power-rating seasons to compare their rankings. Each list and its movement remain available below.")
    elif not comparable:
        st.info("A poll Top 25 and selected ratings are both needed for overrated, underrated, and agreement analysis.")
    else:
        comparison = build_poll_comparison(poll_df, power_df)
        overrated, underrated = disagreement_shortlists(comparison)
        st.caption("Overrated and underrated are relative to the selected ratings and blend. UR means outside the poll’s Top 25; gaps for UR teams are minimums.")
        render_analysis_pair(
            analysis_panel_html("Most overrated by the poll", comparison_rows(overrated, poll_label, show_gap=True),
                                "No teams are ranked higher by the poll.", "analysis-red"),
            analysis_panel_html("Most underrated by the poll", comparison_rows(underrated, poll_label, show_gap=True),
                                "No teams are ranked lower by the poll.", "analysis-green"),
        )
        if comparison["rating_rank"].isna().any():
            st.caption("Poll teams without a selected rating are excluded from rank-gap calculations.")

        st.subheader("Top 25 agreement")
        shared = int((comparison["in_poll"] & comparison["in_ratings"]).sum())
        poll_only = comparison.loc[comparison["in_poll"] & ~comparison["in_ratings"]].sort_values(["poll_rank", "team"])
        ratings_only = comparison.loc[comparison["in_ratings"] & ~comparison["in_poll"]].sort_values(["rating_rank", "team"])
        st.write(f"The poll and selected ratings share {shared} Top 25 teams.")
        tiles = "".join(
            f"<div class='stat-tile'><div class='stat-label'>{label}</div><div class='stat-value'>{value}</div></div>"
            for label, value in [("Shared Top 25", shared), ("Poll only", len(poll_only)), ("Ratings only", len(ratings_only))]
        )
        st.markdown(f"<div class='analysis-metrics'>{tiles}</div>", unsafe_allow_html=True)
        render_analysis_pair(
            analysis_panel_html("In the poll only", comparison_rows(poll_only, poll_label), "No teams appear only in the poll’s Top 25."),
            analysis_panel_html("In the ratings only", comparison_rows(ratings_only, poll_label), "No teams appear only in the ratings’ Top 25."),
        )

    st.subheader("Bubble watch")
    bubble = build_bubble_watch(power_df, poll_df if same_season and poll_available else None)
    rows = []
    for row in bubble.itertuples(index=False):
        poll_position = format_position(row.poll_rank) if same_season and poll_available else "—"
        detail = (f"Ratings #{int(row.rank)} · {poll_label} {poll_position} · Rating {format_decimal(row.power_rating)}"
                  f" · {row.next_game_label if pd.notna(row.next_game_label) else 'Next game unavailable'}")
        gap = (f"{row.points_to_top25:.1f} rating points behind #25"
               if pd.notna(row.points_to_top25) else "Rating gap to #25 unavailable")
        rows.append(analysis_row_html(row.team, row.logo, detail, gap))
    st.markdown(analysis_panel_html("Just outside the ratings’ Top 25", rows, "Ratings #26–30 are unavailable for this selection."), unsafe_allow_html=True)


def movement_rows(frame: pd.DataFrame, *, poll: bool, membership: str = "") -> list[str]:
    rows = []
    for row in frame.itertuples(index=False):
        missing = "UR" if poll else "—"
        detail = f"{format_position(row.previous_rank, missing)} → {format_position(row.current_rank, missing)}"
        if not poll and pd.notna(row.rating_change):
            detail += f" · Rating {row.previous_power_rating:.1f} → {row.current_power_rating:.1f} ({row.rating_change:+.1f})"
        change, tone = membership, ""
        if membership:
            tone = "analysis-green" if row.entered_top25 else "analysis-red"
        elif pd.notna(row.rank_change):
            places = int(abs(row.rank_change))
            change = f"{'↑' if row.rank_change > 0 else '↓'} {places} {'place' if places == 1 else 'places'}"
            tone = "analysis-green" if row.rank_change > 0 else "analysis-red"
        rows.append(analysis_row_html(row.team, row.logo, detail, change, tone))
    return rows


def render_movement_panels(
    movement: pd.DataFrame, *, poll: bool, season: int,
    source_label: str, comparison_label: str, blend_label: str = "",
) -> None:
    risers, fallers = movement_shortlists(movement)
    render_analysis_pair(
        analysis_panel_html("Biggest risers", movement_rows(risers, poll=poll), "No rank increases in this comparison.", "analysis-green"),
        analysis_panel_html("Biggest fallers", movement_rows(fallers, poll=poll), "No rank decreases in this comparison.", "analysis-red"),
    )
    if st.button("Show Instagram graphic", key=f"movement_graphic_{'poll' if poll else 'ratings'}"):
        with st.spinner("Preparing the team logos…"):
            graphic = movement_graphic_controls(
                risers, fallers, season=season, source_label=source_label,
                comparison_label=comparison_label, poll=poll, blend_label=blend_label,
            )
        if hasattr(st, "iframe"):
            st.iframe(graphic, height="content")
        else:
            components.html(graphic, height=1060, scrolling=True)
    entrants = movement.loc[movement["entered_top25"]].sort_values(["current_rank", "team"])
    departures = movement.loc[movement["left_top25"]].sort_values(["previous_rank", "team"])
    render_analysis_pair(
        analysis_panel_html("Entered the Top 25", movement_rows(entrants, poll=poll, membership="New to the Top 25"), "No new Top 25 teams."),
        analysis_panel_html("Left the Top 25", movement_rows(departures, poll=poll, membership="Dropped from the Top 25"), "No teams left the Top 25."),
    )


def render_poll_movement(poll_df, poll, poll_label, season, week, weeks):
    if ranked_teams(poll_df).empty:
        st.info("The selected poll is unavailable.")
        return
    earlier = [value for value in weeks if value < week]
    if not earlier:
        st.info("No earlier week is available for this poll and season.")
        return
    previous_week = max(earlier)
    try:
        previous = get_poll_rankings(poll, season, previous_week)
    except Exception:
        st.info("The earlier poll could not be loaded. Current rankings analysis remains available.")
        return
    if ranked_teams(previous).empty:
        st.info("The earlier poll has no rankings available for comparison.")
        return
    st.caption(f"{poll_label} · {season} · Week {previous_week} → Week {week}. New and dropped teams have no exact rank change outside the Top 25.")
    render_movement_panels(
        build_rank_movements(poll_df, previous, poll=True), poll=True,
        season=season, source_label=poll_label,
        comparison_label=f"Week {previous_week} → Week {week}",
    )


def render_ratings_movement(power_df, season, actual_date, run_dates, weight):
    if not isinstance(season, int) or season < 2026:
        st.info("Ratings movement is unavailable for 2025 and earlier: those seasons use an end-of-season calculation.")
        return
    if ranked_teams(power_df).empty:
        st.info("The selected ratings are unavailable.")
        return
    bounds = comparison_date_bounds(run_dates, actual_date)
    if bounds is None:
        st.info("No earlier saved ratings date is available for this selection.")
        return
    minimum, maximum, _ = bounds
    key = f"rankings_compare_date_{season}"
    saved = st.session_state.get(key)
    valid = valid_comparison_date(saved, bounds)
    if key in st.session_state and saved != valid:
        del st.session_state[key]
    requested = st.date_input(
        "Compare ratings with date", value=valid, min_value=minimum, max_value=maximum, key=key,
        help="Uses the latest saved ratings on or before this date. Both dates use the TeamRankings Blend selected above.",
    )
    previous_date = resolve_rating_date(run_dates, requested)
    try:
        previous = get_snapshot_power_rankings(season, previous_date)
        previous = blend_power_with_teamrankings(previous, season, previous_date, weight)
    except Exception:
        st.info("The comparison ratings could not be loaded. Current rankings analysis remains available.")
        return
    if ranked_teams(previous).empty:
        st.info("No ratings are available in the comparison snapshot.")
        return
    st.caption(f"Current: {format_date(actual_date)} · {format_blend_meta(power_df, weight)}. "
               f"Comparison: {format_date(previous_date)} · {format_blend_meta(previous, weight)}. "
               f"Requested comparison: {format_date(requested)}.")
    st.caption(f"Both snapshots use the selected {weight:.0%} TeamRankings blend with data available on each snapshot date. "
               "Movers cover all rated FBS teams; rank and rating changes require values in both snapshots.")
    if weight > 0:
        for label, frame in [("Current", power_df), ("Comparison", previous)]:
            coverage = frame.get("teamrankings_scaled_rating", pd.Series(np.nan, index=frame.index)).notna()
            if not coverage.all():
                st.caption(f"{label}: {int((~coverage).sum())} teams use BG-only ratings because a usable TeamRankings blend is unavailable.")
    render_movement_panels(
        build_rank_movements(power_df, previous), poll=False, season=season,
        source_label="BG Power Ratings",
        comparison_label=f"{format_date(previous_date)} → {format_date(actual_date)}",
        blend_label=f"TeamRankings blend: {weight:.0%}",
    )


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
actual_rating_date = resolve_rating_date(rating_run_dates, selected_rating_date)
power_rating_as_of = (
    actual_rating_date
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

st.subheader("Rankings Analysis")
st.caption(f"{poll_label}: {poll_meta} · Selected ratings: {power_meta}")
render_snapshot_analysis(poll_df, power_df, poll_label, poll_season == power_season)

st.subheader("Movement")
poll_movement_tab, ratings_movement_tab = st.tabs(["Poll", "Ratings"])
with poll_movement_tab:
    render_poll_movement(poll_df, poll, poll_label, poll_season, poll_week, poll_weeks)
with ratings_movement_tab:
    render_ratings_movement(power_df, power_season, actual_rating_date, rating_run_dates, teamrankings_blend_weight)

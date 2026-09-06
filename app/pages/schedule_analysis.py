import html
import json

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils.db import read_df


ET_TZ = "America/New_York"
FBS_FILTER = "homeclassification = 'fbs' AND awayclassification = 'fbs'"
PPA_STATS_COLUMNS = [
    "game_id",
    "team_key",
    "offense_ppa",
    "defense_ppa",
    "offense_ppa_percentile",
    "defense_ppa_percentile",
]
P4_PROMOTIONS_MAP_SCOPE = "P4 + Promotions"
ALL_MAP_SCOPE = "All Teams / Conferences"
POWER_FOUR_CONFERENCES = {"SEC", "ACC", "Big Ten", "Big 10", "Big 12"}
G6_CONFERENCES = {"American Athletic", "Conference USA", "Mid-American", "Mountain West", "Pac-12", "Pac 12", "Sun Belt"}
INDEPENDENT_CONFERENCES = {"FBS Independents", "Independent", "Independents"}
NOTRE_DAME_TEAM_KEYS = {"notre dame", "notre dame fighting irish"}
UCONN_TEAM_KEYS = {"uconn", "connecticut", "uconn huskies", "connecticut huskies"}
G5_CONFERENCE_PATTERNS = {
    "American Athletic": "diagonal",
    "Conference USA": "backDiagonal",
    "Mid-American": "vertical",
    "Mountain West": "horizontal",
    "Sun Belt": "cross",
}

# Conquest map default logo sizes. Update these values to globally tune initial logo sizes.
CONFERENCE_LOGO_RADIUS = 18
CONFERENCE_LOGO_SIZE = 28
CONFERENCE_LOGO_FONT_SIZE = 8
TEAM_LOGO_RADIUS = 18
TEAM_LOGO_SIZE = 30
TEAM_LOGO_FONT_SIZE = 8

# Add team names here when team territory mode should use the secondary color
# from team_map instead of the primary color.
USE_SECONDARY_COLOR_FOR_TEAMS = {
    "Michigan",
}

# Manually maintain conquest-map conference colors and logo PNG URLs here.
DEFAULT_CONFERENCE_ASSETS = {
    "ACC": {"color": "#013CA6", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/1.png"},
    "American Athletic": {"color": "#808080", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/151.png"},
    "Big 12": {"color": "#C41230", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/4.png"},
    "Big Ten": {"color": "#0088CE", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/5.png"},
    "Conference USA": {"color": "#FFC0CB", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/12.png"},
    "FBS Independents": {"color": "#000000", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/18.png"},
    "Mid-American": {"color": "#019E4F", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/15.png"},
    "Mountain West": {"color": "#4F2D7F", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/17.png"},
    "Pac-12": {"color": "#964B00", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/9.png"},
    "SEC": {"color": "#FBCE28", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/8.png"},
    "Sun Belt": {"color": "#FFA500", "logo": "https://a.espncdn.com/i/teamlogos/ncaa_conf/500/37.png"},
}
INDEPENDENT_TEAM_ASSETS = {
    "notre dame": {"label": "Notre Dame", "color": "#0C2340", "logo": "https://a.espncdn.com/i/teamlogos/ncaa/500/87.png"},
    "notre dame fighting irish": {"label": "Notre Dame", "color": "#0C2340", "logo": "https://a.espncdn.com/i/teamlogos/ncaa/500/87.png"},
    "uconn": {"label": "UConn", "color": "#000E2F", "logo": "https://a.espncdn.com/i/teamlogos/ncaa/500/41.png"},
    "uconn huskies": {"label": "UConn", "color": "#000E2F", "logo": "https://a.espncdn.com/i/teamlogos/ncaa/500/41.png"},
    "connecticut": {"label": "UConn", "color": "#000E2F", "logo": "https://a.espncdn.com/i/teamlogos/ncaa/500/41.png"},
    "connecticut huskies": {"label": "UConn", "color": "#000E2F", "logo": "https://a.espncdn.com/i/teamlogos/ncaa/500/41.png"},
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
GENERIC_SPREAD_COLUMNS = ["predicted_spread", "projected_spread", "spread"]
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
EXCITEMENT_COLUMNS = ["excitement_index", "excitement index", "excitementindex", "excitement"]
LINE_TYPE_COLUMNS = [
    "line_type",
    "linetype",
    "line type",
    "LineType",
    "Line Type",
    "lineType",
    "line_type_label",
    "model_version",
]
WIN_PROBABILITY_SPREAD_SCALE = 14.0
TEAM_ASSET_COLUMNS = [
    "team_id",
    "team_key",
    "team_logo",
    "team_logo_dark",
    "team_color",
    "team_secondary_color",
    "map_venue_id",
]


st.markdown(
    """
    <style>
      .schedule-shell {
        color: #0f172a;
      }
      .schedule-title {
        font-size: 42px;
        line-height: 1;
        font-weight: 950;
        margin: 0 0 6px 0;
        color: #0f172a;
      }
      .schedule-subtitle {
        font-size: 15px;
        color: #475569;
        max-width: 980px;
        margin-bottom: 18px;
      }
      .filter-label {
        color: rgb(49, 51, 63);
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: .35rem;
      }
      .panel-title {
        font-size: 22px;
        font-weight: 900;
        line-height: 1.1;
        margin: 0 0 8px 0;
        color: #0f172a;
      }
      .award-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 10px;
      }
      .award-card {
        min-height: 150px;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        background: #ffffff;
        padding: 12px;
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.06);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: space-between;
        text-align: center;
      }
      .award-name {
        font-size: 14px;
        font-weight: 900;
        color: #0f172a;
        text-align: center;
      }
      .award-meta {
        font-size: 11px;
        color: #64748b;
        line-height: 1.35;
        margin-top: 6px;
      }
      .award-team-row {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 8px;
        margin: 10px 0;
        min-width: 0;
      }
      .award-logo {
        width: 58px;
        height: 58px;
        border-radius: 999px;
        border: 1px solid #e2e8f0;
        background: #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        flex: 0 0 auto;
      }
      .award-logo img {
        max-width: 84%;
        max-height: 84%;
        object-fit: contain;
      }
      .award-logo span {
        font-size: 13px;
        font-weight: 950;
        color: #0f172a;
      }
      .award-value {
        font-size: 11px;
        color: #94a3b8;
        line-height: 1.25;
        margin-top: 4px;
        text-align: center;
      }
      .award-matchup-logos {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        margin: 10px 0;
      }
      .map-heading {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 14px;
        margin: 22px 0 8px 0;
      }
      @media (max-width: 900px) {
        .schedule-title { font-size: 34px; }
        .award-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .map-heading { display: block; }
      }
      @media (max-width: 560px) {
        .award-grid { grid-template-columns: 1fr; }
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def first_existing(columns: set[str], candidates: list[str]) -> str | None:
    return next((col for col in candidates if col in columns), None)


def normalize_id(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    value_str = str(value).strip()
    if value_str.endswith(".0"):
        value_str = value_str[:-2]
    return value_str or None


def team_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().lower().split())


def safe_text(value: object, fallback: str = "") -> str:
    if value is None or pd.isna(value):
        return fallback
    return str(value)


def coerce_bool(series: pd.Series, index: pd.Index) -> pd.Series:
    if series is None:
        return pd.Series(False, index=index)
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    numeric = pd.to_numeric(series, errors="coerce")
    normalized = series.astype(str).str.strip().str.lower()
    return normalized.isin({"true", "t", "1", "1.0", "yes", "y"}) | numeric.fillna(0).ne(0)


def normalize_season_type(value: object) -> str:
    if value is None or pd.isna(value):
        return "regular"
    value = str(value).strip().lower()
    return "postseason" if value == "postseason" else "regular"


def format_week_label(phase: str, week: object) -> str:
    week_number = int(week)
    return f"Postseason Week {week_number}" if phase == "postseason" else f"Week {week_number}"


def add_week_metadata(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "seasontype" in df.columns:
        df["season_phase"] = df["seasontype"].map(normalize_season_type)
    else:
        df["season_phase"] = "regular"
    df["phase_order"] = np.where(df["season_phase"].eq("postseason"), 1, 0)
    df["week_number"] = pd.to_numeric(df["week"], errors="coerce").astype("Int64")
    df["week_label"] = ""
    valid_week = df["week_number"].notna()
    df.loc[valid_week, "week_label"] = [
        format_week_label(phase, week)
        for phase, week in zip(df.loc[valid_week, "season_phase"], df.loc[valid_week, "week_number"])
    ]
    return df


def week_options(schedule: pd.DataFrame) -> list[str]:
    if schedule.empty or "week_number" not in schedule.columns:
        return []
    options = (
        schedule[schedule["week_number"].notna()]
        .drop_duplicates(subset=["season_phase", "week_number"])
        .sort_values(["phase_order", "week_number"])
    )
    return options["week_label"].tolist()


def map_time_options(schedule: pd.DataFrame) -> list[str]:
    return ["Before Season", *week_options(schedule), "After Season"]


def filter_by_week(schedule: pd.DataFrame, week_label: str) -> pd.DataFrame:
    if not week_label:
        return schedule.iloc[0:0].copy()
    return schedule[schedule["week_label"].eq(week_label)].copy()


def normalize_probability(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if value > 1:
        value = value / 100
    return float(np.clip(value, 0, 1))


def projected_winner_team(row: pd.Series) -> str:
    home_probability = normalize_probability(row.get("home_win_probability"))
    if home_probability is None:
        return ""
    return safe_text(row.get("hometeam")) if home_probability >= 0.5 else safe_text(row.get("awayteam"))


def implied_margin_from_probability(probability: pd.Series) -> pd.Series:
    probs = pd.to_numeric(probability, errors="coerce").clip(0.01, 0.99)
    return WIN_PROBABILITY_SPREAD_SCALE * np.log(probs / (1 - probs))


def projected_winner_label(row: pd.Series) -> str:
    home_probability = normalize_probability(row.get("home_win_probability"))
    if home_probability is None:
        return ""
    winner = projected_winner_team(row)
    winner_probability = home_probability if home_probability >= 0.5 else 1 - home_probability
    return f"{winner}: {winner_probability:.1%}"


def prediction_outcome(row: pd.Series) -> str:
    if not bool(row.get("completed", False)):
        return ""
    projected_team = team_key(projected_winner_team(row))
    actual_winner = team_key(row.get("winner_team"))
    if not projected_team or not actual_winner:
        return ""
    return "correct" if projected_team == actual_winner else "wrong"


def weekly_row_style(outcomes: pd.Series):
    def style_row(row: pd.Series) -> list[str]:
        outcome = outcomes.get(row.name, "")
        if outcome == "correct":
            return ["background-color: #dcfce7; color: #14532d;"] * len(row)
        if outcome == "wrong":
            return ["background-color: #fee2e2; color: #7f1d1d;"] * len(row)
        return [""] * len(row)

    return style_row


def fmt_line_type(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    normalized = str(value).strip()
    if not normalized:
        return ""
    return normalized.replace("_", " ").title()


def fmt_time(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.to_datetime(value, utc=True).tz_convert(ET_TZ).strftime("%a, %b %-d | %-I:%M %p")


def initials(name: str) -> str:
    return "".join(part[:1] for part in str(name).split()).upper()[:3] or "CFB"


def conference_map_asset(team: object, conference: object, conference_assets: dict[str, dict[str, str]]) -> tuple[str, dict[str, str]]:
    team_asset = INDEPENDENT_TEAM_ASSETS.get(team_key(team))
    if safe_text(conference) in INDEPENDENT_CONFERENCES and team_asset:
        return team_asset["label"], team_asset
    conference_name = safe_text(conference, "Unknown")
    return conference_name, conference_assets.get(conference_name, {"color": "#64748b", "logo": ""})


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
def get_available_seasons() -> list[int]:
    df = read_df(
        f"""
        SELECT DISTINCT season::int AS season
        FROM public.game_data
        WHERE season IS NOT NULL
          AND {FBS_FILTER}
        ORDER BY season DESC
        """
    )
    return df["season"].astype(int).tolist() if not df.empty else []


@st.cache_data(ttl=300)
def get_team_game_ppa_stats(season: int) -> pd.DataFrame:
    stat_columns = get_table_columns("team_advanced_game_stats")
    required_columns = {"game_id", "team", "offense_ppa", "defense_ppa"}
    if not required_columns.issubset(stat_columns):
        return pd.DataFrame(columns=PPA_STATS_COLUMNS)

    fbs_filter = FBS_FILTER.replace("homeclassification", "gd.homeclassification").replace(
        "awayclassification",
        "gd.awayclassification",
    )

    df = read_df(
        f"""
        SELECT
            gs.game_id::text AS game_id,
            gs.team,
            gs.offense_ppa::float AS offense_ppa,
            gs.defense_ppa::float AS defense_ppa
        FROM public.team_advanced_game_stats gs
        JOIN public.game_data gd
          ON gd.id::text = gs.game_id::text
        WHERE gd.season = :season
          AND {fbs_filter}
          AND gs.team IS NOT NULL
          AND (gs.offense_ppa IS NOT NULL OR gs.defense_ppa IS NOT NULL)
        """,
        {"season": int(season)},
    )
    if df.empty:
        return pd.DataFrame(columns=PPA_STATS_COLUMNS)

    df = df.copy()
    df["game_id"] = df["game_id"].map(normalize_id)
    df["team_key"] = df["team"].map(team_key)
    df = df.drop_duplicates(subset=["game_id", "team_key"], keep="first")
    for col in ["offense_ppa", "defense_ppa"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["offense_ppa_percentile"] = np.nan
    df["defense_ppa_percentile"] = np.nan

    offense_values = df["offense_ppa"].dropna()
    if not offense_values.empty:
        df.loc[df["offense_ppa"].notna(), "offense_ppa_percentile"] = (
            df.loc[df["offense_ppa"].notna(), "offense_ppa"].rank(pct=True) * 100
        )

    defense_values = df["defense_ppa"].dropna()
    if not defense_values.empty:
        df.loc[df["defense_ppa"].notna(), "defense_ppa_percentile"] = (
            (-df.loc[df["defense_ppa"].notna(), "defense_ppa"]).rank(pct=True) * 100
        )

    return df[PPA_STATS_COLUMNS]


def prediction_margin_sql(prediction_columns: set[str]) -> str:
    for col in PREDICTED_HOME_MARGIN_COLUMNS:
        if col in prediction_columns:
            return f"p.{quote_identifier(col)}::float"
    for col in HOME_SPREAD_COLUMNS:
        if col in prediction_columns:
            return f"(-1 * p.{quote_identifier(col)}::float)"
    for col in GENERIC_SPREAD_COLUMNS:
        if col in prediction_columns:
            return f"(-1 * p.{quote_identifier(col)}::float)"
    return "NULL::float"


def prediction_column_sql(prediction_columns: set[str], candidates: list[str]) -> str:
    for col in candidates:
        if col in prediction_columns:
            return f"p.{quote_identifier(col)}::float"
    return "NULL::float"


def prediction_text_column_sql(prediction_columns: set[str], candidates: list[str]) -> str:
    for col in candidates:
        if col in prediction_columns:
            return f"p.{quote_identifier(col)}::text"
    return "NULL::text"


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

    run_time_columns = [col for col in ["completed_at", "created_at"] if col in run_columns]
    if run_time_columns:
        run_time_sql = "COALESCE(" + ", ".join(f"r.{quote_identifier(col)}" for col in run_time_columns) + ")"
        pregame_filter = f"AND (g.startdate IS NULL OR {run_time_sql} IS NULL OR {run_time_sql} <= g.startdate)"
    else:
        pregame_filter = ""

    return f"""
        WITH latest_predictions AS (
            SELECT DISTINCT ON (p.gameid)
                p.*
            FROM {prediction_table_sql(table_name)} p
            JOIN public.game_prediction_runs r
              ON p.game_prediction_run_id = r.game_prediction_run_id
            JOIN public.game_data g
              ON p.gameid = g.id::text
            WHERE r.season = :season
              AND g.season = :season
              {status_filter}
              {pregame_filter}
            ORDER BY p.gameid, {order_sql}{prediction_row_order_sql(prediction_columns)}
        )
    """


@st.cache_data(ttl=300)
def get_schedule_games(season: int) -> pd.DataFrame:
    df = read_df(
        f"""
        SELECT *
        FROM public.game_data
        WHERE season = :season
          AND {FBS_FILTER}
          AND hometeam IS NOT NULL
          AND awayteam IS NOT NULL
        ORDER BY week NULLS LAST, startdate NULLS LAST, awayteam, hometeam
        """,
        {"season": int(season)},
    )
    if df.empty:
        return df

    df = df.copy()
    df = add_week_metadata(df)
    df["game_id"] = df["id"].map(normalize_id) if "id" in df.columns else df.index.astype(str)
    df["hometeam_key"] = df["hometeam"].map(team_key)
    df["awayteam_key"] = df["awayteam"].map(team_key)
    df["startdate"] = pd.to_datetime(df["startdate"], errors="coerce", utc=True)
    for col in ["homeid", "awayid", "venueid"]:
        if col in df.columns:
            df[col] = df[col].map(normalize_id)
    for col in ["homepoints", "awaypoints"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")

    neutral_col = first_existing(
        set(df.columns),
        ["is neutral", "neutralsite", "is_neutral", "isneutral", "neutral_site", "neutral"],
    )
    df["is_neutral"] = coerce_bool(df[neutral_col], df.index) if neutral_col else False
    df["completed"] = df["homepoints"].notna() & df["awaypoints"].notna()
    df["winner_team"] = np.select(
        [
            df["completed"] & (df["homepoints"] > df["awaypoints"]),
            df["completed"] & (df["awaypoints"] > df["homepoints"]),
        ],
        [df["hometeam"], df["awayteam"]],
        default=None,
    )
    df["loser_team"] = np.select(
        [
            df["completed"] & (df["homepoints"] > df["awaypoints"]),
            df["completed"] & (df["awaypoints"] > df["homepoints"]),
        ],
        [df["awayteam"], df["hometeam"]],
        default=None,
    )
    df["matchup"] = np.where(
        df["is_neutral"],
        df["awayteam"].astype(str) + " vs " + df["hometeam"].astype(str),
        df["awayteam"].astype(str) + " at " + df["hometeam"].astype(str),
    )
    return df


@st.cache_data(ttl=300)
def get_prediction_data(season: int) -> pd.DataFrame:
    prediction_table, prediction_columns = get_prediction_source()
    run_columns = get_table_columns("game_prediction_runs")
    if "gameid" not in prediction_columns:
        return pd.DataFrame()

    select_parts = [
        "p.gameid::text AS game_id",
        f"{prediction_column_sql(prediction_columns, HOME_WIN_PROBABILITY_COLUMNS)} AS homewinprob",
        f"{prediction_column_sql(prediction_columns, AWAY_WIN_PROBABILITY_COLUMNS)} AS awaywinprob",
        f"{prediction_text_column_sql(prediction_columns, LINE_TYPE_COLUMNS)} AS line_type",
    ]
    if "model_version" in prediction_columns:
        select_parts.append("p.model_version AS model_version")
    margin_sql = prediction_margin_sql(prediction_columns)
    select_parts.append(f"{margin_sql} AS predicted_home_margin")

    if "game_prediction_run_id" in prediction_columns and {"season", "game_prediction_run_id"}.issubset(run_columns):
        sql = f"""
        {latest_prediction_ctes(prediction_table, run_columns, prediction_columns)}
        SELECT
            {", ".join(select_parts)}
        FROM latest_predictions p
        JOIN public.game_data g
          ON p.gameid = g.id::text
        WHERE g.season = :season
        """
        df = read_df(sql, {"season": int(season)})
    else:
        sql = f"""
        SELECT {", ".join(select_parts)}
        FROM {prediction_table_sql(prediction_table)} p
        JOIN public.game_data g
          ON p.gameid = g.id::text
        WHERE g.season = :season
        """
        df = read_df(sql, {"season": int(season)})

    if df.empty:
        return df
    df["game_id"] = df["game_id"].map(normalize_id)
    return df.drop_duplicates(subset=["game_id"], keep="last")


@st.cache_data(ttl=300)
def get_team_map() -> pd.DataFrame:
    try:
        return read_df("SELECT * FROM public.team_map")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_venue_map() -> pd.DataFrame:
    try:
        return read_df("SELECT * FROM public.venue_map")
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def get_team_assets() -> pd.DataFrame:
    team_map = get_team_map()
    if team_map.empty:
        return pd.DataFrame(columns=TEAM_ASSET_COLUMNS)

    columns = set(team_map.columns)
    id_col = first_existing(columns, ["Id", "id", "TeamId", "teamId", "team_id"])
    name_col = first_existing(columns, ["cfb_name", "team", "school", "Team", "School"])
    field_map = {
        "team_logo": ["Logo", "logo", "logo_url", "Logo_URL"],
        "team_logo_dark": ["DarkLogo", "dark_logo", "Logo_Dark", "LogoDark", "dark_logo_url", "DarkLogoUrl", "Dark_Logo"],
        "team_color": ["Color", "color", "primary_color", "PrimaryColor"],
        "team_secondary_color": [
            "SecondaryColor",
            "Secondary Color",
            "secondary_color",
            "Secondary",
            "secondary",
            "AltColor",
            "AlternateColor",
            "alternate_color",
            "AccentColor",
        ],
        "map_venue_id": ["VenueId", "venueid", "venue_id", "home_venue_id"],
    }

    assets = pd.DataFrame(index=team_map.index)
    assets["team_id"] = team_map[id_col].map(normalize_id) if id_col else None
    assets["team_key"] = team_map[name_col].map(team_key) if name_col else ""
    for output_col, candidates in field_map.items():
        source_col = first_existing(columns, candidates)
        assets[output_col] = team_map[source_col] if source_col else None
    assets["map_venue_id"] = assets["map_venue_id"].map(normalize_id)

    secondary_override_keys = {team_key(team) for team in USE_SECONDARY_COLOR_FOR_TEAMS}
    if secondary_override_keys:
        secondary_values = assets["team_secondary_color"].astype(str).str.strip()
        valid_secondary = assets["team_secondary_color"].notna() & ~secondary_values.str.lower().isin(
            {"", "nan", "none", "null"}
        )
        use_secondary = assets["team_key"].isin(secondary_override_keys) & valid_secondary
        assets.loc[use_secondary, "team_color"] = assets.loc[use_secondary, "team_secondary_color"]

    return assets[TEAM_ASSET_COLUMNS]


def attach_team_logos(schedule: pd.DataFrame) -> pd.DataFrame:
    if schedule.empty:
        return schedule

    df = schedule.copy()
    for col in ["home_logo", "away_logo"]:
        if col not in df.columns:
            df[col] = None

    assets = get_team_assets()
    if assets.empty or assets["team_logo"].isna().all():
        return df

    if assets["team_id"].notna().any():
        logo_by_id = assets[["team_id", "team_logo"]].dropna(subset=["team_id"]).drop_duplicates(subset=["team_id"])
        for side in ["home", "away"]:
            df = df.merge(
                logo_by_id.rename(columns={"team_id": f"{side}id", "team_logo": f"{side}_logo_from_id"}),
                on=f"{side}id",
                how="left",
            )
            df[f"{side}_logo"] = df[f"{side}_logo"].combine_first(df[f"{side}_logo_from_id"])
            df = df.drop(columns=[f"{side}_logo_from_id"])

    if assets["team_key"].astype(bool).any():
        logo_by_name = assets[["team_key", "team_logo"]].dropna(subset=["team_key"]).drop_duplicates(subset=["team_key"])
        for side in ["home", "away"]:
            key_col = f"_{side}_team_key"
            df[key_col] = df[f"{side}team"].map(team_key)
            df = df.merge(
                logo_by_name.rename(columns={"team_key": key_col, "team_logo": f"{side}_logo_from_name"}),
                on=key_col,
                how="left",
            )
            df[f"{side}_logo"] = df[f"{side}_logo"].combine_first(df[f"{side}_logo_from_name"])
            df = df.drop(columns=[f"{side}_logo_from_name", key_col])

    return df


def attach_predictions(schedule: pd.DataFrame, predictions: pd.DataFrame) -> pd.DataFrame:
    if schedule.empty:
        return schedule
    if predictions.empty:
        schedule = schedule.copy()
        schedule["home_win_probability"] = np.nan
        schedule["predicted_home_margin"] = np.nan
        schedule["line_type"] = ""
        return schedule

    df = schedule.merge(predictions, on="game_id", how="left", suffixes=("", "_prediction"))
    if "line_type_prediction" in df.columns:
        existing_line_type = df["line_type"] if "line_type" in df.columns else pd.Series("", index=df.index)
        df["line_type"] = df["line_type_prediction"].combine_first(existing_line_type)
        df = df.drop(columns=["line_type_prediction"])

    home_probability = (
        pd.to_numeric(df["homewinprob"].map(normalize_probability), errors="coerce")
        if "homewinprob" in df.columns
        else pd.Series(np.nan, index=df.index)
    )
    away_probability = (
        pd.to_numeric(df["awaywinprob"].map(normalize_probability), errors="coerce")
        if "awaywinprob" in df.columns
        else pd.Series(np.nan, index=df.index)
    )
    df["home_win_probability"] = home_probability.combine_first(1 - away_probability)
    df["predicted_home_margin"] = pd.to_numeric(df.get("predicted_home_margin"), errors="coerce")
    if "line_type" not in df.columns:
        df["line_type"] = ""
    return df


def weekly_table(schedule: pd.DataFrame, week_label: str, conferences: list[str]):
    df = filter_by_week(schedule, week_label)
    if conferences:
        df = df[df["homeconference"].isin(conferences) | df["awayconference"].isin(conferences)]
    df = df.sort_values(["startdate", "awayteam", "hometeam"], na_position="last")
    outcomes = df.apply(prediction_outcome, axis=1) if not df.empty else pd.Series(dtype=str)
    display = pd.DataFrame(
        {
            "Kickoff": df["startdate"].map(fmt_time),
            "Matchup": df["matchup"],
            "Projected Winner": df.apply(projected_winner_label, axis=1),
            "Line Type": df["line_type"].map(fmt_line_type) if "line_type" in df.columns else "",
            "Score": np.where(
                df["completed"],
                df["awaypoints"].astype("Int64").astype(str) + "-" + df["homepoints"].astype("Int64").astype(str),
                "",
            ),
        }
    )
    return display.style.apply(weekly_row_style(outcomes), axis=1)


def filtered_week_games(schedule: pd.DataFrame, week_label: str, conferences: list[str]) -> pd.DataFrame:
    df = filter_by_week(schedule, week_label)
    if conferences:
        df = df[df["homeconference"].isin(conferences) | df["awayconference"].isin(conferences)]
    return df


def all_teams(schedule: pd.DataFrame) -> pd.DataFrame:
    rows = pd.concat(
        [
            schedule[["homeid", "hometeam", "homeconference"]].rename(
                columns={"homeid": "team_id", "hometeam": "team", "homeconference": "conference"}
            ),
            schedule[["awayid", "awayteam", "awayconference"]].rename(
                columns={"awayid": "team_id", "awayteam": "team", "awayconference": "conference"}
            ),
        ],
        ignore_index=True,
    ).dropna(subset=["team_id", "team"])
    rows["team_id"] = rows["team_id"].map(normalize_id)
    rows["team_key"] = rows["team"].map(team_key)
    return rows.drop_duplicates(subset=["team_key"], keep="first")


def team_locations(schedule: pd.DataFrame) -> pd.DataFrame:
    teams = all_teams(schedule)
    home_games = schedule[(~schedule["is_neutral"]) & schedule["homeid"].notna() & schedule["venueid"].notna()].copy()
    if home_games.empty:
        teams["venue_id"] = None
    else:
        venues = (
            home_games.groupby(["homeid", "venueid"])
            .size()
            .reset_index(name="games")
            .sort_values(["homeid", "games"], ascending=[True, False])
            .drop_duplicates(subset=["homeid"])
            .rename(columns={"homeid": "team_id", "venueid": "venue_id"})
        )
        teams = teams.merge(venues[["team_id", "venue_id"]], on="team_id", how="left")

    assets = get_team_assets()
    if not assets.empty and assets["team_id"].notna().any():
        asset_columns = [col for col in TEAM_ASSET_COLUMNS if col != "team_key"]
        teams = teams.merge(assets[asset_columns].drop_duplicates(subset=["team_id"]), on="team_id", how="left")
        if "map_venue_id" in teams.columns:
            teams["venue_id"] = teams["map_venue_id"].combine_first(teams["venue_id"])

    venue_map = get_venue_map()
    if not venue_map.empty:
        venue_cols = set(venue_map.columns)
        venue_id_col = first_existing(venue_cols, ["Id", "id", "VenueId", "venueid", "venue_id"])
        lat_col = first_existing(venue_cols, ["Latitude", "latitude", "lat"])
        lon_col = first_existing(venue_cols, ["Longitude", "longitude", "lng", "lon"])
        name_col = first_existing(venue_cols, ["Name", "name", "Venue", "venue", "venue_name"])
        if venue_id_col and lat_col and lon_col:
            venues = pd.DataFrame(
                {
                    "venue_id": venue_map[venue_id_col].map(normalize_id),
                    "latitude": pd.to_numeric(venue_map[lat_col], errors="coerce"),
                    "longitude": pd.to_numeric(venue_map[lon_col], errors="coerce"),
                    "stadium": venue_map[name_col] if name_col else "",
                }
            ).drop_duplicates(subset=["venue_id"])
            teams = teams.merge(venues, on="venue_id", how="left")

    for col, default in [
        ("team_logo", None),
        ("team_logo_dark", None),
        ("team_color", "#0f172a"),
        ("team_secondary_color", None),
        ("latitude", np.nan),
        ("longitude", np.nan),
        ("stadium", ""),
    ]:
        if col not in teams.columns:
            teams[col] = default
    return teams.dropna(subset=["latitude", "longitude"]).copy()


def compute_land_ownership_history(
    schedule: pd.DataFrame,
    teams: pd.DataFrame,
    map_checkpoint: str,
    owner_teams: pd.DataFrame | None = None,
) -> tuple[dict[str, str], dict[str, list[dict[str, str]]]]:
    teams = teams.copy()
    teams["team_key"] = teams["team"].map(team_key)
    owners = {key: key for key in teams["team_key"].dropna().astype(str)}
    team_lookup_columns = ["team", "conference", "team_logo", "team_logo_dark", "team_color"]
    lookup_teams = teams if owner_teams is None else pd.concat([teams, owner_teams], ignore_index=True)
    lookup_teams = lookup_teams.copy()
    lookup_teams["team_key"] = lookup_teams["team"].map(team_key)
    team_lookup = (
        lookup_teams.drop_duplicates(subset=["team_key"])
        .set_index("team_key")[team_lookup_columns]
        .to_dict("index")
    )

    played = schedule[
        schedule["week_number"].notna()
        & schedule["completed"]
        & schedule["winner_team"].notna()
        & schedule["loser_team"].notna()
    ].copy()
    played["_week_number"] = pd.to_numeric(played["week_number"], errors="coerce").astype(int)

    if map_checkpoint == "Before Season":
        played = played.iloc[0:0].copy()
    elif map_checkpoint == "After Season":
        pass
    else:
        selected_rows = schedule[schedule["week_label"].eq(map_checkpoint)]
        if selected_rows.empty:
            selected_phase_order = 0
            selected_week_number = 0
        else:
            selected_phase_order = int(selected_rows["phase_order"].iloc[0])
            selected_week_number = int(selected_rows["week_number"].iloc[0])
        played = played[
            (played["phase_order"] < selected_phase_order)
            | (
                played["phase_order"].eq(selected_phase_order)
                & played["_week_number"].le(selected_week_number)
            )
        ]

    histories: dict[str, list[dict[str, str]]] = {seed_team: [] for seed_team in owners}

    def snapshot(label: str) -> None:
        for seed_team, owner_id in owners.items():
            owner = team_lookup.get(owner_id, team_lookup.get(seed_team, {}))
            histories[seed_team].append(
                {
                    "label": label,
                    "team": safe_text(owner.get("team"), owner_id),
                    "conference": safe_text(owner.get("conference"), "Unknown"),
                }
            )

    snapshot("Start of Season")
    all_week_groups = (
        schedule[schedule["week_number"].notna()][["phase_order", "season_phase", "week_number", "week_label"]]
        .drop_duplicates()
        .sort_values(["phase_order", "week_number"])
        .reset_index(drop=True)
    )
    next_week_labels = {
        (int(row["phase_order"]), int(row["week_number"])): (
            str(all_week_groups.iloc[idx + 1]["week_label"])
            if idx + 1 < len(all_week_groups)
            else f"After {row['week_label']}"
        )
        for idx, row in all_week_groups.iterrows()
    }

    week_groups = (
        played[["phase_order", "season_phase", "_week_number", "week_label"]]
        .drop_duplicates()
        .sort_values(["phase_order", "_week_number"])
    )
    for _, week_row in week_groups.iterrows():
        week_games = played[
            played["phase_order"].eq(int(week_row["phase_order"]))
            & played["_week_number"].eq(int(week_row["_week_number"]))
        ].sort_values("startdate")
        for game in week_games.itertuples(index=False):
            winner = team_key(getattr(game, "winner_team"))
            loser = team_key(getattr(game, "loser_team"))
            if not winner or not loser or winner == loser:
                continue
            if loser not in set(owners.values()):
                continue
            for seed_team, current_owner in list(owners.items()):
                if current_owner == loser:
                    owners[seed_team] = winner
        snapshot(
            next_week_labels.get(
                (int(week_row["phase_order"]), int(week_row["_week_number"])),
                f"After {week_row['week_label']}",
            )
        )

    for seed_team, team_history in histories.items():
        compact_history = []
        previous_owner = None
        for entry in team_history:
            owner_key = (entry["team"], entry["conference"])
            if owner_key == previous_owner:
                continue
            compact_history.append(entry)
            previous_owner = owner_key
        histories[seed_team] = compact_history

    return owners, histories


def build_county_conquest_map(
    teams: pd.DataFrame,
    owners: dict[str, str],
    ownership_histories: dict[str, list[dict[str, str]]],
    conference_assets: dict[str, dict[str, str]],
    source_label: str,
    map_scope: str,
    map_mode: str,
    render_key: str,
    owner_teams: pd.DataFrame | None = None,
) -> str:
    if teams.empty:
        return ""

    teams = teams.copy()
    teams["team_key"] = teams["team"].map(team_key)
    team_lookup_columns = ["team", "conference", "team_logo", "team_logo_dark", "team_color"]
    lookup_teams = teams if owner_teams is None else pd.concat([teams, owner_teams], ignore_index=True)
    lookup_teams = lookup_teams.copy()
    lookup_teams["team_key"] = lookup_teams["team"].map(team_key)
    team_lookup = (
        lookup_teams.drop_duplicates(subset=["team_key"])
        .set_index("team_key")[team_lookup_columns]
        .to_dict("index")
    )
    seeds = []
    for row in teams.itertuples(index=False):
        seed_key = str(row.team_key)
        owner_key = owners.get(seed_key, seed_key)
        owner = team_lookup.get(owner_key, team_lookup.get(seed_key, {}))
        owner_team = safe_text(owner.get("team"), owner_key)
        owner_conference = safe_text(owner.get("conference"), "Unknown")
        if map_mode == "Team":
            display_color = safe_text(owner.get("team_color"), "#64748b") or "#64748b"
            logo = safe_text(owner.get("team_logo_dark"), "") or safe_text(owner.get("team_logo"), "")
            logo_name = owner_team
            logo_key = f"team:{owner_key}"
            logo_radius = TEAM_LOGO_RADIUS
            logo_size = TEAM_LOGO_SIZE
            logo_font_size = TEAM_LOGO_FONT_SIZE
            logo_bubble = False
        else:
            logo_name, assets = conference_map_asset(owner_team, owner_conference, conference_assets)
            display_color = assets.get("color", "#64748b")
            logo = assets.get("logo", "")
            logo_key = f"conference:{logo_name}"
            logo_radius = CONFERENCE_LOGO_RADIUS
            logo_size = CONFERENCE_LOGO_SIZE
            logo_font_size = CONFERENCE_LOGO_FONT_SIZE
            logo_bubble = True
        seeds.append(
            {
                "seedTeam": str(row.team),
                "seedTeamId": seed_key,
                "ownerTeam": owner_team,
                "ownerTeamId": owner_key,
                "conference": owner_conference,
                "lat": float(row.latitude),
                "lon": float(row.longitude),
                "color": display_color,
                "logo": logo,
                "logoName": logo_name,
                "logoGroupKey": logo_key,
                "logoRadius": logo_radius,
                "logoSize": logo_size,
                "logoFontSize": logo_font_size,
                "logoBubble": logo_bubble,
                "history": ownership_histories.get(seed_key, []),
            }
        )

    seeds_json = json.dumps(seeds)
    source = html.escape(source_label)
    map_scope_json = json.dumps(map_scope)
    escaped_map_mode = html.escape(map_mode)
    escaped_render_key = html.escape(render_key)

    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
      <script src="https://cdn.jsdelivr.net/npm/topojson-client@3"></script>
      <style>
        html, body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
        .map-shell {{ width: 100%; height: 760px; position: relative; border: 1px solid #cbd5e1; border-radius: 8px; overflow: hidden; background: #e5e7eb; }}
        #county-map {{ width: 100%; height: 100%; display: block; }}
        #logo-layer {{ position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }}
        .map-chip {{
          position: absolute;
          z-index: 1000;
          top: 14px;
          left: 14px;
          max-width: 620px;
          background: rgba(255,255,255,.94);
          border: 1px solid rgba(15,23,42,.16);
          border-radius: 8px;
          padding: 9px 11px;
          font-size: 13px;
          font-weight: 800;
          color: #0f172a;
          box-shadow: 0 10px 24px rgba(15,23,42,.14);
        }}
        .conf-logo-bg {{ fill: #fff; stroke: #0f172a; stroke-width: 2.5px; filter: drop-shadow(0 6px 12px rgba(15,23,42,.24)); }}
        .conf-logo-text {{ font-size: 11px; font-weight: 950; fill: #0f172a; text-anchor: middle; dominant-baseline: middle; }}
        .draggable-logo {{ cursor: grab; pointer-events: all; }}
        .draggable-logo.dragging {{ cursor: grabbing; }}
        .county {{ stroke: rgba(255,255,255,.68); stroke-width: .22px; vector-effect: non-scaling-stroke; }}
        .county:hover {{ stroke: #0f172a; stroke-width: 1.2px; }}
        .state-border {{ fill: none; stroke: rgba(15,23,42,.42); stroke-width: .75px; vector-effect: non-scaling-stroke; pointer-events: none; }}
        .county-tooltip {{
          position: absolute;
          z-index: 2000;
          pointer-events: none;
          display: none;
          max-width: 320px;
          background: rgba(15, 23, 42, .96);
          color: #fff;
          border: 1px solid rgba(255,255,255,.16);
          border-radius: 8px;
          padding: 10px 11px;
          font-size: 12px;
          line-height: 1.35;
          box-shadow: 0 14px 32px rgba(15,23,42,.28);
          white-space: pre-line;
        }}
      </style>
    </head>
    <body>
      <div class="map-shell" data-render-key="{escaped_render_key}">
        <svg id="county-map" viewBox="0 0 1200 760" preserveAspectRatio="xMidYMid meet"></svg>
        <svg id="logo-layer" viewBox="0 0 1200 760" preserveAspectRatio="xMidYMid meet"></svg>
        <div class="map-chip">{source}</div>
        <div id="county-tooltip" class="county-tooltip"></div>
      </div>
      <script>
        const seeds = {seeds_json};
        const mapScope = {map_scope_json};
        const mapMode = "{escaped_map_mode}";
        const renderKey = "{escaped_render_key}";
        const width = 1200;
        const height = 760;
        const svg = d3.select("#county-map");
        const logoLayer = d3.select("#logo-layer");
        const tooltip = d3.select("#county-tooltip");
        const excludedStateIds = new Set(["60", "66", "69", "72", "78"]);
        const logoScopeKey = String(mapScope || "default").toLowerCase().replace(/[^a-z0-9]+/g, "-");
        const logoStorageKey = `cfb-conquest-logo-positions-v6-${{logoScopeKey}}-${{mapMode.toLowerCase()}}`;

        function getStoredLogoPositions() {{
          try {{
            return JSON.parse(window.localStorage.getItem(logoStorageKey) || "{{}}");
          }} catch (_) {{
            return {{}};
          }}
        }}

        function setStoredLogoPosition(placementKey, x, y) {{
          try {{
            const positions = getStoredLogoPositions();
            positions[placementKey] = {{ x, y }};
            window.localStorage.setItem(logoStorageKey, JSON.stringify(positions));
          }} catch (_) {{}}
        }}

        function logoInitials(name) {{
          return String(name || "").split(" ").map(part => part[0]).join("").slice(0, 3).toUpperCase();
        }}

        function drawLogo(logoInfo, x, y, count, options = {{}}) {{
          const placementKey = options.placementKey || logoInfo.key;
          const stored = options.useStored === false ? null : getStoredLogoPositions()[placementKey];
          const startX = Number.isFinite(stored?.x) ? stored.x : x;
          const startY = Number.isFinite(stored?.y) ? stored.y : y;
          const group = logoLayer.append("g")
            .attr("class", "draggable-logo")
            .attr("transform", `translate(${{startX}},${{startY}})`)
            .datum({{
              placementKey,
              x: startX,
              y: startY,
              radius: logoInfo.radius || 18,
              logoInfo,
              count
            }});
          const radius = logoInfo.radius || 18;
          const imageSize = logoInfo.size || 32;
          if (logoInfo.bubble) {{
            group.append("circle").attr("class", "conf-logo-bg").attr("r", radius);
          }}
          if (logoInfo.logo) {{
            group.append("image")
              .attr("class", "logo-image")
              .attr("href", logoInfo.logo)
              .attr("x", -imageSize / 2)
              .attr("y", -imageSize / 2)
              .attr("width", imageSize)
              .attr("height", imageSize)
              .attr("preserveAspectRatio", "xMidYMid meet");
          }} else {{
            group.append("text")
              .attr("class", "conf-logo-text")
              .attr("font-size", logoInfo.fontSize || 11)
              .attr("paint-order", "stroke")
              .attr("stroke", logoInfo.bubble ? "none" : "#ffffff")
              .attr("stroke-width", logoInfo.bubble ? 0 : 3)
              .text(logoInitials(logoInfo.name));
          }}
          group.append("title").text(`${{logoInfo.name}}\\n${{count}} counties\\nDrag to reposition`);
          group.on("dblclick", function (event, d) {{
            event.preventDefault();
            event.stopPropagation();
            drawLogo(
              d.logoInfo,
              Math.max(d.radius, Math.min(width - d.radius, d.x + d.radius * 1.6)),
              Math.max(d.radius, Math.min(height - d.radius, d.y + d.radius * 1.2)),
              d.count,
              {{ placementKey: `${{d.placementKey}}:copy:${{Date.now()}}`, useStored: false }}
            );
          }});
          group.call(
            d3.drag()
              .on("start", function () {{
                tooltip.style("display", "none");
                d3.select(this).classed("dragging", true).raise();
              }})
              .on("drag", function (event, d) {{
                d.x = Math.max(d.radius, Math.min(width - d.radius, event.x));
                d.y = Math.max(d.radius, Math.min(height - d.radius, event.y));
                d3.select(this).attr("transform", `translate(${{d.x}},${{d.y}})`);
              }})
              .on("end", function (event, d) {{
                d3.select(this).classed("dragging", false);
                setStoredLogoPosition(d.placementKey, d.x, d.y);
              }})
          );
        }}

        function centerForCounties(counties) {{
          if (!counties.length) return null;
          const meanX = d3.mean(counties, d => d.centroid[0]);
          const meanY = d3.mean(counties, d => d.centroid[1]);
          let closest = counties[0];
          let bestDistance = Infinity;
          for (const county of counties) {{
            const distance = (county.centroid[0] - meanX) ** 2 + (county.centroid[1] - meanY) ** 2;
            if (distance < bestDistance) {{
              bestDistance = distance;
              closest = county;
            }}
          }}
          return {{ x: closest.centroid[0], y: closest.centroid[1], count: counties.length }};
        }}

        function largestContiguousMass(counties, countyNeighbors, path) {{
          if (!counties.length) return [];
          const countyByIndex = new Map(counties.map(county => [county.topoIndex, county]));
          const unvisited = new Set(countyByIndex.keys());
          let bestComponent = [];
          let bestArea = -Infinity;

          while (unvisited.size) {{
            const start = unvisited.values().next().value;
            const stack = [start];
            const component = [];
            unvisited.delete(start);

            while (stack.length) {{
              const current = stack.pop();
              const county = countyByIndex.get(current);
              if (!county) continue;
              component.push(county);

              for (const neighbor of countyNeighbors[current] || []) {{
                if (unvisited.has(neighbor)) {{
                  unvisited.delete(neighbor);
                  stack.push(neighbor);
                }}
              }}
            }}

            const componentArea = d3.sum(component, county => Math.max(path.area(county), 0));
            if (
              componentArea > bestArea
              || (componentArea === bestArea && component.length > bestComponent.length)
            ) {{
              bestArea = componentArea;
              bestComponent = component;
            }}
          }}

          return bestComponent.length ? bestComponent : counties;
        }}

        function haversineMiles(a, b) {{
          const radius = 3958.8;
          const toRad = value => value * Math.PI / 180;
          const dLat = toRad(b.lat - a.lat);
          const dLon = toRad(b.lon - a.lon);
          const lat1 = toRad(a.lat);
          const lat2 = toRad(b.lat);
          const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
          return radius * 2 * Math.asin(Math.sqrt(h));
        }}

        function nearestGeoSeed(lonLat, projectedSeeds) {{
          let bestSeed = null;
          let bestDistance = Infinity;
          for (const seed of projectedSeeds) {{
            const distance = haversineMiles({{ lat: lonLat[1], lon: lonLat[0] }}, seed);
            if (distance < bestDistance) {{
              bestDistance = distance;
              bestSeed = seed;
            }}
          }}
          return bestSeed;
        }}

        function countyName(county) {{
          const id = String(county.id).padStart(5, "0");
          const props = county.properties || {{}};
          return props.name || props.NAME || props.namelsad || props.NAMELSAD || `County FIPS ${{id}}`;
        }}

        function ownerTimeline(seed) {{
          if (!seed || !seed.history || !seed.history.length) return "";
          return seed.history
            .map(item => `${{item.label}}: ${{item.team}}`)
            .join("\\n");
        }}

        function tooltipText(county) {{
          return `${{countyName(county)}}\\n${{ownerTimeline(county.properties.seed)}}`;
        }}

        function moveTooltip(event) {{
          const shell = document.querySelector(".map-shell").getBoundingClientRect();
          const x = event.clientX - shell.left + 14;
          const y = event.clientY - shell.top + 14;
          tooltip
            .style("left", `${{Math.min(x, shell.width - 340)}}px`)
            .style("top", `${{Math.min(y, shell.height - 170)}}px`);
        }}

        d3.json("https://cdn.jsdelivr.net/npm/us-atlas@3/counties-10m.json").then((us) => {{
          const states = topojson.feature(us, us.objects.states);
          const allCounties = topojson.feature(us, us.objects.counties).features;
          const countyNeighbors = topojson.neighbors(us.objects.counties.geometries);
          const countyIndexById = new Map(
            allCounties.map((county, index) => [String(county.id).padStart(5, "0"), index])
          );
          const counties = allCounties.filter(county => {{
            const id = String(county.id).padStart(5, "0");
            return !excludedStateIds.has(id.slice(0, 2));
          }});
          const projection = d3.geoAlbersUsa().fitSize([width, height], states);
          const path = d3.geoPath(projection);
          const projectedSeeds = seeds
            .map(seed => {{
              const point = projection([seed.lon, seed.lat]);
              return point ? {{ ...seed, x: point[0], y: point[1] }} : null;
            }})
            .filter(Boolean);
          const territoryGroups = new Map();
          const logoInfoByKey = new Map(
            seeds.map(seed => [
              seed.logoGroupKey,
              {{
                key: seed.logoGroupKey,
                name: seed.logoName,
                logo: seed.logo,
                radius: seed.logoRadius,
                size: seed.logoSize,
                fontSize: seed.logoFontSize,
                bubble: seed.logoBubble
              }}
            ])
          );
          for (const county of counties) {{
            const id = String(county.id).padStart(5, "0");
            const stateId = id.slice(0, 2);
            county.topoIndex = countyIndexById.get(id);
            const centroid = path.centroid(county);
            if (!Number.isFinite(centroid[0]) || !Number.isFinite(centroid[1])) continue;
            let bestSeed = null;
            let bestDistance = Infinity;
            if (stateId === "02" || stateId === "15") {{
              bestSeed = nearestGeoSeed(d3.geoCentroid(county), projectedSeeds);
            }} else {{
              for (const seed of projectedSeeds) {{
                const distance = (seed.x - centroid[0]) ** 2 + (seed.y - centroid[1]) ** 2;
                if (distance < bestDistance) {{
                  bestDistance = distance;
                  bestSeed = seed;
                }}
              }}
            }}
            county.properties = {{ ...(county.properties || {{}}), seed: bestSeed, color: bestSeed?.color || "#64748b" }};
            county.centroid = centroid;
            if (bestSeed) {{
              if (!territoryGroups.has(bestSeed.logoGroupKey)) territoryGroups.set(bestSeed.logoGroupKey, []);
              territoryGroups.get(bestSeed.logoGroupKey).push(county);
            }}
          }}

          svg.append("rect").attr("width", width).attr("height", height).attr("fill", "#e5e7eb");
          svg.append("g")
            .selectAll("path")
            .data(counties)
            .join("path")
            .attr("class", "county")
            .attr("d", path)
            .attr("fill", d => d.properties.color)
            .attr("fill-opacity", .95)
            .on("mouseover", (event, d) => {{
              tooltip.text(tooltipText(d)).style("display", "block");
              moveTooltip(event);
            }})
            .on("mousemove", moveTooltip)
            .on("mouseout", () => tooltip.style("display", "none"));

          svg.append("path")
            .datum(topojson.mesh(us, us.objects.states, (a, b) => a !== b))
            .attr("class", "state-border")
            .attr("d", path);

          svg.append("text")
            .attr("x", 760)
            .attr("y", 690)
            .attr("fill", "rgba(15,23,42,.58)")
            .attr("font-size", 22)
            .attr("font-weight", 900)
            .attr("letter-spacing", ".02em")
            .text("@BG.Analytics");

          for (const [logoKey, counties] of territoryGroups.entries()) {{
            const logoInfo = logoInfoByKey.get(logoKey);
            if (!logoInfo) continue;
            const largestMass = largestContiguousMass(counties, countyNeighbors, path);
            const center = centerForCounties(largestMass);
            if (center) drawLogo(logoInfo, center.x, center.y, counties.length, {{ placementKey: logoKey }});
          }}
        }}).catch(() => {{
          svg.append("rect").attr("width", width).attr("height", height).attr("fill", "#e5e7eb");
          svg.append("text")
            .attr("x", 28)
            .attr("y", 58)
            .attr("fill", "#0f172a")
            .attr("font-size", 18)
            .attr("font-weight", 800)
            .text("Unable to load U.S. county geometry for the conquest map.");
        }});
      </script>
    </body>
    </html>
    """


def rerun_app() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()


def checkbox_dropdown(label: str, options: list[str], key: str, all_label: str) -> list[str]:
    if not hasattr(st, "popover"):
        return st.multiselect(label, options, default=options)

    fingerprint = tuple(options)
    fingerprint_key = f"{key}_fingerprint"
    if st.session_state.get(fingerprint_key) != fingerprint:
        st.session_state[fingerprint_key] = fingerprint
        for idx, _ in enumerate(options):
            st.session_state[f"{key}_{idx}"] = True

    selected = [option for idx, option in enumerate(options) if st.session_state.get(f"{key}_{idx}", True)]
    if len(selected) == len(options):
        summary = all_label
    elif not selected:
        summary = "None selected"
    elif len(selected) == 1:
        summary = selected[0]
    else:
        summary = f"{len(selected)} selected"

    st.markdown(f'<div class="filter-label">{html.escape(label)}</div>', unsafe_allow_html=True)
    with st.popover(summary, use_container_width=True):
        left, right = st.columns(2)
        if left.button("Select all", key=f"{key}_all", use_container_width=True):
            for idx, _ in enumerate(options):
                st.session_state[f"{key}_{idx}"] = True
            rerun_app()
        if right.button("Clear", key=f"{key}_clear", use_container_width=True):
            for idx, _ in enumerate(options):
                st.session_state[f"{key}_{idx}"] = False
            rerun_app()
        for idx, option in enumerate(options):
            st.checkbox(option, key=f"{key}_{idx}")
    return [option for idx, option in enumerate(options) if st.session_state.get(f"{key}_{idx}", True)]


def award_logo_html(url: object, team: object) -> str:
    safe_team = html.escape(safe_text(team, "Team"))
    if url is not None and not pd.isna(url) and str(url).strip():
        return f'<div class="award-logo"><img src="{html.escape(str(url), quote=True)}" alt="{safe_team} logo" /></div>'
    return f'<div class="award-logo"><span>{html.escape(initials(safe_team))}</span></div>'


def award_card_html(
    number: int,
    award_name: str,
    winner: str,
    value: str = "",
    logo: object = None,
    matchup_logos: tuple[object, object, str, str] | None = None,
) -> str:
    if matchup_logos:
        away_logo, home_logo, away_team, home_team = matchup_logos
        logo_html = (
            '<div class="award-matchup-logos">'
            f"{award_logo_html(away_logo, away_team)}"
            f"{award_logo_html(home_logo, home_team)}"
            "</div>"
        )
    elif winner:
        logo_html = f'<div class="award-team-row">{award_logo_html(logo, winner)}</div>'
    else:
        logo_html = '<div class="award-meta">No eligible result</div>'

    meta = f'<div class="award-value">{html.escape(value)}</div>' if value else ""

    return (
        '<div class="award-card">'
        f'<div class="award-name">{html.escape(award_name)}</div>'
        f"{logo_html}"
        f"{meta}"
        "</div>"
    )


def weekly_team_rows(games: pd.DataFrame) -> pd.DataFrame:
    if games.empty:
        return pd.DataFrame()

    completed = games[games["completed"]].copy()
    if completed.empty:
        return pd.DataFrame()

    home_rows = pd.DataFrame(
        {
            "game_id": completed["game_id"],
            "team": completed["hometeam"],
            "team_key": completed["hometeam_key"],
            "opponent": completed["awayteam"],
            "logo": completed.get("home_logo"),
            "points_for": completed["homepoints"],
            "points_against": completed["awaypoints"],
            "opponent_classification": completed["awayclassification"],
            "win_probability": completed["home_win_probability"],
            "projected_mov": completed["predicted_home_margin"],
            "actual_mov": completed["homepoints"] - completed["awaypoints"],
            "won": completed["homepoints"] > completed["awaypoints"],
        }
    )
    away_rows = pd.DataFrame(
        {
            "game_id": completed["game_id"],
            "team": completed["awayteam"],
            "team_key": completed["awayteam_key"],
            "opponent": completed["hometeam"],
            "logo": completed.get("away_logo"),
            "points_for": completed["awaypoints"],
            "points_against": completed["homepoints"],
            "opponent_classification": completed["homeclassification"],
            "win_probability": 1 - completed["home_win_probability"],
            "projected_mov": -completed["predicted_home_margin"],
            "actual_mov": completed["awaypoints"] - completed["homepoints"],
            "won": completed["awaypoints"] > completed["homepoints"],
        }
    )
    rows = pd.concat([home_rows, away_rows], ignore_index=True)
    if "season" in completed.columns:
        season_values = completed["season"].dropna()
        if not season_values.empty:
            ppa_stats = get_team_game_ppa_stats(int(season_values.iloc[0]))
            if not ppa_stats.empty:
                rows = rows.merge(ppa_stats, on=["game_id", "team_key"], how="left")
    for col in ["points_for", "points_against", "win_probability", "projected_mov", "actual_mov"]:
        rows[col] = pd.to_numeric(rows[col], errors="coerce")
    for col in ["offense_ppa", "defense_ppa", "offense_ppa_percentile", "defense_ppa_percentile"]:
        if col not in rows.columns:
            rows[col] = np.nan
        rows[col] = pd.to_numeric(rows[col], errors="coerce")
    missing_projected_mov = rows["projected_mov"].isna() & rows["win_probability"].notna()
    rows.loc[missing_projected_mov, "projected_mov"] = implied_margin_from_probability(
        rows.loc[missing_projected_mov, "win_probability"]
    )
    rows["mov"] = rows["actual_mov"].abs()
    rows["vs_fcs"] = rows["opponent_classification"].astype(str).str.lower().eq("fcs")
    return rows


def first_team_award(rows: pd.DataFrame, mask: pd.Series, sort_columns: list[str], ascending: list[bool]) -> pd.Series | None:
    candidates = rows[mask].dropna(subset=sort_columns).copy()
    if candidates.empty:
        return None
    return candidates.sort_values(sort_columns, ascending=ascending).iloc[0]


def team_logo_lookup(schedule: pd.DataFrame) -> dict[str, object]:
    lookup: dict[str, object] = {}
    for side in ["home", "away"]:
        name_col = f"{side}team"
        logo_col = f"{side}_logo"
        if name_col not in schedule.columns or logo_col not in schedule.columns:
            continue
        for row in schedule[[name_col, logo_col]].dropna(subset=[name_col]).itertuples(index=False):
            key = team_key(getattr(row, name_col))
            if key and key not in lookup:
                lookup[key] = getattr(row, logo_col)
    return lookup


def render_awards(games: pd.DataFrame, bg_team: str, season_schedule: pd.DataFrame) -> None:
    rows = weekly_team_rows(games)
    cards = []

    biggest_winner = first_team_award(rows, rows["won"] & ~rows["vs_fcs"], ["actual_mov"], [False]) if not rows.empty else None
    cards.append(
        award_card_html(
            1,
            "Biggest Winner",
            safe_text(biggest_winner.get("team")) if biggest_winner is not None else "",
            f"W +{int(biggest_winner.actual_mov)} vs {safe_text(biggest_winner.opponent)}" if biggest_winner is not None else "",
            biggest_winner.get("logo") if biggest_winner is not None else None,
        )
    )

    biggest_upset = first_team_award(rows, rows["won"], ["win_probability"], [True]) if not rows.empty else None
    cards.append(
        award_card_html(
            2,
            "Biggest Upset",
            safe_text(biggest_upset.get("team")) if biggest_upset is not None else "",
            f"{biggest_upset.win_probability:.1%} win prob" if biggest_upset is not None and pd.notna(biggest_upset.win_probability) else "",
            biggest_upset.get("logo") if biggest_upset is not None else None,
        )
    )

    closest_win = first_team_award(rows, rows["won"], ["actual_mov", "win_probability"], [True, False]) if not rows.empty else None
    cards.append(
        award_card_html(
            3,
            "Closest Win",
            safe_text(closest_win.get("team")) if closest_win is not None else "",
            f"W +{int(closest_win.actual_mov)} vs {safe_text(closest_win.opponent)}" if closest_win is not None else "",
            closest_win.get("logo") if closest_win is not None else None,
        )
    )

    if not rows.empty:
        rows["award_win_probability"] = rows["win_probability"].fillna(0.5).clip(0.01, 0.99)
        rows["difficulty_multiplier"] = 0.75 + ((1 - rows["award_win_probability"]) * 0.5)
        rows["offense_score"] = rows["offense_ppa_percentile"] * rows["difficulty_multiplier"]
    best_offense = first_team_award(
        rows,
        ~rows["vs_fcs"],
        ["offense_score", "offense_ppa_percentile", "offense_ppa"],
        [False, False, False],
    ) if not rows.empty else None
    cards.append(
        award_card_html(
            4,
            "Best Offense",
            safe_text(best_offense.get("team")) if best_offense is not None else "",
            (
                f"Adj PPA {best_offense.offense_score:.1f} | "
                f"{best_offense.award_win_probability:.1%} win prob"
            ) if best_offense is not None else "",
            best_offense.get("logo") if best_offense is not None else None,
        )
    )

    if not rows.empty:
        rows["defense_score"] = rows["defense_ppa_percentile"] * rows["difficulty_multiplier"]
    best_defense = first_team_award(
        rows,
        ~rows["vs_fcs"],
        ["defense_score", "defense_ppa_percentile", "defense_ppa"],
        [False, False, True],
    ) if not rows.empty else None
    cards.append(
        award_card_html(
            5,
            "Best Defense",
            safe_text(best_defense.get("team")) if best_defense is not None else "",
            (
                f"Adj PPA {best_defense.defense_score:.1f} | "
                f"{best_defense.award_win_probability:.1%} win prob"
            ) if best_defense is not None else "",
            best_defense.get("logo") if best_defense is not None else None,
        )
    )

    if not rows.empty:
        rows["under_gap"] = rows["projected_mov"] - rows["actual_mov"]
    underwhelming = first_team_award(rows, rows["won"] & rows["under_gap"].gt(0), ["under_gap"], [False]) if not rows.empty else None
    cards.append(
        award_card_html(
            6,
            "Underwhelming",
            safe_text(underwhelming.get("team")) if underwhelming is not None else "",
            f"{underwhelming.under_gap:.1f} pts below projection" if underwhelming is not None else "",
            underwhelming.get("logo") if underwhelming is not None else None,
        )
    )

    if not rows.empty:
        rows["loss_margin"] = -rows["actual_mov"]
        rows["overperformance"] = rows["actual_mov"] - rows["projected_mov"]
        rows["almost_famous_score"] = (
            rows["overperformance"]
            + ((1 - rows["award_win_probability"]) * 20)
            - (rows["loss_margin"] * 0.75)
        )
        almost_famous_mask = (
            (~rows["won"])
            & rows["award_win_probability"].le(0.45)
            & rows["loss_margin"].le(14)
            & rows["overperformance"].gt(0)
        )
    almost_famous = first_team_award(
        rows,
        almost_famous_mask,
        ["almost_famous_score", "loss_margin", "win_probability"],
        [False, True, True],
    ) if not rows.empty else None
    cards.append(
        award_card_html(
            7,
            "Almost Did It",
            safe_text(almost_famous.get("team")) if almost_famous is not None else "",
            (
                f"Lost by {int(almost_famous.loss_margin)} | "
                f"+{almost_famous.overperformance:.1f} vs proj | "
                f"{almost_famous.win_probability:.1%} win prob"
            ) if almost_famous is not None and pd.notna(almost_famous.win_probability) else "",
            almost_famous.get("logo") if almost_famous is not None else None,
        )
    )

    excitement_col = first_existing(set(games.columns), EXCITEMENT_COLUMNS)
    exciting_game = None
    if excitement_col:
        exciting_candidates = games.copy()
        exciting_candidates["_excitement"] = pd.to_numeric(exciting_candidates[excitement_col], errors="coerce")
        exciting_candidates = exciting_candidates.dropna(subset=["_excitement"])
        if not exciting_candidates.empty:
            exciting_game = exciting_candidates.sort_values("_excitement", ascending=False).iloc[0]
    if exciting_game is not None:
        cards.append(
            award_card_html(
                8,
                "Most Exciting",
                safe_text(exciting_game.get("matchup")),
                f"Excitement index: {float(exciting_game['_excitement']):.2f}",
                matchup_logos=(
                    exciting_game.get("away_logo"),
                    exciting_game.get("home_logo"),
                    safe_text(exciting_game.get("awayteam")),
                    safe_text(exciting_game.get("hometeam")),
                ),
            )
        )
    else:
        cards.append(award_card_html(8, "Most Exciting", "", ""))

    bg_team = bg_team.strip()
    lookup = team_logo_lookup(season_schedule)
    cards.append(
        award_card_html(
            9,
            "BG.Analytics Team of the Week",
            bg_team,
            "",
            lookup.get(team_key(bg_team)),
        )
    )

    st.markdown(f'<div class="award-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


st.markdown(
    """
    <div class="schedule-shell">
      <h1 class="schedule-title">Schedule Analysis</h1>
    </div>
    """,
    unsafe_allow_html=True,
)

seasons = get_available_seasons()
if not seasons:
    st.info("No FBS vs FBS schedule data found.")
    st.stop()

season_col, week_col, conf_col = st.columns([1, 1, 2.4])
with season_col:
    selected_season = st.selectbox("Season", seasons, index=0)

schedule = attach_team_logos(attach_predictions(get_schedule_games(selected_season), get_prediction_data(selected_season)))
if schedule.empty:
    st.info(f"No FBS vs FBS games found for {selected_season}.")
    st.stop()

weeks = week_options(schedule)
with week_col:
    selected_week = st.selectbox("Week of Focus", weeks, index=0 if weeks else None)

conferences = sorted(
    pd.concat([schedule["homeconference"], schedule["awayconference"]]).dropna().astype(str).unique().tolist()
)
with conf_col:
    selected_conferences = checkbox_dropdown("Conferences", conferences, "schedule_focus_conferences", "All conferences")

left, right = st.columns([1.35, 1])
week_games = filtered_week_games(schedule, selected_week, selected_conferences)

with left:
    st.markdown('<div class="panel-title">Weekly Schedule</div>', unsafe_allow_html=True)
    st.dataframe(
        weekly_table(schedule, selected_week, selected_conferences),
        hide_index=True,
        use_container_width=True,
        height=455,
    )

with right:
    st.markdown('<div class="panel-title">Weekly Awards</div>', unsafe_allow_html=True)
    bg_team_of_week = st.text_input("BG.Analytics Team of the Week", value="", key=f"bg_team_of_week_{selected_season}")
    render_awards(week_games, bg_team_of_week, schedule)

st.markdown(
    """
    <div class="map-heading">
      <div>
        <div class="panel-title">Conquest Map</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

teams = team_locations(schedule)
scope_col, mode_control_col, map_control_col = st.columns([1.25, 1, 2.35])
with scope_col:
    map_scope = st.radio(
        "Map Scope",
        ["Power 4 + Notre Dame", P4_PROMOTIONS_MAP_SCOPE, "G6 + UConn", ALL_MAP_SCOPE],
        horizontal=False,
    )
with mode_control_col:
    map_mode = st.radio(
        "Territory Mode",
        ["Conference", "Team"],
        horizontal=False,
    )

p4_team_mask = teams["conference"].isin(POWER_FOUR_CONFERENCES) | teams["team_key"].isin(NOTRE_DAME_TEAM_KEYS)
g6_team_mask = teams["conference"].isin(G6_CONFERENCES) | teams["team_key"].isin(UCONN_TEAM_KEYS)

if map_scope in {"Power 4 + Notre Dame", P4_PROMOTIONS_MAP_SCOPE}:
    map_teams = teams[
        p4_team_mask
    ].copy()
elif map_scope == "G6 + UConn":
    map_teams = teams[
        g6_team_mask
    ].copy()
else:
    map_teams = teams.copy()

map_team_names = set(map_teams["team_key"])
if map_scope == P4_PROMOTIONS_MAP_SCOPE:
    map_schedule = schedule.copy()
    map_owner_teams = teams.copy()
else:
    map_schedule = schedule[
        schedule["hometeam_key"].isin(map_team_names)
        & schedule["awayteam_key"].isin(map_team_names)
    ].copy()
    map_owner_teams = map_teams

map_conferences = sorted(map_owner_teams["conference"].dropna().astype(str).unique().tolist())
conference_assets = {
    conference: DEFAULT_CONFERENCE_ASSETS.get(conference, {"color": "#64748b", "logo": ""})
    for conference in map_conferences
}

map_checkpoint_options = map_time_options(map_schedule)
with map_control_col:
    map_checkpoint = st.select_slider(
        "Conquest Map Week",
        options=map_checkpoint_options,
        value="Before Season",
        key=f"conquest_map_checkpoint_{selected_season}_{map_scope.replace(' ', '_')}",
    )

if map_teams.empty:
    st.info("No home-stadium coordinates are available for the selected conquest map scope.")
else:
    owners, ownership_histories = compute_land_ownership_history(
        map_schedule,
        map_teams,
        map_checkpoint,
        map_owner_teams,
    )
    map_render_key = f"{selected_season}-{map_scope}-{map_checkpoint}-{map_mode}"
    map_html = build_county_conquest_map(
        map_teams,
        owners,
        ownership_histories,
        conference_assets,
        f"{selected_season} | {map_scope} | {map_checkpoint} | {map_mode} territory map",
        map_scope,
        map_mode,
        map_render_key,
        map_owner_teams,
    )
    if map_html:
        components.html(map_html, height=790, scrolling=False)
    else:
        st.info("No conquest territories can be drawn with the current team locations.")

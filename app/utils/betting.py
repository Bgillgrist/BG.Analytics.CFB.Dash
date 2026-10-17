"""Betting page adapters; all mutations require an explicit action button."""
import os

import numpy as np
import pandas as pd
import streamlit as st

from cfb_betting.domain import MODELS, TIERS, last_pregame, recommendations, settle, utc
from cfb_betting.store import Config, read_data, read_seasons
from cfb_betting.service import run_analysis
from cfb_betting import store
from cfb_betting.domain import normalize_quotes
from cfb_betting.features import build_features, prepare_games, quote_inputs
from cfb_betting.models import MODEL_VERSION, score_quotes
from cfb_betting.service import upcoming


class BettingScoringError(RuntimeError):
    """Safe scoring diagnostics for the page, without connection details."""


def score_current_quotes(bundle, targets, quotes):
    try:
        return score_quotes(bundle, targets, quotes)
    except Exception as error:
        if "could not be loaded" in str(error) and "xgboost" in str(error).lower():
            raise BettingScoringError(
                "Current odds loaded, but the model runtime could not start. "
                "Install the OpenMP runtime (libomp on macOS; libgomp1 on Linux), then restart the dashboard."
            ) from error
        raise BettingScoringError(
            f"Current odds loaded, but saved-model scoring failed ({type(error).__name__})."
        ) from error


def credentials():
    from utils.db import _get_db_url
    key = os.getenv("CFBD_API_KEY")
    try:
        key = st.secrets.get("CFBD_API_KEY", key)
    except Exception:
        pass
    return Config(_get_db_url(), key)


def can_refresh():
    return bool(credentials().api_key)


@st.cache_data(ttl=60, show_spinner=False)
def load_seasons():
    return read_seasons(credentials())


@st.cache_data(ttl=60, show_spinner=False)
def load_data(season, source="live"):
    return read_data(credentials(), int(season), source)


@st.cache_data(ttl=60, show_spinner=False)
def load_current_data(season):
    """Score table odds with saved models, without API calls or snapshot writes."""
    config = credentials()
    data = read_data(config, int(season))
    data.update(current=True, candidates=pd.DataFrame(), quote_issues=[], model_message=None)
    if data["runs"].empty or not data["runs"].status.eq("success").any():
        data["model_message"] = "Run analysis once to train models for this season. Current odds come from the betting odds table."
        return data
    with store.connect(config) as conn:
        conn.read_only = True
        saved = store.latest_model(conn, int(season))
        if saved["artifact"]["version"] != MODEL_VERSION:
            data["model_message"] = "Run analysis to update the saved models for this season."
            return data
        as_of = utc()
        games, ratings, stats = store.load_inputs(conn, int(season))
        eligible = upcoming(prepare_games(games), int(season), as_of)
        if eligible.empty:
            return data
        quotes = normalize_quotes(store.load_historical_quotes(conn, eligible.game_id.tolist()), eligible.game_id)
    data["quote_issues"] = quotes.attrs.get("quote_issues", [])
    frame = build_features(games, ratings, stats, as_of, target_ids=eligible.game_id)
    targets = quote_inputs(upcoming(frame, int(season), as_of), quotes)
    candidates = score_current_quotes(saved["artifact"], targets, quotes)
    if not candidates.empty:
        metadata = targets[["game_id", "kickoff", "week", "season_type", "home_team", "away_team"]]
        candidates = candidates.merge(metadata, on="game_id", validate="many_to_one")
        candidates["table_read_at"] = as_of
    data["candidates"] = candidates
    data["metrics"] = saved["metrics"]
    return data


def execute(season, retrain, progress):
    result = run_analysis(credentials(), int(season), retrain=retrain, progress=progress)
    load_data.clear()
    load_current_data.clear()
    return result


def current_candidates(data, now=None):
    games = data["games"].copy()
    if games.empty:
        return pd.DataFrame()
    games["kickoff"] = pd.to_datetime(games.kickoff, utc=True, errors="coerce")
    games = games.loc[games.kickoff.gt(utc(now)) & ~games.completed.fillna(False).eq(True) & ~games.cancelled.fillna(False).eq(True)]
    if data.get("current"):
        candidates = data["candidates"].copy()
        if not candidates.empty:
            candidates = candidates.loc[candidates.game_id.isin(games.game_id)].copy()
    else:
        candidates = last_pregame(data["scopes"], data["candidates"], games, best_only=False)
    if candidates.empty:
        return candidates
    grouped = candidates.groupby(["game_id", "market", "side", "provider"]).probability
    candidates["model_range_pp"] = grouped.transform("max").sub(grouped.transform("min")) * 100
    candidates["models_available"] = grouped.transform("count")
    if not data.get("current"):
        candidates["quote_age_hours"] = (utc(now) - pd.to_datetime(candidates.as_of, utc=True)).dt.total_seconds() / 3600
    return candidates


def history(data, source="live"):
    return settle(last_pregame(data["scopes"], data["candidates"], data["games"], source))


def filter_rows(frame, *, models=None, markets=None, providers=None, teams=None, conferences=None, weeks=None, tiers=None):
    result = frame.copy()
    for column, values in [("model", models), ("market", markets), ("provider", providers),
                           ("conference", conferences), ("classification", tiers), ("week", weeks)]:
        if values and column in result:
            result = result.loc[result[column].isin(values)]
    if teams and not result.empty:
        result = result.loc[result.team.isin(teams) | result.opponent.isin(teams)]
    return result


def display_frame(frame):
    """Keep numeric probabilities sortable; formatting is a page concern."""
    columns = ["classification", "team", "opponent", "market", "provider", "handicap", "american",
               "probability", "baseline", "edge_pp", "push_probability", "expected_return", "model_spread",
               "model_range_pp", "models_available", "kickoff", "as_of", "quote_age_hours", "table_read_at",
               "model", "model_version", "result", "homepoints", "awaypoints", "units", "snapshot_age_hours"]
    shown = frame[[c for c in columns if c in frame]].copy()
    for column in ["probability", "baseline", "push_probability", "expected_return"]:
        if column in shown:
            shown[column] = pd.to_numeric(shown[column], errors="coerce") * 100
    if "model" in shown:
        shown["model"] = shown.model.map(MODELS).fillna(shown.model)
    for column in ["kickoff", "as_of", "table_read_at"]:
        if column in shown:
            shown[column] = pd.to_datetime(shown[column], utc=True).dt.tz_convert("America/New_York")
    return shown


def validation_frame(metrics):
    return pd.DataFrame([dict(model=MODELS.get(name, name),
        training_games=value["training_games"], evaluation_games=value["evaluation_games"],
        seasons=", ".join(map(str,value["evaluation_seasons"])), brier=value["brier"],
        log_loss=value["log_loss"], margin_mae=value["margin_mae"], cover_brier=value.get("cover_brier"))
        for name,value in metrics.items()])


def table_config():
    return {
        "classification": "Edge classification", "team": "Pick", "opponent": "Opponent",
        "market": "Market", "provider": "Sportsbook",
        "handicap": st.column_config.NumberColumn("Spread", format="%+.1f"),
        "american": st.column_config.NumberColumn("Moneyline", format="%+.0f"),
        "probability": st.column_config.NumberColumn("Model probability", format="%.1f%%",
            help="Spread probability excludes pushes. Moneyline probability is the chance to win."),
        "baseline": st.column_config.NumberColumn("Comparison baseline", format="%.1f%%"),
        "edge_pp": st.column_config.NumberColumn("Edge (pp)", format="%+.2f"),
        "push_probability": st.column_config.NumberColumn("Push probability", format="%.1f%%"),
        "expected_return": st.column_config.NumberColumn("ML expected return", format="%+.1f%%"),
        "model_spread": st.column_config.NumberColumn("Model spread", format="%+.1f"),
        "model_range_pp": st.column_config.NumberColumn("Model range (pp)", format="%.1f"),
        "models_available": "Models compared", "kickoff": "Kickoff (Eastern)",
        "as_of": "Odds retrieved (Eastern)", "quote_age_hours": st.column_config.NumberColumn("Quote age (hours)", format="%.1f"),
        "table_read_at": "Table read (Eastern)",
        "model": "Model", "model_version": "Model version", "result": "Result",
        "homepoints": "Home score", "awaypoints": "Away score",
        "units": st.column_config.NumberColumn("ML paper units", format="%+.2f"),
        "snapshot_age_hours": st.column_config.NumberColumn("Hours before kickoff", format="%.1f"),
    }

"""Snapshot provenance and diagnostic calculations without database access."""

from io import BytesIO
from pathlib import Path
import sys
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils import model_data
from utils.predictive_performance import (
    add_errors, breakdown, calibration, csv_bytes, filter_games, metrics, select_forecasts, team_rows, trends, zip_csvs,
)


def game(identifier="001", **changes):
    return dict(dict(game_id=identifier, season=2025, season_type="regular", week=1,
        kickoff="2025-09-06T16:00:00Z", starttimetbd=False, completed=True, cancelled=False,
        home_team="Alpha", away_team="Bravo", home_conference="SEC", away_conference="ACC",
        homepoints=30., awaypoints=20., neutralsite=False), **changes)


def forecast(run_id="first", **changes):
    return dict(dict(game_id="001", run_id=run_id, model_version="v1", status="success", run_type="nightly",
        run_date="2025-09-01", run_created_at="2025-09-01T08:00Z", prediction_created_at="2025-09-01T08:10Z",
        forecast_completed_at="2025-09-01T08:20Z", home_win_probability=.7, predicted_home_margin=8., predicted_total=48.), **changes)


def test_latest_saved_snapshot_selected_before_version_filter_and_corrected_results():
    games = pd.DataFrame([game(homepoints=35.)])
    forecasts = pd.DataFrame([forecast(), forecast("new", model_version="v2", forecast_completed_at="2025-09-05T12:00Z"),
        forecast("late", forecast_completed_at="2025-09-06T17:00Z"), forecast("failed", status="failed"),
        forecast("duplicate", status="duplicate"), forecast("backfill", run_type="backfill")])
    audit = select_forecasts(games, forecasts)
    assert audit.iloc[0].run_id == "new"
    assert audit.iloc[0].actual_home_margin == 15
    assert audit.iloc[0].margin_error == -7
    assert filter_games(audit, versions=["v1"]).empty
    assert len(filter_games(audit, teams=["Bravo"], conferences=["ACC"])) == 1


def test_forward_and_research_records_never_mix_and_honor_horizons():
    rows = pd.DataFrame([forecast("nightly", forecast_completed_at="2025-09-06T10:00Z"),
                         forecast("manual", run_type="manual", forecast_completed_at="2025-09-04T08:00Z"),
                         forecast("research", run_type="backfill", run_date="2025-09-05",
                                  forecast_completed_at="2026-01-01T12:00Z")])
    games = pd.DataFrame([game()])
    assert select_forecasts(games, rows).iloc[0].run_id == "nightly"
    assert select_forecasts(games, rows, horizon_hours=24).iloc[0].run_id == "manual"
    assert pd.isna(select_forecasts(games, rows, horizon_hours=168).iloc[0].run_id)
    assert select_forecasts(games, rows, "Historical research").iloc[0].run_id == "research"
    assert pd.isna(select_forecasts(games, rows, "Historical research", 168).iloc[0].run_id)


@pytest.mark.parametrize("field", ["forecast_completed_at", "run_created_at", "prediction_created_at"])
def test_post_cutoff_or_missing_timestamp_cannot_establish_pregame_record(field):
    for value in ["2025-09-06T16:00Z", "2025-09-07T12:00Z", None]:
        audit = select_forecasts(pd.DataFrame([game()]), pd.DataFrame([forecast(**{field: value})]))
        assert audit.iloc[0].evaluation_status == "No eligible forecast"


def test_pending_invalid_cancelled_and_unknown_kickoff_are_counted_without_fake_losses():
    games = pd.DataFrame([game(), game("002", starttimetbd=True), game("003", kickoff=None),
        game("004", completed=False, homepoints=None, awaypoints=None), game("005", homepoints=-1),
        game("006", homepoints=20), game("007", cancelled=True, completed=False)])
    audit = select_forecasts(games, pd.DataFrame())
    assert list(audit.evaluation_status) == ["No eligible forecast", "Unknown kickoff", "Unknown kickoff", "Awaiting result",
                                           "Invalid final score", "Invalid final score", "Cancelled"]
    assert metrics(audit).games.sum() == 0
    assert metrics(audit).value.isna().all()
    assert calibration(audit).empty


def test_independent_metric_denominators_probability_boundaries_and_bias():
    frame = pd.DataFrame([
        dict(home_win_probability=1., actual_home_win=1., predicted_home_margin=9., actual_home_margin=10., predicted_total=50., actual_total=45.),
        dict(home_win_probability=0., actual_home_win=0., predicted_home_margin=None, actual_home_margin=-5., predicted_total=40., actual_total=45.),
        dict(home_win_probability=.5, actual_home_win=1., predicted_home_margin=12., actual_home_margin=10.),
        dict(home_win_probability=1.2, actual_home_win=0., predicted_home_margin=np.inf, actual_home_margin=-4.),
    ])
    scores = metrics(frame).set_index("metric")
    assert scores.loc["winner_accuracy", "value"] == 1
    assert scores.loc["winner_accuracy", "games"] == 2
    assert scores.loc["brier_score", "value"] == pytest.approx(.25/3)
    assert scores.loc["brier_score", "games"] == 3
    assert scores.loc["margin_mae", "games"] == 2
    assert scores.loc["margin_mae", "value"] == 1.5
    assert scores.loc["margin_bias", "value"] == .5
    assert scores.loc["total_rmse", "value"] == 5
    assert scores.loc["total_bias", "value"] == 0
    assert np.isfinite(scores.loc["log_loss", "value"])
    table = calibration(frame)
    assert table.games.sum() == 3
    assert table.iloc[-1].bin_upper == 1
    assert (table.rate_lower <= table.observed_win_rate).all()
    assert (table.rate_upper >= table.observed_win_rate).all()
    assert pd.isna(metrics(frame.iloc[[0]]).set_index("metric").loc["roc_auc", "value"])


def test_breakdowns_and_cumulative_trends_use_game_weights_and_chronology():
    games = pd.DataFrame([game(), game("002", week=2, kickoff="2025-09-13T16:00Z", homepoints=10, awaypoints=20)])
    audit = select_forecasts(games, pd.DataFrame([forecast(), forecast(game_id="002", home_win_probability=.2)]))
    weekly, cumulative = trends(audit)
    assert weekly.games.tolist() == [1, 1]
    assert cumulative.games.tolist() == [1, 2]
    assert cumulative.iloc[-1].brier_score == pytest.approx((.09+.04)/2)
    by_team = breakdown(team_rows(audit), ["team"])
    assert set(by_team.games) == {2}
    assert by_team.games.sum() == 4  # participants, not league games


def test_csv_zip_roundtrip_preserves_text_ids_probabilities_and_utc_timestamps():
    audit = select_forecasts(pd.DataFrame([game()]), pd.DataFrame([forecast()]))
    parsed = pd.read_csv(BytesIO(csv_bytes(audit)), dtype={"game_id": str})
    assert parsed.iloc[0].game_id == "001"
    assert parsed.iloc[0].home_win_probability == .7
    assert parsed.iloc[0].kickoff.endswith("+00:00")
    with ZipFile(BytesIO(zip_csvs({"games": audit, "metrics": metrics(audit)}))) as archive:
        assert set(archive.namelist()) == {"games.csv", "metrics.csv"}


def test_metric_discovery_excludes_identifiers_and_unsafe_names():
    metadata = pd.DataFrame([dict(column_name=name, data_type=kind) for name, kind in [
        ("season", "integer"), ("opponent_id", "bigint"), ("offense_ppa", "double precision"),
        ("offense_new_metric", "numeric"), ("team", "text"), ('bad"name', "integer")]])
    assert model_data.discover_metrics(metadata) == ["offense_new_metric", "offense_ppa"]


def test_performance_query_negates_spread_and_uses_current_schedule_scores(monkeypatch):
    from utils import db
    calls = []
    def read(sql, params=None):
        calls.append(sql)
        return pd.DataFrame([game()]) if "g.homepoints" in sql else pd.DataFrame()
    monkeypatch.setattr(db, "read_df", read)
    games, _ = model_data.load_performance([2025])
    assert games.iloc[0].homepoints == 30
    assert "-p.homespread AS predicted_home_margin" in calls[-1]
    assert "p.homepoints" not in calls[-1]


def test_duplicate_game_ids_are_rejected():
    with pytest.raises(ValueError, match="Duplicate game"):
        select_forecasts(pd.DataFrame([game(), game()]), pd.DataFrame())

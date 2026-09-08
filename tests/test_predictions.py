"""Behavioral coverage for snapshot comparisons and league projection tables."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from utils.predictions import (
    WIN_BUCKETS, add_changes, comparison_snapshot, conference_summary, filter_teams,
    model_changed, prepare_snapshot, select_snapshot, sort_teams,
)


def run(identifier, run_date, completed=None, **changes):
    row = dict(season_prediction_run_id=identifier, season=2026, run_date=run_date,
               completed_at=completed or f"{run_date}T12:00:00Z", created_at=f"{run_date}T10:00:00Z",
               status="success", run_type="nightly", model_version="v1")
    row.update(changes)
    return row


def team(name, conference="SEC", **changes):
    row = dict(team=name, season=2026, classification="fbs", conference=conference,
               projected_wins=8.5, playoff_prob=.25, conference_champion_prob=.2,
               conference_championship_game_prob=.4, national_champion_prob=.03)
    row.update({column: 0.0 for column in WIN_BUCKETS})
    row[WIN_BUCKETS[8]] = .5
    row[WIN_BUCKETS[13]] = .5
    row.update(changes)
    return row


def test_latest_snapshot_ignores_failed_running_duplicates_and_other_run_types():
    runs = pd.DataFrame([
        run("a", "2026-09-06"), run("b", "2026-09-07", run_type="manual"),
        run("c", "2026-09-08", status="failed"), run("d", "2026-09-08", status="running"),
        run("e", "2026-09-08", status="duplicate"), run("f", "2026-09-08", run_type="backfill"),
        run("g", "2026-09-08", season=2025),
    ])
    assert select_snapshot(runs, 2026)["season_prediction_run_id"] == "b"
    assert select_snapshot(runs, 2024) is None
    assert select_snapshot(pd.DataFrame(), 2026) is None


def test_snapshot_order_uses_completion_creation_id_and_nulls_last():
    runs = pd.DataFrame([
        run("a", "2026-09-07"), run("b", "2026-09-07"),
        run("c", "2026-09-08", completed_at=None),
    ])
    assert select_snapshot(runs, 2026)["season_prediction_run_id"] == "b"
    runs.loc[0, "created_at"] = "2026-09-07T11:00:00Z"
    assert select_snapshot(runs, 2026)["season_prediction_run_id"] == "a"


def test_comparison_excludes_same_day_and_uses_earlier_available_date():
    runs = pd.DataFrame([
        run("old", "2026-08-29"), run("prior", "2026-09-05"),
        run("morning", "2026-09-07"), run("latest", "2026-09-07", "2026-09-07T20:00:00Z"),
    ])
    current = select_snapshot(runs, 2026)
    assert comparison_snapshot(runs, current, date(2026, 9, 6))["season_prediction_run_id"] == "prior"
    assert comparison_snapshot(runs, current, date(2026, 8, 31))["season_prediction_run_id"] == "old"
    assert comparison_snapshot(runs, current, date(2026, 8, 8)) is None
    assert comparison_snapshot(runs, current, date(2026, 9, 5))["season_prediction_run_id"] == "prior"
    assert comparison_snapshot(runs, current, date(2026, 9, 7)) is None
    assert comparison_snapshot(runs, current, date(2026, 9, 8)) is None
    assert comparison_snapshot(runs, current, None) is None
    assert select_snapshot(runs, 2026, date(2026, 9, 5))["season_prediction_run_id"] == "prior"


def test_changes_are_percentage_points_and_preserve_missing_teams_and_metrics():
    current = prepare_snapshot(pd.DataFrame([team("A", playoff_prob=.6, projected_wins=9.5), team("New")]))
    previous = prepare_snapshot(pd.DataFrame([team("A", playoff_prob=.4, national_champion_prob=None), team("Gone")]))
    compared = add_changes(current, previous).set_index("team")
    assert compared.loc["A", "playoff_prob_change"] == pytest.approx(20)
    assert compared.loc["A", "projected_wins_change"] == 1
    assert pd.isna(compared.loc["A", "national_champion_prob_change"])
    assert pd.isna(compared.loc["New", "playoff_prob_change"])
    assert "Gone" not in compared.index
    assert add_changes(current, None)["playoff_prob_change"].isna().all()


def test_history_matches_season_as_well_as_team():
    current = prepare_snapshot(pd.DataFrame([team("A")]))
    previous = prepare_snapshot(pd.DataFrame([team("A", season=2025)]))
    assert add_changes(current, previous)["playoff_prob_change"].isna().all()


def test_model_version_change_is_identified():
    current = pd.Series(run("a", "2026-09-07"))
    previous = pd.Series(run("b", "2026-09-06", model_version="v0"))
    assert model_changed(current, previous)
    assert not model_changed(current, current)
    assert not model_changed(current, None)


def test_thresholds_include_capped_bucket_and_require_complete_data():
    frame = prepare_snapshot(pd.DataFrame([team("A"), team("B", probability_12_wins=None)]))
    assert frame.loc[0, "probability_8_plus_wins"] == 1
    for threshold in (10, 11, 12):
        assert frame.loc[0, f"probability_{threshold}_plus_wins"] == .5
        assert pd.isna(frame.loc[1, f"probability_{threshold}_plus_wins"])


def test_conference_summary_aggregates_complete_members_and_independents():
    frame = prepare_snapshot(pd.DataFrame([
        team("A", playoff_prob=.8, conference_champion_prob=.7),
        team("B", playoff_prob=.5, conference_champion_prob=.3),
        team("Notre Dame", "FBS Independents", playoff_prob=.9),
    ]))
    summary = conference_summary(frame).set_index("conference")
    assert summary.index[0] == "SEC"
    assert summary.loc["SEC", "expected_cfp"] == pytest.approx(1.3)
    assert summary.loc["SEC", "lead_pp"] == pytest.approx(40)
    assert summary.loc["SEC", "favorite"] == "A"
    assert summary.loc["SEC", "runner_up"] == "B"
    assert summary.loc["FBS Independents", "favorite"] == "Not applicable"
    assert pd.isna(summary.loc["FBS Independents", "favorite_prob"])
    assert pd.isna(frame.iloc[2]["conference_championship_game_prob"])


def test_missing_probability_does_not_silently_undercount_conference():
    frame = prepare_snapshot(pd.DataFrame([team("A"), team("B", playoff_prob=None)]))
    assert pd.isna(conference_summary(frame).iloc[0]["expected_cfp"])


def test_numeric_sort_ties_and_nulls():
    frame = prepare_snapshot(pd.DataFrame([
        team("B", projected_wins=10), team("A", projected_wins=10),
        team("C", projected_wins=9), team("D", playoff_prob=None),
    ]))
    assert sort_teams(frame)["team"].tolist() == ["A", "B", "C", "D"]
    assert sort_teams(frame, "projected_wins", True)["team"].tolist() == ["D", "C", "A", "B"]
    assert sort_teams(frame, "playoff_prob", True).iloc[-1]["team"] == "D"


def test_filters_combine_without_mutating_source_and_handle_empty_results():
    frame = prepare_snapshot(pd.DataFrame([team("A"), team("B", "ACC", playoff_prob=.7), team("C", "ACC")]))
    filtered = filter_teams(frame, ["ACC"], metric="playoff_prob", minimum=.5, maximum=.9)
    assert filtered["team"].tolist() == ["B"]
    assert len(frame) == 3
    assert filter_teams(frame, teams=["A"], metric="playoff_prob", minimum=.9).empty


def test_fbs_only_missing_metrics_and_unknown_conference():
    frame = prepare_snapshot(pd.DataFrame([team("A", None), team("B", classification="fcs")]))
    assert frame["team"].tolist() == ["A"]
    assert frame.iloc[0]["conference"] == "Unknown"
    assert frame["projected_ap_ranking"].isna().all()


def test_empty_snapshot_and_conference_summary():
    frame = prepare_snapshot(pd.DataFrame(columns=["team", "season", "classification", "conference"]))
    assert frame.empty
    assert conference_summary(frame).empty


def test_zero_changes_remain_zero_instead_of_missing():
    frame = prepare_snapshot(pd.DataFrame([team("A")]))
    changes = add_changes(frame, frame)
    assert changes.loc[0, "playoff_prob_change"] == 0
    assert changes.loc[0, "projected_wins_change"] == 0

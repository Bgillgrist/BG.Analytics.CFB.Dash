"""Weekly scoring, eligibility, historical snapshot, and batching contracts."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils.weekly_performances import (
    attach_opponent_ratings, attach_pregame_runs, best_ascending, effective_mode,
    filter_performances, load_week, prepare_games, rank_performances,
    sort_performances, standardize,
)


def game(team="A", **changes):
    row = dict(game_id=1, season=2026, week=1, season_type="regular", team=team, opponent="Incorrect source opponent",
               schedule_season=2026, schedule_week=1, schedule_season_type="regular",
               completed=True, startdate="2026-09-05T16:00:00Z", starttimetbd=False, neutralsite=False,
               hometeam="A", awayteam="B", homeclassification="fbs", awayclassification="fbs",
               homeconference="SEC", awayconference="ACC", homepoints=31, awaypoints=17,
               offense_plays=60, defense_plays=55, offense_ppa=.3, defense_ppa=.1,
               offense_passingplays_ppa=.4, offense_rushingplays_ppa=.2,
               defense_passingplays_ppa=.15, defense_rushingplays_ppa=.05)
    row.update(changes)
    return row


def run(identifier="before", **changes):
    row = dict(rating_run_id=identifier, season=2026, status="success", run_type="nightly",
               completed_at="2026-09-05T12:00:00Z", created_at="2026-09-05T11:00:00Z")
    row.update(changes)
    return row


def ratings(values=(-10, 10), identifier="before"):
    return pd.DataFrame([dict(rating_run_id=identifier, team=name, classification="fbs", power_rating=value)
                         for name, value in zip(["A", "B", "C", "D"], values)])


def ready(rows=None, rating_values=(-10, 10)):
    frame = prepare_games(pd.DataFrame(rows if rows is not None else [game(), game("B")]))
    return attach_opponent_ratings(attach_pregame_runs(frame, pd.DataFrame([run()])), ratings(rating_values))


def test_identity_results_and_venue_are_resolved_from_schedule():
    frame = prepare_games(pd.DataFrame([game(), game("B")]))
    assert frame.opponent.tolist() == ["B", "A"]
    assert frame.conference.tolist() == ["SEC", "ACC"]
    assert frame.venue.tolist() == ["Home", "Away"]
    assert frame.result.tolist() == ["W", "L"]
    assert frame.final_score.tolist() == ["31–17", "17–31"]
    neutral = prepare_games(pd.DataFrame([game(neutralsite=True)]))
    assert neutral.iloc[0].venue == "Neutral"


@pytest.mark.parametrize("changes", [
    {"completed": False}, {"awayclassification": "fcs"}, {"homeclassification": "fcs"},
    {"team": "Unknown"}, {"game_id": None}, {"awayteam": None}, {"awayteam": "A"},
    {"season": 2025}, {"offense_plays": 0, "defense_plays": 0},
])
def test_ineligible_rows_are_excluded(changes):
    assert prepare_games(pd.DataFrame([game(**changes)])).empty


def test_duplicate_team_game_is_rejected_but_multiple_games_are_preserved():
    with pytest.raises(ValueError, match="Duplicate team-game"):
        prepare_games(pd.DataFrame([game(), game()]))
    frame = prepare_games(pd.DataFrame([game(), game(game_id=2)]))
    assert len(frame) == 2
    assert frame.team.tolist() == ["A", "A"]


def test_schedule_phase_and_week_override_stats_labels_and_missing_score_stays_missing():
    frame = prepare_games(pd.DataFrame([game(schedule_season_type="postseason", schedule_week=2, homepoints=None)]))
    assert frame.iloc[0].season_type == "postseason"
    assert frame.iloc[0].week == 2
    assert pd.isna(frame.iloc[0].result)
    assert pd.isna(frame.iloc[0].final_score)


def test_snapshot_cutoff_excludes_same_time_future_failed_duplicate_and_other_season():
    runs = pd.DataFrame([
        run(), run("same", completed_at="2026-09-05T16:00:00Z"),
        run("after", completed_at="2026-09-05T17:00:00Z"),
        run("failed", completed_at="2026-09-05T15:00:00Z", status="failed"),
        run("duplicate", completed_at="2026-09-05T15:00:00Z", status="duplicate"),
        run("other", season=2025), run("backfill", run_type="backfill"),
        run("missing", completed_at=None),
    ])
    selected = attach_pregame_runs(prepare_games(pd.DataFrame([game()])), runs)
    assert selected.iloc[0].rating_run_id == "before"


def test_snapshot_tiebreaks_use_creation_then_id():
    runs = pd.DataFrame([run("a"), run("b"), run("z", created_at="2026-09-05T10:00:00Z")])
    selected = attach_pregame_runs(prepare_games(pd.DataFrame([game()])), runs)
    assert selected.iloc[0].rating_run_id == "b"


@pytest.mark.parametrize("changes", [{"startdate": None}, {"starttimetbd": True}, {"startdate": None, "starttimetbd": None}])
def test_unreliable_kickoff_preserves_raw_data_without_rating(changes):
    frame = ready([game(**changes), game("B")])
    assert pd.isna(frame.iloc[0].rating_run_id)
    assert pd.isna(frame.iloc[0].opponent_strength_z)
    assert frame.iloc[0].adjustment_note == "Reliable kickoff time unavailable"
    assert pd.notna(rank_performances(frame, "offense", "Overall").iloc[0].raw_rank)


def test_nullable_tbd_flag_from_existing_game_loader_does_not_discard_known_kickoff():
    frame = ready([game(starttimetbd=None), game("B")])
    assert frame.iloc[0].reliable_kickoff
    assert frame.iloc[0].rating_run_id == "before"
    assert frame.iloc[0].opponent_bg_rating == 10


def test_each_game_uses_its_own_pregame_snapshot():
    frame = prepare_games(pd.DataFrame([game(), game(game_id=2, startdate="2026-09-06T16:00:00Z")]))
    selected = attach_pregame_runs(frame, pd.DataFrame([run(), run("new", completed_at="2026-09-06T12:00:00Z")]))
    assert selected.rating_run_id.tolist() == ["before", "new"]


def test_standardization_uses_population_variance_and_preserves_missing_values():
    assert standardize(pd.Series([1, 3])).tolist() == [-1, 1]
    assert standardize(pd.Series([2, 2])).tolist() == [0, 0]
    assert standardize(pd.Series([2, np.nan, np.inf])).isna().all()
    assert standardize(pd.Series(dtype=float)).empty


def test_opponent_component_uses_full_fbs_snapshot_and_only_unblended_power():
    frame = attach_pregame_runs(prepare_games(pd.DataFrame([game()])), pd.DataFrame([run()]))
    cohort = ratings((-10, 10, 30))
    cohort["team_rating"] = 999
    cohort["blended_rating"] = -999
    cohort = pd.concat([cohort, pd.DataFrame([dict(rating_run_id="before", team="FCS", classification="fcs", power_rating=99999)])])
    result = attach_opponent_ratings(frame, cohort)
    assert result.iloc[0].opponent_bg_rating == 10
    assert result.iloc[0].opponent_strength_z == 0  # B is average among A, B, C.


def test_insufficient_rating_cohort_missing_opponent_and_no_history():
    frame = attach_pregame_runs(prepare_games(pd.DataFrame([game(), game("B")])), pd.DataFrame([run()]))
    result = attach_opponent_ratings(frame, ratings((-10,)))
    assert result.opponent_strength_z.isna().all()
    no_history = attach_opponent_ratings(attach_pregame_runs(prepare_games(pd.DataFrame([game()])), pd.DataFrame()), pd.DataFrame())
    assert no_history.iloc[0].adjustment_note == "No saved pregame BG rating"


@pytest.mark.parametrize("side,preset,field", [
    ("offense", "Overall", "offense_ppa"), ("offense", "Passing", "offense_passingplays_ppa"),
    ("offense", "Rushing", "offense_rushingplays_ppa"), ("defense", "Overall", "defense_ppa"),
    ("defense", "Passing", "defense_passingplays_ppa"), ("defense", "Rushing", "defense_rushingplays_ppa"),
])
def test_scoring_direction_and_exact_quarter_opponent_weight(side, preset, field):
    values = [3, 1] if side == "offense" else [1, 3]
    result = rank_performances(ready([game(**{field: values[0]}), game("B", **{field: values[1]})]), side, preset)
    assert result.raw_rank.tolist() == [1, 2]
    assert result.performance_z.tolist() == pytest.approx([1, -1])
    assert result.adjusted_score.tolist() == pytest.approx([1.25, -1.25])
    assert result.adjusted_rank.tolist() == [1, 2]


def test_zero_variance_ties_and_deterministic_sort():
    result = rank_performances(ready([game("B"), game()], rating_values=(10, 10)), "offense", "Overall")
    assert result.adjusted_score.tolist() == [0, 0]
    assert result.adjusted_rank.tolist() == [1, 1]
    assert result.raw_rank.tolist() == [1, 1]
    assert sort_performances(result, "adjusted_score", False).team.tolist() == ["A", "B"]


def test_missing_ppa_and_small_samples_do_not_create_adjusted_scores():
    result = rank_performances(ready([game(offense_ppa=None), game("B")]), "offense", "Overall")
    assert result.adjusted_score.isna().all()
    assert pd.isna(result.iloc[0].raw_rank)
    assert result.iloc[1].raw_rank == 1
    assert effective_mode(result, "BG-adjusted") == "Raw PPA"
    assert "Fewer than two" in result.iloc[1].adjustment_note


def test_side_play_counts_are_independent():
    frame = ready([game(offense_plays=0), game("B")])
    assert len(rank_performances(frame, "offense", "Overall")) == 1
    assert len(rank_performances(frame, "defense", "Overall")) == 2


def test_filters_preserve_full_week_scores_and_ranks_and_missing_sorts_last():
    result = rank_performances(ready([game(offense_ppa=.5), game("B", offense_ppa=.1)]), "offense", "Overall")
    subset = filter_performances(result, ["ACC"], ["B"])
    assert subset.iloc[0].raw_rank == 2
    assert subset.iloc[0].adjusted_score == result.iloc[1].adjusted_score
    assert filter_performances(result, ["Missing"]).empty
    result.loc[0, "adjusted_score"] = np.nan
    assert sort_performances(result, "adjusted_score", False).iloc[-1].team == "A"
    assert sort_performances(result, "adjusted_score", True).iloc[-1].team == "A"


@pytest.mark.parametrize("field,side,expected", [
    ("raw_ppa", "offense", False), ("raw_ppa", "defense", True),
    ("offense_stuffrate", "offense", True), ("defense_stuffrate", "defense", False),
    ("defense_lineyards", "defense", True), ("defense_powersuccess", "defense", True),
    ("defense_plays", "defense", False), ("adjusted_score", "defense", False),
])
def test_metric_sort_directions(field, side, expected):
    assert best_ascending(field, side) is expected


def test_load_week_batches_only_needed_ratings_and_uses_read_only_queries(monkeypatch):
    calls = []

    def read_df(sql, params=None):
        calls.append((sql, params))
        assert sql.strip().startswith("SELECT")
        if "team_advanced_game_stats" in sql:
            assert params == {"season": 2026, "season_type": "postseason", "week": 1}
            return pd.DataFrame([game(schedule_season_type="postseason"), game("B", schedule_season_type="postseason")])
        if "team_rating_runs" in sql:
            return pd.DataFrame([run()])
        assert params == {"run_ids": ["before"]}
        assert "power_rating" in sql and "blend" not in sql
        return ratings()

    monkeypatch.setitem(sys.modules, "utils.db", SimpleNamespace(read_df=read_df))
    frame, note = load_week(2026, "postseason", 1)
    assert len(calls) == 3
    assert len(frame) == 2 and note is None


def test_rating_query_failure_keeps_raw_performances(monkeypatch):
    def read_df(sql, params=None):
        if "team_advanced_game_stats" in sql:
            return pd.DataFrame([game(), game("B")])
        raise ConnectionError("rating table unavailable")

    monkeypatch.setitem(sys.modules, "utils.db", SimpleNamespace(read_df=read_df))
    frame, note = load_week(2026, "regular", 1)
    assert len(frame) == 2
    assert frame.opponent_strength_z.isna().all()
    assert "Raw performances" in note

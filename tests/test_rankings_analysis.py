"""Rank differences, membership, historical dates, and comparable rating blends."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils.rankings_analysis import (
    blend_rating_snapshot, build_bubble_watch, build_poll_comparison, build_rank_movements,
    comparison_date_bounds, disagreement_shortlists, movement_shortlists, resolve_rating_date,
    valid_comparison_date,
)


def rankings(*rows):
    return pd.DataFrame([
        dict(team=name, rank=rank, power_rating=100 - rank if rank is not None else None,
             logo=f"https://example.test/{name}.png", next_game_label=f"vs Opponent {name}")
        for name, rank in rows
    ])


def test_full_gaps_and_unranked_lower_bounds():
    poll = rankings(("Over", 8), ("Under", 20), ("Match", 1), ("Unrated", 15))
    power = rankings(("Over", 50), ("Under", 8), ("Unpolled", 9), ("Match", 1), ("Neither", 60))
    before_poll, before_power = poll.copy(deep=True), power.copy(deep=True)
    compared = build_poll_comparison(poll, power).set_index("team")
    assert compared.loc["Over", "gap"] == 42
    assert compared.loc["Under", "gap"] == -12
    assert compared.loc["Unpolled", "gap"] == -17
    assert compared.loc["Unpolled", "gap_is_minimum"]
    assert pd.isna(compared.loc["Unpolled", "poll_rank"])
    assert not compared.loc["Under", "gap_is_minimum"]
    assert compared.loc["Match", "gap"] == 0
    assert pd.isna(compared.loc["Unrated", "gap"])
    assert "Neither" not in compared.index
    pd.testing.assert_frame_equal(poll, before_poll)
    pd.testing.assert_frame_equal(power, before_power)


def test_shortlists_sort_by_gap_then_rating_then_name_and_exclude_zero_or_missing():
    names = ["C", "B", "A", "D", "E", "F"]
    poll = rankings(*[(name, 5) for name in names], ("Match", 1), ("Under", 20), ("Missing", 3))
    power = rankings(*[(name, 15) for name in names], ("Match", 1), ("Under", 10))
    over, under = disagreement_shortlists(build_poll_comparison(poll, power))
    assert over.team.tolist() == ["A", "B", "C", "D", "E"]
    assert under.team.tolist() == ["Under"]
    compared = build_poll_comparison(rankings(("A", 10), ("Z", 5)), rankings(("A", 20), ("Z", 15)))
    assert disagreement_shortlists(compared)[0].team.tolist() == ["Z", "A"]


@pytest.mark.parametrize("poll,power", [(pd.DataFrame(), rankings(("A", 1))), (rankings(("A", 1)), pd.DataFrame()), (pd.DataFrame(), pd.DataFrame())])
def test_missing_sources_never_fabricate_gaps(poll, power):
    comparison = build_poll_comparison(poll, power)
    assert comparison.gap.isna().all()
    assert not comparison.gap_is_minimum.any()
    assert all(frame.empty for frame in disagreement_shortlists(comparison))


def test_top25_membership_counts_and_missing_rating_are_distinct():
    comparison = build_poll_comparison(
        rankings(("Shared", 1), ("PollOnly", 10), ("NoRating", 20), ("ReceivingVotes", 30)),
        rankings(("Shared", 2), ("PollOnly", 50), ("ReceivingVotes", 8), ("RatingsOnly", 25)),
    ).set_index("team")
    assert (comparison.in_poll & comparison.in_ratings).sum() == 1
    assert (comparison.in_poll & ~comparison.in_ratings).sum() == 2
    assert (comparison.in_ratings & ~comparison.in_poll).sum() == 2
    assert pd.isna(comparison.loc["ReceivingVotes", "poll_rank"])
    assert comparison.loc["ReceivingVotes", "gap"] == -18
    assert pd.isna(comparison.loc["NoRating", "rating_rank"])


def test_bubble_includes_only_26_through_30_with_cutoff_gap_poll_and_next_game():
    power = rankings(*[(f"Team{rank}", rank) for rank in range(24, 33)])
    bubble = build_bubble_watch(power, rankings(("Team26", 15)))
    assert bubble["rank"].tolist() == [26, 27, 28, 29, 30]
    assert bubble.points_to_top25.tolist() == [1, 2, 3, 4, 5]
    assert bubble.iloc[0].poll_rank == 15
    assert bubble.iloc[1:].poll_rank.isna().all()
    assert bubble.iloc[0].next_game_label == "vs Opponent Team26"
    assert build_bubble_watch(rankings(("A", 26))).points_to_top25.isna().all()
    assert build_bubble_watch(pd.DataFrame()).empty


def test_poll_movement_uses_exact_shared_ranks_and_labels_membership():
    current = rankings(("Up", 1), ("Down", 20), ("New", 12), ("Same", 25))
    previous = rankings(("Up", 5), ("Down", 2), ("Dropped", 8), ("Same", 25))
    movement = build_rank_movements(current, previous, poll=True).set_index("team")
    assert movement.loc["Up", "rank_change"] == 4
    assert movement.loc["Down", "rank_change"] == -18
    assert movement.loc["Same", "rank_change"] == 0
    assert movement.loc["New", "entered_top25"]
    assert movement.loc["Dropped", "left_top25"]
    assert movement.loc[["New", "Dropped"], "rank_change"].isna().all()
    risers, fallers = movement_shortlists(movement.reset_index())
    assert risers.team.tolist() == ["Up"]
    assert fallers.team.tolist() == ["Down"]


def test_ratings_movement_covers_all_fbs_and_does_not_invent_missing_history():
    previous = rankings(("BigMove", 100), ("Enter", 26), ("Leave", 24), ("Gone", 10), ("Same", 5))
    current = rankings(("BigMove", 50), ("Enter", 25), ("Leave", 27), ("NewRecord", 1), ("Same", 5))
    movement = build_rank_movements(current, previous)
    indexed = movement.set_index("team")
    assert movement_shortlists(movement)[0].team.tolist() == ["BigMove", "Enter"]
    assert indexed.loc["BigMove", "rating_change"] == 50
    assert indexed.loc["Enter", "entered_top25"]
    assert indexed.loc["Leave", "left_top25"]
    assert not indexed.loc["NewRecord", "entered_top25"]
    assert not indexed.loc["Gone", "left_top25"]
    assert indexed.loc[["NewRecord", "Gone"], "rank_change"].isna().all()


def test_missing_movement_source_does_not_create_entrants_or_departures():
    for poll in (True, False):
        for current, previous in [(rankings(("A", 1)), pd.DataFrame()), (pd.DataFrame(), rankings(("A", 1)))]:
            movement = build_rank_movements(current, previous, poll=poll)
            assert movement.empty
            assert all(frame.empty for frame in movement_shortlists(movement))


def test_movement_ties_are_stable_and_shortlists_are_limited():
    current = rankings(*[(name, 10) for name in reversed("ABCDEFG")])
    previous = rankings(*[(name, 20) for name in "ABCDEFG"])
    risers, fallers = movement_shortlists(build_rank_movements(current, previous))
    assert risers.team.tolist() == list("ABCDE")
    assert fallers.empty


@pytest.fixture
def run_dates():
    return pd.DataFrame({"completed_date": [date(2026, 9, 7), date(2026, 9, 3), date(2026, 9, 1), None, date(2026, 9, 3)]})


def test_requested_dates_resolve_to_actual_snapshots_before_comparison_bounds(run_dates):
    actual = resolve_rating_date(run_dates, date(2026, 9, 6))
    assert actual == date(2026, 9, 3)
    bounds = comparison_date_bounds(run_dates, actual)
    assert bounds == (date(2026, 9, 1), date(2026, 9, 2), date(2026, 9, 1))
    assert resolve_rating_date(run_dates, date(2026, 9, 2)) == date(2026, 9, 1)
    assert resolve_rating_date(run_dates, date(2026, 9, 20)) == date(2026, 9, 7)
    assert resolve_rating_date(run_dates, date(2026, 8, 31)) is None
    assert resolve_rating_date(run_dates, None) is None
    assert resolve_rating_date(pd.DataFrame(), date(2026, 9, 1)) is None


def test_comparison_defaults_and_reset_of_invalid_saved_dates(run_dates):
    bounds = comparison_date_bounds(run_dates, date(2026, 9, 7))
    assert valid_comparison_date(None, bounds) == date(2026, 9, 3)
    assert valid_comparison_date(date(2026, 9, 6), bounds) == date(2026, 9, 6)
    assert valid_comparison_date(date(2026, 9, 7), bounds) == date(2026, 9, 3)
    assert valid_comparison_date(date(2025, 9, 1), bounds) == date(2026, 9, 3)
    assert comparison_date_bounds(run_dates, date(2026, 9, 1)) is None
    assert comparison_date_bounds(run_dates, None) is None


def test_both_rating_snapshots_apply_the_same_blend_and_changes_update():
    previous = pd.DataFrame({"team": ["A", "B"], "power_rating": [10., 0.]})
    current = pd.DataFrame({"team": ["A", "B"], "power_rating": [20., 0.]})
    old_tr = pd.DataFrame({"team": ["A", "B"], "teamrankings_rating": [100., 0.]})
    new_tr = pd.DataFrame({"team": ["A", "B"], "teamrankings_rating": [0., 100.]})
    for weight, current_values, changes in [(0., [20., 0.], [0, 0]), (.75, [5., 15.], [-1, 1]), (1., [0., 20.], [-1, 1])]:
        before = blend_rating_snapshot(previous, old_tr, weight)
        now = blend_rating_snapshot(current, new_tr, weight)
        assert before.set_index("team").loc[["A", "B"], "power_rating"].tolist() == [10., 0.]
        assert now.set_index("team").loc[["A", "B"], "power_rating"].tolist() == current_values
        movement = build_rank_movements(now, before).set_index("team")
        assert movement.loc[["A", "B"], "rank_change"].tolist() == changes
        assert before.teamrankings_blend_weight.eq(weight).all()
        assert now.teamrankings_blend_weight.eq(weight).all()
    assert current.power_rating.tolist() == [20., 0.]


@pytest.mark.parametrize("teamrankings", [pd.DataFrame(), pd.DataFrame({"team": ["A"], "teamrankings_rating": [5.]}), pd.DataFrame({"team": ["A", "B"], "teamrankings_rating": [5., 5.]})])
def test_unavailable_or_unusable_blend_preserves_bg_ratings(teamrankings):
    power = pd.DataFrame({"team": ["A", "B"], "power_rating": [10., 0.]})
    blended = blend_rating_snapshot(power, teamrankings, .5)
    assert blended.power_rating.tolist() == [10., 0.]
    assert blended["rank"].tolist() == [1, 2]


def test_missing_teamrankings_for_one_team_uses_its_bg_value():
    power = pd.DataFrame({"team": ["A", "B", "C"], "power_rating": [20., 0., -5.]})
    tr = pd.DataFrame({"team": ["A", "B"], "teamrankings_rating": [0., 100.]})
    blended = blend_rating_snapshot(power, tr, 1.).set_index("team")
    assert blended.loc["C", "power_rating"] == -5
    assert pd.isna(blended.loc["C", "teamrankings_scaled_rating"])

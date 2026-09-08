"""Existing weekly award rules, expanded from one pick to five candidates."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils.schedule_awards import build_award_shortlists, shortlist_table


def team(index, **changes):
    row = dict(game_id=index, team=f"Team {index}", opponent=f"Opponent {index}",
               points_for=30 + index, points_against=20, actual_mov=10 + index,
               projected_mov=20, won=True, vs_fcs=False, win_probability=.5,
               offense_ppa=.3, defense_ppa=.1, offense_ppa_percentile=80, defense_ppa_percentile=75)
    row.update(changes)
    return row


def awards(rows, games=None):
    return {award.name: award for award in build_award_shortlists(
        pd.DataFrame(rows), pd.DataFrame() if games is None else games, "excitement")}


def test_each_award_exists_and_top_five_keeps_existing_margin_order():
    result = awards([team(i) for i in range(8)])
    assert list(result) == ["Biggest Winner", "Biggest Upset", "Closest Win", "Best Offense", "Best Defense",
                            "Underwhelming", "Almost Did It", "Most Exciting"]
    assert result["Biggest Winner"].candidates.game_id.tolist() == [7, 6, 5, 4, 3]
    assert all(len(award.candidates) <= 5 for award in result.values())


def test_winner_eligibility_upset_and_closest_win_tiebreak():
    result = awards([
        team(1, actual_mov=1, win_probability=.8), team(2, actual_mov=1, win_probability=.2),
        team(3, actual_mov=50, vs_fcs=True), team(4, actual_mov=-3, won=False),
        team(5, actual_mov=2, win_probability=None),
    ])
    assert result["Biggest Winner"].candidates.game_id.tolist() == [5, 1, 2]
    assert result["Biggest Upset"].candidates.game_id.tolist() == [2, 3, 1]
    assert result["Closest Win"].candidates.game_id.tolist() == [1, 2, 3]


def test_offense_and_defense_preserve_probability_multiplier_and_sort_direction():
    result = awards([
        team(1, win_probability=.2, offense_ppa=.5, defense_ppa=.05),
        team(2, win_probability=.8, offense_ppa=.6, defense_ppa=.01),
        team(3, vs_fcs=True, offense_ppa_percentile=100, defense_ppa_percentile=100),
    ])
    offense = result["Best Offense"].candidates
    defense = result["Best Defense"].candidates
    assert offense.game_id.tolist() == [1, 2]
    assert defense.game_id.tolist() == [1, 2]
    assert offense.iloc[0].offense_score == pytest.approx(80 * 1.15)
    assert defense.iloc[0].defense_score == pytest.approx(75 * 1.15)
    ties = awards([team(1, defense_ppa=.2), team(2, defense_ppa=.1)])
    assert ties["Best Defense"].candidates.game_id.tolist() == [2, 1]


def test_missing_stats_and_neutral_probability_fallback_are_preserved():
    result = awards([
        team(1, win_probability=None), team(2, offense_ppa=None, defense_ppa=None),
        team(3, offense_ppa_percentile=None, defense_ppa_percentile=None),
    ])
    assert result["Best Offense"].candidates.game_id.tolist() == [1]
    assert result["Best Offense"].candidates.iloc[0].offense_score == 80
    table = shortlist_table(result["Best Offense"])
    assert pd.isna(table.iloc[0]["Win probability"])


def test_underwhelming_and_almost_did_it_preserve_existing_rules():
    result = awards([
        team(1, actual_mov=3, projected_mov=20),
        team(2, actual_mov=-3, projected_mov=-14, won=False, win_probability=.2),
        team(3, actual_mov=-15, projected_mov=-30, won=False, win_probability=.1),
        team(4, actual_mov=-3, projected_mov=-1, won=False, win_probability=.2),
        team(5, actual_mov=-3, projected_mov=-14, won=False, win_probability=.7),
    ])
    assert result["Underwhelming"].candidates.game_id.tolist() == [1]
    almost = result["Almost Did It"].candidates
    assert almost.game_id.tolist() == [2]
    assert almost.iloc[0].almost_famous_score == pytest.approx(11 + .8 * 20 - 3 * .75)


def test_most_exciting_returns_five_games_without_duplicating_team_rows():
    games = pd.DataFrame([dict(game_id=i, matchup=f"Away {i} at Home {i}", homepoints=30,
                               awaypoints=20, excitement=i) for i in range(8)])
    award = awards([], games)["Most Exciting"]
    assert award.candidates.game_id.tolist() == [7, 6, 5, 4, 3]
    table = shortlist_table(award)
    assert table["Candidate rank"].tolist() == [1, 2, 3, 4, 5]
    assert table.iloc[0]["Final score (away–home)"] == "20–30"
    assert table.iloc[0]["Matchup"] == "Away 7 at Home 7"


def test_short_empty_and_missing_excitement_lists_are_not_padded():
    empty = awards([])
    assert all(award.candidates.empty for award in empty.values())
    single = awards([team(1)])
    assert len(single["Biggest Winner"].candidates) == 1
    assert single["Almost Did It"].candidates.empty
    assert single["Most Exciting"].candidates.empty


def test_candidate_table_shows_names_results_and_numeric_evidence_without_mutation():
    source = pd.DataFrame([team(1, win_probability=.25)])
    original = source.copy(deep=True)
    shortlist = build_award_shortlists(source, pd.DataFrame())[1]
    table = shortlist_table(shortlist)
    assert table.iloc[0]["Team"] == "Team 1"
    assert table.iloc[0]["Opponent"] == "Opponent 1"
    assert table.iloc[0]["Result"] == "W 31–20"
    assert table.iloc[0]["Win probability"] == 25.0
    pd.testing.assert_frame_equal(source, original)

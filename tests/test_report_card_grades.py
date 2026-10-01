"""Report-card parity, comparison arithmetic, missing data and batched reads."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils.report_card_grades import percentile_grade
from utils.weekly_performances import (
    GRADE_COLUMNS, adjusted_grade_scores, build_grade_comparison, grade_metrics,
    grade_peer_groups, load_grade_baselines,
)


@pytest.mark.parametrize("higher", [True, False])
@pytest.mark.parametrize("value", [-1, 0, .2, .4, .9])
def test_percentile_matches_existing_report_card_with_ties(higher, value):
    baseline = pd.Series([0, .2, .2, .4, np.nan]).dropna()
    observations = pd.concat([baseline, pd.Series([value])], ignore_index=True)
    if not higher:
        observations = -observations
    expected = observations.rank(pct=True).iloc[-1] * 100
    assert percentile_grade(baseline, value, higher) == expected


def test_empty_baseline_is_neutral_and_missing_value_stays_missing():
    assert percentile_grade(pd.Series(dtype=float), .2) == 50
    assert np.isnan(percentile_grade(pd.Series([.1, .2]), np.nan))


def comparison_inputs():
    season = pd.DataFrame([
        dict(team="A", conference="SEC", offense_ppa=.4, defense_ppa=.4),
        dict(team="B", conference="ACC", offense_ppa=.2, defense_ppa=.2),
        dict(team="Bye", conference="Big Ten", offense_ppa=.3, defense_ppa=.3),
    ])
    games = pd.DataFrame([
        dict(team="A", conference="SEC", offense_ppa=.2, defense_ppa=.2, offense_plays=50, defense_plays=50),
        dict(team="B", conference="ACC", offense_ppa=.4, defense_ppa=.4, offense_plays=50, defense_plays=50),
    ])
    baseline = pd.DataFrame(dict(offense_ppa=[.1, .2, .4, .5], defense_ppa=[.1, .2, .4, .5],
                                 offense_plays=50, defense_plays=50))
    return games, season, baseline


def test_season_and_game_use_their_own_population_and_net_ppa():
    grades = build_grade_comparison(*comparison_inputs()).set_index("team")
    assert grades.loc["A", "season_offense"] == 87.5
    assert grades.loc["A", "season_defense"] == 37.5
    assert grades.loc["A", "game_offense"] == 50
    assert grades.loc["A", "game_defense"] == 70
    assert grades.loc["A", "season_overall"] == 62.5
    assert grades.loc["A", "game_overall"] == 60
    assert grades.loc["Bye", ["game_offense", "game_defense", "game_overall"]].isna().all()


def test_missing_season_side_or_ineligible_game_side_does_not_create_overall_grade():
    games, season, baseline = comparison_inputs()
    games.loc[0, "offense_plays"] = 0
    season.loc[0, "defense_ppa"] = np.nan
    grades = build_grade_comparison(games, season, baseline).set_index("team")
    assert grades.loc["A", ["game_offense", "game_overall", "season_defense", "season_overall"]].isna().all()
    assert pd.notna(grades.loc["A", "game_defense"])
    assert pd.notna(grades.loc["A", "season_offense"])
    grades = build_grade_comparison(games, season.iloc[1:], baseline).set_index("team")
    assert grades.loc["A", ["season_offense", "season_defense", "season_overall"]].isna().all()
    assert grades.loc["A", "conference"] == "SEC"


def test_multiple_games_average_individual_grades_and_keep_one_row_per_team():
    games, season, baseline = comparison_inputs()
    extra = games.iloc[[0]].copy()
    extra["offense_ppa"] = .9
    grades = build_grade_comparison(pd.concat([games, extra], ignore_index=True), season, baseline).set_index("team")
    assert grades.index.is_unique
    assert grades.loc["A", "game_offense"] == 75  # Average of 50 and 100.
    assert grades.loc["A", "game_overall"] == 80  # Mean of net-PPA percentiles 60 and 100.


def test_empty_season_data_preserves_game_grades():
    games, _, baseline = comparison_inputs()
    grades = build_grade_comparison(games, pd.DataFrame(), baseline)
    assert len(grades) == 2
    assert grades.season_overall.isna().all()
    assert grades.game_overall.notna().all()


def test_dominant_offense_outweighs_mid_defense_by_net_ppa():
    games, season, baseline = comparison_inputs()
    season.loc[0, ["offense_ppa", "defense_ppa"]] = [1.5, .3]
    games.loc[0, ["offense_ppa", "defense_ppa"]] = [1.5, .3]
    grades = build_grade_comparison(games, season, baseline).set_index("team")
    assert grades.loc["A", "season_overall"] == 87.5
    assert grades.loc["A", "game_overall"] == 100
    for scope in ("season", "game"):
        assert grades.loc["A", f"{scope}_overall"] > grades.loc["A", [f"{scope}_offense", f"{scope}_defense"]].mean()


def adjusted_inputs():
    season = pd.DataFrame({
        "team": ["A", "B", "Notre Dame", "C", "D", "E"],
        "conference": ["SEC", "Big Ten", "FBS Independents", "Sun Belt", "Pac-12", "FBS Independents"],
        "offense_ppa": [.8, .4, .2, .2, .1, 0],
        "defense_ppa": [.2, .15, .3, .5, .4, .6],
    })
    baseline = season.assign(offense_plays=50, defense_plays=60, game_id=1, season=2026,
                             opponent_strength_z=[-1., 1., 0., 1., -1., 0.])
    return baseline.copy(), season, baseline


def test_adjusted_scores_use_global_reference_and_one_quarter_bonus_for_each_metric():
    # The selected game must be standardized against all season observations.
    baseline = pd.DataFrame({"offense_ppa": [1., 3.], "defense_ppa": [3., 1.]})
    selected = pd.DataFrame({"offense_ppa": [3.], "defense_ppa": [1.]})
    scores = adjusted_grade_scores(grade_metrics(selected), grade_metrics(baseline), pd.Series([2.]))
    assert scores.iloc[0].tolist() == pytest.approx([1.5, 1.5, 1.5])
    # A stronger opponent improves identical performance on every metric.
    weaker = adjusted_grade_scores(grade_metrics(selected), grade_metrics(baseline), pd.Series([-2.]))
    assert (scores - weaker).iloc[0].tolist() == pytest.approx([1., 1., 1.])


def test_adjusted_percentiles_split_peers_while_raw_uses_all_fbs():
    games, season, baseline = adjusted_inputs()
    adjusted = build_grade_comparison(games, season, baseline, "BG-adjusted").set_index("team")
    raw = build_grade_comparison(games, season, baseline).set_index("team")
    # C leads G5 offense despite falling well behind A and B nationally.
    assert adjusted.loc["C", "game_offense"] == 87.5
    assert raw.loc["C", "game_offense"] == pytest.approx(4 / 7 * 100)
    assert adjusted.loc["A", "game_offense"] == 87.5
    assert adjusted.loc["C", "peer_group"] == "G5"
    assert adjusted.loc["Notre Dame", "peer_group"] == "P4"
    for column in GRADE_COLUMNS:
        assert not adjusted[column].equals(raw[column])


def test_season_adjusts_stored_totals_using_equal_weight_complete_schedule():
    games, season, baseline = adjusted_inputs()
    extra = baseline.iloc[[0]].assign(game_id=2, opponent_strength_z=3., offense_plays=500,
                                      offense_ppa=-99, defense_ppa=99)
    baseline = pd.concat([baseline, extra], ignore_index=True)
    actual = build_grade_comparison(games, season, baseline, "BG-adjusted").set_index("team")
    # A's opponent strength is (-1 + 3) / 2 = 1, regardless of plays or game PPA.
    strength = pd.Series([1., 1., 0., 1., -1., 0.])
    metrics = grade_metrics(season)
    groups = grade_peer_groups(season)
    for metric in ("offense", "defense", "overall"):
        values = metrics[metric]
        expected_scores = (values - values.mean()) / values.std(ddof=0) + .25 * strength
        expected = percentile_grade(expected_scores[groups.eq("P4")], expected_scores.iloc[0])
        assert actual.loc["A", f"season_{metric}"] == expected
    assert actual.loc["A", "rating_coverage"] == "Season 2/2 · Week 1/1"


def test_missing_stats_game_still_counts_against_season_rating_coverage():
    games, season, baseline = adjusted_inputs()
    extra = baseline.iloc[[0]].assign(game_id=2, opponent_strength_z=np.nan, offense_plays=np.nan,
                                      defense_plays=np.nan, offense_ppa=np.nan, defense_ppa=np.nan)
    baseline = pd.concat([baseline, extra], ignore_index=True)
    adjusted = build_grade_comparison(games, season, baseline, "BG-adjusted").set_index("team")
    assert adjusted.loc["A", ["season_offense", "season_defense", "season_overall"]].isna().all()
    assert adjusted.loc["A", "rating_coverage"] == "Season 1/2 · Week 1/1"
    assert "Season: Incomplete pregame ratings" in adjusted.loc["A", "grade_status"]
    assert adjusted.loc["A", ["game_offense", "game_defense", "game_overall"]].notna().all()
    raw = build_grade_comparison(games, season, baseline).set_index("team")
    assert raw.loc["A", list(GRADE_COLUMNS)].notna().all()


def test_missing_rating_never_falls_back_and_multiple_games_propagate_missing():
    games, season, baseline = adjusted_inputs()
    extra = games.iloc[[0]].assign(game_id=2, opponent_strength_z=np.nan)
    games = pd.concat([games, extra], ignore_index=True)
    result = build_grade_comparison(games, season, baseline, "BG-adjusted").set_index("team")
    assert result.loc["A", ["game_offense", "game_defense", "game_overall"]].isna().all()
    assert "Week: Incomplete pregame ratings" in result.loc["A", "grade_status"]
    assert result.loc["A", "rating_coverage"] == "Season 1/1 · Week 1/2"


def test_adjusted_multiple_games_average_each_independent_grade():
    games, season, baseline = adjusted_inputs()
    extra = games.iloc[[0]].assign(game_id=2, offense_ppa=0., defense_ppa=.9)
    first = build_grade_comparison(games, season, baseline, "BG-adjusted").set_index("team")
    second = build_grade_comparison(extra, season, baseline, "BG-adjusted").set_index("team")
    result = build_grade_comparison(pd.concat([games, extra]), season, baseline, "BG-adjusted").set_index("team")
    assert result.index.is_unique
    for metric in ("offense", "defense", "overall"):
        column = f"game_{metric}"
        assert result.loc["A", column] == (first.loc["A", column] + second.loc["A", column]) / 2


def test_peer_aliases_and_unknown_conference():
    frame = pd.DataFrame({"team": ["a", "b", "Notre Dame Fighting Irish", "c", "d", "e"],
                          "conference": [" Big 10 ", "BIG 12", None, "Pac 12", "Independent", None]})
    assert grade_peer_groups(frame).tolist() == ["P4", "P4", "P4", "G5", "G5", None]


def test_missing_side_and_ineligible_plays_are_excluded_from_adjusted_baselines():
    games, season, baseline = adjusted_inputs()
    season.loc[0, "defense_ppa"] = np.nan
    games.loc[0, "offense_plays"] = 0
    baseline.loc[0, "offense_plays"] = 0
    result = build_grade_comparison(games, season, baseline, "BG-adjusted").set_index("team")
    assert result.loc["A", ["season_defense", "season_overall", "game_offense", "game_overall"]].isna().all()
    assert result.loc["A", ["season_offense", "game_defense"]].notna().all()
    changed = baseline.copy()
    changed.loc[0, "offense_ppa"] = 9999
    again = build_grade_comparison(games, season, changed, "BG-adjusted").set_index("team")
    pd.testing.assert_frame_equal(result, again)


def test_constant_distributions_and_ties_preserve_percentile_convention():
    games, season, baseline = adjusted_inputs()
    for data in (games, season, baseline):
        data[["offense_ppa", "defense_ppa"]] = .2
    games["opponent_strength_z"] = baseline["opponent_strength_z"] = 0.
    result = build_grade_comparison(games, season, baseline, "BG-adjusted")
    assert (result[list(GRADE_COLUMNS)] == 62.5).all().all()  # Three peers plus inserted tied value.


def test_adjusted_cohort_requires_two_valid_scores_and_unknown_group_stays_blank():
    games, season, baseline = adjusted_inputs()
    baseline.loc[baseline.team.isin(["D", "E"]), "opponent_strength_z"] = np.nan
    games.loc[games.team.eq("A"), "conference"] = None
    season.loc[season.team.eq("A"), "conference"] = None
    result = build_grade_comparison(games, season, baseline, "BG-adjusted").set_index("team")
    assert result.loc["C", list(GRADE_COLUMNS)].isna().all()
    assert result.loc["A", list(GRADE_COLUMNS)].isna().all()
    assert "Peer group unavailable" in result.loc["A", "grade_status"]
    assert "fewer than two" in result.loc["C", "grade_status"]


def test_empty_adjusted_season_or_schedule_and_bye_teams():
    games, season, baseline = adjusted_inputs()
    result = build_grade_comparison(games, pd.DataFrame(), baseline, "BG-adjusted")
    assert result.season_overall.isna().all()
    assert result.game_overall.notna().all()
    result = build_grade_comparison(games, season, pd.DataFrame(), "BG-adjusted")
    assert result[list(GRADE_COLUMNS)].isna().all().all()
    result = build_grade_comparison(games.iloc[:0], season, baseline, "BG-adjusted")
    assert result.game_overall.isna().all()
    assert result.season_overall.notna().all()


def test_baseline_queries_use_schedule_left_join_and_fbs_season_membership(monkeypatch):
    calls = []

    def read_df(sql, params):
        calls.append(sql)
        assert sql.strip().startswith("SELECT")
        assert params == {"season": 2026}
        assert ":week" not in sql and ":season_type" not in sql
        assert "offense_ppa" in sql and "defense_ppa" in sql
        if "team_advanced_game_stats" in sql:
            assert "LOWER(g.homeclassification) = 'fbs'" in sql
            assert "LOWER(g.awayclassification) = 'fbs'" in sql
            assert "g.season = :season" in sql and "g.completed IS TRUE" in sql
            assert "LEFT JOIN public.team_advanced_game_stats" in sql
            assert "gs.season = g.season" in sql
        else:
            assert "EXISTS" in sql and "g.season = s.season" in sql
        return pd.DataFrame()

    monkeypatch.setitem(sys.modules, "utils.db", SimpleNamespace(read_df=read_df))
    load_grade_baselines(2026)
    assert len(calls) == 2


@pytest.mark.parametrize("failure", [None, "runs", "ratings"])
def test_season_loader_batches_pregame_context_and_preserves_raw_on_failure(monkeypatch, failure):
    _, season, schedule = adjusted_inputs()
    schedule["opponent"] = ["B", "A", "C", "Notre Dame", "E", "D"]
    schedule["startdate"] = "2026-09-05T16:00:00Z"
    schedule["starttimetbd"] = None
    schedule.loc[0, ["offense_ppa", "defense_ppa", "offense_plays", "defense_plays"]] = np.nan
    runs = pd.DataFrame([
        dict(rating_run_id=identifier, season=2026, status="success", run_type="manual",
             completed_at=time, created_at=time)
        for identifier, time in [("before", "2026-09-05T12:00:00Z"), ("at-kickoff", "2026-09-05T16:00:00Z")]
    ])
    ratings = pd.DataFrame(dict(rating_run_id="before", team=season.team, classification="fbs",
                               power_rating=[1., 2., 3., 4., 5., 6.]))
    calls = []

    def read_df(sql, params):
        calls.append((sql, params))
        assert sql.strip().startswith("SELECT")
        if "team_advanced_season_stats" in sql:
            return season.copy()
        if "team_advanced_game_stats" in sql:
            return schedule.drop(columns=["opponent_strength_z"]).copy()
        if "team_rating_runs" in sql:
            if failure == "runs":
                raise ConnectionError("No history")
            return runs
        assert params == {"run_ids": ["before"]}
        if failure == "ratings":
            raise ConnectionError("No ratings")
        return ratings

    monkeypatch.setitem(sys.modules, "utils.db", SimpleNamespace(read_df=read_df))
    loaded_season, loaded_games = load_grade_baselines(2026)
    assert len(calls) == (3 if failure == "runs" else 4)
    pd.testing.assert_frame_equal(loaded_season, season)
    assert len(loaded_games) == 6  # The missing-stats schedule row survives.
    assert loaded_games.offense_ppa.notna().sum() == 5
    if failure:
        assert loaded_games.opponent_strength_z.isna().all()
        assert "Raw performances" in loaded_games.attrs["rating_note"]
    else:
        assert loaded_games.rating_run_id.eq("before").all()
        assert loaded_games.opponent_strength_z.notna().all()

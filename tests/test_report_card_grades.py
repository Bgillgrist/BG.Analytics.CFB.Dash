"""Report-card parity, comparison arithmetic, missing data and batched reads."""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils.report_card_grades import percentile_grade
from utils.weekly_performances import build_grade_comparison, load_grade_baselines


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
    baseline = pd.DataFrame(dict(offense_ppa=[.1, .2, .4, .5], defense_ppa=[.1, .2, .4, .5]))
    return games, season, baseline


def test_season_and_game_use_their_own_population_and_average_unrounded_grades():
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
    assert grades.loc["A", "game_overall"] == 72.5


def test_empty_season_data_preserves_game_grades():
    games, _, baseline = comparison_inputs()
    grades = build_grade_comparison(games, pd.DataFrame(), baseline)
    assert len(grades) == 2
    assert grades.season_overall.isna().all()
    assert grades.game_overall.notna().all()


def test_baseline_queries_match_report_cards_and_are_batched(monkeypatch):
    calls = []

    def read_df(sql, params):
        calls.append(sql)
        assert sql.strip().startswith("SELECT")
        assert params == {"season": 2026}
        assert "week" not in sql and "seasontype" not in sql
        assert "offense_ppa" in sql and "defense_ppa" in sql
        if "team_advanced_game_stats" in sql:
            assert "gd.homeclassification = 'fbs'" in sql
            assert "gd.awayclassification = 'fbs'" in sql
            assert "gd.season = :season" in sql
        return pd.DataFrame()

    monkeypatch.setitem(sys.modules, "utils.db", SimpleNamespace(read_df=read_df))
    load_grade_baselines(2026)
    assert len(calls) == 2

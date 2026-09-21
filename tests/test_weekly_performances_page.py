"""Interaction smoke tests, runnable with the dashboard's Streamlit dependency."""

import sys
from pathlib import Path

import pandas as pd
import pytest

st = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from utils import weekly_performances as weekly


def widget(elements, label):
    return next(element for element in elements if element.label == label)


@pytest.fixture
def page(monkeypatch):
    st.cache_data.clear()
    weeks = pd.DataFrame([
        {"season": 2026, "season_type": "regular", "week": 2},
        {"season": 2026, "season_type": "regular", "week": 1},
        {"season": 2026, "season_type": "postseason", "week": 1},
        {"season": 2025, "season_type": "regular", "week": 1},
    ])

    def load_week(season, phase, week):
        records = []
        for index, (name, opponent, conference) in enumerate([("Alpha", "Bravo", "SEC"), ("Bravo", "Alpha", "ACC")]):
            record = dict(team=name, opponent=opponent, conference=conference, venue="Home" if index == 0 else "Away",
                          result="W" if index == 0 else "L", final_score="31–17" if index == 0 else "17–31",
                          game_id=1, season=season, week=week, season_type=phase,
                          kickoff=pd.Timestamp("2026-09-05T16:00:00Z"),
                          rating_completed_at=pd.Timestamp("2026-09-05T12:00:00Z"), rating_run_id="test-run",
                          opponent_bg_rating=10 if index == 0 else -10,
                          opponent_strength_z=(1 if index == 0 else -1) if season == 2026 else float("nan"),
                          adjustment_note=None if season == 2026 else "No saved pregame BG rating")
            for side in ("offense", "defense"):
                for suffix in weekly.METRIC_LABELS:
                    record[f"{side}_{suffix}"] = 60 if suffix in ("plays", "drives") else .4 - index * .2
            records.append(record)
        return pd.DataFrame(records), None

    monkeypatch.setattr(weekly, "load_available_weeks", lambda: weeks)
    monkeypatch.setattr(weekly, "load_week", load_week)
    def load_grade_baselines(season):
        scale = 1 if season == 2026 else 2
        season_stats = pd.DataFrame([
            dict(team="Alpha", conference="SEC", offense_ppa=.4 * scale, defense_ppa=.4 * scale),
            dict(team="Bravo", conference="ACC", offense_ppa=.2 * scale, defense_ppa=.2 * scale),
            dict(team="Bye team", conference="Big Ten", offense_ppa=.3 * scale, defense_ppa=.3 * scale),
        ])
        return season_stats, season_stats[["offense_ppa", "defense_ppa"]]

    monkeypatch.setattr(weekly, "load_grade_baselines", load_grade_baselines)
    yield AppTest.from_file(str(ROOT / "app/pages/weekly_performances.py"), default_timeout=20)
    st.cache_data.clear()


def test_initial_selectors_tabs_and_adjusted_mode(page):
    page.run()
    assert not page.exception
    assert widget(page.selectbox, "Season").value == 2026
    assert widget(page.selectbox, "Week").value == 2
    assert widget(page.radio, "Ranking mode").value == "BG-adjusted"
    assert [tab.label for tab in page.tabs] == ["Offense", "Defense"]
    assert page.dataframe[0].value.team.tolist() == ["Alpha", "Bravo"]
    assert page.dataframe[1].value.team.tolist() == ["Bravo", "Alpha"]
    assert not page.get("download_button")


def test_filters_preserve_ranks_and_presets_keep_raw_values(page):
    page.run()
    original = page.dataframe[0].value.set_index("team")
    widget(page.multiselect, "Conferences").set_value(["ACC"]).run()
    assert page.dataframe[0].value.team.tolist() == ["Bravo"]
    assert page.dataframe[0].value.iloc[0].raw_rank == original.loc["Bravo", "raw_rank"]
    for preset in weekly.PRESETS:
        widget(page.selectbox, "Offense view").select(preset).run()
        assert not page.exception
        assert "raw_ppa" in page.dataframe[0].value
        assert "adjusted_score" in page.dataframe[0].value


def test_ranking_switch_sort_and_phase_selection(page):
    page.run()
    widget(page.radio, "Ranking mode").set_value("Raw PPA").run()
    page.selectbox(key="weekly_offense_order").select("Reverse").run()
    assert page.dataframe[0].value.team.tolist() == ["Bravo", "Alpha"]
    widget(page.selectbox, "Season Type").select("postseason").run()
    assert widget(page.selectbox, "Week").value == 1
    assert not page.exception


def test_missing_history_falls_back_to_raw_without_fabricating_scores(page):
    page.run()
    widget(page.selectbox, "Season").select(2025).run()
    assert not page.exception
    assert any("Showing raw PPA rankings" in message.value for message in page.info)
    assert page.dataframe[0].value.adjusted_score.isna().all()
    assert page.dataframe[0].value.raw_rank.notna().all()


def test_unavailable_data_has_clear_empty_and_error_states(page, monkeypatch):
    monkeypatch.setattr(weekly, "load_available_weeks", lambda: pd.DataFrame())
    page.run()
    assert not page.exception
    assert any("No completed FBS-vs-FBS games" in message.value for message in page.info)

    def unavailable():
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(weekly, "load_available_weeks", unavailable)
    page.run()
    assert not page.exception
    assert any("could not be loaded" in message.value for message in page.error)


def test_grade_table_has_six_numeric_grades_and_bye_teams(page):
    page.run()
    assert not page.exception
    grades = page.dataframe[2].value.set_index("team")
    assert grades.columns.tolist() == list(weekly.GRADE_COLUMNS)
    assert set(grades.index) == {"Alpha", "Bravo", "Bye team"}
    assert grades.loc["Alpha", "season_offense"] == 87.5
    assert grades.loc["Alpha", "season_defense"] == 37.5
    assert grades.loc["Alpha", "season_overall"] == 62.5
    assert grades.loc["Bye team", ["game_offense", "game_defense", "game_overall"]].isna().all()
    original = grades.copy()
    widget(page.radio, "Ranking mode").set_value("Raw PPA").run()
    pd.testing.assert_frame_equal(page.dataframe[2].value.set_index("team"), original)
    widget(page.multiselect, "Conferences").set_value(["ACC"]).run()
    pd.testing.assert_frame_equal(page.dataframe[2].value.set_index("team"), original.loc[["Bravo"]])


def test_grade_table_updates_with_week_phase_and_season(page, monkeypatch):
    original_load = weekly.load_week

    def load_week(season, phase, week):
        frame, note = original_load(season, phase, week)
        frame["offense_ppa"] += (week - 1) * .5 + (phase == "postseason") * .2
        return frame, note

    monkeypatch.setattr(weekly, "load_week", load_week)
    page.run()
    original = page.dataframe[2].value.set_index("team")
    widget(page.selectbox, "Week").select(1).run()
    earlier = page.dataframe[2].value.set_index("team")
    assert earlier.loc["Bravo", "game_offense"] < original.loc["Bravo", "game_offense"]
    pd.testing.assert_series_equal(earlier.season_overall.sort_index(), original.season_overall.sort_index())
    widget(page.selectbox, "Season Type").select("postseason").run()
    postseason = page.dataframe[2].value.set_index("team")
    assert postseason.loc["Bravo", "game_offense"] > earlier.loc["Bravo", "game_offense"]
    widget(page.selectbox, "Season").select(2025).run()
    assert not page.exception
    assert page.dataframe[2].value.set_index("team").loc["Alpha", "game_offense"] != earlier.loc["Alpha", "game_offense"]


def test_bye_team_can_be_selected_without_a_weekly_performance(page):
    page.run()
    widget(page.multiselect, "Teams").set_value(["Bye team"]).run()
    assert not page.exception
    assert len(page.dataframe) == 1
    assert page.dataframe[0].value.team.tolist() == ["Bye team"]


def test_grade_data_failure_keeps_existing_leaderboards(page, monkeypatch):
    def unavailable(season):
        raise ConnectionError("season statistics unavailable")

    monkeypatch.setattr(weekly, "load_grade_baselines", unavailable)
    page.run()
    assert not page.exception
    assert len(page.dataframe) == 2
    assert any("Report-card grades could not be loaded" in message.value for message in page.warning)

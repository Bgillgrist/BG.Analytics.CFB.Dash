"""Real Streamlit interaction checks with saved fixtures and no database calls."""

from pathlib import Path
import sys

import pandas as pd
import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")
from streamlit.testing.v1 import AppTest
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from utils import model_builder as builder, model_data
from test_model_builder import inputs
from test_predictive_performance import forecast, game


def widget(elements, label):
    return next(element for element in elements if element.label == label)


@pytest.fixture
def sources(monkeypatch):
    st.cache_data.clear()
    available = pd.DataFrame([
        dict(season=2025, games=40, unfinished=0), dict(season=2024, games=40, unfinished=0),
        dict(season=2023, games=40, unfinished=0),
    ])
    monkeypatch.setattr(model_data, "load_seasons", lambda: available)
    monkeypatch.setattr(model_data, "load_metric_catalog", lambda: ["offense_newmetric"])
    games = pd.DataFrame([game(), game("002", week=2, kickoff="2025-09-13T16:00Z", homepoints=10, awaypoints=20)])
    forecasts = pd.DataFrame([forecast(), forecast("other", game_id="002", home_win_probability=.2),
                              forecast("research", run_type="backfill", forecast_completed_at="2026-01-01T08:00Z")])
    monkeypatch.setattr(model_data, "load_performance", lambda seasons: (games, forecasts))
    calls = []
    def modeling_inputs(start, end, metrics, market=False):
        calls.append((start, end, metrics, market))
        games, ratings = [], []
        for season in [2023, 2024, 2025]:
            for i in range(40):
                games.append(game(f"{season}-{i}", season=season,
                    kickoff=pd.Timestamp(f"{season}-09-01T16:00Z") + pd.Timedelta(days=i),
                    homepoints=30 if i % 2 else 10, awaypoints=20))
            ratings.extend([dict(season=season, team=team, pull_date=f"{season}-08-01", rating=value)
                            for team, value in [("Alpha", 5), ("Bravo", 3)]])
        games.append(game("future", season=2025, completed=False, kickoff="2099-09-01T16:00Z", homepoints=None, awaypoints=None))
        return inputs(games, ratings=ratings)
    monkeypatch.setattr(model_data, "load_builder_inputs", modeling_inputs)
    yield calls
    st.cache_data.clear()


def test_performance_tabs_filters_research_and_downloads(sources):
    page = AppTest.from_file(str(ROOT / "app/pages/predictive_performance.py"), default_timeout=30).run()
    assert not page.exception
    assert [tab.label for tab in page.tabs] == ["Overview", "Win Probabilities", "Margins & Totals", "Breakdowns", "Game Audit"]
    assert any(metric.label == "Graded forecasts" and metric.value == "2" for metric in page.metric)
    widget(page.multiselect, "Teams").set_value(["Bravo"]).run()
    assert not page.exception
    widget(page.selectbox, "Forecast cutoff").select(168).run()
    # Week two's September 1 forecast predates its September 6 cutoff.
    assert any(metric.label == "Graded forecasts" and metric.value == "1" for metric in page.metric)
    widget(page.selectbox, "Forecast cutoff").select(0).run()
    widget(page.selectbox, "Forecast source").select("Historical research").run()
    assert not page.exception
    assert any("recreated later" in item.value for item in page.warning)
    assert any(metric.label == "Graded forecasts" and metric.value == "1" for metric in page.metric)
    assert len(page.get("download_button")) == 5
    assert sources == []


def test_performance_empty_seasons_and_missing_sources_are_clear(sources, monkeypatch):
    page = AppTest.from_file(str(ROOT / "app/pages/predictive_performance.py"), default_timeout=30).run()
    widget(page.multiselect, "Seasons").set_value([]).run()
    assert not page.exception
    assert any("at least one season" in item.value for item in page.info)
    monkeypatch.setattr(model_data, "load_performance", lambda seasons: (_ for _ in ()).throw(RuntimeError("private connection details")))
    page = AppTest.from_file(str(ROOT / "app/pages/predictive_performance.py"), default_timeout=30).run()
    assert not page.exception
    assert "private connection" not in page.error[0].value


def test_builder_trains_only_on_click_preserves_settings_and_fits_upcoming(sources):
    page = AppTest.from_file(str(ROOT / "app/pages/model_builder.py"), default_timeout=30).run()
    assert not page.exception
    assert sources == []
    widget(page.number_input, "Regularization strength").set_value(2.).run()
    assert sources == []
    widget(page.button, "Run experiment").click().run()
    assert not page.exception
    assert len(sources) == 1
    results = page.session_state["model_builder_experiments"]
    assert len(results) == 1
    result = next(iter(results.values()))
    assert result["config"]["params"]["regularization"] == 2.
    widget(page.number_input, "Regularization strength").set_value(3.).run()
    assert len(sources) == 1
    assert len(page.session_state["model_builder_experiments"]) == 1
    assert any("controls differ" in item.value for item in page.info)
    widget(page.button, "Fit for upcoming games").click().run()
    assert not page.exception
    assert len(sources) == 2
    updated = next(iter(page.session_state["model_builder_experiments"].values()))
    assert updated["upcoming_predictions"].game_id.tolist() == ["future"]
    assert updated["config"]["params"]["regularization"] == 2.
    assert len(page.get("download_button")) >= 12


def test_builder_new_features_and_failed_run_preserve_previous_results(sources, monkeypatch):
    page = AppTest.from_file(str(ROOT / "app/pages/model_builder.py"), default_timeout=30).run()
    widget(page.button, "Run experiment").click().run()
    assert not page.exception
    widget(page.radio, "Feature preset").set_value("Advanced").run()
    widget(page.multiselect, "Advanced game metrics").set_value(["offense_newmetric"]).run()
    assert builder.feature_label("home_season_offense_newmetric") in widget(page.multiselect, "Predictor features").options
    widget(page.checkbox, "Allow sportsbook spread and total inputs").check().run()
    assert any("Market-assisted" in item.value for item in page.warning)
    assert len(sources) == 1
    def fail(*args):
        raise ValueError("Insufficient fixture training data")
    monkeypatch.setattr(builder, "run_experiment", fail)
    widget(page.button, "Run experiment").click().run()
    assert not page.exception
    assert len(page.session_state["model_builder_experiments"]) == 1
    assert any("Insufficient fixture" in item.value for item in page.error)


def test_navigation_registers_both_pages_in_renamed_group():
    source = (ROOT / "app/app.py").read_text()
    assert '"Model Performance": [' in source
    assert '"Betting": [' not in source
    for name in ["predictive_performance", "model_builder", "best_bets", "betting_history"]:
        assert f'pages/{name}.py' in source

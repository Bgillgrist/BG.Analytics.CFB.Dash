"""Streamlit interaction smoke tests; require the dashboard dependencies."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from utils import predictions


def widget(elements, label):
    return next(element for element in elements if element.label == label)


@pytest.fixture
def page(monkeypatch):
    runs = pd.DataFrame([
        dict(season_prediction_run_id=identifier, season=2026, run_date=day,
             run_type="nightly", status="success", created_at=f"{day}T10:00:00Z",
             completed_at=f"{day}T12:00:00Z", simulations=10000, model_version=version)
        for identifier, day, version in [("current", "2026-09-07", "v2"),
                                         ("previous", "2026-09-06", "v2"),
                                         ("week", "2026-08-31", "v1")]
    ])

    def snapshot(identifier):
        records = []
        for i, (name, conference) in enumerate([("Alpha", "SEC"), ("Bravo", "SEC"), ("Independent", "FBS Independents")]):
            records.append(dict(team=name, conference=conference, season=2026, classification="fbs",
                                projected_wins=10-i, projected_losses=2+i,
                                playoff_prob=(.8-i*.2) if identifier == "current" else (.7-i*.1),
                                conference_champion_prob=.7-i*.4, national_champion_prob=.2-i*.05,
                                **{column: (1.0 if index == 10-i else 0.0)
                                   for index, column in enumerate(predictions.WIN_BUCKETS)}))
        return predictions.prepare_snapshot(pd.DataFrame(records))

    monkeypatch.setattr(predictions, "load_runs", lambda: runs)
    monkeypatch.setattr(predictions, "load_snapshot", snapshot)
    return AppTest.from_file(str(ROOT / "app/pages/predictions.py"), default_timeout=20)


def test_default_page_tabs_and_sort(page):
    page.run()
    assert not page.exception
    assert [tab.label for tab in page.tabs] == ["Team Predictions", "Conference Races", "Changes"]
    assert page.dataframe[0].value["team"].tolist() == ["Alpha", "Bravo", "Independent"]
    assert not page.get("download_button")
    assert widget(page.date_input, "Compare with date").value == date(2026, 9, 6)


def test_filters_and_sort_do_not_change_conference_totals(page):
    page.run()
    summary = page.dataframe[1].value.copy()
    widget(page.multiselect, "Conferences").set_value(["SEC"]).run()
    assert page.dataframe[0].value["team"].tolist() == ["Alpha", "Bravo"]
    pd.testing.assert_frame_equal(page.dataframe[1].value, summary)
    widget(page.selectbox, "Direction").select("Ascending").run()
    assert page.dataframe[0].value["team"].tolist() == ["Bravo", "Alpha"]
    widget(page.selectbox, "Numeric filter").select("playoff_prob").run()
    widget(page.number_input, "Minimum").set_value(90.0).run()
    assert any("No teams match" in message.value for message in page.info)
    assert not page.exception


def test_presets_distribution_and_independents(page):
    page.run()
    for preset in predictions.PRESETS:
        widget(page.selectbox, "Column preset").select(preset).run()
        assert not page.exception
        assert page.dataframe[0].value.columns.tolist() == ["team", "conference", *predictions.PRESETS[preset]]
        if preset == "Win Outlook":
            assert widget(page.selectbox, "Distribution team").value == "Alpha"
    widget(page.selectbox, "Explore a conference").select("FBS Independents").run()
    assert any("do not apply to independents" in message.value for message in page.info)
    assert not page.exception


def test_calendar_comparison_discloses_actual_snapshot_date_and_model_change(page):
    page.run()
    widget(page.date_input, "Compare with date").set_value(date(2026, 9, 2)).run()
    assert any("model version changed" in message.value for message in page.info)
    assert any("Aug 31, 2026" in caption.value for caption in page.caption)
    assert any("Requested date: Sep 02, 2026" in caption.value for caption in page.caption)
    assert not page.exception


def test_missing_snapshots_and_connection_errors(page, monkeypatch):
    monkeypatch.setattr(predictions, "load_runs", lambda: pd.DataFrame())
    page.run()
    assert any("No successful season prediction" in message.value for message in page.info)
    assert not page.exception

    def unavailable():
        raise ConnectionError("database unavailable")

    monkeypatch.setattr(predictions, "load_runs", unavailable)
    page.run()
    assert any("could not be loaded" in message.value for message in page.error)
    assert not page.exception

"""Streamlit interactions with deterministic poll, ratings, and blend snapshots."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

st = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from utils import db
from utils.rankings_analysis import blend_rating_snapshot


def widget(elements, label):
    return next(element for element in elements if element.label == label)


def ratings(day):
    rows = []
    for i in range(1, 36):
        value = 35. - i
        if day.day >= 7 and i == 30:
            value = 30.5
        rows.append(dict(team=f"Team {i:02}", rank=i, power_rating=value, hfa=2.5,
                         completed_at=pd.Timestamp(day, tz="UTC"), run_date=day, model_version="test-model",
                         team_rating_run_id=str(day), margin_source="completed", completed_games=2, projected_games=10))
    return pd.DataFrame(rows)


def teamrankings(day):
    return pd.DataFrame([dict(team=f"Team {i:02}", teamrankings_rank=i,
                              teamrankings_rating=float(i if day.day >= 7 else 36 - i),
                              teamrankings_pull_date=day) for i in range(1, 36)])


@pytest.fixture
def page(monkeypatch):
    st.cache_data.clear()
    calls, state = [], {"missing_poll": False, "history_error": False}
    days = [date(2026, 9, 1), date(2026, 9, 3), date(2026, 9, 7)]
    tables = {
        "team_map": {"Id", "Logo"},
        "game_data": {"season", "hometeam", "awayteam", "homepoints", "awaypoints", "startdate"},
        "team_rating_runs": {"season", "status", "team_rating_run_id", "completed_at", "created_at", "run_date", "model_version", "home_field_advantage", "margin_source"},
        "team_ratings": {"team", "rank", "power_rating", "team_rating_run_id", "completed_games", "projected_games"},
        "teamrankings_predictive_ratings": {"season", "pull_date", "team", "rating"},
    }

    def read(sql, params=None):
        query = " ".join(sql.split())
        params = params or {}
        calls.append((query, params.copy()))
        if "information_schema.columns" in query:
            return pd.DataFrame({"column_name": sorted(tables.get(params["table_name"], set()))})
        if "SELECT DISTINCT poll" in query:
            return pd.DataFrame({"poll": ["AP Top 25", "Coaches Poll"]})
        if "FROM public.rankings" in query:
            if "SELECT DISTINCT season" in query:
                return pd.DataFrame({"season": [2026, 2025]})
            if "SELECT DISTINCT week" in query:
                return pd.DataFrame({"week": [1, 2]})
            if state["missing_poll"]:
                return pd.DataFrame(columns=["team", "rank"])
            names = list(range(1, 26)) if params["week"] == 1 else [30, *range(2, 26)]
            return pd.DataFrame({"team": [f"Team {i:02}" for i in names], "rank": list(range(1, 26))})
        if "WITH team_rows AS" in query:
            return pd.DataFrame({"team": [f"Team {i:02}" for i in range(1, 36)], "team_id": [str(i) for i in range(1, 36)], "logo": [None] * 35})
        if "GROUP BY" in query and "FROM public.team_rating_runs" in query:
            return pd.DataFrame({"completed_date": days})
        if "JOIN public.team_ratings" in query:
            day = max(day for day in days if day <= params["completed_date"])
            if state["history_error"] and day < days[-1]:
                raise ConnectionError("Comparison unavailable")
            return ratings(day)
        if "FROM public.teamrankings_predictive_ratings" in query:
            return teamrankings(params["as_of_date"])
        if "FROM public.game_data" in query and "SELECT DISTINCT season" in query:
            return pd.DataFrame({"season": [2026, 2025]})
        if "WITH games AS" in query:
            return pd.DataFrame(columns=["team", "opponent", "location", "game_date"])
        if "FROM public.game_data g" in query:
            return pd.DataFrame([dict(id=1, hometeam="Team 01", awayteam="Team 02", homepoints=30, awaypoints=20,
                                     predicted_home_margin=None, homewinprob=None, homeclassification="fbs", awayclassification="fbs")])
        raise AssertionError(f"Unexpected query: {query}")

    monkeypatch.setattr(db, "read_df", read)
    yield AppTest.from_file(str(ROOT / "app/pages/team_rankings.py"), default_timeout=20), calls, state
    st.cache_data.clear()


def markdown(app):
    return "\n".join(element.value for element in app.markdown)


def test_analysis_replaces_exports_and_defaults_to_previous_ratings_day(page):
    app, calls, _ = page
    app.run()
    assert not app.exception
    assert {"Rankings Analysis", "Top 25 agreement", "Bubble watch", "Movement"}.issubset({element.value for element in app.subheader})
    assert [tab.label for tab in app.tabs] == ["Poll", "Ratings"]
    assert "Most overrated by the poll" in markdown(app)
    assert "Most underrated by the poll" in markdown(app)
    assert widget(app.date_input, "Compare ratings with date").value == date(2026, 9, 3)
    assert not app.get("download_button")
    assert not app.get("imgs")
    assert not any(element.label == "Posting export" for element in app.expander)
    assert any(params.get("week") == 1 for query, params in calls if "FROM public.rankings" in query)


def test_date_fallback_uses_actual_dates_for_both_teamrankings_snapshots(page):
    app, calls, _ = page
    app.run()
    widget(app.date_input, "Compare ratings with date").set_value(date(2026, 9, 2)).run()
    assert not app.exception
    assert any("Comparison: Sep 1, 2026" in element.value and "Requested comparison: Sep 2, 2026" in element.value for element in app.caption)
    cutoffs = [params["as_of_date"] for query, params in calls if "FROM public.teamrankings_predictive_ratings" in query]
    assert date(2026, 9, 1) in cutoffs
    assert date(2026, 9, 2) not in cutoffs
    widget(app.date_input, "Ratings As Of").set_value(date(2026, 9, 6)).run()
    assert not app.exception
    assert any("Current: Sep 3, 2026" in element.value for element in app.caption)
    assert widget(app.date_input, "Compare ratings with date").value == date(2026, 9, 2)
    assert not any(params.get("as_of_date") == date(2026, 9, 6) for query, params in calls if "FROM public.teamrankings_predictive_ratings" in query)


def test_current_date_change_resets_invalid_saved_comparison(page):
    app, _, _ = page
    app.run()
    widget(app.date_input, "Compare ratings with date").set_value(date(2026, 9, 6)).run()
    widget(app.date_input, "Ratings As Of").set_value(date(2026, 9, 3)).run()
    assert not app.exception
    assert widget(app.date_input, "Compare ratings with date").value == date(2026, 9, 1)


def test_blend_control_recomputes_both_snapshots_with_same_percentage(page):
    app, _, _ = page
    app.run()
    for weight in (0., 1.):
        widget(app.slider, "TeamRankings Blend").set_value(weight).run()
        assert not app.exception
        before = blend_rating_snapshot(ratings(date(2026, 9, 3)), teamrankings(date(2026, 9, 3)), weight).set_index("team")
        now = blend_rating_snapshot(ratings(date(2026, 9, 7)), teamrankings(date(2026, 9, 7)), weight).set_index("team")
        name = "Team 30" if weight == 0 else "Team 35"
        old_rating, new_rating = before.loc[name, "power_rating"], now.loc[name, "power_rating"]
        assert f"Rating {old_rating:.1f} → {new_rating:.1f} ({new_rating - old_rating:+.1f})" in markdown(app)
        assert any(f"selected {weight:.0%} TeamRankings blend" in element.value for element in app.caption)


def test_no_history_preserves_current_analysis(page):
    app, _, _ = page
    app.run()
    widget(app.date_input, "Ratings As Of").set_value(date(2026, 9, 1)).run()
    widget(app.selectbox, "Poll Week").select(1).run()
    assert not app.exception
    assert "Most overrated by the poll" in markdown(app)
    assert any("No earlier saved ratings date" in element.value for element in app.info)
    assert any("No earlier week" in element.value for element in app.info)


def test_different_seasons_disable_cross_source_analysis_but_keep_trends(page):
    app, _, _ = page
    app.run()
    widget(app.selectbox, "Power Rating Season").select(2025).run()
    assert not app.exception
    assert "Most overrated by the poll" not in markdown(app)
    assert any("Select matching" in element.value for element in app.info)
    assert any("2025 and earlier" in element.value for element in app.info)
    assert [tab.label for tab in app.tabs] == ["Poll", "Ratings"]


def test_missing_history_and_poll_are_local_empty_states(page):
    app, _, state = page
    state["history_error"] = True
    state["missing_poll"] = True
    app.run()
    assert not app.exception
    assert any("comparison ratings could not be loaded" in element.value for element in app.info)
    assert "Most overrated by the poll" not in markdown(app)
    assert "Just outside the ratings’ Top 25" in markdown(app)

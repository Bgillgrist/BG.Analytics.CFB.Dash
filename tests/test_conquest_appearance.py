"""Alternate asset selection, fallbacks, and map-rule persistence."""

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from utils.conquest_appearance import apply_team_appearance


def team_assets():
    return pd.DataFrame([
        dict(team="UCLA", team_key="ucla", team_color="#111111", team_secondary_color="#aaaaaa",
             team_logo="https://example.com/ucla.png", team_logo_dark="https://example.com/ucla-dark.png"),
        dict(team="Mississippi State", team_key="mississippi state", team_color="#222222", team_secondary_color="#bbbbbb",
             team_logo="https://example.com/ms.png", team_logo_dark="https://example.com/ms-dark.png"),
        dict(team="Boise State", team_key="boise state", team_color="#333333", team_secondary_color="#cccccc",
             team_logo="https://example.com/boise.png", team_logo_dark="https://example.com/boise-dark.png"),
        dict(team="Primary Only", team_key="primary only", team_color="#444444", team_secondary_color=None,
             team_logo="https://example.com/primary.png", team_logo_dark=None),
    ])


def test_defaults_preserve_existing_map_and_explicit_empty_restores_primary_assets():
    original = team_assets()
    defaults = apply_team_appearance(original)
    assert defaults.team_color.tolist() == ["#aaaaaa", "#bbbbbb", "#333333", "#444444"]
    assert defaults.iloc[0].team_logo.endswith("ucla-dark.png")
    primary = apply_team_appearance(original, [], [])
    assert primary.team_color.tolist() == original.team_color.tolist()
    assert primary.team_logo.tolist() == original.team_logo.tolist()
    pd.testing.assert_frame_equal(original, team_assets())


def test_color_and_logo_choices_are_independent():
    result = apply_team_appearance(team_assets(), ["boise state"], ["ucla"])
    assert result.team_color.tolist() == ["#111111", "#222222", "#cccccc", "#444444"]
    assert result.iloc[0].team_logo.endswith("ucla-dark.png")
    assert result.iloc[2].team_logo.endswith("boise.png")
    assert result.iloc[0].team_logo_dark.endswith("ucla.png")


@pytest.mark.parametrize("missing", [None, float("nan"), "", "  ", "null", "None"])
def test_missing_alternates_fall_back_to_primary(missing):
    original = team_assets().iloc[[0]].copy()
    original["team_secondary_color"] = missing
    original["team_logo_dark"] = missing
    result = apply_team_appearance(original, ["ucla"], ["ucla"])
    assert result.iloc[0].team_color == "#111111"
    assert result.iloc[0].team_logo.endswith("ucla.png")


def test_missing_primary_logo_falls_back_to_available_alternate():
    original = team_assets().iloc[[0]].copy()
    original["team_logo"] = None
    result = apply_team_appearance(original, [], [])
    assert result.iloc[0].team_logo.endswith("ucla-dark.png")


@pytest.fixture
def map_page(monkeypatch):
    st = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    import streamlit.components.v1 as components
    from utils import db, conquest_slides

    st.cache_data.clear()
    assets = team_assets()
    team_map = assets.rename(columns={"team": "cfb_name", "team_color": "Color",
                                     "team_secondary_color": "SecondaryColor", "team_logo": "Logo",
                                     "team_logo_dark": "DarkLogo"})
    team_map["Id"] = ["1", "2", "3", "4"]
    team_map["VenueId"] = ["11", "12", "13", "14"]
    conferences = ["Big Ten", "SEC", "Mountain West", "ACC"]

    def read_df(sql, params=None):
        if "information_schema" in sql:
            return pd.DataFrame(columns=["column_name"])
        if "SELECT DISTINCT season" in sql:
            return pd.DataFrame({"season": [2026, 2025]})
        if "public.team_map" in sql:
            return team_map.copy()
        if "public.venue_map" in sql:
            return pd.DataFrame({"Id": ["11", "12", "13", "14"], "Latitude": [34., 33., 43., 36.],
                                 "Longitude": [-118., -88., -116., -80.], "Name": ["One", "Two", "Three", "Four"]})
        if "public.game_data" in sql:
            records = []
            for week, home, away in [(1, 0, 1), (2, 2, 0), (3, 3, 1)]:
                records.append(dict(id=week, season=params["season"], week=week, seasontype="regular",
                    homeid=str(home + 1), awayid=str(away + 1), hometeam=assets.iloc[home].team,
                    awayteam=assets.iloc[away].team, homeconference=conferences[home], awayconference=conferences[away],
                    homeclassification="fbs", awayclassification="fbs", venueid=str(home + 11),
                    neutralsite=False, startdate=f"2026-09-{week * 7:02}T16:00:00Z", homepoints=28, awaypoints=14))
            return pd.DataFrame(records)
        raise AssertionError(f"Unexpected query: {sql}")

    rendered = []
    monkeypatch.setattr(db, "read_df", read_df)
    monkeypatch.setattr(conquest_slides, "embed_conquest_logos", lambda seeds: None)
    monkeypatch.setattr(components, "html", lambda markup, **kwargs: rendered.append(markup))
    if hasattr(st, "iframe"):
        monkeypatch.setattr(st, "iframe", lambda markup, **kwargs: rendered.append(markup))
    yield AppTest.from_file(str(ROOT / "app/pages/schedule_analysis.py"), default_timeout=20), rendered
    st.cache_data.clear()


def seeds(rendered):
    return json.loads(re.search(r"const seeds = (.*);", rendered[-1]).group(1))


def test_page_defaults_and_both_selectors_follow_map_rules(map_page):
    page, rendered = map_page
    page.run()
    assert not page.exception
    assert page.multiselect(key="_conquest_alternate_colors").value == ["mississippi state", "ucla"]
    assert page.multiselect(key="_conquest_alternate_logos").value == ["boise state", "mississippi state", "ucla"]
    page.radio(key="conquest_territory_mode").set_value("Team").run()
    ucla = next(seed for seed in seeds(rendered) if seed["ownerTeam"] == "UCLA")
    assert ucla["color"] == "#aaaaaa"
    assert ucla["logo"].endswith("ucla-dark.png")
    assert ucla["ownerLogo"] == ucla["logo"]
    elements = list(page.main)
    labels = [getattr(element, "label", None) for element in elements]
    assert labels.index("Conquest Map Week") < labels.index("Use alternate color for")
    assert labels.index("Conquest Map Week") < labels.index("Use alternate logo for")


def test_edits_preserve_rules_and_apply_to_promoted_owner_and_slides(map_page):
    page, rendered = map_page
    page.run()
    page.radio(key="conquest_map_scope").set_value("P4 + Promotions").run()
    page.radio(key="conquest_territory_mode").set_value("Team").run()
    page.select_slider[0].set_value("Week 3").run()
    original_ownership = [(row["seedTeamId"], row["ownerTeamId"], row["history"]) for row in seeds(rendered)]
    page.multiselect(key="_conquest_alternate_colors").set_value(["boise state"]).run()
    page.multiselect(key="_conquest_alternate_logos").set_value([]).run()
    assert not page.exception
    assert page.radio(key="conquest_map_scope").value == "P4 + Promotions"
    assert page.radio(key="conquest_territory_mode").value == "Team"
    assert page.select_slider[0].value == "Week 3"
    updated = seeds(rendered)
    assert [(row["seedTeamId"], row["ownerTeamId"], row["history"]) for row in updated] == original_ownership
    promoted = next(row for row in updated if row["ownerTeamId"] == "boise state")
    assert promoted["color"] == promoted["ownerColor"] == "#cccccc"
    assert promoted["logo"].endswith("boise.png")
    assert promoted["ownerLogo"] == promoted["logo"]
    assert promoted["logoFallback"].endswith("boise-dark.png")


def test_preferences_survive_scope_mode_week_and_season_changes(map_page):
    page, rendered = map_page
    page.run()
    page.multiselect(key="_conquest_alternate_colors").set_value([]).run()
    page.multiselect(key="_conquest_alternate_logos").set_value(["ucla"]).run()
    page.radio(key="conquest_map_scope").set_value("G6 + UConn").run()
    page.radio(key="conquest_territory_mode").set_value("Team").run()
    page.select_slider[0].set_value("After Season").run()
    next(element for element in page.selectbox if element.label == "Season").select(2025).run()
    page.radio(key="conquest_map_scope").set_value("All Teams / Conferences").run()
    assert not page.exception
    assert page.multiselect(key="_conquest_alternate_colors").value == []
    assert page.multiselect(key="_conquest_alternate_logos").value == ["ucla"]
    page.select_slider[0].set_value("Before Season").run()
    ucla = next(row for row in seeds(rendered) if row["ownerTeamId"] == "ucla")
    assert ucla["color"] == "#111111"
    assert ucla["logo"].endswith("ucla-dark.png")

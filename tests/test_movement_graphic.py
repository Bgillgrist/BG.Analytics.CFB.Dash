"""Graphics must reflect the same shortlists and rank semantics as the page."""

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils import movement_graphic
from utils.rankings_analysis import build_rank_movements, movement_shortlists


@pytest.fixture
def embedded(monkeypatch):
    seen = []

    class Helpers:
        def embed_conquest_logos(self, rows):
            seen.extend(row.copy() for row in rows)
            for row in rows:
                if row["logo"]:
                    row["logo"] = "data:image/png;base64,embedded"

    monkeypatch.setattr(movement_graphic, "load_slide_helpers", lambda: Helpers())
    return seen


def graphic(current, previous, *, poll=False, **labels):
    movement = build_rank_movements(pd.DataFrame(current), pd.DataFrame(previous), poll=poll)
    risers, fallers = movement_shortlists(movement)
    markup = movement_graphic.movement_graphic_controls(
        risers, fallers, poll=poll, season=2026, source_label=labels.get("source", "AP Top 25"),
        comparison_label=labels.get("comparison", "Week 1 → Week 2"),
        blend_label=labels.get("blend", ""),
    )
    return json.loads(re.search(r"const config = (.*);", markup).group(1))


def team(name, rank, rating=None, logo="https://example.com/logo.png"):
    return dict(team=name, rank=rank, power_rating=rating, logo=logo)


def test_poll_graphic_uses_exact_ranks_and_excludes_new_or_dropped_teams(embedded):
    result = graphic(
        [team("Up", 3), team("Down", 24), team("New", 10)],
        [team("Up", 8), team("Down", 6), team("Dropped", 25)], poll=True,
    )
    assert [r["name"] for r in result["risers"]] == ["Up"]
    assert [r["name"] for r in result["fallers"]] == ["Down"]
    assert result["risers"][0]["change"] == 5
    assert result["fallers"][0]["change"] == -18
    assert result["fallers"][0]["previousRank"] == 6
    assert result["fallers"][0]["currentRank"] == 24
    assert all(r["previousRating"] is None for r in result["risers"] + result["fallers"])
    assert result["risers"][0]["logo"].startswith("data:image/png;")
    assert len(embedded) == 2


def test_ratings_graphic_uses_full_fbs_ranks_ratings_and_actual_comparison_metadata(embedded):
    result = graphic(
        [team("Riser", 40, 65.2), team("Faller", 98, 22.4)],
        [team("Riser", 100, 19.1), team("Faller", 30, 70.5)],
        source="BG Power Ratings", comparison="Sep 3, 2026 → Sep 10, 2026", blend="TeamRankings blend: 25%",
    )
    assert result["source"] == "BG Power Ratings"
    assert result["comparison"] == "Sep 3, 2026 → Sep 10, 2026"
    assert result["blend"] == "TeamRankings blend: 25%"
    assert result["risers"][0]["change"] == 60
    assert result["risers"][0]["currentRating"] == 65.2
    assert result["fallers"][0]["previousRating"] == 70.5


def test_previous_logo_is_available_as_fallback(embedded):
    graphic([team("Up", 1, logo=None)], [team("Up", 8, logo="old-logo")], poll=True)
    assert embedded[0]["logo"] == "old-logo"
    assert embedded[0]["logoFallback"] == "old-logo"


def test_no_movement_produces_empty_categories_without_network_requests(embedded):
    result = graphic([team("Same", 3)], [team("Same", 3)], poll=True)
    assert result["risers"] == result["fallers"] == []
    assert embedded == []


def test_labels_cannot_break_inline_script_and_missing_ratings_are_json_null(embedded):
    source = '</script><img src=x onerror="alert(1)">'
    result = graphic([team("Up", 1)], [team("Up", 2)], source=source)
    assert result["source"] == source
    assert result["risers"][0]["currentRating"] is None


def test_graphic_preserves_page_shortlist_tie_order_and_limit(embedded):
    current = [team(name, i + 1) for i, name in enumerate("ABCDEFG")]
    previous = [team(name, i + 11) for i, name in enumerate("ABCDEFG")]
    result = graphic(current, previous)
    assert [r["name"] for r in result["risers"]] == list("ABCDE")

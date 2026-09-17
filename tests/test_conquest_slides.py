"""Slide captions must describe the selected conquest ownership rules."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils.conquest_slides import conquest_slide_controls


def slide_config(scope, label="2026 | Week 3"):
    markup = conquest_slide_controls(scope, label)
    return json.loads(re.search(r"const config = (.*);", markup).group(1))


@pytest.mark.parametrize(
    "scope,initial_teams,promotions",
    [
        ("Power 4 + Notre Dame", "Power 4 schools and Notre Dame", False),
        ("P4 + Promotions", "Power 4 schools and Notre Dame", True),
        ("G6 + UConn", "G6 schools and UConn", False),
        ("All Teams / Conferences", "All FBS schools", False),
    ],
)
def test_rules_match_ownership_scope(scope, initial_teams, promotions):
    config = slide_config(scope)
    assert config["rules"][0].startswith(initial_teams)
    assert len(config["rules"]) == 4
    assert ("even outside the Power 4" in config["rules"][2]) is promotions
    if not promotions:
        assert "Only games between schools in the selected map scope" in config["rules"][2]


def test_checkpoint_and_mode_are_preserved_in_slide_caption():
    label = "2026 | P4 + Promotions | Week 4 | Conference territory map"
    assert slide_config("P4 + Promotions", label)["source"] == label


def test_caption_cannot_insert_html_or_terminate_script():
    label = '</script><img src=x onerror="alert(1)"> & __CONQUEST_SLIDE_CONFIG__'
    markup = conquest_slide_controls("P4 + Promotions", label)
    assert label not in markup
    assert slide_config("P4 + Promotions", label)["source"] == label

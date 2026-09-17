"""Reproduce mixed imported-helper/page versions during a running deployment."""

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils import conquest_slide_runtime, conquest_slides


def test_stale_two_argument_helper_is_reloaded_before_page_calls_it():
    def previous_helper(map_scope, source_label):
        return "previous slide markup"

    try:
        conquest_slides.conquest_slide_controls = previous_helper
        del conquest_slides.SLIDE_API_VERSION
        # This is the argument-binding failure shown in the reported traceback.
        with pytest.raises(TypeError, match="positional arguments"):
            conquest_slides.conquest_slide_controls("P4 + Promotions", 2026, "Week 3")

        helpers = conquest_slide_runtime.load_slide_helpers()
        markup = helpers.conquest_slide_controls("P4 + Promotions", 2026, "Week 3")
        config = json.loads(re.search(r"const config = (.*);", markup).group(1))
        assert config["season"] == "2026"
        assert config["week"] == "Week 3"
        assert len(config["countyLandAreaM2"]) == 3142
        assert 'id="slide-image-2"' in markup
        assert "__CONQUEST_RANKING_HELPERS__" not in markup
    finally:
        importlib.reload(conquest_slides)


def test_current_helper_is_not_reloaded_and_keeps_logo_cache(monkeypatch):
    def unexpected_reload(module):
        pytest.fail("Normal reruns must not reload the module or clear cached logos")

    monkeypatch.setattr(conquest_slide_runtime, "reload", unexpected_reload)
    original_logo_loader = conquest_slides._logo_data_url
    helpers = conquest_slide_runtime.load_slide_helpers()
    assert helpers is conquest_slides
    assert helpers._logo_data_url is original_logo_loader


def test_incomplete_deployment_reports_actionable_error(monkeypatch):
    class OldModule:
        pass

    monkeypatch.setattr(conquest_slide_runtime, "import_module", lambda name: OldModule())
    monkeypatch.setattr(conquest_slide_runtime, "reload", lambda module: module)
    with pytest.raises(RuntimeError, match="Deploy app/utils/conquest_slides.py"):
        conquest_slide_runtime.load_slide_helpers()

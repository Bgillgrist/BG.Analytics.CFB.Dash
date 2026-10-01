"""Regression coverage for stale scoring imports in a running Streamlit app."""

import importlib
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils import weekly_performances, weekly_performances_runtime


def test_old_module_is_reloaded_before_importing_new_names():
    def old_grade_builder(frame, season_stats, game_stats):
        return "old grades"

    try:
        del weekly_performances.GRADE_CONTEXT_COLUMNS
        del weekly_performances.WEEKLY_API_VERSION
        weekly_performances.build_grade_comparison = old_grade_builder
        # Reproduce the exact import failure from the production traceback.
        with pytest.raises(ImportError, match="GRADE_CONTEXT_COLUMNS"):
            exec("from utils.weekly_performances import GRADE_CONTEXT_COLUMNS", {})

        helpers = weekly_performances_runtime.load_weekly_helpers()
        assert helpers is weekly_performances
        assert helpers.WEEKLY_API_VERSION == 2
        assert "peer_group" in helpers.GRADE_CONTEXT_COLUMNS
        assert "mode" in inspect.signature(helpers.build_grade_comparison).parameters
        assert helpers.build_grade_comparison is not old_grade_builder
    finally:
        importlib.reload(weekly_performances)


def test_current_module_is_not_reloaded_on_normal_page_reruns(monkeypatch):
    def unexpected_reload(module):
        pytest.fail("A current helper must not be reloaded on ordinary reruns")

    monkeypatch.setattr(weekly_performances_runtime, "reload", unexpected_reload)
    original_builder = weekly_performances.build_grade_comparison
    assert weekly_performances_runtime.load_weekly_helpers() is weekly_performances
    assert weekly_performances.build_grade_comparison is original_builder


def test_incomplete_deployment_explains_how_to_recover(monkeypatch):
    class OldModule:
        WEEKLY_API_VERSION = 1

    monkeypatch.setattr(weekly_performances_runtime, "import_module", lambda name: OldModule())
    monkeypatch.setattr(weekly_performances_runtime, "reload", lambda module: module)
    with pytest.raises(RuntimeError, match="Deploy app/utils/weekly_performances.py"):
        weekly_performances_runtime.load_weekly_helpers()

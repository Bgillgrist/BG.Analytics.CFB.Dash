"""Reproduce stale Streamlit imports after the quadrant-label deployment."""
import importlib
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from utils import scatterplot, scatterplot_runtime


def test_stale_module_reloads_before_page_uses_layout_key():
    def old_builder(points, *, title):
        return 'old graphic'

    try:
        del scatterplot.SCATTERPLOT_API_VERSION
        del scatterplot.load_season_week_scope
        scatterplot.graphic_config = old_builder
        with pytest.raises(TypeError, match='layout_key'):
            scatterplot.graphic_config([], title='Test', layout_key='test')
        helpers = scatterplot_runtime.load_scatterplot_helpers()
        assert helpers is scatterplot
        assert helpers.SCATTERPLOT_API_VERSION == 2
        assert 'layout_key' in inspect.signature(helpers.graphic_config).parameters
        assert callable(helpers.load_season_week_scope)
        assert helpers.graphic_config is not old_builder
    finally:
        importlib.reload(scatterplot)


def test_current_helper_is_not_reloaded(monkeypatch):
    def unexpected_reload(module):
        pytest.fail('Current helpers should not be reloaded on normal page reruns')
    monkeypatch.setattr(scatterplot_runtime, 'reload', unexpected_reload)
    assert scatterplot_runtime.load_scatterplot_helpers() is scatterplot


def test_incomplete_deployment_shows_recovery_message(monkeypatch):
    old = SimpleNamespace(SCATTERPLOT_API_VERSION=2, graphic_config=lambda points: None)
    monkeypatch.setattr(scatterplot_runtime, 'import_module', lambda name: old)
    monkeypatch.setattr(scatterplot_runtime, 'reload', lambda module: module)
    with pytest.raises(RuntimeError, match='Deploy app/utils/scatterplot.py'):
        scatterplot_runtime.load_scatterplot_helpers()

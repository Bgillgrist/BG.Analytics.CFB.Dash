"""Keep scatterplot pages and imported helpers compatible across live updates."""

from importlib import import_module, reload
from inspect import signature
from types import ModuleType


def _compatible(helpers):
    builder = getattr(helpers, 'graphic_config', None)
    return (
        getattr(helpers, 'SCATTERPLOT_API_VERSION', None) == 2
        and callable(builder)
        and 'layout_key' in signature(builder).parameters
        and callable(getattr(helpers, 'load_season_week_scope', None))
    )


def load_scatterplot_helpers() -> ModuleType:
    helpers = import_module('utils.scatterplot')
    # Streamlit can execute a new page while keeping an older helper module.
    # Reload only a mismatched helper, as on the weekly and conquest pages.
    if not _compatible(helpers):
        helpers = reload(helpers)
    if not _compatible(helpers):
        raise RuntimeError(
            'The scatterplot page and graphics helper are from different app versions. '
            'Deploy app/utils/scatterplot.py with the updated page, then reboot the app.'
        )
    return helpers

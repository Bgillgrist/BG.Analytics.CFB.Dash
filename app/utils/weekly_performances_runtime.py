"""Keep the weekly page and imported scoring helpers compatible after updates."""

from importlib import import_module, reload
from types import ModuleType


def load_weekly_helpers() -> ModuleType:
    helpers = import_module("utils.weekly_performances")
    # Streamlit may rerun an updated page while retaining the old helper in
    # sys.modules. Reload only on a version mismatch, before importing names.
    if getattr(helpers, "WEEKLY_API_VERSION", None) != 2:
        helpers = reload(helpers)
    if getattr(helpers, "WEEKLY_API_VERSION", None) != 2:
        raise RuntimeError(
            "The weekly page and scoring helper are from different app versions. "
            "Deploy app/utils/weekly_performances.py with the updated page, then reboot the app."
        )
    return helpers

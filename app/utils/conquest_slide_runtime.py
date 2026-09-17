"""Keep the map page and its imported slide helpers compatible after updates."""

from importlib import import_module, reload
from types import ModuleType


def load_slide_helpers() -> ModuleType:
    helpers = import_module("utils.conquest_slides")
    # A running Streamlit session can retain the old two-argument helper while
    # the page has already changed to (scope, season, checkpoint). Reload only
    # a mismatched module, preserving the logo cache on ordinary page reruns.
    if getattr(helpers, "SLIDE_API_VERSION", None) != 3:
        helpers = reload(helpers)
    if getattr(helpers, "SLIDE_API_VERSION", None) != 3:
        raise RuntimeError(
            "The conquest page and slide helper are from different app versions. "
            "Deploy app/utils/conquest_slides.py with the updated page, then reboot the app."
        )
    return helpers

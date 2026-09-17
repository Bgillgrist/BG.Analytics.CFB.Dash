"""Copyable carousel slides generated in the live map's browser frame."""

import base64
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

from PIL import Image


@lru_cache(maxsize=512)
def _logo_data_url(url: str) -> str:
    """Cache successful, full-resolution images only; failed requests can retry."""
    if not url.startswith(("https://", "http://")):
        raise ValueError("Unsupported logo URL")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=8) as response:
        payload = response.read()
    # Reject error pages returned with HTTP 200, and normalize other raster formats
    # to PNG without resizing. Existing PNG bytes are preserved exactly.
    with Image.open(BytesIO(payload)) as image:
        image.load()
        if image.format != "PNG":
            output = BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            payload = output.getvalue()
    return "data:image/png;base64," + base64.b64encode(payload).decode("ascii")


def embed_conquest_logos(seeds: list[dict]) -> None:
    """Inline map logos so PNG generation does not depend on browser CORS access.

    Try the normal logo when a preferred dark logo fails. If both fail, keep the
    original URL for the live map and a browser retry with a specific error.
    """
    choices = {
        (seed.get("logo", ""), seed.get("logoFallback", ""))
        for seed in seeds if seed.get("logo") and not seed["logo"].startswith("data:")
    }
    if not choices:
        return

    def load_choice(choice: tuple[str, str]) -> tuple[tuple[str, str], str]:
        for url in dict.fromkeys(choice):
            if not url:
                continue
            try:
                return choice, _logo_data_url(url)
            except (OSError, ValueError) as error:
                logging.getLogger(__name__).warning("Conquest logo unavailable: %s (%s)", url, error)
        return choice, choice[0]

    with ThreadPoolExecutor(max_workers=8) as executor:
        embedded = dict(executor.map(load_choice, choices))
    for seed in seeds:
        choice = (seed.get("logo", ""), seed.get("logoFallback", ""))
        if choice in embedded:
            seed["logo"] = embedded[choice]


def conquest_slide_controls(map_scope: str, source_label: str) -> str:
    if map_scope in {"Power 4 + Notre Dame", "P4 + Promotions"}:
        starting_rule = "Power 4 schools and Notre Dame start the season with the land around their school."
    elif map_scope == "G6 + UConn":
        starting_rule = "G6 schools and UConn start the season with the land around their school."
    else:
        starting_rule = "All FBS schools start the season with the land around their school."

    eligibility_rule = (
        "When a landowner loses to another FBS school, that school gets to claim its land, even outside the Power 4."
        if map_scope == "P4 + Promotions"
        else "Only games between schools in the selected map scope transfer land."
    )
    config = {
        "source": source_label,
        "rules": [
            starting_rule,
            "When a team loses a game, the team that beat them takes all the land they currently own.",
            eligibility_rule,
            "The team with the most land at the end of the season wins!",
        ],
    }
    # Prevent labels from terminating the inline script in the component document.
    config_json = json.dumps(config).replace("<", "\\u003c")
    template = Path(__file__).with_name("conquest_slides.html").read_text(encoding="utf-8")
    return template.replace("__CONQUEST_SLIDE_CONFIG__", config_json)

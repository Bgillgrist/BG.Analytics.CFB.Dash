"""Copyable carousel slides generated in the live map's browser frame."""

import json
from pathlib import Path


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

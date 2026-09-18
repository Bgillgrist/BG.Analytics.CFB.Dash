"""Instagram movement graphics using the same in-browser PNG workflow as maps."""

import json
import math
from pathlib import Path

import pandas as pd

from utils.conquest_slide_runtime import load_slide_helpers


def movement_graphic_controls(
    risers: pd.DataFrame,
    fallers: pd.DataFrame,
    *,
    season: int,
    source_label: str,
    comparison_label: str,
    poll: bool,
    blend_label: str = "",
) -> str:
    def text(value) -> str:
        return "" if pd.isna(value) else str(value)

    def number(value):
        return float(value) if pd.notna(value) and math.isfinite(float(value)) else None

    def rows(frame):
        result = []
        for row in frame.head(5).itertuples(index=False):
            result.append({
                "name": str(row.team),
                "logo": text(row.logo),
                "logoFallback": text(getattr(row, "previous_logo", "")),
                "previousRank": int(row.previous_rank),
                "currentRank": int(row.current_rank),
                "change": int(row.rank_change),
                "previousRating": None if poll else number(row.previous_power_rating),
                "currentRating": None if poll else number(row.current_power_rating),
            })
        return result

    config = {
        "season": str(season),
        "source": source_label,
        "comparison": comparison_label,
        "poll": poll,
        "blend": blend_label,
        "risers": rows(risers),
        "fallers": rows(fallers),
    }
    load_slide_helpers().embed_conquest_logos([*config["risers"], *config["fallers"]])
    encoded = json.dumps(config, allow_nan=False).replace("<", "\\u003c")
    template = Path(__file__).with_name("movement_graphic.html").read_text(encoding="utf-8")
    return template.replace("__MOVEMENT_CONFIG__", encoded)

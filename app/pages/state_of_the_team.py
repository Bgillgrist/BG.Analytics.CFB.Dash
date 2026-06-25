from __future__ import annotations

import html
import math
import re
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from utils.db import read_df


TRANSFER_TABLE = "transfer_portal"
SLIDE_W = 1080
SLIDE_H = 1350
APP_LOGO_COLOR_PATH = Path(__file__).resolve().parents[1] / "assets" / "logo_black.PNG"

POSITION_GROUP_ORDER = {
    "QB": 0,
    "RB": 1,
    "WR": 2,
    "TE": 3,
    "OL": 4,
    "DL": 5,
    "LB": 6,
    "DB": 7,
    "ST": 8,
    "OTHER": 9,
}
POSITION_DETAIL_ORDER = {
    "QB": ("QB",),
    "RB": ("RB", "FB", "HB"),
    "WR": ("WR",),
    "TE": ("TE",),
    "OL": ("OL", "OT", "LT", "RT", "IOL", "OG", "G", "LG", "RG", "C", "OC"),
    "DL": ("DL", "EDGE", "DE", "DT", "NT"),
    "LB": ("LB", "ILB", "MLB", "OLB"),
    "DB": ("DB", "CB", "S", "SAF", "FS", "SS", "NB"),
    "ST": ("ST", "K", "PK", "P", "LS"),
    "OTHER": ("ATH",),
}
POSITION_TO_GROUP = {
    position: group
    for group, positions in POSITION_DETAIL_ORDER.items()
    for position in positions
}
POSITION_IMPACT_WEIGHTS = {
    "QB": {"top_n": 2, "top_quality": 4.0, "avg_quality": 0.0, "depth": 0.0, "depth_cap": 2, "overflow_depth": 0.10},
    "RB": {"top_n": 1, "top_quality": 10.0, "avg_quality": 2.0, "depth": 0.05, "depth_cap": 3, "overflow_depth": 0.05},
    "WR": {"top_n": 6, "top_quality": 9.0, "avg_quality": 2.0, "depth": 0.10, "depth_cap": 8, "overflow_depth": 0.15},
    "TE": {"top_n": 3, "top_quality": 2.0, "avg_quality": 0.25, "depth": 0.10, "depth_cap": 2, "overflow_depth": 0.05},
    "OL": {"top_n": 2, "top_quality": 0.8, "avg_quality": 0.25, "depth": 2.0, "depth_cap": 10, "overflow_depth": 0.05},
    "DL": {"top_n": 3, "top_quality": 1.0, "avg_quality": 0.25, "depth": 0.25, "depth_cap": 6, "overflow_depth": 0.05},
    "LB": {"top_n": 1, "top_quality": 5.0, "avg_quality": 1.5, "depth": 0.25, "depth_cap": 4, "overflow_depth": 0.05},
    "DB": {"top_n": 3, "top_quality": 10.0, "avg_quality": 1.5, "depth": 0.25, "depth_cap": 6, "overflow_depth": 0.05},
    "ST": {"top_n": 1, "top_quality": 2.0, "avg_quality": 0.75, "depth": 0.45, "depth_cap": 2, "overflow_depth": 0.10},
    "OTHER": {"top_n": 1, "top_quality": 1.0, "avg_quality": 0.5, "depth": 0.60, "depth_cap": 3, "overflow_depth": 0.15},
}


st.markdown(
    """
    <style>
      .sott-title {
        font-size: 2.15rem;
        font-weight: 850;
        margin: -0.45rem 0 0.25rem;
      }
      .sott-subtitle {
        color: #475569;
        margin-bottom: 1.25rem;
      }
      div[data-testid="stMetric"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 0.75rem 0.9rem;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def normalize_key(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return " ".join(str(value).strip().lower().split())


def normalize_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    value_str = str(value).strip()
    return value_str[:-2] if value_str.endswith(".0") else value_str


def slugify(value: object) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return slug or "team"


def safe_text(value: object, fallback: str = "") -> str:
    if value is None or pd.isna(value):
        return fallback
    text = str(value).strip()
    return text if text else fallback


def ordinal(value: int) -> str:
    suffix = "th"
    if value % 100 not in {11, 12, 13}:
        if value % 10 == 1:
            suffix = "st"
        elif value % 10 == 2:
            suffix = "nd"
        elif value % 10 == 3:
            suffix = "rd"
    return f"{value}{suffix}"


def display_percentile(value: float) -> int:
    return max(1, min(99, int(round(float(value)))))


def truthy(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "t", "1", "yes", "y"}


def first_existing(columns: set[str], candidates: list[str]) -> str | None:
    exact = next((column for column in candidates if column in columns), None)
    if exact:
        return exact
    lower_lookup = {column.lower(): column for column in columns}
    return next((lower_lookup[candidate.lower()] for candidate in candidates if candidate.lower() in lower_lookup), None)


def valid_hex_color(value: object) -> str:
    value_str = str(value or "").strip()
    if not value_str:
        return ""
    if not value_str.startswith("#"):
        value_str = f"#{value_str}"
    if len(value_str) == 7 and all(char in "0123456789abcdefABCDEF" for char in value_str[1:]):
        return value_str
    return ""


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = valid_hex_color(color) or "#0f172a"
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def relative_luminance(color: str) -> float:
    rgb = [channel / 255 for channel in hex_to_rgb(color)]
    linear = [channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4 for channel in rgb]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_text(color: str) -> str:
    return "#0f172a" if relative_luminance(color) > 0.58 else "#ffffff"


def blend_with_white(color: str, amount: float) -> str:
    r, g, b = hex_to_rgb(color)
    amount = max(0.0, min(1.0, amount))
    return f"#{int(r + (255 - r) * amount):02x}{int(g + (255 - g) * amount):02x}{int(b + (255 - b) * amount):02x}"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def fit_text(draw: ImageDraw.ImageDraw, text: object, text_font: ImageFont.ImageFont, max_width: int) -> str:
    text = safe_text(text)
    if draw.textlength(text, font=text_font) <= max_width:
        return text
    ellipsis = "..."
    while text and draw.textlength(f"{text}{ellipsis}", font=text_font) > max_width:
        text = text[:-1]
    return f"{text}{ellipsis}" if text else ellipsis


def wrap_text(draw: ImageDraw.ImageDraw, text: object, text_font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    words = safe_text(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=text_font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if words and len(lines) == max_lines:
        all_text = " ".join(words)
        if " ".join(lines) != all_text:
            lines[-1] = fit_text(draw, lines[-1], text_font, max_width)
    return lines


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: object,
    fill: str,
    text_font: ImageFont.ImageFont,
    anchor: str | None = None,
) -> None:
    draw.text(xy, safe_text(text), fill=fill, font=text_font, anchor=anchor)


@st.cache_data(ttl=300)
def get_table_columns(table_name: str) -> set[str]:
    try:
        df = read_df(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            """,
            params={"table_name": table_name},
        )
    except Exception:
        return set()
    return set(df["column_name"]) if not df.empty else set()


@st.cache_data(ttl=300)
def load_team_assets() -> pd.DataFrame:
    try:
        team_map = read_df("SELECT * FROM public.team_map")
    except Exception:
        return pd.DataFrame(columns=["team_key", "team_id", "team_color", "team_logo", "team_logo_dark"])
    if team_map.empty:
        return pd.DataFrame(columns=["team_key", "team_id", "team_color", "team_logo", "team_logo_dark"])

    columns = set(team_map.columns)
    id_col = first_existing(columns, ["Id", "id", "TeamId", "teamId", "team_id"])
    name_col = first_existing(columns, ["cfb_name", "team", "school", "Team", "School"])
    color_col = first_existing(columns, ["Color", "color", "primary_color", "PrimaryColor"])
    logo_col = first_existing(columns, ["Logo", "logo", "logo_url", "Logo_URL"])
    dark_logo_col = first_existing(
        columns,
        ["DarkLogo", "dark_logo", "Logo_Dark", "LogoDark", "dark_logo_url", "DarkLogoUrl", "Dark_Logo"],
    )

    assets = pd.DataFrame(index=team_map.index)
    assets["team_key"] = team_map[name_col].map(normalize_key) if name_col else ""
    assets["team_id"] = team_map[id_col].map(normalize_id) if id_col else ""
    assets["team_color"] = team_map[color_col] if color_col else ""
    assets["team_logo"] = team_map[logo_col] if logo_col else ""
    assets["team_logo_dark"] = team_map[dark_logo_col] if dark_logo_col else ""
    assets["team_color"] = assets["team_color"].map(valid_hex_color)
    return assets


@st.cache_data(ttl=300)
def load_fbs_team_metadata() -> pd.DataFrame:
    try:
        teams = read_df(
            """
            WITH team_rows AS (
                SELECT
                    homeid::text AS team_id,
                    hometeam AS team,
                    homeconference AS conference,
                    season,
                    startdate
                FROM public.game_data
                WHERE hometeam IS NOT NULL
                  AND homeclassification = 'fbs'

                UNION ALL

                SELECT
                    awayid::text AS team_id,
                    awayteam AS team,
                    awayconference AS conference,
                    season,
                    startdate
                FROM public.game_data
                WHERE awayteam IS NOT NULL
                  AND awayclassification = 'fbs'
            )
            SELECT DISTINCT ON (LOWER(TRIM(team)))
                LOWER(TRIM(team)) AS team_key,
                team_id,
                team,
                conference
            FROM team_rows
            WHERE team IS NOT NULL
            ORDER BY LOWER(TRIM(team)), season DESC NULLS LAST, startdate DESC NULLS LAST
            """,
        )
    except Exception:
        return pd.DataFrame(columns=["team", "team_key", "team_id", "conference", "team_color", "team_logo", "team_logo_dark"])
    if teams.empty:
        return pd.DataFrame(columns=["team", "team_key", "team_id", "conference", "team_color", "team_logo", "team_logo_dark"])

    teams["team_key"] = teams["team_key"].map(normalize_key)
    teams["team_id"] = teams["team_id"].map(normalize_id)
    teams["conference"] = teams["conference"].fillna("Unknown").replace("", "Unknown")
    assets = load_team_assets()
    if not assets.empty:
        by_id = assets[assets["team_id"].astype(bool)][["team_id", "team_color", "team_logo", "team_logo_dark"]].drop_duplicates("team_id")
        by_key = assets[assets["team_key"].astype(bool)][["team_key", "team_color", "team_logo", "team_logo_dark"]].drop_duplicates("team_key")
        teams = teams.merge(
            by_id.rename(
                columns={
                    "team_color": "team_color_from_id",
                    "team_logo": "team_logo_from_id",
                    "team_logo_dark": "team_logo_dark_from_id",
                }
            ),
            on="team_id",
            how="left",
        )
        teams = teams.merge(
            by_key.rename(
                columns={
                    "team_color": "team_color_from_key",
                    "team_logo": "team_logo_from_key",
                    "team_logo_dark": "team_logo_dark_from_key",
                }
            ),
            on="team_key",
            how="left",
        )
        teams["team_color"] = teams["team_color_from_id"].combine_first(teams["team_color_from_key"])
        teams["team_logo"] = teams["team_logo_from_id"].combine_first(teams["team_logo_from_key"])
        teams["team_logo_dark"] = teams["team_logo_dark_from_id"].combine_first(teams["team_logo_dark_from_key"])
        teams = teams.drop(
            columns=[
                "team_color_from_id",
                "team_color_from_key",
                "team_logo_from_id",
                "team_logo_from_key",
                "team_logo_dark_from_id",
                "team_logo_dark_from_key",
            ]
        )
    else:
        teams["team_color"] = ""
        teams["team_logo"] = ""
        teams["team_logo_dark"] = ""

    teams["team_color"] = teams["team_color"].map(valid_hex_color)
    teams["team_logo"] = teams["team_logo"].fillna("").astype(str).str.strip()
    teams["team_logo_dark"] = teams["team_logo_dark"].fillna("").astype(str).str.strip()
    return teams[["team", "team_key", "team_id", "conference", "team_color", "team_logo", "team_logo_dark"]]


def selected_team_metadata(fbs_metadata: pd.DataFrame, selected_team: str) -> pd.Series:
    if fbs_metadata.empty:
        return pd.Series(dtype="object")
    team_key = normalize_key(selected_team)
    rows = fbs_metadata[fbs_metadata["team_key"] == team_key]
    return rows.iloc[0] if not rows.empty else pd.Series(dtype="object")


@st.cache_data(ttl=3600)
def fetch_logo_bytes(logo_url: str) -> bytes | None:
    if not logo_url or not logo_url.startswith(("http://", "https://")):
        return None
    try:
        request = Request(logo_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(request, timeout=8) as response:
            return response.read()
    except Exception:
        return None


def paste_logo(canvas: Image.Image, logo_url: str, box: tuple[int, int, int, int], opacity: float = 1.0) -> bool:
    logo_bytes = fetch_logo_bytes(logo_url)
    if not logo_bytes:
        return False
    try:
        logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
    except Exception:
        return False

    max_w = box[2] - box[0]
    max_h = box[3] - box[1]
    logo.thumbnail((max_w, max_h), Image.LANCZOS)
    if opacity < 1:
        alpha = logo.getchannel("A")
        alpha = alpha.point(lambda value: int(value * opacity))
        logo.putalpha(alpha)
    x = box[0] + (max_w - logo.width) // 2
    y = box[1] + (max_h - logo.height) // 2
    canvas.alpha_composite(logo, (x, y))
    return True


def paste_local_image(canvas: Image.Image, image_path: Path, box: tuple[int, int, int, int], opacity: float = 1.0) -> None:
    if not image_path.exists():
        return
    try:
        image = Image.open(image_path).convert("RGBA")
    except Exception:
        return
    max_w = box[2] - box[0]
    max_h = box[3] - box[1]
    image.thumbnail((max_w, max_h), Image.LANCZOS)
    if opacity < 1:
        alpha = image.getchannel("A")
        alpha = alpha.point(lambda value: int(value * opacity))
        image.putalpha(alpha)
    x = box[0] + (max_w - image.width) // 2
    y = box[1] + (max_h - image.height) // 2
    canvas.alpha_composite(image, (x, y))


def team_initials(team_name: object) -> str:
    words = [word for word in str(team_name or "").replace("-", " ").split() if word]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:2].upper()
    return "".join(word[0] for word in words[:2]).upper()


def draw_logo_or_initials(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    team_name: object,
    logo_url: str,
    box: tuple[int, int, int, int],
    bg_color: str = "#ffffff",
) -> None:
    if paste_logo(canvas, logo_url, box):
        return
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0, x1, y1), radius=18, fill=bg_color, outline="#cbd5e1", width=2)
    initials_size = max(10, min(34, int((y1 - y0) * 0.48)))
    draw_text(draw, ((x0 + x1) // 2, (y0 + y1) // 2), team_initials(team_name), "#0f172a", font(initials_size, bold=True), "mm")


def begin_slide(
    team: str,
    meta: pd.Series,
    kicker: str,
    title: str,
    team_first_header: bool = False,
) -> tuple[Image.Image, ImageDraw.ImageDraw, str, str, str]:
    team_color = valid_hex_color(meta.get("team_color", "")) or "#0f172a"
    text_color = contrast_text(team_color)
    soft_color = blend_with_white(team_color, 0.88)
    canvas = Image.new("RGBA", (SLIDE_W, SLIDE_H), "#f8fafc")
    draw = ImageDraw.Draw(canvas)

    draw.rectangle((0, 0, SLIDE_W, SLIDE_H), fill="#f8fafc")
    draw.rectangle((0, 0, SLIDE_W, 360), fill=team_color)
    draw.polygon([(0, 360), (SLIDE_W, 295), (SLIDE_W, 438), (0, 504)], fill=soft_color)
    draw.rectangle((0, 1040, SLIDE_W, SLIDE_H), fill="#ffffff")
    draw.rectangle((0, SLIDE_H - 16, SLIDE_W, SLIDE_H), fill=team_color)
    logo_url = safe_text(meta.get("team_logo_dark")) or safe_text(meta.get("team_logo"))
    paste_logo(canvas, logo_url, (705, 14, 1070, 374), opacity=0.22)
    draw_logo_or_initials(canvas, draw, team, logo_url, (52, 50, 208, 206), "#ffffff")
    if team_first_header:
        draw_text(draw, (236, 50), kicker.upper(), text_color, font(28, bold=True))
        team_lines = wrap_text(draw, team, font(60, bold=True), 720, 2)
        for idx, line in enumerate(team_lines):
            draw_text(draw, (236, 88 + idx * 64), line, text_color, font(60, bold=True))
        conference_y = 160 + (len(team_lines) - 1) * 58
        draw_text(draw, (236, conference_y), safe_text(meta.get("conference"), "FBS"), text_color, font(28))
        draw_text(draw, (236, conference_y + 42), title, text_color, font(36, bold=True))
    else:
        draw_text(draw, (236, 58), kicker.upper(), text_color, font(26, bold=True))
        for idx, line in enumerate(wrap_text(draw, title, font(52, bold=True), 710, 2)):
            draw_text(draw, (236, 96 + idx * 58), line, text_color, font(52, bold=True))
        draw_text(draw, (236, 232), team, text_color, font(30, bold=True))
        draw_text(draw, (236, 270), safe_text(meta.get("conference"), "FBS"), text_color, font(23))
    paste_local_image(canvas, APP_LOGO_COLOR_PATH, (892, 1260, 1030, 1332), opacity=0.9)
    draw_text(draw, (58, 1276), "@BG.Analytics", "#0f172a", font(24, bold=True))
    return canvas, draw, team_color, text_color, soft_color


def png_bytes(canvas: Image.Image) -> bytes:
    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def grade_from_percentile(pct: float) -> tuple[str, str, str]:
    pct = float(max(0.0, min(100.0, pct)))
    if pct >= 94:
        return ("A+", "#0B3D1A", "#FFFFFF")
    if pct >= 86:
        return ("A", "#145A32", "#FFFFFF")
    if pct >= 80:
        return ("A-", "#1E7D3A", "#FFFFFF")
    if pct >= 74:
        return ("B+", "#2ECC71", "#0B2E13")
    if pct >= 66:
        return ("B", "#58D68D", "#0B2E13")
    if pct >= 60:
        return ("B-", "#82E0AA", "#0B2E13")
    if pct >= 54:
        return ("C+", "#F7DC6F", "#4D3B00")
    if pct >= 46:
        return ("C", "#F4D03F", "#4D3B00")
    if pct >= 40:
        return ("C-", "#F9E79F", "#4D3B00")
    if pct >= 34:
        return ("D+", "#F8C471", "#5A2E00")
    if pct >= 26:
        return ("D", "#F5B041", "#5A2E00")
    if pct >= 20:
        return ("D-", "#F0B27A", "#5A2E00")
    return ("F", "#E74C3C", "#FFFFFF")


@st.cache_data(ttl=300)
def load_team_season_stats(season: int) -> pd.DataFrame:
    try:
        return read_df(
            """
            SELECT *
            FROM public.team_advanced_season_stats
            WHERE season = :season
            """,
            params={"season": int(season)},
        )
    except Exception:
        return pd.DataFrame()


def percentile_from_series(series: pd.Series, value: float, higher_is_better: bool = True) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if values.empty or pd.isna(value):
        return 50.0
    if not higher_is_better:
        values = -values
        value = -float(value)
    ranked = pd.concat([values, pd.Series([float(value)])], ignore_index=True).rank(pct=True)
    return float(ranked.iloc[-1]) * 100.0


def team_grades(team: str, season: int) -> dict[str, object]:
    stats = load_team_season_stats(season)
    if stats.empty or "team" not in stats.columns:
        return {}
    row_df = stats[stats["team"].map(normalize_key) == normalize_key(team)]
    if row_df.empty:
        return {}
    row = row_df.iloc[0]
    grades: dict[str, object] = {}
    if "offense_ppa" in stats.columns and pd.notna(row.get("offense_ppa")):
        pct = percentile_from_series(stats["offense_ppa"], float(row["offense_ppa"]), True)
        grades["offense"] = grade_from_percentile(pct)
        grades["offense_pct"] = pct
        grades["offense_value"] = float(row["offense_ppa"])
    if "defense_ppa" in stats.columns and pd.notna(row.get("defense_ppa")):
        pct = percentile_from_series(stats["defense_ppa"], float(row["defense_ppa"]), False)
        grades["defense"] = grade_from_percentile(pct)
        grades["defense_pct"] = pct
        grades["defense_value"] = float(row["defense_ppa"])
    best = []
    stat_specs = [
        ("Passing O", "offense_passingplays_ppa", True),
        ("Rushing O", "offense_rushingplays_ppa", True),
        ("Off. Explosiveness", "offense_passingplays_explosiveness", True),
        ("OL Pass Pro", "offense_havoc_frontseven", False),
        ("OL Run Block", "offense_lineyards", True),
        ("Passing D", "defense_passingplays_ppa", False),
        ("Rushing D", "defense_rushingplays_ppa", False),
        ("DB Havoc", "defense_havoc_db", True),
        ("Def. Stuff Rate", "defense_stuffrate", True),
    ]
    for label, col, high_good in stat_specs:
        if col in stats.columns and pd.notna(row.get(col)):
            best.append((label, percentile_from_series(stats[col], float(row[col]), high_good)))
    grades["best_traits"] = sorted(best, key=lambda item: item[1], reverse=True)[:3]
    return grades


@st.cache_data(ttl=300)
def load_team_games(team: str, season: int) -> pd.DataFrame:
    try:
        df = read_df(
            """
            SELECT *
            FROM public.game_data
            WHERE season = :season
              AND startdate IS NOT NULL
              AND (hometeam = :team OR awayteam = :team)
            ORDER BY startdate
            """,
            params={"team": team, "season": int(season)},
        )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["startdate"] = pd.to_datetime(df["startdate"], errors="coerce")
    for col in ["homepoints", "awaypoints"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def game_winner(row: pd.Series) -> str:
    if pd.isna(row.get("homepoints")) or pd.isna(row.get("awaypoints")):
        return ""
    if float(row["homepoints"]) > float(row["awaypoints"]):
        return safe_text(row.get("hometeam"))
    if float(row["awaypoints"]) > float(row["homepoints"]):
        return safe_text(row.get("awayteam"))
    return "Tie"


def team_record(team: str, games: pd.DataFrame, regular_only: bool = False, postseason_only: bool = False) -> tuple[int, int]:
    if games.empty:
        return 0, 0
    df = games.copy()
    if regular_only and "seasontype" in df.columns:
        df = df[df["seasontype"].fillna("regular").astype(str).str.lower() != "postseason"]
    if postseason_only and "seasontype" in df.columns:
        df = df[df["seasontype"].fillna("").astype(str).str.lower() == "postseason"]
    completed = df[df["homepoints"].notna() & df["awaypoints"].notna()].copy()
    wins = int(completed.apply(lambda row: game_winner(row) == team, axis=1).sum())
    losses = int(len(completed) - wins)
    return wins, losses


def record_label(wins: int, losses: int, na_if_empty: bool = False) -> str:
    if na_if_empty and wins == 0 and losses == 0:
        return "N/A"
    return f"{wins}-{losses}"


def postseason_results(team: str, games: pd.DataFrame) -> list[str]:
    if games.empty or "seasontype" not in games.columns:
        return []
    postseason = games[games["seasontype"].fillna("").astype(str).str.lower() == "postseason"].copy()
    results = []
    for _, row in postseason.iterrows():
        opponent = row["awayteam"] if row.get("hometeam") == team else row.get("hometeam")
        if pd.isna(row.get("homepoints")) or pd.isna(row.get("awaypoints")):
            score = "Scheduled"
        else:
            team_points = row["homepoints"] if row.get("hometeam") == team else row["awaypoints"]
            opp_points = row["awaypoints"] if row.get("hometeam") == team else row["homepoints"]
            result = "W" if team_points > opp_points else "L" if team_points < opp_points else "T"
            score = f"{result} {int(team_points)}-{int(opp_points)}"
        notes = safe_text(row.get("notes") or row.get("game_notes") or row.get("gamenotes"))
        label = notes if notes else "Postseason"
        results.append(f"{label}: {score} vs {opponent}")
    return results


@st.cache_data(ttl=300)
def final_ap_rankings(season: int) -> pd.DataFrame:
    try:
        weeks = read_df(
            """
            SELECT MAX(week)::int AS week
            FROM public.rankings
            WHERE season = :season
              AND poll = 'AP Top 25'
            """,
            params={"season": int(season)},
        )
        if weeks.empty or pd.isna(weeks["week"].iloc[0]):
            return pd.DataFrame(columns=["team", "rank"])
        week = int(weeks["week"].iloc[0])
        df = read_df(
            """
            SELECT school AS team, rank::int AS rank
            FROM public.rankings
            WHERE season = :season
              AND poll = 'AP Top 25'
              AND week = :week
            ORDER BY rank
            """,
            params={"season": int(season), "week": week},
        )
    except Exception:
        return pd.DataFrame(columns=["team", "rank"])
    return df


def final_ap_rank(team: str, season: int) -> str:
    rankings = final_ap_rankings(season)
    if rankings.empty:
        return "Unranked"
    rows = rankings[rankings["team"].map(normalize_key) == normalize_key(team)]
    if rows.empty or pd.isna(rows["rank"].iloc[0]):
        return "Unranked"
    return f"#{int(rows['rank'].iloc[0])}"


@st.cache_data(ttl=300)
def conference_standings(season: int, conference: str) -> pd.DataFrame:
    if not conference or conference == "Unknown":
        return pd.DataFrame()
    try:
        df = read_df(
            """
            SELECT
                hometeam,
                awayteam,
                homeconference,
                awayconference,
                homepoints,
                awaypoints,
                seasontype
            FROM public.game_data
            WHERE season = :season
              AND homepoints IS NOT NULL
              AND awaypoints IS NOT NULL
              AND LOWER(COALESCE(seasontype, 'regular')) <> 'postseason'
              AND homeconference = :conference
              AND awayconference = :conference
            """,
            params={"season": int(season), "conference": conference},
        )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    rows: dict[str, dict[str, int]] = {}
    for _, row in df.iterrows():
        home = safe_text(row["hometeam"])
        away = safe_text(row["awayteam"])
        rows.setdefault(home, {"team": home, "wins": 0, "losses": 0})
        rows.setdefault(away, {"team": away, "wins": 0, "losses": 0})
        if float(row["homepoints"]) > float(row["awaypoints"]):
            rows[home]["wins"] += 1
            rows[away]["losses"] += 1
        elif float(row["awaypoints"]) > float(row["homepoints"]):
            rows[away]["wins"] += 1
            rows[home]["losses"] += 1
    standings = pd.DataFrame(rows.values())
    if standings.empty:
        return standings
    standings["win_pct"] = standings["wins"] / (standings["wins"] + standings["losses"]).replace(0, 1)
    standings = standings.sort_values(["win_pct", "wins", "team"], ascending=[False, False, True]).reset_index(drop=True)
    standings["standing"] = standings["win_pct"].rank(method="min", ascending=False).astype(int)
    return standings


def conference_standing_label(team: str, season: int, conference: str) -> str:
    standings = conference_standings(season, conference)
    if standings.empty:
        return "N/A"
    rows = standings[standings["team"].map(normalize_key) == normalize_key(team)]
    if rows.empty:
        return "N/A"
    row = rows.iloc[0]
    standing = int(row["standing"])
    tied = (standings["standing"] == standing).sum() > 1
    prefix = f"T-{standing}" if tied else str(standing)
    return f"{prefix} in {conference} ({int(row['wins'])}-{int(row['losses'])})"


def conference_result(team: str, season: int, conference: str) -> tuple[str, str]:
    standings = conference_standings(season, conference)
    if standings.empty:
        return "N/A", "N/A"
    rows = standings[standings["team"].map(normalize_key) == normalize_key(team)]
    if rows.empty:
        return "N/A", "N/A"
    row = rows.iloc[0]
    standing = int(row["standing"])
    tied = (standings["standing"] == standing).sum() > 1
    standing_label = f"T-{standing}" if tied else str(standing)
    return standing_label, f"{int(row['wins'])}-{int(row['losses'])}"


@st.cache_data(ttl=300)
def ap_ranking_history(team: str, season: int) -> pd.DataFrame:
    try:
        df = read_df(
            """
            SELECT week::int AS week, rank::int AS rank
            FROM public.rankings
            WHERE season = :season
              AND poll = 'AP Top 25'
              AND LOWER(TRIM(school)) = LOWER(TRIM(:team))
            ORDER BY week
            """,
            params={"team": team, "season": int(season)},
        )
    except Exception:
        return pd.DataFrame(columns=["week", "rank"])
    if df.empty:
        return pd.DataFrame(columns=["week", "rank"])
    df["week"] = pd.to_numeric(df["week"], errors="coerce")
    df["rank"] = pd.to_numeric(df["rank"], errors="coerce")
    return df.dropna(subset=["week", "rank"]).sort_values("week").reset_index(drop=True)


def position_group(position: object) -> str:
    pos = str(position or "").upper().strip()
    return POSITION_TO_GROUP.get(pos, "OTHER")


def clean_team_series(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "NULL": "", "null": ""})
    )


@st.cache_data(ttl=300)
def load_transfer_portal() -> pd.DataFrame:
    columns = get_table_columns(TRANSFER_TABLE)
    if not columns:
        return pd.DataFrame()

    field_candidates = {
        "season": ["Season", "season", "year"],
        "first_name": ["FirstName", "firstname", "first_name", "first"],
        "last_name": ["LastName", "lastname", "last_name", "last", "surname"],
        "position": ["Position", "position", "pos"],
        "origin": ["Origin", "origin", "from_team", "from", "previous_team", "old_team"],
        "destination": ["Destination", "destination", "to_team", "to", "new_team", "committed_to"],
        "transfer_date": ["TransferDate", "transferdate", "transfer_date", "date"],
        "rating": ["Rating", "rating", "player_rating"],
        "stars": ["Stars", "stars", "star_rating"],
        "eligibility": ["Eligibility", "eligibility", "status"],
    }
    selected_columns = {
        output_column: first_existing(columns, candidates)
        for output_column, candidates in field_candidates.items()
    }
    required = ["season", "first_name", "last_name", "position", "origin", "destination"]
    missing = [column for column in required if selected_columns[column] is None]
    if missing:
        return pd.DataFrame({"_missing_columns": [", ".join(missing)]})

    select_parts = []
    for output_column, source_column in selected_columns.items():
        if source_column:
            select_parts.append(f"{quote_identifier(source_column)} AS {quote_identifier(output_column)}")
        elif output_column in {"rating", "stars"}:
            select_parts.append(f"NULL::numeric AS {quote_identifier(output_column)}")
        else:
            select_parts.append(f"NULL::text AS {quote_identifier(output_column)}")

    df = read_df(f"SELECT {', '.join(select_parts)} FROM public.{quote_identifier(TRANSFER_TABLE)}")
    if df.empty:
        return df
    df["season"] = pd.to_numeric(df["season"], errors="coerce").astype("Int64")
    df["first_name"] = df["first_name"].fillna("").astype(str).str.strip()
    df["last_name"] = df["last_name"].fillna("").astype(str).str.strip()
    df["player"] = (df["first_name"] + " " + df["last_name"]).str.strip().replace("", "Unknown")
    df["position"] = df["position"].fillna("").astype(str).str.upper().str.strip().replace("", "UNK")
    df["origin"] = clean_team_series(df["origin"])
    df["destination"] = clean_team_series(df["destination"])
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["stars"] = pd.to_numeric(df["stars"], errors="coerce")
    df["transfer_date"] = pd.to_datetime(df["transfer_date"], errors="coerce")
    df["eligibility"] = df["eligibility"].fillna("").astype(str).str.strip()
    df["position_group"] = df["position"].map(position_group)
    return df


def effective_depth_count(player_count: int, weights: dict[str, float]) -> float:
    depth_cap = int(weights.get("depth_cap", player_count))
    overflow_depth = float(weights.get("overflow_depth", 1.0))
    full_depth_count = min(player_count, depth_cap)
    overflow_count = max(player_count - depth_cap, 0)
    return full_depth_count + overflow_count * overflow_depth


def position_side_impact(df: pd.DataFrame, position_group_name: str) -> float:
    if df.empty:
        return 0.0
    weights = POSITION_IMPACT_WEIGHTS.get(position_group_name, POSITION_IMPACT_WEIGHTS["OTHER"])
    ratings = df["rating"].dropna().sort_values(ascending=False)
    top_quality = ratings.head(int(weights["top_n"])).mean() if not ratings.empty else 0.0
    avg_quality = ratings.mean() if not ratings.empty else 0.0
    depth_score = effective_depth_count(len(df), weights) * float(weights["depth"])
    return depth_score + float(weights["top_quality"]) * float(top_quality) + float(weights["avg_quality"]) * float(avg_quality)


def total_position_impact(incoming: pd.DataFrame, outgoing: pd.DataFrame) -> float:
    total = 0.0
    for group in POSITION_GROUP_ORDER:
        total += position_side_impact(incoming[incoming["position_group"] == group], group)
        total -= position_side_impact(outgoing[outgoing["position_group"] == group], group)
    return total


def top_transfers(df: pd.DataFrame, limit: int = 5) -> pd.DataFrame:
    if df.empty:
        return df
    return (
        df.sort_values(["rating", "stars", "transfer_date", "player"], ascending=[False, False, False, True], na_position="last")
        .head(limit)
        .reset_index(drop=True)
    )


def portal_balance(incoming: pd.DataFrame, outgoing: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for group, order in POSITION_GROUP_ORDER.items():
        in_group = incoming[incoming["position_group"] == group]
        out_group = outgoing[outgoing["position_group"] == group]
        impact = position_side_impact(in_group, group) - position_side_impact(out_group, group)
        if len(in_group) or len(out_group):
            rows.append({"position": group, "order": order, "net": len(in_group) - len(out_group), "impact": impact})
    return pd.DataFrame(rows).sort_values("order") if rows else pd.DataFrame()


def portal_impact_rank_context(team: str, season_portal: pd.DataFrame) -> tuple[str, str]:
    fbs_metadata = load_fbs_team_metadata()
    if season_portal.empty or fbs_metadata.empty:
        return "N/A", "N/A"

    portal_with_keys = season_portal.copy()
    portal_with_keys["origin_key"] = portal_with_keys["origin"].map(normalize_key)
    portal_with_keys["destination_key"] = portal_with_keys["destination"].map(normalize_key)

    rows = []
    for team_row in fbs_metadata.drop_duplicates("team_key").itertuples(index=False):
        team_key = str(team_row.team_key)
        incoming_team = portal_with_keys[portal_with_keys["destination_key"] == team_key]
        outgoing_team = portal_with_keys[portal_with_keys["origin_key"] == team_key]
        rows.append(
            {
                "team": team_row.team,
                "team_key": team_key,
                "conference": team_row.conference,
                "impact": total_position_impact(incoming_team, outgoing_team),
            }
        )

    rankings = pd.DataFrame(rows)
    if rankings.empty:
        return "N/A", "N/A"
    rankings = rankings.sort_values(["impact", "team"], ascending=[False, True]).reset_index(drop=True)
    rankings["rank"] = rankings["impact"].rank(method="min", ascending=False).astype(int)

    team_key = normalize_key(team)
    selected = rankings[rankings["team_key"] == team_key]
    if selected.empty:
        return "N/A", "N/A"
    selected_row = selected.iloc[0]
    national_label = f"#{int(selected_row['rank'])}/{len(rankings)}"

    conference_rows = rankings[rankings["conference"] == selected_row["conference"]].copy()
    if conference_rows.empty:
        return national_label, "N/A"
    conference_rows["conference_rank"] = conference_rows["impact"].rank(method="min", ascending=False).astype(int)
    conference_selected = conference_rows[conference_rows["team_key"] == team_key]
    if conference_selected.empty:
        return national_label, "N/A"
    conference_label = f"#{int(conference_selected['conference_rank'].iloc[0])}/{len(conference_rows)}"
    return national_label, conference_label


@st.cache_data(ttl=300)
def load_schedule(team: str, season: int) -> pd.DataFrame:
    columns = get_table_columns("game_data")
    if not columns:
        return pd.DataFrame()
    required = {
        "id",
        "season",
        "week",
        "startdate",
        "hometeam",
        "awayteam",
        "homeid",
        "awayid",
        "homeconference",
        "awayconference",
        "homeclassification",
        "awayclassification",
    }
    if not required.issubset(columns):
        return pd.DataFrame()

    def optional_expr(candidates: list[str], alias: str, cast: str = "") -> str:
        column = first_existing(columns, candidates)
        if column:
            suffix = f"::{cast}" if cast else ""
            return f"{quote_identifier(column)}{suffix} AS {quote_identifier(alias)}"
        if cast == "boolean":
            return f"FALSE AS {quote_identifier(alias)}"
        return f"NULL::text AS {quote_identifier(alias)}"

    neutral_expr = optional_expr(["neutral_site", "neutralSite", "NeutralSite", "neutral"], "neutral_site")
    venue_expr = optional_expr(["venue", "Venue", "venue_name", "VenueName"], "venue")
    venue_id_expr = optional_expr(["venueid", "venue_id", "VenueId", "VenueID"], "venueid")
    seasontype_expr = optional_expr(["seasontype", "season_type", "seasonType"], "seasontype")
    season_type_filter = "AND LOWER(COALESCE(seasontype, 'regular')) <> 'postseason'" if "seasontype" in columns else ""
    try:
        df = read_df(
            f"""
            SELECT
                id,
                season,
                week,
                startdate,
                hometeam,
                awayteam,
                homeid,
                awayid,
                homeconference,
                awayconference,
                homeclassification,
                awayclassification,
                {neutral_expr},
                {venue_expr},
                {venue_id_expr},
                {seasontype_expr}
            FROM public.game_data
            WHERE season = :season
              AND startdate IS NOT NULL
              {season_type_filter}
              AND (hometeam = :team OR awayteam = :team)
            ORDER BY startdate
            """,
            params={"team": team, "season": int(season)},
        )
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    df["startdate"] = pd.to_datetime(df["startdate"], errors="coerce")
    return df.sort_values("startdate").reset_index(drop=True)


@st.cache_data(ttl=300)
def records_for_season(season: int) -> pd.DataFrame:
    try:
        games = read_df(
            """
            SELECT hometeam, awayteam, homepoints, awaypoints, seasontype
            FROM public.game_data
            WHERE season = :season
              AND homepoints IS NOT NULL
              AND awaypoints IS NOT NULL
            """,
            params={"season": int(season)},
        )
    except Exception:
        return pd.DataFrame(columns=["team", "wins", "losses", "record"])
    rows: dict[str, dict[str, int | str]] = {}
    for _, row in games.iterrows():
        home = safe_text(row.get("hometeam"))
        away = safe_text(row.get("awayteam"))
        rows.setdefault(home, {"team": home, "wins": 0, "losses": 0})
        rows.setdefault(away, {"team": away, "wins": 0, "losses": 0})
        if float(row["homepoints"]) > float(row["awaypoints"]):
            rows[home]["wins"] = int(rows[home]["wins"]) + 1
            rows[away]["losses"] = int(rows[away]["losses"]) + 1
        elif float(row["awaypoints"]) > float(row["homepoints"]):
            rows[away]["wins"] = int(rows[away]["wins"]) + 1
            rows[home]["losses"] = int(rows[home]["losses"]) + 1
    records = pd.DataFrame(rows.values())
    if records.empty:
        return pd.DataFrame(columns=["team", "wins", "losses", "record"])
    records["team_key"] = records["team"].map(normalize_key)
    records["record"] = records["wins"].astype(int).astype(str) + "-" + records["losses"].astype(int).astype(str)
    return records


def opponent_record(team: str, season: int) -> str:
    records = records_for_season(season)
    if records.empty:
        return "--"
    rows = records[records["team_key"] == normalize_key(team)]
    if rows.empty:
        return "--"
    return safe_text(rows["record"].iloc[0], "--")


def opponent_rank(team: str, season: int) -> str:
    return final_ap_rank(team, season)


def draw_stat_card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    accent: str,
    sublabel: str = "",
    label_size: int = 19,
    value_size: int = 39,
    sublabel_size: int = 18,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=22, fill="#ffffff", outline="#dbe4ee", width=2)
    draw.rectangle((x0, y0, x0 + 10, y1), fill=accent)
    draw_text(draw, (x0 + 30, y0 + 22), fit_text(draw, label.upper(), font(label_size, bold=True), x1 - x0 - 54), "#64748b", font(label_size, bold=True))
    draw_text(draw, (x0 + 30, y0 + 58), fit_text(draw, value, font(value_size, bold=True), x1 - x0 - 54), "#0f172a", font(value_size, bold=True))
    if sublabel:
        draw_text(draw, (x0 + 30, y1 - 38), fit_text(draw, sublabel, font(sublabel_size), x1 - x0 - 54), "#64748b", font(sublabel_size))


def draw_grade_badge(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    title: str,
    grade: tuple[str, str, str] | None,
    pct: float | None,
) -> None:
    x, y = xy
    draw.rounded_rectangle((x, y, x + 480, y + 170), radius=28, fill="#ffffff", outline="#dbe4ee", width=2)
    draw_text(draw, (x + 30, y + 25), title.upper(), "#64748b", font(23, bold=True))
    if grade:
        letter, bg, fg = grade
        draw.rounded_rectangle((x + 330, y + 34, x + 446, y + 124), radius=25, fill=bg)
        draw_text(draw, (x + 388, y + 79), letter, fg, font(46, bold=True), "mm")
        if pct is not None:
            # Tweak these two y-offsets if you want to fine-tune the percentile text placement.
            pct_value_y = y + 68
            pct_label_y = y + 116
            pct_int = display_percentile(pct)
            draw_text(draw, (x + 30, pct_value_y), ordinal(pct_int), "#0f172a", font(48, bold=True))
            draw_text(draw, (x + 30, pct_label_y), "FBS percentile", "#64748b", font(20))
    else:
        draw_text(draw, (x + 30, y + 82), "N/A", "#0f172a", font(48, bold=True))


def draw_ap_history_chart(
    draw: ImageDraw.ImageDraw,
    history: pd.DataFrame,
    box: tuple[int, int, int, int],
    team_color: str,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=24, fill="#f8fafc", outline="#e2e8f0", width=2)
    draw_text(draw, (x0 + 28, y0 + 22), "AP RANKING OVER TIME", "#64748b", font(20, bold=True))
    if history.empty:
        draw_text(draw, (x0 + 28, y0 + 70), "Not ranked in the AP Top 25 during this season.", "#0f172a", font(24, bold=True))
        return

    plot_left = x0 + 74
    plot_right = x1 - 46
    plot_top = y0 + 64
    plot_bottom = y1 - 32
    draw.line((plot_left, plot_bottom, plot_right, plot_bottom), fill="#cbd5e1", width=2)
    draw.line((plot_left, plot_top, plot_left, plot_bottom), fill="#cbd5e1", width=2)
    for rank in [1, 5, 10, 15, 20, 25]:
        y = plot_top + (rank - 1) / 24 * (plot_bottom - plot_top)
        draw.line((plot_left, int(y), plot_right, int(y)), fill="#e2e8f0", width=1)
        draw_text(draw, (x0 + 28, int(y) - 10), f"#{rank}", "#94a3b8", font(14, bold=True))

    weeks = history["week"].astype(float)
    ranks = history["rank"].astype(float)
    min_week = float(weeks.min())
    max_week = float(weeks.max())
    week_span = max(max_week - min_week, 1.0)

    points = []
    for week, rank in zip(weeks, ranks):
        x = plot_left + (float(week) - min_week) / week_span * (plot_right - plot_left)
        y = plot_top + (float(rank) - 1) / 24 * (plot_bottom - plot_top)
        points.append((int(x), int(y)))

    if len(points) > 1:
        draw.line(points, fill=team_color, width=5, joint="curve")
    for x, y in points:
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=team_color, outline="#ffffff", width=3)

    first_rank = int(ranks.iloc[0])
    final_rank = int(ranks.iloc[-1])
    movement = first_rank - final_rank
    movement_label = "even" if movement == 0 else f"{movement:+d} spots"
    draw_text(draw, (plot_right - 210, y0 + 22), f"Final #{final_rank}", "#0f172a", font(20, bold=True))
    draw_text(draw, (plot_right - 94, y0 + 22), movement_label, team_color, font(20, bold=True))


def asset_logo_url(team_name: object, team_id: object, assets: pd.DataFrame) -> str:
    if assets.empty:
        return ""
    team_id_key = normalize_id(team_id)
    if team_id_key and "team_id" in assets.columns:
        by_id = assets[assets["team_id"].astype(str) == team_id_key]
        if not by_id.empty:
            row = by_id.iloc[0]
            return safe_text(row.get("team_logo")) or safe_text(row.get("team_logo_dark"))
    team_key = normalize_key(team_name)
    if team_key and "team_key" in assets.columns:
        by_key = assets[assets["team_key"].astype(str) == team_key]
        if not by_key.empty:
            row = by_key.iloc[0]
            return safe_text(row.get("team_logo")) or safe_text(row.get("team_logo_dark"))
    return ""


def game_margin_rows(team: str, games: pd.DataFrame) -> list[dict[str, object]]:
    if games.empty:
        return []
    completed = games[games["homepoints"].notna() & games["awaypoints"].notna()].copy()
    if completed.empty:
        return []

    rows = []
    for _, row in completed.sort_values("startdate").iterrows():
        is_home = row.get("hometeam") == team
        opponent = row.get("awayteam") if is_home else row.get("hometeam")
        opponent_id = row.get("awayid") if is_home else row.get("homeid")
        team_points = row.get("homepoints") if is_home else row.get("awaypoints")
        opponent_points = row.get("awaypoints") if is_home else row.get("homepoints")
        if pd.isna(team_points) or pd.isna(opponent_points):
            continue
        mov = int(float(team_points) - float(opponent_points))
        rows.append(
            {
                "week": int(row["week"]) if pd.notna(row.get("week")) else len(rows) + 1,
                "opponent": safe_text(opponent, "TBD"),
                "opponent_id": opponent_id,
                "mov": mov,
                "result": "W" if mov > 0 else "L" if mov < 0 else "T",
            }
        )
    return rows


def draw_mov_bar_chart(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    team: str,
    games: pd.DataFrame,
    box: tuple[int, int, int, int],
    team_color: str,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=24, fill="#f8fafc", outline="#e2e8f0", width=2)
    draw_text(draw, (x0 + 30, y0 + 20), "Game Results:", "#64748b", font(24, bold=True))
    rows = game_margin_rows(team, games)
    if not rows:
        draw_text(draw, (x0 + 28, y0 + 70), "No completed games found for this season.", "#0f172a", font(24, bold=True))
        return

    rows = rows[:16]
    max_abs_mov = max(max(abs(int(row["mov"])) for row in rows), 1)
    chart_left = x0 + 66
    chart_right = x1 - 38
    chart_top = y0 + 58
    chart_bottom = y1 - 58
    baseline = (chart_top + chart_bottom) // 2
    positive_span = max(baseline - chart_top - 6, 1)
    negative_span = max(chart_bottom - baseline - 6, 1)
    slot = (chart_right - chart_left) / len(rows)
    bar_w = max(9, min(34, int(slot * 0.48)))
    assets = load_team_assets()

    draw.line((chart_left - 14, baseline, chart_right + 10, baseline), fill="#94a3b8", width=2)
    draw_text(draw, (x0 + 28, baseline - 13), "0", "#94a3b8", font(16, bold=True))
    draw_text(draw, (x0 + 28, chart_top), f"+{max_abs_mov}", "#94a3b8", font(16, bold=True))
    draw_text(draw, (x0 + 28, chart_bottom - 17), f"-{max_abs_mov}", "#94a3b8", font(16, bold=True))

    for idx, row in enumerate(rows):
        cx = int(chart_left + slot * idx + slot / 2)
        mov = int(row["mov"])
        color = "#16a34a" if mov > 0 else "#dc2626" if mov < 0 else "#64748b"
        if mov > 0:
            y_bar = int(baseline - (mov / max_abs_mov) * positive_span)
            draw.rounded_rectangle((cx - bar_w // 2, y_bar, cx + bar_w // 2, baseline), radius=6, fill=color)
            label_y = baseline + 16
        elif mov < 0:
            y_bar = int(baseline + (abs(mov) / max_abs_mov) * negative_span)
            draw.rounded_rectangle((cx - bar_w // 2, baseline, cx + bar_w // 2, y_bar), radius=6, fill=color)
            label_y = baseline - 16
        else:
            y_bar = baseline
            draw.rounded_rectangle((cx - bar_w // 2, baseline - 4, cx + bar_w // 2, baseline + 4), radius=4, fill=color)
            label_y = baseline - 16

        label_text = f"{mov:+d}"
        label_font = font(15, bold=True)
        label_w = int(draw.textlength(label_text, font=label_font))
        draw.rounded_rectangle(
            (cx - label_w // 2 - 5, int(label_y) - 10, cx + label_w // 2 + 5, int(label_y) + 10),
            radius=6,
            fill="#ffffff",
        )
        draw_text(draw, (cx, int(label_y)), label_text, color, label_font, "mm")

        logo_url = asset_logo_url(row["opponent"], row["opponent_id"], assets)
        logo_y = y1 - 44
        draw_logo_or_initials(canvas, draw, row["opponent"], logo_url, (cx - 18, logo_y, cx + 18, logo_y + 36), "#ffffff")

    wins = sum(1 for row in rows if int(row["mov"]) > 0)
    losses = sum(1 for row in rows if int(row["mov"]) < 0)
    avg_mov = sum(int(row["mov"]) for row in rows) / len(rows)
    draw_text(draw, (x1 - 330, y0 + 22), f"{wins}-{losses} shown", "#0f172a", font(21, bold=True))
    draw_text(draw, (x1 - 178, y0 + 22), f"Avg MOV {avg_mov:+.1f}", team_color, font(21, bold=True))


def draw_table_row(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    team: str,
    logo_url: str,
    name: str,
    detail: str,
    value: str,
    accent: str,
    x0: int,
    x1: int,
    row_h: int = 76,
) -> None:
    draw.rounded_rectangle((x0, y, x1, y + row_h), radius=16, fill="#ffffff", outline="#e2e8f0", width=1)
    logo_size = min(52, row_h - 18)
    logo_y = y + (row_h - logo_size) // 2
    draw_logo_or_initials(canvas, draw, team, logo_url, (x0 + 14, logo_y, x0 + 14 + logo_size, logo_y + logo_size), "#f8fafc")
    draw_text(draw, (x0 + 82, y + 10), fit_text(draw, name, font(20, bold=True), x1 - x0 - 210), "#0f172a", font(20, bold=True))
    draw_text(draw, (x0 + 82, y + 37), fit_text(draw, detail, font(16), x1 - x0 - 210), "#64748b", font(16))
    draw.rounded_rectangle((x1 - 104, y + 14, x1 - 18, y + row_h - 14), radius=13, fill=accent)
    draw_text(draw, (x1 - 61, y + row_h // 2), value, contrast_text(accent), font(18, bold=True), "mm")


def draw_rank_pill(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    fill: str,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=16, fill=fill, outline="#cbd5e1", width=1)
    mid_y = (y0 + y1) // 2
    draw_text(draw, (x0 + 26, mid_y), label.upper(), "#64748b", font(15, bold=True), "lm")
    draw_text(draw, (x1 - 26, mid_y), fit_text(draw, value, font(21, bold=True), 128), "#0f172a", font(21, bold=True), "rm")


def draw_position_swing_chip(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    position: object,
    net: int,
    impact: float,
    fill: str,
    outline: str,
    accent: str,
) -> None:
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    draw.rounded_rectangle(box, radius=18, fill=fill, outline=outline, width=1)
    draw_text(draw, (cx - 34, y0 + 27), safe_text(position), "#0f172a", font(25, bold=True), "mm")
    draw_text(draw, (cx + 42, y0 + 27), f"{int(net):+d}", accent, font(23, bold=True), "mm")
    draw_text(draw, (cx, y0 + 56), f"Impact {impact:+.1f}", accent, font(20, bold=True), "mm")


def results_slide(team: str, meta: pd.Series, season: int, outlook_season: int) -> bytes:
    canvas, draw, team_color, _, soft_color = begin_slide(
        team,
        meta,
        f"{outlook_season} Preseason Outlook",
        f"{season} Results:",
        team_first_header=True,
    )
    games = load_team_games(team, season)
    wins, losses = team_record(team, games)
    regular_wins, regular_losses = team_record(team, games, regular_only=True)
    postseason_wins, postseason_losses = team_record(team, games, postseason_only=True)
    conference_standing, conference_record = conference_result(team, season, safe_text(meta.get("conference"), "Unknown"))
    ap_label = final_ap_rank(team, season)
    grades = team_grades(team, season)

    draw_stat_card(
        draw,
        (42, 385, 342, 545),
        "Final Record",
        f"{wins}-{losses}",
        team_color,
        f"Postseason: {record_label(postseason_wins, postseason_losses, na_if_empty=True)}",
        label_size=21,
        value_size=48,
        sublabel_size=20,
    )
    draw_stat_card(
        draw,
        (390, 385, 690, 545),
        "Conference Record",
        conference_record,
        team_color,
        f"Rank: {conference_standing}",
        label_size=21,
        value_size=48,
        sublabel_size=20,
    )
    draw_stat_card(
        draw,
        (738, 385, 1038, 545),
        "Final AP",
        ap_label,
        team_color,
        "Final AP Top 25",
        label_size=21,
        value_size=48,
        sublabel_size=20,
    )

    draw_grade_badge(draw, (42, 570), "Offense Grade", grades.get("offense"), grades.get("offense_pct"))
    draw_grade_badge(draw, (558, 570), "Defense Grade", grades.get("defense"), grades.get("defense_pct"))
    draw_text(draw, (68, 756), "*Grades are not scaled for Strength of Schedule", "#64748b", font(20, bold=True))

    draw.rounded_rectangle((42, 790, 1038, 1016), radius=28, fill="#ffffff", outline="#dbe4ee", width=2)
    draw_text(draw, (72, 822), f"WHAT WENT WELL IN {season}", "#0f172a", font(30, bold=True))
    traits = grades.get("best_traits") or []
    if traits:
        for idx, (label, pct) in enumerate(traits):
            x = 72 + idx * 322
            draw.rounded_rectangle((x, 872, x + 292, 988), radius=24, fill=soft_color, outline="#cbd5e1", width=1)
            draw_text(draw, (x + 24, 894), fit_text(draw, label, font(23, bold=True), 244), "#0f172a", font(23, bold=True))
            draw_text(draw, (x + 24, 930), ordinal(display_percentile(pct)), "#0f172a", font(42, bold=True))
            draw_text(draw, (x + 124, 942), "percentile", "#475569", font(20))
    else:
        draw_text(draw, (86, 884), "No advanced season stat profile found.", "#64748b", font(24, bold=True))

    draw_mov_bar_chart(canvas, draw, team, games, (42, 1030, 1038, 1248), team_color)

    return png_bytes(canvas)


def transfer_slide(team: str, meta: pd.Series, portal_season: int, portal: pd.DataFrame) -> bytes:
    canvas, draw, team_color, _, soft_color = begin_slide(
        team,
        meta,
        f"{portal_season} Preseason Outlook",
        "Transfer Portal Changes:",
        team_first_header=True,
    )
    season_portal = portal[portal["season"].astype("Int64") == int(portal_season)].copy() if not portal.empty else pd.DataFrame()
    team_key = normalize_key(team)
    incoming = season_portal[season_portal["destination"].map(normalize_key) == team_key].copy() if not season_portal.empty else pd.DataFrame()
    outgoing = season_portal[season_portal["origin"].map(normalize_key) == team_key].copy() if not season_portal.empty else pd.DataFrame()
    top_in = top_transfers(incoming)
    top_out = top_transfers(outgoing)
    impact = total_position_impact(incoming, outgoing) if not incoming.empty or not outgoing.empty else 0.0
    balance = portal_balance(incoming, outgoing)
    national_rank, conference_rank = portal_impact_rank_context(team, season_portal)

    impact_color = "#16a34a" if impact > 0 else "#dc2626" if impact < 0 else "#64748b"
    draw.rounded_rectangle((58, 382, 1022, 535), radius=30, fill="#ffffff", outline="#dbe4ee", width=2)
    draw_text(draw, (88, 412), "POSITION-ADJUSTED NET IMPACT", "#64748b", font(22, bold=True))
    draw_text(draw, (88, 452), f"{impact:+.2f}", impact_color, font(58, bold=True))
    summary = f"{len(incoming)} in / {len(outgoing)} out / {len(incoming) - len(outgoing):+d} net"
    draw_text(draw, (332, 444), fit_text(draw, summary, font(24, bold=True), 374), "#0f172a", font(24, bold=True))
    draw_text(
        draw,
        (332, 484),
        fit_text(draw, "Weighted for position scarcity and depth", font(16), 374),
        "#64748b",
        font(16),
    )
    draw_rank_pill(draw, (732, 405, 996, 458), "National", national_rank, soft_color)
    draw_rank_pill(draw, (732, 469, 996, 522), "Conference", conference_rank, "#f8fafc")

    draw.rounded_rectangle((58, 585, 515, 1010), radius=26, fill=soft_color, outline="#cbd5e1", width=2)
    draw.rounded_rectangle((565, 585, 1022, 1010), radius=26, fill="#fff7ed", outline="#fed7aa", width=2)
    draw_text(draw, (88, 618), "TOP ADDITIONS", "#0f172a", font(25, bold=True))
    draw_text(draw, (595, 618), "TOP LOSSES", "#0f172a", font(25, bold=True))

    logo_url = safe_text(meta.get("team_logo")) or safe_text(meta.get("team_logo_dark"))
    for idx in range(5):
        y = 660 + idx * 67
        if idx < len(top_in):
            row = top_in.iloc[idx]
            detail = f"{safe_text(row.get('position'), 'UNK')} from {safe_text(row.get('origin'), 'Unknown')}"
            draw_table_row(canvas, draw, y, team, logo_url, row["player"], detail, f"{row['rating']:.2f}" if pd.notna(row["rating"]) else "N/R", team_color, 84, 491, row_h=58)
        else:
            draw.rounded_rectangle((84, y, 491, y + 56), radius=14, fill="#ffffff", outline="#e2e8f0", width=1)
            draw_text(draw, (106, y + 17), "No rated addition", "#94a3b8", font(20, bold=True))
        if idx < len(top_out):
            row = top_out.iloc[idx]
            detail = f"{safe_text(row.get('position'), 'UNK')} to {safe_text(row.get('destination'), 'Uncommitted')}"
            draw_table_row(canvas, draw, y, team, logo_url, row["player"], detail, f"{row['rating']:.2f}" if pd.notna(row["rating"]) else "N/R", "#dc2626", 591, 998, row_h=58)
        else:
            draw.rounded_rectangle((591, y, 998, y + 56), radius=14, fill="#ffffff", outline="#e2e8f0", width=1)
            draw_text(draw, (613, y + 17), "No rated loss", "#94a3b8", font(20, bold=True))

    draw.rounded_rectangle((58, 1052, 1022, 1226), radius=24, fill="#ffffff", outline="#dbe4ee", width=2)
    draw_text(draw, (390, 1080), "POSITION IMPACT CHANGES", "#64748b", font(21, bold=True))
    if not balance.empty:
        gained = balance[balance["impact"] > 0].sort_values("impact", ascending=False).head(2)
        lost = balance[balance["impact"] < 0].sort_values("impact", ascending=True).head(2)
        draw_text(draw, (292, 1117), "BIGGEST GAINS", "#16a34a", font(20, bold=True), "mm")
        draw_text(draw, (788, 1117), "BIGGEST LOSSES", "#dc2626", font(20, bold=True), "mm")
        for idx, row in enumerate(gained.itertuples(index=False)):
            x = 84 + idx * 220
            draw_position_swing_chip(draw, (x, 1140, x + 204, 1208), row.position, int(row.net), float(row.impact), "#ecfdf5", "#bbf7d0", "#16a34a")
        for idx, row in enumerate(lost.itertuples(index=False)):
            x = 580 + idx * 220
            draw_position_swing_chip(draw, (x, 1140, x + 204, 1208), row.position, int(row.net), float(row.impact), "#fef2f2", "#fecaca", "#dc2626")
        if gained.empty:
            draw_text(draw, (292, 1172), "No positive position impact", "#94a3b8", font(20, bold=True), "mm")
        if lost.empty:
            draw_text(draw, (788, 1172), "No negative position impact", "#94a3b8", font(20, bold=True), "mm")
    else:
        draw_text(draw, (540, 1142), "No transfer movement found for this season.", "#64748b", font(23, bold=True), "mm")

    return png_bytes(canvas)


def schedule_slide(team: str, meta: pd.Series, schedule_season: int, context_season: int) -> bytes:
    canvas, draw, team_color, _, soft_color = begin_slide(team, meta, "Schedule Analysis", f"{schedule_season} Schedule Shape")
    schedule = load_schedule(team, schedule_season)
    if schedule.empty:
        draw_text(draw, (72, 450), "No schedule found for this team/season.", "#0f172a", font(36, bold=True))
        return png_bytes(canvas)

    home_count = 0
    away_count = 0
    neutral_count = 0
    ranked_count = 0
    opponent_rows = []
    for idx, row in schedule.iterrows():
        is_home = row.get("hometeam") == team
        opponent = row.get("awayteam") if is_home else row.get("hometeam")
        opponent_id = row.get("awayid") if is_home else row.get("homeid")
        neutral = truthy(row.get("neutral_site"))
        location = "Neutral" if neutral else "Home" if is_home else "Away"
        if location == "Home":
            home_count += 1
        elif location == "Away":
            away_count += 1
        else:
            neutral_count += 1
        rank = opponent_rank(opponent, context_season)
        if rank.startswith("#"):
            ranked_count += 1
        opponent_rows.append(
            {
                "week": int(row["week"]) if pd.notna(row.get("week")) else idx + 1,
                "date": row["startdate"].strftime("%b %-d") if pd.notna(row.get("startdate")) else "",
                "opponent": safe_text(opponent, "TBD"),
                "opponent_id": normalize_id(opponent_id),
                "location": location,
                "venue": safe_text(row.get("venue"), ""),
                "record": opponent_record(opponent, context_season),
                "rank": rank,
            }
        )

    draw_stat_card(draw, (58, 382, 294, 510), "Home", str(home_count), team_color)
    draw_stat_card(draw, (316, 382, 552, 510), "Away", str(away_count), team_color)
    draw_stat_card(draw, (574, 382, 810, 510), "Neutral", str(neutral_count), team_color)
    draw_stat_card(draw, (832, 382, 1022, 510), f"{context_season} AP", str(ranked_count), team_color, "ranked foes")

    draw.rounded_rectangle((58, 554, 1022, 1162), radius=28, fill="#ffffff", outline="#dbe4ee", width=2)
    draw_text(draw, (86, 584), "OPPONENT SNAPSHOT", "#0f172a", font(27, bold=True))
    draw_text(draw, (720, 590), f"{context_season} record", "#64748b", font(18, bold=True))
    draw_text(draw, (904, 590), "Final AP", "#64748b", font(18, bold=True))

    assets = load_team_assets()
    logo_by_id = assets[assets["team_id"].astype(bool)].drop_duplicates("team_id").set_index("team_id") if not assets.empty else pd.DataFrame()
    logo_by_key = assets[assets["team_key"].astype(bool)].drop_duplicates("team_key").set_index("team_key") if not assets.empty else pd.DataFrame()

    max_rows = min(13, len(opponent_rows))
    row_h = 41 if max_rows > 12 else 44
    for idx, row in enumerate(opponent_rows[:max_rows]):
        y = 632 + idx * row_h
        fill = "#f8fafc" if idx % 2 == 0 else "#ffffff"
        draw.rounded_rectangle((82, y, 998, y + row_h - 6), radius=12, fill=fill)
        logo_url = ""
        if row["opponent_id"] and not logo_by_id.empty and row["opponent_id"] in logo_by_id.index:
            logo_url = safe_text(logo_by_id.loc[row["opponent_id"]].get("team_logo")) or safe_text(logo_by_id.loc[row["opponent_id"]].get("team_logo_dark"))
        if not logo_url and not logo_by_key.empty and normalize_key(row["opponent"]) in logo_by_key.index:
            asset = logo_by_key.loc[normalize_key(row["opponent"])]
            logo_url = safe_text(asset.get("team_logo")) or safe_text(asset.get("team_logo_dark"))
        draw_logo_or_initials(canvas, draw, row["opponent"], logo_url, (96, y + 5, 126, y + 35), "#ffffff")
        loc_token = "vs" if row["location"] == "Home" else "at" if row["location"] == "Away" else "N"
        draw_text(draw, (144, y + 9), f"Wk {row['week']}", "#64748b", font(17, bold=True))
        draw_text(draw, (218, y + 9), row["date"], "#64748b", font(17))
        draw_text(draw, (304, y + 8), loc_token, team_color, font(18, bold=True))
        draw_text(draw, (344, y + 7), fit_text(draw, row["opponent"], font(20, bold=True), 330), "#0f172a", font(20, bold=True))
        draw_text(draw, (742, y + 8), row["record"], "#0f172a", font(20, bold=True))
        rank_fill = team_color if row["rank"].startswith("#") else soft_color
        rank_text = contrast_text(rank_fill) if row["rank"].startswith("#") else "#475569"
        draw.rounded_rectangle((890, y + 5, 970, y + 35), radius=11, fill=rank_fill)
        draw_text(draw, (930, y + 20), row["rank"].replace("Unranked", "UR"), rank_text, font(16, bold=True), "mm")

    if len(opponent_rows) > max_rows:
        draw_text(draw, (86, 1130), f"+ {len(opponent_rows) - max_rows} more games not shown", "#64748b", font(18, bold=True))

    return png_bytes(canvas)


def build_zip(slides: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, data in slides.items():
            archive.writestr(filename, data)
    return output.getvalue()


def season_index(options: list[int], preferred: int) -> int:
    return options.index(preferred) if preferred in options else 0


st.markdown('<div class="sott-title">State of the Team</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sott-subtitle">Preseason social-slide mockups: results, transfer movement, and schedule shape.</div>',
    unsafe_allow_html=True,
)

fbs_metadata = load_fbs_team_metadata()
if fbs_metadata.empty:
    st.info("No FBS team metadata found.")
    st.stop()

teams = fbs_metadata.sort_values("team")["team"].dropna().astype(str).tolist()
portal = load_transfer_portal()
if "_missing_columns" in portal.columns:
    st.warning(f"The `{TRANSFER_TABLE}` table is missing required columns: {portal['_missing_columns'].iloc[0]}")
    portal = pd.DataFrame()

try:
    game_seasons_df = read_df("SELECT DISTINCT season FROM public.game_data WHERE season IS NOT NULL ORDER BY season DESC")
    game_seasons = game_seasons_df["season"].astype(int).tolist()
except Exception:
    game_seasons = [2026, 2025]

portal_seasons = (
    sorted(portal["season"].dropna().astype(int).unique().tolist(), reverse=True)
    if not portal.empty and "season" in portal.columns
    else game_seasons
)

control_cols = st.columns([2.2, 1, 1, 1])
with control_cols[0]:
    selected_team = st.selectbox("FBS school", teams, index=0)
with control_cols[1]:
    results_season = st.selectbox("Results season", game_seasons, index=season_index(game_seasons, 2025))
with control_cols[2]:
    selected_portal_season = st.selectbox("Portal season", portal_seasons, index=season_index(portal_seasons, 2026))
with control_cols[3]:
    schedule_season = st.selectbox("Schedule season", game_seasons, index=season_index(game_seasons, 2026))

team_meta = selected_team_metadata(fbs_metadata, selected_team)
slides = {
    f"{slugify(selected_team)}_{results_season}_results.png": results_slide(
        selected_team,
        team_meta,
        int(results_season),
        int(schedule_season),
    ),
    f"{slugify(selected_team)}_{selected_portal_season}_transfer_portal.png": transfer_slide(
        selected_team,
        team_meta,
        int(selected_portal_season),
        portal,
    ),
    f"{slugify(selected_team)}_{schedule_season}_schedule.png": schedule_slide(
        selected_team,
        team_meta,
        int(schedule_season),
        int(results_season),
    ),
}

zip_data = build_zip(slides)
st.download_button(
    "Export all 3 slides as ZIP",
    data=zip_data,
    file_name=f"{slugify(selected_team)}_preseason_slide_pack.zip",
    mime="application/zip",
    use_container_width=True,
)

tabs = st.tabs(["2025 Results", "Transfer Portal", "2026 Schedule"])
for tab, (filename, image_bytes) in zip(tabs, slides.items()):
    with tab:
        left, right = st.columns([0.72, 0.28], vertical_alignment="top")
        with left:
            st.image(image_bytes, use_container_width=True)
        with right:
            st.download_button(
                "Export PNG",
                data=image_bytes,
                file_name=filename,
                mime="image/png",
                use_container_width=True,
                key=f"download_{filename}",
            )
            st.caption(f"{SLIDE_W} x {SLIDE_H}px")

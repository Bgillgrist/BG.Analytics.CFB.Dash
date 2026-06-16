import datetime as dt
from io import BytesIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from utils.db import read_df


TRANSFER_TABLE = "transfer_portal"
APP_LOGO_COLOR_PATH = Path(__file__).resolve().parents[1] / "assets" / "logo_color.PNG"
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
POSITION_TO_DETAIL_ORDER = {
    position: index
    for positions in POSITION_DETAIL_ORDER.values()
    for index, position in enumerate(positions)
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
SIDE_OF_BALL = {
    "QB": "Offense",
    "RB": "Offense",
    "WR": "Offense",
    "TE": "Offense",
    "OL": "Offense",
    "DL": "Defense",
    "LB": "Defense",
    "DB": "Defense",
}
st.markdown(
    """
    <style>
      .portal-title {
        font-size: 2.1rem;
        font-weight: 800;
        margin: -0.5rem 0 0.75rem;
      }
      .portal-subtitle {
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


def first_existing(columns: set[str], candidates: list[str]) -> str | None:
    exact = next((column for column in candidates if column in columns), None)
    if exact:
        return exact

    lower_lookup = {column.lower(): column for column in columns}
    return next((lower_lookup[candidate.lower()] for candidate in candidates if candidate.lower() in lower_lookup), None)


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
def load_transfer_portal() -> pd.DataFrame:
    columns = get_table_columns(TRANSFER_TABLE)
    if not columns:
        return pd.DataFrame()

    field_candidates = {
        "season": ["Season", "season", "year"],
        "first_name": ["FirstName", "firstname", "first_name", "first", "first_name"],
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

    df = read_df(
        f"""
        SELECT
            {", ".join(select_parts)}
        FROM public.{quote_identifier(TRANSFER_TABLE)}
        """,
    )
    if df.empty:
        return df

    df["season"] = pd.to_numeric(df["season"], errors="coerce").astype("Int64")
    df["first_name"] = df["first_name"].fillna("").astype(str).str.strip()
    df["last_name"] = df["last_name"].fillna("").astype(str).str.strip()
    df["player"] = (df["first_name"] + " " + df["last_name"]).str.strip()
    df["position"] = df["position"].fillna("").astype(str).str.upper().str.strip()
    df["origin"] = clean_team_series(df["origin"])
    df["destination"] = clean_team_series(df["destination"])
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["stars"] = pd.to_numeric(df["stars"], errors="coerce")
    df["transfer_date"] = pd.to_datetime(df["transfer_date"], errors="coerce")
    df["eligibility"] = df["eligibility"].fillna("").astype(str).str.strip()
    df["position_group"] = df["position"].map(position_group)
    df["position_group_order"] = df["position_group"].map(POSITION_GROUP_ORDER).fillna(POSITION_GROUP_ORDER["OTHER"])
    df["position_detail_order"] = df["position"].map(POSITION_TO_DETAIL_ORDER).fillna(99)
    return df


def clean_team_series(series: pd.Series) -> pd.Series:
    return (
        series.fillna("")
        .astype(str)
        .str.strip()
        .replace({"nan": "", "None": "", "NULL": "", "null": ""})
    )


def position_group(position: object) -> str:
    pos = str(position or "").upper().strip()
    return POSITION_TO_GROUP.get(pos, "OTHER")


def transfer_display(df: pd.DataFrame, direction: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=["Player", "Pos", "From", "To", "Rating", "Stars", "Eligibility", "Transfer Date"]
        )

    display = df.sort_values(
        ["position_group_order", "rating", "position_detail_order", "player"],
        ascending=[True, False, True, True],
        na_position="last",
    ).copy()
    display["Rating"] = display["rating"].map(lambda value: "" if pd.isna(value) else f"{value:.2f}")
    display["Stars"] = display["stars"].map(lambda value: "" if pd.isna(value) else f"{int(value)}")
    display["Transfer Date"] = display["transfer_date"].dt.strftime("%b %-d, %Y").fillna("")
    display["From"] = display["origin"].replace("", "Unknown")
    display["To"] = display["destination"].replace("", "Uncommitted")
    display["Player"] = display["player"].replace("", "Unknown")
    display["Pos"] = display["position"].replace("", "UNK")
    display["Eligibility"] = display["eligibility"]
    columns = ["Player", "Pos", "From", "To", "Rating", "Stars", "Eligibility", "Transfer Date"]
    if direction == "incoming":
        columns.remove("To")
    elif direction == "outgoing":
        columns.remove("From")
    return display[columns]


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


def valid_hex_color(value: object) -> str:
    value_str = str(value or "").strip()
    if not value_str:
        return ""
    if not value_str.startswith("#"):
        value_str = f"#{value_str}"
    if len(value_str) == 7 and all(char in "0123456789abcdefABCDEF" for char in value_str[1:]):
        return value_str
    return ""


def team_options(df: pd.DataFrame) -> list[str]:
    teams = pd.concat([df["origin"], df["destination"]], ignore_index=True)
    return sorted(team for team in teams.dropna().astype(str).str.strip().unique().tolist() if team)


def fbs_team_options(df: pd.DataFrame, fbs_metadata: pd.DataFrame) -> list[str]:
    if fbs_metadata.empty:
        return []
    fbs_keys = set(fbs_metadata["team_key"].dropna().astype(str))
    teams = team_options(df)
    return sorted(team for team in teams if normalize_key(team) in fbs_keys)


def rating_delta_metric(incoming_rating: float, outgoing_rating: float) -> str:
    if pd.isna(incoming_rating) or pd.isna(outgoing_rating):
        return "N/A"
    return f"{incoming_rating - outgoing_rating:+.2f}"


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
    return (
        depth_score
        + float(weights["top_quality"]) * float(top_quality)
        + float(weights["avg_quality"]) * float(avg_quality)
    )


def total_position_impact(incoming: pd.DataFrame, outgoing: pd.DataFrame) -> float:
    total = 0.0
    for group in POSITION_GROUP_ORDER:
        group_incoming = incoming[incoming["position_group"] == group]
        group_outgoing = outgoing[outgoing["position_group"] == group]
        total += position_side_impact(group_incoming, group) - position_side_impact(group_outgoing, group)
    return total


def team_portal_impact_table(season_portal: pd.DataFrame, fbs_metadata: pd.DataFrame) -> pd.DataFrame:
    if season_portal.empty or fbs_metadata.empty:
        return pd.DataFrame()

    portal_with_keys = season_portal.copy()
    portal_with_keys["origin_key"] = portal_with_keys["origin"].map(normalize_key)
    portal_with_keys["destination_key"] = portal_with_keys["destination"].map(normalize_key)

    rows = []
    teams = fbs_metadata.drop_duplicates("team_key").sort_values("team")
    for team in teams.itertuples(index=False):
        team_key = str(team.team_key)
        incoming_team = portal_with_keys[portal_with_keys["destination_key"] == team_key]
        outgoing_team = portal_with_keys[portal_with_keys["origin_key"] == team_key]
        rows.append(
            {
                "Team": team.team,
                "Conference": team.conference,
                "Incoming": len(incoming_team),
                "Outgoing": len(outgoing_team),
                "Net Transfers": len(incoming_team) - len(outgoing_team),
                "Portal Impact": total_position_impact(incoming_team, outgoing_team),
            }
        )

    impact_table = pd.DataFrame(rows)
    if impact_table.empty:
        return impact_table

    impact_table = impact_table.sort_values(
        ["Portal Impact", "Net Transfers", "Incoming", "Team"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    impact_table.insert(0, "Rank", impact_table.index + 1)
    return impact_table


def position_balance_data(incoming: pd.DataFrame, outgoing: pd.DataFrame) -> pd.DataFrame:
    position_rows = []
    for group, order in POSITION_GROUP_ORDER.items():
        group_incoming = incoming[incoming["position_group"] == group].copy()
        group_outgoing = outgoing[outgoing["position_group"] == group].copy()
        incoming_count = len(group_incoming)
        outgoing_count = len(group_outgoing)
        net_change = incoming_count - outgoing_count
        impact_score = position_side_impact(group_incoming, group) - position_side_impact(group_outgoing, group)
        if incoming_count == 0 and outgoing_count == 0 and group == "OTHER":
            continue

        incoming_avg = group_incoming["rating"].dropna().mean()
        outgoing_avg = group_outgoing["rating"].dropna().mean()
        position_rows.append(
            {
                "position": group,
                "order": order,
                "incoming_count": incoming_count,
                "outgoing_count": outgoing_count,
                "net_change": net_change,
                "impact_score": impact_score,
                "incoming_avg": incoming_avg,
                "outgoing_avg": outgoing_avg,
                "rating_delta": rating_delta_metric(incoming_avg, outgoing_avg),
            }
        )

    return pd.DataFrame(position_rows).sort_values("order")


def position_balance_figure(incoming: pd.DataFrame, outgoing: pd.DataFrame, season_portal: pd.DataFrame) -> go.Figure:
    balance = position_balance_data(incoming, outgoing)
    if balance.empty:
        fig = go.Figure()
        fig.update_layout(
            height=360,
            margin=dict(l=0, r=0, t=10, b=0),
            annotations=[
                dict(
                    text="No position transfer activity for this selection.",
                    x=0.5,
                    y=0.5,
                    xref="paper",
                    yref="paper",
                    showarrow=False,
                )
            ],
        )
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return fig

    y_positions = balance["position"].tolist()
    max_impact = max(float(balance["impact_score"].abs().max()), 1.0)
    hover_text = balance.apply(
        lambda row: (
            f"Position Group: {row['position']}<br>"
            f"Net Change: {row['net_change']:+d}<br>"
            f"Net Avg Rating Change: {row['rating_delta']}"
        ),
        axis=1,
    )
    bar_colors = balance["impact_score"].map(lambda value: "#16a34a" if value > 0 else "#dc2626" if value < 0 else "#94a3b8")

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            y=y_positions,
            x=balance["impact_score"],
            orientation="h",
            marker_color=bar_colors,
            marker_line=dict(color="rgba(15, 23, 42, 0.12)", width=1),
            customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>",
            text=balance["impact_score"].map(lambda value: f"{value:+.2f}"),
            textposition="outside",
            cliponaxis=False,
            showlegend=False,
        )
    )
    fig.add_vline(x=0, line_width=1, line_color="#64748b")
    fig.update_layout(
        height=max(430, len(balance) * 54),
        margin=dict(l=12, r=62, t=28, b=48),
        xaxis_title="Position-adjusted portal impact",
        font=dict(color="#0f172a"),
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8fafc",
    )
    fig.update_xaxes(
        range=[-(max_impact * 1.22), max_impact * 1.22],
        zeroline=False,
        gridcolor="#e2e8f0",
        linecolor="#cbd5e1",
    )
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=list(reversed(y_positions)),
        gridcolor="#eef2f7",
        linecolor="#cbd5e1",
    )
    return fig


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


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


def selected_team_metadata(fbs_metadata: pd.DataFrame, selected_team: str) -> pd.Series:
    if fbs_metadata.empty:
        return pd.Series(dtype="object")
    team_key = normalize_key(selected_team)
    rows = fbs_metadata[fbs_metadata["team_key"] == team_key]
    return rows.iloc[0] if not rows.empty else pd.Series(dtype="object")


def paste_logo(canvas: Image.Image, logo_url: str, box: tuple[int, int, int, int]) -> None:
    logo_bytes = fetch_logo_bytes(logo_url)
    if not logo_bytes:
        return
    try:
        logo = Image.open(BytesIO(logo_bytes)).convert("RGBA")
    except Exception:
        return

    max_w = box[2] - box[0]
    max_h = box[3] - box[1]
    logo.thumbnail((max_w, max_h), Image.LANCZOS)
    x = box[0] + (max_w - logo.width) // 2
    y = box[1] + (max_h - logo.height) // 2
    canvas.alpha_composite(logo, (x, y))


def paste_local_image(canvas: Image.Image, image_path: Path, box: tuple[int, int, int, int]) -> None:
    if not image_path.exists():
        return
    try:
        image = Image.open(image_path).convert("RGBA")
    except Exception:
        return

    max_w = box[2] - box[0]
    max_h = box[3] - box[1]
    image.thumbnail((max_w, max_h), Image.LANCZOS)
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


def logo_lookup_frame(fbs_metadata: pd.DataFrame) -> pd.DataFrame:
    frames = []
    assets = load_team_assets()
    if not assets.empty:
        frames.append(assets[["team_key", "team_logo", "team_logo_dark"]].copy())
    if not fbs_metadata.empty:
        frames.append(fbs_metadata[["team_key", "team_logo", "team_logo_dark"]].copy())
    if not frames:
        return pd.DataFrame(columns=["team_key", "team_logo", "team_logo_dark"])

    lookup = pd.concat(frames, ignore_index=True)
    lookup["team_key"] = lookup["team_key"].fillna("").astype(str)
    lookup["team_logo"] = lookup["team_logo"].fillna("").astype(str)
    lookup["team_logo_dark"] = lookup["team_logo_dark"].fillna("").astype(str)
    lookup = lookup[lookup["team_key"].astype(bool)]
    return lookup.drop_duplicates("team_key", keep="last").set_index("team_key")


def logo_url_for_team(team_name: object, logo_lookup: pd.DataFrame) -> str:
    team_key = normalize_key(team_name)
    if not team_key or logo_lookup.empty or team_key not in logo_lookup.index:
        return ""
    row = logo_lookup.loc[team_key]
    return str(row.get("team_logo", "") or row.get("team_logo_dark", "") or "")


def draw_team_logo_or_initials(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    team_name: object,
    logo_lookup: pd.DataFrame,
    box: tuple[int, int, int, int],
) -> None:
    logo_url = logo_url_for_team(team_name, logo_lookup)
    if logo_url:
        paste_logo(canvas, logo_url, box)
        return

    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0, y0, x1, y1), radius=10, fill="#e2e8f0", outline="#cbd5e1", width=1)
    draw_text(
        draw,
        ((x0 + x1) // 2, (y0 + y1) // 2),
        team_initials(team_name),
        "#334155",
        font(15, bold=True),
        anchor="mm",
    )


def draw_route_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    draw.line((start[0], start[1], end[0], end[1]), fill="#64748b", width=3)
    draw.polygon(
        [
            (end[0], end[1]),
            (end[0] - 8, end[1] - 6),
            (end[0] - 8, end[1] + 6),
        ],
        fill="#64748b",
    )


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    fill: str,
    text_font: ImageFont.ImageFont,
    anchor: str | None = None,
) -> None:
    draw.text(xy, text, fill=fill, font=text_font, anchor=anchor)


def portal_impact_png(
    incoming: pd.DataFrame,
    outgoing: pd.DataFrame,
    selected_team: str,
    selected_season: int,
    fbs_metadata: pd.DataFrame,
    portal_impact: float,
) -> bytes:
    size = 1080
    canvas = Image.new("RGBA", (size, size), "#f8fafc")
    draw = ImageDraw.Draw(canvas)
    team_meta = selected_team_metadata(fbs_metadata, selected_team)
    team_color = valid_hex_color(team_meta.get("team_color", "")) or "#0f172a"
    logo_url = str(team_meta.get("team_logo_dark", "") or team_meta.get("team_logo", "") or "")

    draw.rounded_rectangle((40, 40, 1040, 1040), radius=34, fill="#ffffff", outline="#dbe4ee", width=2)
    draw.rounded_rectangle((40, 40, 1040, 170), radius=34, fill=team_color)
    draw.rectangle((40, 118, 1040, 170), fill=team_color)
    draw_text(draw, (76, 66), selected_team, "#ffffff", font(42, bold=True))
    draw_text(draw, (78, 114), f"{selected_season} transfer portal impact", "#e2e8f0", font(23))
    paste_logo(canvas, logo_url, (876, 58, 1018, 154))

    metric_specs = [
        ("Incoming", f"{len(incoming):,}"),
        ("Outgoing", f"{len(outgoing):,}"),
        ("Net", f"{len(incoming) - len(outgoing):+d}"),
        ("Impact", f"{portal_impact:+.2f}"),
    ]
    card_y = 200
    card_w = 226
    for index, (label, value) in enumerate(metric_specs):
        x0 = 60 + index * 246
        draw.rounded_rectangle((x0, card_y, x0 + card_w, card_y + 92), radius=16, fill="#f8fafc", outline="#e2e8f0", width=2)
        draw_text(draw, (x0 + 22, card_y + 18), label.upper(), "#64748b", font(17, bold=True))
        draw_text(draw, (x0 + 22, card_y + 46), value, "#0f172a", font(34, bold=True))

    balance = position_balance_data(incoming, outgoing)
    if balance.empty:
        draw_text(draw, (540, 560), "No position transfer activity", "#64748b", font(30, bold=True), anchor="mm")
    else:
        chart_left = 174
        chart_right = 986
        center_x = 580
        chart_top = 375
        row_h = 55
        max_impact = max(float(balance["impact_score"].abs().max()), 1.0)
        scale = (chart_right - center_x - 72) / max_impact

        draw_text(draw, (76, 322), "POSITION-ADJUSTED NET CHANGE", "#0f172a", font(25, bold=True))
        draw_text(draw, (982, 324), "IMPACT", "#64748b", font(18, bold=True), anchor="ra")
        draw.line((center_x, chart_top - 8, center_x, chart_top + row_h * len(balance) - 8), fill="#94a3b8", width=2)

        for idx, row in enumerate(balance.itertuples(index=False)):
            y = chart_top + idx * row_h
            y_mid = y + 22
            impact = float(row.impact_score)
            impact_label = f"{impact:+.2f}"
            bar_color = "#16a34a" if impact > 0 else "#dc2626" if impact < 0 else "#94a3b8"
            draw_text(draw, (76, y_mid), str(row.position), "#0f172a", font(23, bold=True), anchor="lm")

            if impact >= 0:
                x0, x1 = center_x, center_x + max(5, impact * scale)
            else:
                x0, x1 = center_x + min(-5, impact * scale), center_x
            draw.rounded_rectangle((int(x0), y + 8, int(x1), y + 37), radius=10, fill=bar_color)
            draw_text(draw, (982, y_mid), impact_label, "#0f172a", font(22, bold=True), anchor="ra")

        draw_text(
            draw,
            (76, 942),
            "Bar length and end label reflect position-adjusted portal impact.",
            "#64748b",
            font(19),
        )

    draw_text(draw, (850, 988), "@BG.Analytics", "#0f172a", font(24, bold=True))
    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def available_transfer_dates(df: pd.DataFrame) -> tuple[dt.date | None, dt.date | None]:
    dates = df["transfer_date"].dropna()
    if dates.empty:
        return None, None
    return dates.dt.date.min(), dates.dt.date.max()


def league_headline_transfers(
    df: pd.DataFrame,
    start_date: dt.date | None,
    end_date: dt.date | None,
    fbs_metadata: pd.DataFrame,
    limit: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty or fbs_metadata.empty:
        return pd.DataFrame(), pd.DataFrame()

    filtered = df.copy()
    if start_date and end_date:
        transfer_dates = filtered["transfer_date"].dt.date
        filtered = filtered[transfer_dates.between(start_date, end_date)]

    fbs_destination_keys = set(fbs_metadata["team_key"].dropna().astype(str))
    filtered = filtered[filtered["destination"].map(normalize_key).isin(fbs_destination_keys)].copy()
    if filtered.empty:
        return pd.DataFrame(), pd.DataFrame()

    filtered["side"] = filtered["position_group"].map(SIDE_OF_BALL)
    filtered = filtered[filtered["side"].isin(["Offense", "Defense"]) & filtered["rating"].notna()].copy()
    if filtered.empty:
        return pd.DataFrame(), pd.DataFrame()

    filtered["origin_display"] = filtered["origin"].replace("", "Unknown")
    filtered["destination_display"] = filtered["destination"].replace("", "Uncommitted")
    filtered["player_display"] = filtered["player"].replace("", "Unknown")
    filtered = filtered.sort_values(
        ["rating", "stars", "transfer_date", "player_display"],
        ascending=[False, False, False, True],
        na_position="last",
    )
    offense = filtered[filtered["side"] == "Offense"].head(limit).reset_index(drop=True)
    defense = filtered[filtered["side"] == "Defense"].head(limit).reset_index(drop=True)
    return offense, defense


def date_range_label(start_date: dt.date | None, end_date: dt.date | None) -> str:
    if not start_date or not end_date:
        return "All transfer dates"
    if start_date == end_date:
        return start_date.strftime("%b %-d, %Y")
    return f"{start_date.strftime('%b %-d, %Y')} - {end_date.strftime('%b %-d, %Y')}"


def fit_text(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.ImageFont, max_width: int) -> str:
    text = str(text)
    if draw.textlength(text, font=text_font) <= max_width:
        return text

    ellipsis = "..."
    while text and draw.textlength(f"{text}{ellipsis}", font=text_font) > max_width:
        text = text[:-1]
    return f"{text}{ellipsis}" if text else ellipsis


def draw_headline_column(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    title: str,
    transfers: pd.DataFrame,
    box: tuple[int, int, int, int],
    accent_color: str,
    logo_lookup: pd.DataFrame,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=24, fill="#ffffff", outline="#dbe4ee", width=2)
    draw.rounded_rectangle((x0, y0, x1, y0 + 72), radius=24, fill=accent_color)
    draw.rectangle((x0, y0 + 40, x1, y0 + 72), fill=accent_color)
    draw_text(draw, (x0 + 28, y0 + 22), title.upper(), "#ffffff", font(25, bold=True))

    if transfers.empty:
        draw_text(draw, ((x0 + x1) // 2, (y0 + y1) // 2), "No rated transfers", "#64748b", font(24, bold=True), anchor="mm")
        return

    row_top = y0 + 92
    row_h = 122
    for index, row in enumerate(transfers.itertuples(index=False), start=1):
        y = row_top + (index - 1) * row_h
        row_fill = "#f8fafc" if index % 2 else "#ffffff"
        draw.rounded_rectangle((x0 + 18, y, x1 - 18, y + 102), radius=16, fill=row_fill, outline="#e2e8f0", width=1)
        draw.ellipse((x0 + 34, y + 16, x0 + 78, y + 60), fill=accent_color)
        draw_text(draw, (x0 + 56, y + 38), str(index), "#ffffff", font(22, bold=True), anchor="mm")

        rating = "" if pd.isna(row.rating) else f"{float(row.rating):.2f}"
        draw.rounded_rectangle((x1 - 112, y + 12, x1 - 36, y + 48), radius=12, fill="#0f172a")
        draw_text(draw, (x1 - 74, y + 30), rating, "#ffffff", font(18, bold=True), anchor="mm")

        player_name = fit_text(draw, str(row.player_display), font(26, bold=True), x1 - x0 - 238)
        position = str(row.position or "UNK")
        transfer_date = "" if pd.isna(row.transfer_date) else row.transfer_date.strftime("%b %-d")

        draw_text(draw, (x0 + 56, y + 78), position, "#475569", font(16, bold=True), anchor="mm")
        draw_text(draw, (x0 + 96, y + 16), player_name, "#0f172a", font(26, bold=True))

        logo_y0 = y + 58
        logo_size = 30
        origin_box = (x0 + 98, logo_y0, x0 + 98 + logo_size, logo_y0 + logo_size)
        destination_box = (x0 + 176, logo_y0, x0 + 176 + logo_size, logo_y0 + logo_size)
        draw_team_logo_or_initials(canvas, draw, row.origin_display, logo_lookup, origin_box)
        draw_route_arrow(draw, (x0 + 138, logo_y0 + 15), (x0 + 166, logo_y0 + 15))
        draw_team_logo_or_initials(canvas, draw, row.destination_display, logo_lookup, destination_box)
        if transfer_date:
            draw_text(draw, (x0 + 226, y + 66), transfer_date, "#64748b", font(17, bold=True))


def league_headlines_png(
    offense: pd.DataFrame,
    defense: pd.DataFrame,
    selected_season: int,
    start_date: dt.date | None,
    end_date: dt.date | None,
    fbs_metadata: pd.DataFrame,
) -> bytes:
    size = 1080
    canvas = Image.new("RGBA", (size, size), "#f8fafc")
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((40, 40, 1040, 1040), radius=34, fill="#ffffff", outline="#dbe4ee", width=2)
    draw.rounded_rectangle((40, 40, 1040, 170), radius=34, fill="#0f172a")
    draw.rectangle((40, 118, 1040, 170), fill="#0f172a")
    draw_text(draw, (76, 66), "TRANSFER PORTAL HEADLINES", "#ffffff", font(39, bold=True))
    draw_text(draw, (78, 116), f"{date_range_label(start_date, end_date)}", "#cbd5e1", font(22))

    paste_local_image(canvas, APP_LOGO_COLOR_PATH, (850, 10, 1040, 200))

    logo_lookup = logo_lookup_frame(fbs_metadata)
    draw_headline_column(canvas, draw, "Top 5 Offense", offense, (72, 214, 518, 916), "#0c2c56", logo_lookup)
    draw_headline_column(canvas, draw, "Top 5 Defense", defense, (562, 214, 1008, 916), "#f53e22", logo_lookup)
    draw_text(draw, (76, 960), "Ranked by transfer rating among players with a listed rating.", "#64748b", font(19))
    draw_text(draw, (850, 988), "@BG.Analytics", "#0f172a", font(24, bold=True))

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


st.markdown('<div class="portal-title">Transfer Portal</div>', unsafe_allow_html=True)

portal = load_transfer_portal()
if "_missing_columns" in portal.columns:
    st.error(f"The `{TRANSFER_TABLE}` table is missing required columns: {portal['_missing_columns'].iloc[0]}")
    st.stop()

if portal.empty:
    st.info(f"No transfer portal data found in `public.{TRANSFER_TABLE}`.")
    st.stop()

seasons = sorted(portal["season"].dropna().astype(int).unique().tolist(), reverse=True)
if not seasons:
    st.info("No transfer portal seasons are available.")
    st.stop()

top_left, top_right = st.columns([3, 1])
with top_right:
    selected_season = st.selectbox("Season", seasons, index=0)

season_portal = portal[portal["season"] == selected_season].copy()
fbs_metadata = load_fbs_team_metadata()
teams = fbs_team_options(season_portal, fbs_metadata)
if not teams:
    st.info("No FBS teams are available for the selected season.")
    st.stop()

with top_left:
    selected_team = st.selectbox("Team", teams, index=0)

incoming = season_portal[season_portal["destination"] == selected_team].copy()
outgoing = season_portal[season_portal["origin"] == selected_team].copy()
portal_impact = total_position_impact(incoming, outgoing)
team_meta = selected_team_metadata(fbs_metadata, selected_team)
team_logo_url = str(team_meta.get("team_logo", "") or "")

metric_cols = st.columns(4)
metric_cols[0].metric("Incoming", f"{len(incoming):,}")
metric_cols[1].metric("Outgoing", f"{len(outgoing):,}")
metric_cols[2].metric("Net Transfers", f"{len(incoming) - len(outgoing):+,}")
metric_cols[3].metric("Portal Impact", f"{portal_impact:+.2f}")

st.divider()
st.subheader(f"{selected_team} Transfers")
incoming_col, outgoing_col = st.columns(2)
with incoming_col:
    st.markdown("#### Incoming")
    incoming_display = transfer_display(incoming, "incoming")
    if incoming_display.empty:
        st.caption("No incoming transfers for this selection.")
    else:
        st.dataframe(incoming_display, use_container_width=True, hide_index=True, height=430)

with outgoing_col:
    st.markdown("#### Outgoing")
    outgoing_display = transfer_display(outgoing, "outgoing")
    if outgoing_display.empty:
        st.caption("No outgoing transfers for this selection.")
    else:
        st.dataframe(outgoing_display, use_container_width=True, hide_index=True, height=430)

st.divider()
impact_header_cols = st.columns([0.45, 2.55, 1])
with impact_header_cols[0]:
    if team_logo_url:
        st.image(team_logo_url, width=72)
with impact_header_cols[1]:
    st.subheader(f"{selected_team} Transfer Portal Changes")
with impact_header_cols[2]:
    export_png = portal_impact_png(
        incoming,
        outgoing,
        selected_team,
        selected_season,
        fbs_metadata,
        portal_impact,
    )
    st.download_button(
        "Export PNG",
        data=export_png,
        file_name=f"{normalize_key(selected_team).replace(' ', '_')}_{selected_season}_portal_impact.png",
        mime="image/png",
        use_container_width=True,
    )

balance_fig = position_balance_figure(incoming, outgoing, season_portal)
st.plotly_chart(balance_fig, use_container_width=True, key=f"position_balance_{selected_season}_{selected_team}")

st.divider()
st.subheader("League-Wide Transfer Portal Headlines")
min_transfer_date, max_transfer_date = available_transfer_dates(season_portal)
if not min_transfer_date or not max_transfer_date:
    st.caption("No transfer dates are available for this season.")
else:
    default_start = max(min_transfer_date, max_transfer_date - dt.timedelta(days=30))
    news_control_cols = st.columns([2, 1])
    with news_control_cols[0]:
        selected_date_range = st.date_input(
            "Date range",
            value=(default_start, max_transfer_date),
            min_value=min_transfer_date,
            max_value=max_transfer_date,
        )

    if isinstance(selected_date_range, tuple):
        if len(selected_date_range) == 2:
            news_start_date, news_end_date = selected_date_range
        elif len(selected_date_range) == 1:
            news_start_date = news_end_date = selected_date_range[0]
        else:
            news_start_date, news_end_date = default_start, max_transfer_date
    else:
        news_start_date = news_end_date = selected_date_range

    if news_start_date > news_end_date:
        news_start_date, news_end_date = news_end_date, news_start_date

    headline_offense, headline_defense = league_headline_transfers(
        season_portal,
        news_start_date,
        news_end_date,
        fbs_metadata,
    )
    news_png = league_headlines_png(
        headline_offense,
        headline_defense,
        selected_season,
        news_start_date,
        news_end_date,
        fbs_metadata,
    )

    with news_control_cols[1]:
        st.download_button(
            "Export Headlines PNG",
            data=news_png,
            file_name=f"{selected_season}_transfer_portal_headlines_{news_start_date}_{news_end_date}.png",
            mime="image/png",
            use_container_width=True,
        )

    if headline_offense.empty and headline_defense.empty:
        st.caption("No rated offensive or defensive transfers found for this date range.")
    st.image(news_png, use_container_width=True)

st.divider()
st.subheader("Team Portal Impact Rankings")
impact_table = team_portal_impact_table(season_portal, fbs_metadata)
if impact_table.empty:
    st.caption("No team portal impact data is available for this season.")
else:
    st.dataframe(
        impact_table,
        use_container_width=True,
        hide_index=True,
        height=560,
        column_config={
            "Portal Impact": st.column_config.NumberColumn("Portal Impact", format="%.2f"),
            "Net Transfers": st.column_config.NumberColumn("Net Transfers", format="%+d"),
        },
    )

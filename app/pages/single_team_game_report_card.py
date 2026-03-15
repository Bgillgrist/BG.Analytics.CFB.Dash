import streamlit as st
import pandas as pd
from utils.db import read_df

# ============================
# STYLING
# ============================

def _apply_styles() -> None:
    """Apply all custom CSS for report cards."""
    st.markdown(
        """
        <style>
          div[data-testid="stSelectbox"] { margin-top: -1rem; }
          .rc-card {
            border: 1px solid rgba(49, 51, 63, 0.2);
            border-radius: 10px;
            padding: 0.65rem 0.75rem;
            margin: 0.35rem 0 0.65rem 0;
            background: rgba(255, 255, 255, 0.02);
          }
          .rc-card .rc-head {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            margin-bottom: 0.4rem;
          }
          .rc-card .rc-title {
            font-weight: 800;
            font-size: 1.22rem;
            letter-spacing: 0.2px;
            margin: 0;
          }
          .rc-grid {
            display: grid;
            grid-template-columns: 88px 1fr;
            gap: 0.35rem 0.6rem;
            align-items: center;
          }
          .rc-grid > div:nth-child(1),
          .rc-grid > div:nth-child(2) {
            align-self: end;
          }
          .rc-grid > div {
            padding-bottom: 0.2rem;
          }
          .rc-grid > div:not(:nth-last-child(-n+2)) {
            border-bottom: 1px dashed rgba(49, 51, 63, 0.25);
          }
          .rc-pos {
            font-weight: 700;
            font-size: 0.92rem;
          }
          .rc-pos-wrap {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            gap: 0.25rem;
          }
          .rc-pos-overall {
            font-size: 0.78rem;
            padding: 0.06rem 0.45rem;
          }
          .rc-pills {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            justify-content: center;
          }
          .rc-pill {
            border: 1px solid rgba(49, 51, 63, 0.18);
            border-radius: 999px;
            padding: 0.08rem 0.5rem;
            font-size: 0.82rem;
            line-height: 1.35;
            opacity: 0.95;
            white-space: nowrap;
          }
          .rc-pill-grade {
            border-radius: 999px;
            padding: 0.08rem 0.55rem;
            font-size: 0.82rem;
            line-height: 1.35;
            font-weight: 800;
            white-space: nowrap;
          }
          .rc-head-grade {
            border-radius: 999px;
            padding: 0.14rem 0.6rem;
            font-size: 1.02rem;
            font-weight: 900;
            line-height: 1;
            display: inline-block;
          }
        </style>
        """,
        unsafe_allow_html=True
    )


_apply_styles()

# ============================
# DATABASE HELPERS
# ============================

def get_team_hex(team: str | None) -> str:
    """Get hex color for a team from team_map."""
    if not team:
        return "#4C78A8"
    df = read_df(
        """
        SELECT "Color1"
        FROM public.team_map
        WHERE cfb_name = :team
        LIMIT 1
        """,
        params={"team": team},
    )
    return df["Color1"].iloc[0] if not df.empty else "#4C78A8"


def get_available_seasons() -> list[int]:
    """Return seasons available in game_data (most recent first)."""
    df = read_df(
        """
        SELECT DISTINCT season::int AS season
        FROM public.game_data
        WHERE season IS NOT NULL
          AND homeclassification = 'fbs'
          AND awayclassification = 'fbs'
        ORDER BY season DESC
        """
    )
    return df["season"].astype(int).tolist() if not df.empty else []


def get_team_game_stats(team: str | None, game_id: str | int | None) -> pd.DataFrame:
    """Fetch team advanced GAME stats for one team in one game."""
    if not team or game_id is None:
        return pd.DataFrame()

    df = read_df(
        """
        SELECT *
        FROM public.team_advanced_game_stats
        WHERE team = :team
          AND game_id = :game_id
        LIMIT 1
        """,
        params={"team": team, "game_id": game_id},
    )
    return df


# ============================
# PERCENTILE HELPER
# ============================

def league_percentile_for_stat(season: int, stat_col: str, value: float, higher_is_better: bool = True) -> float:
    """Compute league percentile (0-100) for a value vs all FBS team-games in that season.

    Baseline uses ONLY game-level rows from team_advanced_game_stats joined to game_data.season.
    """

    df = read_df(
        f"""
        SELECT gs.{stat_col} AS v
        FROM public.team_advanced_game_stats gs
        JOIN public.game_data gd
          ON gd.id = gs.game_id
        WHERE gd.season = :season
          AND gd.homeclassification = 'fbs'
          AND gd.awayclassification = 'fbs'
          AND gs.{stat_col} IS NOT NULL
        """,
        params={"season": int(season)},
    )

    # If we have no baseline data, fall back to neutral percentile.
    if df.empty:
        return 50.0

    s = df["v"].astype(float)
    if not higher_is_better:
        s = -s
        value = -float(value)

    # Include the current value as an additional observation and compute its percentile rank.
    s2 = pd.concat([s, pd.Series([float(value)])], ignore_index=True)
    pct = float(s2.rank(pct=True).iloc[-1]) * 100.0
    return pct

def grade_from_percentile(pct: float) -> tuple[str, str, str]:
    """Map percentile (0-100) to (letter, background, foreground)."""
    if pct >= 94:
        return ("A+", "#166534", "#FFFFFF")
    if pct >= 86:
        return ("A", "#15803d", "#FFFFFF")
    if pct >= 80:
        return ("A-", "#16a34a", "#FFFFFF")
    if pct >= 74:
        return ("B+", "#4ade80", "#14532d")
    if pct >= 68:
        return ("B", "#86efac", "#14532d")
    if pct >= 62:
        return ("B-", "#bbf7d0", "#14532d")
    if pct >= 56:
        return ("C+", "#fde68a", "#78350f")
    if pct >= 50:
        return ("C", "#fcd34d", "#78350f")
    if pct >= 44:
        return ("C-", "#fbbf24", "#78350f")
    if pct >= 38:
        return ("D+", "#fdba74", "#7c2d12")
    if pct >= 32:
        return ("D", "#fb923c", "#7c2d12")
    if pct >= 26:
        return ("D-", "#f97316", "#FFFFFF")
    return ("F", "#dc2626", "#FFFFFF")

# ============================
# GAME SUMMARY (GOOD/BAD)
# ============================

# Sample stat catalog (we'll tune these later)
# key: display label, value: (column_name, higher_is_better)
GAME_STAT_CATALOG: list[tuple[str, str, bool]] = [
    ("Offensive Success Rate", "offense_successrate", True),
    ("Offensive Explosiveness", "offense_explosiveness", True),
    ("Power Success", "offense_powersuccess", True),
    ("Line Yards", "offense_lineyards", True),

    ("Defensive Success Rate Allowed", "defense_successrate", False),
    ("Defensive Explosiveness Allowed", "defense_explosiveness", False),
    ("Stuff Rate", "defense_stuffrate", True),
]


def compute_game_percentiles(
    stats: pd.DataFrame,
    season: int,
    stat_catalog: list[tuple[str, str, bool]] = GAME_STAT_CATALOG,
) -> pd.DataFrame:
    """Return a df with columns: label, col, value, pct.

    Percentiles are league-wide for the selected season (all FBS team-games).
    """
    if stats.empty:
        return pd.DataFrame(columns=["label", "col", "value", "pct"])  # empty

    rows: list[dict] = []
    for label, col, higher_is_better in stat_catalog:
        if col not in stats.columns:
            continue
        v = stats[col].iloc[0]
        if pd.isna(v):
            continue

        pct = league_percentile_for_stat(int(season), col, float(v), higher_is_better=higher_is_better)
        rows.append({"label": label, "col": col, "value": float(v), "pct": float(pct)})

    if not rows:
        return pd.DataFrame(columns=["label", "col", "value", "pct"])  # empty

    out = pd.DataFrame(rows)
    out = out.sort_values("pct", ascending=False).reset_index(drop=True)
    return out


def render_good_bad_panel(
    team: str | None,
    season: int | None,
    game_label: str | None,
    team_hex: str,
    stats: pd.DataFrame,
    top_n: int = 3,
) -> None:
    """Render a single team panel showing top/bottom percentiles for the selected game."""

    if not team or season is None:
        st.info("Select a game.")
        return

    if stats.empty:
        st.info("No game stats for that team/game.")
        return

    # Headline percentiles (always shown)
    off_pct = None
    def_pct = None
    overall_pct = None

    if "offense_ppa" in stats.columns and not pd.isna(stats["offense_ppa"].iloc[0]):
        off_pct = league_percentile_for_stat(int(season), "offense_ppa", float(stats["offense_ppa"].iloc[0]), higher_is_better=True)

    if "defense_ppa" in stats.columns and not pd.isna(stats["defense_ppa"].iloc[0]):
        def_pct = league_percentile_for_stat(int(season), "defense_ppa", float(stats["defense_ppa"].iloc[0]), higher_is_better=False)

    if off_pct is not None and def_pct is not None:
        overall_pct = (float(off_pct) + float(def_pct)) / 2.0

    overall_grade = grade_from_percentile(overall_pct) if overall_pct is not None else None
    off_grade = grade_from_percentile(off_pct) if off_pct is not None else None
    def_grade = grade_from_percentile(def_pct) if def_pct is not None else None

    pcts = compute_game_percentiles(stats, int(season))
    if pcts.empty:
        st.info("No comparable stats available for this game.")
        return

    good = pcts.head(top_n).copy()
    bad = pcts.tail(top_n).sort_values("pct", ascending=True).copy()

    if overall_grade:
        overall_letter, overall_bg, overall_fg = overall_grade
        overall_html = f"<span class='rc-head-grade' style='background:{overall_bg}; color:{overall_fg};'>Overall: {overall_letter}</span>"
    else:
        overall_html = "<span class='rc-pill'>Overall: N/A</span>"

    if off_grade:
        off_letter, off_bg, off_fg = off_grade
        offense_html = f"<span class='rc-pill-grade' style='background:{off_bg}; color:{off_fg}; border:1px solid rgba(49, 51, 63, 0.18);'>Offense: {off_letter}</span>"
    else:
        offense_html = "<span class='rc-pill' style='border:1px solid rgba(49, 51, 63, 0.18);'>Offense: N/A</span>"

    if def_grade:
        def_letter, def_bg, def_fg = def_grade
        defense_html = f"<span class='rc-pill-grade' style='background:{def_bg}; color:{def_fg}; border:1px solid rgba(49, 51, 63, 0.18);'>Defense: {def_letter}</span>"
    else:
        defense_html = "<span class='rc-pill' style='border:1px solid rgba(49, 51, 63, 0.18);'>Defense: N/A</span>"

    good_rows_html = "".join(
        [
            (
                f"<div style='display:flex; justify-content:space-between; gap:0.6rem; padding:0.12rem 0;'>"
                f"<span style='font-weight:650;'>{r.label}</span>"
                f"<span class='rc-pill-grade' style='background:{grade_from_percentile(float(r.pct))[1]}; color:{grade_from_percentile(float(r.pct))[2]};'>"
                f"{grade_from_percentile(float(r.pct))[0]}"
                f"</span></div>"
            )
            for r in good.itertuples()
        ]
    )

    bad_rows_html = "".join(
        [
            (
                f"<div style='display:flex; justify-content:space-between; gap:0.6rem; padding:0.12rem 0;'>"
                f"<span style='font-weight:650;'>{r.label}</span>"
                f"<span class='rc-pill-grade' style='background:{grade_from_percentile(float(r.pct))[1]}; color:{grade_from_percentile(float(r.pct))[2]};'>"
                f"{grade_from_percentile(float(r.pct))[0]}"
                f"</span></div>"
            )
            for r in bad.itertuples()
        ]
    )

    # Header
    st.markdown(
        f"""
        <div class='rc-card'>
          <div class='rc-head'>
            <div>
              <div class='rc-title'>{team}</div>
              <div style='font-size:0.85rem; opacity:0.8; margin-top:0.05rem;'>{game_label or ''}</div>
            </div>
            {overall_html}
          </div>

          <div style='display:flex; flex-direction:column; align-items:center; gap:0.35rem; margin:0.15rem 0 0.55rem 0;'>
            <div style='display:flex; gap:0.45rem; flex-wrap:wrap; justify-content:center;'>
              {offense_html}
              {defense_html}
            </div>
          </div>

          <div style='display:grid; grid-template-columns: 1fr; gap:0.5rem;'>
            <div>
              <div style='font-weight:800; font-size:0.95rem; margin-bottom:0.25rem;'>What was good</div>
              {good_rows_html}
            </div>
            <div>
              <div style='font-weight:800; font-size:0.95rem; margin-bottom:0.25rem;'>What was bad</div>
              {bad_rows_html}
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================
# MAIN EXECUTION
# ============================

# Load team options
game_data = read_df(
    """
    SELECT id, season, startdate, hometeam, awayteam, homeclassification, awayclassification
    FROM public.game_data
    WHERE season IS NOT NULL
      AND startdate IS NOT NULL
      AND homeclassification = 'fbs'
      AND awayclassification = 'fbs'
    ORDER BY startdate DESC
    """
)

# Top selectors: Season then Game
seasons = get_available_seasons()
season_sel = st.selectbox(
    "Season",
    options=seasons,
    index=0 if seasons else None,
    placeholder="Select a season",
    key="season_sel",
)

# Filter games for selected season
if season_sel is not None and not game_data.empty:
    season_games = game_data.loc[game_data["season"].astype(int) == int(season_sel)].copy()
else:
    season_games = pd.DataFrame(columns=game_data.columns)

# Build dropdown labels
if not season_games.empty:
    season_games["game_label"] = (
        pd.to_datetime(season_games["startdate"]).dt.strftime("%Y-%m-%d")
        + " "
        + season_games["awayteam"].astype(str)
        + " VS "
        + season_games["hometeam"].astype(str)
    )

    label_to_game_id = dict(zip(season_games["game_label"], season_games["id"]))
    game_labels = season_games["game_label"].tolist()
else:
    label_to_game_id = {}
    game_labels = []

game_label_sel = st.selectbox(
    "Game",
    options=game_labels,
    index=0 if game_labels else None,
    placeholder="Select a game",
    disabled=not bool(game_labels),
    key="game_sel",
)

game_id_sel = label_to_game_id.get(game_label_sel)

# Determine away/home teams from the selected game
if game_id_sel is not None and not season_games.empty:
    row = season_games.loc[season_games["id"] == game_id_sel].iloc[0]
    team_a = str(row["awayteam"])
    team_b = str(row["hometeam"])
else:
    team_a = None
    team_b = None

season_a = int(season_sel) if season_sel is not None else None
season_b = int(season_sel) if season_sel is not None else None

label_a = f"{team_a} ({season_a})" if team_a and season_a else (team_a or "")
label_b = f"{team_b} ({season_b})" if team_b and season_b else (team_b or "")

team_hex_a = get_team_hex(team_a)
team_hex_b = get_team_hex(team_b)

# Pre-fetch game stats for away/home
stats_a = get_team_game_stats(team_a, game_id_sel)
stats_b = get_team_game_stats(team_b, game_id_sel)

# Render both sides
out_left, out_right = st.columns(2, gap="large")

with out_left:
    render_good_bad_panel(team_a, season_a, game_label_sel, team_hex_a, stats_a, top_n=3)

with out_right:
    render_good_bad_panel(team_b, season_b, game_label_sel, team_hex_b, stats_b, top_n=3)

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


def get_team_seasons(team: str | None) -> list[int]:
    """Return available seasons for a team (most recent first)."""
    if not team:
        return []
    df = read_df(
        """
        SELECT DISTINCT season
        FROM public.team_advanced_season_stats
        WHERE team = :team
        ORDER BY season DESC
        """,
        params={"team": team},
    )
    return df["season"].astype(int).tolist() if not df.empty else []


def get_team_stats(team: str | None, season: int | None = None) -> pd.DataFrame:
    """Fetch team advanced season stats; if season is None, get most recent."""
    if not team:
        return pd.DataFrame()

    if season is None:
        df = read_df(
            """
            SELECT *
            FROM public.team_advanced_season_stats
            WHERE team = :team
            ORDER BY season DESC
            LIMIT 1
            """,
            params={"team": team},
        )
    else:
        df = read_df(
            """
            SELECT *
            FROM public.team_advanced_season_stats
            WHERE team = :team
              AND season = :season
            LIMIT 1
            """,
            params={"team": team, "season": int(season)},
        )
    return df


# ============================
# GRADING & PERCENTILE HELPERS
# ============================

def grade_from_percentile(pct: float) -> tuple[str, str, str]:
    """Return (letter, bg_hex, fg_hex) from a 0-100 percentile.
    
    Grade bands: A+/A/A- (94+), B+/B/B- (74+), C+/C/C- (54+), D+/D/D- (34+), F.
    """
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


def league_percentile_for_stat(season: int, stat_col: str, value: float, higher_is_better: bool = True) -> float:
    """Compute league percentile (0-100) for a value vs all FBS teams in that season."""
    df = read_df(
        f"""
        SELECT {stat_col} AS v
        FROM public.team_advanced_season_stats
        WHERE season = :season
          AND {stat_col} IS NOT NULL
        """,
        params={"season": int(season)},
    )
    if df.empty:
        return 50.0

    s = df["v"].astype(float)
    if not higher_is_better:
        s = -s
        value = -float(value)

    s2 = pd.concat([s, pd.Series([float(value)])], ignore_index=True)
    pct = float(s2.rank(pct=True).iloc[-1]) * 100.0
    return pct


def _grade_from_stats(stats: pd.DataFrame, season: int, col: str, higher_is_better: bool = True) -> tuple[str, str, str] | None:
    """Safely compute a grade for one stat column from the single-row stats df."""
    if col not in stats.columns:
        return None
    v = stats[col].iloc[0]
    if pd.isna(v):
        return None
    pct = league_percentile_for_stat(int(season), col, float(v), higher_is_better=higher_is_better)
    return grade_from_percentile(pct)


# ============================
# HTML RENDERING HELPERS
# ============================

def _rc_pill(text: str, g: tuple[str, str, str] | None) -> tuple[str, str, str]:
    """Return (label_text, bg, fg) for a pill."""
    if not g:
        return (text, "", "")
    letter, bg, fg = g
    return (f"{text}: {letter}", bg, fg)


def _rc_pos_with_overall(label: str, g: tuple[str, str, str] | None) -> str:
    """Left-column label with a small Overall pill underneath."""
    if not g:
        return f"<div class='rc-pos-wrap'><div>{label}</div><span class='rc-pill'>Overall</span></div>"
    letter, bg, fg = g
    return (
        f"<div class='rc-pos-wrap'>"
        f"<div>{label}</div>"
        f"<span class='rc-pill-grade rc-pos-overall' style='background:{bg}; color:{fg};'>Overall: {letter}</span>"
        f"</div>"
    )


def _rc_pill_html(text: str, bg: str, fg: str) -> str:
    """Render one pill span."""
    if bg and fg:
        return (
            f"<span class='rc-pill-grade' style='background:{bg}; color:{fg};'>"
            f"{text}"
            f"</span>"
        )
    return f"<span class='rc-pill'>{text}</span>"


def _rc_rows_html(rows: list[tuple[str, list[tuple[str, str, str]]]]) -> str:
    """Build the 2-column grid HTML (left label + right pill group per row)."""
    return "".join(
        [
            f"<div class='rc-pos'>{pos}</div>"
            f"<div class='rc-pills'>"
            + "".join([_rc_pill_html(t, bg, fg) for (t, bg, fg) in pills])
            + "</div>"
            for pos, pills in rows
        ]
    )


def _rc_header_grade(overall: tuple[str, str, str] | None) -> str:
    """Big header grade pill (right side of card header)."""
    if not overall:
        return ""
    letter, bg, fg = overall
    return f"<span class='rc-head-grade' style='background:{bg}; color:{fg};'>{letter}</span>"


# ============================
# CARD RENDERERS
# ============================

def render_offense_card(
    team_hex: str,
    offense_overall: tuple[str, str, str] | None = None,
    passing_overall: tuple[str, str, str] | None = None,
    passing_efficiency: tuple[str, str, str] | None = None,
    passing_explosiveness: tuple[str, str, str] | None = None,
    rushing_overall: tuple[str, str, str] | None = None,
    rushing_efficiency: tuple[str, str, str] | None = None,
    rushing_explosiveness: tuple[str, str, str] | None = None,
    rushing_power: tuple[str, str, str] | None = None,
    ol_pass_protection: tuple[str, str, str] | None = None,
    ol_run_blocking: tuple[str, str, str] | None = None,
) -> None:
    """Render offense report card."""
    rows: list[tuple[str, list[tuple[str, str, str]]]] = [
        (
            _rc_pos_with_overall("Passing", passing_overall),
            [
                _rc_pill("Efficiency", passing_efficiency),
                _rc_pill("Explosiveness", passing_explosiveness),
            ],
        ),
        (
            _rc_pos_with_overall("Rushing", rushing_overall),
            [
                _rc_pill("Efficiency", rushing_efficiency),
                _rc_pill("Explosiveness", rushing_explosiveness),
                _rc_pill("Power", rushing_power),
            ],
        ),
        (
            "O-Line",
            [
                _rc_pill("Pass Protection", ol_pass_protection),
                _rc_pill("Run Blocking", ol_run_blocking),
            ],
        ),
    ]

    rows_html = _rc_rows_html(rows)
    title_right = _rc_header_grade(offense_overall)

    st.markdown(
        f"""
        <div class='rc-card' style='border-left: 6px solid {team_hex};'>
          <div class='rc-head'>
            <div class='rc-title'>Offense</div>
            {title_right}
          </div>
          <div class='rc-grid'>
            {rows_html}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_defense_card(
    team_hex: str,
    defense_overall: tuple[str, str, str] | None = None,
    pass_overall: tuple[str, str, str] | None = None,
    pass_efficiency: tuple[str, str, str] | None = None,
    pass_db_havoc: tuple[str, str, str] | None = None,
    run_overall: tuple[str, str, str] | None = None,
    run_efficiency: tuple[str, str, str] | None = None,
    run_stuff_rate: tuple[str, str, str] | None = None,
    pass_explosiveness_allowed: tuple[str, str, str] | None = None,
    run_explosiveness_allowed: tuple[str, str, str] | None = None,
) -> None:
    """Render defense report card."""
    rows: list[tuple[str, list[tuple[str, str, str]]]] = [
        (
            _rc_pos_with_overall("Pass D", pass_overall),
            [
                _rc_pill("Efficiency", pass_efficiency),
                _rc_pill("DB Havoc", pass_db_havoc),
                _rc_pill("Explosive Plays Allowed", pass_explosiveness_allowed),
            ],
        ),
        (
            _rc_pos_with_overall("Run Stop", run_overall),
            [
                _rc_pill("Efficiency", run_efficiency),
                _rc_pill("Stuff Rate", run_stuff_rate),
                _rc_pill("Explosive Plays Allowed", run_explosiveness_allowed),
            ],
        ),
    ]

    rows_html = _rc_rows_html(rows)
    title_right = _rc_header_grade(defense_overall)

    st.markdown(
        f"""
        <div class='rc-card' style='border-left: 6px solid {team_hex};'>
          <div class='rc-head'>
            <div class='rc-title'>Defense</div>
            {title_right}
          </div>
          <div class='rc-grid'>
            {rows_html}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================
# GRADE COMPUTATION
# ============================

def compute_offense_grades(stats: pd.DataFrame, season: int) -> dict[str, tuple[str, str, str] | None]:
    """Compute all offense grades for the report card from one team-season row."""
    return {
        "offense_overall": _grade_from_stats(stats, season, "offense_ppa", higher_is_better=True),

        "passing_overall": _grade_from_stats(stats, season, "offense_passingplays_ppa", higher_is_better=True),
        "passing_efficiency": _grade_from_stats(stats, season, "offense_passingplays_successrate", higher_is_better=True),
        "passing_explosiveness": _grade_from_stats(stats, season, "offense_passingplays_explosiveness", higher_is_better=True),

        "rushing_overall": _grade_from_stats(stats, season, "offense_rushingplays_ppa", higher_is_better=True),
        "rushing_efficiency": _grade_from_stats(stats, season, "offense_rushingplays_successrate", higher_is_better=True),
        "rushing_explosiveness": _grade_from_stats(stats, season, "offense_rushingplays_explosiveness", higher_is_better=True),
        "rushing_power": _grade_from_stats(stats, season, "offense_powersuccess", higher_is_better=True),

        "ol_pass_protection": _grade_from_stats(stats, season, "offense_havoc_frontseven", higher_is_better=False),
        "ol_run_blocking": _grade_from_stats(stats, season, "offense_lineyards", higher_is_better=True),
    }


def compute_defense_grades(stats: pd.DataFrame, season: int) -> dict[str, tuple[str, str, str] | None]:
    """Compute all defense grades for the report card from one team-season row."""
    return {
        # Overall defense: lower is better
        "defense_overall": _grade_from_stats(stats, season, "defense_ppa", higher_is_better=False),

        # Passing
        "pass_overall": _grade_from_stats(stats, season, "defense_passingplays_ppa", higher_is_better=False),
        "pass_efficiency": _grade_from_stats(stats, season, "defense_passingplays_successrate", higher_is_better=False),
        "pass_db_havoc": _grade_from_stats(stats, season, "defense_havoc_db", higher_is_better=True),
        "pass_explosiveness_allowed": _grade_from_stats(stats, season, "defense_passingplays_explosiveness", higher_is_better=False),

        # Run Stop
        "run_overall": _grade_from_stats(stats, season, "defense_rushingplays_ppa", higher_is_better=False),
        "run_efficiency": _grade_from_stats(stats, season, "defense_rushingplays_successrate", higher_is_better=False),
        "run_stuff_rate": _grade_from_stats(stats, season, "defense_stuffrate", higher_is_better=True),
        "run_explosiveness_allowed": _grade_from_stats(stats, season, "defense_rushingplays_explosiveness", higher_is_better=False),
    }


# ============================
# PAGE LAYOUT
# ============================

def render_side_panel(team: str | None, season: int | None, label: str, team_hex: str) -> None:
    """Render one side (header + offense/defense cards)."""
    st.subheader(label or (team or ""))

    if not team or not season:
        st.info("Select a team and season.")
        return

    stats = get_team_stats(team, season)
    if stats.empty:
        st.info("No data for that team/season.")
        return

    off_grades = compute_offense_grades(stats, int(season))
    def_grades = compute_defense_grades(stats, int(season))

    render_offense_card(
        team_hex,
        offense_overall=off_grades["offense_overall"],
        passing_overall=off_grades["passing_overall"],
        passing_efficiency=off_grades["passing_efficiency"],
        passing_explosiveness=off_grades["passing_explosiveness"],
        rushing_overall=off_grades["rushing_overall"],
        rushing_efficiency=off_grades["rushing_efficiency"],
        rushing_explosiveness=off_grades["rushing_explosiveness"],
        rushing_power=off_grades["rushing_power"],
        ol_pass_protection=off_grades["ol_pass_protection"],
        ol_run_blocking=off_grades["ol_run_blocking"],
    )

    render_defense_card(
        team_hex,
        defense_overall=def_grades["defense_overall"],
        pass_overall=def_grades["pass_overall"],
        pass_efficiency=def_grades["pass_efficiency"],
        pass_db_havoc=def_grades["pass_db_havoc"],
        run_overall=def_grades["run_overall"],
        run_efficiency=def_grades["run_efficiency"],
        run_stuff_rate=def_grades["run_stuff_rate"],
        pass_explosiveness_allowed=def_grades["pass_explosiveness_allowed"],
        run_explosiveness_allowed=def_grades["run_explosiveness_allowed"],
    )


# ============================
# MAIN EXECUTION
# ============================

# Load team options
game_data = read_df(
    """
    SELECT *
    FROM public.game_data
    WHERE startdate IS NOT NULL
      AND homeclassification = 'fbs'
      AND awayclassification = 'fbs'
    """
)
teams = sorted(pd.concat([game_data["hometeam"], game_data["awayteam"]]).dropna().unique())

# Header with side-by-side selectors
left_col, right_col = st.columns(2, gap="large")

with left_col:
    team_a = st.selectbox("Team (Left)", options=teams, index=None, placeholder="Select a team", key="team_a")
    seasons_a = get_team_seasons(team_a)
    season_a = st.selectbox(
        "Season (Left)",
        options=seasons_a,
        index=0 if seasons_a else None,
        placeholder="Select a season",
        disabled=not bool(seasons_a),
        key="season_a",
    )

with right_col:
    team_b = st.selectbox("Team (Right)", options=teams, index=None, placeholder="Select a team", key="team_b")
    seasons_b = get_team_seasons(team_b)
    season_b = st.selectbox(
        "Season (Right)",
        options=seasons_b,
        index=0 if seasons_b else None,
        placeholder="Select a season",
        disabled=not bool(seasons_b),
        key="season_b",
    )

# Build display labels
label_a = f"{team_a} ({season_a})" if team_a and season_a else (team_a or "")
label_b = f"{team_b} ({season_b})" if team_b and season_b else (team_b or "")

team_hex_a = get_team_hex(team_a)
team_hex_b = get_team_hex(team_b)

# Render both sides
out_left, out_right = st.columns(2, gap="large")

with out_left:
    render_side_panel(team_a, season_a, label_a or "Left Team", team_hex_a)

with out_right:
    render_side_panel(team_b, season_b, label_b or "Right Team", team_hex_b)
"""Best weekly offenses and defenses, with pregame BG opponent context."""

import html

import pandas as pd
import streamlit as st

from utils.weekly_performances import (
    METRIC_LABELS, PRESETS, best_ascending, effective_mode, filter_performances,
    load_available_weeks, load_week, metric_label, rank_performances, sort_performances,
)


@st.cache_data(ttl=300)
def get_ranked_week(season, season_type, week):
    frame, note = load_week(season, season_type, week)
    ranked = {} if frame.empty else {
        (side, preset): rank_performances(frame, side, preset)
        for side in ("offense", "defense") for preset in PRESETS
    }
    return frame, ranked, note


st.markdown("""
<style>
.weekly-kicker {color:#64748b;font-size:.78rem;font-weight:750;letter-spacing:.12em;text-transform:uppercase;margin-top:16px}
.weekly-heading {color:#0C2C56;font-size:2.6rem;font-weight:850;line-height:1.15;margin:4px 0 10px}
.weekly-card {border:1px solid #dce4ee;border-top:4px solid #0C2C56;border-radius:10px;
  padding:18px 20px;margin:8px 0 16px;background:#fff;color:#0f172a;min-height:155px}
.weekly-card .label {font-size:.8rem;color:#64748b;margin-bottom:8px}
.weekly-card .team {font-size:1.4rem;font-weight:750;overflow-wrap:anywhere}
.weekly-card .value {font-size:1rem;color:#0C2C56;margin-top:7px}
.weekly-card .context {font-size:.85rem;color:#64748b;margin-top:5px}
[data-testid="stElementToolbar"] {display:none !important}
@media(max-width:640px) {.weekly-heading {font-size:2rem}.weekly-card {min-height:0}}
</style>
<div class="weekly-kicker">League Wide / Game Performances</div>
<div class="weekly-heading">Weekly Performances</div>
""", unsafe_allow_html=True)
st.caption("The best offensive and defensive performances of the week, with actual production and pregame opponent strength side by side.")


def render_leader(frame, side, requested):
    mode = effective_mode(frame, requested)
    field = "adjusted_score" if mode == "BG-adjusted" else "raw_ppa"
    candidates = sort_performances(frame.dropna(subset=[field]), field, best_ascending(field, side))
    title = "Best offensive performance" if side == "offense" else "Best defensive performance"
    if candidates.empty:
        team, context, value = "Unavailable", "No qualifying performance data", "—"
    else:
        row = candidates.iloc[0]
        team = html.escape(str(row["team"]))
        context = html.escape(f"vs {row['opponent']} · {row['venue']} · {row['result'] or '—'} {row['final_score'] or '—'}")
        ppa_label = "PPA/play" if side == "offense" else "PPA allowed/play"
        value = f"{row['raw_ppa']:+.3f} {ppa_label}"
        if mode == "BG-adjusted":
            value = f"{row['adjusted_score']:+.2f} BG score · " + value
        if len(candidates.loc[candidates[field] == row[field]]) > 1:
            title += " (tied)"
    st.markdown(f'<div class="weekly-card"><div class="label">{title} · {mode}</div>'
                f'<div class="team">{team}</div><div class="value">{value}</div>'
                f'<div class="context">{context}</div></div>', unsafe_allow_html=True)


def column_labels(side, preset):
    labels = {
        "team": "Team", "opponent": "Opponent", "conference": "Conference", "venue": "Venue",
        "final_score": "Final score", "result": "Result", "raw_rank": "Raw rank",
        "adjusted_rank": "BG-adjusted rank", "adjusted_score": "BG-adjusted score",
        "opponent_bg_rating": "Opponent BG rating", "game_id": "Game ID", "kickoff": "Kickoff (UTC)",
        "rating_completed_at": "Rating snapshot (UTC)", "rating_run_id": "Rating run ID",
        "adjustment_note": "Adjustment availability",
        "raw_ppa": metric_label(side, PRESETS[preset][0]),
    }
    labels.update({f"{side}_{suffix}": metric_label(side, suffix) for suffix in METRIC_LABELS})
    return labels


def render_table(frame, columns, side, labels, key):
    displayed = frame[columns].copy()
    configs = {}
    for column in columns:
        label = labels[column]
        suffix = column.removeprefix(f"{side}_")
        if column in ("kickoff", "rating_completed_at"):
            displayed[column] = pd.to_datetime(displayed[column], utc=True, errors="coerce")
            configs[column] = st.column_config.DatetimeColumn(label, format="YYYY-MM-DD HH:mm")
        elif column in ("raw_rank", "adjusted_rank", "game_id") or suffix in ("plays", "drives"):
            configs[column] = st.column_config.NumberColumn(label, format="%d")
        elif suffix.endswith("successrate") or suffix in ("powersuccess", "stuffrate"):
            displayed[column] = displayed[column] * 100
            configs[column] = st.column_config.NumberColumn(label, format="%.1f%%")
        elif column == "adjusted_score":
            configs[column] = st.column_config.NumberColumn(label, format="%+.2f",
                help="Weekly performance z-score + 0.25 × pregame opponent BG rating z-score. Higher is better.")
        elif column == "opponent_bg_rating":
            configs[column] = st.column_config.NumberColumn(label, format="%+.1f",
                help="Unblended BG Power Rating from the latest successful snapshot completed strictly before kickoff.")
        elif column == "raw_ppa" or column.startswith(f"{side}_"):
            configs[column] = st.column_config.NumberColumn(label, format="%.3f")
        else:
            configs[column] = st.column_config.TextColumn(label)
    st.dataframe(displayed, hide_index=True, use_container_width=True,
                 height=min(640, 38 + 35 * len(displayed)), column_config=configs, key=key)


def render_side(ranked, side, requested, conferences, teams):
    preset = st.selectbox(f"{side.title()} view", list(PRESETS), key=f"weekly_{side}_preset")
    full = ranked[(side, preset)]
    if full.empty:
        st.info(f"No qualifying {side} performances with positive play counts are available for this week.")
        return
    mode = effective_mode(full, requested)
    covered = int(full["adjusted_score"].notna().sum())
    st.caption(f"Adjustment coverage: {covered} of {len(full)} {side} performances · {preset.lower()} PPA")
    if requested == "BG-adjusted" and mode == "Raw PPA":
        st.info("BG adjustment is unavailable for this view. Showing raw PPA rankings; adjusted values remain unavailable.")
    elif covered < len(full):
        st.caption("Unadjusted rows remain in the table. Missing pregame ratings, kickoff times, or PPA appear as —; see Adjustment availability.")
    labels = column_labels(side, preset)
    primary = f"{side}_{PRESETS[preset][0]}"
    metrics = [f"{side}_{suffix}" for suffix in PRESETS[preset][1]]
    columns = ["adjusted_rank", "raw_rank", "team", "opponent", "conference", "venue", "result", "final_score",
               "adjusted_score", "raw_ppa", "opponent_bg_rating", *metrics]
    if covered < len(full):
        columns.append("adjustment_note")
    extras = [column for column in labels if column not in columns and column != primary]
    chosen = st.multiselect("Additional columns", extras, format_func=labels.get,
                            key=f"weekly_{side}_{preset}_extras")
    first, second = st.columns([3, 1])
    sortable = ["raw_ppa", "adjusted_score", "raw_rank", "adjusted_rank", "opponent_bg_rating",
                *[f"{side}_{suffix}" for suffix in METRIC_LABELS if f"{side}_{suffix}" != primary],
                "team", "opponent", "conference"]
    selection = first.selectbox("Sort by", ["leaderboard", *sortable],
        format_func=lambda column: "Leaderboard order" if column == "leaderboard" else labels[column],
        key=f"weekly_{side}_{preset}_sort")
    order = second.selectbox("Order", ["Best first", "Reverse"], key=f"weekly_{side}_order")
    field = ("adjusted_score" if mode == "BG-adjusted" else "raw_ppa") if selection == "leaderboard" else selection
    ascending = best_ascending(field, side)
    if order == "Reverse":
        ascending = not ascending
    filtered = sort_performances(filter_performances(full, conferences, teams), field, ascending)
    st.caption(f"Showing {len(filtered)} of {len(full)} performances · Ranks cover the full week and do not change with filters · Click any column header to sort")
    if filtered.empty:
        st.info("No performances match these filters. Clear the conference or team selection.")
        return
    render_table(filtered, list(dict.fromkeys([*columns, *chosen, field])), side, labels, f"weekly_{side}_table")
    st.caption("PPA and yardage allowed: lower is better on defense. Stuff rate: lower is better on offense, higher on defense. — means unavailable.")


try:
    weeks = load_available_weeks()
except Exception:
    st.error("Weekly advanced stats could not be loaded. Check the database connection and try again.")
    st.stop()
if weeks.empty:
    st.info("No completed FBS-vs-FBS games with advanced stats are available yet.")
    st.stop()

first, second, third = st.columns(3)
season = first.selectbox("Season", sorted(weeks["season"].unique(), reverse=True))
season_weeks = weeks.loc[weeks["season"] == season]
# Availability is ordered by latest kickoff, so the initial phase/week follows the latest data.
phase = second.selectbox("Season Type", season_weeks["season_type"].drop_duplicates().tolist(), format_func=str.title)
phase_weeks = season_weeks.loc[season_weeks["season_type"] == phase]
week = third.selectbox("Week", phase_weeks["week"].drop_duplicates().tolist(), format_func=lambda value: f"Week {value}")
requested = st.radio("Ranking mode", ["BG-adjusted", "Raw PPA"], horizontal=True)
try:
    frame, ranked, note = get_ranked_week(int(season), phase, int(week))
except Exception:
    st.error("This week’s performances could not be prepared. Check the advanced-stat data and try again.")
    st.stop()
if frame.empty:
    st.info("No qualifying completed FBS-vs-FBS performances are available for this selection.")
    st.stop()
if note:
    st.warning(note)
st.caption(f"{season} · {phase.title()} season · Week {week} · {frame['game_id'].nunique()} games · {len(frame)} team-game performances")
for container, side in zip(st.columns(2), ("offense", "defense")):
    with container:
        render_leader(ranked[(side, "Overall")], side, requested)
st.caption("Headline leaders cover the full week. Each row is one game, including when a team has multiple games in the selected week.")

first, second = st.columns(2)
conferences = first.multiselect("Conferences", sorted(frame["conference"].unique()), placeholder="All conferences")
team_options = sorted(filter_performances(frame, conferences)["team"].unique())
teams = second.multiselect("Teams", team_options, placeholder="All teams")

with st.expander("How BG adjustment works"):
    st.markdown("**BG-adjusted score = performance z-score + 0.25 × opponent BG rating z-score.**")
    st.write("A z-score measures distance from the average in standard deviations. Offense uses higher PPA as better; defense reverses the direction so lower PPA allowed is better. Each baseline includes all qualifying performances from this week, separately for overall, passing, and rushing.")
    st.write("Opponent strength uses the stored, unblended BG Power Rating, standardized against all FBS teams in that snapshot. We select the latest successful manual/nightly snapshot completed strictly before kickoff. TeamRankings ratings and later snapshots are never substituted.")
    st.write("The 0.25 weight is a conservative design choice, not a fitted model. The score is a weekly comparison index—not adjusted PPA, a prediction, or a probability. Scores should not be compared across weeks or views. BG Power measures whole-team strength, not separate offensive and defensive strength.")
    st.write("At least two valid observations are needed for each standardized component. A population with zero variance contributes zero. Missing pregame ratings, reliable kickoff times, or PPA remain unavailable; raw rankings are still shown. Missing adjusted rows are excluded from the adjusted ranking population, so raw and adjusted coverage can differ. Ties share ranks.")
    st.write("Only completed FBS-vs-FBS games qualify. Offense and defense each require positive play counts. All other advanced statistics remain raw. Definitions and garbage-time treatment follow the stored source data; this page applies no additional play filtering.")

offense_tab, defense_tab = st.tabs(["Offense", "Defense"])
with offense_tab:
    render_side(ranked, "offense", requested, conferences, teams)
with defense_tab:
    render_side(ranked, "defense", requested, conferences, teams)

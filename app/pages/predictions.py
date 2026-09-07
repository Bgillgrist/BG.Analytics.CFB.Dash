"""League-wide season outlook, conference races, and snapshot changes."""

import html

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.predictions import (
    CHANGE_METRICS, LABELS, PRESETS, PROBABILITIES, RANKS, WIN_BUCKETS, WIN_NOTE,
    add_changes, comparison_snapshot, conference_summary, filter_teams,
    independent_mask, load_runs, load_snapshot, model_changed, select_snapshot, sort_teams,
)


NAVY = "#0C2C56"
st.markdown("""
<style>
.prediction-heading {color:#0C2C56;font-size:2.6rem;font-weight:850;margin:16px 0 4px;line-height:1.15}
.prediction-kicker {color:#64748b;font-size:.78rem;font-weight:750;letter-spacing:.12em;text-transform:uppercase}
.prediction-card {border:1px solid #dce4ee;border-top:4px solid #0C2C56;border-radius:10px;
  padding:18px 20px;margin:8px 0 18px;background:#fff;color:#0f172a;min-height:142px}
.prediction-card .label {font-size:.8rem;color:#64748b;margin-bottom:8px}
.prediction-card .team {font-size:1.25rem;font-weight:750;overflow-wrap:anywhere}
.prediction-card .value {font-size:1.1rem;color:#0C2C56;margin-top:5px}
/* This research page deliberately has no export controls. */
[data-testid="stElementToolbar"] {display:none !important}
@media(max-width:640px) {.prediction-heading {font-size:2rem}.prediction-card {min-height:0}}
</style>
<div class="prediction-kicker">League Wide / Season Outlook</div>
<div class="prediction-heading">Predictions</div>
""", unsafe_allow_html=True)
st.caption("Explore the season ahead: win projections, playoff paths, conference races, and what’s changed.")


def display_table(frame, columns, key):
    if frame.empty:
        st.info("No teams match these filters. Clear a filter or widen the numeric range.")
        return
    columns = list(dict.fromkeys(columns))
    displayed = frame[columns].copy()
    config = {}
    for column in columns:
        label = LABELS.get(column, column)
        if column in ("team", "conference"):
            config[column] = st.column_config.TextColumn(label)
        elif column in PROBABILITIES:
            displayed[column] = displayed[column] * 100
            config[column] = st.column_config.NumberColumn(label, format="%.1f%%")
        elif column in RANKS:
            config[column] = st.column_config.NumberColumn(label, format="%d", help="Model projection, not an official ranking.")
        elif column.endswith("_change"):
            suffix = "wins" if column == "projected_wins_change" else "pp"
            config[column] = st.column_config.NumberColumn(label, format=f"%+.1f {suffix}")
        elif "strength_of_schedule" in column:
            config[column] = st.column_config.NumberColumn(label, format="%.3f", help="Model schedule-strength score. Higher means harder.")
        else:
            config[column] = st.column_config.NumberColumn(label, format="%.1f")
    st.dataframe(displayed, column_config=config, hide_index=True, width="stretch",
                 height=min(640, 38 + 35 * len(displayed)), key=key)


def style_chart(figure):
    figure.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                         font=dict(color=NAVY), margin=dict(l=0, r=20, t=20, b=0))
    return figure


def render_favorites(frame):
    for container, metric, label in zip(st.columns(3),
            ["playoff_prob", "national_champion_prob", "projected_wins"],
            ["Playoff favorite", "National title favorite", "Projected-wins leader"]):
        candidates = sort_teams(frame.dropna(subset=[metric]), metric)
        with container:
            if candidates.empty:
                name, value = "Unavailable", "—"
            else:
                leader = candidates.iloc[0]
                name = html.escape(str(leader["team"]))
                value = f"{leader[metric]:.1%}" if metric in PROBABILITIES else f"{leader[metric]:.1f} wins"
            st.markdown(f'<div class="prediction-card"><div class="label">{label}</div>'
                        f'<div class="team">{name}</div><div class="value">{value}</div></div>', unsafe_allow_html=True)


def render_teams(frame):
    render_favorites(frame)
    st.caption("Headlines cover the full league. Filters below apply to the team table and win chart.")
    first, second = st.columns(2)
    conferences = first.multiselect("Conferences", sorted(frame["conference"].unique()), placeholder="All conferences")
    candidates = filter_teams(frame, conferences=conferences)
    teams = second.multiselect("Teams", sorted(candidates["team"].unique()), placeholder="All teams")
    preset = st.selectbox("Column preset", list(PRESETS))
    metrics = [column for column in LABELS if column not in ("team", "conference")]
    chosen = st.multiselect("Projection columns", metrics, default=PRESETS[preset],
                            format_func=LABELS.get, key=f"prediction_columns_{preset}")
    st.caption("Team and Conference stay visible. Add change columns using the comparison period above.")
    first, second, third = st.columns([2, 2, 1])
    metric = first.selectbox("Numeric filter", [None, *metrics],
                             format_func=lambda value: "No numeric filter" if value is None else LABELS[value])
    field = second.selectbox("Sort by", [*metrics, "team", "conference"],
                              index=metrics.index("playoff_prob"), format_func=LABELS.get)
    direction = third.selectbox("Direction", ["Descending", "Ascending"])
    minimum = maximum = None
    if metric:
        scale = 100 if metric in PROBABILITIES else 1
        st.caption("Enter percentages on a 0–100 scale; change columns use percentage points or wins. Blank bounds are unrestricted.")
        first, second = st.columns(2)
        minimum = first.number_input("Minimum", value=None, step=0.1, format="%.2f", key=f"prediction_min_{metric}")
        maximum = second.number_input("Maximum", value=None, step=0.1, format="%.2f", key=f"prediction_max_{metric}")
        if minimum is not None:
            minimum /= scale
        if maximum is not None:
            maximum /= scale
    if minimum is not None and maximum is not None and minimum > maximum:
        st.warning("Minimum must be less than or equal to maximum.")
        return
    filtered = filter_teams(frame, conferences, teams, metric, minimum, maximum)
    filtered = sort_teams(filtered, field, direction == "Ascending")
    st.caption(f"{len(filtered)} of {len(frame)} FBS teams · Click a column header to sort · — means unavailable or not applicable")
    display_table(filtered, ["team", "conference", *chosen], "prediction_team_table")
    st.caption(WIN_NOTE)
    if any("strength_of_schedule" in column for column in chosen):
        st.caption("Schedule strength is the model’s score, not a rank; higher means harder. Rankings shown are model projections.")
    if any(column in {"conference_champion_prob", "conference_championship_game_prob"} for column in chosen):
        st.caption("Conference championship probabilities do not apply to independents.")
    if chosen and frame[chosen].isna().any().any():
        st.caption("Some selected metrics are unavailable in this snapshot or comparison and appear as —.")
    if preset == "Win Outlook" and not filtered.empty:
        st.subheader("Win distribution")
        team = st.selectbox("Distribution team", filtered["team"].tolist())
        row = filtered.loc[filtered["team"] == team].iloc[0]
        distribution = pd.DataFrame({"Wins": [str(i) for i in range(13)] + ["13+"],
                                     "Probability": row[WIN_BUCKETS].astype(float).values * 100})
        if distribution["Probability"].isna().any():
            st.info("A complete win distribution is unavailable for this team.")
        else:
            figure = px.bar(distribution, x="Wins", y="Probability", color_discrete_sequence=[NAVY])
            figure.update_xaxes(type="category")
            figure.update_yaxes(title="Probability", ticksuffix="%")
            figure.update_traces(hovertemplate="%{x} wins: %{y:.1f}%<extra></extra>")
            st.plotly_chart(style_chart(figure), width="stretch", config={"displayModeBar": False})


def render_conferences(frame):
    st.subheader("Conference outlook")
    st.caption("Includes every member of each conference, regardless of Team Predictions filters. Expected CFP teams is the sum of member playoff probabilities; fractional values are an expectation.")
    summary = conference_summary(frame)
    displayed = summary.copy()
    for column in ("favorite_prob", "runner_up_prob"):
        displayed[column] *= 100
    st.dataframe(displayed, hide_index=True, width="stretch", column_config={
        "conference": "Conference", "teams": st.column_config.NumberColumn("Teams", format="%d"),
        "favorite": "Title favorite", "favorite_prob": st.column_config.NumberColumn("Favorite %", format="%.1f%%"),
        "runner_up": "Runner-up", "runner_up_prob": st.column_config.NumberColumn("Runner-up %", format="%.1f%%"),
        "lead_pp": st.column_config.NumberColumn("Favorite’s lead (pp)", format="%.1f pp"),
        "expected_cfp": st.column_config.NumberColumn("Expected CFP teams", format="%.2f"),
    }, key="prediction_conference_summary")
    conference = st.selectbox("Explore a conference", summary["conference"].tolist())
    members = sort_teams(frame.loc[frame["conference"] == conference], "conference_champion_prob")
    st.subheader(f"{conference} title race")
    if independent_mask(pd.Series([conference])).iloc[0]:
        st.info("Conference championship games and titles do not apply to independents.")
    else:
        chart = members.dropna(subset=["conference_champion_prob"]).copy()
        if chart.empty:
            st.info("Conference title probabilities are unavailable in this snapshot.")
        else:
            chart["Title probability"] = chart["conference_champion_prob"] * 100
            figure = px.bar(chart, x="Title probability", y="team", orientation="h",
                            color_discrete_sequence=[NAVY], height=max(320, 30 * len(chart)))
            figure.update_yaxes(title=None, autorange="reversed", categoryorder="array", categoryarray=chart["team"].tolist())
            figure.update_xaxes(title="Conference title probability", ticksuffix="%")
            figure.update_traces(hovertemplate="%{y}: %{x:.1f}%<extra></extra>")
            st.plotly_chart(style_chart(figure), width="stretch", config={"displayModeBar": False})
    display_table(members, ["team", "conference", *PRESETS["Conference Race"], "projected_wins",
                            "projected_losses", "national_champion_prob"], "prediction_conference_teams")
    st.caption(WIN_NOTE)


def render_changes(frame, previous):
    st.subheader("What’s changed")
    if previous is None:
        st.info("No earlier successful snapshot is available for this comparison period.")
        return
    st.caption("Probability changes are percentage points (pp), not relative percent changes. Teams without historical values show —.")
    available = frame.dropna(subset=["playoff_prob_change"])
    for container, positive, title in zip(st.columns(2), [True, False], ["Biggest CFP risers", "Biggest CFP fallers"]):
        with container:
            st.markdown(f"**{title}**")
            subset = available.loc[available["playoff_prob_change"] > 0] if positive else available.loc[available["playoff_prob_change"] < 0]
            subset = sort_teams(subset, "playoff_prob_change", ascending=not positive).head(5)
            if subset.empty:
                st.info("No increases in this comparison." if positive else "No decreases in this comparison.")
            else:
                display_table(subset, ["team", "playoff_prob", "playoff_prob_change"], f"prediction_movers_{positive}")
    columns = ["team", "conference", *[field for metric in CHANGE_METRICS for field in (metric, f"{metric}_change")]]
    first, second = st.columns([3, 1])
    field = first.selectbox("Compare by", columns[2:], index=3, format_func=LABELS.get)
    direction = second.selectbox("Change direction", ["Descending", "Ascending"])
    display_table(sort_teams(frame, field, direction == "Ascending"), columns, "prediction_changes_table")


try:
    runs = load_runs()
except Exception:
    st.error("Prediction snapshots could not be loaded. Check the database connection and try again.")
    st.stop()
if runs.empty:
    st.info("No successful season prediction snapshots are available yet.")
    st.stop()

first, second = st.columns(2)
season = first.selectbox("Season", sorted(runs["season"].unique(), reverse=True))
period = second.selectbox("Compare with", ["Previous day", "One week earlier"])
current = select_snapshot(runs, int(season))
if current is None:
    st.info("No successful snapshot is available for this season.")
    st.stop()
previous = comparison_snapshot(runs, current, 1 if period == "Previous day" else 7)
try:
    frame = load_snapshot(str(current["season_prediction_run_id"]))
except Exception:
    st.error("The selected prediction snapshot could not be loaded. Try again shortly.")
    st.stop()
if frame.empty:
    st.info("This snapshot contains no FBS team predictions.")
    st.stop()

historical = None
if previous is not None:
    try:
        historical = load_snapshot(str(previous["season_prediction_run_id"]))
    except Exception:
        st.warning("Historical predictions could not be loaded. Current predictions are still available.")
    if historical is None or historical.empty:
        previous = None
frame = add_changes(frame, historical)
date_label = pd.Timestamp(current["run_date"]).strftime("%b %d, %Y")
st.caption(f"Snapshot: {date_label} · {int(current['simulations']):,} simulations · {len(frame)} FBS teams")
if previous is not None:
    old_date = pd.Timestamp(previous["run_date"]).strftime("%b %d, %Y")
    st.caption(f"Changes compare {date_label} with {old_date} (latest available snapshot on or before the requested date).")
else:
    st.caption("Historical comparison unavailable for this period; change columns show —.")
if model_changed(current, previous):
    st.info("The model version changed between these snapshots. Differences may reflect model updates as well as new results and inputs.")
with st.expander("Snapshot details & definitions"):
    st.write(f"Model: {current['model_version']}")
    st.write(f"Run ID: {current['season_prediction_run_id']}")
    st.write(f"Run type: {current['run_type']}")
    completed = pd.to_datetime(current["completed_at"], utc=True)
    if pd.notna(completed):
        st.write(f"Completed: {completed.tz_convert('America/New_York').strftime('%b %d, %Y %I:%M %p %Z')}")
    if previous is not None:
        st.write(f"Comparison model: {previous['model_version']}")
        st.write(f"Comparison run ID: {previous['season_prediction_run_id']}")
    st.write(WIN_NOTE)
    st.write("AP, CFP, and résumé ranks are model projections, not official rankings. Schedule strength is a model score; higher means harder. Missing values appear as —, including conference title odds for independents.")
    st.write("Automatic bid and at-large probabilities are unconditional probabilities of each path. All probabilities are model estimates.")

team_tab, conference_tab, change_tab = st.tabs(["Team Predictions", "Conference Races", "Changes"])
with team_tab:
    render_teams(frame)
with conference_tab:
    render_conferences(frame)
with change_tab:
    render_changes(frame, previous)

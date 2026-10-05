"""Interactive head-to-head rankings and result evidence."""

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from utils import head_to_head as h2h
from utils import head_to_head_graphics as graphics


@st.cache_data(ttl=300)
def source_data(season):
    return h2h.load_season(season)


@st.cache_data(max_entries=24)
def cached_rankings(dataset, version):
    return h2h.solve_ranking(dataset)


@st.cache_data(max_entries=48)
def cached_ranges(dataset, ranking, teams, version):
    return h2h.calculate_ranges(dataset, ranking, teams)


@st.cache_data(max_entries=24)
def cached_cycles(dataset, team, max_teams, seconds, version):
    return h2h.longest_cycles(dataset.games, team, max_teams=max_teams, seconds=seconds)


def show_graphic(kind, identity, config_factory, label):
    key = f"h2h_graphic_{kind}"
    if st.session_state.get(key, (None,))[0] != identity:
        st.session_state.pop(key, None)
    if st.button(label, key=f"h2h_show_{kind}"):
        try:
            with st.spinner("Preparing copyable graphic…"):
                markup = graphics.render_graphic(config_factory())
            st.session_state[key] = (identity, markup)
        except Exception:
            st.error("The graphic could not be prepared. Try again.")
    if key in st.session_state:
        components.html(st.session_state[key][1], height=1000, scrolling=True)


st.markdown("""<style>
.h2h-kicker {color:#64748b;font-size:.8rem;letter-spacing:.12em;text-transform:uppercase;margin-top:16px}
.h2h-heading {color:#0C2C56;font-size:2.6rem;font-weight:850;line-height:1.15;margin:4px 0 10px}
.h2h-chain {display:flex;align-items:center;gap:12px;overflow-x:auto;padding:12px 0;margin:10px 0}
.h2h-node {display:flex;align-items:center;gap:10px;flex-shrink:0;padding:12px;border:1px solid #dce4ee;border-radius:10px;background:#fff;color:#0c2c50}
@media(max-width:640px){.h2h-heading{font-size:2rem}}
</style><div class="h2h-kicker">League Wide / Results Only</div>
<div class="h2h-heading">Head to Head Analysis</div>""", unsafe_allow_html=True)
st.caption("Who beat whom. Explore the rankings, the connections, and the contradictions.")

with st.expander("How the rankings work"):
    st.markdown("Direct wins come first: minimize games whose winner ranks below the loser. Among equally good orders, "
                "minimize reversed two-game chains: Missouri → Florida → Ole Miss supports Missouri above Ole Miss. Each pair contributes once at its "
                "shortest distance; repeated games count individually as direct results. Three-game and longer chains add no separate ranking priority, but remain in the explorer.")
    st.markdown("Then fill each position by **record: fewer FBS losses → more FBS wins**, followed by **résumé: opponents' FBS winning percentage**. "
                "FBS-undefeated teams stay above teams with FBS losses. Direct and two-game priorities otherwise take precedence over record. "
                "Opponent records exclude games against the team being ranked; repeated opponents count once per meeting. "
                "Alphabetical order is only the final fallback when these values also tie. No opponent games means a schedule tiebreak value of zero.")
    st.caption("Scores, polls, and power ratings do not influence ranks. All records use only eligible FBS games through the selected cutoff.")
    st.caption("A → B means A beat B. Circular results make a perfect ordering impossible. The list is one representative "
               "order; positions may not be unique. Calculations run only when requested, for up to 30 seconds each. "
               "Historical weeks use today's stored corrected results, not historical database snapshots.")

try:
    seasons = h2h.load_seasons()
except Exception:
    st.error("Game results could not be loaded. Check the database connection and try again.")
    st.stop()
if not seasons:
    st.info("No FBS seasons are available yet.")
    st.stop()
first, second = st.columns(2)
season = first.selectbox("Season", seasons)
try:
    rows, assets = source_data(season)
except Exception:
    st.error("This season's game results could not be loaded. Try again.")
    st.stop()
checkpoints = h2h.checkpoints(rows)
if not checkpoints:
    st.info("No completed FBS-versus-FBS checkpoints are available for this season.")
    unplayed = h2h.prepare_dataset(rows, assets, season, ("regular", 0))
    if unplayed.excluded:
        st.warning(f"Excluded {unplayed.excluded} invalid completed FBS records with no usable checkpoint.")
    if unplayed.teams:
        st.dataframe(pd.DataFrame({"Team": [t.name for t in unplayed.teams], "Status": "Unranked"}), hide_index=True)
    for key in list(st.session_state):
        if key.startswith(("h2h_result", "h2h_ranges", "h2h_graphic_", "h2h_cycles")):
            del st.session_state[key]
    st.stop()
cutoff = second.selectbox("Through week", checkpoints, index=len(checkpoints) - 1, format_func=h2h.checkpoint_label,
                          key=f"h2h_cutoff_{season}")
dataset = h2h.prepare_dataset(rows, assets, season, cutoff)
identity = dataset.fingerprint
if st.session_state.get("h2h_dataset") != identity:
    for key in list(st.session_state):
        if key.startswith(("h2h_result", "h2h_ranges", "h2h_graphic_", "h2h_cycles")):
            del st.session_state[key]
    st.session_state.h2h_dataset = identity
if dataset.excluded:
    st.warning(f"Excluded {dataset.excluded} invalid completed FBS records (including unknown weeks or conflicting game IDs).")
st.caption(f"{len(dataset.games)} eligible games · FBS vs. FBS only · Cumulative through {h2h.checkpoint_label(cutoff)}")
tabs = st.tabs(["Rankings", "Win-chain explorer", "Circle of Chaos"])

with tabs[0]:
    if st.button("Calculate rankings", type="primary", disabled=not dataset.games):
        try:
            with st.spinner("Solving results priorities · up to 30 seconds…"):
                result = cached_rankings(dataset, h2h.API_VERSION)
            st.session_state.h2h_result = result
            st.session_state.pop("h2h_ranges", None)
            st.session_state.pop("h2h_graphic_rankings", None)
        except ImportError:
            st.error("The ranking solver is unavailable. Install the project's requirements (including OR-Tools) and restart the app.")
        except Exception:
            st.error("The ranking calculation failed. No new ranking was published; try again.")
    ranking = st.session_state.get("h2h_result")
    if ranking:
        exceptions = h2h.exception_games(dataset, ranking)
        a, b, c, d = st.columns(4)
        a.metric("Games included", len(dataset.games))
        b.metric("Results honored", f"{(len(dataset.games) - len(exceptions)) / len(dataset.games):.1%}")
        c.metric("Exceptions", len(exceptions))
        d.metric("Results fit", ("All results fit" if not exceptions else "Best fit proven") if ranking.optimal else "Provisional")
        st.info("A best fit is not necessarily a unique ranking. Zero exceptions means every included winner is above its loser; many different orders may do that. "
                "Record, then résumé, select among those orders. Only FBS games through the selected cutoff count.")
        if ranking.order_unique is False:
            st.caption("Confirmed: multiple equally valid head-to-head orders exist for these results.")
        elif ranking.order_unique is True:
            st.caption("These head-to-head results determine a unique ordering of the ranked teams.")
        if ranking.optimal and ranking.tiebreak_positions < len(ranking.order):
            st.warning(f"Result priorities are proven, but the time budget ended before all record/résumé tiebreaks were resolved. "
                       f"Tiebreaks finalized for the first {ranking.tiebreak_positions} positions.")
        else:
            st.caption("Order: direct results → two-game win chains → fewer FBS losses → more FBS wins → opponents' FBS win percentage.")
        if not ranking.optimal:
            st.warning("Best order found within the budget; optimality is not yet proven for all priorities.")
        with st.expander("Calculation details and proof status"):
            st.dataframe(pd.DataFrame(ranking.objectives, columns=["Distance", "Reversed results/pairs", "Proven optimal"]), hide_index=True)
            if ranking.active_distance is not None:
                st.caption(f"First unproven priority: distance {ranking.active_distance}. Lower bound: {ranking.bound if ranking.bound is not None else 'Not established'}.")
        with st.expander("Calculate optimal rank ranges"):
            if not ranking.optimal:
                st.info("Optimal rank ranges are unavailable until every ranking priority is proven optimal.")
            else:
                selected = st.multiselect("Teams for rank ranges", list(ranking.order), max_selections=5, key=f"h2h_range_teams_{identity}")
                if st.session_state.get("h2h_ranges_selection") != tuple(selected):
                    st.session_state.pop("h2h_ranges", None)
                    st.session_state.h2h_ranges_selection = tuple(selected)
                if st.button("Calculate rank ranges", disabled=not selected):
                    try:
                        with st.spinner("Finding rank bounds · up to 30 seconds…"):
                            ranges = cached_ranges(dataset, ranking, tuple(selected), h2h.API_VERSION)
                        st.session_state.h2h_ranges = ranges
                    except Exception:
                        st.error("Rank ranges could not be calculated. Try again.")
                st.caption("Ranges show the flexibility in direct/two-game evidence BEFORE record and résumé tiebreaks (including the undefeated rule). Exact ranges give the best and worst position across all optimal result orders. Incomplete ranges are conservative outer bounds. "
                           "Intermediate positions and different teams' endpoints are not necessarily jointly attainable.")
                calculated = st.session_state.get("h2h_ranges", ())
                if calculated:
                    st.dataframe(pd.DataFrame([{
                        "Team": r.team, "Best position / lower bound": r.low,
                        "Best endpoint proven": r.low_exact, "Worst position / upper bound": r.high,
                        "Worst endpoint proven": r.high_exact,
                    } for r in calculated]), hide_index=True, use_container_width=True)
        frame = h2h.ranking_rows(dataset, ranking, st.session_state.get("h2h_ranges", ()))
        a, b = st.columns(2)
        conferences = a.multiselect("Conferences", sorted({t.conference for t in dataset.teams if t.conference}), key=f"h2h_conf_{season}")
        teams = b.multiselect("Teams", [t.name for t in dataset.teams], key=f"h2h_teams_{season}")
        visible = frame
        if conferences:
            visible = visible.loc[visible.conference.isin(conferences)]
        if teams:
            visible = visible.loc[visible.team.isin(teams)]
        st.caption("Filters preserve national positions and evidence. Teams without eligible completed games are unranked.")
        st.dataframe(visible, hide_index=True, use_container_width=True, column_config={
            "position": st.column_config.NumberColumn("Position", format="%d"), "team": "Team",
            "logo": st.column_config.ImageColumn("Logo"), "conference": "Conference", "record": "FBS record",
            "win_pct": st.column_config.NumberColumn("FBS win pct", format="%.3f", help="Context only. Record tiebreaks use fewer losses, then more wins—not winning percentage."),
            "opponent_win_pct": st.column_config.NumberColumn("Opponent win pct", format="%.3f", help="Pooled FBS opponent records, excluding games against this team; repeated opponents count per meeting."),
            "exceptions": "Exceptions", "rank_range": "Optimal rank range"})
        with st.expander(f"Direct-result exceptions ({len(exceptions)})"):
            if exceptions:
                st.dataframe(h2h.game_rows(exceptions), hide_index=True, use_container_width=True)
            else:
                st.success("Every direct result is honored.")
        st.caption("The Top 25 graphic always uses the national ranking, regardless of table filters.")
        show_graphic("rankings", (identity, ranking), lambda: graphics.graphic_config(dataset, "rankings", ranking=ranking), "Show Top 25 graphic")
    else:
        st.info("Calculate rankings to see the best-fit order and its exceptions. The explorers are available without a ranking calculation.")
        if not dataset.games:
            st.dataframe(pd.DataFrame({"Team": [t.name for t in dataset.teams], "Status": "Unranked"}), hide_index=True)

edges = h2h.graph(dataset.games)
names = [t.name for t in dataset.teams]
with tabs[1]:
    st.caption("Shortest win paths in both directions. These describe season-wide relationships; games need not occur in chronological order.")
    if len(names) >= 2:
        a, b = st.columns(2)
        source = a.selectbox("First team", names, key=f"h2h_source_{season}")
        targets = [n for n in names if n != source]
        target = b.selectbox("Second team", targets, key=f"h2h_target_{season}_{source}")
        meetings = [g for g in dataset.games if {g.winner, g.loser} == {source, target}]
        st.markdown("**Direct meetings**")
        if meetings:
            st.dataframe(h2h.game_rows(meetings), hide_index=True, use_container_width=True)
        else:
            st.info("No eligible direct meeting by this cutoff.")
        paths = [(a, b, h2h.shortest_paths(edges, a).get(b, ())) for a, b in ((source, target), (target, source))]
        if all(path for _, _, path in paths):
            st.warning("Contradictory paths exist in both directions; these teams belong to a circle of results.")
        for a, b, path in paths:
            st.markdown(f"**{a} → {b}**")
            if path:
                st.caption(f"Shortest distance: {len(path) - 1} game(s)")
                st.markdown(graphics.chain_markup(dataset, path), unsafe_allow_html=True)
                st.dataframe(h2h.game_rows(h2h.path_games(dataset.games, path)), hide_index=True, use_container_width=True)
            else:
                st.info("No win path in this direction.")
        show_graphic("chains", (identity, source, target), lambda: graphics.graphic_config(dataset, "chains", paths=paths), "Show matchup chain graphics")
    else:
        st.info("At least two teams are needed to explore paths.")

with tabs[2]:
    st.caption("Search for the longest circles first, with up to 16 distinct teams. Every team appears once before the loop closes. "
               "Two-team circles are split rematches. Search runs only when requested and returns up to 50 examples.")
    circle_team = st.selectbox("Circle includes", ["All teams", *names], key=f"h2h_circle_team_{season}")
    a, b = st.columns(2)
    max_teams = a.selectbox("Maximum teams in circle", list(range(2, 17)), index=14)
    seconds = b.selectbox("Search budget (seconds)", [15, 30, 60, 120], index=2)
    search_identity = (identity, circle_team, max_teams, seconds)
    if st.session_state.get("h2h_cycles_identity") != search_identity:
        st.session_state.pop("h2h_cycles", None)
        st.session_state.pop("h2h_graphic_circle", None)
        st.session_state.h2h_cycles_identity = search_identity
    if st.button("Search longest circles", disabled=not dataset.games):
        with st.spinner(f"Searching longest-first · up to {seconds} seconds…"):
            st.session_state.h2h_cycles = cached_cycles(dataset, None if circle_team == "All teams" else circle_team,
                                                       max_teams, seconds, h2h.API_VERSION)
    search = st.session_state.get("h2h_cycles")
    cycles = search.cycles if search else ()
    if search and cycles:
        st.caption(f"{len(cycles)} examples · Longest {'proven within selected limit' if search.longest_proven else 'found, not proven longest'}: "
                   f"{len(cycles[0])} teams · {search.reason}")
        if not search.exhaustive:
            st.info("This is a bounded selection, not every possible circle. Increase the time budget or filter to a team to explore further.")
    if cycles:
        cycle = st.selectbox("Circle", cycles, format_func=lambda c: f"{len(c)} teams · " + " → ".join((*c, c[0])), key=f"h2h_circle_{search_identity}")
        st.markdown(graphics.circle_svg(dataset, cycle), unsafe_allow_html=True)
        if len(cycle) > 6:
            st.caption(" · ".join(f"{i}. {name}" for i, name in enumerate(cycle, 1)))
        st.dataframe(h2h.game_rows(h2h.path_games(dataset.games, (*cycle, cycle[0]))), hide_index=True, use_container_width=True)
        show_graphic("circle", (identity, cycle), lambda: graphics.graphic_config(dataset, "circle", cycle=cycle), "Show Circle of Chaos graphic")
    else:
        st.info(("No matching circles found in this search. A time-limited search does not establish that none exist."
                 if not search.exhaustive else "No matching circles within the selected size limit exist by this cutoff.")
                if search else "Choose a team/size limit and search to find the longest circles first.")

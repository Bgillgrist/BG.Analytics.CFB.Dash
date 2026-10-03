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
                "minimize reversed two-game chains, then three-game chains, and so on. Each pair contributes once at its "
                "shortest distance; repeated games count individually as direct results. Scores, polls, and power ratings do not influence ranks.")
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
        if key.startswith(("h2h_result", "h2h_ranges", "h2h_graphic_")):
            del st.session_state[key]
    st.stop()
cutoff = second.selectbox("Through week", checkpoints, index=len(checkpoints) - 1, format_func=h2h.checkpoint_label,
                          key=f"h2h_cutoff_{season}")
dataset = h2h.prepare_dataset(rows, assets, season, cutoff)
identity = dataset.fingerprint
if st.session_state.get("h2h_dataset") != identity:
    for key in list(st.session_state):
        if key.startswith(("h2h_result", "h2h_ranges", "h2h_graphic_")):
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
        d.metric("Solve status", "Optimal" if ranking.optimal else "Provisional")
        st.caption("Positions show one representative order, not necessarily unique ranks. Each game's exception counts toward both participating teams.")
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
                st.caption("Exact ranges give the best and worst position across all optimal orders. Incomplete ranges are conservative outer bounds. "
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
    st.caption("A selection of short cycles: the shortest circle found for each team, deduplicated and limited to two through six teams. "
               "This is not an exhaustive list; longer circles may also exist. Two-team circles are split rematches.")
    circle_team = st.selectbox("Circle includes", ["All teams", *names], key=f"h2h_circle_team_{season}")
    cycles, truncated = h2h.short_cycles(dataset.games, None if circle_team == "All teams" else circle_team)
    if truncated:
        st.caption("Showing the first 50 matching examples. Filter to a team for a narrower selection.")
    if cycles:
        cycle = st.selectbox("Circle", cycles, format_func=lambda c: " → ".join((*c, c[0])), key=f"h2h_circle_{identity}_{circle_team}")
        st.markdown(graphics.circle_svg(dataset, cycle), unsafe_allow_html=True)
        st.dataframe(h2h.game_rows(h2h.path_games(dataset.games, (*cycle, cycle[0]))), hide_index=True, use_container_width=True)
        show_graphic("circle", (identity, cycle), lambda: graphics.graphic_config(dataset, "circle", cycle=cycle), "Show Circle of Chaos graphic")
    else:
        st.info("No matching two-to-six-team circles found by this cutoff.")

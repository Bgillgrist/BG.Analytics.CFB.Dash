"""Result eligibility, graph semantics, and brute-force optimization oracles."""

from dataclasses import replace
from itertools import permutations
from pathlib import Path
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils import head_to_head as h


def dataset(pairs, extra=()):
    games = tuple(h.Game(str(i), a, b, 21, 10, f"2026-09-{i+1:02d}", "regular", i+1) for i, (a,b) in enumerate(pairs))
    teams = tuple(h.Team(n) for n in sorted({n for p in pairs for n in p} | set(extra)))
    return h.Dataset(2026, ("regular", 8), games, teams)


def source_row(**changes):
    return dict(id=1, season=2026, completed=True, hometeam="A", awayteam="B", homeclassification="fbs", awayclassification="fbs",
                homepoints=21, awaypoints=10, seasontype="regular", week=1, startdate="2026-09-01", **changes)


def row(**changes):
    original = source_row()
    original.update(changes)
    return original


def brute(data):
    layers = h.layers_for(data.games)
    scored = [(h.objective_vector(order, layers), order) for order in permutations(h.graph(data.games))]
    best = min(v for v, _ in scored)
    return best, [order for v, order in scored if v == best]


def test_normalization_deduplicates_and_excludes_live_fcs_invalid():
    rows = pd.DataFrame([row(), row(), row(id=2, completed=False, awayteam="Live"),
        row(id=3, awayclassification="fcs", awayteam="FCS"), row(id=4, awayteam="Tied", awaypoints=21),
        row(id=5, homepoints=None), row(id=6, homepoints=-1), row(id=7, homepoints=3.5), row(id=8, hometeam="B"),
        row(id=9, week=None), row(id=None), row(id=10, week=2)])
    data = h.prepare_dataset(rows, pd.DataFrame(), 2026, ("regular",1))
    assert len(data.games) == 1
    assert data.excluded == 7
    assert "Live" in [t.name for t in data.teams]
    assert "FCS" not in [t.name for t in data.teams]


def test_conflicting_game_ids_excluded_not_counted_twice():
    data = h.prepare_dataset(pd.DataFrame([row(), row(homepoints=0)]), pd.DataFrame(), 2026, ("regular",1))
    assert not data.games and data.excluded == 1


def test_cumulative_postseason_and_fingerprint_score_correction():
    rows = pd.DataFrame([row(), row(id=2, week=15), row(id=3, seasontype="postseason", week=1), row(id=4, seasontype="postseason", week=2)])
    assert h.checkpoints(rows) == [("regular",1),("regular",15),("postseason",1),("postseason",2)]
    data = h.prepare_dataset(rows, pd.DataFrame(), 2026, ("postseason",1))
    assert len(data.games) == 3
    corrected = rows.copy()
    corrected.loc[0,"homepoints"] = 3
    assert h.prepare_dataset(corrected,pd.DataFrame(),2026,("postseason",1)).fingerprint != data.fingerprint


def test_dag_ranking_ranges_and_unranked():
    data = dataset([("A","B"),("B","C"),("D","E")], extra=["Bye"])
    result = h.solve_ranking(data)
    assert result.optimal and all(value == 0 for _,value,_ in result.objectives)
    best, orders = brute(data)
    ranges = h.calculate_ranges(data,result,["A","B","C","D","E"])
    for r in ranges:
        actual = [order.index(r.team)+1 for order in orders]
        assert (r.low,r.high) == (min(actual),max(actual))
        assert r.low_exact and r.high_exact
    frame = h.ranking_rows(data,result)
    assert pd.isna(frame.set_index("team").loc["Bye","position"])
    assert frame.set_index("team").loc["Bye","rank_range"] == "Unranked"
    assert h.solve_ranking(dataset([])).order == ()
    assert result.order_unique is False
    assert result.tiebreak_positions == len(result.order)
    assert h.solve_ranking(dataset([("A","B"),("B","C")])).order_unique is True


def test_resume_tiebreak_prefers_record_over_alphabet_and_preserves_results():
    data = dataset([("Zulu","Loser 1"),("Zulu","Loser 2"),("Alpha","Beta"),("Beta","Gamma")])
    result = h.solve_ranking(data)
    assert result.order[:2] == ("Zulu","Alpha")  # both undefeated; two wins beat one
    assert result.order.index("Alpha") < result.order.index("Beta") < result.order.index("Gamma")
    assert not h.exception_games(data,result)
    preference = {name:i for i,name in enumerate(h.resume_order(data.games))}
    _, orders = brute(data)
    assert result.order == min(orders,key=lambda o:tuple(preference[n] for n in o))


def test_opponent_strength_excludes_self_games_and_breaks_equal_records():
    data = dataset([("Zulu","Strong"),("Strong","X"),("Strong","Y"),("Alpha","Weak"),("X","Weak")])
    stats = h.resume_stats(data.games)
    assert stats["Zulu"][:2] == stats["Alpha"][:2]
    assert stats["Zulu"][2] == 1 and stats["Alpha"][2] == 0
    assert h.solve_ranking(data).order[0] == "Zulu"


def test_shortest_distances_count_pairs_once_and_keep_rematches():
    data = dataset([("A","B"),("A","B"),("B","D"),("A","C"),("C","D"),("D","E")])
    layers = h.layers_for(data.games)
    assert ("A","B",2) in layers[1]
    assert layers[2].count(("A","D",1)) == 1
    assert ("A","E",1) in layers[3]
    assert h.shortest_paths(h.graph(data.games),"A")["D"] == ("A","B","D")
    assert "A" not in h.shortest_paths(h.graph(data.games),"E")
    assert h.path_games(data.games,("A","B"))[0].id == "0"
    unknown_date = replace(data.games[0], id="unknown", date="")
    assert h.path_games((unknown_date, *data.games), ("A", "B"))[0].id == "0"


def test_cycles_split_rematches_dedup_filters_and_long_cycles():
    data = dataset([("A","B"),("B","A"),("C","D"),("D","E"),("E","C")])
    cycles, truncated = h.short_cycles(data.games)
    assert cycles == (("A","B"),("C","D","E")) and not truncated
    assert h.short_cycles(data.games,"D")[0] == (("C","D","E"),)
    assert not h.short_cycles(dataset([(str(i),str((i+1)%7)) for i in range(7)]).games)[0]


@pytest.mark.parametrize("pairs", [
    [("A","B"),("B","C"),("C","A")],
    [("A","B"),("B","A")],
    [("A","B"),("A","B"),("B","C"),("C","A"),("C","D")],
    [("A","B"),("B","C"),("C","A"),("D","E")],
    [("A","B"),("B","C"),("C","A"),("D","A"),("B","E"),("E","D")],
])
def test_solver_and_ranges_match_all_permutations(pairs):
    pytest.importorskip("ortools")
    data = dataset(pairs)
    best, orders = brute(data)
    result = h.solve_ranking(data,seconds=10)
    assert result.optimal
    assert tuple(v for _,v,_ in result.objectives) == best
    assert result.order in orders
    priority = {n:i for i,n in enumerate(h.resume_order(data.games))}
    assert result.order == min(orders,key=lambda o:tuple(priority[n] for n in o))
    assert result.tiebreak_positions == len(result.order)
    for r in h.calculate_ranges(data,result,list(result.order)[:5],seconds=10):
        actual = [o.index(r.team)+1 for o in orders]
        assert r.low_exact and r.high_exact
        assert (r.low,r.high) == (min(actual),max(actual))


def test_timeout_and_range_bound_semantics():
    pytest.importorskip("ortools")
    data = dataset([("A","B"),("B","C"),("C","A")])
    incomplete = h.solve_ranking(data,seconds=0)
    assert not incomplete.optimal and not any(p for _,_,p in incomplete.objectives)
    with pytest.raises(ValueError,match="proven"):
        h.calculate_ranges(data,incomplete,["A"])
    solved = h.solve_ranking(data)
    ranges = h.calculate_ranges(data,solved,["A"],seconds=0)
    assert ranges == (h.RankRange("A",1,3,False,False),)
    with pytest.raises(ValueError,match="these results"):
        h.calculate_ranges(replace(data,season=2025),solved,["A"])


def test_exception_counts_and_direct_results_first_oracle():
    data = dataset([("A","B"),("A","B"),("B","C"),("C","A")])
    best, orders = brute(data)
    assert best[0] == 1
    assert all(order.index("A") < order.index("B") for order in orders)
    result = h.Ranking(orders[0],(),True,"test",fingerprint=data.fingerprint)
    assert len(h.exception_games(data,result)) == 1
    assert h.ranking_rows(data,result).exceptions.sum() == 2


def test_partial_range_outer_bounds_and_individual_endpoint_flags(monkeypatch):
    pytest.importorskip("ortools")
    from ortools.sat.python import cp_model
    data = dataset([("A","B"),("B","C"),("C","A"),("D","A")])
    ranking = h.solve_ranking(data)
    class LimitedSolver:
        best_objective_bound = 1
        def solve(self, model):
            return cp_model.UNKNOWN
    monkeypatch.setattr(h,"new_solver",lambda seconds: LimitedSolver())
    ranges = h.calculate_ranges(data,ranking,["A"])
    assert ranges == (h.RankRange("A",1,4,False,False),)


def test_longest_circle_finds_16_distinct_teams_even_with_shortcut():
    pairs = [(f"T{i:02}",f"T{(i+1)%16:02}") for i in range(16)] + [("T01","T00")]
    data = dataset(pairs)
    result = h.longest_cycles(data.games,seconds=2)
    assert len(result.cycles[0]) == 16 and len(set(result.cycles[0])) == 16
    assert result.longest_proven
    assert [len(c) for c in result.cycles] == [16,2]
    for cycle in result.cycles:
        assert len(h.path_games(data.games,(*cycle,cycle[0]))) == len(cycle)
    filtered = h.longest_cycles(data.games,team="T10",seconds=2)
    assert all("T10" in c for c in filtered.cycles)
    assert len(filtered.cycles) == 1


def test_long_cycle_size_limit_dedup_and_time_limit_labels():
    data = dataset([("A","B"),("B","C"),("C","A"),("B","A")])
    result = h.longest_cycles(data.games,max_teams=2)
    assert result.cycles == (("A","B"),) and result.longest_proven
    dense = dataset([(str(i),str(j)) for i in range(8) for j in range(8) if i != j])
    stopped = h.longest_cycles(dense.games,max_teams=8,seconds=0)
    assert stopped.cycles and not stopped.exhaustive and not stopped.longest_proven
    assert stopped.reason == "Time limit"
    capped = h.longest_cycles(dense.games,max_teams=8,limit=3,seconds=2)
    assert len(capped.cycles) == 3 and all(len(c)==8 for c in capped.cycles)
    assert capped.longest_proven and not capped.exhaustive and capped.reason == "Result limit"
    empty = h.longest_cycles(dataset([("A","B")]).games)
    assert empty.exhaustive and not empty.cycles


def test_long_cycle_search_matches_exhaustive_small_graph_oracle():
    data = dataset([("A","B"),("B","C"),("C","A"),("A","D"),("D","B"),("C","D"),("B","A")])
    edges = h.graph(data.games)
    expected = set()
    for size in range(2,5):
        for cycle in permutations(edges,size):
            if cycle[0] == min(cycle) and all(b in edges[a] for a,b in zip(cycle,(*cycle[1:],cycle[0]))):
                expected.add(cycle)
    result = h.longest_cycles(data.games,max_teams=4,seconds=3)
    assert result.exhaustive and set(result.cycles) == expected
    assert list(result.cycles) == sorted(expected,key=lambda c:(-len(c),c))

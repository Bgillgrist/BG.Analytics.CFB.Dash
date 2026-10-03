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

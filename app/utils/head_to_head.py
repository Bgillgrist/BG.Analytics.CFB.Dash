"""Results-only rankings. Pure transforms and optimization; no Streamlit imports."""

from collections import Counter, deque
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import heapq
import math
import time

import pandas as pd

API_VERSION = 2
PHASES = {"regular": 0, "postseason": 1}


@dataclass(frozen=True)
class Game:
    id: str
    winner: str
    loser: str
    winner_points: int
    loser_points: int
    date: str
    phase: str
    week: int


@dataclass(frozen=True)
class Team:
    name: str
    conference: str = ""
    logo: str = ""
    logo_fallback: str = ""


@dataclass(frozen=True)
class Dataset:
    season: int
    cutoff: tuple
    games: tuple
    teams: tuple
    excluded: int = 0

    @property
    def fingerprint(self):
        return hashlib.sha256(repr((API_VERSION, self)).encode()).hexdigest()


@dataclass(frozen=True)
class Ranking:
    order: tuple
    objectives: tuple  # (distance, achieved exceptions, proven optimal)
    optimal: bool
    status: str
    bound: float | None = None  # lower bound for first unproven layer
    active_distance: int | None = None
    fingerprint: str = ""
    tiebreak_positions: int = 0
    order_unique: bool | None = None  # head-to-head evidence alone, before tiebreaking


@dataclass(frozen=True)
class RankRange:
    team: str
    low: int
    high: int
    low_exact: bool
    high_exact: bool


@dataclass(frozen=True)
class CycleSearch:
    cycles: tuple
    exhaustive: bool
    longest_proven: bool
    reason: str


def clean(value):
    return "" if pd.isna(value) else str(value).strip()


def phase_week(row):
    phase = clean(row.get("seasontype", "regular")).lower() or "regular"
    try:
        value = float(row.get("week"))
        week = int(value)
        if value != week or week < 0 or phase not in PHASES:
            return None
        return phase, week
    except (ValueError, TypeError, OverflowError):
        return None


def checkpoint_key(checkpoint):
    return PHASES[checkpoint[0]], checkpoint[1]


def checkpoint_label(checkpoint):
    return f"{'Regular season' if checkpoint[0] == 'regular' else 'Postseason'} · Week {checkpoint[1]}"


def is_completed(row):
    value = row.get("completed")
    return pd.notna(value) and value == True  # explicitly completed, never inferred from scores


def both_fbs(row):
    return all(clean(row.get(f"{side}classification")).lower() == "fbs" for side in ("home", "away"))


def checkpoints(rows):
    return sorted({cp for row in rows.to_dict("records")
                   if is_completed(row) and both_fbs(row) and (cp := phase_week(row))}, key=checkpoint_key)


def prepare_dataset(rows, assets, season, cutoff):
    """Roster uses the season schedule; only evidence is cut off at the selected week.

    Identical repeated source rows count once. Conflicting versions of one game ID
    are excluded rather than arbitrarily selecting a winner.
    """
    rows = rows.copy()
    if "season" in rows:
        rows = rows.loc[pd.to_numeric(rows.season, errors="coerce") == season]
    asset_map = {}
    for row in assets.to_dict("records"):
        name = next((clean(row.get(k)) for k in ("cfb_name", "team", "school", "Team", "School") if clean(row.get(k))), "")
        logo = next((clean(row.get(k)) for k in ("Logo", "logo", "logo_url", "Logo_URL") if clean(row.get(k))), "")
        dark = next((clean(row.get(k)) for k in ("DarkLogo", "dark_logo", "Logo_Dark") if clean(row.get(k))), "")
        asset_map[name] = (logo or dark, dark or logo)
    roster = {}
    # Deterministic conference selection if the source contains differing values.
    records = sorted(rows.to_dict("records"), key=lambda r: (clean(r.get("startdate")), clean(r.get("id"))))
    for row in records:
        for side in ("home", "away"):
            name = clean(row.get(f"{side}team"))
            if name and clean(row.get(f"{side}classification")).lower() == "fbs":
                roster[name] = Team(name, clean(row.get(f"{side}conference")), *asset_map.get(name, ("", "")))
    candidates, invalid, missing = {}, set(), 0
    for row in records:
        if not is_completed(row) or not both_fbs(row):
            continue
        cp = phase_week(row)
        if cp and checkpoint_key(cp) > checkpoint_key(cutoff):
            continue
        game_id = clean(row.get("id"))
        if not game_id:
            missing += 1
            continue
        try:
            home, away = clean(row.get("hometeam")), clean(row.get("awayteam"))
            hp, ap = float(row.get("homepoints")), float(row.get("awaypoints"))
            if not cp or not home or not away or home == away or not all(
                math.isfinite(p) and p >= 0 and p.is_integer() for p in (hp, ap)
            ) or hp == ap:
                raise ValueError("Invalid completed result")
            date = pd.to_datetime(row.get("startdate"), utc=True, errors="coerce")
            game = Game(game_id, home if hp > ap else away, away if hp > ap else home,
                        int(max(hp, ap)), int(min(hp, ap)), "" if pd.isna(date) else date.isoformat(), *cp)
            if game_id in candidates and candidates[game_id] != game:
                invalid.add(game_id)
            candidates[game_id] = game
        except (TypeError, ValueError, OverflowError):
            invalid.add(game_id)
    games = tuple(sorted((g for id_, g in candidates.items() if id_ not in invalid), key=lambda g: (g.date, g.id)))
    return Dataset(int(season), tuple(cutoff), games, tuple(roster[n] for n in sorted(roster)), len(invalid) + missing)


def load_seasons():
    from utils.db import read_df
    frame = read_df("""SELECT DISTINCT season::int AS season FROM public.game_data
        WHERE season IS NOT NULL AND
        (LOWER(homeclassification) = 'fbs' OR LOWER(awayclassification) = 'fbs')
        ORDER BY season DESC""")
    return frame.season.tolist()


def load_season(season):
    from utils.db import read_df
    rows = read_df("SELECT * FROM public.game_data WHERE season = :season", {"season": int(season)})
    try:
        assets = read_df("SELECT * FROM public.team_map")
    except Exception:
        assets = pd.DataFrame()
    return rows, assets


def graph(games):
    nodes = sorted({name for g in games for name in (g.winner, g.loser)})
    edges = {name: set() for name in nodes}
    for game in games:
        edges[game.winner].add(game.loser)
    return {name: tuple(sorted(edges[name])) for name in nodes}


def shortest_paths(edges, source):
    paths = {source: (source,)}
    queue = deque([source])
    while queue:
        current = queue.popleft()
        for target in edges.get(current, ()):
            if target not in paths:
                paths[target] = (*paths[current], target)
                queue.append(target)
    return paths


def layers_for(games, edges=None):
    edges = graph(games) if edges is None else edges
    direct = Counter((g.winner, g.loser) for g in games)
    layers = {1: [(a, b, weight) for (a, b), weight in sorted(direct.items())]}
    for source in edges:
        for target, path in shortest_paths(edges, source).items():
            distance = len(path) - 1
            if distance > 1:
                layers.setdefault(distance, []).append((source, target, 1))
    return dict(sorted(layers.items()))


def objective_vector(order, layers):
    positions = {name: index for index, name in enumerate(order)}
    return tuple(sum(w for a, b, w in pairs if positions[a] > positions[b]) for pairs in layers.values())


def resume_stats(games):
    """Exact fractions avoid accidental float ties. OWP excludes games vs this team.

    Opponents' remaining records are pooled, once per matchup (including rematches).
    With no remaining opponent games, the schedule-strength tiebreak is zero.
    """
    wins = Counter(g.winner for g in games)
    losses = Counter(g.loser for g in games)
    meetings = Counter((g.winner, g.loser) for g in games)
    opponents = {n: [] for n in graph(games)}
    for g in games:
        opponents[g.winner].append(g.loser)
        opponents[g.loser].append(g.winner)
    stats = {}
    for name, rivals in opponents.items():
        ow = sum(wins[o] - meetings[o, name] for o in rivals)
        ol = sum(losses[o] - meetings[name, o] for o in rivals)
        stats[name] = (Fraction(wins[name], wins[name] + losses[name]), wins[name], Fraction(ow, ow + ol) if ow + ol else Fraction(0))
    return stats


def resume_order(games):
    stats = resume_stats(games)
    return tuple(sorted(stats, key=lambda n: (*(-value for value in stats[n]), n)))


def topological_order(edges, preference=None):
    priority = {n: i for i, n in enumerate(preference or sorted(edges))}
    indegree = Counter(b for values in edges.values() for b in values)
    ready = [(priority[n], n) for n in edges if not indegree[n]]
    heapq.heapify(ready)
    result = []
    while ready:
        _, current = heapq.heappop(ready)
        result.append(current)
        for target in edges[current]:
            indegree[target] -= 1
            if not indegree[target]:
                heapq.heappush(ready, (priority[target], target))
    return tuple(result) if len(result) == len(edges) else None


def initial_order(edges, games):
    return resume_order(games)


def break_solver_ties(model, positions, order, games, deadline):
    """Lexicographically prefer the best résumé at each position, within fixed optima.

    This agrees with the DAG ready-team rule. It never turns a résumé preference
    into an additional result constraint for pre-tiebreak rank ranges.
    """
    from ortools.sat.python import cp_model
    preference = resume_order(games)
    count = len(preference)
    zero_positions = [model.new_int_var(0, count - 1, f"zero_{i}") for i in range(count)]
    at_position = [model.new_int_var(0, count - 1, f"occupant_{i}") for i in range(count)]
    for name, zero in zip(preference, zero_positions):
        model.add(zero == positions[name] - 1)
    model.add_inverse(zero_positions, at_position)
    fixed = 0
    for variable in at_position:
        if time.monotonic() >= deadline:
            break
        model.minimize(variable)
        solver = new_solver(deadline - time.monotonic())
        status = solver.solve(model)
        if status in (cp_model.INFEASIBLE, cp_model.MODEL_INVALID):
            raise RuntimeError("Tiebreak model failed validation.")
        if status in (cp_model.FEASIBLE, cp_model.OPTIMAL):
            order = tuple(sorted(positions, key=lambda name: solver.value(positions[name])))
        if status != cp_model.OPTIMAL:
            break
        model.add(variable == solver.value(variable))
        fixed += 1
        model.clear_hints()
        for index, name in enumerate(order, 1):
            model.add_hint(positions[name], index)
    return order, fixed


def build_model(nodes, layers, hint, deadline):
    from ortools.sat.python import cp_model
    model = cp_model.CpModel()
    positions = {n: model.new_int_var(1, len(nodes), f"rank_{i}") for i, n in enumerate(nodes)}
    model.add_all_different(list(positions.values()))
    for index, name in enumerate(hint, 1):
        model.add_hint(positions[name], index)
    pairs = {}
    expressions = {}
    for distance, values in layers.items():
        terms = []
        for a, b, weight in values:
            if time.monotonic() >= deadline:
                return None
            key = tuple(sorted((a, b)))
            if key not in pairs:
                first, second = key
                before = model.new_bool_var(f"pair_{len(pairs)}")
                model.add(positions[first] < positions[second]).only_enforce_if(before)
                model.add(positions[first] > positions[second]).only_enforce_if(before.Not())
                pairs[key] = before
            # before=1 means alphabetically first is ahead; violation reverses it.
            terms.append(weight * (1 - pairs[key] if a == key[0] else pairs[key]))
        expressions[distance] = sum(terms)
    return model, positions, expressions


def new_solver(seconds):
    from ortools.sat.python import cp_model
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max(.001, seconds)
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    return solver


def solve_ranking(dataset, seconds=30):
    deadline = time.monotonic() + seconds
    edges = graph(dataset.games)
    layers = layers_for(dataset.games, edges)
    if not edges:
        return Ranking((), (), True, "No eligible results", fingerprint=dataset.fingerprint)
    dag = topological_order(edges, resume_order(dataset.games))
    if dag is not None:
        # A DAG has a unique order iff every consecutive pair is linked by an edge.
        unique = all(b in edges[a] for a, b in zip(dag, dag[1:]))
        return Ranking(dag, tuple((d, 0, True) for d in layers), True, "All results fit", fingerprint=dataset.fingerprint,
                       tiebreak_positions=len(dag), order_unique=unique)
    from ortools.sat.python import cp_model
    order = initial_order(edges, dataset.games)
    built = build_model(tuple(edges), layers, order, deadline)
    proven, bound, active = set(), None, 1
    if built:
        model, positions, expressions = built
        for distance, expression in expressions.items():
            active = distance
            if time.monotonic() >= deadline:
                break
            model.minimize(expression)
            solver = new_solver(deadline - time.monotonic())
            status = solver.solve(model)
            if status == cp_model.MODEL_INVALID or status == cp_model.INFEASIBLE:
                raise RuntimeError("Ranking model failed validation; no ranking was published.")
            if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                order = tuple(sorted(edges, key=lambda n: solver.value(positions[n])))
            bound = max(0, math.ceil(solver.best_objective_bound - 1e-6))
            if status != cp_model.OPTIMAL:
                break
            value = int(round(solver.objective_value))
            model.add(expression == value)
            proven.add(distance)
            model.clear_hints()
            for index, name in enumerate(order, 1):
                model.add_hint(positions[name], index)
            bound = None
    optimal = len(proven) == len(layers)
    tiebreak_positions = 0
    if optimal:
        order, tiebreak_positions = break_solver_ties(model, positions, order, dataset.games, deadline)
    values = objective_vector(order, layers)
    objectives = tuple((distance, value, distance in proven) for distance, value in zip(layers, values))
    return Ranking(order, objectives, optimal, "Best fit proven" if optimal else "Provisional · best found",
                   bound, None if optimal else active, dataset.fingerprint, tiebreak_positions)


def calculate_ranges(dataset, ranking, selected, seconds=30):
    if not ranking.optimal or ranking.fingerprint != dataset.fingerprint:
        raise ValueError("Optimal rank ranges require a proven ranking for these results.")
    selected = tuple(dict.fromkeys(selected))
    if len(selected) > 5 or any(n not in ranking.order for n in selected):
        raise ValueError("Select up to five ranked teams.")
    deadline = time.monotonic() + seconds
    edges = graph(dataset.games)
    n = len(edges)
    if topological_order(edges) is not None:
        reach = {a: set(shortest_paths(edges, a)) - {a} for a in edges}
        return tuple(RankRange(a, 1 + sum(a in targets for targets in reach.values()), n - len(reach[a]), True, True)
                     for a in selected)
    from ortools.sat.python import cp_model
    built = build_model(tuple(edges), layers_for(dataset.games, edges), ranking.order, deadline)
    if not built:
        return tuple(RankRange(a, 1, n, False, False) for a in selected)
    model, positions, expressions = built
    for distance, value, _ in ranking.objectives:
        model.add(expressions[distance] == value)
    result = []
    tasks_left = 2 * len(selected)
    for name in selected:
        low, high, exact = 1, n, []
        for maximize in (False, True):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                exact.append(False)
            else:
                # Divide the remaining budget fairly among outstanding endpoints.
                model.minimize(n + 1 - positions[name] if maximize else positions[name])
                solver = new_solver(remaining / tasks_left)
                status = solver.solve(model)
                if status in (cp_model.INFEASIBLE, cp_model.MODEL_INVALID):
                    raise RuntimeError("Rank range model failed validation.")
                proven = status == cp_model.OPTIMAL
                bound = int(round(solver.objective_value)) if proven else math.ceil(solver.best_objective_bound - 1e-6)
                bound = max(1, min(n, bound))
                if maximize:
                    high = n + 1 - bound
                else:
                    low = bound
                exact.append(proven)
            tasks_left -= 1
        result.append(RankRange(name, low, high, *exact))
    return tuple(result)


def exception_games(dataset, ranking):
    pos = {name: i for i, name in enumerate(ranking.order)}
    return tuple(g for g in dataset.games if pos[g.winner] > pos[g.loser])


def ranking_rows(dataset, ranking, ranges=()):
    pos = {name: i for i, name in enumerate(ranking.order, 1)}
    wins = Counter(g.winner for g in dataset.games)
    losses = Counter(g.loser for g in dataset.games)
    exceptions = Counter(n for g in exception_games(dataset, ranking) for n in (g.winner, g.loser))
    intervals = {r.team: f"{r.low}–{r.high}" + (" (bounds incomplete)" if not (r.low_exact and r.high_exact) else "") for r in ranges}
    stats = resume_stats(dataset.games)
    return pd.DataFrame([dict(position=pos.get(t.name), team=t.name, logo=t.logo, conference=t.conference,
                              record=f"{wins[t.name]}–{losses[t.name]}", exceptions=exceptions[t.name],
                              win_pct=float(stats[t.name][0]) if t.name in stats else None,
                              opponent_win_pct=float(stats[t.name][2]) if t.name in stats else None,
                              rank_range=intervals.get(t.name, "Not calculated" if t.name in pos else "Unranked"))
                         for t in dataset.teams], columns=["position", "team", "logo", "conference", "record", "win_pct", "opponent_win_pct", "exceptions", "rank_range"]).sort_values(["position", "team"], na_position="last")


def path_games(games, path):
    # Earliest available meeting is the deterministic witness for a repeated edge.
    first = {}
    for game in sorted(games, key=lambda g: (not bool(g.date), g.date, g.id)):
        first.setdefault((game.winner, game.loser), game)
    return tuple(first[(a, b)] for a, b in zip(path, path[1:]))


def short_cycles(games, team=None, limit=50):
    edges = graph(games)
    paths = {a: shortest_paths(edges, a) for a in edges}
    found = set()
    for source in edges:
        choices = [(source, *paths[target][source]) for target in edges[source] if source in paths[target]]
        if not choices:
            continue
        cycle = min(choices, key=lambda c: (len(c), c))[:-1]
        if 2 <= len(cycle) <= 6:
            found.add(min(cycle[i:] + cycle[:i] for i in range(len(cycle))))
    cycles = sorted((c for c in found if not team or team in c), key=lambda c: (len(c), c))
    return tuple(cycles[:limit]), len(cycles) > limit


def longest_cycles(games, team=None, max_teams=16, limit=50, seconds=60):
    """Search simple cycles longest-first; every node occurs once before closing.

    Canonical roots avoid rotational duplicates. Shortest-return distances prune
    impossible branches. A bounded search never claims the best found is longest
    unless longer lengths were exhausted or the requested cap was reached.
    """
    if not 2 <= max_teams <= 16 or limit < 1:
        raise ValueError("Choose 2–16 teams and a positive result limit.")
    deadline = time.monotonic() + seconds
    edges = graph(games)
    paths = {a: shortest_paths(edges, a) for a in edges}
    found = set()
    for source in edges:
        choices = [(source, *paths[target][source]) for target in edges[source] if source in paths[target]]
        if choices:
            cycle = min(choices, key=lambda c: (len(c), c))[:-1]
            if len(cycle) <= max_teams and (not team or team in cycle):
                found.add(min(cycle[i:] + cycle[:i] for i in range(len(cycle))))
    roots = [team] if team in edges else ([] if team else sorted(edges))
    root_graphs = []
    for root in roots:
        component = {a for a in paths[root] if root in paths[a] and (team or a >= root)}
        if len(component) < 2:
            continue
        reverse = {a: [] for a in component}
        local = {a: tuple(sorted((b for b in edges[a] if b in component), key=lambda b: (-len(edges[b]), b))) for a in component}
        for a, targets in local.items():
            for b in targets:
                reverse[b].append(a)
        distances = {root: 0}
        queue = deque([root])
        while queue:
            current = queue.popleft()
            for previous in reverse[current]:
                if previous not in distances:
                    distances[previous] = distances[current] + 1
                    queue.append(previous)
        root_graphs.append((root, local, distances))
    completed_lengths = set()
    reason = "Complete"
    for length in range(max_teams, 1, -1):
        stopped = False
        for root, local, distances in root_graphs:
            if len(local) < length:
                continue
            path, visited = [root], {root}

            def visit(current):
                nonlocal reason
                if time.monotonic() >= deadline:
                    reason = "Time limit"
                    return True
                if len(path) == length:
                    if root in local[current]:
                        cycle = tuple(path)
                        found.add(min(cycle[i:] + cycle[:i] for i in range(len(cycle))))
                        if sum(len(c) >= length for c in found) >= limit:
                            reason = "Result limit"
                            return True
                    return False
                for target in local[current]:
                    if target in visited or distances.get(target, length + 1) > length - len(path):
                        continue
                    visited.add(target)
                    path.append(target)
                    stop = visit(target)
                    path.pop()
                    visited.remove(target)
                    if stop:
                        return True
                return False

            if visit(root):
                stopped = True
                break
        if stopped:
            break
        completed_lengths.add(length)
    cycles = tuple(sorted(found, key=lambda c: (-len(c), c))[:limit])
    proven = bool(cycles) and all(length in completed_lengths for length in range(len(cycles[0]) + 1, max_teams + 1))
    return CycleSearch(cycles, reason == "Complete", proven, reason)


def game_rows(games):
    return pd.DataFrame([{"Winner": g.winner, "Loser": g.loser,
                          "Score": f"{g.winner_points}–{g.loser_points}",
                          "Date": g.date[:10] or "Unknown", "Week": checkpoint_label((g.phase, g.week))}
                         for g in games])

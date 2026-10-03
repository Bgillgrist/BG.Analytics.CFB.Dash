"""Copyable results graphics and compact, accessible on-page graph markup."""

import html
import json
import math
from pathlib import Path

from utils.head_to_head import checkpoint_label, path_games, ranking_rows
from utils.conquest_slides import embed_conquest_logos


def team_payload(dataset, name):
    team = next(t for t in dataset.teams if t.name == name)
    return {"name": name, "logo": team.logo, "logoFallback": team.logo_fallback}


def game_payload(dataset, game):
    return {"winner": team_payload(dataset, game.winner), "loser": team_payload(dataset, game.loser),
            "score": f"{game.winner_points}–{game.loser_points}", "date": game.date[:10] or "Date unavailable"}


def graphic_config(dataset, kind, ranking=None, paths=(), cycle=()):
    config = {"season": dataset.season, "cutoff": checkpoint_label(dataset.cutoff), "kind": kind,
              "status": ranking.status if ranking else "Completed results", "slides": []}
    if kind == "rankings":
        frame = ranking_rows(dataset, ranking)
        rows = []
        for row in frame.dropna(subset=["position"]).head(25).itertuples():
            rows.append({**team_payload(dataset, row.team), "position": int(row.position),
                         "record": row.record, "exceptions": row.exceptions})
        config["slides"] = [{"title": "HEAD TO HEAD TOP 25", "rows": rows,
                             "subtitle": "One representative order · Positions may not be unique"}]
    elif kind == "chains":
        for source, target, path in paths:
            games = path_games(dataset.games, path) if path else ()
            chunks = [games[i:i + 5] for i in range(0, len(games), 5)] or [()]
            for index, chunk in enumerate(chunks, 1):
                config["slides"].append({"title": "THE WIN CHAIN", "subtitle": f"{source} → {target}",
                    "detail": f"{len(games)}-game chain · Part {index}/{len(chunks)}" if path else "No win path in this direction",
                    "games": [game_payload(dataset, g) for g in chunk]})
    elif kind == "circle":
        config["slides"] = [{"title": "CIRCLE OF CHAOS", "subtitle": f"{len(cycle)} teams · Every arrow is a win",
                             "teams": [team_payload(dataset, n) for n in cycle],
                             "games": [game_payload(dataset, g) for g in path_games(dataset.games, (*cycle, cycle[0]))]}]
    else:
        raise ValueError("Unknown graphic type")
    return config


def render_graphic(config):
    teams = []
    for slide in config["slides"]:
        teams.extend(slide.get("rows", []))
        teams.extend(slide.get("teams", []))
        for game in slide.get("games", []):
            teams.extend((game["winner"], game["loser"]))
    embed_conquest_logos(teams)
    encoded = json.dumps(config, allow_nan=False).replace("<", "\\u003c")
    return Path(__file__).with_name("head_to_head_graphics.html").read_text().replace("__H2H_CONFIG__", encoded)


def chain_markup(dataset, path):
    items = []
    for name in path:
        team = team_payload(dataset, name)
        logo = html.escape(team["logo"], quote=True)
        icon = f'<img src="{logo}" alt="" width="40" height="40" style="object-fit:contain">' if logo.startswith(("http://", "https://", "data:image/")) else ""
        items.append(f'<span class="h2h-node">{icon}<strong>{html.escape(name)}</strong></span>')
    return '<div class="h2h-chain">' + '<span aria-label="beat">→</span>'.join(items) + '</div>'


def circle_svg(dataset, cycle):
    """Responsive SVG; game table below supplies full names and dated evidence."""
    size, center, radius = 900, 450, 295
    points = [(center + radius * math.cos(-math.pi / 2 + i * 2 * math.pi / len(cycle)),
               center + radius * math.sin(-math.pi / 2 + i * 2 * math.pi / len(cycle))) for i in range(len(cycle))]
    pieces = [f'<svg viewBox="0 0 {size} {size}" style="display:block;width:100%;max-height:760px" role="img" aria-label="Circle of Chaos" xmlns="http://www.w3.org/2000/svg">',
              '<defs><marker id="h2h-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#ad7735"/></marker></defs>']
    for i, (x, y) in enumerate(points):
        nx, ny = points[(i + 1) % len(points)]
        dx, dy = nx - x, ny - y
        length = math.hypot(dx, dy)
        # Opposite rematch arrows occupy separate parallel lanes.
        ox, oy = (-dy / length * 18, dx / length * 18) if len(cycle) == 2 else (0, 0)
        clearance = min(132 / max(.0001, abs(dx / length)), 58 / max(.0001, abs(dy / length))) + 15
        pieces.append(f'<line x1="{x + dx / length * clearance + ox}" y1="{y + dy / length * clearance + oy}" x2="{nx - dx / length * clearance + ox}" y2="{ny - dy / length * clearance + oy}" stroke="#ad7735" stroke-width="4" marker-end="url(#h2h-arrow)"/>')
    for name, (x, y) in zip(cycle, points):
        pieces.append(f'<rect x="{x - 132}" y="{y - 58}" width="264" height="116" rx="16" fill="#edf3fa" stroke="#bdcbd9"/>')
        logo = team_payload(dataset, name)["logo"]
        if logo.startswith(("http://", "https://", "data:image/")):
            pieces.append(f'<image href="{html.escape(logo, quote=True)}" x="{x - 25}" y="{y - 48}" width="50" height="50"/>')
        words = name.split()
        lines = [name] if len(name) <= 23 else [" ".join(words[:max(1, len(words)//2)]), " ".join(words[max(1, len(words)//2):])]
        for index, line in enumerate(lines):
            pieces.append(f'<text x="{x}" y="{y + 24 + index * 22}" text-anchor="middle" fill="#0c2c50" font-family="Arial" font-size="{min(20, 230/max(1,len(line)) * 1.7)}">{html.escape(line)}</text>')
    return "".join(pieces) + "</svg>"

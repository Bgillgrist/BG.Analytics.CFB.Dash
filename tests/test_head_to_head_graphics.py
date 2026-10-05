import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils import head_to_head as h
from utils import head_to_head_graphics as g
from test_head_to_head import dataset


def test_top25_is_national_and_preserves_provisional_label(monkeypatch):
    data = dataset([(f"Team {i:02}",f"Team {i+1:02}") for i in range(30)])
    result = h.Ranking(tuple(t.name for t in data.teams),(),False,"Provisional · best found",fingerprint=data.fingerprint)
    config = g.graphic_config(data,"rankings",ranking=result)
    assert len(config["slides"][0]["rows"]) == 25
    assert config["status"] == "Provisional · best found"
    assert config["tiebreak"] == "Fewer FBS losses → More FBS wins → Opponent win %"
    assert config["slides"][0]["subtitle"] == "Direct wins → Two-game chains → Record → Résumé"
    monkeypatch.setattr(g,"embed_conquest_logos",lambda teams: None)
    markup = g.render_graphic(config)
    payload = json.loads(re.search(r"const config = (.*);",markup).group(1))
    assert payload == config
    assert 'width=2160, height=2700' in markup
    assert 'navigator.clipboard.write' in markup


def test_chain_pagination_preserves_every_edge_in_order():
    data = dataset([(f"Team {i}",f"Team {i+1}") for i in range(13)])
    path = tuple(f"Team {i}" for i in range(14))
    config = g.graphic_config(data,"chains",paths=[(path[0],path[-1],path),(path[-1],path[0],())])
    assert [len(s["games"]) for s in config["slides"]] == [5,5,3,0]
    games = [game for s in config["slides"] for game in s["games"]]
    assert [game["winner"]["name"] for game in games] == list(path[:-1])
    assert config["slides"][-1]["detail"] == "No win path in this direction"


def test_circles_preserve_closing_game_and_escape_html(monkeypatch):
    data = dataset([("A</script>","B"),("B","C"),("C","A</script>")])
    config = g.graphic_config(data,"circle",cycle=("A</script>","B","C"))
    assert len(config["slides"][0]["games"]) == 3
    monkeypatch.setattr(g,"embed_conquest_logos",lambda teams: None)
    assert "A</script>" not in g.render_graphic(config)
    assert "A&lt;/script&gt;" in g.circle_svg(data,("A</script>","B","C"))
    assert "A&lt;/script&gt;" in g.chain_markup(data,("A</script>","B"))


def test_16_team_circle_overview_and_evidence_preserve_closing_link():
    cycle = tuple(f"Team {i:02}" for i in range(16))
    data = dataset(list(zip(cycle,(*cycle[1:],cycle[0]))))
    config = g.graphic_config(data,"circle",cycle=cycle)
    assert len(config["slides"]) == 5
    details = [game for slide in config["slides"][1:] for game in slide["games"]]
    assert len(details) == 16
    assert details[-1]["winner"]["name"] == cycle[-1]
    assert details[-1]["loser"]["name"] == cycle[0]
    markup = g.circle_svg(data,cycle)
    assert all(name in markup for name in cycle)

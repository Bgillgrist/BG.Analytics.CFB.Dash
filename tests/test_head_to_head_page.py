"""Page interaction tests run without a database or CP-SAT (DAG fixtures)."""

from pathlib import Path
import sys

import pandas as pd
import pytest

st = pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app"))
from utils import head_to_head as h
from utils import head_to_head_graphics as g
from test_head_to_head import row


def widget(elements,label):
    return next(e for e in elements if e.label == label)


@pytest.fixture
def page(monkeypatch):
    st.cache_data.clear()
    monkeypatch.setattr(h,"load_seasons",lambda:[2026])
    rows=pd.DataFrame([row(homeconference="SEC",awayconference="ACC"),
        row(id=2,hometeam="B",awayteam="C",week=2,homeconference="ACC",awayconference="SEC"),
        row(id=3,hometeam="D",awayteam="A",week=3,completed=False,homeconference="SEC",awayconference="SEC")])
    monkeypatch.setattr(h,"load_season",lambda season:(rows,pd.DataFrame()))
    monkeypatch.setattr(g,"embed_conquest_logos",lambda teams:None)
    yield AppTest.from_file(str(ROOT/"app/pages/head_to_head_analysis.py"),default_timeout=20)
    st.cache_data.clear()


def test_explicit_calculation_filters_and_ranges(page):
    page.run()
    assert not page.exception
    assert [t.label for t in page.tabs] == ["Rankings","Win-chain explorer","Circle of Chaos"]
    assert any("fewer FBS losses" in item.value for item in page.markdown)
    assert any("Missouri → Florida → Ole Miss" in item.value for item in page.markdown)
    assert "h2h_result" not in page.session_state
    widget(page.button,"Calculate rankings").click().run()
    assert not page.exception
    original=page.session_state["h2h_result"]
    assert original.order == ("A","B","C")
    widget(page.multiselect,"Conferences").set_value(["ACC"]).run()
    assert page.session_state["h2h_result"] == original
    widget(page.multiselect,"Teams for rank ranges").set_value(["B"]).run()
    widget(page.button,"Calculate rank ranges").click().run()
    assert page.session_state["h2h_ranges"] == (h.RankRange("B",2,2,True,True),)
    widget(page.button,"Show Top 25 graphic").click().run()
    assert "h2h_graphic_rankings" in page.session_state
    widget(page.selectbox,"Through week").set_value(("regular",1)).run()
    assert not page.exception
    assert "h2h_result" not in page.session_state
    assert "h2h_ranges" not in page.session_state
    assert "h2h_graphic_rankings" not in page.session_state


def test_chain_graphic_invalidates_on_team_change(page):
    page.run()
    widget(page.button,"Show matchup chain graphics").click().run()
    assert "h2h_graphic_chains" in page.session_state
    widget(page.selectbox,"Second team").set_value("C").run()
    assert "h2h_graphic_chains" not in page.session_state
    assert not page.exception


def test_empty_and_failed_data(page,monkeypatch):
    monkeypatch.setattr(h,"load_seasons",lambda:[])
    page.run()
    assert not page.exception
    assert any("No FBS seasons" in x.value for x in page.info)
    def failure():
        raise ConnectionError("private error")
    monkeypatch.setattr(h,"load_seasons",failure)
    page.run()
    assert not page.exception
    assert any("could not be loaded" in x.value for x in page.error)


def test_no_completed_games_shows_unranked_roster(page,monkeypatch):
    monkeypatch.setattr(h,"load_season",lambda season:(pd.DataFrame([row(completed=False)]),pd.DataFrame()))
    page.run()
    assert not page.exception
    assert page.dataframe[0].value.Status.tolist() == ["Unranked","Unranked"]


def test_corrected_scores_invalidate_existing_result(page,monkeypatch):
    page.run()
    widget(page.button,"Calculate rankings").click().run()
    assert "h2h_result" in page.session_state
    st.cache_data.clear()
    monkeypatch.setattr(h,"load_season",lambda season:(pd.DataFrame([row(homepoints=3)]),pd.DataFrame()))
    page.run()
    assert not page.exception
    assert "h2h_result" not in page.session_state


def test_provisional_ranking_blocks_optimal_ranges_and_labels_graphic(page,monkeypatch):
    original=h.solve_ranking
    def provisional(data):
        from dataclasses import replace
        result=original(data)
        return replace(result,optimal=False,status="Provisional · best found",active_distance=1,bound=0,
                       objectives=tuple((d,v,False) for d,v,_ in result.objectives))
    monkeypatch.setattr(h,"solve_ranking",provisional)
    page.run()
    widget(page.button,"Calculate rankings").click().run()
    assert not page.exception
    assert any("unavailable until" in item.value for item in page.info)
    assert not any(b.label=="Calculate rank ranges" for b in page.button)
    widget(page.button,"Show Top 25 graphic").click().run()
    assert "Provisional" in page.session_state["h2h_graphic_rankings"][1]


def test_circle_explorer_and_graphics_do_not_require_solver(page,monkeypatch):
    monkeypatch.setattr(h,"load_season",lambda season:(pd.DataFrame([row(),row(id=2,hometeam="B",awayteam="A")]),pd.DataFrame()))
    page.run()
    assert not any(s.label == "Circle" for s in page.selectbox)
    widget(page.button,"Search longest circles").click().run()
    assert not page.exception
    assert widget(page.selectbox,"Circle").value == ("A","B")
    assert any("Contradictory paths" in item.value for item in page.warning)
    widget(page.button,"Show Circle of Chaos graphic").click().run()
    assert "h2h_graphic_circle" in page.session_state
    widget(page.selectbox,"Maximum teams in circle").set_value(8).run()
    assert "h2h_cycles" not in page.session_state
    assert "h2h_graphic_circle" not in page.session_state

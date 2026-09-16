"""Streamlit interactions use saved fixtures; they never access the database/API."""
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")
pytest.importorskip("cfb_betting")
from streamlit.testing.v1 import AppTest
import streamlit as st

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"app"))
from utils import betting
from cfb_betting.domain import MODELS


def widget(elements,label):
    return next(element for element in elements if element.label==label)


@pytest.fixture
def setup_pages(monkeypatch):
    st.cache_data.clear()
    games=pd.DataFrame([dict(game_id=str(i),season=2026,week=i,season_type="regular",
        kickoff=pd.Timestamp(day),kickoff_known=True,home_team="Alpha",away_team="Bravo",
        home_conference="SEC",away_conference="ACC",completed=completed,
        homepoints=24 if completed else None,awaypoints=20 if completed else None,cancelled=False)
        for i,day,completed in [(1,"2099-09-18T16:00Z",False),(2,"2026-09-12T16:00Z",True)]])
    runs=pd.DataFrame([dict(run_id="run",season=2026,source="live",status="success",
        as_of=pd.Timestamp("2026-09-10T12:00Z"),completed_at=pd.Timestamp("2026-09-10T12:10Z"),
        trained_at=pd.Timestamp("2026-09-10T12:00Z"),model_version="test-v1")])
    scopes=pd.DataFrame([dict(runs.iloc[0],game_id=str(i)) for i in (1,2)])
    candidates=[]
    for identifier in ["1","2"]:
        for model in MODELS:
            for market in ["spread","moneyline"]:
                for provider,edge in [("Book A",6),("Book B",5)]:
                    candidates.append(dict(game_id=identifier,run_id="run",model=model,market=market,side="home",
                        provider=provider,team="Alpha",opponent="Bravo",conference="SEC",handicap=-3.5 if market=="spread" else None,
                        american=-110 if market=="moneyline" else None,probability=.56,baseline=.5,edge_pp=edge,
                        push_probability=0,expected_return=.05 if market=="moneyline" else None,
                        model_spread=-6,classification="Strong",model_version="test-v1"))
    data=dict(games=games,runs=runs,scopes=scopes,candidates=pd.DataFrame(candidates),metrics={},outcomes=pd.DataFrame())
    monkeypatch.setattr(betting,"load_seasons",lambda:pd.DataFrame({"season":[2026,2025]}))
    monkeypatch.setattr(betting,"load_data",lambda *args:data)
    monkeypatch.setattr(betting,"can_refresh",lambda:True)
    calls=[]
    def execute(season,retrain,progress):
        calls.append((season,retrain))
        progress("Test progress")
        return {"classifications":32,"games":2}
    monkeypatch.setattr(betting,"execute",execute)
    yield data,calls
    st.cache_data.clear()


def test_best_bets_defaults_and_filters_never_train(setup_pages):
    data,calls=setup_pages
    page=AppTest.from_file(str(ROOT/"app/pages/best_bets.py"),default_timeout=20).run()
    assert not page.exception
    assert widget(page.selectbox,"Show").value==10
    assert widget(page.selectbox,"Model").value=="teamrankings"
    assert len(page.dataframe[0].value)==2
    widget(page.selectbox,"Market").select("Spread").run()
    widget(page.multiselect,"Sportsbooks").set_value(["Book B"]).run()
    assert not page.exception
    table=page.dataframe[0].value
    assert len(table)==1 and table.iloc[0].provider=="Book B"
    assert calls==[]


def test_explicit_training_refresh_and_failure_preserve_results(setup_pages,monkeypatch):
    _,calls=setup_pages
    page=AppTest.from_file(str(ROOT/"app/pages/best_bets.py"),default_timeout=20).run()
    widget(page.button,"Run analysis").click().run()
    assert calls==[(2026,True)] and not page.exception
    widget(page.button,"Refresh odds").click().run()
    assert calls[-1]==(2026,False) and not page.exception
    def fail(*args,**kwargs):
        raise RuntimeError("fixture failure")
    monkeypatch.setattr(betting,"execute",fail)
    widget(page.button,"Refresh odds").click().run()
    assert not page.exception
    assert any("last successful" in message.value for message in page.error)
    assert len(page.dataframe[0].value)==2


def test_history_filters_do_not_reselect_another_book(setup_pages):
    data,calls=setup_pages
    # Book B is a canonical moneyline selection, so it is a valid filter option,
    # but choosing it must not substitute its inferior spread for Book A's pick.
    moneyline=data["candidates"].market.eq("moneyline") & data["candidates"].provider.eq("Book B")
    data["candidates"].loc[moneyline,["american","baseline","edge_pp","classification"]]=[150,.4,16,"Very strong"]
    page=AppTest.from_file(str(ROOT/"app/pages/betting_history.py"),default_timeout=20).run()
    assert not page.exception
    assert [tab.label for tab in page.tabs]==["Classification performance","Graded picks","Classification timeline"]
    table=next(element.value for element in page.dataframe if "snapshot_age_hours" in element.value)
    assert len(table)==8
    assert set(table.provider)=={"Book A"}
    widget(page.multiselect,"Sportsbooks").set_value(["Book B"]).run()
    assert any(metric.label=="Forecasts in this view" and metric.value=="0" for metric in page.metric)
    widget(page.multiselect,"Sportsbooks").set_value([]).run()
    widget(page.multiselect,"Models").set_value(["spread"]).run()
    assert len(next(element.value for element in page.dataframe if "snapshot_age_hours" in element.value))==2
    widget(page.selectbox,"Market").select("Moneyline").run()
    assert not page.exception and calls==[]


def test_missing_snapshots_and_missing_key_are_clear(setup_pages,monkeypatch):
    data,_=setup_pages
    data["scopes"]=pd.DataFrame()
    data["candidates"]=pd.DataFrame()
    monkeypatch.setattr(betting,"can_refresh",lambda:False)
    page=AppTest.from_file(str(ROOT/"app/pages/best_bets.py"),default_timeout=20).run()
    assert not page.exception
    assert widget(page.button,"Run analysis").disabled
    assert any("No classified" in message.value for message in page.info)
    page=AppTest.from_file(str(ROOT/"app/pages/betting_history.py"),default_timeout=20).run()
    assert not page.exception
    assert any("No saved pregame" in message.value for message in page.info)


def test_history_keeps_timeline_when_latest_collection_has_no_quotes(setup_pages):
    data,calls=setup_pages
    latest=data["scopes"].copy()
    latest["run_id"]="empty-collection"
    latest["as_of"]=pd.Timestamp("2026-09-11T12:00Z")
    latest["completed_at"]=pd.Timestamp("2026-09-11T12:10Z")
    data["scopes"]=pd.concat([data["scopes"],latest],ignore_index=True)
    page=AppTest.from_file(str(ROOT/"app/pages/betting_history.py"),default_timeout=20).run()
    assert not page.exception
    assert widget(page.selectbox,"Timeline game").value=="1"
    assert len(page.dataframe[-1].value)>0
    assert any(metric.label=="Forecasts in this view" and metric.value=="0" for metric in page.metric)
    assert calls==[]

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
    def current_data(*args):
        current = betting.current_candidates(data)
        current = current.drop(columns=["as_of", "quote_age_hours"], errors="ignore")
        return dict(data, current=True, candidates=current, quote_issues=[])
    monkeypatch.setattr(betting,"load_current_data",current_data)
    current_data.clear = lambda: None
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
    widget(page.button,"Reload current odds").click().run()
    assert calls==[(2026,True)] and not page.exception
    def fail(*args,**kwargs):
        raise RuntimeError("fixture failure")
    monkeypatch.setattr(betting,"execute",fail)
    widget(page.button,"Run analysis").click().run()
    assert not page.exception
    assert any("Training failed" in message.value for message in page.error)
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


def test_current_table_lines_are_rescored_without_snapshots_or_api(monkeypatch):
    from contextlib import contextmanager

    st.cache_data.clear()
    games = pd.DataFrame([dict(game_id="1", season=2026, week=8, season_type="regular",
        kickoff=pd.Timestamp("2099-10-17T16:00Z"), kickoff_known=True,
        home_team="Opponent", away_team="Ohio State", home_conference="SEC", away_conference="Big Ten",
        homeclassification="fbs", awayclassification="fbs", completed=False, cancelled=False)])
    data = dict(games=games, runs=pd.DataFrame([dict(status="success")]),
                scopes=pd.DataFrame(), candidates=pd.DataFrame(), metrics={})
    monkeypatch.setattr(betting, "credentials", lambda: object())
    monkeypatch.setattr(betting, "read_data", lambda *args: dict(data))
    class Connection:
        read_only = False
    connection = Connection()
    @contextmanager
    def connect(config):
        yield connection
    monkeypatch.setattr(betting.store, "connect", connect)
    monkeypatch.setattr(betting.store, "latest_model", lambda *args:
        dict(artifact={"version": betting.MODEL_VERSION}, metrics={}))
    monkeypatch.setattr(betting.store, "load_inputs", lambda *args: (games, pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(betting, "prepare_games", lambda frame: frame)
    monkeypatch.setattr(betting, "build_features", lambda games, *args, **kwargs: games)
    payload = [dict(id="1", lines=[dict(provider="DraftKings", spread=-1.5)])]
    monkeypatch.setattr(betting.store, "load_historical_quotes", lambda *args: payload)
    def score(bundle, targets, quotes):
        if quotes.empty:
            return pd.DataFrame()
        # Check the model's spread input is updated alongside the displayed quote.
        assert targets.iloc[0].avg_spread == quotes.loc[quotes.side.eq("home"), "handicap"].iloc[0]
        result = quotes.copy()
        result["model"] = "spread"
        result["probability"] = .5 + result.handicap / 100
        result["edge_pp"] = result.handicap
        return result
    monkeypatch.setattr(betting, "score_quotes", score)
    monkeypatch.setattr(betting, "run_analysis", lambda *args, **kwargs: pytest.fail("Must not run analysis"))
    first = betting.current_candidates(betting.load_current_data(2026))
    assert first.loc[first.side.eq("away"), "handicap"].iloc[0] == 1.5
    payload[0]["lines"][0]["spread"] = -3.5
    betting.load_current_data.clear()
    second = betting.current_candidates(betting.load_current_data(2026))
    ohio = second.loc[second.side.eq("away")].iloc[0]
    assert ohio.handicap == 3.5 and ohio.probability == .535 and ohio.edge_pp == 3.5
    assert "quote_age_hours" not in second and "table_read_at" in second
    assert connection.read_only
    # Deleted odds must disappear, never fall back to a saved quote.
    payload.clear()
    betting.load_current_data.clear()
    assert betting.current_candidates(betting.load_current_data(2026)).empty
    st.cache_data.clear()


def test_scoring_runtime_failure_is_not_reported_as_database_failure(setup_pages, monkeypatch):
    def fail(*args):
        raise RuntimeError('XGBoost Library (libxgboost.dylib) could not be loaded. private runtime path')
    monkeypatch.setattr(betting, 'score_quotes', fail)
    with pytest.raises(betting.BettingScoringError, match='OpenMP') as error:
        betting.score_current_quotes({}, pd.DataFrame(), pd.DataFrame())
    assert 'private runtime path' not in str(error.value)
    def failed_load(*args):
        raise error.value
    monkeypatch.setattr(betting, 'load_current_data', failed_load)
    page = AppTest.from_file(str(ROOT/'app/pages/best_bets.py'), default_timeout=20).run()
    assert not page.exception
    assert any('Current odds loaded, but the model runtime could not start' in item.value for item in page.error)

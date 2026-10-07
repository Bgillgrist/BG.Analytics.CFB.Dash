import sys
from pathlib import Path

import pytest
import pandas as pd
st = pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from utils import scatterplot as sp
from test_scatterplot import rows


def widget(elements,label):
    return next(e for e in elements if e.label == label)


@pytest.fixture
def page(monkeypatch):
    monkeypatch.setattr(sp,'load_catalog',lambda source: (['offense_ppa','defense_ppa'] if source == 'Season stats' else ['offense_ppa','defense_ppa','offense_plays'],[2026,2025]))
    monkeypatch.setattr(sp,'load_rows',lambda source,season: rows().assign(offense_plays=60) if source == 'Game stats' else rows().iloc[:1].drop(columns=['week','season_type','opponent']))
    monkeypatch.setattr(sp,'render_graphic',lambda config: '<html>Graphic</html>')
    return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app/pages/scatterplot_creator.py'))


def test_defaults_empty_conferences_and_sources(page):
    page.run()
    assert not page.exception
    assert widget(page.selectbox,'Season').value == 2026
    assert widget(page.selectbox,'X metric').value == 'offense_ppa'
    assert widget(page.selectbox,'Y metric').value == 'defense_ppa'
    widget(page.multiselect,'Conferences').set_value([]).run()
    assert not page.exception and any('No points' in i.value for i in page.info)
    widget(page.radio,'Data source').set_value('Game stats').run()
    assert not page.exception
    assert widget(page.multiselect,'Weeks').value == [('postseason',1)]
    widget(page.selectbox,'X metric').set_value('offense_plays').run()
    widget(page.radio,'Data source').set_value('Season stats').run()
    assert not page.exception
    assert widget(page.selectbox,'X metric').value == 'offense_ppa'


def test_game_averages_weeks_axes_and_labels(page):
    page.run()
    widget(page.radio,'Data source').set_value('Game stats').run()
    widget(page.multiselect,'Weeks').set_value([('regular',1),('regular',2)]).run()
    widget(page.radio,'Points represent').set_value('Team averages').run()
    assert not page.exception
    data = page.dataframe[0].value
    assert data['Contributing games'].tolist() == [2]
    widget(page.radio,'X direction (left → right)').set_value('High to low').run()
    widget(page.radio,'Y direction (bottom → top)').set_value('High to low').run()
    widget(page.text_input,'Chart title').set_value('My comparison').run()
    assert not page.exception
    widget(page.multiselect,'Weeks').set_value([]).run()
    assert not page.exception and any('No points' in i.value for i in page.info)

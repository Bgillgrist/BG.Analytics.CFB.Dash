import json
from pathlib import Path
import re
import sys

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from utils import scatterplot as sp


def rows():
    return pd.DataFrame([
        dict(team='A', conference='SEC', offense_ppa=.2, defense_ppa=.1, week=1, season_type='regular', opponent='B', logo='', logoFallback=''),
        dict(team='A', conference='SEC', offense_ppa=.8, defense_ppa=.3, week=2, season_type='regular', opponent='C', logo='', logoFallback=''),
        dict(team='A', conference='SEC', offense_ppa=8., defense_ppa=None, week=3, season_type='regular', opponent='D', logo='', logoFallback=''),
        dict(team='B', conference='ACC', offense_ppa=float('inf'), defense_ppa=.2, week=1, season_type='regular', opponent='A', logo='', logoFallback=''),
        dict(team='C', conference='ACC', offense_ppa=-.2, defense_ppa=.4, week=1, season_type='postseason', opponent='A', logo='', logoFallback=''),
    ])

METRICS = ['offense_ppa', 'defense_ppa']


def test_metric_discovery_and_labels():
    metadata = pd.DataFrame([dict(column_name=c, data_type=t) for c,t in [
        ('game_id','bigint'),('season','integer'),('week','integer'),('team','text'),
        ('offense_ppa','double precision'),('offense_havoc_total','numeric'),('new_metric','real'),('opponent_id','bigint')]])
    assert sp.discover_metrics(metadata) == ['offense_ppa','offense_havoc_total','new_metric']
    assert sp.metric_label('offense_ppa') == 'Offense · PPA/play'
    assert sp.is_rate('defense_successrate') and sp.is_rate('offense_havoc_db')
    assert not sp.is_rate('offense_ppa')


def test_filters_and_pairwise_averages():
    points, omitted = sp.prepare_points(rows(), *METRICS, METRICS, ['SEC'], [('regular',1),('regular',2),('regular',3)], True)
    assert len(points) == 1 and omitted == 1
    assert points.iloc[0].x == pytest.approx(.5)
    assert points.iloc[0].y == pytest.approx(.2)
    assert points.iloc[0].games == 2
    points, omitted = sp.prepare_points(rows(), *METRICS, METRICS, ['ACC'], [('postseason',1)])
    assert points.team.tolist() == ['C'] and omitted == 0
    points, omitted = sp.prepare_points(rows(), *METRICS, METRICS, ['SEC','ACC'])
    assert len(points) == 3 and omitted == 2


@pytest.mark.parametrize('conferences,weeks', [([],None),(['SEC'],[])])
def test_empty_selections(conferences,weeks):
    points, _ = sp.prepare_points(rows(), *METRICS, METRICS, conferences, weeks)
    assert points.empty


def test_invalid_metric_and_same_metric():
    with pytest.raises(ValueError):
        sp.prepare_points(rows(), 'invalid', 'defense_ppa', METRICS, ['SEC'])
    points, _ = sp.prepare_points(rows(), 'offense_ppa', 'offense_ppa', METRICS, ['SEC'])
    assert (points.x == points.y).all()


def test_weeks_and_logos():
    assert sp.week_options(rows())[-1] == ('postseason',1)
    result = sp.attach_logos(rows().drop(columns=['logo','logoFallback']), pd.DataFrame([{'cfb_name':'A','Logo':'https://a','DarkLogo':'https://b'}]))
    assert result.iloc[0].logo == 'https://a'
    assert result.iloc[-1].logo == ''


def test_config_and_safe_serialization(monkeypatch):
    from utils import conquest_slides
    monkeypatch.setattr(conquest_slides, 'embed_conquest_logos', lambda points: None)
    points, _ = sp.prepare_points(rows(), *METRICS, METRICS, ['SEC'])
    config = sp.graphic_config(points, title='</script><script>bad()</script>', subtitle='2026', scope='SEC',
        x=METRICS[0], y=METRICS[1], x_label='X', y_label='Y', reverse_y=True)
    markup = sp.render_graphic(config)
    assert config['title'] not in markup
    payload = json.loads(re.search(r'const config = (.*);',markup).group(1))
    assert payload.pop('brandLogo').startswith('data:image/png;base64,')
    assert len(payload.pop('brandBounds')) == 4
    assert payload == config
    assert config['y']['reverse'] is True
    assert config['points'][0]['detail'] == 'vs B · Regular season · Week 1'


def test_game_query_restricts_completed_fbs_and_parameters(monkeypatch):
    from utils import db
    calls = []
    def read(sql, params=None):
        calls.append((sql,params))
        if 'team_map' in sql:
            return pd.DataFrame()
        return rows().assign(schedule_week=rows().week,schedule_phase=rows().season_type)
    monkeypatch.setattr(db,'read_df',read)
    sp.load_rows('Game stats',2026)
    sql, params = calls[0]
    assert 'g.completed IS TRUE' in sql
    assert "LOWER(g.homeclassification) = 'fbs'" in sql
    assert "LOWER(g.awayclassification) = 'fbs'" in sql
    assert 'gs.season = g.season' in sql
    assert params == {'season':2026}


def test_season_week_coverage(monkeypatch):
    from utils import db
    calls = []
    def read(sql, params):
        calls.append((sql, params))
        return pd.DataFrame({'season_type':['regular']*3+['postseason'], 'week':[0,1,3,1]})
    monkeypatch.setattr(db,'read_df',read)
    assert sp.load_season_week_scope(2026) == 'Regular season weeks 0–1, 3; Postseason weeks 1'
    assert calls[0][1] == {'season':2026}
    assert 'g.completed IS TRUE' in calls[0][0]

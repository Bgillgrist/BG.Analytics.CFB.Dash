"""Read-only scatterplot data, metric metadata, and graphics configuration."""
import base64
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from utils.weekly_performances import METRIC_LABELS

SCATTERPLOT_API_VERSION = 2

TABLES = {"Season stats": "team_advanced_season_stats", "Game stats": "team_advanced_game_stats"}
NUMERIC_TYPES = {"smallint", "integer", "bigint", "numeric", "decimal", "real", "double precision"}
ADMIN = {"id", "game_id", "team_id", "opponent_id", "season", "week", "year"}
ELIGIBLE = """g.completed IS TRUE AND LOWER(g.homeclassification) = 'fbs'
    AND LOWER(g.awayclassification) = 'fbs' AND gs.season = g.season
    AND gs.team IN (g.hometeam, g.awayteam) AND g.hometeam <> g.awayteam"""


def discover_metrics(metadata):
    return [str(r.column_name) for r in metadata.itertuples()
            if r.data_type in NUMERIC_TYPES and r.column_name not in ADMIN
            and not r.column_name.endswith('_id')]


def metric_label(column):
    side, _, suffix = column.partition('_')
    extra = {
        'totalopportunies': 'Total opportunities', 'pointsperopportunity': 'Points per opportunity',
        'fieldposition_averagestart': 'Average starting field position',
        'fieldposition_averagepredictedpoints': 'Starting field position predicted points',
        'havoc_total': 'Havoc rate', 'havoc_frontseven': 'Front seven havoc rate', 'havoc_db': 'DB havoc rate',
        'standarddowns_rate': 'Standard-down rate', 'passingdowns_rate': 'Passing-down rate',
        'rushingplays_rate': 'Rushing play rate', 'passingplays_rate': 'Passing play rate',
    }
    name = METRIC_LABELS.get(suffix, extra.get(suffix, suffix.replace('_', ' ').title()))
    return f"{side.title()} · {name}" if side in ('offense', 'defense') else column.replace('_', ' ').title()


def is_rate(column):
    return column.endswith(('successrate', 'powersuccess', 'stuffrate', '_rate')) or '_havoc_' in column


def load_catalog(source):
    from utils.db import read_df
    table = TABLES[source]
    metadata = read_df("""SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table ORDER BY ordinal_position""", {'table': table})
    if source == 'Game stats':
        seasons = read_df(f"""SELECT DISTINCT gs.season FROM public.{table} gs
            JOIN public.game_data g ON g.id = gs.game_id WHERE {ELIGIBLE} ORDER BY gs.season DESC""")
    else:
        seasons = read_df(f"SELECT DISTINCT season FROM public.{table} WHERE season IS NOT NULL ORDER BY season DESC")
    return discover_metrics(metadata), seasons['season'].astype(int).tolist()


def load_rows(source, season):
    from utils.db import read_df
    table = TABLES[source]
    if source == 'Season stats':
        rows = read_df(f"SELECT * FROM public.{table} WHERE season = :season ORDER BY team", {'season': int(season)})
    else:
        rows = read_df(f"""SELECT gs.*, g.week AS schedule_week,
            LOWER(COALESCE(g.seasontype, 'regular')) AS schedule_phase,
            CASE WHEN gs.team = g.hometeam THEN g.homeconference ELSE g.awayconference END AS conference
            FROM public.{table} gs JOIN public.game_data g ON g.id = gs.game_id
            WHERE {ELIGIBLE} AND gs.season = :season ORDER BY g.startdate, g.id, gs.team""", {'season': int(season)})
        rows['week'] = rows['schedule_week']
        rows['season_type'] = rows['schedule_phase']
    assets = read_df('SELECT * FROM public.team_map')
    return attach_logos(rows, assets)


def attach_logos(rows, assets):
    assets_by_name = {}
    def first(record, keys):
        return next((str(record[k]).strip() for k in keys if k in record and pd.notna(record[k]) and str(record[k]).strip()), '')
    for record in assets.to_dict('records'):
        name = first(record, ('cfb_name', 'team', 'school', 'Team', 'School'))
        assets_by_name[name] = (first(record, ('Logo', 'logo', 'logo_url', 'Logo_URL')),
                                first(record, ('DarkLogo', 'dark_logo', 'Logo_Dark')))
    result = rows.copy()
    result['logo'] = result.team.map(lambda t: (assets_by_name.get(t, ('', ''))[0] or assets_by_name.get(t, ('', ''))[1]))
    result['logoFallback'] = result.team.map(lambda t: assets_by_name.get(t, ('', ''))[1])
    result['conference'] = result['conference'].fillna('Unknown').replace('', 'Unknown')
    return result


def week_options(rows):
    pairs = {(str(r.season_type), int(r.week)) for r in rows.itertuples() if pd.notna(r.week)}
    return sorted(pairs, key=lambda p: (p[0] == 'postseason', p[1]))


def week_label(pair):
    return f"{'Postseason' if pair[0] == 'postseason' else 'Regular season'} · Week {pair[1]}"


def week_scope(weeks):
    """Compact exact selections; a missing week is never implied by a range."""
    parts = []
    for phase in ('regular', 'postseason'):
        numbers = sorted({int(week) for kind, week in weeks if kind == phase})
        ranges = []
        for number in numbers:
            if ranges and number == ranges[-1][-1] + 1:
                ranges[-1].append(number)
            else:
                ranges.append([number])
        if ranges:
            label = 'Regular season' if phase == 'regular' else 'Postseason'
            parts.append(label + ' weeks ' + ', '.join(str(r[0]) if len(r) == 1 else f'{r[0]}–{r[-1]}' for r in ranges))
    return '; '.join(parts)


def load_season_week_scope(season):
    """Available game-stat coverage; season aggregates do not store a cutoff."""
    from utils.db import read_df
    rows = read_df("""SELECT DISTINCT LOWER(COALESCE(g.seasontype, 'regular')) AS season_type,
        g.week FROM public.team_advanced_game_stats gs
        JOIN public.game_data g ON g.id = gs.game_id AND g.season = gs.season
        WHERE gs.season = :season AND g.completed IS TRUE AND g.week IS NOT NULL""",
        {'season': int(season)})
    return week_scope(week_options(rows)) if not rows.empty else ''


def prepare_points(rows, x, y, metrics, conferences, weeks=None, average=False):
    if x not in metrics or y not in metrics:
        raise ValueError('Choose metrics available in the selected table.')
    selected = rows.loc[rows.conference.isin(conferences)].copy()
    if weeks is not None:
        wanted = set(weeks)
        selected = selected.loc[[pd.notna(r.week) and (str(r.season_type), int(r.week)) in wanted for r in selected.itertuples()]].copy()
    for target, column in [('x', x), ('y', y)]:
        selected[target] = pd.to_numeric(selected[column], errors='coerce').replace([np.inf, -np.inf], np.nan)
    valid = selected.dropna(subset=['x', 'y']).copy()
    omitted = len(selected) - len(valid)
    if average and not valid.empty:
        valid = valid.groupby('team', as_index=False, sort=True).agg(
            x=('x', 'mean'), y=('y', 'mean'), games=('x', 'size'),
            conference=('conference', 'last'), logo=('logo', 'first'), logoFallback=('logoFallback', 'first'))
    return valid, omitted


def graphic_config(points, *, title, subtitle, scope, x, y, x_label, y_label, reverse_x=False, reverse_y=False, logo_size=56, layout_key=""):
    records = []
    for row in points.to_dict('records'):
        detail = f"{row['games']} contributing games" if 'games' in row else (
            f"vs {row.get('opponent', '')} · {week_label((row['season_type'], int(row['week'])))}" if 'week' in row else 'Season statistics')
        records.append(dict(name=str(row['team']), conference=str(row['conference']), detail=detail,
                            x=float(row['x']), y=float(row['y']), logo=row['logo'], logoFallback=row['logoFallback']))
    return dict(title=title, subtitle=subtitle, scope=scope, points=records, logoSize=logo_size,
                layoutKey=hashlib.sha256(layout_key.encode()).hexdigest()[:20],
                x=dict(label=x_label, rate=is_rate(x), reverse=reverse_x),
                y=dict(label=y_label, rate=is_rate(y), reverse=reverse_y))


def render_graphic(config):
    from utils.conquest_slides import embed_conquest_logos
    # Copy before embedding so callers retain their original configuration.
    config = json.loads(json.dumps(config, allow_nan=False))
    embed_conquest_logos(config['points'])
    from PIL import Image
    asset = Path(__file__).resolve().parents[1] / 'assets' / 'logo_color.PNG'
    config['brandLogo'] = 'data:image/png;base64,' + base64.b64encode(asset.read_bytes()).decode('ascii')
    with Image.open(asset) as image:
        config['brandBounds'] = list(image.getbbox() or (0, 0, image.width, image.height))
    encoded = json.dumps(config, allow_nan=False).replace('<', '\\u003c')
    return Path(__file__).with_name('scatterplot.html').read_text().replace('__SCATTER_CONFIG__', encoded)

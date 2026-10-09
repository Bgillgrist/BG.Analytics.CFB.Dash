"""Create branded logo scatterplots from the advanced stats tables."""
import streamlit as st
import streamlit.components.v1 as components
from utils import scatterplot as sp

# Streamlit marks the previous component stale as a new rerun starts.
# Hide it during that interval to prevent mouse or keyboard copying old settings.
st.markdown('<style>[data-stale="true"] iframe {visibility:hidden;pointer-events:none}</style>', unsafe_allow_html=True)
st.title('Scatterplot Creator')
st.caption('Compare advanced statistics with team logos, then copy a full-resolution graphic for your post.')
source = st.radio('Data source', list(sp.TABLES), horizontal=True)
try:
    metrics, seasons = sp.load_catalog(source)
except Exception:
    st.error('Advanced statistics could not be loaded. Please try again.')
    st.stop()
if not metrics or not seasons:
    st.info('No advanced statistics are available for this source.')
    st.stop()
season = st.selectbox('Season', seasons, key=f'scatter_season_{source}')
try:
    rows = sp.load_rows(source, season)
except Exception:
    st.error('Statistics or team logos could not be loaded. Please try again.')
    st.stop()
if rows.empty:
    st.info('No statistics are available for this season.')
    st.stop()
context = f'{source}_{season}'
weeks, average = None, False
if source == 'Game stats':
    options = sp.week_options(rows)
    weeks = st.multiselect('Weeks', options, default=options[-1:], format_func=sp.week_label, key=f'scatter_weeks_{context}')
    average = st.radio('Points represent', ['Individual team-games', 'Team averages'], horizontal=True) == 'Team averages'
    st.caption('Completed FBS-versus-FBS games only. Team averages weight each game equally, using games with both selected metrics available.')
else:
    st.caption('Season statistics are used as stored; they are not recalculated using the game-mode FBS-opponent restriction.')
    try:
        suggested_weeks = sp.load_season_week_scope(season)
    except Exception:
        suggested_weeks = ''
    season_weeks = st.text_input('Weeks included (season label)', suggested_weeks, key=f'scatter_coverage_{season}', max_chars=180)
    st.caption('Suggested from available completed game statistics. Season totals do not store a week cutoff; adjust this label if their coverage differs. This changes the label, not the data.')
conferences = sorted(rows.conference.unique())
selected = st.multiselect('Conferences', conferences, default=conferences, key=f'scatter_conferences_{context}')
left, right = st.columns(2)
with left:
    x = st.selectbox('X metric', metrics, index=metrics.index('offense_ppa') if 'offense_ppa' in metrics else 0,
                     format_func=lambda m: f'{sp.metric_label(m)} ({m})', key=f'scatter_x_{source}')
    reverse_x = st.radio('X direction (left → right)', ['Low to high', 'High to low'], horizontal=True) == 'High to low'
with right:
    y = st.selectbox('Y metric', metrics, index=metrics.index('defense_ppa') if 'defense_ppa' in metrics else min(1, len(metrics)-1),
                     format_func=lambda m: f'{sp.metric_label(m)} ({m})', key=f'scatter_y_{source}')
    reverse_y = st.radio('Y direction (bottom → top)', ['Low to high', 'High to low'], horizontal=True) == 'High to low'
with st.expander('Presentation'):
    title = st.text_input('Chart title', 'College Football · Advanced Stats', max_chars=120)
    x_label = st.text_input('X axis label', sp.metric_label(x), key=f'scatter_xlabel_{x}', max_chars=120)
    y_label = st.text_input('Y axis label', sp.metric_label(y), key=f'scatter_ylabel_{y}', max_chars=120)
    logo_size = st.slider('Logo size', 24, 100, 56, step=4)
points, omitted = sp.prepare_points(rows, x, y, metrics, selected, weeks, average)
if omitted:
    st.caption(f'{omitted} row(s) omitted because one or both selected metrics are missing or nonfinite.')
if points.empty:
    st.info('No points match these selections. Choose conferences and weeks with both metrics available.')
    st.stop()
mode = 'Season statistics' if weeks is None else 'Team averages · equal weight per game' if average else 'Individual team-game performances'
scope = 'All conferences' if len(selected) == len(conferences) else ', '.join(selected)
coverage = sp.week_scope(weeks) if weeks is not None else season_weeks.strip() or 'Week coverage unavailable'
if average:
    scope += ' · Equal-weight game averages'
st.caption(f'{len(points)} points · {mode}. Dashed lines mark the median of the plotted X and Y values.')
config = sp.graphic_config(points, title=title, subtitle=f'{season} · {coverage}', scope=scope,
                           x=x, y=y, x_label=x_label, y_label=y_label, reverse_x=reverse_x, reverse_y=reverse_y, logo_size=logo_size,
                           layout_key=f'{context}:{x}:{y}:{reverse_x}:{reverse_y}:{average}')
# Clear the previous frame before logo retrieval so it cannot copy stale settings.
preview = st.empty()
with preview.container():
    with st.spinner('Preparing your graphic…'):
        markup = sp.render_graphic(config)
    components.html(markup, height=1160, scrolling=True)
with st.expander('Plotted data'):
    columns = ['team', 'conference', 'x', 'y'] + ([c for c in ('opponent', 'season_type', 'week') if c in points] if not average else ['games'])
    st.dataframe(points[columns].rename(columns={'team': 'Team', 'conference': 'Conference', 'x': f'X: {sp.metric_label(x)}',
                                                'y': f'Y: {sp.metric_label(y)}', 'games': 'Contributing games'}), hide_index=True, use_container_width=True)

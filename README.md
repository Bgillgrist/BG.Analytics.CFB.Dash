# BG.Analytics.CFB.Dash
BG.Analytics CFB Dashboard

The **Conquest Map** has a **Show slide images** button below the map. After
positioning the logos, use it to display three matching 2160 × 2700 portrait PNG
slides (4:5) for Instagram, with the season and week in a large header on every
slide and a rules panel on the first. Use each slide's **Copy** button, or
right-click each image and choose **Copy Image**, then paste into your post.
The first two slides are cut from one continuous map; rules follow the selected map scope.
**Slide 3** summarizes the top ten schools by counties owned and land area owned,
side by side with school logos and totals. It follows the current map week and
scope, even in Conference mode. Area uses Census land-only square miles (including
Alaska and Hawaii), matched to the map's county boundaries. Use **Copy slide 3**
to finish the carousel. Rankings tests: `node --test tests/test_conquest_rankings.cjs`.
Moving or duplicating a logo prompts you to update the slides before copying.
No download or export is needed.

**Team Rankings → Rankings Analysis** compares the selected poll with the selected
ratings blend using full rank gaps; unranked poll teams show minimum gaps. It also
shows Top 25 agreement, bubble teams, and movement. Ratings movement uses a chosen
comparison date, resolves missing dates to the latest earlier snapshot, and applies
the same TeamRankings blend to both snapshots using their respective historical
data. Poll movement uses the previous available week. Posting PNG/ZIP exports have
been replaced by this analysis.

The **League Wide → Predictions** page reads successful manual/nightly season
snapshots and provides sortable team projections, conference races, and comparisons
to a calendar date. If that day has no snapshot, the latest available snapshot on
or before it is used, with the actual date displayed. It uses the same
`NEON_DATABASE_URL` configuration as the other pages.

Run prediction tests with `python -m pytest tests -q` after installing the dashboard
requirements and pytest. Data tests run without Streamlit; the Streamlit interaction
test module is skipped when Streamlit or Plotly is unavailable. Run the dashboard
with `streamlit run app/app.py` to check the page at desktop and mobile widths.

**League Wide → Weekly Performances** ranks completed FBS-vs-FBS team-game
performances by raw overall/passing/rushing PPA or a BG-adjusted index. The index
adds 0.25 times standardized pregame opponent BG Power Rating to standardized
weekly performance (reversing defensive PPA so higher scores are better). It uses
unblended, successful manual/nightly snapshots completed strictly before kickoff.
Without a reliable kickoff or saved pregame rating, performances remain available
in raw rankings. Conference/team filters do not recalculate weekly ranks.

Run all data and optional Streamlit interaction tests with `python -m pytest tests -q`.
Weekly query and scoring tests are in `tests/test_weekly_performances.py`; its page
interaction tests require Streamlit. No database writes or export controls are added.

**Betting → Best Bets** classifies upcoming FBS-vs-FBS moneylines and spreads
using four models: spread-aware and TeamRankings without spread input, each with
and without pregame advanced statistics. Run analysis explicitly retrains/tests
all four models; Refresh odds reuses their saved artifacts. Filters and page loads
never train, refresh odds, or write to the database.

Set `CFBD_API_KEY` alongside `NEON_DATABASE_URL` in Streamlit secrets to enable
these controls. The first explicit run creates additive `public.betting_*` tables.
Saved results can be viewed without the API key. No Betting jobs are scheduled.

**Betting → Betting History** grades the last successful snapshot completed before
each game's kickoff, once per game/model/market, at its saved line. Earlier
classifications remain in the timeline. Spread hit rate excludes pushes and uses
a 50% comparison baseline; spread ROI is unavailable. Moneyline paper returns
use the saved offered price. Historical research for 2023–2025 is shown separately
because old CFBD odds have no verified collection timestamps.

The shared engine is distributed in
`vendor/bga_cfb_betting-0.1.0-py3-none-any.whl`, built from the `cfb_betting`
package in the analytics repository. Install requirements from this repository's
root. Hosting does not require an adjacent analytics checkout.
Engine documentation and CLI backtest instructions are in that repository's
`docs/betting_handoff.md`. The existing nightly game refresh records score
corrections after the betting schema exists.

Betting interaction tests are in `tests/test_betting_pages.py`; engine, cutoff,
quote, artifact, and settlement tests live with the shared package. On macOS,
XGBoost requires an available OpenMP runtime (libomp).

# BG.Analytics.CFB.Dash
BG.Analytics CFB Dashboard

**League Wide → Head to Head Analysis** builds results-only national rankings,
explores shortest win chains in both directions, and searches two-to-sixteen-team
Circles of Chaos. Select a season and cumulative **Through week**, then explicitly
**Calculate rankings**. Only completed FBS-vs-FBS games with valid unequal scores
are evidence; teams without an eligible result remain unranked. Conference/team
filters only filter the table. Historical checkpoints use currently stored corrected
results, not historical database snapshots. Invalid completed records and conflicting
duplicate IDs are excluded and counted; identical duplicate games count once.

The optimizer first minimizes direct-result exceptions (a winner below its loser),
then reversed pairs at shortest distance two. Repeated meetings count separately
at distance one; each indirect ordered pair counts once at distance two. Chains of
three or more games remain in the explorer but add no separate ranking objective.
Following all direct results can still imply a longer chain's ordering.
Later priorities cannot worsen earlier proven optima. Scores,
polls, rating models, and victory margins do not break ties. After fixing the result
priorities, fill positions in order by record (fewer FBS losses, then more FBS wins),
then résumé (opponents' FBS winning percentage). FBS-undefeated teams are always
ahead of teams with FBS losses, even in provisional solutions; this cannot worsen
result objectives because undefeated teams have no incoming win paths. Other
record preferences yield to direct and two-game priorities. Winning percentage is
displayed only as context. Opponent records exclude games against the
evaluated team, pool remaining wins/losses, and count repeated opponents per matchup;
no remaining games gives a zero schedule tiebreak value. Alphabetical order is the
last fallback for equal résumés. Acyclic graphs pick the best available résumé at
each topological step; circular graphs use OR-Tools CP-SAT with the same positional
preference after fixing every proven result objective. Install the updated
`requirements.txt` to enable circular-result optimization.

Ranking calculations have a shared 30-second budget and are cached by normalized
results, cutoff, and algorithm version. **Provisional** means best found, not proven
optimal. **All results fit** means zero exceptions, not a unique ranking. The page
identifies multiple valid orders in acyclic graphs and reports separately when the
time budget leaves record/résumé tiebreaks incomplete. Expand calculation details to inspect objective values, proof statuses, and
the first unproven objective's lower bound. Every direct-result exception is listed.
Positions represent one ordering; they need not be unique. Corrected scores clear
cached identities and stale previews after the normal five-minute source refresh.

After all priorities are proven, **Calculate optimal rank ranges** supports up to
five selected teams with a separate shared 30-second budget. Exact endpoints are
the best and worst positions among optimal direct/two-game result orders **before**
record and résumé tiebreaks (including the undefeated rule), so the remaining
flexibility stays visible. Incomplete endpoints are
conservative outer bounds, not proven attainable positions; intermediate positions
and different teams' endpoints need not be jointly attainable.

The chain explorer uses one deterministic shortest path per direction, with the
earliest available meeting witnessing each repeated edge. Paths need not follow
game-date order. **Search longest circles** searches simple cycles longest-first,
with a selectable maximum of 2–16 teams (default 16), optional team filter, and
15/30/60/120-second budget (default 60). Search runs explicitly and returns up to
50 rotation-deduplicated loops. Each team occurs once before the loop closes.
The page distinguishes longest found from longest proven within the chosen size
limit, and reports whether time or the result limit stopped enumeration. Short
examples may be available even if time expires before finding a longer circle.
Two-team circles represent split rematches. **Show Top 25 graphic**, **Show matchup
chain graphics**, and **Show Circle of Chaos graphic** produce copyable 2160 × 2700
PNGs with scope/cutoff labels. Long chains paginate without losing games. The Top 25
graphic uses national ranks regardless of table filters; provisional rankings carry
a provisional label. Missing logos fall back to initials and readable team names.
Circles with more than six teams use a numbered overview plus paginated game
evidence, retaining all links including the final win that closes the loop.

Focused checks: `python -m pytest tests/test_head_to_head*.py -q` and
`node --test tests/test_head_to_head_graphics.cjs`. Optimizer tests compare small
graphs and rank ranges against all permutations and require OR-Tools. Page tests
use synthetic results without database access. No database writes or jobs are added.

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

Below the Conquest Map scope, territory mode, and week controls, expand
**Alternate team colors** or **Alternate team logos** to choose each independently.
UCLA and Mississippi State start with alternate colors; teams with dark/alternate
logos start selected to preserve the existing map appearance. Removing a team
restores its primary asset. Missing alternate assets fall back to the available
version. Selections persist during the session across map-rule and season changes;
editing appearance retains the selected scope, mode, and week. Team colors affect
Team territory mode, and logo choices also carry into the team rankings slide.

**Team Rankings → Rankings Analysis** compares the selected poll with the selected
ratings blend using full rank gaps; unranked poll teams show minimum gaps. It also
shows Top 25 agreement, bubble teams, and movement. Ratings movement uses a chosen
comparison date, resolves missing dates to the latest earlier snapshot, and applies
the same TeamRankings blend to both snapshots using their respective historical
data. Poll movement uses the previous available week. Posting PNG/ZIP exports have
been replaced by this analysis.

The **Biggest risers / Biggest fallers** sections in both the Poll and Ratings
tabs include **Show Instagram graphic**. It creates a 2160 × 2700 PNG (4:5) with
the current comparison's top five risers and fallers, prominent team logos, and
old/new ranks. Ratings include old/new rating values and the selected blend.
Use **Copy graphic** or right-click **Copy Image**, as on the conquest map; no
download is needed. Changing comparison controls clears the preview so the next
graphic uses the new selection. Logos load only when the button is pressed.

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

The **Season & game grades** section lists each team with six numeric grades:
season offense/defense, selected-week game offense/defense, and season/game
overall (the percentile of offensive PPA minus defensive PPA allowed). **Raw PPA**
uses one FBS percentile scale. **BG-adjusted** applies to all six grades and uses
separate P4 and G5 percentile scales. P4 includes SEC, ACC, Big Ten, Big 12, and
Notre Dame; G5 denotes all other FBS teams, including Pac-12 and other independents,
using conferences recorded for the selected season. These are within-group grades,
not directly comparable across the two groups.

Adjusted game scores add 0.25 times pregame opponent strength z-score to performance
z-score, standardized against the entire season's eligible completed FBS-vs-FBS
team-games (regular season and postseason). Season scores standardize current
stored FBS season PPA, then add 0.25 times the equally weighted mean opponent
strength across completed FBS matchups. Defense reverses PPA; overall uses net PPA
and receives the opponent bonus once. Final scores use the existing percentile
tie convention within each peer group, requiring at least two valid observations.
The leaderboards above continue to standardize performance within the selected week.

Adjusted season grades require pregame ratings for every completed FBS matchup,
including schedule games with missing advanced stats. The table shows season/week
rated-game coverage and availability; missing ratings never fall back silently to
raw grades. Switch to Raw PPA to see unadjusted grades. Stored season totals keep
their source coverage; the schedule bonus covers FBS opponents only. Selecting an
earlier week does not rewind season totals. Bye teams retain season grades, missing
grades stay blank, and multiple games in a week are graded individually before
averaging per team. Conference/team filters never change the grade populations.
Standalone report cards are unchanged.

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


## Scatterplot Creator

Open **League Wide → Scatterplot Creator** to compare any two numeric metrics
from the advanced season or game stats tables. Choose a season, conferences,
X/Y metrics, and each axis's direction. Presentation controls customize the
chart title, axis labels, and logo size. The source column name appears beside
each readable metric label.

Season mode plots stored season statistics as-is. Game mode includes only
completed FBS-versus-FBS games and allows multiple regular-season/postseason
weeks. Choose individual team-game points or equal-weight team averages.
Averages use only games where **both** selected metrics are finite; totals are
also averaged per game, and contributing game counts appear in the data table.
Season-table values are not recalculated with the game-mode opponent restriction.
Conference filters apply to the plotted team, not its opponent. Clearing the
conference or week selection produces an empty chart state.

The square graphic uses exact point positions, BG.Analytics branding, and team
logos (initials when unavailable). Hover shows all overlapping points; expand
**Plotted data** for values and game context. Use **Copy graphic** for the
2160 × 2160 PNG, or right-click the preview and choose **Copy Image** if browser
clipboard permissions block the button. Changes regenerate the preview and
export together. Missing/nonfinite metric pairs are omitted and counted.


Scatterplot graphics include light dashed lines at the median X and median Y of
the plotted points (including the team averages when that mode is selected).
Open **Quadrant labels (optional)** above the preview to enter up to four custom
labels. Drag a label on the image to move it, or adjust its horizontal/vertical
percentages; blank labels are omitted. Copying or right-clicking the image includes
the latest label positions. Labels persist for the same season/metric/orientation
combination during the browser session; **Reset label positions** restores their
initial quadrant centers while keeping the text.

The graphic subtitle shows the year and weeks, and the footer uses the saved
BG.Analytics PNG. Game-mode weeks reflect the selection. In season mode,
**Weeks included (season label)** is suggested from available completed game
statistics and can be edited: the season aggregate table has no stored cutoff,
so this label does not guarantee aggregate ingestion coverage or filter the data.

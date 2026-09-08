# BG.Analytics.CFB.Dash
BG.Analytics CFB Dashboard

The **League Wide → Predictions** page reads successful manual/nightly season
snapshots and provides sortable team projections, conference races, and day/week
comparisons. It uses the same `NEON_DATABASE_URL` configuration as the other pages.

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

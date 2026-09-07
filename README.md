# BG.Analytics.CFB.Dash
BG.Analytics CFB Dashboard

The **League Wide → Predictions** page reads successful manual/nightly season
snapshots and provides sortable team projections, conference races, and day/week
comparisons. It uses the same `NEON_DATABASE_URL` configuration as the other pages.

Run prediction tests with `python -m pytest tests -q` after installing the dashboard
requirements and pytest. Data tests run without Streamlit; the Streamlit interaction
test module is skipped when Streamlit or Plotly is unavailable. Run the dashboard
with `streamlit run app/app.py` to check the page at desktop and mobile widths.

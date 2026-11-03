"""Shared Streamlit presentation for predictive diagnostics."""

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from utils.predictive_performance import add_errors, calibration, graded, metrics, trends

NAVY = "#0C2C56"
LABELS = {"winner_accuracy": "Winner accuracy", "brier_score": "Brier score", "log_loss": "Log loss", "roc_auc": "ROC AUC",
          "margin_mae": "Margin MAE", "margin_rmse": "Margin RMSE", "margin_bias": "Margin bias",
          "total_mae": "Total MAE", "total_rmse": "Total RMSE", "total_bias": "Total bias"}


def summary(frame, target=None):
    table = metrics(frame).set_index("metric")
    groups = {"win": ["winner_accuracy", "brier_score", "log_loss", "roc_auc"],
              "margin": ["margin_mae", "margin_rmse", "margin_bias"], "total": ["total_mae", "total_rmse", "total_bias"]}
    for kind, names in groups.items():
        if target and target != kind:
            continue
        for column, name in zip(st.columns(len(names)), names):
            value, count = table.loc[name, ["value", "games"]]
            text = "—" if not np.isfinite(value) else (f"{value:.1%}" if name == "winner_accuracy" else f"{value:.3f}")
            column.metric(LABELS[name], text)
            column.caption(f"{int(count):,} games")
    st.caption("Lower Brier score, log loss, MAE, and RMSE are better. Bias is predicted minus actual; zero is ideal. "
               "Winner accuracy excludes exact 50% forecasts. ROC AUC requires both home wins and home losses.")


def probability_charts(frame):
    table = calibration(frame)
    if table.empty:
        st.info("No valid win probabilities and final results are available in this view.")
        return
    figure = go.Figure(go.Scatter(x=table.mean_probability, y=table.observed_win_rate, mode="lines+markers",
        name="Observed", marker_color=NAVY, customdata=table[["games"]],
        error_y=dict(type="data", symmetric=False, array=table.rate_upper-table.observed_win_rate,
                     arrayminus=table.observed_win_rate-table.rate_lower),
        hovertemplate="Predicted %{x:.1%}<br>Observed %{y:.1%}<br>%{customdata[0]} games<extra></extra>"))
    figure.add_shape(type="line", x0=0, x1=1, y0=0, y1=1, line=dict(color="#94a3b8", dash="dash"))
    figure.update_layout(xaxis_title="Mean predicted home win probability", yaxis_title="Observed home win rate")
    figure.update_xaxes(range=[0, 1], tickformat=".0%")
    figure.update_yaxes(range=[0, 1], tickformat=".0%")
    st.plotly_chart(figure, width="stretch")
    st.caption("A calibrated model follows the diagonal. Bars are 95% Wilson intervals; games are correlated, so intervals are descriptive. "
               "Each bin covers 10 percentage points; probabilities of 100% belong in the final bin.")
    st.dataframe(table, hide_index=True, width="stretch")
    sample = add_errors(graded(frame))
    st.plotly_chart(px.histogram(sample.dropna(subset=["home_win_probability"]), x="home_win_probability", nbins=20,
        color_discrete_sequence=[NAVY], labels={"home_win_probability": "Home win probability"}), width="stretch")


def error_charts(frame, target=None):
    sample = add_errors(graded(frame))
    for kind, actual, prediction in [("margin", "actual_home_margin", "predicted_home_margin"),
                                      ("total", "actual_total", "predicted_total")]:
        if target and target != kind:
            continue
        st.subheader("Home scoring margin" if kind == "margin" else "Combined points")
        valid = sample.dropna(subset=[actual, prediction])
        if valid.empty:
            st.info("No valid predictions and final results for this target.")
            continue
        first, second = st.columns(2)
        figure = px.scatter(valid, x=prediction, y=actual, hover_data=["home_team", "away_team", "game_id"],
                            color_discrete_sequence=[NAVY], labels={prediction: "Predicted points", actual: "Actual points"})
        low, high = min(valid[actual].min(), valid[prediction].min()), max(valid[actual].max(), valid[prediction].max())
        figure.add_shape(type="line", x0=low, x1=high, y0=low, y1=high, line=dict(color="#94a3b8", dash="dash"))
        first.plotly_chart(figure, width="stretch", key=f"diagnostic_{kind}_scatter")
        second.plotly_chart(px.histogram(valid, x=f"{kind}_error", nbins=25, color_discrete_sequence=[NAVY],
            labels={f"{kind}_error": "Prediction error (predicted − actual)"}), width="stretch", key=f"diagnostic_{kind}_histogram")
        st.caption("Largest misses by absolute error. Positive margin means the home team outscores the away team.")
        worst = valid.assign(absolute_error=valid[f"{kind}_error"].abs()).sort_values("absolute_error", ascending=False).head(15)
        st.dataframe(worst[["game_id", "home_team", "away_team", prediction, actual, f"{kind}_error"]], hide_index=True, width="stretch")


def trend_chart(frame, key, target=None):
    weekly, cumulative = trends(frame)
    if weekly.empty:
        st.info("No graded games are available for trend charts.")
        return
    choices = [name for name in LABELS if target is None or (target == "win" and name in ("winner_accuracy", "brier_score", "log_loss", "roc_auc"))
               or name.startswith(f"{target}_")]
    first, second = st.columns(2)
    name = first.selectbox("Trend metric", choices, format_func=LABELS.get, key=f"{key}_metric")
    mode = second.radio("Trend window", ["Weekly", "Cumulative"], horizontal=True, key=f"{key}_window")
    data = weekly if mode == "Weekly" else cumulative
    figure = px.line(data, x="period", y=name, markers=True, color_discrete_sequence=[NAVY],
                     labels={"period": "Season and week", name: LABELS[name]}, hover_data=["games"])
    if name == "winner_accuracy":
        figure.update_yaxes(tickformat=".0%", range=[0, 1])
    st.plotly_chart(figure, width="stretch")
    st.caption("Weeks follow first kickoff order, including postseason. Cumulative metrics pool game-level predictions across the selected seasons.")

"""Pregame feature and real small-model chronological evaluation tests."""

from dataclasses import replace
from io import BytesIO
from pathlib import Path
import sys
from zipfile import ZipFile

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from utils import model_builder as builder
from utils.predictive_performance import csv_bytes, zip_csvs
from test_predictive_performance import game


def inputs(games, stats=None, ratings=None, talent=None, odds=None):
    return dict(games=pd.DataFrame(games),
        stats=pd.DataFrame(stats or [], columns=["game_id", "season", "team", "offense_newmetric"]),
        ratings=pd.DataFrame(ratings or [], columns=["season", "team", "pull_date", "rating"]),
        talent=pd.DataFrame(talent or [], columns=["season", "team", "talent"]),
        odds=pd.DataFrame(odds or [], columns=["game_id", "avg_spread", "avg_over_under"]))


def test_rolling_features_exclude_same_day_and_future_and_respect_prior_season():
    games = [game("prior", season=2024, kickoff="2024-11-01T16:00Z"),
             game("early", kickoff="2025-09-01T16:00Z"), game("same", kickoff="2025-09-06T12:00Z"),
             game("target"), game("future", kickoff="2025-09-13T16:00Z", completed=False)]
    stats = [dict(game_id=g["game_id"], season=g["season"], team="Alpha", offense_newmetric=value)
             for g, value in zip(games, [2, 4, 100, 200, 999])]
    ratings = [dict(season=2025, team="Alpha", pull_date=day, rating=value)
               for day, value in [("2025-09-01", 8), ("2025-09-06", 99), ("2025-09-10", 999)]]
    dataset = builder.build_dataset(inputs(games, stats, ratings), ["offense_newmetric"], as_of="2025-09-06T20:00Z").set_index("game_id")
    target = dataset.loc["target"]
    assert target.home_season_offense_newmetric == 4
    assert target.home_last5_offense_newmetric_n == 1
    assert target.home_prior_offense_newmetric == 2
    assert target.home_teamrankings_rating == 8
    assert dataset.loc["future", "home_season_offense_newmetric"] == 4
    assert dataset.loc["future", "home_teamrankings_rating"] == 8
    assert pd.isna(dataset.loc["early", "home_teamrankings_rating"])


def test_last5_is_current_season_and_counts_nonmissing_values():
    games = [game(str(i), kickoff=f"2025-09-{i:02}T16:00Z") for i in range(1, 8)]
    stats = [dict(game_id=str(i), season=2025, team="Alpha", offense_newmetric=float(i) if i != 5 else None) for i in range(1, 7)]
    row = builder.build_dataset(inputs(games, stats), ["offense_newmetric"], as_of="2025-10-01").iloc[-1]
    assert row.home_last5_games == 5
    assert row.home_last5_offense_newmetric_n == 4
    assert row.home_last5_offense_newmetric == pytest.approx((2+3+4+6)/4)


def test_duplicate_stats_and_conflicting_rating_or_talent_are_rejected():
    source = inputs([game()], stats=[dict(game_id="001", season=2025, team="Alpha", offense_newmetric=1)]*2)
    with pytest.raises(ValueError, match="Duplicate team-game"):
        builder.build_dataset(source, ["offense_newmetric"])
    for kind, values, message in [
        ("ratings", [dict(season=2025, team="Alpha", pull_date="2025-09-01", rating=i) for i in [1, 2]], "rating rows"),
        ("talent", [dict(season=2025, team="Alpha", talent=i) for i in [1, 2]], "talent rows")]:
        source = inputs([game()], **{kind: values})
        with pytest.raises(ValueError, match=message):
            builder.build_dataset(source)


@pytest.fixture
def dataset():
    rows = []
    for season in [2022, 2023, 2024]:
        for i in range(40):
            home = 10 + i % 20
            away = 12 + (i*7) % 18
            if home == away:
                home += 1
            rows.append(game(f"{season}-{i:03}", season=season, week=i//4+1,
                kickoff=pd.Timestamp(f"{season}-09-01T16:00Z") + pd.Timedelta(days=i), homepoints=home, awaypoints=away))
    frame = builder.prepare_games(pd.DataFrame(rows))
    frame["signal"] = np.arange(len(frame)) % 11
    frame.loc[frame.index % 7 == 0, "signal"] = np.nan
    frame["missing"] = np.nan
    frame["neutral_site"] = frame.neutralsite.astype(float)
    frame.attrs["as_of"] = "2025-01-01T12:00:00Z"
    return frame


def config(**changes):
    return replace(builder.ExperimentConfig("Test", "win", "Linear", ("signal", "missing"), 2022, (2023, 2024)), **changes)


@pytest.mark.parametrize("target", ["win", "margin", "total"])
def test_real_linear_models_use_expanding_folds_and_training_only_preprocessing(dataset, target):
    result = builder.run_experiment(dataset, config(target=target))
    assert len(result["predictions"]) == 80
    for season, membership in result["folds"].groupby("fold"):
        joined = membership.merge(dataset[["game_id", "season"]], on="game_id")
        assert joined.loc[joined.role.eq("train"), "season"].lt(int(season)).all()
        assert joined.loc[joined.role.eq("evaluation"), "season"].eq(int(season)).all()
    assert not result["missingness"].loc[result["missingness"].feature.eq("missing"), "used"].any()
    train, test = dataset.loc[dataset.season.eq(2022)], dataset.loc[dataset.season.eq(2023)]
    model, used = builder.fit_model(train, config(target=target))
    assert used == ["signal"]
    assert model.named_steps["impute"].statistics_[0] == train.signal.median()
    modified = test.copy()
    modified["signal"] = 1e6
    builder.predict(model, modified, used, target)
    assert model.named_steps["impute"].statistics_[0] == train.signal.median()
    expected = train[builder.TARGET_COLUMNS[target]].mean()
    assert result["predictions"].loc[result["predictions"].fold.eq("2023"), "training_mean_baseline"].eq(expected).all()


@pytest.mark.parametrize("family", ["Random forest", "XGBoost"])
@pytest.mark.parametrize("target", ["win", "margin", "total"])
def test_real_tree_models_and_heldout_importance(dataset, family, target):
    result = builder.run_experiment(dataset, config(target=target, family=family, evaluation_seasons=(2023,), params=dict(trees=5, depth=2)))
    assert len(result["predictions"]) == 40
    assert result["importance"].method.eq("held_out_permutation_score_decrease").all()
    assert result["predictions"][builder.OUTPUT_COLUMNS[target]].notna().all()
    if target == "win":
        assert result["predictions"].home_win_probability.between(0, 1).all()


def test_reproducibility_and_cache_identity_include_features_data_and_cutoff_day(dataset):
    a = builder.run_experiment(dataset, config())
    b = builder.run_experiment(dataset.sample(frac=1, random_state=10), config())
    assert a["experiment_id"] == b["experiment_id"]
    np.testing.assert_allclose(a["predictions"].home_win_probability, b["predictions"].home_win_probability)
    changed = dataset.copy()
    changed.loc[0, "signal"] = 900
    assert builder.experiment_key(changed, config()) != a["experiment_id"]
    assert builder.experiment_key(dataset, config(features=("signal",))) != a["experiment_id"]
    changed = dataset.copy()
    changed.attrs["as_of"] = "2025-01-02T12:00Z"
    assert builder.experiment_key(changed, config()) != a["experiment_id"]


def test_insufficient_data_single_class_empty_features_and_allmissing_fail(dataset):
    for frame, settings, message in [
        (dataset.iloc[:10], config(), "No eligible completed games"),
        (dataset, config(features=("missing",)), "No selected feature"),
        (dataset, config(features=()), "at least one feature"),
        (dataset, config(evaluation_seasons=(2022,)), "must follow"),
        (dataset.assign(actual_home_win=1.), config(), "two distinct")]:
        with pytest.raises(ValueError, match=message):
            builder.run_experiment(frame, settings)


def test_upcoming_fit_has_separate_cutoff_data_and_does_not_change_holdouts(dataset):
    result = builder.run_experiment(dataset, config())
    future_games = builder.prepare_games(pd.DataFrame([
        game("future", season=2025, completed=False, kickoff="2025-09-10T16:00Z", homepoints=None, awaypoints=None),
        game("unknown", season=2025, completed=False, kickoff="2025-09-10T16:00Z", starttimetbd=True),
        game("cancelled", season=2025, completed=False, kickoff="2025-09-10T16:00Z", cancelled=True),
        game("same_day", season=2025, kickoff="2025-09-01T12:00Z"),
    ]))
    future_games["signal"] = 5.
    future_games["missing"] = np.nan
    combined = pd.concat([dataset, future_games], ignore_index=True)
    combined.attrs["as_of"] = "2025-09-01T20:00:00Z"
    updated = builder.fit_upcoming(result, combined, 2025)
    assert updated["upcoming_predictions"].game_id.tolist() == ["future"]
    assert updated["upcoming_fit"]["training_games"] == 120
    pd.testing.assert_frame_equal(updated["predictions"], result["predictions"])
    assert result["upcoming_predictions"].empty
    assert updated["upcoming_predictions"].actual_home_win.isna().all()


def test_comparison_uses_common_heldout_games_and_exports_are_r_readable(dataset):
    a = builder.run_experiment(dataset, config())
    b = builder.run_experiment(dataset, config(name="Other", evaluation_seasons=(2024,)))
    table = builder.comparison([a, b], "win")
    assert set(table.common_games) == {40}
    assert sorted(table.evaluation_games) == [40, 80]
    frames = builder.export_frames(a)
    assert {"dataset", "folds", "predictions", "metrics", "importance", "settings", "feature_dictionary"} <= set(frames)
    parsed = pd.read_csv(BytesIO(csv_bytes(frames["predictions"])), dtype={"game_id": str})
    assert parsed.game_id.iloc[0] == "2023-000"
    assert parsed.home_win_probability.between(0, 1).all()
    assert frames["feature_dictionary"].feature.eq("actual_home_margin").any()
    with ZipFile(BytesIO(zip_csvs(frames))) as archive:
        assert "settings.csv" in archive.namelist()
    c = dict(b, predictions=b["predictions"].assign(game_id=lambda frame: "other-" + frame.game_id))
    assert builder.comparison([a, c], "win").value.isna().all()


def test_optional_market_inputs_are_preserved_and_not_in_base_defaults():
    source = inputs([game()], odds=[dict(game_id="001", avg_spread=-4., avg_over_under=50.)])
    dataset = builder.build_dataset(source)
    assert dataset.iloc[0].avg_spread == -4
    assert "avg_spread" not in builder.feature_catalog().feature.tolist()
    assert "avg_spread" in builder.feature_catalog(market=True).feature.tolist()

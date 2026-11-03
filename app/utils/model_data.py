"""Read-only sources for model research. Queries share the five-minute DB cache."""

import re

import pandas as pd

NUMERIC_TYPES = {"smallint", "integer", "bigint", "numeric", "decimal", "real", "double precision"}
ADMIN = {"id", "game_id", "team_id", "opponent_id", "season", "week", "year", "period"}
FBS = "LOWER(g.homeclassification) = 'fbs' AND LOWER(g.awayclassification) = 'fbs'"


def discover_metrics(metadata):
    return sorted({str(row.column_name) for row in metadata.itertuples()
                   if row.data_type in NUMERIC_TYPES and row.column_name not in ADMIN
                   and not row.column_name.endswith("_id")
                   and re.fullmatch(r"[a-z][a-z0-9_]*", str(row.column_name))})


def load_seasons():
    from utils.db import read_df
    return read_df(f"""SELECT g.season::int AS season, COUNT(*)::int AS games,
        COUNT(*) FILTER (WHERE g.completed IS NOT TRUE AND NOT
            (LOWER(BTRIM(COALESCE(g.notes,''))) ~ '^(game )?cancel(l)?ed([ .:-]|$)'))::int AS unfinished,
        MAX(g.startdate) AS last_kickoff
        FROM public.game_data g WHERE {FBS} AND g.season >= 2015
        GROUP BY g.season ORDER BY g.season DESC""")


def load_games(start_season, end_season):
    from utils.db import read_df
    return read_df(f"""SELECT g.id::text AS game_id, g.season, g.week,
        LOWER(COALESCE(g.seasontype, 'regular')) AS season_type,
        g.startdate AS kickoff, g.starttimetbd, g.completed, g.neutralsite,
        g.hometeam AS home_team, g.awayteam AS away_team,
        g.homeconference AS home_conference, g.awayconference AS away_conference,
        g.homepoints, g.awaypoints,
        (g.completed IS NOT TRUE AND LOWER(BTRIM(COALESCE(g.notes,'')))
            ~ '^(game )?cancel(l)?ed([ .:-]|$)') AS cancelled
        FROM public.game_data g WHERE {FBS} AND g.season BETWEEN :start AND :end
        ORDER BY g.startdate, g.id""", {"start": int(start_season), "end": int(end_season)})


def load_performance(seasons):
    from utils.db import read_df
    games = load_games(min(seasons), max(seasons))
    games = games.loc[games.season.isin(seasons)].copy()
    forecasts = read_df("""SELECT p.gameid::text AS game_id, p.game_prediction_run_id::text AS run_id,
        p.model_version, p.homewinprob AS home_win_probability,
        -p.homespread AS predicted_home_margin, p.totalpred AS predicted_total,
        p.created_at AS prediction_created_at, r.run_type, r.status, r.run_date,
        r.created_at AS run_created_at, r.completed_at AS forecast_completed_at
        FROM public.game_predictions_full p JOIN public.game_prediction_runs r
            ON r.game_prediction_run_id = p.game_prediction_run_id
        WHERE p.season BETWEEN :start AND :end AND r.season = p.season
          AND r.status = 'success' AND r.run_type IN ('manual', 'nightly', 'backfill')
        ORDER BY r.completed_at, p.gameid""", {"start": int(min(seasons)), "end": int(max(seasons))})
    return games, forecasts


def load_metric_catalog():
    from utils.db import read_df
    return discover_metrics(read_df("""SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'team_advanced_game_stats'"""))


def load_builder_inputs(start_season, end_season, metrics, market=False):
    from utils.db import read_df
    games = load_games(start_season - 1, end_season)
    ratings = read_df("""SELECT season, team, pull_date, rating
        FROM public.teamrankings_predictive_ratings WHERE season BETWEEN :start AND :end
        ORDER BY season, team, pull_date""", {"start": int(start_season), "end": int(end_season)})
    talent = read_df("""SELECT year AS season, team, talent FROM public.team_talent_composite
        WHERE year BETWEEN :start AND :end""", {"start": int(start_season), "end": int(end_season)})
    # All identifiers must originate in the metadata allowlist, never free-form SQL.
    allowed = set(load_metric_catalog())
    if not set(metrics) <= allowed:
        raise ValueError("An advanced metric is no longer available. Reload the feature catalog.")
    stats = pd.DataFrame(columns=["game_id", "season", "team", *metrics])
    if metrics:
        columns = ", ".join(f'gs."{column}"' for column in metrics)
        stats = read_df(f"""SELECT gs.game_id::text AS game_id, gs.season, gs.team, {columns}
            FROM public.team_advanced_game_stats gs JOIN public.game_data g
                ON g.id = gs.game_id AND g.season = gs.season
            WHERE g.completed IS TRUE AND {FBS}
              AND gs.team IN (g.hometeam, g.awayteam)
              AND gs.season BETWEEN :start AND :end""",
            {"start": int(start_season - 1), "end": int(end_season)})
    odds = pd.DataFrame(columns=["game_id", "avg_spread", "avg_over_under"])
    if market:
        odds = read_df(f"""SELECT b."Id"::text AS game_id,
            AVG(b."Spread") AS avg_spread, AVG(b."OverUnder") AS avg_over_under
            FROM public.betting_odds b JOIN public.game_data g ON b."Id" = g.id
            WHERE {FBS} AND g.season BETWEEN :start AND :end
              AND LOWER(COALESCE(b."LineProvider",''))
                NOT IN ('','consensus','teamrankings','numberfire','average','vegas')
            GROUP BY b."Id""", {"start": int(start_season), "end": int(end_season)})
    return dict(games=games, ratings=ratings, talent=talent, stats=stats, odds=odds)

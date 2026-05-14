import json
import html as html_lib
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import altair as alt
import plotly.graph_objects as go
from utils.db import read_df


WIN_PROBABILITY_COLUMNS = [
    (0, "probability_0_wins"),
    (1, "probability_1_win"),
    (2, "probability_2_wins"),
    (3, "probability_3_wins"),
    (4, "probability_4_wins"),
    (5, "probability_5_wins"),
    (6, "probability_6_wins"),
    (7, "probability_7_wins"),
    (8, "probability_8_wins"),
    (9, "probability_9_wins"),
    (10, "probability_10_wins"),
    (11, "probability_11_wins"),
    (12, "probability_12_wins"),
    (13, "probability_13_wins"),
]

SEASON_ODDS_COLUMNS = [
    "conference_champion_prob",
    "playoff_prob",
    "national_champion_prob",
]

RANKING_OPTIONS = {
    "AP": {
        "label": "AP",
        "poll": "AP Top 25",
        "projected_column": "projected_ap_ranking",
        "projected_end_column": "projected_end_ap_ranking",
        "current_column": "current_ap_rank",
        "previous_column": "previous_ap_rank",
    },
    "CFP": {
        "label": "CFP",
        "poll": "Playoff Committee Rankings",
        "projected_column": "projected_cfp_ranking",
        "projected_end_column": "projected_end_cfp_ranking",
        "current_column": "current_cfp_rank",
        "previous_column": "previous_cfp_rank",
    },
}


# ----------------------------
# Styling
# ----------------------------
st.markdown(
    """
    <style>
      /* Move ONLY the selectbox upward */
      div[data-testid="stSelectbox"] { margin-top: -3rem; }
    </style>
    """,
    unsafe_allow_html=True
)


# ----------------------------
# Small helpers
# ----------------------------
def donut(probability: float, team_color: str) -> go.Figure:
    """Probability expected on 0–1 scale."""
    prob = float(np.clip(probability, 0.0, 1.0))
    percent = round(prob * 100, 1)

    fig = go.Figure(
        data=[
            go.Pie(
                values=[prob, 1 - prob],
                hole=0.5,
                marker_colors=[team_color, "#eee"],
                sort=False,
                direction="clockwise",
                textinfo="none",
            )
        ]
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(t=0, b=0, l=0, r=0),
        width=225,
        height=225,
        paper_bgcolor="rgba(0,0,0,0)",
        annotations=[
            dict(
                text=f"<b>{percent:.1f}%</b>",
                x=0.5,
                y=0.5,
                font_size=20,
                showarrow=False,
            )
        ],
    )
    return fig


def get_team_hex(team: str | None) -> str:
    if not team:
        return "#4C78A8"
    df = read_df(
        """
        WITH team_ids AS (
            SELECT homeid::text AS team_id
            FROM public.game_data
            WHERE hometeam = :team
              AND homeid IS NOT NULL

            UNION

            SELECT awayid::text AS team_id
            FROM public.game_data
            WHERE awayteam = :team
              AND awayid IS NOT NULL
        )
        SELECT tm."Color"
        FROM public.team_map tm
        JOIN team_ids ti
          ON tm."Id"::text = ti.team_id
        WHERE tm."Color" IS NOT NULL
        LIMIT 1
        """,
        params={"team": team},
    )
    return df["Color"].iloc[0] if not df.empty else "#4C78A8"


def quote_identifier(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


def get_table_columns(table_name: str) -> set[str]:
    df = read_df(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = :table_name
        """,
        params={"table_name": table_name},
    )
    return set(df["column_name"]) if not df.empty else set()


def scale_probability(value: float | int | None) -> float:
    if pd.isna(value):
        return 0.0

    prob = float(value)
    if prob > 1:
        prob = prob / 100.0
    return float(np.clip(prob, 0.0, 1.0))


def get_season_prediction(team: str | None, season: int | None) -> pd.Series:
    if not team or season is None:
        return pd.Series(dtype="float64")

    table_columns = get_table_columns("season_predictions_full")
    if not table_columns:
        return pd.Series(dtype="float64")

    team_id_col = next(
        (col for col in ["team_id", "teamid", "TeamId", "teamId"] if col in table_columns),
        None,
    )
    team_name_col = next(
        (col for col in ["team", "Team", "school", "school_name"] if col in table_columns),
        None,
    )

    selected_columns = [
        col
        for _, col in WIN_PROBABILITY_COLUMNS
        if col in table_columns
    ] + [col for col in SEASON_ODDS_COLUMNS if col in table_columns]

    if not selected_columns or (team_id_col is None and team_name_col is None):
        return pd.Series(dtype="float64")

    select_sql = ",\n            ".join(f"sp.{quote_identifier(col)}" for col in selected_columns)
    season_sql = 'AND sp."season" = :season' if "season" in table_columns else ""
    run_join_sql = (
        """
        LEFT JOIN public.game_prediction_runs gpr
          ON gpr.game_prediction_run_id = sp."game_prediction_run_id"
        """
        if "game_prediction_run_id" in table_columns
        else ""
    )
    order_parts = ["gpr.created_at DESC"] if "game_prediction_run_id" in table_columns else []
    order_columns = [
        col
        for col in [
            "created_at",
            "updated_at",
            "asof_date",
            "prediction_date",
            "game_prediction_run_id",
            "season_prediction_run_id",
        ]
        if col in table_columns
    ]
    order_parts.extend(f"sp.{quote_identifier(col)} DESC" for col in order_columns)
    order_sql = (
        "ORDER BY " + ", ".join(order_parts)
        if order_parts
        else ""
    )

    if team_id_col is not None:
        sql = f"""
        WITH team_ids AS (
            SELECT homeid::text AS team_id, MAX(season) AS last_seen
            FROM public.game_data
            WHERE hometeam = :team
              AND homeid IS NOT NULL
            GROUP BY homeid

            UNION ALL

            SELECT awayid::text AS team_id, MAX(season) AS last_seen
            FROM public.game_data
            WHERE awayteam = :team
              AND awayid IS NOT NULL
            GROUP BY awayid
        ),
        selected_team_id AS (
            SELECT team_id
            FROM team_ids
            ORDER BY last_seen DESC
            LIMIT 1
        )
        SELECT
            {select_sql}
        FROM public.season_predictions_full sp
        JOIN selected_team_id ti
          ON sp.{quote_identifier(team_id_col)}::text = ti.team_id
        {run_join_sql}
        WHERE 1 = 1
          {season_sql}
        {order_sql}
        LIMIT 1
        """
        params = {"team": team, "season": int(season)}
    else:
        sql = f"""
        SELECT
            {select_sql}
        FROM public.season_predictions_full sp
        {run_join_sql}
        WHERE sp.{quote_identifier(team_name_col)} = :team
          {season_sql}
        {order_sql}
        LIMIT 1
        """
        params = {"team": team, "season": int(season)}

    df = read_df(sql, params=params)
    return df.iloc[0] if not df.empty else pd.Series(dtype="float64")


def get_latest_ranking_projection(team: str | None, season: int | None) -> pd.Series:
    if not team or season is None:
        return pd.Series(dtype="object")

    df = read_df(
        """
        WITH latest_row AS (
            SELECT
                rp.*,
                COALESCE(
                    (
                        SELECT MAX(g.week)::int + 1
                        FROM public.game_data g
                        WHERE g.season = rp.season
                          AND g.week IS NOT NULL
                          AND g.startdate IS NOT NULL
                          AND (g.startdate AT TIME ZONE 'America/New_York')::date <= rp.run_date::date
                    ),
                    1
                ) AS projection_week
            FROM public.ranking_projections_full rp
            WHERE rp.season = :season
              AND rp.team = :team
              AND LOWER(COALESCE(rp.classification, '')) = 'fbs'
            ORDER BY rp.run_date DESC, rp.created_at DESC, rp.ranking_projection_run_id DESC
            LIMIT 1
        )
        SELECT *
        FROM latest_row
        """,
        params={"team": team, "season": int(season)},
    )
    return df.iloc[0] if not df.empty else pd.Series(dtype="object")


def get_poll_ranking_history(team: str | None, season: int | None, poll: str) -> pd.DataFrame:
    if not team or season is None:
        return pd.DataFrame()

    df = read_df(
        """
        SELECT
            week::int AS week,
            rank::int AS ranking
        FROM public.rankings
        WHERE season = :season
          AND poll = :poll
          AND school = :team
        ORDER BY week
        """,
        params={"team": team, "season": int(season), "poll": poll},
    )
    if df.empty:
        return df

    df["week"] = pd.to_numeric(df["week"], errors="coerce")
    df["ranking"] = pd.to_numeric(df["ranking"], errors="coerce")
    return df.dropna(subset=["week", "ranking"]).sort_values("week")


def get_schedule_map_data(team: str | None, season: int | None) -> pd.DataFrame:
    if not team or season is None:
        return pd.DataFrame()

    venue_columns = get_table_columns("venue_map")
    if not venue_columns:
        return pd.DataFrame()

    venue_id_col = next(
        (col for col in ["Id", "id", "VenueId", "venueid", "venue_id"] if col in venue_columns),
        None,
    )
    latitude_col = next(
        (col for col in ["Latitude", "latitude", "lat"] if col in venue_columns),
        None,
    )
    longitude_col = next(
        (col for col in ["Longitude", "longitude", "lng", "lon"] if col in venue_columns),
        None,
    )
    venue_name_col = next(
        (col for col in ["Name", "name", "Venue", "venue", "venue_name"] if col in venue_columns),
        None,
    )

    if venue_id_col is None or latitude_col is None or longitude_col is None:
        return pd.DataFrame()

    team_columns = get_table_columns("team_map")
    team_id_col = next(
        (col for col in ["Id", "id", "TeamId", "teamId", "team_id"] if col in team_columns),
        None,
    )
    logo_col = next(
        (col for col in ["Logo", "logo", "logo_url", "Logo_URL"] if col in team_columns),
        None,
    )
    venue_name_sql = (
        f"v.{quote_identifier(venue_name_col)} AS venue_name"
        if venue_name_col
        else "NULL::text AS venue_name"
    )
    opponent_id_sql = "CASE WHEN g.hometeam = :team THEN g.awayid ELSE g.homeid END"
    logo_sql = (
        f"tm.{quote_identifier(logo_col)} AS opponent_logo"
        if team_id_col and logo_col
        else "NULL::text AS opponent_logo"
    )
    logo_join_sql = (
        f"""
        LEFT JOIN public.team_map tm
          ON {opponent_id_sql}::text = tm.{quote_identifier(team_id_col)}::text
        """
        if team_id_col and logo_col
        else ""
    )

    df = read_df(
        f"""
        SELECT
            g.id,
            g.week,
            g.startdate,
            g.hometeam,
            g.awayteam,
            g.homepoints,
            g.awaypoints,
            g.venueid,
            {venue_name_sql},
            {opponent_id_sql} AS opponent_id,
            {logo_sql},
            v.{quote_identifier(latitude_col)}::float AS latitude,
            v.{quote_identifier(longitude_col)}::float AS longitude,
            CASE
                WHEN g.hometeam = :team THEN g.awayteam
                ELSE g.hometeam
            END AS opponent,
            CASE
                WHEN g.hometeam = :team THEN 'Home'
                ELSE 'Away'
            END AS location_type
        FROM public.game_data g
        JOIN public.venue_map v
          ON g.venueid::text = v.{quote_identifier(venue_id_col)}::text
        {logo_join_sql}
        WHERE g.season = :season
          AND g.startdate IS NOT NULL
          AND g.venueid IS NOT NULL
          AND (g.hometeam = :team OR g.awayteam = :team)
        ORDER BY g.startdate
        """,
        params={"team": team, "season": int(season)},
    )
    if df.empty:
        return df

    df["startdate"] = pd.to_datetime(df["startdate"], utc=True)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df["game_number"] = range(1, len(df) + 1)
    df["date_label"] = df["startdate"].dt.tz_convert("America/New_York").dt.strftime("%b %-d")
    df["matchup"] = np.where(
        df["location_type"] == "Home",
        "vs " + df["opponent"].astype(str),
        "at " + df["opponent"].astype(str),
    )
    df["result_label"] = np.where(
        df["homepoints"].notna() & df["awaypoints"].notna(),
        df["awaypoints"].astype("Int64").astype(str) + "-" + df["homepoints"].astype("Int64").astype(str),
        "Scheduled",
    )
    df = df.dropna(subset=["latitude", "longitude"]).copy()
    df["map_latitude"] = df["latitude"]
    df["map_longitude"] = df["longitude"]

    coord_key = df["latitude"].round(4).astype(str) + "," + df["longitude"].round(4).astype(str)
    duplicate_count = coord_key.map(coord_key.value_counts())
    duplicate_index = df.groupby(coord_key).cumcount()
    duplicate_mask = duplicate_count > 1
    if duplicate_mask.any():
        angle = 2 * np.pi * duplicate_index[duplicate_mask] / duplicate_count[duplicate_mask]
        radius = 0.18
        df.loc[duplicate_mask, "map_latitude"] = (
            df.loc[duplicate_mask, "latitude"] + radius * np.sin(angle)
        )
        df.loc[duplicate_mask, "map_longitude"] = (
            df.loc[duplicate_mask, "longitude"] + radius * np.cos(angle)
        )
    return df


def build_schedule_map(schedule_df: pd.DataFrame, team: str) -> str:
    if schedule_df.empty:
        return ""

    route_df = schedule_df.sort_values("game_number").reset_index(drop=True)
    games = []
    for _, row in route_df.iterrows():
        logo = row.get("opponent_logo")
        games.append(
            {
                "gameNumber": int(row["game_number"]),
                "lat": float(row["map_latitude"]),
                "lon": float(row["map_longitude"]),
                "matchup": str(row["matchup"]),
                "opponent": str(row["opponent"]),
                "venue": str(row["venue_name"]) if pd.notna(row["venue_name"]) else "Unknown venue",
                "date": str(row["date_label"]),
                "result": str(row["result_label"]),
                "locationType": str(row["location_type"]),
                "logo": str(logo) if pd.notna(logo) and str(logo).strip() else None,
            }
        )

    games_json = json.dumps(games)
    title = html_lib.escape(f"{team} Schedule Map")

    return f"""
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8" />
      <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
      <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
      <style>
        html, body {{ margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
        .map-wrap {{ width: 100%; height: 470px; position: relative; background: #f8fafc; }}
        #schedule-map {{ width: 100%; height: 430px; border-radius: 8px; overflow: hidden; }}
        .map-title {{ font-size: 20px; font-weight: 700; margin: 0 0 6px 0; color: #111827; }}
        .map-controls {{
          position: absolute;
          z-index: 1000;
          left: 12px;
          right: 12px;
          bottom: 10px;
          display: flex;
          align-items: center;
          gap: 8px;
          background: rgba(255, 255, 255, 0.92);
          border: 1px solid rgba(15, 23, 42, 0.12);
          border-radius: 8px;
          padding: 8px;
          box-shadow: 0 8px 20px rgba(15, 23, 42, 0.12);
        }}
        .map-controls button {{
          border: 0;
          border-radius: 6px;
          background: #111827;
          color: white;
          font-weight: 700;
          padding: 7px 11px;
          cursor: pointer;
        }}
        .map-controls input {{ flex: 1; }}
        .game-label {{ min-width: 64px; font-weight: 700; color: #111827; text-align: right; }}
        .logo-marker {{
          width: 42px;
          height: 42px;
          box-sizing: border-box;
          padding: 5px;
          border-radius: 999px;
          background: white;
          border: 2px solid #111827;
          box-shadow: 0 4px 12px rgba(15, 23, 42, 0.35);
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: hidden;
        }}
        .logo-marker.current {{
          width: 54px;
          height: 54px;
          padding: 5px;
          border-width: 3px;
          box-shadow: 0 7px 20px rgba(15, 23, 42, 0.45);
        }}
        .logo-marker img {{
          width: 100%;
          height: 100%;
          object-fit: contain;
        }}
        .fallback-marker {{
          font-weight: 800;
          font-size: 13px;
          color: #111827;
        }}
        .popup-title {{ font-weight: 800; margin-bottom: 3px; }}
        .popup-meta {{ color: #374151; }}
      </style>
    </head>
    <body>
      <div id="schedule-map-title" class="map-title">{title}</div>
      <div class="map-wrap">
        <div id="schedule-map"></div>
        <div class="map-controls">
          <button id="play-btn">Play</button>
          <button id="pause-btn">Pause</button>
          <input id="game-slider" type="range" min="0" max="0" value="0" />
          <div id="game-label" class="game-label">Game 1</div>
        </div>
      </div>
      <script>
        const games = {games_json};
        const flyZoom = 6;
        const millisecondsPerGame = 1800;
        let currentIndex = 0;
        let timer = null;

        const map = L.map("schedule-map", {{ zoomControl: true }});
        L.tileLayer("https://tiles.stadiamaps.com/tiles/stamen_terrain/{{z}}/{{x}}/{{y}}{{r}}.png", {{
          maxZoom: 19,
          attribution: "&copy; Stadia Maps &copy; Stamen Design &copy; OpenStreetMap contributors"
        }}).addTo(map);

        const points = games.map((game) => [game.lat, game.lon]);
        const fullRoute = L.polyline(points, {{ color: "#94a3b8", weight: 3, opacity: 0.6 }}).addTo(map);
        const progressRoute = L.polyline([], {{ color: "#111827", weight: 5, opacity: 0.85 }}).addTo(map);

        function markerHtml(game, current) {{
          const classes = current ? "logo-marker current" : "logo-marker";
          const fallback = game.opponent
            .split(" ")
            .map((part) => part[0])
            .join("")
            .slice(0, 3)
            .toUpperCase();
          const content = game.logo
            ? `<img src="${{game.logo}}" alt="${{game.opponent}} logo" />`
            : `<span class="fallback-marker">${{fallback}}</span>`;
          return `<div class="${{classes}}" title="Game ${{game.gameNumber}}: ${{game.matchup}}">${{content}}</div>`;
        }}

        function iconFor(game, current=false) {{
          const size = current ? 60 : 48;
          return L.divIcon({{
            html: markerHtml(game, current),
            className: "",
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
            popupAnchor: [0, -size / 2]
          }});
        }}

        const markers = games.map((game) => {{
          const marker = L.marker([game.lat, game.lon], {{ icon: iconFor(game, false) }}).addTo(map);
          marker.bindPopup(`
            <div class="popup-title">Game ${{game.gameNumber}}: ${{game.matchup}}</div>
            <div class="popup-meta">${{game.date}}<br>${{game.venue}}<br>${{game.locationType}} | ${{game.result}}</div>
          `);
          return marker;
        }});

        const currentMarker = L.marker(points[0], {{ icon: iconFor(games[0], true), zIndexOffset: 1000 }}).addTo(map);
        currentMarker.bindPopup("");

        const slider = document.getElementById("game-slider");
        const label = document.getElementById("game-label");
        const title = document.getElementById("schedule-map-title");
        slider.max = Math.max(games.length - 1, 0);

        if (points.length > 1) {{
          map.fitBounds(fullRoute.getBounds(), {{ padding: [30, 30] }});
        }} else {{
          map.setView(points[0], flyZoom);
        }}

        function setGame(index, fly=true) {{
          currentIndex = Math.max(0, Math.min(index, games.length - 1));
          const game = games[currentIndex];
          const latLng = [game.lat, game.lon];

          progressRoute.setLatLngs(points.slice(0, currentIndex + 1));
          currentMarker.setLatLng(latLng);
          currentMarker.setIcon(iconFor(game, true));
          currentMarker.setPopupContent(`
            <div class="popup-title">Game ${{game.gameNumber}}: ${{game.matchup}}</div>
            <div class="popup-meta">${{game.date}}<br>${{game.venue}}<br>${{game.locationType}} | ${{game.result}}</div>
          `);
          slider.value = currentIndex;
          label.textContent = `Game ${{game.gameNumber}}`;
          title.textContent = `{title} | Game ${{game.gameNumber}}: ${{game.matchup}}`;

          if (fly) {{
            map.flyTo(latLng, flyZoom, {{ duration: 0.8 }});
          }}
        }}

        function play() {{
          clearInterval(timer);
          setGame(currentIndex, true);
          timer = setInterval(() => {{
            if (currentIndex >= games.length - 1) {{
              clearInterval(timer);
              return;
            }}
            setGame(currentIndex + 1, true);
          }}, millisecondsPerGame);
        }}

        document.getElementById("play-btn").addEventListener("click", play);
        document.getElementById("pause-btn").addEventListener("click", () => clearInterval(timer));
        slider.addEventListener("input", (event) => {{
          clearInterval(timer);
          setGame(Number(event.target.value), true);
        }});

        setGame(0, false);
      </script>
    </body>
    </html>
    """


def build_win_distribution(season_prediction: pd.Series) -> pd.DataFrame:
    dist_df = pd.DataFrame(
        {
            "Wins": [str(wins) for wins, _ in WIN_PROBABILITY_COLUMNS],
            "Probability": [
                scale_probability(season_prediction.get(column, 0.0))
                for _, column in WIN_PROBABILITY_COLUMNS
            ],
        }
    )
    return dist_df


def render_odds_donut(title: str, probability: float, team_color: str) -> None:
    st.markdown(
        f"<div style='text-align:center; font-size:18px; font-weight:600;'>{title}</div>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(
        donut(probability, team_color),
        use_container_width=True,
        config={"displayModeBar": False},
    )


def format_rank(value: float | int | None) -> str:
    if pd.isna(value):
        return "NR"
    return f"#{int(round(float(value)))}"


def win_probability_style(probability: float) -> str:
    if pd.isna(probability):
        return "background-color: #d1d5db; color: #374151;"

    prob = float(np.clip(probability, 0.0, 1.0))

    if prob <= 0.5:
        ratio = prob / 0.5
        start = np.array([220, 38, 38])
        end = np.array([250, 204, 21])
    else:
        ratio = (prob - 0.5) / 0.5
        start = np.array([250, 204, 21])
        end = np.array([22, 163, 74])

    red, green, blue = (start + (end - start) * ratio).astype(int)
    text_color = "#111827" if 0.25 <= prob <= 0.75 else "#ffffff"
    return f"background-color: rgb({red}, {green}, {blue}); color: {text_color};"


# ----------------------------
# Data for dropdown
# ----------------------------
game_data = read_df(
    """
    SELECT *
    FROM public.game_data
    WHERE startdate IS NOT NULL
      AND homeclassification = 'fbs'
      AND awayclassification = 'fbs'
    """
)
current_season = int(game_data["season"].max())
teams = sorted(pd.concat([game_data["hometeam"], game_data["awayteam"]]).dropna().unique())


# ----------------------------
# Header: dropdown + title
# ----------------------------
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    selected_team = st.selectbox("", options=teams, index=None, placeholder="Select a team")

team_hex = get_team_hex(selected_team)
team_label = selected_team or ""

st.markdown(
    f"""
    <h1 style='text-align:left; margin-top:-1.5rem; margin-bottom:0.25rem;'>
      Single Team Projections for: {team_label}
    </h1>
    """,
    unsafe_allow_html=True,
)


# ----------------------------
# Main content (only after team selected)
# ----------------------------
if selected_team:
    now = pd.Timestamp.now(tz="UTC")

    # Team games + win probabilities
    team_games = read_df(
        """
        WITH latest_run AS (
            SELECT game_prediction_run_id
            FROM public.game_prediction_runs
            WHERE season = :season
              AND status = 'success'
            ORDER BY created_at DESC
            LIMIT 1
        )
        SELECT
            g.*,
            p.model_version AS model_version,
            CASE
                WHEN g.hometeam = :team THEN p.homewinprob
                WHEN g.awayteam = :team THEN p.awaywinprob
                ELSE NULL
            END AS teamwinprob
        FROM public.game_data g
        LEFT JOIN latest_run r
          ON TRUE
        LEFT JOIN public.game_predictions_full p
          ON p.game_prediction_run_id = r.game_prediction_run_id
         AND p.gameid = g.id::text
        WHERE g.startdate IS NOT NULL
          AND (g.hometeam = :team OR g.awayteam = :team)
          AND g.homeclassification = 'fbs'
          AND g.awayclassification = 'fbs'
        """,
        params={"team": selected_team, "season": current_season},
    )

    team_games["startdate"] = pd.to_datetime(team_games["startdate"], utc=True)

    # Upcoming games
    upcoming_games = team_games[team_games["startdate"] > now].sort_values("startdate")

    # Season-long projections
    season_prediction = get_season_prediction(selected_team, current_season)
    dist_df = build_win_distribution(season_prediction)
    bowl_prob = float(dist_df.loc[dist_df["Wins"].astype(int) >= 6, "Probability"].sum())
    conference_champion_prob = scale_probability(
        season_prediction.get("conference_champion_prob", 0.0)
    )
    playoff_prob = scale_probability(season_prediction.get("playoff_prob", 0.0))
    national_champion_prob = scale_probability(
        season_prediction.get("national_champion_prob", 0.0)
    )
    latest_ranking_projection = get_latest_ranking_projection(selected_team, current_season)
    schedule_map_df = get_schedule_map_data(selected_team, current_season)

    # Layout: table + bar chart
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader(f"Upcoming Games for {selected_team}")
        upcoming_start_et = upcoming_games["startdate"].dt.tz_convert("America/New_York")
        upcoming_display = (
            upcoming_games.assign(
                Date=upcoming_start_et.dt.strftime("%m/%d/%Y"),
                Time=upcoming_start_et.dt.strftime("%-I:%M %p"),
                win_probability=pd.to_numeric(upcoming_games["teamwinprob"], errors="coerce"),
            )[
                ["Date", "Time", "hometeam", "awayteam", "win_probability", "model_version"]
            ].rename(
                columns={
                    "hometeam": "Home Team",
                    "awayteam": "Away Team",
                    "win_probability": "Win Probability",
                    "model_version": "Model Version",
                }
            )
        )

        st.dataframe(
            upcoming_display.style
            .format({"Win Probability": lambda x: "NA" if pd.isna(x) else f"{x:.1%}"})
            .applymap(win_probability_style, subset=["Win Probability"]),
            hide_index=True,
            use_container_width=True,
        )

    with right_col:
        st.subheader("Projected Regular-Season Win Distribution")
        if dist_df["Probability"].sum() == 0:
            st.info(f"No season prediction found for {selected_team} in {current_season}.")
        else:
            chart = (
                alt.Chart(dist_df)
                .mark_bar(color=team_hex)
                .encode(
                    x=alt.X("Wins:N", title="Final Regular-Season Wins", sort=[str(i) for i in range(14)]),
                    y=alt.Y("Probability:Q", title="Probability"),
                    tooltip=["Wins:N", alt.Tooltip("Probability:Q", format=".1%")],
                )
            )
            st.altair_chart(chart, use_container_width=True)

    # Bottom: season projection odds
    pie1col, pie2col, pie3col, pie4col = st.columns(4)

    with pie1col:
        render_odds_donut("Bowl Eligibility Odds", bowl_prob, team_hex)

    with pie2col:
        render_odds_donut("Conference Champion Odds", conference_champion_prob, team_hex)

    with pie3col:
        render_odds_donut("CFP Team Odds", playoff_prob, team_hex)

    with pie4col:
        render_odds_donut("National Champion Odds", national_champion_prob, team_hex)

    ranking_left, ranking_right = st.columns(2)

    with ranking_left:
        ranking_choice = st.radio(
            "Ranking Type",
            options=list(RANKING_OPTIONS.keys()),
            horizontal=True,
            label_visibility="collapsed",
            key="ranking_projection_type",
        )
        ranking_option = RANKING_OPTIONS[ranking_choice]
        poll = ranking_option["poll"]
        projected_col = ranking_option["projected_column"]
        projected_end_col = ranking_option["projected_end_column"]
        current_col = ranking_option["current_column"]
        rank_label = ranking_option["label"]
        poll_history = get_poll_ranking_history(selected_team, current_season, poll)
        projected_rank = latest_ranking_projection.get(projected_col, np.nan)
        projected_end_rank = latest_ranking_projection.get(projected_end_col, np.nan)
        current_rank = latest_ranking_projection.get(current_col, np.nan)
        projection_week = latest_ranking_projection.get("projection_week", np.nan)
        run_date = latest_ranking_projection.get("run_date", None)
        run_type = latest_ranking_projection.get("run_type", None)
        model_version = latest_ranking_projection.get("model_version", None)

        st.markdown(
            f"<div style='font-size:20px; font-weight:700;'>Projected {rank_label} Ranking: {format_rank(projected_rank)}</div>",
            unsafe_allow_html=True,
        )

        caption_parts = []
        if not pd.isna(projected_end_rank):
            caption_parts.append(f"Projected end-of-season: {format_rank(projected_end_rank)}")
        if not pd.isna(current_rank):
            caption_parts.append(f"Current poll rank: {format_rank(current_rank)}")
        if run_date is not None and not pd.isna(run_date):
            run_label = pd.to_datetime(run_date).strftime("%b %-d, %Y")
            run_source = f"{run_type} run" if run_type is not None and not pd.isna(run_type) else "latest run"
            caption_parts.append(f"Projection from {run_label} {run_source}")
        if model_version is not None and not pd.isna(model_version):
            caption_parts.append(f"Model: {model_version}")
        if not pd.isna(projection_week):
            caption_parts.append(f"Projected poll week: {int(projection_week)}")
        if caption_parts:
            st.caption(" | ".join(caption_parts))

        chart_parts = []
        if not poll_history.empty:
            actual_df = poll_history.rename(columns={"week": "Week", "ranking": "Ranking"})
            actual_df["Type"] = "Actual"
            chart_parts.append(actual_df[["Week", "Ranking", "Type"]])

        if not pd.isna(projected_rank) and not pd.isna(projection_week):
            projected_df = pd.DataFrame(
                {
                    "Week": [int(projection_week)],
                    "Ranking": [float(projected_rank)],
                    "Type": ["Projected"],
                }
            )
            chart_parts.append(projected_df)

        if not chart_parts:
            st.info(f"No current-season {rank_label} poll history or ranking projection found for {selected_team}.")
        else:
            chart_df = pd.concat(chart_parts, ignore_index=True)
            y_max = max(25, int(np.ceil(chart_df["Ranking"].max())))
            week_sort = sorted(chart_df["Week"].dropna().astype(int).unique().tolist())

            ranking_chart = (
                alt.Chart(chart_df)
                .mark_line(point=True)
                .encode(
                    x=alt.X(
                        "Week:O",
                        title="Week",
                        sort=week_sort,
                    ),
                    y=alt.Y(
                        "Ranking:Q",
                        title=f"{rank_label} Ranking",
                        scale=alt.Scale(domain=[1, y_max], reverse=True),
                        axis=alt.Axis(tickMinStep=1),
                    ),
                    color=alt.Color(
                        "Type:N",
                        scale=alt.Scale(
                            domain=["Actual", "Projected"],
                            range=[team_hex, "#111827"],
                        ),
                        legend=alt.Legend(title=None),
                    ),
                    strokeDash=alt.StrokeDash(
                        "Type:N",
                        scale=alt.Scale(
                            domain=["Actual", "Projected"],
                            range=[[1, 0], [4, 4]],
                        ),
                        legend=None,
                    ),
                    tooltip=[
                        alt.Tooltip("Week:O", title="Week"),
                        alt.Tooltip("Ranking:Q", title=f"{rank_label} Ranking", format=".0f"),
                        alt.Tooltip("Type:N", title="Source"),
                    ],
                )
            )
            st.altair_chart(ranking_chart, use_container_width=True)

    with ranking_right:
        if schedule_map_df.empty:
            st.info(f"No mapped schedule venues found for {selected_team} in {current_season}.")
        else:
            components.html(
                build_schedule_map(schedule_map_df, selected_team),
                height=490,
                scrolling=False,
            )

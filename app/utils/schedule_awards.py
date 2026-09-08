"""Weekly award shortlists using Schedule Analysis's existing award rules."""

from dataclasses import dataclass

import pandas as pd


@dataclass
class AwardShortlist:
    name: str
    explanation: str
    candidates: pd.DataFrame
    metrics: dict[str, str]


def top_candidates(rows, mask, columns, ascending):
    candidates = rows.loc[mask].dropna(subset=columns).copy()
    tie_columns = [column for column in ("team", "opponent", "game_id") if column in candidates and column not in columns]
    return candidates.sort_values(columns + tie_columns, ascending=ascending + [True] * len(tie_columns),
                                  kind="stable").head(5).reset_index(drop=True)


def build_award_shortlists(team_rows, games, excitement_column=None):
    """Rank up to five eligible performances per award; never select a winner."""
    rows = team_rows.copy()
    if not rows.empty:
        # Preserve the existing Schedule Analysis formulas, including its
        # neutral probability fallback and the Almost Did It eligibility rules.
        rows["award_win_probability"] = rows["win_probability"].fillna(0.5).clip(0.01, 0.99)
        rows["difficulty_multiplier"] = 0.75 + ((1 - rows["award_win_probability"]) * 0.5)
        rows["offense_score"] = rows["offense_ppa_percentile"] * rows["difficulty_multiplier"]
        rows["defense_score"] = rows["defense_ppa_percentile"] * rows["difficulty_multiplier"]
        rows["under_gap"] = rows["projected_mov"] - rows["actual_mov"]
        rows["loss_margin"] = -rows["actual_mov"]
        rows["overperformance"] = rows["actual_mov"] - rows["projected_mov"]
        rows["almost_famous_score"] = rows["overperformance"] + ((1 - rows["award_win_probability"]) * 20) - rows["loss_margin"] * 0.75

    def award(name, explanation, mask, columns, ascending, metrics):
        candidates = top_candidates(rows, mask(rows), columns, ascending) if not rows.empty else pd.DataFrame()
        return AwardShortlist(name, explanation, candidates, metrics)

    shortlists = [
        award("Biggest Winner", "Largest winning margin, excluding games against FCS opponents.",
              lambda r: r["won"] & ~r["vs_fcs"], ["actual_mov"], [False],
              {"actual_mov": "Winning margin"}),
        award("Biggest Upset", "Winning teams with the lowest projected win probability.",
              lambda r: r["won"], ["win_probability"], [True],
              {"win_probability": "Win probability"}),
        award("Closest Win", "Smallest winning margin; higher projected win probability breaks ties.",
              lambda r: r["won"], ["actual_mov", "win_probability"], [True, False],
              {"actual_mov": "Winning margin", "win_probability": "Win probability"}),
        award("Best Offense", "Offensive PPA percentile × opponent-difficulty multiplier; FCS opponents excluded.",
              lambda r: ~r["vs_fcs"], ["offense_score", "offense_ppa_percentile", "offense_ppa"], [False, False, False],
              {"offense_score": "Award score", "offense_ppa": "PPA/play", "offense_ppa_percentile": "PPA percentile",
               "win_probability": "Win probability"}),
        award("Best Defense", "Defensive PPA percentile × opponent-difficulty multiplier; FCS opponents excluded.",
              lambda r: ~r["vs_fcs"], ["defense_score", "defense_ppa_percentile", "defense_ppa"], [False, False, True],
              {"defense_score": "Award score", "defense_ppa": "PPA allowed/play", "defense_ppa_percentile": "PPA percentile",
               "win_probability": "Win probability"}),
        award("Underwhelming", "Wins that fell furthest below the projected margin.",
              lambda r: r["won"] & r["under_gap"].gt(0), ["under_gap"], [False],
              {"under_gap": "Below projection", "projected_mov": "Projected margin", "actual_mov": "Actual margin"}),
        award("Almost Did It", "Underdogs (≤45% win probability) who lost by at most 14 and beat the projected margin.",
              lambda r: ~r["won"] & r["award_win_probability"].le(0.45) & r["loss_margin"].le(14) & r["overperformance"].gt(0),
              ["almost_famous_score", "loss_margin", "win_probability"], [False, True, True],
              {"almost_famous_score": "Award score", "loss_margin": "Loss margin", "overperformance": "Above projection",
               "win_probability": "Win probability"}),
    ]
    excitement = pd.DataFrame()
    if excitement_column and excitement_column in games:
        excitement = games.copy()
        excitement["_excitement"] = pd.to_numeric(excitement[excitement_column], errors="coerce")
        excitement = excitement.dropna(subset=["_excitement"])
        tie_columns = [column for column in ("matchup", "game_id") if column in excitement]
        excitement = excitement.sort_values(["_excitement", *tie_columns], ascending=[False, *([True] * len(tie_columns))],
                                            kind="stable").head(5).reset_index(drop=True)
    shortlists.append(AwardShortlist("Most Exciting", "Games with the highest available excitement index.", excitement,
                                     {"_excitement": "Excitement index"}))
    return shortlists


def shortlist_table(shortlist):
    """Keep numeric decision metrics numeric; present results from the team's side."""
    candidates = shortlist.candidates
    if candidates.empty:
        return pd.DataFrame()
    displayed = pd.DataFrame({"Candidate rank": range(1, len(candidates) + 1)})
    if shortlist.name == "Most Exciting":
        displayed["Matchup"] = candidates["matchup"]
        home_points, away_points = candidates["homepoints"], candidates["awaypoints"]
        displayed["Final score (away–home)"] = [
            f"{int(away)}–{int(home)}" if pd.notna(home) and pd.notna(away) else "—"
            for home, away in zip(home_points, away_points)
        ]
    else:
        displayed["Team"] = candidates["team"]
        displayed["Opponent"] = candidates["opponent"]
        displayed["Result"] = [
            f"{'W' if points_for > points_against else 'L' if points_for < points_against else 'T'} {int(points_for)}–{int(points_against)}"
            if pd.notna(points_for) and pd.notna(points_against) else "—"
            for points_for, points_against in zip(candidates["points_for"], candidates["points_against"])
        ]
    for field, label in shortlist.metrics.items():
        displayed[label] = candidates[field] * 100 if field == "win_probability" else candidates[field]
    return displayed

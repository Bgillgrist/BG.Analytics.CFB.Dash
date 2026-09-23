"""Session-local team appearance choices for conquest maps and their slides."""

import pandas as pd


DEFAULT_ALTERNATE_COLORS = {"ucla", "mississippi state"}


def asset_text(value):
    if value is None or pd.isna(value):
        return ""
    value = str(value).strip()
    return "" if value.lower() in {"", "nan", "none", "null"} else value


def apply_team_appearance(teams, alternate_colors=None, alternate_logos=None):
    """Resolve preferred assets on a copy; retain the other logo as fallback.

    Omitted preferences preserve the original map: the two color overrides and
    dark logos wherever available. An explicit empty selection uses primaries.
    """
    result = teams.copy()
    colors = DEFAULT_ALTERNATE_COLORS if alternate_colors is None else set(alternate_colors)
    logos = set(result["team_key"]) if alternate_logos is None else set(alternate_logos)
    for index, row in result.iterrows():
        secondary = asset_text(row.get("team_secondary_color"))
        if row["team_key"] in colors and secondary:
            result.at[index, "team_color"] = secondary
        primary = asset_text(row.get("team_logo"))
        alternate = asset_text(row.get("team_logo_dark"))
        preferred, fallback = (alternate, primary) if row["team_key"] in logos else (primary, alternate)
        result.at[index, "team_logo"] = preferred or fallback
        result.at[index, "team_logo_dark"] = fallback
    return result


def render_team_appearance_controls(teams):
    """Keep preferences independent of map rules, seasons, and widget cleanup."""
    import streamlit as st

    available = teams.drop_duplicates("team_key").sort_values("team")
    labels = available.set_index("team_key")["team"].to_dict()
    options = list(labels)
    preferences = st.session_state.setdefault("conquest_team_appearance", {"colors": {}, "logos": {}})
    for row in available.itertuples(index=False):
        preferences["colors"].setdefault(row.team_key, row.team_key in DEFAULT_ALTERNATE_COLORS)
        preferences["logos"].setdefault(row.team_key, bool(asset_text(row.team_logo_dark)))

    def remember(kind, widget_key):
        selected = set(st.session_state[widget_key])
        st.session_state["conquest_team_appearance"][kind].update(
            {key: key in selected for key in options}
        )

    selected = {}
    for container, kind, heading, label in zip(
        st.columns(2), ("colors", "logos"),
        ("Alternate team colors", "Alternate team logos"),
        ("Use alternate color for", "Use alternate logo for"),
    ):
        with container, st.expander(heading):
            widget_key = f"_conquest_alternate_{kind}"
            st.session_state[widget_key] = [key for key in options if preferences[kind].get(key, False)]
            selected[kind] = st.multiselect(
                label, options, format_func=labels.get, key=widget_key,
                on_change=remember, args=(kind, widget_key),
                help="Add a team to use its alternate asset; remove it to use its primary asset. "
                     "If the selected version is unavailable, the available version is used.",
            )
            if kind == "colors":
                st.caption("UCLA and Mississippi State start with alternate colors. Colors apply in Team territory mode.")
            else:
                st.caption("Teams with dark/alternate logos start selected to preserve the current map look. "
                           "Choices also apply to team logos in the rankings slide.")
    return selected["colors"], selected["logos"]

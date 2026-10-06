"""Code shared by the pages of the app: team colours, helpers, data and the season / date controls."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from cryptography.hazmat.primitives import serialization


# Main colour of each team's logo, used by the evolution lines, the game timeline and the scorers chart
TEAM_COLORS = {
    "Anaheim Ducks": "#F47A38",
    "Boston Bruins": "#FFB81C",
    "Buffalo Sabres": "#003087",
    "Calgary Flames": "#C8102E",
    "Carolina Hurricanes": "#CE1126",
    "Chicago Blackhawks": "#CF0A2C",
    "Colorado Avalanche": "#6F263D",
    "Columbus Blue Jackets": "#002654",
    "Dallas Stars": "#006847",
    "Detroit Red Wings": "#CE1126",
    "Edmonton Oilers": "#FF4C00",
    "Florida Panthers": "#C8102E",
    "Los Angeles Kings": "#111111",
    "Minnesota Wild": "#154734",
    "Montréal Canadiens": "#AF1E2D",
    "Nashville Predators": "#FFB81C",
    "New Jersey Devils": "#CE1126",
    "New York Islanders": "#00539B",
    "New York Rangers": "#0038A8",
    "Ottawa Senators": "#DA1A32",
    "Philadelphia Flyers": "#F74902",
    "Pittsburgh Penguins": "#FCB514",
    "San Jose Sharks": "#006D75",
    "Seattle Kraken": "#68A2B9",
    "St. Louis Blues": "#002F87",
    "Tampa Bay Lightning": "#002868",
    "Toronto Maple Leafs": "#00205B",
    "Utah Mammoth": "#6CACE4",
    "Vancouver Canucks": "#00205B",
    "Vegas Golden Knights": "#B4975A",
    "Washington Capitals": "#C8102E",
    "Winnipeg Jets": "#041E42",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Formatting seasons: 20252026 -> "2025 - 2026"
def display_season(season_int):
    season_str = str(season_int)
    return str(season_str[:4]) + " - " + str(season_str[4:])


@st.cache_resource
def _private_key_der():
    """Private key from the private_key_pem secret (Streamlit Cloud, where there's no key file),
    decrypted and converted to the DER bytes the Snowflake connector expects."""
    secrets = st.secrets["connections"]["snowflake"]
    password = secrets.get("private_key_file_pwd")
    key = serialization.load_pem_private_key(
        secrets["private_key_pem"].encode(),
        password=password.encode() if password else None,
    )
    return key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def get_connection():
    # Locally, secrets.toml points to the key file (private_key_file); on Streamlit Cloud the key content is in the secrets
    if "private_key_pem" in st.secrets["connections"]["snowflake"]:
        return st.connection("snowflake", private_key=_private_key_der())
    return st.connection("snowflake")


# The Airflow pipeline loads new data once a day (10:15 UTC): the app keeps its query results
# until REFRESH_HOUR_UTC, then queries Snowflake again, once, for everyone
REFRESH_HOUR_UTC = 12


def data_version():
    """The date of the data currently in Snowflake: changes once a day, at REFRESH_HOUR_UTC.
    Before that hour it's still yesterday's date, as the new data may not be loaded yet."""
    return (datetime.now(timezone.utc) - timedelta(hours=REFRESH_HOUR_UTC)).date()


@st.cache_data(max_entries=10, show_spinner="Loading data...")
def _cached_query(sql, version):
    """Runs the query and keeps the result. st.cache_data keys the cache on the arguments:
    same sql and same version -> the stored result is returned, Snowflake isn't queried.
    `version` isn't used in the body, it's only there so a new day means a new cache entry.
    (The cursor is used instead of conn.query, as conn.query has its own cache with a ttl.)"""
    return get_connection().cursor().execute(sql).fetch_pandas_all()


def run_query(sql):
    """Query result, cached until the next refresh (see data_version)."""
    return _cached_query(sql, data_version())


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

# Ranking history of every team, used by the Standings and Evolution pages (cached 10 min)
def load_rankings():
    return run_query(
        """
        select
            rankings.ranking_date,
            rankings.season,
            rankings.ranking,
            teams.logo_url,
            teams.name as team,
            teams.conference_name as conference,
            teams.division_name as division,
            rankings.games_played,
            rankings.points,
            rankings.total_wins,
            rankings.regulation_wins,
            rankings.regulation_ot_wins,
            rankings.goals_for,
            rankings.goals_against,
            rankings.goal_diff,
            rankings.tie_rate::float as tie_rate
        from fct_league_rankings as rankings
        inner join dim_teams as teams
            on rankings.team_id = teams.team_id
        """
    )


# ---------------------------------------------------------------------------
# Controls, the same on every page: they're drawn in the container they're given,
# so each page places them in its own row of columns
# ---------------------------------------------------------------------------

def season_picker(container, seasons):
    """Season selectbox, most recent season first."""
    return container.selectbox(
        "Season",
        options=sorted(seasons, reverse=True),
        format_func=display_season,
    )


def view_picker(container):
    """League / Conference / Division."""
    return container.segmented_control("View", ["League", "Conference", "Division"], default="League") or "League"


def group_picker(container, rankings, view):
    """For the Conference and Division views: which conference or division to show.
    Returns (group column, selected group), or (None, None) for the League view (nothing drawn)."""
    if view == "League":
        return None, None
    group_column = view.upper()  # "CONFERENCE" or "DIVISION"
    groups = sorted(rankings[group_column].unique())
    group = container.segmented_control(
        view,
        groups,
        default=groups[0],
        key=f"group_{view}",  # one widget per view, as the options differ
    ) or groups[0]
    return group_column, group


def date_picker(container, available_dates, key):
    """Date input limited to the season's dates. Returns the selected date among available_dates:
    a day without data (no game played that day) falls back to the last date before it.
    The key should include the season, so changing season resets the date to its last day."""
    season_dates = pd.to_datetime(pd.Series(available_dates))
    picked_date = container.date_input(
        "Date",
        value=season_dates.iloc[-1].date(),
        min_value=season_dates.iloc[0].date(),
        max_value=season_dates.iloc[-1].date(),
        key=key,
    )
    date_i = season_dates.searchsorted(pd.Timestamp(picked_date), side="right") - 1
    return available_dates[date_i]

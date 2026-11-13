"""Code shared by the pages: team colours, Snowflake access with a daily cache, and the controls
that appear on several pages (season, date, league / conference / division)."""

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from cryptography.hazmat.primitives import serialization
from snowflake.connector.errors import ProgrammingError


# Main colour of each team's logo: evolution lines, game timeline, game charts
TEAM_COLORS_MAIN = {
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

# Colour of the away team when it's too close to the home team's main colour (see game_colors).
# From each logo, except Detroit, Tampa Bay and Toronto: theirs only have white, which wouldn't show
# on the page, so they use a silver
TEAM_COLORS_SEC = {
    "Anaheim Ducks": "#89734C",
    "Boston Bruins": "#010101",
    "Buffalo Sabres": "#FFB81C",
    "Calgary Flames": "#F1BE48",
    "Carolina Hurricanes": "#A2AAAD",
    "Chicago Blackhawks": "#D9A510",
    "Colorado Avalanche": "#236192",
    "Columbus Blue Jackets": "#C8102E",
    "Dallas Stars": "#A2AAAD",
    "Detroit Red Wings": "#A2AAAD",
    "Edmonton Oilers": "#00205B",
    "Florida Panthers": "#041E42",
    "Los Angeles Kings": "#A2AAAD",
    "Minnesota Wild": "#A6192E",
    "Montréal Canadiens": "#001E62",
    "Nashville Predators": "#041E42",
    "New Jersey Devils": "#010101",
    "New York Islanders": "#FC4C02",
    "New York Rangers": "#C8102E",
    "Ottawa Senators": "#B9975B",
    "Philadelphia Flyers": "#010101",
    "Pittsburgh Penguins": "#010101",
    "San Jose Sharks": "#E57200",
    "Seattle Kraken": "#041C2C",
    "St. Louis Blues": "#FFB81C",
    "Tampa Bay Lightning": "#A2AAAD",
    "Toronto Maple Leafs": "#A2AAAD",
    "Utah Mammoth": "#010101",
    "Vancouver Canucks": "#97999B",
    "Vegas Golden Knights": "#333F48",
    "Washington Capitals": "#041E42",
    "Winnipeg Jets": "#A6192E",
}

TIED_COLOR = "#e6e6e6"  # timeline bar while the score is tied, and any team without a colour
CLOSE_COLORS = 130  # under this color_distance, two teams can't be told apart on a chart

# Pairs under CLOSE_COLORS that still look different on a chart: Minnesota's forest green next to a
# navy. Both keep their main colour, so that Minnesota stays green instead of switching to its red
DISTINCT_PAIRS = {
    frozenset({"Minnesota Wild", "Toronto Maple Leafs"}),
    frozenset({"Minnesota Wild", "Vancouver Canucks"}),
    frozenset({"Minnesota Wild", "Tampa Bay Lightning"}),
}


def color_distance(color_1, color_2):
    """How different two "#RRGGBB" colours look: 0 when identical, 765 from black to white.
    This is the "redmean" formula, an RGB distance weighted to be closer to what the eye sees."""
    red_1, green_1, blue_1 = (int(color_1[i:i + 2], 16) for i in (1, 3, 5))
    red_2, green_2, blue_2 = (int(color_2[i:i + 2], 16) for i in (1, 3, 5))
    mean_red = (red_1 + red_2) / 2
    return (
        (2 + mean_red / 256) * (red_1 - red_2) ** 2
        + 4 * (green_1 - green_2) ** 2
        + (2 + (255 - mean_red) / 256) * (blue_1 - blue_2) ** 2
    ) ** 0.5


def game_colors(home_team, away_team):
    """(home colour, away colour) for the charts of one game: their main colours, except that the
    away team takes its secondary colour when the two are too close, unless the pair is in
    DISTINCT_PAIRS."""
    home_color = TEAM_COLORS_MAIN.get(home_team, TIED_COLOR)
    away_color = TEAM_COLORS_MAIN.get(away_team, TIED_COLOR)
    too_close = color_distance(home_color, away_color) < CLOSE_COLORS
    if too_close and frozenset({home_team, away_team}) not in DISTINCT_PAIRS:
        away_color = TEAM_COLORS_SEC.get(away_team, away_color)
    return home_color, away_color


def display_season(season):
    """20252026 -> "2025 - 2026"."""
    season = str(season)
    return f"{season[:4]} - {season[4:]}"


# ---------------------------------------------------------------------------
# Snowflake
# ---------------------------------------------------------------------------


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
    # Locally, secrets.toml points to the key file (private_key_file). On Streamlit Cloud there is
    # no file, so the key itself is stored in the secrets (private_key_pem)
    if "private_key_pem" in st.secrets["connections"]["snowflake"]:
        return st.connection("snowflake", private_key=_private_key_der())
    return st.connection("snowflake")


# Airflow loads new data once a day at 06:15 UTC. Query results are kept until REFRESH_HOUR_UTC,
# then Snowflake is queried again, once for every visitor
REFRESH_HOUR_UTC = 8


def data_version():
    """The date of the data currently in Snowflake: changes once a day, at REFRESH_HOUR_UTC.
    Before that hour it's still yesterday's date, as the new data may not be loaded yet."""
    return (datetime.now(timezone.utc) - timedelta(hours=REFRESH_HOUR_UTC)).date()


def fetch_query(sql):
    """Query result, straight from Snowflake: the caller caches it. A cursor is used rather than
    conn.query, which has its own ttl cache."""
    try:
        return get_connection().cursor().execute(sql).fetch_pandas_all()
    except ProgrammingError:
        get_connection().reset()
        return get_connection().cursor().execute(sql).fetch_pandas_all()


@st.cache_data(max_entries=10, show_spinner="Loading data...")
def _cached_query(sql, version):
    """The cache is keyed on the arguments: `version` is unused in the body, it only makes a new
    day a new cache entry."""
    return fetch_query(sql)


def run_query(sql):
    """Query result, cached until the next refresh (see data_version)."""
    return _cached_query(sql, data_version())


# ---------------------------------------------------------------------------
# Data shared by several pages
# ---------------------------------------------------------------------------

def load_rankings():
    """Daily standings of every team, for the Standings and Evolution pages."""
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
# Controls. Each one is drawn in the container it is given, so every page can lay them out
# in its own row of columns
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
    """Which conference or division to show, for those views.
    Returns (group column, selected group), or (None, None) in the League view, where nothing is drawn."""
    if view == "League":
        return None, None
    group_column = view.upper()  # "CONFERENCE" or "DIVISION"
    groups = sorted(rankings[group_column].unique())
    group = container.segmented_control(
        view,
        groups,
        default=groups[0],
        key=f"group_{view}",  # one widget per view, since the options differ
    ) or groups[0]
    return group_column, group


def date_picker(container, available_dates, key):
    """Date input limited to the season. Returns a date from available_dates: a day without data
    (no game that day) falls back to the last date before it.
    Include the season in the key, so that changing season resets the date to the season's end."""
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

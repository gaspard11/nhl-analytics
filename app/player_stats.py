"""Player stats page: skaters or goalies on a chosen date. Clicking a column header sorts the table
by that column, highlights it and recomputes the rank (see sortable_table)."""

import streamlit as st
from st_aggrid import JsCode

from common import date_picker, group_picker, run_query, season_picker, view_picker
from sortable_table import NUMBER_COLUMN, TEXT_COLUMN, UNSORTABLE, image_column, sortable_table


ROW_HEIGHT = 70  # pixels, twice Streamlit's default, so the headshots are readable

# Values as nhl.com shows them: time on ice 1234:56 (or 21:34 per game), save % .915, GAA 2.47,
# shooting % 12.5
TOI_FORMAT = JsCode("""
function(params) {
    if (params.value == null) return '';
    const seconds = Math.round(params.value);
    return Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
}
""")
SAVE_PCT_FORMAT = JsCode("function(params) { return params.value == null ? '' : params.value.toFixed(3).replace(/^0/, ''); }")
GAA_FORMAT = JsCode("function(params) { return params.value == null ? '' : params.value.toFixed(2); }")
SHOOTING_PCT_FORMAT = JsCode("function(params) { return params.value == null ? '' : (100 * params.value).toFixed(1); }")
PLUS_MINUS_FORMAT = JsCode("function(params) { return params.value > 0 ? '+' + params.value : String(params.value); }")

# Narrower than the default number column, so the 15 skater stats fit on a laptop screen
STAT_COLUMN = {**NUMBER_COLUMN, "minWidth": 58}

PLAYER_COLUMN_DEFS = [
    {"field": "RANK", "headerName": "Rank", "type": "numericColumn", "width": 70, **UNSORTABLE,
     "headerTooltip": "Rank on the column the table is sorted by. Tied players share a rank"},
    {"field": "HEADSHOT_URL", "headerName": "", **image_column(80, 56)},
    {"field": "NAME", "headerName": "Name", **TEXT_COLUMN},
    {"field": "LOGO_URL", "headerName": "", **image_column(80, 56)},
    {"field": "TEAM", "headerName": "Team", "headerTooltip": "The player's current team", **TEXT_COLUMN},
]

# The columns of nhl.com's skater summary, this season up to the chosen date
SKATER_COLUMN_DEFS = PLAYER_COLUMN_DEFS + [
    {"field": "GAMES_PLAYED", "headerName": "GP", "headerTooltip": "Games played: games with at least one shift", **STAT_COLUMN},
    {"field": "GOALS", "headerName": "G", "headerTooltip": "Goals, shootout goals excluded", **STAT_COLUMN},
    {"field": "ASSISTS", "headerName": "A", "headerTooltip": "Assists, first and second", **STAT_COLUMN},
    {"field": "POINTS", "headerName": "P", "headerTooltip": "Points: goals + assists",
     "sort": "desc", **STAT_COLUMN},  # sorted by points to start with
    {"field": "PLUS_MINUS", "headerName": "+/-",
     "headerTooltip": "Plus/minus: +1 for each even strength or short handed goal of the team with the skater on the ice, -1 for each one against",
     "valueFormatter": PLUS_MINUS_FORMAT, **STAT_COLUMN},
    {"field": "PENALTY_MINUTES", "headerName": "PIM", "headerTooltip": "Penalty minutes", **STAT_COLUMN},
    {"field": "EV_GOALS", "headerName": "EVG", "headerTooltip": "Even strength goals", **STAT_COLUMN},
    {"field": "EV_POINTS", "headerName": "EVP", "headerTooltip": "Even strength points: goals + assists", **STAT_COLUMN},
    {"field": "PP_GOALS", "headerName": "PPG", "headerTooltip": "Power play goals", **STAT_COLUMN},
    {"field": "PP_POINTS", "headerName": "PPP", "headerTooltip": "Power play points: goals + assists", **STAT_COLUMN},
    {"field": "SH_GOALS", "headerName": "SHG", "headerTooltip": "Short handed goals", **STAT_COLUMN},
    {"field": "SH_POINTS", "headerName": "SHP", "headerTooltip": "Short handed points: goals + assists", **STAT_COLUMN},
    {"field": "SHOTS", "headerName": "S", "headerTooltip": "Shots on goal, shootout excluded", **STAT_COLUMN},
    {"field": "SHOOTING_PCT", "headerName": "S%", "headerTooltip": "Shooting percentage: goals / shots",
     "valueFormatter": SHOOTING_PCT_FORMAT, **STAT_COLUMN},
    {"field": "TOI_PER_GAME", "headerName": "TOI/GP", "headerTooltip": "Average time on ice per game, minutes:seconds",
     "valueFormatter": TOI_FORMAT, **STAT_COLUMN, "minWidth": 72},
]

# The columns of nhl.com's goalie summary, this season up to the chosen date
GOALIE_COLUMN_DEFS = PLAYER_COLUMN_DEFS + [
    {"field": "GAMES_PLAYED", "headerName": "GP", "headerTooltip": "Games played: games with at least one shift", **STAT_COLUMN},
    {"field": "GAMES_STARTED", "headerName": "GS", "headerTooltip": "Games started: in net at the opening faceoff", **STAT_COLUMN},
    {"field": "AWARDED_WINS", "headerName": "W",
     "headerTooltip": "Wins: the goalie in net when the team scored the goal that put it ahead for good", **STAT_COLUMN},
    {"field": "AWARDED_LOSSES", "headerName": "L", "headerTooltip": "Losses in regulation", **STAT_COLUMN},
    {"field": "AWARDED_OT_LOSSES", "headerName": "OT", "headerTooltip": "Losses in overtime or in a shootout", **STAT_COLUMN},
    {"field": "SHOTS_AGAINST", "headerName": "SA", "headerTooltip": "Shots against: saves + goals against", **STAT_COLUMN},
    {"field": "SAVES", "headerName": "Svs", "headerTooltip": "Saves: shots on goal stopped, shootout excluded", **STAT_COLUMN},
    {"field": "GOALS_AGAINST", "headerName": "GA", "headerTooltip": "Goals against, shootout and empty net goals excluded", **STAT_COLUMN},
    {"field": "SAVE_PCT", "headerName": "SV%", "headerTooltip": "Save percentage: saves / shots against", "valueFormatter": SAVE_PCT_FORMAT, **STAT_COLUMN},
    # Sorted by GAA to start with, lowest first
    {"field": "GAA", "headerName": "GAA", "headerTooltip": "Goals against average: goals against per 60 minutes", "valueFormatter": GAA_FORMAT,
     **STAT_COLUMN, "sortingOrder": ["asc", "desc"], "sort": "asc"},
    {"field": "SHUTOUTS", "headerName": "SO", "headerTooltip": "Shutouts: full games without a goal against, shootout excluded", **STAT_COLUMN},
    {"field": "TOI_SECONDS", "headerName": "TOI", "headerTooltip": "Time on ice this season, minutes:seconds",
     "valueFormatter": TOI_FORMAT, **STAT_COLUMN, "minWidth": 80},
]


# One row per player and per day. The team is the player's current team (dim_players)
PLAYER_SELECT = """
        stats.ranking_date,
        stats.season,
        stats.player_id,
        players.first_name || ' ' || players.last_name as name,
        players.headshot_url,
        teams.name as team,
        teams.division_name as division,
        teams.conference_name as conference,
        teams.logo_url,
"""
PLAYER_JOINS = """
    inner join nhl_analytics.marts.dim_players as players
        on stats.player_id = players.player_id
    inner join nhl_analytics.marts.dim_teams as teams
        on players.team_id = teams.team_id
"""


def load_skaters():
    return run_query(
        f"""
    select
        {PLAYER_SELECT}
        stats.games_played,
        stats.goals,
        stats.assists,
        stats.points,
        stats.plus_minus,
        stats.penalty_minutes,
        stats.ev_goals,
        stats.ev_goals + stats.ev_assists                       as ev_points,
        stats.pp_goals,
        stats.pp_goals + stats.pp_assists                       as pp_points,
        stats.sh_goals,
        stats.sh_goals + stats.sh_assists                       as sh_points,
        stats.shots,
        -- ::float: Snowflake decimals would come back as Python Decimal objects, sorted as text
        (stats.goals / nullif(stats.shots, 0))::float           as shooting_pct,
        (stats.toi_seconds / stats.games_played)::float         as toi_per_game
    from nhl_analytics.marts.fct_skater_stats as stats
    {PLAYER_JOINS}
    """
    )


def load_goalies():
    return run_query(
        f"""
    select
        {PLAYER_SELECT}
        stats.games_played,
        stats.games_started,
        stats.awarded_wins,
        stats.awarded_losses,
        stats.awarded_ot_losses,
        stats.toi_seconds,
        stats.shots_against,
        stats.saves,
        stats.goals_against,
        -- ::float: Snowflake decimals would come back as Python Decimal objects, sorted as text
        stats.save_pct::float as save_pct,
        stats.gaa::float as gaa,
        stats.shutouts
    from nhl_analytics.marts.fct_goalie_stats as stats
    {PLAYER_JOINS}
    """
    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

season_col, date_col, player_type_col, view_col, group_col = st.columns([2, 2, 3, 3, 4], vertical_alignment="bottom")

selected_type = player_type_col.segmented_control("Players", ["Skaters", "Goalies"], default="Skaters") or "Skaters"
# Only the chosen type is queried
if selected_type == "Skaters":
    players, column_defs = load_skaters(), SKATER_COLUMN_DEFS
else:
    players, column_defs = load_goalies(), GOALIE_COLUMN_DEFS

selected_season = season_picker(season_col, players["SEASON"].unique())
season_players = players[players["SEASON"] == selected_season]
available_dates = sorted(season_players["RANKING_DATE"].unique())
selected_date = date_picker(date_col, available_dates, key=f"date_{selected_season}")

view = view_picker(view_col)
group_column, group = group_picker(group_col, season_players, view)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

day_players = season_players[season_players["RANKING_DATE"] == selected_date]
if group_column:
    day_players = day_players[day_players[group_column] == group]

sortable_table(
    day_players,
    column_defs,
    ROW_HEIGHT,
    # A new table for every choice of players, date and group, so the data is never stale
    key=f"players_{selected_type}_{selected_season}_{selected_date}_{view}_{group}",
    rank_column=True,
)

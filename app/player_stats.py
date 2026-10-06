"""Player stats page: players ranked by points, goals or assists on a chosen date."""

import streamlit as st

from common import date_picker, group_picker, run_query, season_picker, view_picker


ROW_HEIGHT = 70  # pixels, twice Streamlit's default, so the headshots are readable
HIGHLIGHT_STYLE = {"background-color": "#e8eefc", "color": "#1f3b8f"}  # the column the table is ranked by

COLUMNS = {
    "RANK": st.column_config.NumberColumn("Rank", width="small"),
    "HEADSHOT_URL": st.column_config.ImageColumn("", width="small"),
    "NAME": st.column_config.TextColumn("Name", width="small"),
    "LOGO_URL": st.column_config.ImageColumn("", width="small"),
    "TEAM": st.column_config.TextColumn("Team"),
    "POINTS": st.column_config.NumberColumn("Points"),
    "GOALS": st.column_config.NumberColumn("Goals"),
    "ASSISTS": st.column_config.NumberColumn("Assists"),
}


def players_table(players, metric):
    """Players sorted by metric (POINTS, GOALS or ASSISTS); equal values share a rank."""
    table = players.sort_values(metric, ascending=False)
    table = table.assign(RANK=table[metric].rank(method="min", ascending=False).astype(int))
    # Streamlit only applies a Styler's colours (not bold), hence a background colour
    styled = table[list(COLUMNS)].style.set_properties(subset=[metric], **HIGHLIGHT_STYLE)
    st.dataframe(
        styled,
        column_config=COLUMNS,
        hide_index=True,
        width="stretch",
        row_height=ROW_HEIGHT,
        # Header (35px, not affected by row_height) + every row, so the table shows without scrolling
        height=35 + len(table) * ROW_HEIGHT + 3,
    )


# One row per player and per day. The team is the player's current team (dim_players)
players = run_query(
    """
    select
        points.ranking_date,
        points.season,
        points.player_id,
        players.first_name || ' ' || players.last_name as name,
        players.headshot_url,
        teams.name as team,
        teams.division_name as division,
        teams.conference_name as conference,
        teams.logo_url,
        points.number_of_points as points,
        goals.number_of_goals as goals,
        assists.number_of_assists as assists
    from nhl_analytics.marts.fct_player_points_rankings as points
    inner join nhl_analytics.marts.fct_player_goals_rankings as goals
        on points.player_id = goals.player_id and points.ranking_date = goals.ranking_date
    inner join nhl_analytics.marts.fct_player_assists_rankings as assists
        on points.player_id = assists.player_id and points.ranking_date = assists.ranking_date
    inner join nhl_analytics.marts.dim_players as players
        on points.player_id = players.player_id
    inner join nhl_analytics.marts.dim_teams as teams
        on players.team_id = teams.team_id
    """
)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

season_col, date_col, metric_col, view_col, group_col = st.columns([2, 2, 3, 3, 4], vertical_alignment="bottom")

selected_metric = metric_col.segmented_control("Metric", ["Points", "Goals", "Assists"], default="Points") or "Points"

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

players_table(day_players, selected_metric.upper())

import streamlit as st

st.set_page_config(page_title="NHL", layout="wide") 
from common import date_picker, group_picker, load_rankings, season_picker, view_picker, get_connection
conn = get_connection()


players = conn.query(
    """select 
    points.ranking_date,
    points.season,
    points.player_id,
    players.first_name || ' ' || players.last_name as Name,
    players.headshot_url,
    teams.name as team,
    division_name as division,
    conference_name as conference,
    teams.logo_url,
    number_of_points as points,
    number_of_goals as goals,
    number_of_assists as assists
    from 
    nhl_analytics.marts.fct_player_points_rankings points
    inner join nhl_analytics.marts.fct_player_goals_rankings goals on points.player_id = goals.player_id and points.ranking_date = goals.ranking_date
    inner join nhl_analytics.marts.fct_player_assists_rankings assists on assists.player_id = points.player_id and points.ranking_date = assists.ranking_date
    inner join nhl_analytics.marts.dim_players players on points.player_id = players.player_id
    inner join nhl_analytics.marts.dim_teams teams on players.team_id = teams.team_id
    """,
        ttl=600,
    )

COLUMNS = {
        "RANK": st.column_config.NumberColumn("Rank", width="small"),
        "HEADSHOT_URL": st.column_config.ImageColumn("", width="small"),
        "NAME": st.column_config.TextColumn("Name   ", width="small"),
        "LOGO_URL": st.column_config.ImageColumn("", width="small"),
        "TEAM": st.column_config.TextColumn("Team"),
        "POINTS": st.column_config.NumberColumn("Points"),
        "GOALS": st.column_config.NumberColumn("Goals"),
        "ASSISTS": st.column_config.NumberColumn("Assists")
    }

ROW_HEIGHT = 70  # pixels: twice the default (35), so the headshots are bigger


def standings_table(players, metric):
        table = players.sort_values(metric, ascending=False)
        table = table.assign(RANK=table[metric].rank(method="min", ascending=False).astype(int))
        styled = table[list(COLUMNS)].style.set_properties(
            subset=[metric],
            **{"background-color": "#e8eefc", "color": "#1f3b8f"},
        )
        st.dataframe(
            styled,
            column_config=COLUMNS,
            hide_index=True,
            width="stretch",
            row_height=ROW_HEIGHT,
            # Header (35px, unchanged) + every row, so the whole table shows without scrolling
            height=35 + len(table) * ROW_HEIGHT + 3,
        )







season_col, date_col, score_view_col, view_col, group_col = st.columns([2, 2, 3, 3, 4], vertical_alignment="bottom")
selected_metric = score_view_col.segmented_control("Metric", ["Points", "Goals", "Assists"], default="Points") or "Points"

selected_season = season_picker(season_col, players["SEASON"].unique())
season_rankings = players[players["SEASON"] == selected_season]
available_dates = sorted(season_rankings["RANKING_DATE"].unique())
selected_date = date_picker(date_col, available_dates, key=f"date_{selected_season}")

view = view_picker(view_col)
group_column, group = group_picker(group_col, season_rankings, view)



day_ranking = season_rankings[season_rankings["RANKING_DATE"] == selected_date]
if group_column:
    day_ranking = day_ranking[day_ranking[group_column] == group]

standings_table(day_ranking,selected_metric.upper())



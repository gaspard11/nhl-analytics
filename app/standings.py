"""Standings page: the standings table on a chosen date, for the league, a conference or a division."""

import streamlit as st

from common import date_picker, group_picker, load_rankings, season_picker, view_picker


COLUMNS = {
    "RANK": st.column_config.NumberColumn("Rank", width="small"),
    "LOGO_URL": st.column_config.ImageColumn("", width="small"),
    "TEAM": st.column_config.TextColumn("Team"),
    "GAMES_PLAYED": st.column_config.NumberColumn("GP", help="Games played"),
    "POINTS": st.column_config.NumberColumn("PTS", help="Points: win = 2, OT/shootout loss = 1"),
    "TOTAL_WINS": st.column_config.NumberColumn("W", help="Wins, including shootout wins"),
    "REGULATION_WINS": st.column_config.NumberColumn("RW", help="Regulation wins"),
    "REGULATION_OT_WINS": st.column_config.NumberColumn("ROW", help="Regulation + overtime wins"),
    "GOALS_FOR": st.column_config.NumberColumn("GF", help="Goals for"),
    "GOALS_AGAINST": st.column_config.NumberColumn("GA", help="Goals against"),
    "GOAL_DIFF": st.column_config.NumberColumn("DIFF", help="Goal differential", format="%+d"),
}


def standings_table(teams):
    """RANKING is the league order (tie breakers included). The rank shown is recomputed within the
    teams displayed, so a division starts at 1. Tied teams share a rank."""
    table = teams.sort_values("RANKING").assign(RANK=lambda d: d["RANKING"].rank(method="min").astype(int))
    st.dataframe(
        table[list(COLUMNS)],
        column_config=COLUMNS,
        hide_index=True,
        width="stretch",
        # Header + one 35px row per team, so the whole table shows without scrolling
        height=(len(table) + 1) * 35 + 3,
    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

rankings = load_rankings()

season_col, date_col, view_col, group_col = st.columns([2, 2, 3, 4], vertical_alignment="bottom")

selected_season = season_picker(season_col, rankings["SEASON"].unique())
season_rankings = rankings[rankings["SEASON"] == selected_season]
available_dates = sorted(season_rankings["RANKING_DATE"].unique())
selected_date = date_picker(date_col, available_dates, key=f"date_{selected_season}")

view = view_picker(view_col)
group_column, group = group_picker(group_col, season_rankings, view)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

day_ranking = season_rankings[season_rankings["RANKING_DATE"] == selected_date]
if group_column:
    day_ranking = day_ranking[day_ranking[group_column] == group]

standings_table(day_ranking)

"""Blown leads page: the games behind the Lead retention page. For each selected team, from the start of
the season up to a chosen date, the timelines of the games it lost even though it led more than it
trailed, or had a lead in the 3rd. A loss in overtime or in a shootout counts."""

import streamlit as st

from common import IN_THE_3RD_SQL, data_version, date_picker, load_rankings, run_query, season_picker
from game_details import TIMELINE_TOOLTIP_CSS, game_timeline, load_goals


st.html(f"<style>{TIMELINE_TOOLTIP_CSS}</style>")

# One row per game lost by a team that led more than it trailed or had a lead in the 3rd. % lead =
# time leading / (time leading + time trailing), on a single game
BLOWN_LEADS_SQL = f"""
    with team_games as (
        select game_id, home_team_id as team_id, away_team_id as opponent_id
        from fct_games
        where home_team_score < away_team_score
        union all
        select game_id, away_team_id, home_team_id
        from fct_games
        where away_team_score < home_team_score
    ),

    team_leads as (
        select
            team_games.game_id,
            team_games.team_id,
            sum(iff(segments.leading_team_id = team_games.team_id, segments.duration_s, 0)) as leading_time,
            sum(iff(segments.leading_team_id = team_games.opponent_id, segments.duration_s, 0)) as trailing_time,
            max(iff(segments.leading_team_id = team_games.team_id and {IN_THE_3RD_SQL}, 1, 0)) = 1 as led_in_3rd
        from team_games
        inner join fct_games_leading_segments as segments
            on team_games.game_id = segments.game_id
        group by team_games.game_id, team_games.team_id
    )

    select
        team_leads.game_id,
        teams.name as team,
        div0(team_leads.leading_time, team_leads.leading_time + team_leads.trailing_time)::float as lead_rate,
        team_leads.led_in_3rd
    from team_leads
    inner join dim_teams as teams
        on team_leads.team_id = teams.team_id
    where team_leads.leading_time > team_leads.trailing_time
        or team_leads.led_in_3rd
"""


def game_title(game):
    """"2026-10-14 · Boston Bruins 3 @ Florida Panthers 4 (OT)", away team first as on the Games page."""
    title = (
        f'{game["GAME_DATE"]} · {game["AWAY_TEAM"]} {game["AWAY_TEAM_FINAL_SCORE"]}'
        f' @ {game["HOME_TEAM"]} {game["HOME_TEAM_FINAL_SCORE"]}'
    )
    return title if game["LAST_PERIOD_TYPE"] == "REG" else f'{title} ({game["LAST_PERIOD_TYPE"]})'


def blown_why(game):
    """What makes this loss a blown lead: its % lead when over 50%, and its lead in the 3rd."""
    reasons = []
    if game["LEAD_RATE"] > 0.5:
        reasons.append(f':red-badge[{game["LEAD_RATE"]:.0%} lead]')
    if game["LED_IN_3RD"]:
        reasons.append(":orange-badge[Lead in the 3rd]")
    return " ".join(reasons)


def team_games(team, team_blown):
    """The timelines of a team's blown games, newest first."""
    for _, game in team_blown.sort_values("GAME_DATE", ascending=False, kind="stable").iterrows():
        with st.container(border=True, gap="small"):
            st.markdown(f"**{game_title(game)}** {blown_why(game)}")
            game_timeline(game, goals_by_game.get(game["GAME_ID"], no_goals))


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

rankings = load_rankings()
games, goals_by_game, no_goals = load_goals(data_version())

season_col, date_col, teams_col = st.columns([2, 2, 3], vertical_alignment="bottom")

selected_season = season_picker(season_col, rankings["SEASON"].unique())
season_rankings = rankings[rankings["SEASON"] == selected_season]
# Not before the first game: nothing can have been blown yet
available_dates = sorted(season_rankings.loc[season_rankings["GAMES_PLAYED"] > 0, "RANKING_DATE"].unique())
selected_date = date_picker(date_col, available_dates, key=f"blown_date_{selected_season}")
selected_teams = teams_col.multiselect("Teams", sorted(season_rankings["TEAM"].unique()), placeholder="Choose teams")


# ---------------------------------------------------------------------------
# Page: one section per team, one timeline per game
# ---------------------------------------------------------------------------

st.markdown("Games lost with **more than 50% of the non-tied time in the lead**, or with **a lead at some point in the 3rd period**. Losses in overtime and in a shootout count.")

if not selected_teams:
    st.info("Choose one or more teams to see their blown leads.")
    st.stop()

season_games = games[(games["SEASON"] == selected_season) & (games["GAME_DATE"] <= selected_date)]
blown = season_games.merge(run_query(BLOWN_LEADS_SQL), on="GAME_ID")

for team in selected_teams:
    team_blown = blown[blown["TEAM"] == team]
    # on_change="rerun" tells the script whether the expander is open, so the timelines are only built
    # for the open teams
    details = st.expander(f"{team}: {len(team_blown)} blown", expanded=True, key=f"blown_{team}", on_change="rerun")
    if details.open:
        with details:
            if team_blown.empty:
                st.info(f"No blown lead for the {team} so far.")
            else:
                team_games(team, team_blown)

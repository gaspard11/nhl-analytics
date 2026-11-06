"""Games page: the last days of games up to a chosen date, newest first, with a button to load older
ones. Opening a game shows its timeline, the players' points and the goal log (see game_details.py)."""

from datetime import timedelta

import streamlit as st

from common import TIED_COLOR, data_version, date_picker, display_season, fetch_query, game_colors, season_picker
from game_details import (
    PERIOD_NAMES, goal_log, pbp_log, player_points, points_chart, roster_log, timeline_chart, stats_charts,
)


SCORE_ROW_LOGO_WIDTH = 100  # pixels
DAYS_PER_LOAD = 7  # days of games shown at first, and added by the Load more button
st.set_page_config(page_title="NHL", layout="wide")

st.html("""<style>
/* The details expander is the bottom of the game's card: no box of its own, a thin line above it */
[data-testid="stExpander"] details { border: none !important; border-top: 1px solid rgba(49, 51, 63, 0.1) !important; border-radius: 0 !important; }
[data-testid="stExpander"] summary { padding-left: 0 !important; }
/* No fullscreen button over logos and headshots */
[data-testid="stElementContainer"]:has([data-testid="stImage"]) [data-testid="stElementToolbar"] { display: none; }
/* Streamlit's tooltip styles leave with the last chart of the page, which showed the old tooltip's
   pill after closing a game. This rule stays, so a tooltip not in use is always hidden */
#vg-tooltip-element:not(.visible) { display: none; }
/* Goal tooltips of the timeline: centred title, round headshot */
#vg-tooltip-element h2 { font-size: 14px; margin: 0 0 6px; text-align: center; }
#vg-tooltip-element img { display: block; width: 120px; height: 120px; margin: 0 auto 6px; border-radius: 50%; background: #f0f2f6; }
/* First row of the goal tooltip (the goal type) shown as a pill centred under the headshot. A table row
   can't be wider than its columns, so the row only keeps the height and the pill is centred on the
   whole tooltip */
#vg-tooltip-element tr:first-child { height: 30px; }
#vg-tooltip-element tr:first-child td.key { display: none; }
#vg-tooltip-element tr:first-child td.value { position: absolute; left: 50%; transform: translateX(-50%); white-space: nowrap; padding: 2px 10px; border-radius: 999px; background: #e8eefc; color: #1f3b8f; font-weight: 600; font-size: 12px; }
/* Play-by-play log (game_details.pbp_log): one grid row per event, thin centred lines for whistles
   and period ends. Greys are see-through so they work on light and dark themes */
.pbp-period { font-weight: 600; margin: 14px 0 4px; }
.pbp-period:first-child { margin-top: 0; }
.pbp-row { display: grid; grid-template-columns: 40px 36px 32px 1fr auto; align-items: center; gap: 8px; padding: 5px 6px; border-bottom: 1px solid rgba(128, 128, 128, 0.15); font-size: 14px; }
.pbp-goal { background: rgba(33, 163, 90, 0.10); border-radius: 6px; }
.pbp-time { color: rgba(128, 128, 128, 0.9); font-size: 12px; font-variant-numeric: tabular-nums; }
.pbp-logo { width: 36px; }
.pbp-headshot { width: 32px; height: 32px; border-radius: 50%; background: rgba(128, 128, 128, 0.15); object-fit: cover; }
.pbp-pill { display: inline-block; margin-right: 6px; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.pbp-sub { color: rgba(128, 128, 128, 0.9); font-size: 12px; }
.pbp-right { display: flex; align-items: center; gap: 8px; white-space: nowrap; }
.pbp-tag { display: inline-flex; align-items: center; gap: 4px; padding: 1px 8px; border-radius: 999px; background: rgba(128, 128, 128, 0.12); font-size: 11px; }
.pbp-tag-logo { width: 18px; }
.pbp-goal-tag { background: rgba(33, 163, 90, 0.18); font-weight: 600; }
.pbp-line { display: flex; align-items: center; gap: 8px; margin: 4px 0; color: rgba(128, 128, 128, 0.9); font-size: 11px; }
/* Rosters (game_details.roster_log): the two teams side by side, one line per player */
.roster { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
.roster-team-name { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.roster-team-name img { width: 44px; }
.roster-group { margin: 12px 0 4px; color: rgba(128, 128, 128, 0.9); font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
.roster-player { display: grid; grid-template-columns: 32px 32px 1fr auto; align-items: center; gap: 8px; padding: 3px 0; border-bottom: 1px solid rgba(128, 128, 128, 0.15); font-size: 14px; }
.roster-number { color: rgba(128, 128, 128, 0.9); font-size: 12px; font-variant-numeric: tabular-nums; text-align: right; }
.roster-position { color: rgba(128, 128, 128, 0.9); font-size: 11px; }
.pbp-line::before, .pbp-line::after { content: ""; flex: 1; border-top: 1px dashed rgba(128, 128, 128, 0.3); }
</style>""")


# ---------------------------------------------------------------------------
# Queries, run once a day by load_games. The goals have one row per goal, with its game's columns repeated
# ---------------------------------------------------------------------------

GOALS_SQL = """
    select
        games.game_id,
        games.game_date,
        games.season,
        games.last_period_type,
        home_teams.name as home_team,
        away_teams.name as away_team,
        games.home_team_id,
        home_teams.logo_url as home_team_logo,
        away_teams.logo_url as away_team_logo,
        games.home_team_score as home_team_final_score,
        games.away_team_score as away_team_final_score,
        scorers.first_name || ' ' || scorers.last_name || coalesce(' #' || scorer_rosters.sweater_number, '') as scorer,
        assist1.first_name || ' ' || assist1.last_name || coalesce(' #' || assist1_rosters.sweater_number, '') as assist1,
        assist2.first_name || ' ' || assist2.last_name || coalesce(' #' || assist2_rosters.sweater_number, '') as assist2,
        scorers.headshot_url as scorer_headshot,
        assist1.headshot_url as assist1_headshot,
        assist2.headshot_url as assist2_headshot,
        goals.home_score,
        goals.away_score,
        goals.team_id as scoring_team_id,
        goals.period_number,
        goals.time_in_period,
        goals.goal_type as goal_type_code,
        goals.strength
    from nhl_analytics.marts.fct_games as games
    inner join nhl_analytics.marts.dim_teams as home_teams
        on games.home_team_id = home_teams.team_id
    inner join nhl_analytics.marts.dim_teams as away_teams
        on games.away_team_id = away_teams.team_id
    inner join nhl_analytics.marts.fct_goals as goals
        on games.game_id = goals.game_id
    inner join nhl_analytics.marts.dim_players as scorers
        on goals.scoring_player_id = scorers.player_id
    left join nhl_analytics.marts.dim_players as assist1
        on goals.assist1_player_id = assist1.player_id
    left join nhl_analytics.marts.dim_players as assist2
        on goals.assist2_player_id = assist2.player_id
    -- Sweater numbers worn in this game, shown next to the names
    left join nhl_analytics.marts.fct_game_rosters as scorer_rosters
        on goals.game_id = scorer_rosters.game_id and goals.scoring_player_id = scorer_rosters.player_id
    left join nhl_analytics.marts.fct_game_rosters as assist1_rosters
        on goals.game_id = assist1_rosters.game_id and goals.assist1_player_id = assist1_rosters.player_id
    left join nhl_analytics.marts.fct_game_rosters as assist2_rosters
        on goals.game_id = assist2_rosters.game_id and goals.assist2_player_id = assist2_rosters.player_id
    order by games.game_date, games.game_id, goals.period_number, goals.time_in_period
"""

EVENTS_SQL = """
    select
        games.game_id,
        games.game_date,
        games.season,
        games.last_period_type,
        home_teams.name as home_team,
        away_teams.name as away_team,
        games.home_team_id,
        home_teams.logo_url as home_team_logo,
        away_teams.logo_url as away_team_logo,
        games.home_team_score as home_team_final_score,
        games.away_team_score as away_team_final_score,
        events.team_id as event_team_id,
        event_type,
        events.player_1_desc,
        player1.first_name || ' ' || player1.last_name || coalesce(' #' || player1_rosters.sweater_number, '') as player_1,
        events.player_2_desc,
        player2.first_name || ' ' || player2.last_name || coalesce(' #' || player2_rosters.sweater_number, '') as player_2,
        events.player_3_desc,
        player3.first_name || ' ' || player3.last_name || coalesce(' #' || player3_rosters.sweater_number, '') as player_3,
        goalie.first_name || ' ' || goalie.last_name || coalesce(' #' || goalie_rosters.sweater_number, '') as goalie,
        player1.headshot_url as player1_headshot,
        player2.headshot_url as player2_headshot,
        player3.headshot_url as player3_headshot,
        goalie.headshot_url as goalie_headshot,
        events.home_score,
        events.away_score,
        events.period_number,
        events.time_in_period,
        events.zone_code,
        events.situation as situation,
        events.strength_adv_team,
        events.details,
        man_adv_team_id
    from nhl_analytics.marts.fct_games as games
    inner join nhl_analytics.marts.dim_teams as home_teams
        on games.home_team_id = home_teams.team_id
    inner join nhl_analytics.marts.dim_teams as away_teams
        on games.away_team_id = away_teams.team_id
    inner join nhl_analytics.marts.fct_games_events as events
        on games.game_id = events.game_id
    left join nhl_analytics.marts.dim_players as player1
        on events.player_1_id = player1.player_id
    left join nhl_analytics.marts.dim_players as player2
        on events.player_2_id = player2.player_id
    left join nhl_analytics.marts.dim_players as player3
        on events.player_3_id = player3.player_id
    left join nhl_analytics.marts.dim_players as goalie
        on events.goalie_in_net_id = goalie.player_id
    -- Sweater numbers worn in this game, shown next to the names
    left join nhl_analytics.marts.fct_game_rosters as player1_rosters
        on events.game_id = player1_rosters.game_id and events.player_1_id = player1_rosters.player_id
    left join nhl_analytics.marts.fct_game_rosters as player2_rosters
        on events.game_id = player2_rosters.game_id and events.player_2_id = player2_rosters.player_id
    left join nhl_analytics.marts.fct_game_rosters as player3_rosters
        on events.game_id = player3_rosters.game_id and events.player_3_id = player3_rosters.player_id
    left join nhl_analytics.marts.fct_game_rosters as goalie_rosters
        on events.game_id = goalie_rosters.game_id and events.goalie_in_net_id = goalie_rosters.player_id
    order by games.game_date, games.game_id, events.period_number, events.time_in_period
"""

# One row per player per game, with the sweater number they wore in that game (shown in its own
# column of the rosters, so not added to the name like in the goals and events)
ROSTERS_SQL = """
    select
        rosters.game_id,
        games.game_date,
        games.season,
        rosters.team_id,
        rosters.position,
        players.first_name || ' ' || players.last_name as player,
        rosters.sweater_number,
        players.headshot_url
    from nhl_analytics.marts.fct_game_rosters as rosters
    inner join nhl_analytics.marts.fct_games as games
        on rosters.game_id = games.game_id
    inner join nhl_analytics.marts.dim_players as players
        on rosters.player_id = players.player_id
    order by games.game_date, rosters.game_id, rosters.sweater_number
"""

STATS_SQL = """
    select
        stats.game_id,
        stats.team_id,
        teams.name as team_name,
        stats.stat_name,
        stats.stat_value
    from NHL_ANALYTICS.MARTS.FCT_GAMES_STATS stats
    join NHL_ANALYTICS.MARTS.DIM_TEAMS teams on stats.team_id = teams.team_id
"""

# goal_type of fct_goals, where the situation of each goal is worked out
GOAL_TYPE_LABELS = {
    "PS": "🎯 Penalty shot",
    "EN": "🥅 Empty net",
    "PPG": "⚡ Power play",
    "SHG": "🛡️ Short-handed",
    "EA": "➕ Extra attacker",
    "EV": "🟰 Even strength",
}


def goal_situation(goals):
    """Label shown for each goal, e.g. "⚡ Power play · 5 on 4". A penalty shot has no strength."""
    labels = goals["GOAL_TYPE_CODE"].map(GOAL_TYPE_LABELS)
    return labels.where(goals["GOAL_TYPE_CODE"] == "PS", labels + " · " + goals["STRENGTH"])


def prepare_goals(goals):
    """Adds the columns used by the game details. Done once a day for every goal, not game by game."""
    goals = goals.assign(PERIOD_NUMBER=goals["PERIOD_NUMBER"].astype(int))  # Snowflake returns a small int type
    minutes_seconds = goals["TIME_IN_PERIOD"].str.split(":", expand=True).astype(int)
    is_home_goal = goals["SCORING_TEAM_ID"] == goals["HOME_TEAM_ID"]
    home_leads = goals["HOME_SCORE"] > goals["AWAY_SCORE"]
    away_leads = goals["AWAY_SCORE"] > goals["HOME_SCORE"]
    home_color = goals["HOME_TEAM"].combine(goals["AWAY_TEAM"], lambda home, away: game_colors(home, away)[0])
    away_color = goals["HOME_TEAM"].combine(goals["AWAY_TEAM"], lambda home, away: game_colors(home, away)[1])
    return goals.assign(
        ELAPSED=(goals["PERIOD_NUMBER"] - 1) * 1200 + minutes_seconds[0] * 60 + minutes_seconds[1],  # seconds into the game
        SCORING_TEAM_SIDE=is_home_goal.map({True: "HOME", False: "AWAY"}),
        SCORING_TEAM=goals["HOME_TEAM"].where(is_home_goal, goals["AWAY_TEAM"]),
        SCORING_TEAM_LOGO=goals["HOME_TEAM_LOGO"].where(is_home_goal, goals["AWAY_TEAM_LOGO"]),
        LEADING_TEAM_COLOR=home_color.where(home_leads, away_color.where(away_leads, TIED_COLOR)),  # timeline colour after the goal
        GOAL_TYPE=goal_situation(goals),
        GOAL_TIME=goals["PERIOD_NUMBER"].map(PERIOD_NAMES) + " period · " + goals["TIME_IN_PERIOD"],
        ASSISTS=goals[["ASSIST1", "ASSIST2"]].apply(lambda names: ", ".join(names.dropna()) or "Unassisted", axis=1),
        SCORE=goals["HOME_TEAM"] + " " + goals["HOME_SCORE"].astype(str)
            + " - " + goals["AWAY_SCORE"].astype(str) + " " + goals["AWAY_TEAM"],
    )

def team_logo(events, team_id):
    """Logo of the team in team_id on each event, None when the event has no team (e.g. a whistle)."""
    logos = events["HOME_TEAM_LOGO"].where(team_id == events["HOME_TEAM_ID"], events["AWAY_TEAM_LOGO"])
    return logos.where(team_id.notna(), None)


def prepare_events(events):
    """Adds the columns used by the play-by-play log. Done once a day for every event, not game by game."""
    events = events.assign(PERIOD_NUMBER=events["PERIOD_NUMBER"].astype(int))  # Snowflake returns a small int type
    minutes_seconds = events["TIME_IN_PERIOD"].str.split(":", expand=True).astype(int)
    return events.assign(
        ELAPSED=(events["PERIOD_NUMBER"] - 1) * 1200 + minutes_seconds[0] * 60 + minutes_seconds[1],  # seconds into the game
        EVENT_TEAM_SIDE=(events["EVENT_TEAM_ID"] == events["HOME_TEAM_ID"]).map({True: "HOME", False: "AWAY"}),
        EVENT_TEAM_LOGO=team_logo(events, events["EVENT_TEAM_ID"]),
        MAN_ADV_LOGO=team_logo(events, events["MAN_ADV_TEAM_ID"]),
    )

@st.cache_resource(max_entries=1, show_spinner="Loading data...")
def load_games(version):
    """One row per game, and the goals, events, rosters and stats of each game by game id. `version`
    is unused in the body: a new day is a new cache entry (see data_version), so Snowflake is only
    queried once a day. cache_resource doesn't copy the data on every rerun like cache_data, but
    every user shares the same objects, so they must never be modified."""
    goals = prepare_goals(fetch_query(GOALS_SQL))
    return (
        goals.drop_duplicates(subset=["GAME_ID"]),
        dict(tuple(goals.groupby("GAME_ID"))),
        dict(tuple(prepare_events(fetch_query(EVENTS_SQL)).groupby("GAME_ID"))),
        dict(tuple(fetch_query(ROSTERS_SQL).groupby("GAME_ID"))),
        dict(tuple(fetch_query(STATS_SQL).groupby("GAME_ID"))),
    )


games, goals_by_game, events_by_game, rosters_by_game, stats_by_game = load_games(data_version())


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

season_col, team_col, date_col = st.columns([2, 3, 2], vertical_alignment="bottom")

selected_season = season_picker(season_col, games["SEASON"].unique())
season_games = games[games["SEASON"] == selected_season]

teams = sorted(set(games["HOME_TEAM"]) | set(games["AWAY_TEAM"]))
selected_team = team_col.selectbox("Team", ["All teams"] + teams)
if selected_team != "All teams":
    season_games = season_games[(season_games["HOME_TEAM"] == selected_team) | (season_games["AWAY_TEAM"] == selected_team)]

available_dates = sorted(season_games["GAME_DATE"].unique())
if not available_dates:
    st.info(f"No game for the {selected_team} in {display_season(selected_season)} yet.")
    st.stop()
selected_date = date_picker(date_col, available_dates, key=f"games_date_{selected_season}")


# ---------------------------------------------------------------------------
# Page: one card per game
# ---------------------------------------------------------------------------

# The filters are in the key, so that changing one goes back to the first days
shown_days_key = f"shown_days_{selected_season}_{selected_team}_{selected_date}"
shown_days = st.session_state.get(shown_days_key, DAYS_PER_LOAD)
first_shown_date = selected_date - timedelta(days=shown_days - 1)

games_to_date = season_games[season_games["GAME_DATE"] <= selected_date]
older_games = games_to_date[games_to_date["GAME_DATE"] < first_shown_date]
# Newest date first. A stable sort keeps the games of a day in their original order
shown_games = (
    games_to_date[games_to_date["GAME_DATE"] >= first_shown_date]
    .sort_values("GAME_DATE", ascending=False, kind="stable")
)


def score_row(game):
    """Home team, logo, score, how the game ended (REG / OT / SO), score, logo, away team.
    The winner's score is in bold."""
    home_score, away_score = game["HOME_TEAM_FINAL_SCORE"], game["AWAY_TEAM_FINAL_SCORE"]
    home_won = home_score > away_score
    home_score = f"**{home_score}**" if home_won else str(home_score)
    away_score = str(away_score) if home_won else f"**{away_score}**"

    away_score_col, away_logo_col, away_team_col, end_col, home_score_col,home_logo_col, home_team_col   = st.columns(
        7, vertical_alignment="center"
    )
    home_score_display = home_score
    away_score_display = away_score
    if game["LAST_PERIOD_TYPE"] != 'REG':
        if home_won:
            home_score_display+= ' (' + f"**{game['LAST_PERIOD_TYPE']}**" + ')'
        else:
            away_score_display+= ' (' + f"**{game['LAST_PERIOD_TYPE']}**" + ')'



    # width="stretch": by default text is only as wide as itself, so centring it would do nothing
    home_team_col.text(game["HOME_TEAM"], text_alignment="center", width="stretch")
    home_logo_col.container(horizontal_alignment="center").image(game["HOME_TEAM_LOGO"], width=SCORE_ROW_LOGO_WIDTH)
    home_score_col.markdown(home_score_display, text_alignment="center", width="stretch")
    end_col.text('@', text_alignment="center", width="stretch")
    away_score_col.markdown(away_score_display, text_alignment="center", width="stretch")
    away_logo_col.container(horizontal_alignment="center").image(game["AWAY_TEAM_LOGO"], width=SCORE_ROW_LOGO_WIDTH)
    away_team_col.text(game["AWAY_TEAM"], text_alignment="center", width="stretch")


# A fragment: the log menu and the play-by-play filters only rerun this game's details, not the
# whole page
@st.fragment
def game_details(game, game_goals, game_events, game_rosters, game_stats):
    if game["LAST_PERIOD_TYPE"] == "SO":
        overtime_length = 1200
    elif game["LAST_PERIOD_TYPE"] == "OT":
        # The OT ends with the winning goal
        overtime_length = game_goals.loc[game_goals["PERIOD_NUMBER"] == 4, "ELAPSED"].max() - 3600
    else:
        overtime_length = None

    st.markdown("#### Timeline")
    timeline_chart(game_goals, has_overtime=game["LAST_PERIOD_TYPE"] != "REG", overtime_length=overtime_length)

    charts_col, log_col = st.columns([2, 3], gap="large")
    with charts_col:
        # Same layout as the log menu on the right
        title_col, menu_col = st.columns([1, 2], vertical_alignment="center")
        chart = menu_col.segmented_control(
            "Chart", ["Stats", "Points"], default="Stats", required=True,
            key=f"chart_{game['GAME_ID']}", label_visibility="collapsed", width="stretch",
        )
        title_col.markdown(f"#### {chart}")
        if chart == "Points":
            points_chart(player_points(game_goals), game["HOME_TEAM"], game["AWAY_TEAM"])
        else:
            if game_stats is None:
                st.info("No stats for this game yet.")
            else:
                stats_charts(
                    game_stats, game["HOME_TEAM"], game["AWAY_TEAM"], game["HOME_TEAM_LOGO"], game["AWAY_TEAM_LOGO"],
                )
    with log_col:
        # Title on the left, the menu to switch log on the right. The menu is drawn first so the
        # title can follow what it picks
        title_col, menu_col = st.columns([1, 2], vertical_alignment="center")
        log = menu_col.segmented_control(
            "Log", ["Goals", "Play-by-play", "Rosters"], default="Goals", required=True,
            key=f"log_{game['GAME_ID']}", label_visibility="collapsed", width="stretch",
        )
        title_col.markdown(f"#### {log}")
        if log == "Goals":
            goal_log(game_goals)
        elif log == "Play-by-play":
            if game_events is None:
                st.info("No play-by-play for this game yet.")
            else:
                pbp_log(game_events)
        elif game_rosters is None:
            st.info("No roster for this game yet.")
        else:
            roster_log(game, game_rosters)


for date, day_games in shown_games.groupby("GAME_DATE", sort=False):
    st.subheader(date)
    for _, game in day_games.iterrows():
        with st.container(border=True, gap="small"):
            score_row(game)
            # on_change="rerun" tells the script whether the expander is open, so the details are only
            # built for the open games instead of for every game of the page on every rerun
            details = st.expander("Show details", key=f"details_{game['GAME_ID']}", on_change="rerun")
            if details.open:
                with details:
                    game_details(
                        game, goals_by_game[game["GAME_ID"]],
                        events_by_game.get(game["GAME_ID"]), rosters_by_game.get(game["GAME_ID"]),
                        stats_by_game.get(game["GAME_ID"]),
                    )

if not older_games.empty and st.button("Load more", width="stretch"):
    # At least as far as the next game, so that a long break doesn't make a click show nothing
    days_to_next_game = (selected_date - older_games["GAME_DATE"].max()).days + 1
    st.session_state[shown_days_key] = max(shown_days + DAYS_PER_LOAD, days_to_next_game)
    st.rerun()

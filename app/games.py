"""Games page: every game up to a chosen date, newest first. Opening a game shows its timeline,
the players' points and the goal log (see game_details.py)."""

import streamlit as st

from common import TEAM_COLORS, date_picker, display_season, run_query, season_picker
from game_details import PERIOD_NAMES, TIED_COLOR, goal_log, player_points, points_chart, timeline_chart


SCORE_ROW_LOGO_WIDTH = 100  # pixels

st.html("""<style>
/* The details expander is the bottom of the game's card: no box of its own, a thin line above it */
[data-testid="stExpander"] details { border: none !important; border-top: 1px solid rgba(49, 51, 63, 0.1) !important; border-radius: 0 !important; }
[data-testid="stExpander"] summary { padding-left: 0 !important; }
/* No fullscreen button over logos and headshots */
[data-testid="stElementContainer"]:has([data-testid="stImage"]) [data-testid="stElementToolbar"] { display: none; }
/* Goal tooltips of the timeline: centred title, round headshot */
#vg-tooltip-element h2 { font-size: 14px; margin: 0 0 6px; text-align: center; }
#vg-tooltip-element img { display: block; width: 120px; height: 120px; margin: 0 auto 6px; border-radius: 50%; background: #f0f2f6; }
/* First row of the goal tooltip (the goal type) shown as a pill centred under the headshot. A table row
   can't be wider than its columns, so the row only keeps the height and the pill is centred on the
   whole tooltip */
#vg-tooltip-element tr:first-child { height: 30px; }
#vg-tooltip-element tr:first-child td.key { display: none; }
#vg-tooltip-element tr:first-child td.value { position: absolute; left: 50%; transform: translateX(-50%); white-space: nowrap; padding: 2px 10px; border-radius: 999px; background: #e8eefc; color: #1f3b8f; font-weight: 600; font-size: 12px; }
</style>""")


# ---------------------------------------------------------------------------
# Data: one row per goal, with its game's columns repeated
# ---------------------------------------------------------------------------

goals = run_query(
    """
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
        scorers.first_name || ' ' || scorers.last_name as scorer,
        assist1.first_name || ' ' || assist1.last_name as assist1,
        assist2.first_name || ' ' || assist2.last_name as assist2,
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
    order by games.game_date, games.game_id, goals.period_number, goals.time_in_period
    """
)


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
    """Adds the columns used by the game details. Done once for every goal shown, not game by game."""
    goals = goals.assign(PERIOD_NUMBER=goals["PERIOD_NUMBER"].astype(int))  # Snowflake returns a small int type
    minutes_seconds = goals["TIME_IN_PERIOD"].str.split(":", expand=True).astype(int)
    is_home_goal = goals["SCORING_TEAM_ID"] == goals["HOME_TEAM_ID"]
    home_leads = goals["HOME_SCORE"] > goals["AWAY_SCORE"]
    away_leads = goals["AWAY_SCORE"] > goals["HOME_SCORE"]
    leading_team = goals["HOME_TEAM"].where(home_leads, goals["AWAY_TEAM"].where(away_leads, "TIED"))
    return goals.assign(
        ELAPSED=(goals["PERIOD_NUMBER"] - 1) * 1200 + minutes_seconds[0] * 60 + minutes_seconds[1],  # seconds into the game
        SCORING_TEAM_SIDE=is_home_goal.map({True: "HOME", False: "AWAY"}),
        SCORING_TEAM=goals["HOME_TEAM"].where(is_home_goal, goals["AWAY_TEAM"]),
        SCORING_TEAM_LOGO=goals["HOME_TEAM_LOGO"].where(is_home_goal, goals["AWAY_TEAM_LOGO"]),
        LEADING_TEAM_COLOR=leading_team.map(TEAM_COLORS).fillna(TIED_COLOR),  # timeline colour after the goal
        GOAL_TYPE=goal_situation(goals),
        GOAL_TIME=goals["PERIOD_NUMBER"].map(PERIOD_NAMES) + " period · " + goals["TIME_IN_PERIOD"],
        ASSISTS=goals[["ASSIST1", "ASSIST2"]].apply(lambda names: ", ".join(names.dropna()) or "Unassisted", axis=1),
        SCORE=goals["HOME_TEAM"] + " " + goals["HOME_SCORE"].astype(str)
            + " - " + goals["AWAY_SCORE"].astype(str) + " " + goals["AWAY_TEAM"],
    )


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

season_col, team_col, date_col = st.columns([2, 3, 2], vertical_alignment="bottom")

selected_season = season_picker(season_col, goals["SEASON"].unique())
season_goals = goals[goals["SEASON"] == selected_season]

teams = sorted(set(goals["HOME_TEAM"]) | set(goals["AWAY_TEAM"]))
selected_team = team_col.selectbox("Team", ["All teams"] + teams)
if selected_team != "All teams":
    season_goals = season_goals[(season_goals["HOME_TEAM"] == selected_team) | (season_goals["AWAY_TEAM"] == selected_team)]

available_dates = sorted(season_goals["GAME_DATE"].unique())
if not available_dates:
    st.info(f"No game for the {selected_team} in {display_season(selected_season)} yet.")
    st.stop()
selected_date = date_picker(date_col, available_dates, key=f"games_date_{selected_season}")


# ---------------------------------------------------------------------------
# Page: one card per game
# ---------------------------------------------------------------------------

shown_goals = prepare_goals(season_goals[season_goals["GAME_DATE"] <= selected_date])
goals_by_game = dict(tuple(shown_goals.groupby("GAME_ID")))
# One row per game, newest date first. A stable sort keeps the games of a day in their original order
shown_games = shown_goals.drop_duplicates(subset=["GAME_ID"]).sort_values("GAME_DATE", ascending=False, kind="stable")


def score_row(game):
    """Home team, logo, score, how the game ended (REG / OT / SO), score, logo, away team.
    The winner's score is in bold."""
    home_score, away_score = game["HOME_TEAM_FINAL_SCORE"], game["AWAY_TEAM_FINAL_SCORE"]
    home_won = home_score > away_score
    home_score = f"**{home_score}**" if home_won else str(home_score)
    away_score = str(away_score) if home_won else f"**{away_score}**"

    home_team_col, home_logo_col, home_score_col, end_col, away_score_col, away_logo_col, away_team_col = st.columns(
        7, vertical_alignment="center"
    )
    # width="stretch": by default text is only as wide as itself, so centring it would do nothing
    home_team_col.text(game["HOME_TEAM"], text_alignment="center", width="stretch")
    home_logo_col.container(horizontal_alignment="center").image(game["HOME_TEAM_LOGO"], width=SCORE_ROW_LOGO_WIDTH)
    home_score_col.markdown(home_score, text_alignment="center", width="stretch")
    end_col.text(game["LAST_PERIOD_TYPE"], text_alignment="center", width="stretch")
    away_score_col.markdown(away_score, text_alignment="center", width="stretch")
    away_logo_col.container(horizontal_alignment="center").image(game["AWAY_TEAM_LOGO"], width=SCORE_ROW_LOGO_WIDTH)
    away_team_col.text(game["AWAY_TEAM"], text_alignment="center", width="stretch")


def game_details(game, game_goals):
    if game["LAST_PERIOD_TYPE"] == "SO":
        overtime_length = 1200
    elif game["LAST_PERIOD_TYPE"] == "OT":
        # The OT ends with the winning goal
        overtime_length = game_goals.loc[game_goals["PERIOD_NUMBER"] == 4, "ELAPSED"].max() - 3600
    else:
        overtime_length = None

    st.markdown("#### Timeline")
    timeline_chart(game_goals, has_overtime=game["LAST_PERIOD_TYPE"] != "REG", overtime_length=overtime_length)

    points_col, goals_col = st.columns([2, 3], gap="large")
    with points_col:
        st.markdown("#### Points")
        points_chart(player_points(game_goals))
    with goals_col:
        st.markdown("#### Goals")
        goal_log(game_goals)


for date, day_games in shown_games.groupby("GAME_DATE", sort=False):
    st.subheader(date)
    for _, game in day_games.iterrows():
        with st.container(border=True, gap="small"):
            score_row(game)
            with st.expander("Show details"):
                game_details(game, goals_by_game[game["GAME_ID"]])

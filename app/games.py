"""Games page: every game up to the selected date, with its scorers and timeline."""

import streamlit as st
import pandas as pd
import altair as alt

from common import TEAM_COLORS, date_picker, display_season, run_query, season_picker

period_names = {1: "1st", 2: "2nd", 3: "3rd", 4: "OT"}
LOGO_WIDTH = 100

# Game timeline sizes, in pixels. Everything is placed from the middle of the chart, where the bar is,
# and computed from the logo size: change GOAL_LOGO_WIDTH and the rest follows.
BAR_HEIGHT = 20
GOAL_LOGO_WIDTH = 100
GOAL_LOGO_HEIGHT = GOAL_LOGO_WIDTH * 2 / 3  # the NHL logos are 3:2
GAP = 4  # between the bar, the logos and the period names
# Home logos this far above the middle, away logos this far below (centre of the logo)
GOAL_LOGO_OFFSET = BAR_HEIGHT / 2 + GAP + GOAL_LOGO_HEIGHT / 2
# Period names under the away logos
LABELS_OFFSET = GOAL_LOGO_OFFSET + GOAL_LOGO_HEIGHT / 2 + GAP + 6
# Tall enough for the labels at the bottom, and the same room at the top for the home logos
TIMELINE_HEIGHT = 2 * (LABELS_OFFSET + 8)

# The details expander sits inside the game's card: no border of its own, and a thin line
# above it, so it reads as the bottom of the card rather than a separate box
st.html("""<style>
[data-testid="stExpander"] details { border: none !important; border-top: 1px solid rgba(49, 51, 63, 0.1) !important; border-radius: 0 !important; }
[data-testid="stExpander"] summary { padding-left: 0 !important; }
/* No "fullscreen" button over the images (team logos, headshots) when hovering them */
[data-testid="stElementContainer"]:has([data-testid="stImage"]) [data-testid="stElementToolbar"] { display: none; }
/* Goal tooltips of the timeline: title (period and time), scorer headshot, then the details */
#vg-tooltip-element h2 { font-size: 14px; margin: 0 0 6px; text-align: center; }
#vg-tooltip-element img { display: block; width: 120px; height: 120px; margin: 0 auto 6px; border-radius: 50%; background: #f0f2f6; }
/* First row of the goal tooltip (the goal type): no label, the value as a pill centred under the photo.
   A table row can't be wider than its columns, so the row only keeps the space (height) and the pill
   is placed on its own, centred on the whole tooltip (left 50% + shift back by half its width) */
#vg-tooltip-element tr:first-child { height: 30px; }
#vg-tooltip-element tr:first-child td.key { display: none; }
#vg-tooltip-element tr:first-child td.value { position: absolute; left: 50%; transform: translateX(-50%); white-space: nowrap; padding: 2px 10px; border-radius: 999px; background: #e8eefc; color: #1f3b8f; font-weight: 600; font-size: 12px; }
</style>""")



games = run_query(
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
            goals.situation_code,
            goals.goal_type,
            goals.strength
        from nhl_analytics.marts.fct_games as games
        inner join nhl_analytics.marts.dim_teams as home_teams
            on games.home_team_id = home_teams.team_id
        inner join nhl_analytics.marts.dim_teams as away_teams
                on games.away_team_id = away_teams.team_id
        inner join nhl_analytics.marts.fct_goals as goals
            on games.game_id = goals.game_id
        inner join nhl_analytics.marts.dim_players scorers on goals.scoring_player_id = scorers.player_id
        left join nhl_analytics.marts.dim_players assist1 on goals.assist1_player_id = assist1.player_id
        left join nhl_analytics.marts.dim_players assist2 on goals.assist2_player_id = assist2.player_id
        """
    )



# ---------------------------------------------------------------------------
# Controls: season, team, date (same row as on the other pages)
# ---------------------------------------------------------------------------

season_col, team_col, date_col = st.columns([2, 3, 2], vertical_alignment="bottom")

selected_season = season_picker(season_col, games["SEASON"].unique())
season_rankings = games[games["SEASON"] == selected_season]

teams = sorted(set(games["HOME_TEAM"]) | set(games["AWAY_TEAM"]))
selected_team = team_col.selectbox("Team", ["All teams"] + teams)
if selected_team != "All teams":
    season_rankings = season_rankings[
        (season_rankings["HOME_TEAM"] == selected_team) | (season_rankings["AWAY_TEAM"] == selected_team)
    ]

available_dates = sorted(season_rankings["GAME_DATE"].unique())
if not available_dates:
    st.info(f"No game for the {selected_team} in {display_season(selected_season)} yet.")
    st.stop()
selected_date = date_picker(date_col, available_dates, key=f"games_date_{selected_season}")


TIED_COLOR = "#e6e6e6"  # timeline bar while the score is tied


HEADSHOT_SIZE = 50  # pixels, headshots at the end of the scorers' bars
SCORER_ROW_HEIGHT = HEADSHOT_SIZE + 10  # pixels per player: the bar and its headshot, with a small gap


def game_scorers(game_scorers):
    # Players by points (goals + assists), highest first; on a tie, the one with the most goals first.
    # Computed here as a list, because the headshot layer has no "amount" column to sort on
    # (it only has the total, see below)
    totals = (
        game_scorers
        .assign(goals=game_scorers["amount"].where(game_scorers["type"] == "Goals", 0))  # assists count 0 goals
        .groupby("player_name")[["amount", "goals"]].sum()
    )
    player_order = totals.sort_values(["amount", "goals"], ascending=False).index.tolist()

    bars = alt.Chart(game_scorers).mark_bar().encode(
        # One row per player, top to bottom, the bars going right
        y=alt.Y("player_name:N", title=None, sort=player_order),
        x=alt.X("amount:Q", title=None, axis=alt.Axis(format="d", tickMinStep=1)),
        # Team colour, the same as the timeline
        color=alt.Color(
            "team:N",
            scale=alt.Scale(domain=list(TEAM_COLORS), range=list(TEAM_COLORS.values())),
            legend=None,
        ),
        # Goals in full colour, assists lighter, so both parts of a bar can be told apart
        opacity=alt.Opacity(
            "type:N",
            scale=alt.Scale(domain=["Goals", "Assists"], range=[1, 0.45]),
            legend=None,
        ),
        # Goals first (left), then assists
        order=alt.Order("type:N", sort="descending"),
        tooltip=[
            alt.Tooltip("headshot_url:N", title="image"),
            alt.Tooltip("player_name:N", title="Player"),
            alt.Tooltip("type:N", title="Type"),
            alt.Tooltip("amount:Q", title="Amount"),
        ],
    )

    # The player's headshot at the end of their bar: one row per player with their total,
    # and the picture moved right by half its width so it sits after the bar instead of across its end
    headshots = alt.Chart(game_scorers).transform_aggregate(
        total="sum(amount)", groupby=["player_name", "headshot_url"]
    ).mark_image(
        width=HEADSHOT_SIZE, height=HEADSHOT_SIZE, xOffset=HEADSHOT_SIZE / 2 + 2
    ).encode(
        y=alt.Y("player_name:N", sort=player_order),
        x="total:Q",
        url="headshot_url:N",
        tooltip=[
            alt.Tooltip("headshot_url:N", title="image"),
            alt.Tooltip("player_name:N", title="Player"),
            alt.Tooltip("total:Q", title="Points"),
        ],
    )

    st.altair_chart(
        (bars + headshots).properties(
            # One row per player, so the chart grows with the number of scorers
            height=len(player_order) * SCORER_ROW_HEIGHT,
            # Room right of the plot for the headshot of the longest bar
            padding={"top": 5, "left": 5, "right": HEADSHOT_SIZE + 5, "bottom": 5},
        ),
        width="stretch",
    )


LOG_LOGO_WIDTH = 36  # pixels, scoring team's logo in the goal log
LOG_HEADSHOT_WIDTH = 44  # pixels, scorer's headshot in the goal log


# Goal by goal, grouped by period: scoring team's logo, scorer's headshot, scorer and assists,
# score after the goal (the scoring team's number in bold), time, and goal type as a badge
def game_log(game_goals):
    for period, period_goals in game_goals.sort_values("ELAPSED").groupby("PERIOD_NUMBER"):
        st.markdown(f"**{period_names.get(period, f'Period {period}')}" + (" period**" if period <= 3 else "**"))
        for _, goal in period_goals.iterrows():
            logo_col, headshot_col, names_col, score_col, time_col, type_col = st.columns(
                [0.6, 0.7, 4, 1.2, 1, 3], vertical_alignment="center", gap="small"
            )
            logo_col.image(goal["SCORING_TEAM_LOGO"], width=LOG_LOGO_WIDTH)
            headshot_col.image(goal["SCORER_HEADSHOT"], width=LOG_HEADSHOT_WIDTH)
            # Scorer in bold, assists under it in small grey text
            names_col.markdown(f"**{goal['SCORER']}**  \n:gray[<small>{goal['ASSISTS']}</small>]", unsafe_allow_html=True)
            home_score, away_score = goal["HOME_SCORE"], goal["AWAY_SCORE"]
            if goal["SCORING_TEAM_SIDE"] == "HOME":
                score_col.markdown(f"**{home_score}** - {away_score}")
            else:
                score_col.markdown(f"{home_score} - **{away_score}**")
            time_col.markdown(f":gray[{goal['TIME_IN_PERIOD']}]")
            type_col.badge(goal["GOAL_TYPE"], color="blue")



def game_timeline(game_goals, has_overtime, overtime_length=300):
    periods = pd.DataFrame({
        "PERIOD": ["1st", "2nd", "3rd"],
        "START": [0, 1200, 2400],
        "END": [1200, 2400, 3600],
    })

    if has_overtime:
            periods.loc[len(periods)] = ["OT", 3600, 3600 + overtime_length]
    
    game_length = int(periods["END"].max())
    

    pieces = pd.DataFrame({
        "START" : [0] + game_goals["ELAPSED"].tolist(),
        "END" : game_goals["ELAPSED"].tolist() + [game_length],
        "LEADING_TEAM_COLOR" : [TIED_COLOR] + game_goals["LEADING_TEAM_COLOR"].tolist()
    })

    
    x_scale = alt.Scale(domain=[0, game_length], nice=False)

    # Shootout: its goals aren't in fct_goals, so add one virtual "goal" for the winner at the end of OT
    game = game_goals.iloc[0]  # the game's columns are the same on every goal row
    if game["LAST_PERIOD_TYPE"] == "SO":
            home_won = game["HOME_TEAM_FINAL_SCORE"] > game["AWAY_TEAM_FINAL_SCORE"]
            shootout_goal = {
                "ELAPSED": game_length,
                "SCORING_TEAM_SIDE": "HOME" if home_won else "AWAY",
                "HOME_TEAM_LOGO": game["HOME_TEAM_LOGO"],
                "AWAY_TEAM_LOGO": game["AWAY_TEAM_LOGO"],
                "GOAL_TIME": "Shootout",
                "SCORER_HEADSHOT": game["HOME_TEAM_LOGO"] if home_won else game["AWAY_TEAM_LOGO"],
                "GOAL_TYPE": "🎯 Shootout winner",
                "SCORER": game["HOME_TEAM"] if home_won else game["AWAY_TEAM"],
                "ASSISTS": "—",
                "SCORE": f'{game["HOME_TEAM"]} {game["HOME_TEAM_FINAL_SCORE"]} - {game["AWAY_TEAM_FINAL_SCORE"]} {game["AWAY_TEAM"]}',
            }
            game_goals = pd.concat([game_goals, pd.DataFrame([shootout_goal])], ignore_index=True)

    # Tooltip of the goal logos. Streamlit's tooltips show one title, one image, then a table of
    # text values (no other pictures, no HTML): period and time as the title, the scorer's headshot,
    # then the goal type (styled as a pill by the CSS at the top: it must stay the first row), scorer,
    # assists and score
    goal_tooltip = [
        alt.Tooltip("GOAL_TIME:N", title="title"),
        alt.Tooltip("SCORER_HEADSHOT:N", title="image"),
        alt.Tooltip("GOAL_TYPE:N", title="Type"),  # first row of the table: the pill
        alt.Tooltip("SCORER:N", title="Goal"),
        alt.Tooltip("ASSISTS:N", title="Assists"),
        alt.Tooltip("SCORE:N", title="Score"),
    ]

    # Vertical positions in pixels from the middle of the chart (up is positive): with this scale,
    # 1 unit on y = 1 pixel, so every layer is placed exactly, whatever its mark type
    y_scale = alt.Scale(domain=[-TIMELINE_HEIGHT / 2, TIMELINE_HEIGHT / 2], nice=False)

    bar = alt.Chart(pieces).mark_bar().encode(
        x=alt.X("START:Q", scale=x_scale, axis=None),
        x2="END:Q",
        y=alt.YDatum(-BAR_HEIGHT / 2, scale=y_scale, axis=None),
        y2=alt.datum(BAR_HEIGHT / 2),
        color = alt.Color("LEADING_TEAM_COLOR:N", scale=None),
        tooltip=alt.value(None),  # no tooltip on the bar, only on the goals
    )

    # White lines between the periods, from the bottom to the top of the bar, so it looks cut into blocks
    splits_periods = alt.Chart(periods.iloc[1:]).mark_rule(color="black", strokeWidth=3).encode(
        x="START:Q",
        y=alt.datum(-BAR_HEIGHT*1.0001),
        y2=alt.datum(BAR_HEIGHT*1.0001),
        tooltip = alt.value(None)
    )

    splits_goals = alt.Chart(game_goals).mark_rule(color="white", strokeWidth=3).encode(
            x="ELAPSED:Q",
            y=alt.datum(-BAR_HEIGHT / 2),
            y2=alt.datum(BAR_HEIGHT / 2),
            tooltip=goal_tooltip
        )



    home_goals = alt.Chart(game_goals).transform_filter("datum.SCORING_TEAM_SIDE == 'HOME'").mark_image(
        width = GOAL_LOGO_WIDTH, height = GOAL_LOGO_HEIGHT).encode(
        x=alt.X("ELAPSED:Q", scale=x_scale),
        y=alt.datum(GOAL_LOGO_OFFSET),
        url = "HOME_TEAM_LOGO:N",
        tooltip=goal_tooltip,
    )

    away_goals = alt.Chart(game_goals).transform_filter("datum.SCORING_TEAM_SIDE == 'AWAY'").mark_image(
            width = GOAL_LOGO_WIDTH, height = GOAL_LOGO_HEIGHT).encode(
            x=alt.X("ELAPSED:Q", scale=x_scale),
            y=alt.datum(-GOAL_LOGO_OFFSET),
            url = "AWAY_TEAM_LOGO:N",
            tooltip=goal_tooltip,
        )


    # Period name under the middle of each block, below the away logos
    labels = alt.Chart(periods).transform_calculate(
        MIDDLE="(datum.START + datum.END) / 2"
    ).mark_text(fontSize=20, color="black").encode(
        x="MIDDLE:Q",
        y=alt.datum(-LABELS_OFFSET),
        text="PERIOD:N",
    )

    st.altair_chart(
        (bar + splits_periods + splits_goals + away_goals + home_goals + labels).properties(
            height=TIMELINE_HEIGHT,
            # Half a logo of room on each side, so a goal at the very start or end isn't cut off
            padding={"left": GOAL_LOGO_WIDTH / 2, "right": GOAL_LOGO_WIDTH / 2, "top": 0, "bottom": 0},
        ),
        width="stretch",
    )

# Goal type for the tooltip pill, e.g. "⚡ Power play · 5v4", from the scoring team's point of view.
# SITUATION_CODE has 4 digits: away goalie (1/0), away skaters, home skaters, home goalie (1/0)
def goal_situation(goal):
    code = goal['SITUATION_CODE']
    away_goalie, away_skaters, home_skaters, home_goalie = (int(digit) for digit in code)
    if goal['SCORING_TEAM_ID'] == goal['HOME_TEAM_ID']:
        own_skaters, own_goalie, opp_skaters, opp_goalie = home_skaters, home_goalie, away_skaters, away_goalie
    else:
        own_skaters, own_goalie, opp_skaters, opp_goalie = away_skaters, away_goalie, home_skaters, home_goalie

    if own_skaters + opp_skaters == 1:  # one shooter against the goalie (1010 / 0101)
        return "🎯 Penalty shot"
    if opp_goalie == 0:
        goal_type = "🥅 Empty net"
    elif own_goalie == 0:
        goal_type = "➕ Extra attacker"
    elif own_skaters > opp_skaters:
        goal_type = "⚡ Power play"
    elif own_skaters < opp_skaters:
        goal_type = "🛡️ Short-handed"
    else:
        goal_type = "🟰 Even strength"
    return f"{goal_type} · {own_skaters} on {opp_skaters}"

# Player points of one game: one row per player, type (Goals / Assists) and team, with the amount
def game_points(game_goals):
    involvements = pd.concat([
        pd.DataFrame({"player_name": game_goals["SCORER"], "headshot_url": game_goals["SCORER_HEADSHOT"], "type": "Goals", "team": game_goals["SCORING_TEAM"]}),
        pd.DataFrame({"player_name": game_goals["ASSIST1"], "headshot_url": game_goals["ASSIST1_HEADSHOT"], "type": "Assists", "team": game_goals["SCORING_TEAM"]}),
        pd.DataFrame({"player_name": game_goals["ASSIST2"], "headshot_url": game_goals["ASSIST2_HEADSHOT"], "type": "Assists", "team": game_goals["SCORING_TEAM"]}),
    ]).dropna(subset=["player_name"])  # unassisted goals have no ASSIST1 / ASSIST2
    return (
        involvements
        .groupby(["player_name", "headshot_url", "type", "team"], as_index=False)
        .size()
        .rename(columns={"size": "amount"})
    )


# Every column derived from the goals, computed once for all the goals shown (not game by game)
def prepare_goals(goals):
    goals = goals.assign(PERIOD_NUMBER=goals["PERIOD_NUMBER"].astype(int))  # small int type from Snowflake
    time_parts = goals["TIME_IN_PERIOD"].str.split(":", expand=True).astype(int)
    is_home_goal = goals["SCORING_TEAM_ID"] == goals["HOME_TEAM_ID"]
    home_leads = goals["HOME_SCORE"] > goals["AWAY_SCORE"]
    away_leads = goals["AWAY_SCORE"] > goals["HOME_SCORE"]
    leading_team = goals["HOME_TEAM"].where(home_leads, goals["AWAY_TEAM"].where(away_leads, "TIED"))
    return goals.assign(
        # Seconds since the start of the game
        ELAPSED=(goals["PERIOD_NUMBER"] - 1) * 1200 + time_parts[0] * 60 + time_parts[1],
        SCORING_TEAM_SIDE=is_home_goal.map({True: "HOME", False: "AWAY"}),
        SCORING_TEAM=goals["HOME_TEAM"].where(is_home_goal, goals["AWAY_TEAM"]),
        SCORING_TEAM_LOGO=goals["HOME_TEAM_LOGO"].where(is_home_goal, goals["AWAY_TEAM_LOGO"]),
        # Colour of the timeline bar after the goal: the leading team's colour, grey when tied
        LEADING_TEAM_COLOR=leading_team.map(TEAM_COLORS).fillna(TIED_COLOR),
        GOAL_TYPE=goals.apply(goal_situation, axis=1),
        # Tooltip and log texts
        GOAL_TIME=goals["PERIOD_NUMBER"].map(period_names) + " period · " + goals["TIME_IN_PERIOD"],
        ASSISTS=goals[["ASSIST1", "ASSIST2"]].apply(lambda names: ", ".join(names.dropna()) or "Unassisted", axis=1),
        SCORE=goals["HOME_TEAM"] + " " + goals["HOME_SCORE"].astype(str)
            + " - " + goals["AWAY_SCORE"].astype(str) + " " + goals["AWAY_TEAM"],
    )


# ---------------------------------------------------------------------------
# Page: one card per game, most recent date first
# ---------------------------------------------------------------------------

selected_goals = prepare_goals(season_rankings[season_rankings["GAME_DATE"] <= selected_date])
goals_by_game = dict(tuple(selected_goals.groupby("GAME_ID")))  # each game's goals, split once
# One row per game, most recent date first
selected_games = selected_goals.drop_duplicates(subset=["GAME_ID"]).sort_values("GAME_DATE", ascending=False, kind="stable")

for date, day_games in selected_games.groupby("GAME_DATE", sort=False):
    st.subheader(date)
    for index, game in day_games.iterrows():
        home_team = game["HOME_TEAM"]
        away_team = game["AWAY_TEAM"]
        home_team_logo = game["HOME_TEAM_LOGO"]
        away_team_logo = game["AWAY_TEAM_LOGO"]
        home_team_final_score = game["HOME_TEAM_FINAL_SCORE"]
        away_team_final_score = game["AWAY_TEAM_FINAL_SCORE"]
        last_period_type = game["LAST_PERIOD_TYPE"]

        if home_team_final_score > away_team_final_score:
            home_team_final_score_str = "**"+str(home_team_final_score)+"**"
            away_team_final_score_str = away_team_final_score
        else:
            home_team_final_score_str = home_team_final_score
            away_team_final_score_str = "**"+str(away_team_final_score)+"**"

        label = (
        "Show details"
        )
        

        
        # One card per game: the score row, and the details expander as its footer
        with st.container(border=True, gap="small"):
            home_team_col,home_team_logo_col, home_score_col, last_period_type_col, away_score_col, away_team_logo_col, away_team_col = st.columns([1,1,1,1,1,1,1], vertical_alignment="center")
            # width="stretch": by default st.text / st.markdown can be only as wide as their text,
            # and centring inside a box that size does nothing. Stretched, they centre in the column
            home_team_col.text(home_team, text_alignment="center", width="stretch")
            away_team_col.text(away_team, text_alignment="center", width="stretch")
            home_score_col.markdown(home_team_final_score_str, text_alignment="center", width="stretch")
            away_score_col.markdown(away_team_final_score_str, text_alignment="center", width="stretch")
            home_team_logo_col.container(horizontal_alignment="center").image(home_team_logo, width=LOGO_WIDTH)
            away_team_logo_col.container(horizontal_alignment="center").image(away_team_logo, width=LOGO_WIDTH)
            last_period_type_col.text(last_period_type, text_alignment="center", width="stretch")
            with st.expander(label):
                game_goals = goals_by_game[game["GAME_ID"]]
                if game["LAST_PERIOD_TYPE"] == 'SO':
                    ot_length = 1200
                elif game["LAST_PERIOD_TYPE"] == 'OT':
                    ot_length = game_goals[game_goals["PERIOD_NUMBER"] == 4]["ELAPSED"].max() - 3600
                else:
                    ot_length = None

                st.markdown("#### Timeline")
                game_timeline(game_goals,has_overtime=game["LAST_PERIOD_TYPE"] != "REG", overtime_length=ot_length)
                
                # Points and goal log side by side
                points_col, goals_col = st.columns([2, 3], gap="large")
                with points_col:
                    st.markdown("#### Points")
                    game_scorers(game_points(game_goals))
                with goals_col:
                    st.markdown("#### Goals")
                    game_log(game_goals)
                




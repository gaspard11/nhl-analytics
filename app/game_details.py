"""What the Games page shows when a game is opened: the score timeline, the players' points and
the goal log. Each function takes the goals of one game, as prepared by games.prepare_goals."""

import altair as alt
import pandas as pd
import streamlit as st

from common import TEAM_COLORS


PERIOD_NAMES = {1: "1st", 2: "2nd", 3: "3rd", 4: "OT"}
TIED_COLOR = "#e6e6e6"  # timeline bar while the score is tied


# ---------------------------------------------------------------------------
# Timeline: a bar over the length of the game in the leading team's colour, cut by period,
# with the scoring team's logo at each goal (home above the bar, away below)
# ---------------------------------------------------------------------------

# Sizes in pixels, all derived from the logo size so that changing it keeps everything in place
BAR_HEIGHT = 20
GOAL_LOGO_WIDTH = 100
GOAL_LOGO_HEIGHT = GOAL_LOGO_WIDTH * 2 / 3  # NHL logos are 3:2
GAP = 4  # between the bar, the logos and the period names
GOAL_LOGO_OFFSET = BAR_HEIGHT / 2 + GAP + GOAL_LOGO_HEIGHT / 2  # from the middle to a logo's centre
LABELS_OFFSET = GOAL_LOGO_OFFSET + GOAL_LOGO_HEIGHT / 2 + GAP + 6  # period names, under the away logos
TIMELINE_HEIGHT = 2 * (LABELS_OFFSET + 8)  # same room above the bar as below it


def shootout_goal(game, game_length):
    """Shootout goals aren't in fct_goals, so the winner gets one virtual goal at the end of OT,
    with only the columns the timeline uses."""
    home_won = game["HOME_TEAM_FINAL_SCORE"] > game["AWAY_TEAM_FINAL_SCORE"]
    return {
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


def timeline_chart(game_goals, has_overtime, overtime_length=300):
    periods = pd.DataFrame({
        "PERIOD": ["1st", "2nd", "3rd"],
        "START": [0, 1200, 2400],
        "END": [1200, 2400, 3600],
    })
    if has_overtime:
        periods.loc[len(periods)] = ["OT", 3600, 3600 + overtime_length]
    game_length = int(periods["END"].max())

    # One piece of bar between two goals, coloured by the team leading after the first one
    pieces = pd.DataFrame({
        "START": [0] + game_goals["ELAPSED"].tolist(),
        "END": game_goals["ELAPSED"].tolist() + [game_length],
        "LEADING_TEAM_COLOR": [TIED_COLOR] + game_goals["LEADING_TEAM_COLOR"].tolist(),
    })

    game = game_goals.iloc[0]  # the game's own columns are the same on every goal
    if game["LAST_PERIOD_TYPE"] == "SO":
        game_goals = pd.concat([game_goals, pd.DataFrame([shootout_goal(game, game_length)])], ignore_index=True)

    # Streamlit's tooltips show one title, one image, then a table of plain text. The goal type must
    # stay the first row: the CSS of the Games page turns that row into a pill
    goal_tooltip = [
        alt.Tooltip("GOAL_TIME:N", title="title"),
        alt.Tooltip("SCORER_HEADSHOT:N", title="image"),
        alt.Tooltip("GOAL_TYPE:N", title="Type"),
        alt.Tooltip("SCORER:N", title="Goal"),
        alt.Tooltip("ASSISTS:N", title="Assists"),
        alt.Tooltip("SCORE:N", title="Score"),
    ]

    x_scale = alt.Scale(domain=[0, game_length], nice=False)
    # Vertical positions in pixels from the middle of the chart (up is positive). With this scale one
    # unit is one pixel, so every layer is placed exactly whatever its mark type
    y_scale = alt.Scale(domain=[-TIMELINE_HEIGHT / 2, TIMELINE_HEIGHT / 2], nice=False)

    bar = alt.Chart(pieces).mark_bar().encode(
        x=alt.X("START:Q", scale=x_scale, axis=None),
        x2="END:Q",
        y=alt.YDatum(-BAR_HEIGHT / 2, scale=y_scale, axis=None),
        y2=alt.datum(BAR_HEIGHT / 2),
        color=alt.Color("LEADING_TEAM_COLOR:N", scale=None),
        tooltip=alt.value(None),  # Streamlit turns tooltips on for every mark by default
    )

    # Black lines between periods, taller than the bar
    period_splits = alt.Chart(periods.iloc[1:]).mark_rule(color="black", strokeWidth=3).encode(
        x="START:Q",
        y=alt.datum(-BAR_HEIGHT),
        y2=alt.datum(BAR_HEIGHT),
        tooltip=alt.value(None),
    )

    # White line at each goal, across the bar
    goal_splits = alt.Chart(game_goals).mark_rule(color="white", strokeWidth=3).encode(
        x="ELAPSED:Q",
        y=alt.datum(-BAR_HEIGHT / 2),
        y2=alt.datum(BAR_HEIGHT / 2),
        tooltip=goal_tooltip,
    )

    home_goals = alt.Chart(game_goals).transform_filter("datum.SCORING_TEAM_SIDE == 'HOME'").mark_image(
        width=GOAL_LOGO_WIDTH, height=GOAL_LOGO_HEIGHT,
    ).encode(
        x=alt.X("ELAPSED:Q", scale=x_scale),
        y=alt.datum(GOAL_LOGO_OFFSET),
        url="HOME_TEAM_LOGO:N",
        tooltip=goal_tooltip,
    )

    away_goals = alt.Chart(game_goals).transform_filter("datum.SCORING_TEAM_SIDE == 'AWAY'").mark_image(
        width=GOAL_LOGO_WIDTH, height=GOAL_LOGO_HEIGHT,
    ).encode(
        x=alt.X("ELAPSED:Q", scale=x_scale),
        y=alt.datum(-GOAL_LOGO_OFFSET),
        url="AWAY_TEAM_LOGO:N",
        tooltip=goal_tooltip,
    )

    period_labels = alt.Chart(periods).transform_calculate(
        MIDDLE="(datum.START + datum.END) / 2"
    ).mark_text(fontSize=20, color="black").encode(
        x="MIDDLE:Q",
        y=alt.datum(-LABELS_OFFSET),
        text="PERIOD:N",
    )

    st.altair_chart(
        (bar + period_splits + goal_splits + away_goals + home_goals + period_labels).properties(
            height=TIMELINE_HEIGHT,
            # Half a logo on each side, so a goal at the very start or end isn't cut off
            padding={"left": GOAL_LOGO_WIDTH / 2, "right": GOAL_LOGO_WIDTH / 2, "top": 0, "bottom": 0},
        ),
        width="stretch",
    )


# ---------------------------------------------------------------------------
# Points: one bar per player (goals, then assists in a lighter shade), headshot at the end
# ---------------------------------------------------------------------------

HEADSHOT_SIZE = 50  # pixels
POINTS_ROW_HEIGHT = HEADSHOT_SIZE + 10  # pixels per player


def player_points(game_goals):
    """One row per player, team and type (Goals / Assists), with the amount."""
    involvements = pd.concat([
        pd.DataFrame({"player_name": game_goals["SCORER"], "headshot_url": game_goals["SCORER_HEADSHOT"], "type": "Goals", "team": game_goals["SCORING_TEAM"]}),
        pd.DataFrame({"player_name": game_goals["ASSIST1"], "headshot_url": game_goals["ASSIST1_HEADSHOT"], "type": "Assists", "team": game_goals["SCORING_TEAM"]}),
        pd.DataFrame({"player_name": game_goals["ASSIST2"], "headshot_url": game_goals["ASSIST2_HEADSHOT"], "type": "Assists", "team": game_goals["SCORING_TEAM"]}),
    ]).dropna(subset=["player_name"])  # no row for the missing assists of a goal
    return (
        involvements
        .groupby(["player_name", "headshot_url", "type", "team"], as_index=False)
        .size()
        .rename(columns={"size": "amount"})
    )


def points_chart(points):
    # Most points first, then most goals. Sorted here as a list because the headshot layer only has
    # the total, not the amount per type, so Altair couldn't sort both layers the same way
    totals = (
        points
        .assign(goals=points["amount"].where(points["type"] == "Goals", 0))
        .groupby("player_name")[["amount", "goals"]].sum()
    )
    player_order = totals.sort_values(["amount", "goals"], ascending=False).index.tolist()

    bars = alt.Chart(points).mark_bar().encode(
        y=alt.Y("player_name:N", title=None, sort=player_order),
        x=alt.X("amount:Q", title=None, axis=alt.Axis(format="d", tickMinStep=1)),
        color=alt.Color(
            "team:N",
            scale=alt.Scale(domain=list(TEAM_COLORS), range=list(TEAM_COLORS.values())),
            legend=None,
        ),
        opacity=alt.Opacity("type:N", scale=alt.Scale(domain=["Goals", "Assists"], range=[1, 0.45]), legend=None),
        order=alt.Order("type:N", sort="descending"),  # goals first, then assists
        tooltip=[
            alt.Tooltip("headshot_url:N", title="image"),
            alt.Tooltip("player_name:N", title="Player"),
            alt.Tooltip("type:N", title="Type"),
            alt.Tooltip("amount:Q", title="Amount"),
        ],
    )

    # One headshot per player at the end of the bar, shifted by half its width to sit after it
    headshots = alt.Chart(points).transform_aggregate(
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
            height=len(player_order) * POINTS_ROW_HEIGHT,
            padding={"top": 5, "left": 5, "right": HEADSHOT_SIZE + 5, "bottom": 5},  # room for the last headshot
        ),
        width="stretch",
    )


# ---------------------------------------------------------------------------
# Goal log: goal by goal, grouped by period
# ---------------------------------------------------------------------------

LOG_LOGO_WIDTH = 36  # pixels
LOG_HEADSHOT_WIDTH = 44  # pixels


def goal_log(game_goals):
    for period, period_goals in game_goals.sort_values("ELAPSED").groupby("PERIOD_NUMBER"):
        st.markdown(f"**{PERIOD_NAMES.get(period, f'Period {period}')}" + (" period**" if period <= 3 else "**"))
        for _, goal in period_goals.iterrows():
            logo_col, headshot_col, names_col, score_col, time_col, type_col = st.columns(
                [0.6, 0.7, 4, 1.2, 1, 3], vertical_alignment="center", gap="small"
            )
            logo_col.image(goal["SCORING_TEAM_LOGO"], width=LOG_LOGO_WIDTH)
            headshot_col.image(goal["SCORER_HEADSHOT"], width=LOG_HEADSHOT_WIDTH)
            names_col.markdown(f"**{goal['SCORER']}**  \n:gray[<small>{goal['ASSISTS']}</small>]", unsafe_allow_html=True)
            # Score after the goal, the scoring team's number in bold
            home_score, away_score = goal["HOME_SCORE"], goal["AWAY_SCORE"]
            if goal["SCORING_TEAM_SIDE"] == "HOME":
                score_col.markdown(f"**{home_score}** - {away_score}")
            else:
                score_col.markdown(f"{home_score} - **{away_score}**")
            time_col.markdown(f":gray[{goal['TIME_IN_PERIOD']}]")
            type_col.badge(goal["GOAL_TYPE"], color="blue")

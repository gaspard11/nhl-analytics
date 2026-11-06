"""What the Games page shows when a game is opened: the score timeline, the players' points, the
goal log, the play-by-play log and the rosters. Each function takes the goals of one game, as
prepared by games.prepare_goals, except pbp_log which takes its events, as prepared by
games.prepare_events, and roster_log which takes its players."""

import altair as alt
import pandas as pd
import streamlit as st
import html
import json

from common import TIED_COLOR, game_colors


PERIOD_NAMES = {1: "1st", 2: "2nd", 3: "3rd", 4: "OT"}

# strength_situation and net_situation of fct_goals, shared by the goal log and the play-by-play log
STRENGTH_LABELS = {
    "PS": "🎯 Penalty shot",
    "PP": "⚡ Power play",
    "SH": "🛡️ Short-handed",
    "EV": "🟰 Even strength",
}
NET_LABELS = {"EN": "🥅 Empty net", "EA": "➕ Extra attacker"}


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


def timeline_chart(game, game_goals, has_overtime, overtime_length=300):
    periods = pd.DataFrame({
        "PERIOD": ["1st", "2nd", "3rd"],
        "START": [0, 1200, 2400],
        "END": [1200, 2400, 3600],
    })
    if has_overtime:
        periods.loc[len(periods)] = ["OT", 3600, 3600 + overtime_length]
    game_length = int(periods["END"].max())

    # One piece of bar per stretch of fct_games_leading_segments, coloured by the team leading
    home_color, away_color = game_colors(game["HOME_TEAM"], game["AWAY_TEAM"])
    pieces = pd.DataFrame(json.loads(game["LEADING_SEGMENTS"]))
    pieces["LEADING_TEAM_COLOR"] = pieces["STATE"].map(
        {"home_leads": home_color, "away_leads": away_color, "tied": TIED_COLOR}
    )
    # The stretches of a game going to a shootout stop at the end of the 3rd: the last one, tied,
    # goes on through the OT
    pieces.loc[pieces.index[-1], "END"] = game_length

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

# Sizes of the game stats chart, in pixels
STAT_ROW_HEIGHT = 44  # a line of text and its bar
STAT_BAR_HEIGHT = 10
STAT_LOGO_WIDTH = 48
STAT_LINE_OFFSET = 9  # from the middle of a row, up to the text and down to the bar


def stats_charts(stats, home_team, away_team, home_logo, away_logo):
    """The logo and name of each team, then one row per stat: a line with the home value on the left,
    the name of the stat in the middle and the away value on the right, above a bar split by each
    team's share of the stat (home on the left). Both teams at 0 are shown as an even split."""
    home_col, away_col = st.columns(2)
    home_side = home_col.container(horizontal=True, horizontal_alignment="left", vertical_alignment="center", gap="small")
    home_side.image(home_logo, width=STAT_LOGO_WIDTH)
    home_side.markdown(f"**{home_team}**", width="content")
    away_side = away_col.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small")
    away_side.markdown(f"**{away_team}**", width="content")
    away_side.image(away_logo, width=STAT_LOGO_WIDTH)

    bars, lines = [], []
    stat_names = ['Shots On Goal', 'Faceoffs', 'Power Play %', 'Penalty Minutes', 'Hits', 'Blocked Shots', 'Giveaways', 'Takeaways']
    in_game = stats['STAT_NAME'].unique()

    for stat in stat_names:
        home_row = stats.loc[(stats['STAT_NAME'] == stat) & (stats['TEAM_NAME'] == home_team), 'STAT_VALUE']
        away_row = stats.loc[(stats['STAT_NAME'] == stat) & (stats['TEAM_NAME'] == away_team), 'STAT_VALUE']
        home_stat = home_row.iloc[0] if not home_row.empty else 0
        away_stat = away_row.iloc[0] if not away_row.empty else 0
        total = home_stat + away_stat
        home_stat_rate = home_stat / total if total > 0 else 0.5
        if stat == 'Faceoffs':  # share won, then the count: 47% (27/57)
            home_label = f'{home_stat_rate:.0%} ({home_stat:.0f}/{total:.0f})'
            away_label = f'{1 - home_stat_rate:.0%} ({away_stat:.0f}/{total:.0f})'
        elif stat == 'Power Play %':
            home_pp_goals_row = stats.loc[(stats['STAT_NAME'] == 'Power Play Goals') & (stats['TEAM_NAME'] == home_team), 'STAT_VALUE']
            away_pp_goals_row = stats.loc[(stats['STAT_NAME'] == 'Power Play Goals') & (stats['TEAM_NAME'] == away_team), 'STAT_VALUE']
            home_pp_opp_row = stats.loc[(stats['STAT_NAME'] == 'Power Play Opportunities') & (stats['TEAM_NAME'] == home_team), 'STAT_VALUE']
            away_pp_opp_row = stats.loc[(stats['STAT_NAME'] == 'Power Play Opportunities') & (stats['TEAM_NAME'] == away_team), 'STAT_VALUE']
                        
            home_pp_goals = home_pp_goals_row.iloc[0] if not home_pp_goals_row.empty else 0
            away_pp_goals = away_pp_goals_row.iloc[0] if not away_pp_goals_row.empty else 0
            home_pp_opp = home_pp_opp_row.iloc[0] if not home_pp_opp_row.empty else 0
            away_pp_opp = away_pp_opp_row.iloc[0] if not away_pp_opp_row.empty else 0

            home_label = f'{home_stat:.0%} ({home_pp_goals:.0f}/{home_pp_opp:.0f})'
            away_label = f'{away_stat:.0%} ({away_pp_goals:.0f}/{away_pp_opp:.0f})'
        else:
            home_label, away_label = f'{home_stat:.0f}', f'{away_stat:.0f}'
        bars.append({'category': stat, 'part': home_team, 'side': 0, 'value': home_stat_rate})
        bars.append({'category': stat, 'part': away_team, 'side': 1, 'value': 1 - home_stat_rate})
        lines.append({'category': stat, 'home_label': home_label, 'away_label': away_label})

    y = alt.Y('category:N', sort=None, axis=None)
    bar = alt.Chart(pd.DataFrame(bars)).mark_bar(size=STAT_BAR_HEIGHT, yOffset=STAT_LINE_OFFSET).encode(
        x=alt.X('value:Q', stack='zero', scale=alt.Scale(domain=[0, 1], nice=False), axis=None),
        y=y,
        color=alt.Color(
            'part:N',
            scale=alt.Scale(domain=[home_team, away_team], range=list(game_colors(home_team, away_team))),
            legend=None,
        ),
        order=alt.Order('side:Q'),  # home on the left, under its value
        tooltip=alt.value(None),
    )

    # The three texts of the line above each bar, at the two ends of the bar and in its middle
    line = alt.Chart(pd.DataFrame(lines)).encode(y=y, tooltip=alt.value(None))
    home_values = line.mark_text(align='left', dy=-STAT_LINE_OFFSET, fontWeight='bold').encode(x=alt.datum(0), text='home_label:N')
    stat_titles = line.mark_text(align='center', dy=-STAT_LINE_OFFSET).encode(x=alt.datum(0.5), text='category:N')
    away_values = line.mark_text(align='right', dy=-STAT_LINE_OFFSET, fontWeight='bold').encode(x=alt.datum(1), text='away_label:N')

    st.altair_chart(
        (bar + home_values + stat_titles + away_values)
        .properties(height=len(lines) * STAT_ROW_HEIGHT)
        .configure_view(stroke=None),
        width="stretch",
    )


def points_chart(points, home_team, away_team):
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
            scale=alt.Scale(domain=[home_team, away_team], range=list(game_colors(home_team, away_team))),
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

LOG_LOGO_WIDTH = 44  # pixels
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


# ---------------------------------------------------------------------------
# Play-by-play log: every event, grouped by period. Drawn as one HTML block per game: a game has
# a few hundred events, too many for one row of Streamlit columns each. The CSS (pbp-* classes) is
# on the Games page
# ---------------------------------------------------------------------------

PBP_PERIOD_NAMES = {1: "1st period", 2: "2nd period", 3: "3rd period", 4: "Overtime", 5: "Shootout"}
PBP_LOG_HEIGHT = 600  # pixels, the log scrolls past that

# Label and colour of each event type the filter offers, in the filter's order
EVENT_TYPES = {
    "goal": ("Goal", "#21a35a"),
    "shot-on-goal": ("Shot", "#3b7dd8"),
    "missed-shot": ("Missed shot", "#8a94a6"),
    "blocked-shot": ("Blocked shot", "#8a94a6"),
    "failed-shot-attempt": ("Failed attempt", "#8a94a6"),  # shootout only
    "penalty": ("Penalty", "#d64545"),
    "delayed-penalty": ("Delayed penalty", "#d64545"),
    "hit": ("Hit", "#e07b28"),
    "faceoff": ("Faceoff", "#8e6bd6"),
    "giveaway": ("Giveaway", "#d6a21e"),
    "takeaway": ("Takeaway", "#1fa3a3"),
    "stoppage": ("Stoppage", "#8a94a6"),
}
# Shown whatever the filter, as a thin line rather than a row (period-start is the period's title)
STRUCTURE_EVENTS = {"period-start", "period-end", "game-end", "shootout-complete"}
ZONES = {"O": "Offensive zone", "D": "Defensive zone", "N": "Neutral zone"}


def text(value):
    """The value escaped for HTML, or None when it's missing (Snowflake nulls come as None or NaN)."""
    return html.escape(value) if isinstance(value, str) and value else None


def readable(code):
    """API codes like "wide-of-net" as "Wide of net"."""
    return code.replace("-", " ").capitalize() if isinstance(code, str) else None


def joined(*parts):
    return " · ".join(part for part in parts if part)


def image(url, css_class):
    """An <img>, or an empty box of the same size so the columns stay aligned."""
    return f'<img class="{css_class}" src="{html.escape(url)}">' if isinstance(url, str) else f'<span class="{css_class}"></span>'


def event_details(event):
    """The event's DETAILS JSON as a dict, empty when it has none."""
    return json.loads(event["DETAILS"]) if isinstance(event["DETAILS"], str) else {}


def event_text(event, details):
    """Main line (the event's player in bold) and grey second line of an event."""
    player_1, player_2, player_3 = text(event["PLAYER_1"]), text(event["PLAYER_2"]), text(event["PLAYER_3"])
    goalie = text(event["GOALIE"])
    shot_type = readable(details.get("shotType"))
    shot_type = shot_type and f"{shot_type} shot"
    zone = ZONES.get(event["ZONE_CODE"])

    match event["EVENT_TYPE"]:
        case "goal":
            assists = ", ".join(name for name in (player_2, player_3) if name)
            return f"<b>{player_1}</b>", joined(shot_type, f"Assists: {assists}" if assists else "Unassisted")
        case "shot-on-goal":
            return f"<b>{player_1}</b>", joined(shot_type, f"saved by {goalie}" if goalie else None)
        case "missed-shot" | "failed-shot-attempt":
            return f"<b>{player_1}</b>", joined(shot_type, readable(details.get("reason")))
        case "blocked-shot":  # player 1 is the blocker, player 2 the shooter
            return f"<b>{player_1}</b> blocks {player_2}", zone
        case "faceoff":
            return f"<b>{player_1}</b> wins against {player_2}", zone
        case "hit":
            return f"<b>{player_1}</b> hits {player_2}", zone
        case "giveaway" | "takeaway":
            return f"<b>{player_1}</b>", zone
        case "penalty":  # player 2 drew it, player 3 serves it (a bench minor has no player 1)
            duration = details.get("duration")
            return f"<b>{player_1 or 'Bench'}</b>", joined(
                f"{duration} min" if duration else None,
                readable(details.get("descKey")),
                f"drawn by {player_2}" if player_2 else None,
                f"served by {player_3}" if player_3 else None,
            )
        case "delayed-penalty":
            return "Delayed penalty call", None
        case _:
            return readable(event["EVENT_TYPE"]), None


def structure_line(event, details):
    """Thin centred line for the period ends, the end of the game and the whistles."""
    period = PBP_PERIOD_NAMES.get(event["PERIOD_NUMBER"], f"Period {event['PERIOD_NUMBER']}").lower()
    match event["EVENT_TYPE"]:
        case "period-end":
            label = f"End of {period}"
        case "game-end" | "shootout-complete":
            label = "End of the game"
        case _:  # stoppage
            label = joined("Whistle", readable(details.get("reason")), readable(details.get("secondaryReason")))
    return f'<div class="pbp-line"><span>{event["TIME_IN_PERIOD"]} · {label}</span></div>'


def goal_types(event):
    """Tags of a goal: its strength and its net, which can both apply, like a power play goal into an
    empty net. fct_games_events is from the game's side, so the scoring team is compared with the team
    on the power play and with the team that pulled its goalie."""
    if event["STRENGTH_SITUATION"] == "PS":
        return [STRENGTH_LABELS["PS"]]
    tags = []
    if event["STRENGTH_SITUATION"] == "PP":
        strength = "PP" if event["MAN_ADV_TEAM_ID"] == event["EVENT_TEAM_ID"] else "SH"
        tags.append(f"{STRENGTH_LABELS[strength]} · {event['STRENGTH_ADV_TEAM']}")
    if event["NET_SITUATION"] == "PULLED":
        tags.append(NET_LABELS["EA" if event["EMPTY_NET_TEAM_ID"] == event["EVENT_TEAM_ID"] else "EN"])
    return tags


def situation_tags(event):
    """Tags of a play other than a goal, with the logo of the team concerned. The skaters are only
    shown once when a team on the power play faces a pulled goalie."""
    if event["STRENGTH_SITUATION"] == "PS":
        return '<span class="pbp-tag">Penalty shot</span>'
    tags = ""
    skaters = f' · {event["STRENGTH_ADV_TEAM"]}'
    if event["STRENGTH_SITUATION"] == "PP":
        tags += f'<span class="pbp-tag">{image(event["MAN_ADV_LOGO"], "pbp-tag-logo")}Power play{skaters}</span>'
        skaters = ""
    if event["NET_SITUATION"] == "PULLED":
        tags += f'<span class="pbp-tag">{image(event["EMPTY_NET_LOGO"], "pbp-tag-logo")}Extra attacker{skaters}</span>'
    return tags


def event_row(event, details):
    """Time, team logo, player headshot, event pill and text, then the score and situation on the right."""
    label, color = EVENT_TYPES.get(event["EVENT_TYPE"], (readable(event["EVENT_TYPE"]), "#8a94a6"))
    main, sub = event_text(event, details)

    # Score after a goal, the scoring team's number in bold, then the goal type or the situation
    # when the teams aren't at even strength
    right = ""
    if event["EVENT_TYPE"] == "goal" and pd.notna(event["HOME_SCORE"]):
        home_score, away_score = int(event["HOME_SCORE"]), int(event["AWAY_SCORE"])
        right += (f"<b>{home_score}</b> - {away_score}" if event["EVENT_TEAM_SIDE"] == "HOME"
                  else f"{home_score} - <b>{away_score}</b>")
    goal_tags = goal_types(event) if event["EVENT_TYPE"] == "goal" else []
    if goal_tags:
        right += "".join(f'<span class="pbp-tag pbp-goal-tag">{tag}</span>' for tag in goal_tags)
    else:
        right += situation_tags(event)

    return (
        f'<div class="pbp-row{" pbp-goal" if event["EVENT_TYPE"] == "goal" else ""}">'
        f'<span class="pbp-time">{event["TIME_IN_PERIOD"]}</span>'
        f'{image(event["EVENT_TEAM_LOGO"], "pbp-logo")}'
        f'{image(event["PLAYER1_HEADSHOT"], "pbp-headshot")}'
        f'<div><span class="pbp-pill" style="color: {color}; background: {color}22">{label}</span>{main}'
        + (f'<div class="pbp-sub">{sub}</div>' if sub else "")
        + f'</div><div class="pbp-right">{right}</div></div>'
    )


def pbp_log(game_events):
    game = game_events.iloc[0]  # the game's own columns are the same on every event
    game_id = game["GAME_ID"]
    present_types = [event_type for event_type in EVENT_TYPES if event_type in set(game_events["EVENT_TYPE"])]
    teams = {"BOTH": "Both teams", "HOME": game["HOME_TEAM"], "AWAY": game["AWAY_TEAM"]}
    periods = sorted(game_events["PERIOD_NUMBER"].unique())

    type_col, team_col, period_col = st.columns([3, 2, 2], vertical_alignment="center", gap="small")
    selected_types = type_col.multiselect(
        "Event types", present_types, format_func=lambda event_type: EVENT_TYPES[event_type][0],
        placeholder="All events", key=f"pbp_types_{game_id}", label_visibility="collapsed",
    ) or present_types  # nothing picked: every event
    selected_team = team_col.selectbox(
        "Team", list(teams), format_func=teams.get, key=f"pbp_team_{game_id}", label_visibility="collapsed",
    )
    selected_period = period_col.selectbox(
        "Period", ["ALL"] + periods, key=f"pbp_period_{game_id}", label_visibility="collapsed",
        format_func=lambda period: "All periods" if period == "ALL" else PBP_PERIOD_NAMES.get(period, f"Period {period}"),
    )

    # The period ends stay whatever the event types and team picked (whistles have no team, so
    # they go when one team is picked)
    keep = game_events["EVENT_TYPE"].isin(selected_types)
    if selected_team != "BOTH":
        keep &= game_events["EVENT_TEAM_ID"].notna() & (game_events["EVENT_TEAM_SIDE"] == selected_team)
    keep |= game_events["EVENT_TYPE"].isin(STRUCTURE_EVENTS)
    if selected_period != "ALL":
        keep &= game_events["PERIOD_NUMBER"] == selected_period
    shown = game_events[keep]
    parts = []
    # Stable sort: the events of the same second keep the order of the query
    for period, period_events in shown.sort_values("ELAPSED", kind="stable").groupby("PERIOD_NUMBER"):
        if period_events["EVENT_TYPE"].isin(STRUCTURE_EVENTS).all():
            continue  # nothing left in this period after the filter
        parts.append(f'<div class="pbp-period">{PBP_PERIOD_NAMES.get(period, f"Period {period}")}</div>')
        for _, event in period_events.iterrows():
            if event["EVENT_TYPE"] == "period-start":
                continue
            details = event_details(event)
            if event["EVENT_TYPE"] in STRUCTURE_EVENTS or event["EVENT_TYPE"] == "stoppage":
                parts.append(structure_line(event, details))
            else:
                parts.append(event_row(event, details))

    with st.container(height=PBP_LOG_HEIGHT, border=False):
        st.html("".join(parts) or "<i>No event of these types.</i>")


# ---------------------------------------------------------------------------
# Rosters: the players who dressed for each team, by position. One HTML block like the
# play-by-play log, with the roster-* classes of the Games page
# ---------------------------------------------------------------------------

POSITION_GROUPS = {"Forwards": ["C", "L", "R"], "Defense": ["D"], "Goalies": ["G"]}
POSITION_NAMES = {"C": "C", "L": "LW", "R": "RW", "D": "D", "G": "G"}


def roster_team(team, logo, team_rosters):
    parts = [f'<div><div class="roster-team-name">{image(logo, "")}{html.escape(team)}</div>']
    for group, positions in POSITION_GROUPS.items():
        group_players = team_rosters[team_rosters["POSITION"].isin(positions)]
        if group_players.empty:
            continue
        parts.append(f'<div class="roster-group">{group}</div>')
        for _, player in group_players.sort_values("SWEATER_NUMBER").iterrows():
            number = f'#{int(player["SWEATER_NUMBER"])}' if pd.notna(player["SWEATER_NUMBER"]) else ""
            parts.append(
                f'<div class="roster-player">'
                f'<span class="roster-number">{number}</span>'
                f'{image(player["HEADSHOT_URL"], "pbp-headshot")}'
                f'<span>{text(player["PLAYER"]) or ""}</span>'
                f'<span class="roster-position">{POSITION_NAMES.get(player["POSITION"], "")}</span></div>'
            )
    return "".join(parts) + "</div>"


def roster_log(game, game_rosters):
    is_home = game_rosters["TEAM_ID"] == game["HOME_TEAM_ID"]
    st.html(
        '<div class="roster">'
        + roster_team(game["HOME_TEAM"], game["HOME_TEAM_LOGO"], game_rosters[is_home])
        + roster_team(game["AWAY_TEAM"], game["AWAY_TEAM_LOGO"], game_rosters[~is_home])
        + "</div>"
    )

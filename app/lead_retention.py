"""Lead retention page: how well the teams hold their leads, from the start of the season up to a chosen
date, as a chart of logos and a table. Two charts:
- Whole game: the share of the non-tied time spent leading against the share of games won. The 50%
  lines and the line where both shares are equal split the teams into six areas.
- After 2 periods: how often a team leads after 2 periods against how often it then wins. The league
  averages split the teams into four areas."""

import altair as alt
import pandas as pd
import streamlit as st

from common import date_picker, load_rankings, run_query, season_picker


FONT_SIZE = 14  # pixels, of everything but the menus: the size Streamlit uses for its labels and tables
LOGO_SIZE = 44  # pixels
BLOCK_HEIGHT = 620  # pixels, of the table and of the chart with its legend: all visible on a 1080p screen
LEGEND_HEIGHT = 40  # pixels
AXIS_MARGIN = 0.07  # share of the axis left on each side of the teams, so that their logos stay inside

# The explanations of the charts: tight, to leave room for the chart under them
st.html(f"""<style>
.st-key-logic_text p, .st-key-logic_text li {{ font-size: {FONT_SIZE}px; line-height: 1.35; margin: 0; padding: 0; }}
</style>""")

WHOLE_GAME = "Whole game"
AFTER_2_PERIODS = "After 2 periods"

WHOLE_GAME_TEXT = """
- **% lead** = time leading / (time leading + time trailing). Tied time and overtime don't count.
- **% wins** includes overtime and shootout wins.
- **Dashed lines** (50%): to the right, a team leads more than it trails. Above, it wins more than it loses.
- **Red line**: a team wins as often as it leads. Above, it wins more than its time in the lead suggests. Below, less.
"""
AFTER_2_PERIODS_TEXT = """
- Only the games a team was leading after 2 periods count.
- **% led** = those games / games played.
- **% kept** = those games won / those games. A loss in overtime or in a shootout counts as blown.
- **Dashed lines** (league averages): to the right, a team leads after 2 periods more often than average. Above, it holds on to those leads more often than average.
"""

AREA_COLORS = {
    "Killers": "#2E9E5B",
    "Leaky contenders": "#9BCB5F",
    "Collapsers": "#F28E2B",
    "Come-backers": "#4C8DD6",
    "Opportunists": "#5BBCD6",
    "Scrappers": "#B07CC6",
    "Sinkers": "#8C8C8C",
}

AREA_OPACITY = 0.3  # of the areas of the chart
AREA_TINT = "55"  # about the same strength, as a hex alpha, for the legend and the table

# Far outside any axis: the areas and the red line are cut at the edges of the plot
LOW, HIGH = -1, 2
# An area is filled between Y_RATE and Y_RATE_TOP, from its first row to its second
AREA_COLUMNS = ["AREA", "X_RATE", "Y_RATE", "Y_RATE_TOP"]
WHOLE_GAME_AREAS = pd.DataFrame(
    [
        ("Killers", 0.5, 0.5, HIGH), ("Killers", HIGH, HIGH, HIGH),
        ("Leaky contenders", 0.5, 0.5, 0.5), ("Leaky contenders", HIGH, 0.5, HIGH),
        ("Collapsers", 0.5, LOW, 0.5), ("Collapsers", HIGH, LOW, 0.5),
        ("Come-backers", LOW, 0.5, HIGH), ("Come-backers", 0.5, 0.5, HIGH),
        ("Scrappers", LOW, LOW, 0.5), ("Scrappers", 0.5, 0.5, 0.5),
        ("Sinkers", LOW, LOW, LOW), ("Sinkers", 0.5, LOW, 0.5),
    ],
    columns=AREA_COLUMNS,
)

# One row per game and team that led at some point: a team that never led in a game has no row. That
# time is also the time its opponent trailed
LEADING_TIME_SQL = """
    select
        games.season,
        games.game_date,
        teams.name as team,
        opponents.name as opponent,
        stats.stat_value::float as leading_time
    from fct_games_stats as stats
    inner join fct_games as games
        on stats.game_id = games.game_id
    inner join dim_teams as teams
        on stats.team_id = teams.team_id
    inner join dim_teams as opponents
        on opponents.team_id = iff(stats.team_id = games.home_team_id, games.away_team_id, games.home_team_id)
    where stats.stat_name = 'Leading time'
"""

# One row per game with a team leading after 2 periods, and whether it won. Each goal has the score
# just after it, so the last goal of the first two periods gives the score at the end of the 2nd. A
# game without a goal by then has no row: it was tied
AFTER_2_PERIODS_SQL = """
    with score_after_2 as (
        select
            game_id,
            home_score,
            away_score
        from fct_goals
        where period_number <= 2
        -- The total score breaks a tie if two goals have the same time
        qualify row_number() over (
            partition by game_id
            order by period_number desc, time_in_period desc, home_score + away_score desc
        ) = 1
    )

    select
        games.season,
        games.game_date,
        teams.name as team,
        iff(
            (score.home_score > score.away_score) = (games.home_team_score > games.away_team_score), 1, 0
        )::float as won
    from score_after_2 as score
    inner join fct_games as games
        on score.game_id = games.game_id
    inner join dim_teams as teams
        on teams.team_id = iff(score.home_score > score.away_score, games.home_team_id, games.away_team_id)
    where score.home_score <> score.away_score
"""


def up_to_selected_date(games):
    """The rows of the selected season, up to the selected date."""
    return games[(games["SEASON"] == selected_season) & (games["GAME_DATE"] <= selected_date)]


def hours_and_minutes(seconds):
    """5025 -> "1 h 24 min"."""
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours} h {minutes:02d} min"


def whole_game_area(lead_rate, win_rate):
    """Area of the chart a team is in, None while it has no % of lead. A team on a 50% line goes to the
    right of it or above it, a team on the red line away from the centre: a team that has won and led
    all along is a Killer, not a Leaky contender."""
    if pd.isna(lead_rate):
        return None
    if lead_rate >= 0.5:
        if win_rate < 0.5:
            return "Collapsers"
        return "Killers" if win_rate >= lead_rate else "Leaky contenders"
    if win_rate >= 0.5:
        return "Come-backers"
    return "Scrappers" if win_rate > lead_rate else "Sinkers"


def after_2_periods_area(led_rate, kept_rate, led_line, kept_line):
    """Area of the chart a team is in, None while it hasn't led after 2 periods. A team on a line goes
    to the right of it or above it."""
    if pd.isna(kept_rate):
        return None
    if led_rate >= led_line:
        return "Killers" if kept_rate >= kept_line else "Collapsers"
    return "Opportunists" if kept_rate >= kept_line else "Sinkers"


def after_2_periods_areas(led_line, kept_line):
    """The four areas around the league averages."""
    return pd.DataFrame(
        [
            ("Killers", led_line, kept_line, HIGH), ("Killers", HIGH, kept_line, HIGH),
            ("Collapsers", led_line, LOW, kept_line), ("Collapsers", HIGH, LOW, kept_line),
            ("Opportunists", LOW, kept_line, HIGH), ("Opportunists", led_line, kept_line, HIGH),
            ("Sinkers", LOW, LOW, kept_line), ("Sinkers", led_line, LOW, kept_line),
        ],
        columns=AREA_COLUMNS,
    )


def axis_domain(rates, line):
    """The teams and the line of this axis, with a margin on each side."""
    low, high = min(rates.min(), line), max(rates.max(), line)
    margin = (high - low) * AXIS_MARGIN
    return [low - margin, high + margin]


def area_legend(area_names):
    """The colours of the areas, spread over the width of the chart: a legend inside the chart can't be
    stretched."""
    items = "".join(
        '<span style="display: inline-flex; align-items: center; gap: 6px;">'
        f'<span style="width: 14px; height: 14px; border-radius: 3px; background: {AREA_COLORS[name]}{AREA_TINT};"></span>{name}</span>'
        for name in area_names
    )
    st.html(f'<div style="display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 12px; font-size: {FONT_SIZE}px;">{items}</div>')


def solidity_chart(teams, x_title, y_title, x_line, y_line, areas, tooltip, equal_rates_line=False):
    """One logo per team (X_RATE, Y_RATE) over the coloured areas, and the dashed lines that separate
    them. With equal_rates_line, the red line where both rates are equal. The axes follow the selected
    date, so that the teams stay spread out from the first weeks to the end of the season."""
    # In every layer, so that the areas and the red line don't stretch the axes
    x = alt.X(
        "X_RATE:Q", title=x_title, axis=alt.Axis(format=".0%"),
        scale=alt.Scale(domain=axis_domain(teams["X_RATE"], x_line), nice=False),
    )
    y = alt.Y(
        "Y_RATE:Q", title=y_title, axis=alt.Axis(format=".0%"),
        scale=alt.Scale(domain=axis_domain(teams["Y_RATE"], y_line), nice=False),
    )

    area_names = list(areas["AREA"].unique())
    layers = [
        alt.Chart(areas).mark_area(clip=True, opacity=AREA_OPACITY, tooltip=None).encode(
            x=x, y=y, y2="Y_RATE_TOP:Q",
            color=alt.Color(
                "AREA:N",
                scale=alt.Scale(domain=area_names, range=[AREA_COLORS[name] for name in area_names]),
                legend=None,  # see area_legend
            ),
        ),
    ]
    lines = alt.Chart(pd.DataFrame({"X_RATE": [x_line], "Y_RATE": [y_line]})).mark_rule(
        color="gray", strokeDash=[6, 4], tooltip=None,
    )
    layers += [lines.encode(x=x), lines.encode(y=y)]
    if equal_rates_line:
        layers.append(
            alt.Chart(pd.DataFrame({"X_RATE": [LOW, HIGH], "Y_RATE": [LOW, HIGH]})).mark_line(
                color="red", clip=True, tooltip=None,
            ).encode(x=x, y=y)
        )
    layers.append(
        alt.Chart(teams).mark_image(width=LOGO_SIZE, height=LOGO_SIZE).encode(x=x, y=y, url="LOGO_URL:N", tooltip=tooltip)
    )
    st.altair_chart(
        alt.layer(*layers).properties(height=BLOCK_HEIGHT - LEGEND_HEIGHT)
        .configure_axis(labelFontSize=FONT_SIZE, titleFontSize=FONT_SIZE),
        width="stretch",
    )
    area_legend(area_names)


def solidity_table(teams, column_config):
    """One row per team, best Y_RATE first, with its label in the colour of its area. The columns are
    the ones of column_config, in its order."""
    table = teams.sort_values("Y_RATE", ascending=False)[list(column_config)]
    st.dataframe(
        table.style.map(lambda area: f"background-color: {AREA_COLORS[area]}{AREA_TINT}" if area else "", subset=["AREA"]),
        hide_index=True,
        height=BLOCK_HEIGHT,
        width="stretch",
        column_config=column_config,
    )


def text_and_columns(text):
    """The explanation of the chart, then the columns of the chart and of the table, which needs its
    full width to show the labels."""
    st.container(key="logic_text").markdown(text)
    return st.columns([5, 6])


def whole_game_view(day_rankings):
    """The Whole game chart and table. The overtime counts for nothing here: the teams are tied all
    through it. A team that hasn't played, or has only been tied so far, has no % of lead: it is in the
    table, not on the chart."""
    leading_time = up_to_selected_date(run_query(LEADING_TIME_SQL))
    # 0: hasn't led or trailed in a game yet
    team_leading = day_rankings["TEAM"].map(leading_time.groupby("TEAM")["LEADING_TIME"].sum()).fillna(0)
    team_trailing = day_rankings["TEAM"].map(leading_time.groupby("OPPONENT")["LEADING_TIME"].sum()).fillna(0)

    teams = day_rankings.assign(
        X_RATE=team_leading / (team_leading + team_trailing),
        Y_RATE=day_rankings["TOTAL_WINS"] / day_rankings["GAMES_PLAYED"],
        # Numbers in the table, so that clicking a column sorts them properly
        LEADING_HOURS=team_leading / 3600,
        TRAILING_HOURS=team_trailing / 3600,
        LEADING_TIME_LABEL=team_leading.map(hours_and_minutes),
        TRAILING_TIME_LABEL=team_trailing.map(hours_and_minutes),
    )
    teams = teams.assign(AREA=[whole_game_area(*rates) for rates in zip(teams["X_RATE"], teams["Y_RATE"])])

    chart_col, table_col = text_and_columns(WHOLE_GAME_TEXT)
    with chart_col:
        solidity_chart(
            teams[teams["X_RATE"].notna()],
            "% of the non-tied time in the lead", "% of wins",
            0.5, 0.5,  # the league average: every game has a winner, every lead a team trailing
            WHOLE_GAME_AREAS,
            [
                alt.Tooltip("TEAM:N", title="Team"),
                alt.Tooltip("AREA:N", title="Label"),
                alt.Tooltip("Y_RATE:Q", title="% of wins", format=".1%"),
                alt.Tooltip("X_RATE:Q", title="% of the non-tied time in the lead", format=".1%"),
                alt.Tooltip("TOTAL_WINS:Q", title="Wins"),
                alt.Tooltip("LEADING_TIME_LABEL:N", title="Leading time"),
                alt.Tooltip("TRAILING_TIME_LABEL:N", title="Trailing time"),
                alt.Tooltip("GAMES_PLAYED:Q", title="Games played"),
            ],
            equal_rates_line=True,
        )
    with table_col:
        solidity_table(teams, {
            "TEAM": st.column_config.TextColumn("Team", width=160),
            "LOGO_URL": st.column_config.ImageColumn("Logo", width=50),
            "Y_RATE": st.column_config.NumberColumn("% wins", format="percent", width=70),
            "LEADING_HOURS": st.column_config.NumberColumn("Leading time", format="%.1f h", width=90),
            "TRAILING_HOURS": st.column_config.NumberColumn("Trailing time", format="%.1f h", width=90),
            "X_RATE": st.column_config.NumberColumn("% lead", format="percent", width=70),
            "AREA": st.column_config.TextColumn("Label", width=125),
        })


def after_2_periods_view(day_rankings):
    """The After 2 periods chart and table. A game lost in overtime or in a shootout counts as blown. A
    team that hasn't led after 2 periods yet has no % kept: it is in the table, not on the chart."""
    after_2 = up_to_selected_date(run_query(AFTER_2_PERIODS_SQL))
    games_led = day_rankings["TEAM"].map(after_2.groupby("TEAM").size()).fillna(0)
    games_won = day_rankings["TEAM"].map(after_2.groupby("TEAM")["WON"].sum()).fillna(0)

    teams = day_rankings.assign(
        X_RATE=games_led / day_rankings["GAMES_PLAYED"],
        Y_RATE=games_won / games_led,
        GAMES_LED=games_led,
        GAMES_WON=games_won,
        GAMES_BLOWN=games_led - games_won,
    )
    # The whole league rather than an average of the teams, whose games don't weigh the same
    led_line = games_led.sum() / day_rankings["GAMES_PLAYED"].sum()
    kept_line = games_won.sum() / games_led.sum()
    teams = teams.assign(
        AREA=[after_2_periods_area(*rates, led_line, kept_line) for rates in zip(teams["X_RATE"], teams["Y_RATE"])]
    )

    chart_col, table_col = text_and_columns(AFTER_2_PERIODS_TEXT)
    with chart_col:
        solidity_chart(
            teams[teams["Y_RATE"].notna()],
            "% of games leading after 2 periods", "% of these games won",
            led_line, kept_line,
            after_2_periods_areas(led_line, kept_line),
            [
                alt.Tooltip("TEAM:N", title="Team"),
                alt.Tooltip("AREA:N", title="Label"),
                alt.Tooltip("X_RATE:Q", title="% of games leading after 2 periods", format=".1%"),
                alt.Tooltip("Y_RATE:Q", title="% of these games won", format=".1%"),
                alt.Tooltip("GAMES_LED:Q", title="Games led after 2 periods"),
                alt.Tooltip("GAMES_WON:Q", title="Won"),
                alt.Tooltip("GAMES_BLOWN:Q", title="Blown"),
                alt.Tooltip("GAMES_PLAYED:Q", title="Games played"),
            ],
        )
    with table_col:
        solidity_table(teams, {
            "TEAM": st.column_config.TextColumn("Team", width=150),
            "LOGO_URL": st.column_config.ImageColumn("Logo", width=50),
            "X_RATE": st.column_config.NumberColumn("% led", format="percent", width=65),
            "GAMES_LED": st.column_config.NumberColumn("Games led", format="%d", width=85),
            "GAMES_WON": st.column_config.NumberColumn("Won", format="%d", width=60),
            "GAMES_BLOWN": st.column_config.NumberColumn("Blown", format="%d", width=60),
            "Y_RATE": st.column_config.NumberColumn("% kept", format="percent", width=65),
            "AREA": st.column_config.TextColumn("Label", width=125),
        })


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

rankings = load_rankings()

season_col, date_col, chart_picker_col = st.columns(3, vertical_alignment="bottom")

selected_season = season_picker(season_col, rankings["SEASON"].unique())
season_rankings = rankings[rankings["SEASON"] == selected_season]
# Not before the first game: no team has a rate yet
available_dates = sorted(season_rankings.loc[season_rankings["GAMES_PLAYED"] > 0, "RANKING_DATE"].unique())
selected_date = date_picker(date_col, available_dates, key=f"date_{selected_season}")
chart = chart_picker_col.segmented_control("Chart", [WHOLE_GAME, AFTER_2_PERIODS], default=WHOLE_GAME, required=True, width="stretch")


# ---------------------------------------------------------------------------
# Page: chart on the left, table on the right
# ---------------------------------------------------------------------------

day_rankings = season_rankings[season_rankings["RANKING_DATE"] == selected_date]
if chart == WHOLE_GAME:
    whole_game_view(day_rankings)
else:
    after_2_periods_view(day_rankings)

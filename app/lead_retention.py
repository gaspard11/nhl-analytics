"""Lead retention page: which teams turn their time in the lead into points, from the start of the season
up to a chosen date, as a chart of logos and a table. Minutes in the lead per game against points per
game: the league trend (red line) gives the points a team usually gets for its time in the lead, so a
team below it lets its leads slip. A toggle counts the time in the lead over the whole game, or in the
3rd period only."""

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

from common import date_picker, load_rankings, run_query, season_picker


FONT_SIZE = 14  # pixels, of everything but the menus: the size Streamlit uses for its labels and tables
LOGO_SIZE = 44  # pixels
BLOCK_HEIGHT = 620  # pixels, of the table and of the chart: both visible on a 1080p screen
AXIS_MARGIN = 0.07  # share of the axis left on each side of the teams, so that their logos stay inside

# The explanation of the chart: tight, to leave room for the chart under it
st.html(f"""<style>
.st-key-logic_text p, .st-key-logic_text li {{ font-size: {FONT_SIZE}px; line-height: 1.35; margin: 0; padding: 0; }}
.st-key-logic_text {{ margin-bottom: {FONT_SIZE * 1.35}px; }}
</style>""")

WHOLE_GAME = "Whole game"
THIRD_PERIOD = "3rd period"

# What X counts in each view: the column of LEADING_TIME_SQL and the axis title
VIEWS = {
    WHOLE_GAME: ("LEADING_TIME", "Minutes in the lead per game"),
    THIRD_PERIOD: ("LEADING_TIME_3RD", "Minutes in the lead in the 3rd per game"),
}

LOGIC_TEXT = """
The chart shows each team's average points per game against its average time in the lead per game, in
minutes. The red line is the league trend. A team above it gets more points than most teams with a
similar time in the lead. A team below it gets fewer: it struggles to turn its leads into wins. Switch
to the 3rd period to count only the time in the lead in the 3rd and bring out the teams that let a late
lead slip.
"""

# Far outside any axis: the red line is cut at the edges of the plot
LOW, HIGH = -100, 100

# One row per game and team that led at some point: a team that never led in a game has no row. Its
# time in the lead, in the whole game and in the 3rd only: each segment is cut to the 3rd period
# (2400 to 3600 s), and one entirely outside it counts for 0
LEADING_TIME_SQL = """
    select
        games.season,
        games.game_date,
        teams.name as team,
        sum(segments.duration_s)::float as leading_time,
        sum(greatest(0, least(segments.end_s, 3600) - greatest(segments.start_s, 2400)))::float as leading_time_3rd
    from fct_games_leading_segments as segments
    inner join fct_games as games
        on segments.game_id = games.game_id
    inner join dim_teams as teams
        on segments.leading_team_id = teams.team_id
    group by games.season, games.game_date, games.game_id, teams.name
"""


def hours_and_minutes(seconds):
    """5025 -> "1 h 24 min"."""
    hours, minutes = divmod(round(seconds / 60), 60)
    return f"{hours} h {minutes:02d} min"


def axis_domain(values, line=None):
    """The teams, and the line of this axis if any, with a margin on each side."""
    low, high = values.min(), values.max()
    if line is not None:
        low, high = min(low, line), max(high, line)
    margin = (high - low) * AXIS_MARGIN
    return [low - margin, high + margin]


def lead_chart(teams, trend, x_title):
    """One logo per team and the red line of the league trend. The axes follow the selected date, so
    that the teams stay spread out from the first weeks to the end of the season."""
    # In both layers, so that the red line doesn't stretch the axes
    x = alt.X(
        "X:Q", title=x_title,
        scale=alt.Scale(domain=axis_domain(teams["X"]), nice=False),
    )
    y = alt.Y(
        "Y:Q", title="Points per game", axis=alt.Axis(format=".2f"),
        scale=alt.Scale(domain=axis_domain(teams["Y"]), nice=False),
    )

    layers = [
        alt.Chart(pd.DataFrame({"X": [LOW, HIGH], "Y": [trend(LOW), trend(HIGH)]})).mark_line(
            color="red", clip=True, tooltip=None,
        ).encode(x=x, y=y),
        alt.Chart(teams).mark_image(width=LOGO_SIZE, height=LOGO_SIZE).encode(
            x=x, y=y, url="LOGO_URL:N",
            tooltip=[
                alt.Tooltip("TEAM:N", title="Team"),
                alt.Tooltip("Y:Q", title="Points per game", format=".2f"),
                alt.Tooltip("X:Q", title=x_title, format=".1f"),
                alt.Tooltip("POINTS:Q", title="Points"),
                alt.Tooltip("LEADING_TIME_LABEL:N", title="Leading time"),
                alt.Tooltip("GAMES_PLAYED:Q", title="Games played"),
            ],
        ),
    ]
    st.altair_chart(
        alt.layer(*layers).properties(height=BLOCK_HEIGHT)
        .configure_axis(labelFontSize=FONT_SIZE, titleFontSize=FONT_SIZE),
        width="stretch",
    )


def lead_table(teams):
    """One row per team, most points per game first."""
    column_config = {
        "TEAM": st.column_config.TextColumn("Team", width=160),
        "LOGO_URL": st.column_config.ImageColumn("Logo", width=50),
        "Y": st.column_config.NumberColumn("Pts / game", format="%.2f", width=80),
        "X": st.column_config.NumberColumn("Lead min / game", format="%.1f", width=110),
    }
    table = teams.sort_values("Y", ascending=False)[list(column_config)]
    st.dataframe(
        table,
        hide_index=True,
        height=BLOCK_HEIGHT,
        width="stretch",
        column_config=column_config,
    )


def lead_view(day_rankings, view):
    """The chart and the table of a view of VIEWS. A team that hasn't played yet has no rate: it is in
    the table, not on the chart, and doesn't count in the red line."""
    column, x_title = VIEWS[view]
    leading_time = run_query(LEADING_TIME_SQL)
    leading_time = leading_time[
        (leading_time["SEASON"] == selected_season) & (leading_time["GAME_DATE"] <= selected_date)
    ]
    # 0: hasn't led in a game yet
    team_leading = day_rankings["TEAM"].map(leading_time.groupby("TEAM")[column].sum()).fillna(0)
    games_played = day_rankings["GAMES_PLAYED"].where(day_rankings["GAMES_PLAYED"] > 0)

    teams = day_rankings.assign(
        X=team_leading / 60 / games_played,
        Y=day_rankings["POINTS"] / games_played,
        LEADING_TIME_LABEL=team_leading.map(hours_and_minutes),
    )
    played = teams[teams["X"].notna()]
    if played["X"].nunique() < 2:
        st.info("Not enough games yet to draw the league trend.")
        return

    # Straight line through the teams that have played: points per game = intercept + slope x minutes
    slope, intercept = np.polyfit(played["X"], played["Y"], 1)

    def trend(minutes):
        return intercept + slope * minutes
    st.container(key="logic_text").markdown(LOGIC_TEXT)
    # The table needs its full width to show the labels
    chart_col, table_col = st.columns([5, 6])
    with chart_col:
        lead_chart(teams[teams["X"].notna()], trend, x_title)
    with table_col:
        lead_table(teams)


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------

rankings = load_rankings()

season_col, date_col, view_col = st.columns(3, vertical_alignment="bottom")

selected_season = season_picker(season_col, rankings["SEASON"].unique())
season_rankings = rankings[rankings["SEASON"] == selected_season]
# Not before the first game: no team has a rate yet
available_dates = sorted(season_rankings.loc[season_rankings["GAMES_PLAYED"] > 0, "RANKING_DATE"].unique())
selected_date = date_picker(date_col, available_dates, key=f"date_{selected_season}")
selected_view = view_col.segmented_control("Time in the lead", list(VIEWS), default=WHOLE_GAME, required=True, width="stretch")


# ---------------------------------------------------------------------------
# Page: chart on the left, table on the right
# ---------------------------------------------------------------------------

lead_view(season_rankings[season_rankings["RANKING_DATE"] == selected_date], selected_view)

"""Evolution page: points above .500 of every team, game after game, up to the selected date."""

import altair as alt
import pandas as pd
import streamlit as st

from common import TEAM_COLORS, date_picker, group_picker, load_rankings, season_picker, view_picker


# Team pills (logo + abbreviation): the logos only get a max height, and the pill keeps the width
# of its text alone, so the abbreviation is cut to "…". A fixed logo size makes the pill fit both.
# (!important: so it wins over Streamlit's own image style)
st.html("""<style>
[data-variant="pills"] img { width: 1.5em !important; height: 1em !important; object-fit: contain; }
</style>""")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOGO_SIZE = 50  # pixels, for the logos at the end of the lines
# Tall enough that the chart reaches the bottom of a 1080p screen, under the controls
PLOT_HEIGHT = 650
PILLS_PER_ROW = 4  # team pills per row, so a division (8 teams) is two rows that fit the options column


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Teams shown on the chart, one small pill (logo + abbreviation) per team, highlighted when clicked,
# grouped by division. Returns the highlighted teams.
def team_picker(teams):
    teams = teams.drop_duplicates("TEAM").sort_values("TEAM")
    # No abbreviation column in dim_teams, but every logo URL has it: .../COL_light.svg -> COL
    teams = teams.assign(ABBREV=teams["LOGO_URL"].str.extract(r"/([A-Z]{3})_[^/]*$", expand=False))
    labels = {team.TEAM: f"![]({team.LOGO_URL}) {team.ABBREV}" for team in teams.itertuples()}

    # The highlighted teams are also kept in highlighted_teams, so they stay highlighted when the
    # conference / division filter hides their pills, and come back with them
    saved = st.session_state.setdefault("highlighted_teams", [])

    def clear():
        for key in st.session_state:
            if str(key).startswith("highlight_"):
                st.session_state[key] = []
        st.session_state["highlighted_teams"] = []

    st.button("Clear highlights", on_click=clear)
    highlighted = []
    for division in sorted(teams["DIVISION"].unique()):
        division_teams = teams.loc[teams["DIVISION"] == division, "TEAM"].tolist()
        rows = [division_teams[i:i + PILLS_PER_ROW] for i in range(0, len(division_teams), PILLS_PER_ROW)]
        for line, line_teams in enumerate(rows):
            key = f"highlight_{division}_{line}"
            # New widget (first run, or its division was hidden by the filter): start from the
            # highlighted teams. Through the session state, not default=..., so clear() can reset it
            if key not in st.session_state:
                st.session_state[key] = [team for team in line_teams if team in saved]
            highlighted += st.pills(
                division,
                options=line_teams,
                format_func=labels.get,
                selection_mode="multi",
                # Directly in a column, pills default to one squeezed row: the abbreviations get cut to "…"
                wrap=True,
                key=key,
                # Division name above the first row only
                label_visibility="visible" if line == 0 else "collapsed",
            )
    # Keep the highlighted teams whose pills are hidden by the filter
    hidden = [team for team in saved if team not in labels]
    st.session_state["highlighted_teams"] = highlighted + hidden
    return highlighted


# Evolution chart given a list of teams and their standing stats up to the selected date.
# x_max and y_domain cover the whole season, so the axes don't move when the date changes.
# Each line has its team's colour. The highlighted teams are drawn thicker and on top, the others faded.
def standing_evolution(teams, x_max, y_domain, highlighted=()):
    df_teams = pd.DataFrame(teams)
    df_teams['POINTS_ABOVE_AVERAGE'] = df_teams['POINTS'] - df_teams['GAMES_PLAYED']
    df_teams = df_teams[['TEAM','LOGO_URL','GAMES_PLAYED','POINTS_ABOVE_AVERAGE']].drop_duplicates()

    # All teams on the same point, e.g. "Boston Bruins, Florida Panthers"
    df_teams["TEAMS_AT_POINT"] = (
        df_teams
        .groupby(["GAMES_PLAYED", "POINTS_ABOVE_AVERAGE"])["TEAM"]
        .transform(lambda names: ", ".join(sorted(names)))
    )

    tooltip = [
        alt.Tooltip("TEAMS_AT_POINT:N", title="Teams"),
        alt.Tooltip("GAMES_PLAYED:Q", title="Games played"),
        alt.Tooltip("POINTS_ABOVE_AVERAGE:Q", title="Points above .500"),
    ]

    last_points = (
        df_teams
        .sort_values("GAMES_PLAYED")
        .groupby("TEAM")
        .tail(1)
    )

    # Whole numbers only on the axes: no ticks or labels at 0.5, 1.5, ...
    integer_axis = dict(format="d", tickMinStep=1)
    base = alt.Chart(df_teams).encode(
        x=alt.X("GAMES_PLAYED:Q", title="Games played",
                axis=alt.Axis(**integer_axis), scale=alt.Scale(domain=[0, x_max])),
        y=alt.Y("POINTS_ABOVE_AVERAGE:Q", title="Points above .500",
                axis=alt.Axis(**integer_axis), scale=alt.Scale(domain=y_domain)),
    )

    lines = base.mark_line().encode(
        # detail: still one line per team when several teams share a colour
        detail="TEAM:N",
        color=alt.Color(
            "TEAM:N",
            scale=alt.Scale(domain=list(TEAM_COLORS), range=list(TEAM_COLORS.values())),
            legend=None,  # the logos at the end of the lines say which team it is
        ),
    )

    logos = alt.Chart(last_points).mark_image(width=LOGO_SIZE, height=LOGO_SIZE).encode(
        x="GAMES_PLAYED:Q",
        y="POINTS_ABOVE_AVERAGE:Q",
        url="LOGO_URL:N",
        tooltip=tooltip,
    )

    if highlighted:
        is_highlighted = alt.FieldOneOfPredicate("TEAM", list(highlighted))
        # Every line faded, then the highlighted ones drawn again on top, thicker
        lines = (
            lines.encode(opacity=alt.value(0.15))
            + lines.transform_filter(is_highlighted).encode(strokeWidth=alt.value(3))
        )
        logos = logos.encode(opacity=alt.condition(is_highlighted, alt.value(1), alt.value(0.25)))

    # Invisible points, one per team per game: they carry the tooltip
    points = base.mark_circle(size=100, opacity=0).encode(tooltip=tooltip)

    st.altair_chart(
        (lines + logos + points).properties(height=PLOT_HEIGHT),
        width="stretch",
    )


# ---------------------------------------------------------------------------
# Controls: season, date, standings view, and the conference / division for those views
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
# Data for the selected date, and the selected conference / division
# ---------------------------------------------------------------------------

# Axes of the evolution chart cover the whole season (all teams), so they stay still when the date
# or the conference / division changes
x_max = int(season_rankings["GAMES_PLAYED"].max())
points_above_500 = season_rankings["POINTS"] - season_rankings["GAMES_PLAYED"]
y_domain = [int(points_above_500.min()), int(points_above_500.max())]

shown_rankings = season_rankings
if group_column:
    shown_rankings = shown_rankings[shown_rankings[group_column] == group]
rankings_selected_season_date = shown_rankings[shown_rankings["RANKING_DATE"] <= selected_date]


# ---------------------------------------------------------------------------
# Page: chart on the left; the teams to highlight on the right (only the teams on the chart)
# ---------------------------------------------------------------------------

chart_col, options_col = st.columns([3, 1])
with options_col:
    highlighted = team_picker(shown_rankings)

with chart_col:
    standing_evolution(rankings_selected_season_date, x_max, y_domain, highlighted)

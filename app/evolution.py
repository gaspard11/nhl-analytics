"""Evolution page: each team's points above .500, game after game, up to a chosen date."""

import altair as alt
import streamlit as st

from common import TEAM_COLORS, date_picker, group_picker, load_rankings, season_picker, view_picker


# Team pills (logo + abbreviation): Streamlit sizes a pill for its text only, so the logo pushed the
# abbreviation out and it was cut to "…". A fixed logo size makes the pill fit both.
st.html("""<style>
[data-variant="pills"] img { width: 1.5em !important; height: 1em !important; object-fit: contain; }
</style>""")

LOGO_SIZE = 50  # pixels, logos at the end of the lines
LOGO_SPACING = 40  # pixels between logos sharing a point, a bit less than a logo so they overlap slightly
PLOT_HEIGHT = 650  # pixels, reaches the bottom of a 1080p screen under the controls
PILLS_PER_ROW = 4  # a division (8 teams) is two rows, which fits the side column


# ---------------------------------------------------------------------------
# Team picker and chart
# ---------------------------------------------------------------------------

def team_picker(teams):
    """One pill (logo + abbreviation) per team on the chart, grouped by division.
    Returns the teams to highlight."""
    teams = teams.drop_duplicates("TEAM").sort_values("TEAM")
    # dim_teams has no abbreviation, but every logo URL contains it: .../COL_light.svg -> COL
    teams = teams.assign(ABBREV=teams["LOGO_URL"].str.extract(r"/([A-Z]{3})_[^/]*$", expand=False))
    labels = {team.TEAM: f"![]({team.LOGO_URL}) {team.ABBREV}" for team in teams.itertuples()}

    # Also kept in highlighted_teams, so a team stays highlighted while the conference / division
    # filter hides its pill
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
            # A new widget (first run, or its division was hidden) starts from the saved teams. Set
            # through the session state rather than default=..., so that clear() can reset it
            if key not in st.session_state:
                st.session_state[key] = [team for team in line_teams if team in saved]
            highlighted += st.pills(
                division,
                options=line_teams,
                format_func=labels.get,
                selection_mode="multi",
                wrap=True,  # inside a column, pills default to one squeezed row
                key=key,
                label_visibility="visible" if line == 0 else "collapsed",  # division name once
            )
    hidden = [team for team in saved if team not in labels]
    st.session_state["highlighted_teams"] = highlighted + hidden
    return highlighted


def standing_evolution(teams, x_max, y_domain, highlighted=()):
    """One line per team in its colour, with its logo at the end. x_max and y_domain cover the
    whole season, so the axes don't move when the date or the group changes. Highlighted teams
    are drawn on top and thicker, the others faded."""
    # Points above .500: a team that wins half its games stays at 0
    df_teams = (
        teams.assign(POINTS_ABOVE_AVERAGE=teams["POINTS"] - teams["GAMES_PLAYED"])
        [["TEAM", "LOGO_URL", "GAMES_PLAYED", "POINTS_ABOVE_AVERAGE"]]
        .drop_duplicates()
    )

    # Several teams can share a point: the tooltip lists them all
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

    last_points = df_teams.sort_values("GAMES_PLAYED").groupby("TEAM").tail(1)
    # Teams with the same record end on the same point: number them within the point (highlighted
    # teams first, so they stay on the point itself) to place their logos side by side
    last_points = (
        last_points
        .assign(IS_HIGHLIGHTED=last_points["TEAM"].isin(highlighted))
        .sort_values(["IS_HIGHLIGHTED", "TEAM"], ascending=[False, True])
    )
    last_points["STACK_INDEX"] = last_points.groupby(["GAMES_PLAYED", "POINTS_ABOVE_AVERAGE"]).cumcount()
    max_stack_index = int(last_points["STACK_INDEX"].max()) if len(last_points) else 0

    integer_axis = dict(format="d", tickMinStep=1)  # whole numbers only on the axes
    base = alt.Chart(df_teams).encode(
        x=alt.X("GAMES_PLAYED:Q", title="Games played",
                axis=alt.Axis(**integer_axis), scale=alt.Scale(domain=[0, x_max])),
        y=alt.Y("POINTS_ABOVE_AVERAGE:Q", title="Points above .500",
                axis=alt.Axis(**integer_axis), scale=alt.Scale(domain=y_domain)),
    )

    lines = base.mark_line().encode(
        detail="TEAM:N",  # one line per team even when two teams share a colour
        color=alt.Color(
            "TEAM:N",
            scale=alt.Scale(domain=list(TEAM_COLORS), range=list(TEAM_COLORS.values())),
            legend=None,  # the logos identify the teams
        ),
    )

    is_highlighted = alt.FieldOneOfPredicate("TEAM", list(highlighted))

    def logo_layer(stack_index):
        """The logos with this index within their point, shifted right by that many logos.
        xOffset is the same for a whole layer, hence one layer per index."""
        layer = alt.Chart(last_points[last_points["STACK_INDEX"] == stack_index]).mark_image(
            width=LOGO_SIZE, height=LOGO_SIZE, xOffset=stack_index * LOGO_SPACING
        ).encode(
            x="GAMES_PLAYED:Q",
            y="POINTS_ABOVE_AVERAGE:Q",
            url="LOGO_URL:N",
            tooltip=tooltip,
        )
        if highlighted:
            layer = layer.encode(opacity=alt.condition(is_highlighted, alt.value(1), alt.value(0.25)))
        return layer

    # Last index drawn first, so the logo on the point itself is on top
    logos = alt.layer(*[logo_layer(index) for index in range(max_stack_index, -1, -1)])

    if highlighted:
        # Every line faded, then the highlighted ones drawn again on top
        lines = (
            lines.encode(opacity=alt.value(0.15))
            + lines.transform_filter(is_highlighted).encode(strokeWidth=alt.value(3))
        )

    # Invisible points, one per team per game, to carry the tooltip
    points = base.mark_circle(size=100, opacity=0).encode(tooltip=tooltip)

    st.altair_chart(
        (lines + logos + points).properties(
            height=PLOT_HEIGHT,
            # Room for the logos side by side after the last game, so they aren't cut
            padding={"left": 5, "top": 5, "bottom": 5, "right": LOGO_SIZE / 2 + max_stack_index * LOGO_SPACING},
        ),
        width="stretch",
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
# Data
# ---------------------------------------------------------------------------

# Axes over the whole season and all teams, so they stay still when the date or the group changes
x_max = int(season_rankings["GAMES_PLAYED"].max())
points_above_500 = season_rankings["POINTS"] - season_rankings["GAMES_PLAYED"]
y_domain = [int(points_above_500.min()), int(points_above_500.max())]

shown_rankings = season_rankings
if group_column:
    shown_rankings = shown_rankings[shown_rankings[group_column] == group]
rankings_until_date = shown_rankings[shown_rankings["RANKING_DATE"] <= selected_date]


# ---------------------------------------------------------------------------
# Page: chart on the left, teams to highlight on the right
# ---------------------------------------------------------------------------

chart_col, options_col = st.columns([3, 1])
with options_col:
    highlighted = team_picker(shown_rankings)

with chart_col:
    standing_evolution(rankings_until_date, x_max, y_domain, highlighted)

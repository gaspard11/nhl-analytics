"""Evolution page: each team's points above .500, game after game, up to a chosen date."""

import altair as alt
import streamlit as st
import pandas as pd
st.set_page_config(page_title="NHL", layout="wide")

from common import TEAM_COLORS_MAIN, date_picker, group_picker, load_rankings, season_picker, view_picker


# Team pills (logo + abbreviation): Streamlit sizes a pill for its text only, so the logo pushed the
# abbreviation out and it was cut to "…". A fixed logo size makes the pill fit both.
st.html("""<style>
[data-variant="pills"] img { width: 1.5em !important; height: 1em !important; object-fit: contain; }
</style>""")

LOGO_SIZE = 50  # pixels, logos at the end of the lines
LOGO_SPACING = 40  # pixels between logos sharing a point, a bit less than a logo so they overlap slightly
PLOT_HEIGHT = 650  # pixels, reaches the bottom of a 1080p screen under the controls
PILLS_PER_ROW = 4  # a division (8 teams) is two rows, which fits the side column
BAR_HEIGHT = 20
GOAL_LOGO_WIDTH = 100
GOAL_LOGO_HEIGHT = GOAL_LOGO_WIDTH * 2 / 3  # NHL logos are 3:2
GAP = 4  # between the bar, the logos and the period names

GOAL_LOGO_OFFSET = BAR_HEIGHT / 2 + GAP + GOAL_LOGO_HEIGHT / 2  # from the middle to a logo's centre

LABELS_OFFSET = GOAL_LOGO_OFFSET + GOAL_LOGO_HEIGHT / 2 + GAP + 6  # period names, under the away logos
TIMELINE_HEIGHT = 2 * (LABELS_OFFSET + 8)  # same room above the bar as below it
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


def rank_periods(teams, rank):
    """Periods during which each team held `rank`, one row per period."""
    evolution_team_rank = teams[teams["RANKING"] == rank].sort_values("RANKING_DATE").reset_index(drop=True)
    # A new streak starts each time the team at this rank changes
    streak_id = (evolution_team_rank["TEAM"] != evolution_team_rank["TEAM"].shift()).cumsum()

    periods = (
        evolution_team_rank.groupby(streak_id)
        .agg(START=("RANKING_DATE", "first"), TEAM=("TEAM", "first"))
        .reset_index(drop=True)
    )
    periods["START"] = pd.to_datetime(periods["START"])  # Snowflake DATEs can arrive as plain objects
    periods["END"] = periods["START"].shift(-1)
    # +1 day so the last period counts its last day (otherwise a 1-day period has length 0)
    periods["END"] = periods["END"].fillna(periods["START"].max() + pd.Timedelta(days=1))
    periods["TEAM_COLOR"] = periods["TEAM"].map(TEAM_COLORS_MAIN)
    periods["RANK"] = rank
    return periods


def bar_evolution(teams):
    """One row per rank, coloured by the team holding it; bar length = number of days."""
    ranks = sorted(teams["RANKING"].unique())  # 1..32, or only the ranks of the shown group
    pieces = pd.concat([rank_periods(teams, rank) for rank in ranks], ignore_index=True)

    bar = alt.Chart(pieces).mark_bar(strokeWidth=1).encode(
        # Explicit domain: a time scale otherwise rounds its ends to "nice" dates, leaving blank margins
        x=alt.X("START:T", axis=None, scale=alt.Scale(
            domain=[pieces["START"].min().isoformat(), pieces["END"].max().isoformat()], nice=False,
        )),
        x2="END:T",
        y=alt.Y("RANK:O", scale=alt.Scale(paddingInner=0, paddingOuter=0), axis=alt.Axis(title=None)),
        color=alt.Color("TEAM_COLOR:N", scale=None),
        stroke=alt.Stroke("TEAM_COLOR:N", scale=None),  # outline = fill, hides anti-aliasing seams
        tooltip=alt.value(None),  # Streamlit turns tooltips on for every mark by default
    )

    st.altair_chart(bar.properties(height=len(ranks) * BAR_HEIGHT), width="stretch")



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
shown_rankings = season_rankings
if group_column:
    shown_rankings = shown_rankings[shown_rankings[group_column] == group]
rankings_until_date = shown_rankings[shown_rankings["RANKING_DATE"] <= selected_date]


# ---------------------------------------------------------------------------
# Page: chart on the left, teams to highlight on the right
# ---------------------------------------------------------------------------

bar_evolution(rankings_until_date)
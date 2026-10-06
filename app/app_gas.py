import streamlit as st
import pandas as pd
import altair as alt

from common import get_connection
# import time  # play loop (disabled)

st.set_page_config(layout="wide") #So the charts take the whole width

# Team pills (logo + abbreviation): the logos only get a max height, and the pill keeps the width
# of its text alone, so the abbreviation is cut to "…". A fixed logo size makes the pill fit both.
# (!important: so it wins over Streamlit's own image style)
st.html("""<style>
[data-variant="pills"] img { width: 1.5em !important; height: 1em !important; object-fit: contain; }
</style>""")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Main colour of each team's logo, used for the lines of the evolution chart
TEAM_COLORS = {
    "Anaheim Ducks": "#F47A38",
    "Boston Bruins": "#FFB81C",
    "Buffalo Sabres": "#003087",
    "Calgary Flames": "#C8102E",
    "Carolina Hurricanes": "#CE1126",
    "Chicago Blackhawks": "#CF0A2C",
    "Colorado Avalanche": "#6F263D",
    "Columbus Blue Jackets": "#002654",
    "Dallas Stars": "#006847",
    "Detroit Red Wings": "#CE1126",
    "Edmonton Oilers": "#FF4C00",
    "Florida Panthers": "#C8102E",
    "Los Angeles Kings": "#111111",
    "Minnesota Wild": "#154734",
    "Montréal Canadiens": "#AF1E2D",
    "Nashville Predators": "#FFB81C",
    "New Jersey Devils": "#CE1126",
    "New York Islanders": "#00539B",
    "New York Rangers": "#0038A8",
    "Ottawa Senators": "#DA1A32",
    "Philadelphia Flyers": "#F74902",
    "Pittsburgh Penguins": "#FCB514",
    "San Jose Sharks": "#006D75",
    "Seattle Kraken": "#68A2B9",
    "St. Louis Blues": "#002F87",
    "Tampa Bay Lightning": "#002868",
    "Toronto Maple Leafs": "#00205B",
    "Utah Mammoth": "#6CACE4",
    "Vancouver Canucks": "#00205B",
    "Vegas Golden Knights": "#B4975A",
    "Washington Capitals": "#C8102E",
    "Winnipeg Jets": "#041E42",
}

# Columns of the standings table
COLUMNS = {
        "RANK": st.column_config.NumberColumn("Rank", width="small"),
        "LOGO_URL": st.column_config.ImageColumn("", width="small"),
        "TEAM": st.column_config.TextColumn("Team"),
        "GAMES_PLAYED": st.column_config.NumberColumn("GP", help="Games played"),
        "POINTS": st.column_config.NumberColumn("PTS", help="Points: win = 2, OT/shootout loss = 1"),
        "TOTAL_WINS": st.column_config.NumberColumn("W", help="Wins, including shootout wins"),
        "REGULATION_WINS": st.column_config.NumberColumn("RW", help="Regulation wins"),
        "REGULATION_OT_WINS": st.column_config.NumberColumn("ROW", help="Regulation + overtime wins"),
        "GOALS_FOR": st.column_config.NumberColumn("GF", help="Goals for"),
        "GOALS_AGAINST": st.column_config.NumberColumn("GA", help="Goals against"),
        "GOAL_DIFF": st.column_config.NumberColumn("DIFF", help="Goal differential", format="%+d")
    }

# Line colours of the evolution chart, for each "Colour by" option other than Team
GROUP_PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd"]  # divisions / conferences, in alphabetical order
PLAYOFF_COLORS = {
    "Top 3 of division": "#2e9e44",
    "Wild card": "#f28e2b",
    "Out of playoffs": "#bbbbbb",
}

LOGO_SIZE = 50  # pixels, for the logos at the end of the lines
# STRIP_LOGO_SIZE = 50  # pixels, for the hovered logos under the chart
# STRIP_ROWS = 2  # rows of hovered logos reserved under the chart (fixed, so the page doesn't jump while playing)
# Tall enough that the chart reaches the bottom of a 1080p screen, under the controls
PLOT_HEIGHT = 650

# PLAY_DELAY_SECONDS = 0.01  # pause between two dates while playing


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

# Snowflake connection
conn = get_connection()

# Getting the ranking history (cached 10 min, so the reruns of the play loop don't query Snowflake)
rankings = conn.query(
        """
        select
            rankings.ranking_date,
            rankings.season,
            rankings.ranking,
            teams.logo_url,
            teams.name as team,
            teams.conference_name as conference,
            teams.division_name as division,
            rankings.games_played,
            rankings.points,
            rankings.total_wins,
            rankings.regulation_wins,
            rankings.regulation_ot_wins,
            rankings.goals_for,
            rankings.goals_against,
            rankings.goal_diff,
            rankings.tie_rate::float as tie_rate
        from fct_league_rankings as rankings
        inner join dim_teams as teams
            on rankings.team_id = teams.team_id
        """,
        ttl=600,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Formatting seasons: 20252026 -> "2025 - 2026"
def display_season(season_int):
    season_str = str(season_int)
    return str(season_str[:4]) + " - " + str(season_str[4:])


# Standing table given a list of team and their standing stats at one date
def standings_table(teams):
        """One standings table; the rank is recomputed inside the group (league order, ties share a rank)."""
        table = teams.sort_values("RANKING").assign(RANK=lambda d: d["RANKING"].rank(method="min").astype(int))
        st.dataframe(
            table[list(COLUMNS)],
            column_config=COLUMNS,
            hide_index=True,
            width="stretch",
            height=(len(table) + 1) * 35 + 3,
        )


# Playoff spot of each team at one date (NHL format): the top 3 of each division,
# then the next 2 best teams of each conference (wild cards). RANKING is the league order.
def playoff_status(day_ranking):
    ordered = day_ranking.drop_duplicates("TEAM").sort_values("RANKING")
    top_3 = ordered.groupby("DIVISION").head(3)
    wild_cards = ordered.drop(top_3.index).groupby("CONFERENCE").head(2)
    status = pd.Series("Out of playoffs", index=ordered["TEAM"])
    status[top_3["TEAM"]] = "Top 3 of division"
    status[wild_cards["TEAM"]] = "Wild card"
    return status


# Column used to colour the lines, with its values and their colours.
# Divisions and conferences come from the whole season, so a group keeps its colour in every chart.
def line_colors(color_by, season_rankings):
    if color_by == "Team":
        return "TEAM", list(TEAM_COLORS), list(TEAM_COLORS.values())
    if color_by == "Playoffs":
        return "PLAYOFF_STATUS", list(PLAYOFF_COLORS), list(PLAYOFF_COLORS.values())
    column = color_by.upper()  # "DIVISION" or "CONFERENCE"
    groups = sorted(season_rankings[column].unique())
    return column, groups, GROUP_PALETTE[:len(groups)]


# Teams of the season grouped by division, one small pill (logo + abbreviation) per team,
# highlighted when clicked. Returns the selected teams.
def team_picker(season_rankings):
    teams = season_rankings.drop_duplicates("TEAM").sort_values("TEAM")
    # No abbreviation column in dim_teams, but every logo URL has it: .../COL_light.svg -> COL
    teams = teams.assign(ABBREV=teams["LOGO_URL"].str.extract(r"/([A-Z]{3})_[^/]*$", expand=False))
    labels = {team.TEAM: f"![]({team.LOGO_URL}) {team.ABBREV}" for team in teams.itertuples()}
    divisions = sorted(teams["DIVISION"].unique())

    def clear():
        for division in divisions:
            for line in (0, 1):
                st.session_state[f"highlight_{division}_{line}"] = []

    st.button("Clear highlights", on_click=clear)
    highlighted = []
    for division in divisions:
        # Each division split in two rows of 4, so it fits the column
        division_teams = teams.loc[teams["DIVISION"] == division, "TEAM"].tolist()
        half = (len(division_teams) + 1) // 2
        for line, line_teams in enumerate([division_teams[:half], division_teams[half:]]):
            highlighted += st.pills(
                division,
                options=line_teams,
                format_func=labels.get,
                selection_mode="multi",
                # Directly in a column, pills default to one squeezed row: the abbreviations get cut to "…"
                wrap=True,
                key=f"highlight_{division}_{line}",
                # Division name above the first row only
                label_visibility="visible" if line == 0 else "collapsed",
            )
    return highlighted


# Evolution chart given a list of teams and their standing stats up to the selected date.
# x_max and y_domain cover the whole season, so the axes don't move while playing.
# The lines are coloured by the color_field column, using color_domain -> color_range.
# The highlighted teams are drawn thicker and on top, the others faded.
def standing_evolution(teams, x_max, y_domain, color_field, color_domain, color_range, highlighted=()):
    df_teams = pd.DataFrame(teams)
    df_teams['POINTS_ABOVE_AVERAGE'] = df_teams['POINTS'] - df_teams['GAMES_PLAYED']
    columns = ['TEAM','LOGO_URL','GAMES_PLAYED','POINTS_ABOVE_AVERAGE']
    if color_field not in columns:
        columns.append(color_field)
    df_teams = df_teams[columns].drop_duplicates()

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
            f"{color_field}:N",
            scale=alt.Scale(domain=color_domain, range=color_range),
            # No legend per team (the logos say it), a legend at the top for the groups
            legend=None if color_field == "TEAM" else alt.Legend(title=None, orient="top"),
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

    # # Hovering a point (not the line between points) selects every team on it
    # # (same games played and same points above .500)
    # hover = alt.selection_point(
    #     fields=["GAMES_PLAYED", "POINTS_ABOVE_AVERAGE"],
    #     on="pointerover",
    #     clear="pointerout",
    #     empty=False,
    # )

    # Invisible points, one per team per game: they carry the tooltip
    points = base.mark_circle(size=100, opacity=0).encode(tooltip=tooltip)  # .add_params(hover)

    # # Logos of the hovered teams, in a row under the x-axis, only when several teams share the point.
    # # Mark x/y set with expressions are positions in pixels: `width`/`height` are the plot's size.
    # # The row wraps onto more lines when it's wider than the chart.
    # STRIP_TOP = "height + 45"  # just below the x-axis labels and title
    # logos_per_row = f"max(1, floor(width / {STRIP_LOGO_SIZE}))"
    # hovered_logos = (
    #     alt.Chart(df_teams)
    #     .transform_filter(hover)
    #     .transform_joinaggregate(LOGO_COUNT="count()")
    #     .transform_filter("datum.LOGO_COUNT > 1")
    #     .transform_window(LOGO_INDEX="row_number()", sort=[alt.SortField("TEAM")])
    #     .mark_image(
    #         width=STRIP_LOGO_SIZE,
    #         height=STRIP_LOGO_SIZE,
    #         x=alt.expr(f"((datum.LOGO_INDEX - 1) % {logos_per_row} + 0.5) * {STRIP_LOGO_SIZE}"),
    #         y=alt.expr(f"{STRIP_TOP} + (floor((datum.LOGO_INDEX - 1) / {logos_per_row}) + 0.5) * {STRIP_LOGO_SIZE}"),
    #     )
    #     .encode(url="LOGO_URL:N")
    # )

    # # Room under the chart for the hovered logos: axis labels and title, then STRIP_ROWS rows of logos
    # bottom_padding = 45 + STRIP_ROWS * STRIP_LOGO_SIZE + 10

    st.altair_chart(
        (lines + logos + points).properties(  # + hovered_logos
            height=PLOT_HEIGHT,
            # padding={"left": 5, "top": 5, "right": 5, "bottom": bottom_padding},
            # # Keep the plot PLOT_HEIGHT tall and add the padding around it, instead of squeezing the plot
            # autosize=alt.AutoSizeParams(type="fit-x", contains="padding"),
        ),
        width="stretch",
    )


# ---------------------------------------------------------------------------
# Controls: display, season, standings view
# ---------------------------------------------------------------------------

# def reset_replay():
#     """New season: stop playing and go back to its last date."""
#     st.session_state.playing = False
#     st.session_state.pop("date_i", None)


display = st.segmented_control("Display", ["Current", "Evolution"], default="Current") or "Current"

season_col, date_col, view_col = st.columns([2, 2, 3], vertical_alignment="bottom")

available_seasons = sorted(rankings["SEASON"].unique(), reverse = True)
selected_season = season_col.selectbox(
    label = "Select a Season",
    options = available_seasons,
    index=0,
    format_func=display_season,
    # on_change=reset_replay,
)

view = view_col.segmented_control("Standings", ["League", "Conference", "Division"], default="League") or "League"

season_rankings = rankings[rankings["SEASON"] == selected_season]
available_dates = sorted(season_rankings["RANKING_DATE"].unique())
n_dates = len(available_dates)


# # ---------------------------------------------------------------------------
# # Controls: date replay (◀ Play ▶ + slider)
# # The selected date is an index in available_dates, stored in st.session_state.date_i
# # so the buttons and the play loop can move it.
# # Everything that changes date_i must run before the slider is drawn
# # (Streamlit forbids changing a widget's value after it's drawn in the same run).
# # ---------------------------------------------------------------------------

# # First run, or new season (reset_replay removed date_i): start at the last date of the season
# if st.session_state.get("date_i", n_dates) >= n_dates:
#     st.session_state.date_i = n_dates - 1
# st.session_state.setdefault("playing", False)

# # While playing, every rerun moves one date forward (except the run right after pressing Play,
# # so the current date is shown first)
# if st.session_state.playing and not st.session_state.pop("just_started", False):
#     if st.session_state.date_i < n_dates - 1:
#         st.session_state.date_i += 1
#     else:
#         st.session_state.playing = False


# def step(delta):
#     st.session_state.playing = False
#     st.session_state.date_i = min(max(st.session_state.date_i + delta, 0), n_dates - 1)


# def toggle_play():
#     if not st.session_state.playing and st.session_state.date_i == n_dates - 1:
#         st.session_state.date_i = 0  # at the end of the season: restart from the first date
#     st.session_state.playing = not st.session_state.playing
#     st.session_state.just_started = st.session_state.playing


# def pause():
#     st.session_state.playing = False


# prev_col, play_col, next_col, slider_col = st.columns([1, 1.5, 1, 10], vertical_alignment="bottom")
# prev_col.button("◀", on_click=step, args=(-1,), help="Previous date")
# # Fixed key: without it the button's id comes from its label, which switches Play <-> Pause,
# # and a click on Pause while playing gets lost
# play_col.button("⏸ Pause" if st.session_state.playing else "▶ Play", key="play_button", on_click=toggle_play)
# next_col.button("▶", on_click=step, args=(1,), help="Next date")
# date_i = slider_col.select_slider(
#     "Date",
#     options=list(range(n_dates)),
#     format_func=lambda i: pd.Timestamp(available_dates[i]).strftime("%Y-%m-%d"),
#     key="date_i",
#     on_change=pause,
# )

# selected_date = available_dates[date_i]


# ---------------------------------------------------------------------------
# Controls: date filter
# The key includes the season, so changing season resets the date to its last day.
# ---------------------------------------------------------------------------

season_dates = pd.to_datetime(pd.Series(available_dates))
picked_date = date_col.date_input(
    "Date",
    value=season_dates.iloc[-1].date(),
    min_value=season_dates.iloc[0].date(),
    max_value=season_dates.iloc[-1].date(),
    key=f"date_{selected_season}",
)
# Day without a ranking (no game played that day): use the last ranking before it
date_i = season_dates.searchsorted(pd.Timestamp(picked_date), side="right") - 1
selected_date = available_dates[date_i]


# ---------------------------------------------------------------------------
# Data for the selected date
# ---------------------------------------------------------------------------

day_ranking = season_rankings[season_rankings["RANKING_DATE"] == selected_date]
# Playoff status at the selected date, the same for the whole line of a team
rankings_selected_season_date = season_rankings[season_rankings["RANKING_DATE"] <= selected_date].assign(
    PLAYOFF_STATUS=lambda d: d["TEAM"].map(playoff_status(day_ranking))
)

# Axes of the evolution chart cover the whole season, so they stay still while playing
x_max = int(season_rankings["GAMES_PLAYED"].max())
points_above_500 = season_rankings["POINTS"] - season_rankings["GAMES_PLAYED"]
y_domain = [int(points_above_500.min()), int(points_above_500.max())]


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

if display == 'Current':
    if view == "League":
        standings_table(day_ranking)
    else:
        group_column = "CONFERENCE" if view == "Conference" else "DIVISION"
        for group in sorted(day_ranking[group_column].unique()):
            st.subheader(group)
            standings_table(day_ranking[day_ranking[group_column] == group])
else:
    # Chart(s) on the left; colour options and the teams to highlight on the right
    chart_col, options_col = st.columns([3, 1])
    with options_col:
        color_by = st.radio("Colour by", ["Team", "Division", "Conference", "Playoffs"], key="color_by")
        highlighted = team_picker(season_rankings)
    colors = line_colors(color_by, season_rankings)

    with chart_col:
        if view == "League":
            standing_evolution(rankings_selected_season_date, x_max, y_domain, *colors, highlighted)
        else:
            group_column = "CONFERENCE" if view == "Conference" else "DIVISION"
            for group in sorted(rankings_selected_season_date[group_column].unique()):
                st.subheader(group)
                standing_evolution(
                    rankings_selected_season_date[rankings_selected_season_date[group_column] == group],
                    x_max,
                    y_domain,
                    *colors,
                    highlighted,
                )


# # ---------------------------------------------------------------------------
# # Play loop: must stay at the very end, once the whole page is drawn.
# # Wait, then rerun the script, which moves the slider one date forward (see the replay controls).
# # ---------------------------------------------------------------------------

# if st.session_state.playing:
#     time.sleep(PLAY_DELAY_SECONDS)
#     st.rerun()

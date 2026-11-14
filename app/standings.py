"""Standings page: the standings table on a chosen date, for the league, a conference or a division."""

import base64

import streamlit as st

from common import date_picker, group_picker, load_rankings, season_picker, view_picker


# Last 10 icons. Always 10 slots wide, so the icons line up from one team to the next even before
# the 10th game
WIN_COLOR = "#2E9E5B"
OT_COLOR = "#9E9E9E"
LOSS_COLOR = "#D64545"
ICON_STEP = 18  # pixels between the left of two icons, at the SVG's own size
# The table scales every image to the row's height (29 px inside a 35 px row). The SVG is made taller
# than the 16 px icons, with empty space above and below, so that once scaled the 10 icons fit in
# LAST_10_WIDTH: 10 x 18 x 29 / 32 = 163 px, for 174 px inside the cell's padding
ICON_SVG_HEIGHT = 32
LAST_10_WIDTH = 190  # pixels, of the L10 column

COLUMNS = {
    "RANK": st.column_config.NumberColumn("Rank", width="small"),
    "LOGO_URL": st.column_config.ImageColumn("", width="small"),
    "TEAM": st.column_config.TextColumn("Team"),
    "GAMES_PLAYED": st.column_config.NumberColumn("GP", help="Games played"),
    "TOTAL_WINS": st.column_config.NumberColumn("W", help="Wins, including shootout wins"),
    "LOSSES": st.column_config.NumberColumn("L", help="Losses in regulation"),
    "OT_LOSSES": st.column_config.NumberColumn("OT", help="Losses in overtime or in a shootout"),
    "POINTS": st.column_config.NumberColumn("PTS", help="Points: win = 2, OT/shootout loss = 1"),
    "POINTS_PCT": st.column_config.NumberColumn("P%", help="Points % = points / (2 x games played)"),
    "REGULATION_WINS": st.column_config.NumberColumn("RW", help="Regulation wins"),
    "REGULATION_OT_WINS": st.column_config.NumberColumn("ROW", help="Regulation + overtime wins"),
    "GOALS_FOR": st.column_config.NumberColumn("GF", help="Goals for"),
    "GOALS_AGAINST": st.column_config.NumberColumn("GA", help="Goals against"),
    "GOAL_DIFF": st.column_config.NumberColumn("DIFF", help="Goal differential"),
    "HOME_RECORD": st.column_config.TextColumn("Home", help="Record at home: W-L-OT"),
    "AWAY_RECORD": st.column_config.TextColumn("Away", help="Record away: W-L-OT"),
    "SHOOTOUT_RECORD": st.column_config.TextColumn("S/O", help="Record in shootouts: W-L"),
    "LAST_10_RECORD": st.column_config.TextColumn("L10", help="Last 10 games: W-L-OT"),
    "STREAK": st.column_config.TextColumn("STRK", help="Current streak: W = wins, L = regulation losses, OT = OT/shootout losses"),
    "LAST_10_ICONS": st.column_config.ImageColumn(
        "Last 10", width=LAST_10_WIDTH,
        help="Last 10 games, oldest first: check = win, grey dash = OT/shootout loss, red cross = regulation loss",
    ),
}


def last_10_icons(results):
    """The last 10 results ("W,L,OT,...", oldest first) as one small SVG image: a green check per
    win, a grey dash per overtime or shootout loss, a red cross per regulation loss. None before the
    first game, so the cell stays empty."""
    if not results:
        return None
    shapes = []
    for i, result in enumerate(results.split(",")):
        x = i * ICON_STEP  # left of this icon's 16 x 16 box
        if result == "W":
            shapes.append(f'<polyline points="{x + 3},8.5 {x + 6.5},12 {x + 13},4.5" stroke="{WIN_COLOR}" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
        elif result == "OT":
            shapes.append(f'<line x1="{x + 3.5}" y1="8" x2="{x + 12.5}" y2="8" stroke="{OT_COLOR}" stroke-width="2.4" stroke-linecap="round"/>')
        else:
            shapes.append(f'<path d="M{x + 4} 4 L{x + 12} 12 M{x + 12} 4 L{x + 4} 12" stroke="{LOSS_COLOR}" stroke-width="2.4" stroke-linecap="round"/>')
    width, top = 10 * ICON_STEP, (ICON_SVG_HEIGHT - 16) / 2  # icons centred vertically
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{ICON_SVG_HEIGHT}" viewBox="0 0 {width} {ICON_SVG_HEIGHT}">'
        f'<g transform="translate(0 {top})">{"".join(shapes)}</g></svg>'
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def diff_color(diff):
    """Text colour of the DIFF cell: green from 0 up, red when negative."""
    return f"color: {LOSS_COLOR if diff < 0 else WIN_COLOR}"


def standings_table(teams):
    """RANKING is the league order (tie breakers included). The rank shown is recomputed within the
    teams displayed, so a division starts at 1. Tied teams share a rank."""
    table = teams.sort_values("RANKING").assign(
        RANK=lambda d: d["RANKING"].rank(method="min").astype(int),
        LAST_10_ICONS=lambda d: d["LAST_10_RESULTS"].map(last_10_icons),
    )
    st.dataframe(
        # With a Styler, the table shows the Styler's text: the formats are set here, not in COLUMNS
        table[list(COLUMNS)].style
        .map(diff_color, subset=["GOAL_DIFF"])
        .format({"GOAL_DIFF": "{:+d}", "POINTS_PCT": "{:.3f}"}, na_rep=""),
        column_config=COLUMNS,
        hide_index=True,
        width="stretch",
        # Header + one 35px row per team, so the whole table shows without scrolling
        height=(len(table) + 1) * 35 + 3,
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
# Page
# ---------------------------------------------------------------------------

day_ranking = season_rankings[season_rankings["RANKING_DATE"] == selected_date]
if group_column:
    day_ranking = day_ranking[day_ranking[group_column] == group]

standings_table(day_ranking)

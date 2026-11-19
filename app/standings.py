"""Standings page: the standings table on a chosen date, for the league, a conference or a division.
Clicking a column header sorts the table by that column and highlights it (see sortable_table); the
Official NHL Rank, with every tie breaker, stays as it is."""

import base64

import streamlit as st
from st_aggrid import JsCode

from common import date_picker, group_picker, load_rankings, season_picker, view_picker
from sortable_table import NUMBER_COLUMN, TEXT_COLUMN, UNSORTABLE, image_column, sortable_table


ROW_HEIGHT = 35  # pixels, st.dataframe's default
IMAGE_HEIGHT = 29  # pixels, as st.dataframe draws an image in a 35px row
ICONS_HEIGHT = 27  # pixels, the last 10 icons, a little smaller so the table fits on a laptop

# Last 10 icons. Always 10 slots wide, so the icons line up from one team to the next even before
# the 10th game
WIN_COLOR = "#2E9E5B"
OT_COLOR = "#9E9E9E"
LOSS_COLOR = "#D64545"
ICON_STEP = 18  # pixels between the left of two icons, at the SVG's own size
# The image is drawn ICONS_HEIGHT tall. The SVG is made taller than the 16 px icons, with empty space
# above and below, so that once scaled the 10 icons fit in LAST_10_WIDTH: 10 x 18 x 27 / 32 = 152 px
ICON_SVG_HEIGHT = 32
LAST_10_WIDTH = 175  # pixels, of the Last 10 column

# DIFF as +12 / -3, in green from 0 up and in red below
DIFF_FORMAT = JsCode("function(params) { return params.value > 0 ? '+' + params.value : String(params.value); }")
DIFF_STYLE = JsCode(f"""
function(params) {{
    return {{color: params.value < 0 ? '{LOSS_COLOR}' : '{WIN_COLOR}'}};
}}
""")
POINTS_PCT_FORMAT = JsCode("function(params) { return params.value == null ? '' : params.value.toFixed(3); }")

# Records and streaks are text like 9-2-1 or W2: sorting them alphabetically would mean nothing
RECORD_COLUMN = {**UNSORTABLE, "flex": 1, "minWidth": 54}

# Minimum widths add up to about 1,430px, so the whole table fits on a laptop screen. A sorted
# header also shows an arrow: 56px for a 2-letter header, 64px for a longer one
SHORT = {**NUMBER_COLUMN, "minWidth": 56}
LONGER = {**NUMBER_COLUMN, "minWidth": 64}

COLUMN_DEFS = [
    # The official order: points, then every NHL tie breaker (computed in dbt). It doesn't change when
    # the table is sorted by another column; clicking it goes back to the official order
    {"field": "OFFICIAL_RANK", "headerName": "Official NHL Rank", "type": "numericColumn", "sort": "asc",
     "sortingOrder": ["asc", "desc"], "width": 150,  # room for the sort arrow
     "headerTooltip": "League rank after every NHL tie breaker, within the teams shown"},
    {"field": "LOGO_URL", "headerName": "", **image_column(50, IMAGE_HEIGHT)},
    {"field": "TEAM", "headerName": "Team", **TEXT_COLUMN, "minWidth": 140},
    {"field": "GAMES_PLAYED", "headerName": "GP", "headerTooltip": "Games played", **SHORT},
    {"field": "TOTAL_WINS", "headerName": "W", "headerTooltip": "Wins, including shootout wins", **SHORT},
    {"field": "LOSSES", "headerName": "L", "headerTooltip": "Losses in regulation", **SHORT},
    {"field": "OT_LOSSES", "headerName": "OT", "headerTooltip": "Losses in overtime or in a shootout", **SHORT},
    {"field": "POINTS", "headerName": "PTS", "headerTooltip": "Points: win = 2, OT/shootout loss = 1", **LONGER},
    {"field": "POINTS_PCT", "headerName": "P%", "headerTooltip": "Points % = points / (2 x games played)",
     "valueFormatter": POINTS_PCT_FORMAT, **LONGER},
    {"field": "REGULATION_WINS", "headerName": "RW", "headerTooltip": "Regulation wins", **SHORT},
    {"field": "REGULATION_OT_WINS", "headerName": "ROW", "headerTooltip": "Regulation + overtime wins", **LONGER},
    {"field": "GOALS_FOR", "headerName": "GF", "headerTooltip": "Goals for", **SHORT},
    {"field": "GOALS_AGAINST", "headerName": "GA", "headerTooltip": "Goals against", **SHORT},
    {"field": "GOAL_DIFF", "headerName": "DIFF", "headerTooltip": "Goal differential",
     "valueFormatter": DIFF_FORMAT, "cellStyle": DIFF_STYLE, **LONGER},
    {"field": "HOME_RECORD", "headerName": "Home", "headerTooltip": "Record at home: W-L-OT", **RECORD_COLUMN},
    {"field": "AWAY_RECORD", "headerName": "Away", "headerTooltip": "Record away: W-L-OT", **RECORD_COLUMN},
    {"field": "SHOOTOUT_RECORD", "headerName": "S/O", "headerTooltip": "Record in shootouts: W-L", **RECORD_COLUMN},
    {"field": "LAST_10_RECORD", "headerName": "L10", "headerTooltip": "Last 10 games: W-L-OT", **RECORD_COLUMN},
    {"field": "STREAK", "headerName": "STRK",
     "headerTooltip": "Current streak: W = wins, L = regulation losses, OT = OT/shootout losses", **RECORD_COLUMN},
    {"field": "LAST_10_ICONS", "headerName": "Last 10",
     "headerTooltip": "Last 10 games, oldest first: check = win, grey dash = OT/shootout loss, red cross = regulation loss",
     **image_column(LAST_10_WIDTH, ICONS_HEIGHT), "cellStyle": {"justifyContent": "flex-start"}},
]


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


def standings_table(teams, key):
    """RANKING is the league order (tie breakers included). The official rank shown is recomputed
    within the teams displayed, so a division starts at 1. Tied teams share a rank."""
    table = teams.sort_values("RANKING").assign(
        OFFICIAL_RANK=lambda d: d["RANKING"].rank(method="min").astype(int),
        LAST_10_ICONS=lambda d: d["LAST_10_RESULTS"].map(last_10_icons),
    )
    sortable_table(table, COLUMN_DEFS, ROW_HEIGHT, key=key)


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

# A new table for every date and group, so the data is never stale
standings_table(day_ranking, key=f"standings_{selected_season}_{selected_date}_{view}_{group}")

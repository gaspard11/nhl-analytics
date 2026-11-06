"""NHL app. Run with `streamlit run app.py` from app/.

Each page is its own file; the code they share (team colours, Snowflake access, season and
date controls) is in common.py.
"""

import streamlit as st

# Set once here for every page: wide layout, so the charts use the whole width
st.set_page_config(page_title="NHL", layout="wide")

# The page starts just under the menu, instead of Streamlit's large empty space at the top
st.html("""<style>
[data-testid="stMainBlockContainer"] { padding-top: 4rem; }
</style>""")

pages = [
    st.Page("games.py", title="Games", icon=":material/sports_hockey:", default=True),
    st.Page("standings.py", title="Standings", icon=":material/format_list_numbered:"),
    st.Page("evolution.py", title="Evolution", icon=":material/show_chart:"),
    st.Page("player_stats.py", title="Player stats", icon=":material/badge:"),
    st.Page("lead_retention.py", title="Lead retention", icon=":material/shield:"),
]
st.navigation(pages, position="top").run()

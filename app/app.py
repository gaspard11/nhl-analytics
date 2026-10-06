"""NHL app: run with `streamlit run app.py` from app/.

The navigation bar at the top switches between the three pages. Each page is its own file,
and the code they share (team colours, data, season / date controls) is in common.py.
"""

import streamlit as st

st.set_page_config(page_title="NHL", layout="wide")  # once for the whole app, so the charts take the whole width

pages = [
    st.Page("games.py", title="Games", icon=":material/sports_hockey:", default=True),
    st.Page("standings.py", title="Standings", icon=":material/format_list_numbered:"),
    st.Page("evolution.py", title="Evolution", icon=":material/show_chart:"),
    st.Page("player_stats.py", title="Player stats", icon=":material/badge:")
]
st.navigation(pages, position="top").run()

import colorsys
import time

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

from common import get_connection

st.set_page_config(page_title="NHL travel", layout="wide")  # must be the first Streamlit call

conn = get_connection()


def season_label(season):
    """20252026 -> '2025-2026'"""
    return f"{str(season)[:4]}-{str(season)[4:]}"


travel_tab, rankings_tab = st.tabs(["Travel", "Rankings"])

with travel_tab:

    def reset_replay():
        """New team or season selected: stop playing and go back to the end of the season."""
        st.session_state.playing = False
        st.session_state.pop("game_n", None)

    travel_seasons = conn.query("select distinct season from fct_team_travel order by season desc", ttl=600)
    SEASON = st.selectbox(
        "Season", travel_seasons["SEASON"], format_func=season_label, key="travel_season", on_change=reset_replay
    )

    df = conn.query(
        """
        select
            teams.name as team,
            teams.division_name as division,
            sum(travel.distance_km)::float as total_km
        from fct_team_travel as travel
        inner join dim_teams as teams
            on travel.team_id = teams.team_id
        where travel.season = ?
        group by teams.name, teams.division_name
        """,
        params=[SEASON],
        ttl=600,
    )

    st.title(f"NHL travel distance, {season_label(SEASON)}")

    # Fixed division -> color mapping (East first, then West), so a division always keeps its color
    DIVISION_COLORS = {
        "Atlantic": "#2a78d6",      # blue
        "Metropolitan": "#eb6834",  # orange
        "Central": "#1baf7a",       # aqua
        "Pacific": "#eda100",       # yellow
    }

    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("TOTAL_KM:Q", title="Total travel (km)"),
            y=alt.Y("TEAM:N", title=None, sort="-x"),
            color=alt.Color(
                "DIVISION:N",
                title="Division",
                scale=alt.Scale(domain=list(DIVISION_COLORS), range=list(DIVISION_COLORS.values())),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                "TEAM",
                alt.Tooltip("DIVISION:N", title="Division"),
                alt.Tooltip("TOTAL_KM:Q", format=",.0f", title="km"),
            ],
        )
    )

    st.altair_chart(chart, width="stretch")

    # --- Season replay ---

    # One row per team per game, home stands included, so the slider can step through all 82 games.
    games = conn.query(
        """
        select
            teams.name as team,
            to_char(travel.game_date, 'YYYY-MM-DD') as game_date,
            travel.is_home,
            opponents.name as opponent,
            travel.previous_arena_name,
            travel.arena_name,
            travel.previous_arena_longitude::float as from_lon,
            travel.previous_arena_latitude::float as from_lat,
            travel.arena_longitude::float as to_lon,
            travel.arena_latitude::float as to_lat,
            coalesce(travel.distance_km, 0)::float as distance_km
        from fct_team_travel as travel
        inner join dim_teams as teams
            on travel.team_id = teams.team_id
        inner join fct_games as games
            on travel.game_id = games.game_id
        inner join dim_teams as opponents
            on opponents.team_id = iff(travel.is_home, games.away_team_id, games.home_team_id)
        where travel.season = ?
        order by teams.name, travel.game_date, travel.game_id
        """,
        params=[SEASON],
        ttl=600,
    )

    arenas = conn.query(
        """
        select
            name as team,
            arena_name,
            arena_longitude::float as lon,
            arena_latitude::float as lat
        from dim_teams
        """,
        ttl=600,
    )

    st.header("Season replay")

    # Each road trip gets its own hue. From one road trip to the next, the hue turns by the "golden angle"
    # (137.5° on the color wheel): consecutive road trips are always far apart (blue -> red -> green -> ...)
    # and the hues never repeat exactly. The shade also cycles over 3 levels, so two road trips that land
    # on a similar hue (e.g. 1 and 9) still differ in lightness.
    FIRST_HUE = 210  # degrees: road trip 1 = blue
    GOLDEN_ANGLE = 137.5
    LIGHTNESS_LEVELS = (0.45, 0.62, 0.32)
    SATURATION = 0.8


    def road_trip_color(rt, n_road_trips):
        """Color of road trip number rt (1-based)."""
        hue = (FIRST_HUE + (rt - 1) * GOLDEN_ANGLE) % 360
        lightness = LIGHTNESS_LEVELS[(rt - 1) % len(LIGHTNESS_LEVELS)]
        r, g, b = colorsys.hls_to_rgb(hue / 360, lightness, SATURATION)
        return [round(r * 255), round(g * 255), round(b * 255), 255]


    def text_color_on(rgba):
        """Black or white, whichever reads better on this background."""
        r, g, b = rgba[:3]
        return "black" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "white"


    def to_hex(rgba):
        return "#{:02x}{:02x}{:02x}".format(*rgba[:3])


    HOME_STAND_GREY = [150, 150, 150, 255]
    NOT_PLAYED_GREY = "#dddddd"
    PLAY_DELAY_SECONDS = 0.4  # pause between two games while playing

    team = st.selectbox("Team", sorted(games["TEAM"].unique()), on_change=reset_replay)

    team_games = games[games["TEAM"] == team].reset_index(drop=True)
    n_games = len(team_games)

    # Road trip = a run of consecutive away games. Its legs are the trips to each of those games,
    # plus the trip back home after the last one.
    is_away = ~team_games["IS_HOME"].astype(bool)
    road_trip = (is_away & ~is_away.shift(fill_value=False)).cumsum().where(is_away)
    leg_road_trip = road_trip.fillna(road_trip.shift())  # the home game right after a road trip = the trip home
    n_road_trips = int(road_trip.max()) if is_away.any() else 0

    team_games = team_games.assign(
        GAME_NUMBER=lambda d: d.index + 1,
        CUMUL_KM=lambda d: d["DISTANCE_KM"].cumsum(),
        ROAD_TRIP=leg_road_trip,  # NaN = home stand (no travel)
        # The color is tied to the road trip number, so a trip keeps its color while the slider moves
        TRIP_COLOR=lambda d: [
            HOME_STAND_GREY if pd.isna(rt) else road_trip_color(int(rt), n_road_trips)
            for rt in d["ROAD_TRIP"]
        ],
        LABEL=lambda d: "Road trip " + d["ROAD_TRIP"].fillna(0).astype(int).astype(str) + "/" + str(n_road_trips)
        + " · Game " + d["GAME_NUMBER"].astype(str) + " · " + d["GAME_DATE"]
        + ": " + d["PREVIOUS_ARENA_NAME"].fillna("") + " → " + d["ARENA_NAME"]
        + " (" + d["DISTANCE_KM"].round().astype(int).astype(str) + " km)",
    )

    # The slider's value lives in st.session_state.game_n, so the buttons and the play loop can move it.
    # It must be changed before the slider is drawn (Streamlit forbids changing a widget's value after).
    if "game_n" not in st.session_state:
        st.session_state.game_n = n_games
    st.session_state.setdefault("playing", False)

    # While playing, every rerun moves one game forward (except the run right after pressing Play,
    # so the current game is shown first)
    if st.session_state.playing and not st.session_state.pop("just_started", False):
        if st.session_state.game_n < n_games:
            st.session_state.game_n += 1
        else:
            st.session_state.playing = False


    def step(delta):
        st.session_state.playing = False
        st.session_state.game_n = min(max(st.session_state.game_n + delta, 1), n_games)


    def toggle_play():
        if not st.session_state.playing and st.session_state.game_n == n_games:
            st.session_state.game_n = 1  # at the end of the season: restart from game 1
        st.session_state.playing = not st.session_state.playing
        st.session_state.just_started = st.session_state.playing


    prev_col, play_col, next_col, slider_col = st.columns([1, 1.5, 1, 10], vertical_alignment="bottom")
    prev_col.button("◀", on_click=step, args=(-1,), help="Previous game")
    play_col.button("⏸ Pause" if st.session_state.playing else "▶ Play", on_click=toggle_play)
    next_col.button("▶", on_click=step, args=(1,), help="Next game")
    game_n = slider_col.slider("Game", min_value=1, max_value=n_games, key="game_n", on_change=lambda: st.session_state.update(playing=False))

    played = team_games[team_games["GAME_NUMBER"] <= game_n]
    current = played.iloc[-1]
    current_road_trip = current["ROAD_TRIP"]  # NaN during a home stand

    # Legs of the current road trip in full color, earlier road trips faded; the leg to this game is thicker
    legs = played[played["DISTANCE_KM"] > 0].assign(
        COLOR=lambda d: [
            color[:3] + [255 if rt == current_road_trip else 90]
            for color, rt in zip(d["TRIP_COLOR"], d["ROAD_TRIP"])
        ],
        WIDTH=lambda d: [6 if n == game_n else 3 for n in d["GAME_NUMBER"]],
    )

    where = "vs" if current["IS_HOME"] else "@"
    st.markdown(f"**Game {game_n}/{n_games}** · {current['GAME_DATE']} · {where} {current['OPPONENT']} · {current['ARENA_NAME']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Distance so far", f"{current['CUMUL_KM']:,.0f} km")
    col2.metric("Road trips so far", int(played["ROAD_TRIP"].max()) if played["ROAD_TRIP"].notna().any() else 0)
    if pd.isna(current_road_trip):
        col3.metric("Now", "Home stand")
    else:
        road_trip_km = played.loc[played["ROAD_TRIP"] == current_road_trip, "DISTANCE_KM"].sum()
        col3.metric(f"Road trip {int(current_road_trip)}/{n_road_trips}", f"{road_trip_km:,.0f} km")

    arenas = arenas.assign(
        LABEL=lambda d: d["ARENA_NAME"] + " (" + d["TEAM"] + ")",
        # Home arena in purple (not part of the gradient) and bigger
        COLOR=lambda d: [[140, 60, 200] if t == team else [130, 130, 130] for t in d["TEAM"]],
        RADIUS=lambda d: [50000 if t == team else 25000 for t in d["TEAM"]],
    )

    legs_layer = pdk.Layer(
        "ArcLayer",
        data=legs,
        get_source_position=["FROM_LON", "FROM_LAT"],  # pydeck wants [longitude, latitude]
        get_target_position=["TO_LON", "TO_LAT"],
        get_source_color="COLOR",
        get_target_color="COLOR",
        get_width="WIDTH",
        pickable=True,
    )

    arenas_layer = pdk.Layer(
        "ScatterplotLayer",
        data=arenas,
        get_position=["LON", "LAT"],
        get_fill_color="COLOR",
        get_radius="RADIUS",  # meters
        pickable=True,
    )

    # Where the team is at the selected game: a big dot in the road trip's color, white outline
    position_layer = pdk.Layer(
        "ScatterplotLayer",
        data=played.tail(1).assign(COLOR=lambda d: d["TRIP_COLOR"]),
        get_position=["TO_LON", "TO_LAT"],
        get_fill_color="COLOR",
        get_radius=70000,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=2,
        pickable=True,
    )

    # Legend: one numbered box per road trip
    swatches = "".join(
        f'<div style="flex:1; text-align:center; padding:2px 0; border-radius:3px; '
        f'background:{to_hex(road_trip_color(rt, n_road_trips))}; color:{text_color_on(road_trip_color(rt, n_road_trips))};">{rt}</div>'
        for rt in range(1, n_road_trips + 1)
    )
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:8px; font-size:0.8rem;">
          <span>Road trips</span>
          <div style="flex:1; display:flex; gap:2px;">{swatches}</div>
          <span style="margin-left:16px; display:inline-block; width:24px; height:16px; border-radius:3px; background:{to_hex(HOME_STAND_GREY)};"></span>
          <span>Home stand</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    CHART_HEIGHT = 450
    map_col, chart_col = st.columns([3, 2])

    map_col.pydeck_chart(
        pdk.Deck(
            layers=[arenas_layer, legs_layer, position_layer],
            initial_view_state=pdk.ViewState(latitude=45, longitude=-95, zoom=2.5, pitch=30),
            tooltip={"text": "{LABEL}"},
        ),
        height=CHART_HEIGHT,
    )

    # Cumulative distance: one segment per game (previous game -> this game), colored like the map.
    # Steep colored parts = road trips, flat grey parts = home stands, light grey = not played yet.
    segments = team_games.assign(
        PREV_GAME=lambda d: d["GAME_NUMBER"] - 1,
        PREV_CUMUL_KM=lambda d: d["CUMUL_KM"].shift(fill_value=0),
        SEGMENT_COLOR=lambda d: [
            to_hex(color) if n <= game_n else NOT_PLAYED_GREY
            for color, n in zip(d["TRIP_COLOR"], d["GAME_NUMBER"])
        ],
    ).iloc[1:]  # game 1 has no previous game

    line = (
        alt.Chart(segments)
        .mark_rule(strokeWidth=3, strokeCap="round")
        .encode(
            x=alt.X("PREV_GAME:Q", title="Game", scale=alt.Scale(domain=[1, n_games])),
            x2="GAME_NUMBER:Q",
            y=alt.Y("PREV_CUMUL_KM:Q", title="Cumulative travel (km)"),
            y2="CUMUL_KM:Q",
            color=alt.Color("SEGMENT_COLOR:N", scale=None),  # use the hex colors as they are
            tooltip=[
                alt.Tooltip("GAME_NUMBER:Q", title="Game"),
                alt.Tooltip("GAME_DATE:N", title="Date"),
                alt.Tooltip("ROAD_TRIP:Q", title="Road trip"),
                alt.Tooltip("CUMUL_KM:Q", format=",.0f", title="Total km"),
            ],
        )
    )
    marker = (
        alt.Chart(team_games[team_games["GAME_NUMBER"] == game_n].assign(HEX=lambda d: d["TRIP_COLOR"].map(to_hex)))
        .mark_point(size=120, filled=True, opacity=1, stroke="white", strokeWidth=2)
        .encode(x="GAME_NUMBER:Q", y="CUMUL_KM:Q", color=alt.Color("HEX:N", scale=None))
    )
    chart_col.altair_chart((line + marker).properties(height=CHART_HEIGHT), width="stretch")

with rankings_tab:
    # Standings for every team on every ranking date (game days + day 0 of each season)
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
    rankings["RANKING_DATE"] = pd.to_datetime(rankings["RANKING_DATE"]).dt.date

    st.header("Rankings")

    season_col, prev_col, date_col, next_col, view_col = st.columns([2, 0.5, 2, 0.5, 3], vertical_alignment="bottom")

    rank_season = season_col.selectbox(
        "Season",
        sorted(rankings["SEASON"].unique(), reverse=True),
        format_func=season_label,
        key="rank_season",
        on_change=lambda: st.session_state.pop("rank_date", None),  # new season: start from its last day
    )
    season_rankings = rankings[rankings["SEASON"] == rank_season]
    dates = sorted(season_rankings["RANKING_DATE"].unique())  # game days (+ day 0) of that season

    # The date picker's value lives in st.session_state.rank_date, so the arrows can move it
    if "rank_date" not in st.session_state:
        st.session_state.rank_date = dates[-1]

    def latest_ranking_date():
        """Rankings only exist on game days: a day without games shows the latest standings before it."""
        return max(d for d in dates if d <= st.session_state.rank_date)

    def step_date(delta):
        """Jump to the previous (-1) or next (+1) game day."""
        i = dates.index(latest_ranking_date()) + delta
        st.session_state.rank_date = dates[min(max(i, 0), len(dates) - 1)]

    ranking_date = latest_ranking_date()
    prev_col.button("◀", on_click=step_date, args=(-1,), disabled=ranking_date == dates[0],
                    help="Previous game day", key="rank_prev")
    date_col.date_input("Date", min_value=dates[0], max_value=dates[-1], key="rank_date")
    next_col.button("▶", on_click=step_date, args=(1,), disabled=ranking_date == dates[-1],
                    help="Next game day", key="rank_next")
    view = view_col.segmented_control("Standings", ["League", "Conference", "Division"], default="League") or "League"

    day = season_rankings[season_rankings["RANKING_DATE"] == ranking_date]
    st.caption(f"Standings as of {ranking_date:%B %d, %Y} · season {season_label(rank_season)}")

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
        "GOAL_DIFF": st.column_config.NumberColumn("DIFF", help="Goal differential", format="%+d"),
        "TIE_RATE": st.column_config.NumberColumn(
            "H2H %", help="Head-to-head points % against the teams tied on points (tie-breaker)", format="%.3f"
        ),
    }

    def standings_table(teams):
        """One standings table; the rank is recomputed inside the group (league order, ties share a rank)."""
        table = teams.sort_values("RANKING").assign(RANK=lambda d: d["RANKING"].rank(method="min").astype(int))
        st.dataframe(
            table[list(COLUMNS)],
            column_config=COLUMNS,
            hide_index=True,
            width="stretch",
            height=(len(table) + 1) * 35 + 3,  # tall enough to show every team without scrolling
        )

    if view == "League":
        standings_table(day)
    else:
        group_column = "CONFERENCE" if view == "Conference" else "DIVISION"
        for group in sorted(day[group_column].unique()):
            st.subheader(group)
            standings_table(day[day[group_column] == group])

# Play loop: wait, then rerun the script, which moves the slider one game forward (see above)
if st.session_state.playing:
    time.sleep(PLAY_DELAY_SECONDS)
    st.rerun()

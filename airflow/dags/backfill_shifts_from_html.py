"""One-off full backfill of NHL_RAW.RAW.GAMES_SHIFTS_RAW from the NHL's HTML time-on-ice reports.

Why the HTML: the shift API (api.nhle.com/stats/rest/en/shiftcharts) sends bad data. Some shifts are
recorded twice for the same minutes (game 2025020512: both goalies 12 to 14 minutes too high once
summed), some games hold the shifts of teams that didn't play (2025020565), shift numbers restart in
overtime, and 50 games were never published (2026020154 to 2026020203). The HTML reports, TH (home
team) and TV (away team), one table per player with every shift, were clean on every game checked:
each player's total equals the official time on ice of the boxscore.

Loads every finished regular season game of SEASONS, one payload per game, in the same format as the
API: {"data": [...], "total": n}. Per shift (typeCode 517):
- playerId, firstName, lastName: matched on team + sweater number in the game's play-by-play
  rosterSpots (accented names re-encoded the way the shift API sent them, see as_shift_api)
- teamId, teamAbbrev, teamName: from the play-by-play (TH = home team, TV = away team)
- shiftNumber, period, startTime, endTime, duration: from the report, "MM:SS" as in the API
- null: id and eventNumber (API internal ids), hexValue (team colour, not in the report)
Not rebuilt: the goal rows of the API (typeCode 505), which are not shifts.

Each game is also checked against the boxscore: every player's total time on ice from the HTML is
compared with the official one, and the differences are logged (they never fail the run).

Games already in GAMES_SHIFTS_RAW are skipped, so a failed run can simply be triggered again.
Manual only (no schedule). One task per season, one season after the other.
"""

from datetime import datetime
import html
import json
import re
import time

import requests
from airflow.decorators import dag, task
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook


SNOWFLAKE_CONN_ID = "snowflake_conn_25"
TABLE = "NHL_RAW.RAW.GAMES_SHIFTS_RAW"
SEASONS = ["20252026", "20262027"]
FINAL = 7  # gameStateId of a finished game
PAUSE_SECONDS = 0.3  # between games, to stay gentle with the NHL sites

GAMES_URL = "https://api.nhle.com/stats/rest/en/game?cayenneExp=season={season}%20and%20gameType=2"
REPORT_URL = "https://www.nhl.com/scores/htmlreports/{season}/{side}{game_number}.HTM"
PBP_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
BOXSCORE_URL = "https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore"

# Player tables: a heading "<sweater> <LAST, FIRST>", then one row of 6 plain cells per shift:
# shift number, period, start "elapsed / remaining", end "elapsed / remaining", duration, event.
# The per-period summary tables under each player have 7 cells, so they don't match.
PLAYER_RE = re.compile(r'class="playerHeading[^"]*"[^>]*>([^<]*)</td>')
ROW_RE = re.compile(r"<tr[^>]*>\s*((?:<td[^>]*>[^<]*</td>\s*){6})</tr>")
CELL_RE = re.compile(r"<td[^>]*>([^<]*)</td>")


def get(url, attempts=3):
    """Response of url, or None when the page doesn't exist (404: a report not published)."""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt == attempts:
                raise
            time.sleep(5 * attempt)


def seconds(mm_ss):
    minutes, secs = mm_ss.strip().split(":")
    return int(minutes) * 60 + int(secs)


def mmss(value):
    """'1:22' -> '01:22', the API's format."""
    minutes, secs = value.strip().split(":")
    return f"{int(minutes):02d}:{int(secs):02d}"


def as_shift_api(name):
    """The shift API sent accented names double-encoded ("Stützle" arrived as "StÃ¼tzle"). The
    play-by-play sends them correctly, so they are encoded the same way as the API's, for the
    payloads to look the same whatever their source."""
    return name.encode("utf-8").decode("latin-1")


def parse_period(value):
    if value.isdigit():
        return int(value)
    if value == "OT":
        return 4
    raise ValueError(f"Unknown period in the HTML report: {value!r}")


def parse_report(text):
    """One (sweater, shift_number, period, start, end, duration) per shift of one TH/TV report."""
    shifts = []
    headings = list(PLAYER_RE.finditer(text))
    for i, heading in enumerate(headings):
        sweater = int(html.unescape(heading.group(1)).split()[0])
        end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        for row in ROW_RE.finditer(text[heading.end():end]):
            cells = [html.unescape(c).strip() for c in CELL_RE.findall(row.group(1))]
            if not cells[0].isdigit():  # column headings
                continue
            shifts.append((
                sweater,
                int(cells[0]),
                parse_period(cells[1]),
                mmss(cells[2].split("/")[0]),
                mmss(cells[3].split("/")[0]),
                mmss(cells[4]),
            ))
    return shifts


def build_payload(game_id):
    """The game's shifts in the shift API's format, or None when a report isn't published."""
    pbp = get(PBP_URL.format(game_id=game_id)).json()
    roster = {(r["teamId"], r["sweaterNumber"]): r for r in pbp["rosterSpots"]}
    season = f"{str(game_id)[:4]}{int(str(game_id)[:4]) + 1}"

    data = []
    for side, team in (("TH", pbp["homeTeam"]), ("TV", pbp["awayTeam"])):
        response = get(REPORT_URL.format(season=season, side=side, game_number=str(game_id)[4:]))
        if response is None:
            return None
        team_name = f"{team['placeName']['default']} {team['commonName']['default']}"
        for sweater, shift_number, period, start, end, duration in parse_report(response.text):
            player = roster.get((team["id"], sweater))
            if player is None:
                raise ValueError(f"Game {game_id}: no player #{sweater} for team {team['abbrev']} in the rosterSpots")
            data.append({
                "id": None,
                "detailCode": 0,
                "duration": duration,
                "endTime": end,
                "eventDescription": None,
                "eventDetails": None,
                "eventNumber": None,
                "firstName": as_shift_api(player["firstName"]["default"]),
                "gameId": game_id,
                "hexValue": None,
                "lastName": as_shift_api(player["lastName"]["default"]),
                "period": period,
                "playerId": player["playerId"],
                "shiftNumber": shift_number,
                "startTime": start,
                "teamAbbrev": team["abbrev"],
                "teamId": team["id"],
                "teamName": team_name,
                "typeCode": 517,
            })
    return {"data": data, "total": len(data)}


def boxscore_mismatches(game_id, payload):
    """Players whose total time on ice in the payload differs from the boxscore's (by more than a
    second): [(player_id, html_seconds, boxscore_seconds)]."""
    box = get(BOXSCORE_URL.format(game_id=game_id)).json()
    html_totals = {}
    for shift in payload["data"]:
        html_totals[shift["playerId"]] = html_totals.get(shift["playerId"], 0) + seconds(shift["duration"])
    mismatches = []
    for side in ("awayTeam", "homeTeam"):
        for group in ("forwards", "defense", "goalies"):
            for player in box["playerByGameStats"][side].get(group, []):
                official = seconds(player["toi"])
                measured = html_totals.get(player["playerId"], 0)
                if abs(measured - official) > 1:
                    mismatches.append((player["playerId"], measured, official))
    return mismatches


def season_game_ids(season):
    games = get(GAMES_URL.format(season=season)).json().get("data", [])
    return sorted(game["id"] for game in games if game.get("gameStateId") == FINAL)


@dag(
    dag_id="backfill_shifts_from_html",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_tasks=1,  # one season after the other
    tags=["nhl", "one-off"],
    doc_md=__doc__,
)
def backfill_shifts_from_html():

    @task
    def load_season_shifts(season: str):
        game_ids = season_game_ids(season)

        conn = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID).get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT DISTINCT raw_payload:data[0]:gameId::int FROM {TABLE}")
            already = {row[0] for row in cursor.fetchall()}
            to_load = [g for g in game_ids if g not in already]
            print(f"{season}: {len(game_ids)} finished games, {len(game_ids) - len(to_load)} already loaded, {len(to_load)} to load")

            not_published, mismatched = [], {}
            for n, game_id in enumerate(to_load, start=1):
                payload = build_payload(game_id)
                if payload is None or not payload["data"]:
                    print(f"Game {game_id}: no time-on-ice report, not loaded")
                    not_published.append(game_id)
                else:
                    cursor.execute(
                        f"INSERT INTO {TABLE} (raw_payload) SELECT PARSE_JSON(%s)",
                        (json.dumps(payload),),
                    )
                    mismatches = boxscore_mismatches(game_id, payload)
                    if mismatches:
                        print(f"Game {game_id}: time on ice differs from the boxscore for (player, HTML s, boxscore s) {mismatches}")
                        mismatched[game_id] = mismatches
                if n % 50 == 0 or n == len(to_load):
                    print(f"{time.strftime('%H:%M:%S')} {n}/{len(to_load)}")
                time.sleep(PAUSE_SECONDS)
        finally:
            cursor.close()
            conn.close()

        print(f"\n{season} done: {len(to_load) - len(not_published)} games loaded")
        print(f"Without a time-on-ice report (not loaded, trigger again later): {not_published or 'none'}")
        print(f"With a time on ice different from the boxscore: {sorted(mismatched) or 'none'}")

    load_season_shifts.expand(season=SEASONS)


backfill_shifts_from_html()

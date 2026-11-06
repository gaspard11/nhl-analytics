"""One-off replay of the nhl_players_team_snapshot history in production.

A snapshot run only sees the league as of its `as_of` date, so the history is rebuilt by running
`dbt snapshot` once per game date, oldest first, then once without --vars (today). The commands
are sent to a dbt Cloud prod job with steps_override, in batches, one batch after the other.

Before running: pause the Airflow DAG, clone then drop SNAPSHOTS.NHL_PLAYERS_TEAM_SNAPSHOT.

Usage (PowerShell, from the repo root):
    $env:DBT_CLOUD_API_TOKEN = "<token>"
    python scripts/replay_player_team_snapshot.py replay_dates.csv --dry-run
    python scripts/replay_player_team_snapshot.py replay_dates.csv
    python scripts/replay_player_team_snapshot.py replay_dates.csv --start-from 2026-01-15

The dates file is any text or CSV file with one YYYY-MM-DD date per line (a header is ignored),
e.g. the export of: select distinct game_date from NHL_ANALYTICS.MARTS.FCT_GAMES order by 1
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request

DBT_CLOUD_HOST = "https://ps806.us1.dbt.com"
ACCOUNT_ID = 70506183162119
JOB_ID = 70506183143657  # one-off prod job "snapshot replay"

SNAPSHOT_COMMAND = "dbt snapshot --select nhl_players_team_snapshot"
BATCH_SIZE = 50
POLL_SECONDS = 30

# dbt Cloud run statuses
SUCCESS, ERROR, CANCELLED = 10, 20, 30


def api(method, path, body=None):
    request = urllib.request.Request(
        f"{DBT_CLOUD_HOST}/api/v2/accounts/{ACCOUNT_ID}/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Token {os.environ['DBT_CLOUD_API_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)["data"]


def read_dates(path):
    with open(path, encoding="utf-8-sig") as f:
        dates = {m.group(0) for line in f if (m := re.search(r"\d{4}-\d{2}-\d{2}", line))}
    return sorted(dates)


def run_batch(commands, cause):
    run = api("POST", f"jobs/{JOB_ID}/run/", {"cause": cause, "steps_override": commands})
    print(f"  run {run['id']} started: {run['href']}")
    while True:
        time.sleep(POLL_SECONDS)
        run = api("GET", f"runs/{run['id']}/")
        print(f"  {time.strftime('%H:%M:%S')} {run['status_humanized']}")
        if run["status"] in (SUCCESS, ERROR, CANCELLED):
            return run["status"] == SUCCESS


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dates_file")
    parser.add_argument("--start-from", help="skip the dates before this one (to resume after a failed batch)")
    parser.add_argument("--dry-run", action="store_true", help="print the batches without calling dbt Cloud")
    args = parser.parse_args()

    dates = [d for d in read_dates(args.dates_file) if not args.start_from or d >= args.start_from]
    commands = [f"""{SNAPSHOT_COMMAND} --vars '{{as_of: "{d}"}}'""" for d in dates]
    # Last run without --vars: today's state, for the stints still going on
    commands.append(SNAPSHOT_COMMAND)
    batches = [commands[i:i + BATCH_SIZE] for i in range(0, len(commands), BATCH_SIZE)]
    print(f"{len(dates)} dates ({dates[0]} to {dates[-1]}) + final run = {len(commands)} commands, {len(batches)} batches")

    for n, batch in enumerate(batches, start=1):
        first, last = batch[0], batch[-1]
        print(f"\nBatch {n}/{len(batches)}: {len(batch)} commands\n  first: {first}\n  last:  {last}")
        if args.dry_run:
            continue
        if not run_batch(batch, f"Snapshot replay, batch {n}/{len(batches)}"):
            resume = re.search(r"\d{4}-\d{2}-\d{2}", first)
            print(f"\nBatch {n} failed: check the run logs, then resume with --start-from {resume.group(0) if resume else '(final run only)'}")
            sys.exit(1)

    print("\nDone." if not args.dry_run else "\nDry run only, nothing was sent.")


if __name__ == "__main__":
    main()

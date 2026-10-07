"""Daily NHL load.

Fetches the finished regular season games of one date from the NHL API, appends the raw JSON
to NHL_RAW.RAW in Snowflake, then runs the dbt Cloud production job that builds the marts.
All the API calls come first and the inserts at the end, so the warehouse only wakes up briefly.

Scheduled runs load the previous day. Any date can be (re)loaded by triggering the DAG with
game_date = YYYY-MM-DD: staging keeps only the latest load of each game, so reloading is safe.

The DAG runs on a GCP VM that is only up around the scheduled run: an instance schedule starts
it at 06:00 UTC and the last task, stop_vm, shuts it down.
"""

from datetime import datetime, timedelta
import json

import requests
from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException
from airflow.models.param import Param
from airflow.operators.empty import EmptyOperator
from airflow.providers.dbt.cloud.operators.dbt import DbtCloudRunJobOperator
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook


SNOWFLAKE_CONN_ID = "snowflake_conn_25"
DBT_CLOUD_CONN_ID = "dbt_conn_gas25"
DBT_CLOUD_JOB_ID = 70506183139286  # production job

GCE_METADATA_URL = "http://169.254.169.254/computeMetadata/v1"


def insert_raw_payload(table, payload):
    """Appends one API response to a raw table, as-is, in its VARIANT column."""
    hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
    conn = hook.get_conn()
    cursor = conn.cursor()
    cursor.execute(
        f"INSERT INTO NHL_RAW.RAW.{table} (raw_payload) SELECT PARSE_JSON(%s)",
        (json.dumps(payload),),
    )
    cursor.close()
    conn.close()


@dag(
    dag_id="nhl_raw_pipeline",
    schedule="15 6 * * *",  # 06:15 UTC, 15 minutes after the VM's instance schedule starts it
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["nhl", "learning"],
    doc_md=__doc__,
    params={
        "game_date": Param(
            default="yesterday",
            type="string",
            description="Date to load (YYYY-MM-DD), or 'yesterday' for the day before the run",
        )
    },
)
def nhl_raw_pipeline():

    @task
    def extract_nhl_data(**kwargs):
        game_date = kwargs["params"]["game_date"]
        if game_date == "yesterday":
            # Games end late in North America: the morning run loads the day before
            game_date = (kwargs["dag_run"].run_after - timedelta(days=1)).strftime("%Y-%m-%d")
        game_date = game_date.replace("-", "")

        # gameType=2: regular season only
        url = f"https://api.nhle.com/stats/rest/en/game?cayenneExp=gameDate=%22{game_date}%22%20and%20gameType=2"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    @task(trigger_rule="none_failed")
    def load_games_to_snowflake(payload: dict):
        # Nothing to load on a day without games
        if payload.get("data"):
            insert_raw_payload("GAMES_RAW", payload)

    @task
    def extract_game_ids(payload: dict):
        return [game["id"] for game in payload.get("data", [])]

    @task
    def extract_game_pbp(game_id: int):
        response = requests.get(f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play")
        response.raise_for_status()
        return response.json()

    @task
    def extract_player_ids(payloads: list):
        """Every player with a goal or an assist that day, once even with several points."""
        player_ids = set()
        for payload in payloads:
            for play in payload.get("plays", []):
                if play["typeDescKey"] != "goal":
                    continue
                details = play["details"]
                # Shootout goals don't count as goals in player stats
                if play["periodDescriptor"]["periodType"] != "SO":
                    player_ids.add(int(details["scoringPlayerId"]))
                for assist in ("assist1PlayerId", "assist2PlayerId"):
                    if assist in details:
                        player_ids.add(int(details[assist]))
        return list(player_ids)

    @task
    def filter_new_player_ids(player_ids: list):
        # Players are loaded once: keep only the ones not yet in DIM_PLAYERS
        hook = SnowflakeHook(snowflake_conn_id=SNOWFLAKE_CONN_ID)
        conn = hook.get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT player_id FROM NHL_ANALYTICS.MARTS.DIM_PLAYERS"
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        known_ids = {row[0] for row in rows}
        new_ids = set(player_ids) - known_ids
        return list(new_ids)

    @task
    def extract_player_infos(player_id: int):
        response = requests.get(f"https://api-web.nhle.com/v1/player/{player_id}/landing")
        response.raise_for_status()
        return response.json()

    @task(trigger_rule="none_failed")
    def load_game_pbp_to_snowflake(payload: dict):
        insert_raw_payload("GAMES_PBP_RAW", payload)

    @task(trigger_rule="none_failed")
    def load_player_infos_to_snowflake(payload: dict):
        insert_raw_payload("PLAYERS_INFO_RAW", payload)

    @task.branch(trigger_rule="none_failed")
    def check_has_games(games_payload):
        return "run_dbt" if games_payload.get("data") else "skip_dbt"

    skip_dbt = EmptyOperator(task_id="skip_dbt")

    run_dbt = DbtCloudRunJobOperator(
        task_id="run_dbt",
        dbt_cloud_conn_id=DBT_CLOUD_CONN_ID,
        job_id=DBT_CLOUD_JOB_ID,
        wait_for_termination=True,
        check_interval=30,
        timeout=3600,
        trigger_rule="none_failed",
    )

    # all_done: runs even if an upstream task failed, so the VM is never left running
    @task(trigger_rule="all_done")
    def stop_vm(**kwargs):
        # Manual runs leave the VM up, to keep working in the Airflow UI
        if kwargs["dag_run"].run_type != "scheduled":
            raise AirflowSkipException("Not a scheduled run: leaving the VM up")

        # The metadata server gives the VM's own name, zone and an access token for its service
        # account, which only has compute.instances.stop (custom role vmSelfStop)
        headers = {"Metadata-Flavor": "Google"}
        token = requests.get(f"{GCE_METADATA_URL}/instance/service-accounts/default/token", headers=headers, timeout=5).json()["access_token"]
        project = requests.get(f"{GCE_METADATA_URL}/project/project-id", headers=headers, timeout=5).text
        zone = requests.get(f"{GCE_METADATA_URL}/instance/zone", headers=headers, timeout=5).text.split("/")[-1]
        name = requests.get(f"{GCE_METADATA_URL}/instance/name", headers=headers, timeout=5).text

        response = requests.post(
            f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{name}/stop",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        response.raise_for_status()

    games_payload = extract_nhl_data()

    game_ids = extract_game_ids(games_payload)
    game_pbp_payloads = extract_game_pbp.expand(game_id=game_ids)

    player_ids = extract_player_ids(game_pbp_payloads)
    new_ids = filter_new_player_ids(player_ids)
    player_infos_payloads = extract_player_infos.expand(player_id=new_ids)

    load_games = load_games_to_snowflake(games_payload)
    load_game_pbp = load_game_pbp_to_snowflake.expand(payload=game_pbp_payloads)
    load_player_infos = load_player_infos_to_snowflake.expand(payload=player_infos_payloads)

    branch = check_has_games(games_payload)
    # Inserts wait for the last API call. none_failed on the loads: a day without new players skips
    # extract_player_infos, which must not skip the other inserts
    player_infos_payloads >> [load_games, load_game_pbp]
    [load_games, load_game_pbp, load_player_infos] >> branch
    branch >> [run_dbt, skip_dbt] >> stop_vm()


nhl_raw_pipeline()

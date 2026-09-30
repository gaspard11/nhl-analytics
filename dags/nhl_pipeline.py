from airflow.decorators import dag, task
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from airflow.models.param import Param
from airflow.providers.dbt.cloud.operators.dbt import DbtCloudRunJobOperator
from airflow.operators.empty import EmptyOperator
from airflow.decorators import task


from datetime import datetime
import requests
import json

@dag(
    dag_id="nhl_raw_pipeline",
    schedule=None,          # run manually for now, no auto-schedule yet
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["nhl", "learning"],
    params={
        "game_date": Param(
            default="now",          # keep "now" as a safe fallback
            type="string",
            description="Date to fetch NHL scores for (YYYY-MM-DD), or 'now' for today",
        )
    }
)
def nhl_raw_pipeline():

    @task
    def extract_nhl_data(**kwargs):
        game_date = kwargs["params"]["game_date"].replace('-','')
        # Simple endpoint: today's NHL schedule/scores
        url = f"https://api.nhle.com/stats/rest/en/game?cayenneExp=gameDate=%22{game_date}%22%20and%20gameType=2"
        response = requests.get(url)
        response.raise_for_status()
        r = response.json()
        return response.json() 

    @task
    def load_games_to_snowflake(payload: dict):
        if payload.get("data", []) != []:
            hook = SnowflakeHook(snowflake_conn_id="snowflake_conn_25")
            conn = hook.get_conn()
            cursor = conn.cursor()

            # Insert the whole JSON payload into the VARIANT column
            cursor.execute(
                "INSERT INTO NHL_RAW.RAW.GAMES_RAW (raw_payload) SELECT PARSE_JSON(%s)",
                (json.dumps(payload),)
            )
            cursor.close()
            conn.close()
        

    @task
    def extract_game_ids(payload: dict):
        # id is a plain field on each game object, no dbt needed to get it
        return [game["id"] for game in payload.get("data", [])]

    @task
    def extract_game_pbp(game_id: int):
        url = f"https://api-web.nhle.com/v1/gamecenter/{game_id}/play-by-play"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    @task
    def extract_player_ids(payloads: dict):
        player_ids = []
        for payload in payloads:
            scorers = [int(play['details']['scoringPlayerId']) for play in payload.get("plays",[]) if play['typeDescKey'] == 'goal' and play['periodDescriptor']['periodType'] != 'SO']
            assisters1 = [int(play['details']['assist1PlayerId']) for play in payload.get("plays",[]) if play['typeDescKey'] == 'goal' and 'assist1PlayerId' in play['details']]
            assisters2 = [int(play['details']['assist2PlayerId']) for play in payload.get("plays",[]) if play['typeDescKey'] == 'goal' and 'assist2PlayerId' in play['details']]
            player_ids+= list(set(scorers + assisters1+ assisters2))
        return player_ids

    @task
    def extract_player_infos(player_id: int):
        hook = SnowflakeHook(snowflake_conn_id="snowflake_conn_25")
        conn = hook.get_conn()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT 1 FROM NHL_ANALYTICS.MARTS.NHL_PLAYERS WHERE PLAYER_ID = %s LIMIT 1",
            (player_id,)
        )
        row_exists = cursor.fetchone() is not None
        cursor.close()
        conn.close()

        if row_exists:
            return None  # or some sentinel indicating "already present"
        else:
            url = f"https://api-web.nhle.com/v1/player/{player_id}/landing"
            response = requests.get(url)
            response.raise_for_status()
            return response.json()
    
    @task
    def load_game_pbp_to_snowflake(payload: dict):
        hook = SnowflakeHook(snowflake_conn_id="snowflake_conn_25")
        conn = hook.get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO NHL_RAW.RAW.GAMES_PBP_RAW (raw_payload) SELECT PARSE_JSON(%s)",
            (json.dumps(payload),)
            )
        cursor.close()
        conn.close()

    @task
    def load_player_infos_to_snowflake(payload: dict):
        hook = SnowflakeHook(snowflake_conn_id="snowflake_conn_25")
        conn = hook.get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO NHL_RAW.RAW.PLAYERS_INFO_RAW (raw_payload) SELECT PARSE_JSON(%s)",
            (json.dumps(payload),)
            )
        cursor.close()
        conn.close()

    @task.branch(trigger_rule="none_failed")
    def check_has_games(games_payload):
        return "run_dbt" if games_payload.get("data") else "skip_dbt"

    skip_dbt = EmptyOperator(task_id="skip_dbt")


    games_payload = extract_nhl_data()  

    game_ids = extract_game_ids(games_payload)
    game_infos_payloads = extract_game_pbp.expand(game_id=game_ids)
    

    player_ids = extract_player_ids(game_infos_payloads)
    player_infos_payloads = extract_player_infos.expand(player_id=player_ids)

    load_games = load_games_to_snowflake(games_payload)
    load_game_infos = load_game_pbp_to_snowflake.expand(payload=game_infos_payloads)
    load_player_infos = load_player_infos_to_snowflake.expand(payload=player_infos_payloads)

    

    run_dbt = DbtCloudRunJobOperator(
        task_id="run_dbt",
        dbt_cloud_conn_id="dbt_conn_gas25",
        job_id=70506183139286,  # replace with your actual dbt Cloud job ID
        wait_for_termination=True,   # task waits/polls until dbt Cloud job finishes
        check_interval=30,           # poll every 30s
        timeout=3600,                # fail if it runs over 1hr
        trigger_rule="none_failed"
    )

    branch = check_has_games(games_payload)

    [load_games, load_game_infos, load_player_infos] >> branch
    branch >> [run_dbt, skip_dbt]

    

    


nhl_raw_pipeline()
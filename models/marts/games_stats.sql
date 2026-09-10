{{ config(materialized='incremental', schema='marts', unique_key= ['game_id','event_id']) }}

SELECT
    game_id,
    event_id,
    team_id,
    situation_code,
    home_score,
    away_score,
    scoring_player_id,
    assist1_player_id,
    assist2_player_id,
    period_number,
    time_in_period,
    time_remaining_in_period
FROM {{ ref('stg_game_stats') }}
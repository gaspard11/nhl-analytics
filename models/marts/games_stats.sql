{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id')}}

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
    time_remaining_in_period,
    fetched_at
FROM {{ ref('stg_games_pbp') }}
{% if is_incremental() %}
where fetched_at > (select max(fetched_at) from {{ this }})
{% endif %}
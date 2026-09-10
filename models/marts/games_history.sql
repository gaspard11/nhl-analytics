{{ config(materialized='incremental', schema='marts', unique_key= 'game_id') }}

select
    game_id,
    game_date,
    game_state,
    home_team_id,
    home_team_score,
    away_team_id,
    away_team_score,
    lastperiodtype as last_period_type
from {{ref('stg_games')}}
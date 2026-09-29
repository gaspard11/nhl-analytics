{{ config(materialized='incremental', unique_key='game_id') }}

-- One row per finished game. New or reloaded games are merged on game_id.

select
    game_id,
    season,
    game_date,
    game_state,
    home_team_id,
    home_team_score,
    away_team_id,
    away_team_score,
    last_period_type,
    fetched_at
from {{ ref('stg_nhl_api__games') }}
{% if is_incremental() %}
where fetched_at > (select max(fetched_at) from {{ this }})
{% endif %}

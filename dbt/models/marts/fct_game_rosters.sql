{{ config(materialized='incremental', unique_key='game_id') }}

-- One row per finished game. New or reloaded games are merged on game_id.

select
    game_id,
    player_id,
    team_id,
    position,
    fetched_at
from {{ ref('stg_nhl_api__game_rosters') }}
{% if is_incremental() %}
where fetched_at > (select max(fetched_at) from {{ this }})
{% endif %}
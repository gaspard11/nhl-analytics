{{ config(materialized='incremental', unique_key='game_id', incremental_strategy='delete+insert') }}

select
    game_id,
    player_id,
    team_id,
    position,
    sweater_number,
    fetched_at
from {{ ref('stg_nhl_api__game_rosters') }}
{% if is_incremental() %}
where fetched_at > (select max(fetched_at) from {{ this }})
{% endif %}
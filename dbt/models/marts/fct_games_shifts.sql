{{ config(materialized='incremental', unique_key='game_id') }}

-- One row per finished game. New or reloaded games are merged on game_id.

select
    game_id,
    team_id,
    played_id,
    shift_number,
    period,
    shift_id,
    start_time,
    end_time,
    duration,
    fetched_at
from {{ ref('stg_nhl_api__games_shifts') }}
{% if is_incremental() %}
where fetched_at > (select max(fetched_at) from {{ this }})
{% endif %}
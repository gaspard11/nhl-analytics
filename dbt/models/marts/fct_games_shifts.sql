{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

-- One row per shift of a finished game. A reloaded game replaces all its shifts (delete+insert on
-- game_id): a merge would fail, since a game has many rows.

select
    game_id,
    team_id,
    player_id,
    shift_number,
    period,
    start_time,
    end_time,
    duration,
    fetched_at
from {{ ref('stg_nhl_api__games_shifts') }}
{% if is_incremental() %}
where fetched_at > (select max(fetched_at) from {{ this }})
{% endif %}

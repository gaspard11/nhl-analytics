{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

-- One row per non-shootout goal. A reloaded game replaces all its goals (delete+insert on game_id),
-- so a goal disallowed after the first load disappears.

select
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
from {{ ref('stg_nhl_api__goals') }}
{% if is_incremental() %}
where fetched_at > (select max(fetched_at) from {{ this }})
{% endif %}

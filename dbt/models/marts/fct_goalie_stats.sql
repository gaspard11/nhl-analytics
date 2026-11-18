{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}

select
    ranking_date,
    season,
    player_id,
    games_played,
    toi_seconds, 
    goals_against, 
    saves, 
    shutouts,
    shots_against,
    gaa,
    save_pct,
    _batch_loaded_at
from {{ ref('int_goalie_stats_cumulative') }}
{% if is_incremental() %}
where _batch_loaded_at > (
    select coalesce(max(_batch_loaded_at), '1900-01-01'::timestamp_ltz) from {{ this }}
)
{% endif %}
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
    number_of_goals as goals,
    number_of_assists as assists,
    number_of_points as points,
    _batch_loaded_at
from {{ ref('int_player_scoring_cumulative') }}
{% if is_incremental() %}
where _batch_loaded_at > (
    select coalesce(max(_batch_loaded_at), '1900-01-01'::timestamp_ltz) from {{ this }}
)
{% endif %}

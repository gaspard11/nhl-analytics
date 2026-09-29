{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}

-- Points (goals + assists) ranking per day.
-- Every row of int_player_scoring_cumulative has at least one point, so no filter is needed.

select
    ranking_date,
    season,
    rank() over (
        partition by season, ranking_date
        order by number_of_points desc
    )                   as ranking,
    player_id,
    number_of_points,
    _batch_loaded_at
from {{ ref('int_player_scoring_cumulative') }}
{% if is_incremental() %}
where _batch_loaded_at > (
    select coalesce(max(_batch_loaded_at), '1900-01-01'::timestamp_ltz) from {{ this }}
)
{% endif %}
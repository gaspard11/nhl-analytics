{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['season', 'ranking_date'],
    on_schema_change='fail'
) }}

-- Goals ranking per day. Only players with at least one goal this season are ranked.

select
    ranking_date,
    season,
    rank() over (
        partition by season, ranking_date
        order by number_of_goals desc
    )                   as ranking,
    player_id,
    number_of_goals,
    _batch_loaded_at
from {{ ref('int_player_scoring_cumulative') }}
where number_of_goals > 0
{% if is_incremental() %}
  and _batch_loaded_at > (
      select coalesce(max(_batch_loaded_at), '1900-01-01'::timestamp_ltz) from {{ this }}
  )
{% endif %}
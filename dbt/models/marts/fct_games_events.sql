{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

with base as (
  select
    pbp.* exclude (fetched_at),
    lpad(cast(pbp.situation_code as varchar), 4, '0') as sc,
    games.home_team_id,
    games.away_team_id,
    greatest(pbp.fetched_at, games.fetched_at) as fetched_at
  from {{ ref('stg_nhl_api__games') }} games
  join {{ ref('stg_nhl_api__pbp') }} pbp on games.game_id = pbp.game_id
  {% if is_incremental() %}
  where greatest(pbp.fetched_at, games.fetched_at) > (select max(fetched_at) from {{ this }})
  {% endif %}
),

sides as (
  select
    base.*,
    -- re-orient the code from away/home to scorer/opponent
    cast(substr(sc, 4, 1) as int) as home_goalie,
    cast(substr(sc, 3, 1) as int) as home_skaters,
    cast(substr(sc, 2, 1) as int) as away_skaters,
    cast(substr(sc, 1, 1) as int) as away_goalie
  from base
),

-- A pulled goalie gives an extra skater, not a power play: it is taken off both sides before comparing
effective as (
  select
    sides.*,
    home_skaters - (1 - home_goalie) as home_effective,
    away_skaters - (1 - away_goalie) as away_effective
  from sides
)

select
    game_id,
    event_id,
    sort_order,
    team_id,
    situation_code,
    event_type,
    home_score,
    away_score,
    period_number,
    period_descriptor,
    time_in_period,
    time_remaining_in_period,
    zone_code,
    x_coord,
    y_coord,
    player_1_desc,
    player_1_id,
    player_2_desc,
    player_2_id,
    player_3_desc,
    player_3_id,
    goalie_in_net_id,
    details,
    case
        when sc in ('0101', '1010')          then 'PS'
        when home_effective <> away_effective then 'PP'
        else 'EV'
    end as strength_situation,
    -- Penalty shots first: their code has a 0 where a goalie is usually counted
    case
        when sc in ('0101', '1010')              then 'NORMAL'
        when home_goalie = 0 or away_goalie = 0  then 'PULLED'
        else 'NORMAL'
    end as net_situation,
    case
        when sc in ('0101', '1010')  then null
        when home_goalie = 0         then home_team_id
        when away_goalie = 0         then away_team_id
    end as empty_net_team_id,
    case
        when sc in ('0101', '1010') then 'Penalty shot'
        when home_skaters > away_skaters then concat(home_skaters, ' on ', away_skaters)
        else concat(away_skaters, ' on ', home_skaters)
    end as strength_adv_team,
    case
        when home_effective > away_effective then home_team_id
        when away_effective > home_effective then away_team_id
    end as man_adv_team_id,
    fetched_at
from effective

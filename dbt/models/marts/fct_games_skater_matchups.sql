{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}

-- Time two opposing skaters spent on the ice at the same time, per game and period.
-- Goalies excluded. One row per pair: player_1_id < player_2_id.
-- Incremental: a reloaded game (newer fetched_at) is recomputed whole, delete+insert on game_id.

with skater_shifts as (

    select
        s.game_id,
        s.period,
        s.team_id,
        s.player_id,
        split_part(s.start_time, ':', 1)::int * 60 + split_part(s.start_time, ':', 2)::int as start_s,
        split_part(s.end_time, ':', 1)::int * 60 + split_part(s.end_time, ':', 2)::int     as end_s,
        s.fetched_at
    from {{ ref('fct_games_shifts') }} s
    join {{ ref('fct_game_rosters') }} r
        on r.game_id = s.game_id
       and r.player_id = s.player_id
    where r.position <> 'G'
    {% if is_incremental() %}
      and s.fetched_at > (select max(fetched_at) from {{ this }})
    {% endif %}

)

select
    a.game_id,
    a.period,
    a.player_id                                                   as player_1_id,
    a.team_id                                                     as player_1_team_id,
    b.player_id                                                   as player_2_id,
    b.team_id                                                     as player_2_team_id,
    sum(least(a.end_s, b.end_s) - greatest(a.start_s, b.start_s)) as toi_seconds,
    max(a.fetched_at)                                             as fetched_at
from skater_shifts a
join skater_shifts b
    on b.game_id = a.game_id
   and b.period = a.period
   and b.team_id <> a.team_id
   and a.player_id < b.player_id
   -- the two shifts overlap: each starts before the other ends
   and b.start_s < a.end_s
   and a.start_s < b.end_s
group by all
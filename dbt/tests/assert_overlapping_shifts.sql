with shifts as (
    select
        game_id, player_id, period, start_time, end_time,
        split_part(start_time, ':', 1)::int * 60 + split_part(start_time, ':', 2)::int as start_s,
        split_part(end_time, ':', 1)::int * 60 + split_part(end_time, ':', 2)::int as end_s
    from {{ ref('stg_nhl_api__games_shifts') }}
)

select a.game_id, a.player_id, a.period,
       a.start_time as start_1, a.end_time as end_1,
       b.start_time as start_2, b.end_time as end_2
from shifts a
join shifts b
    on  b.game_id = a.game_id
    and b.player_id = a.player_id
    and b.period = a.period
    and (b.start_s, b.end_s) > (a.start_s, a.end_s)  -- each pair once, and identical rows still pair up below
    and b.start_s < a.end_s                           -- b starts before a ends: they overlap
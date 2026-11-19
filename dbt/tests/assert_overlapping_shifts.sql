-- A player can't be on the ice twice at the same time: two shifts of the same player in the same
-- period must not overlap. Catches a game whose shifts were recorded twice by the shift API (game
-- 2025020512: the same minutes in a few long shifts and again in several short ones), which would
-- count that time twice.
-- Returns each pair of overlapping shifts, and each shift present more than once.

with shifts as (
    select
        game_id, player_id, period, start_time, end_time,
        split_part(start_time, ':', 1)::int * 60 + split_part(start_time, ':', 2)::int as start_s,
        split_part(end_time, ':', 1)::int * 60 + split_part(end_time, ':', 2)::int as end_s
    from {{ ref('stg_nhl_api__games_shifts') }}
)

-- Two different shifts that overlap
select a.game_id, a.player_id, a.period,
       a.start_time as start_1, a.end_time as end_1,
       b.start_time as start_2, b.end_time as end_2
from shifts a
join shifts b
    on  b.game_id = a.game_id
    and b.player_id = a.player_id
    and b.period = a.period
    and (b.start_s, b.end_s) > (a.start_s, a.end_s)  -- each pair once (identical shifts never pair up here)
    and b.start_s < a.end_s                           -- b starts before a ends: they overlap

union all

-- The same shift more than once (game 2025020565: every period twice, under two shift ids)
select game_id, player_id, period,
       start_time as start_1, end_time as end_1,
       start_time as start_2, end_time as end_2
from shifts
group by game_id, player_id, period, start_time, end_time
having count(*) > 1

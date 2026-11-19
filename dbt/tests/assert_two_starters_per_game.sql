-- Every finished game has exactly two starting goalies, one per team: the goalies with a shift
-- starting at 00:00 of period 1. Catches a game with missing or duplicated goalie shifts.
-- Returns the games with a number of starters other than 2.

with starters as (

    select
        game_id,
        count(*) as starters
    from {{ ref('int_goalie_game_stats') }}
    where stat_name = 'games_started'
    group by game_id

)

select
    g.game_id,
    coalesce(s.starters, 0) as starters
from {{ ref('stg_nhl_api__games') }} g
left join starters s
    on s.game_id = g.game_id
where coalesce(s.starters, 0) <> 2

-- Every finished game not decided in a shootout has exactly one game-winning goal in
-- int_goals_situations, and a shootout game has none (the NHL credits no GWG in a shootout game).
-- Catches a missing or extra goal in the play-by-play, which would also break the goalie decisions.
-- Returns the games with the wrong number of game-winning goals.

with winning_goals as (

    select
        game_id,
        count_if(is_game_winning_goal) as game_winning_goals
    from {{ ref('int_goals_situations') }}
    group by game_id

)

select
    g.game_id,
    g.last_period_type,
    coalesce(w.game_winning_goals, 0) as game_winning_goals
from {{ ref('stg_nhl_api__games') }} g
left join winning_goals w
    on w.game_id = g.game_id
where coalesce(w.game_winning_goals, 0) <> iff(g.last_period_type = 'SO', 0, 1)

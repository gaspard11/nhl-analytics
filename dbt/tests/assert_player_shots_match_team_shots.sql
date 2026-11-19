-- A team's shots on goal in a game equal the sum of its players' shots. Catches a player stat
-- double counted, or a shot given to the wrong team.
-- A warning: fct_games_stats counts the shootout attempts in 'Shots On Goal' (its filter doesn't
-- exclude period 5), while the player shots exclude them, so every game decided in a shootout is
-- returned until fct_games_stats leaves the shootout out.
-- Returns the game and team where the two differ.

{{ config(severity='warn') }}

with player_shots as (

    select
        s.game_id,
        r.team_id,
        sum(s.stat_value) as player_shots
    from {{ ref('int_skater_game_stats') }} s
    join {{ ref('stg_nhl_api__game_rosters') }} r
        on r.game_id = s.game_id
       and r.player_id = s.player_id
    where s.stat_name = 'shots'
    group by s.game_id, r.team_id

),

team_shots as (

    select
        game_id,
        team_id,
        stat_value as team_shots
    from {{ ref('fct_games_stats') }}
    where stat_name = 'Shots On Goal'

)

select
    coalesce(p.game_id, t.game_id) as game_id,
    coalesce(p.team_id, t.team_id) as team_id,
    p.player_shots,
    t.team_shots
from player_shots p
full outer join team_shots t
    on t.game_id = p.game_id
   and t.team_id = p.team_id
where coalesce(p.player_shots, 0) <> coalesce(t.team_shots, 0)

-- Within a season, a goalie's season-to-date totals can never go down from one ranking date to the next.
-- Catches a day replaced with older data on the goalie side.
-- Returns the rows where a total is lower than on the previous ranking date.

with ordered as (

    select
        season,
        ranking_date,
        player_id,
        games_played,
        toi_seconds,
        goals_against,
        saves,
        shutouts,
        lag(games_played)  over (partition by season, player_id order by ranking_date) as previous_games_played,
        lag(toi_seconds)   over (partition by season, player_id order by ranking_date) as previous_toi_seconds,
        lag(goals_against) over (partition by season, player_id order by ranking_date) as previous_goals_against,
        lag(saves)         over (partition by season, player_id order by ranking_date) as previous_saves,
        lag(shutouts)      over (partition by season, player_id order by ranking_date) as previous_shutouts
    from {{ ref('fct_goalie_stats') }}

)

select *
from ordered
where games_played  < previous_games_played
   or toi_seconds   < previous_toi_seconds
   or goals_against < previous_goals_against
   or saves         < previous_saves
   or shutouts      < previous_shutouts

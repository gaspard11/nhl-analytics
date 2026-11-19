-- Within a season, a skater's season-to-date totals can never go down from one ranking date to the next.
-- Catches a day replaced with older data on the skater side.
-- Returns the rows where a total is lower than on the previous ranking date.

with ordered as (

    select
        season,
        ranking_date,
        player_id,
        games_played,
        toi_seconds,
        goals,
        assists,
        lag(games_played) over (partition by season, player_id order by ranking_date) as previous_games_played,
        lag(toi_seconds)  over (partition by season, player_id order by ranking_date) as previous_toi_seconds,
        lag(goals)        over (partition by season, player_id order by ranking_date) as previous_goals,
        lag(assists)      over (partition by season, player_id order by ranking_date) as previous_assists
    from {{ ref('fct_skater_stats') }}

)

select *
from ordered
where games_played < previous_games_played
   or toi_seconds  < previous_toi_seconds
   or goals        < previous_goals
   or assists      < previous_assists

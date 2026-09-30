-- Within a season, a player's season-to-date goals and assists can never go down from one ranking date to the next.
-- Catches a day replaced with older data on the player side.
-- Returns the rows where a total is lower than on the previous ranking date.

with ordered as (

    select
        season,
        ranking_date,
        player_id,
        number_of_goals,
        number_of_assists,
        lag(number_of_goals)   over (partition by season, player_id order by ranking_date) as previous_goals,
        lag(number_of_assists) over (partition by season, player_id order by ranking_date) as previous_assists
    from {{ ref('int_player_scoring_cumulative') }}

)

select *
from ordered
where number_of_goals < previous_goals
   or number_of_assists < previous_assists

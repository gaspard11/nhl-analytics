{{ config(materialized='view', schema='marts') }}

select
    ranking_date,
    rank() over (partition by ranking_date order by ranking) as ranking,
    LR.team_id,
    points,
    goals_for,
    goals_against,
    goal_diff,
    LR.games_played,
    regulation_wins,
    regulation_ot_wins,
    total_wins
from {{ref('league_rankings')}} LR
join {{ source('nhl_marts', 'NHL_TEAMS') }} NT on LR.team_id = NT.team_id
WHERE DIVISION_NAME = 'Pacific'
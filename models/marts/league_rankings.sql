{{ config(materialized='incremental', schema='marts', unique_key= ['team_id', 'ranking_date']) }}


SELECT
    game_date as ranking_date,
    rank() over (partition by game_date order by [cumul_points, -RPT.games_played, regulation_wins, regulation_ot_wins, total_wins, COALESCE(tie_rate,0), diff, goals_for] desc) as ranking,
    RPT.team_id,
    cumul_points as points,
    goals_for,
    goals_against,
    diff as goal_diff,
    RPT.games_played,
    regulation_wins,
    regulation_ot_wins,
    total_wins
FROM {{ref('stg_league_ranking_pre_tie_breaker')}} RPT
LEFT JOIN {{ref('stg_tied_teams_rate')}} TTR on RPT.team_id = TTR.team_id and RPT.TIE_GROUP_ID = TTR.TIE_GROUP_ID

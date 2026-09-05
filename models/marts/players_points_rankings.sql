{{ config(materialized='incremental', schema='marts', unique_key = ['player_id','ranking_date']) }}


select 
    COALESCE(AR.ranking_date, GR.ranking_date) as ranking_date,
    rank() over (PARTITION BY COALESCE(AR.ranking_date, GR.ranking_date) order by COALESCE(AR.number_of_assists, 0) + COALESCE(GR.number_of_goals, 0) desc) as ranking,
    COALESCE(AR.player_id, GR.player_id) as player_id,
    COALESCE(AR.number_of_assists, 0) + COALESCE(GR.number_of_goals, 0) as number_of_points

from {{ref('players_assists_rankings')}} AR
FULL OUTER JOIN {{ref('players_goals_rankings')}} GR on AR.player_id = GR.player_id and AR.ranking_date = GR.ranking_date
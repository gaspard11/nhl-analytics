{{ config(materialized='incremental', unique_key = ['player_id','ranking_date']) }}


WITH CTE_CURRENT_DATE
AS
(
    SELECT MAX(ranking_date) as cdate FROM {{ref('players_assists_rankings')}}
),

CTE_CURRENT_SEASON
AS
(
    SELECT MAX(season) as cseason FROM {{ref('players_assists_rankings')}}
),


CTE_LAST_RANKING_ASSISTS 
AS
(
SELECT * FROM {{ref('players_assists_rankings')}} WHERE ranking_date = (SELECT cdate from CTE_CURRENT_DATE)
),
CTE_LAST_RANKING_GOALS AS
(
SELECT * FROM {{ref('players_goals_rankings')}} WHERE ranking_date = (SELECT cdate from CTE_CURRENT_DATE)
)

select 
    (SELECT cdate from CTE_CURRENT_DATE) as ranking_date,
    (SELECT cseason from CTE_CURRENT_SEASON) as season,
    rank() over (PARTITION BY COALESCE(AR.ranking_date, GR.ranking_date) order by COALESCE(AR.number_of_assists, 0) + COALESCE(GR.number_of_goals, 0) desc) as ranking,
    COALESCE(AR.player_id, GR.player_id) as player_id,
    COALESCE(AR.number_of_assists, 0) + COALESCE(GR.number_of_goals, 0) as number_of_points

from CTE_LAST_RANKING_ASSISTS AR
FULL OUTER JOIN CTE_LAST_RANKING_GOALS GR 
on AR.player_id = GR.player_id
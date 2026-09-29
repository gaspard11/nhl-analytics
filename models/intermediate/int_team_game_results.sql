WITH STG_GAMES AS
(
    select * from {{ref('stg_games')}}
),

HOME AS
(
select 
    game_id,
    game_date,
    season,
    home_team_id as team_id,
    away_team_id as opponent_team_id,
    True as is_home,
    home_team_score as goals_for,
    away_team_score as goals_against,
    last_period_type,
    fetched_at,
    CASE WHEN home_team_score > away_team_score THEN 1 ELSE 0 END AS win,
    CASE WHEN last_period_type = 'REG' AND home_team_score > away_team_score THEN 1 ELSE 0 END AS regulation_win,
    CASE WHEN last_period_type <> 'SO' AND home_team_score > away_team_score THEN 1 ELSE 0 END AS regulation_OT_win,
    CASE WHEN home_team_score > away_team_score THEN 2
         WHEN last_period_type <> 'REG' THEN 1
         ELSE 0 END AS points
from STG_GAMES
),

AWAY AS
(
select 
    game_id,
    game_date,
    season,
    away_team_id as team_id,
    home_team_id as opponent_team_id,
    False as is_home,
    away_team_score as goals_for,
    home_team_score as goals_against,
    last_period_type,
    fetched_at,
    CASE WHEN home_team_score < away_team_score THEN 1 ELSE 0 END AS win,
    CASE WHEN last_period_type = 'REG' AND home_team_score < away_team_score THEN 1 ELSE 0 END AS regulation_win,
    CASE WHEN last_period_type <> 'SO' AND home_team_score < away_team_score THEN 1 ELSE 0 END AS regulation_OT_win,
    CASE WHEN home_team_score < away_team_score THEN 2
         WHEN last_period_type <> 'REG' THEN 1
         ELSE 0 END AS points
from STG_GAMES
)

SELECT * FROM HOME
UNION ALL
SELECT * FROM AWAY
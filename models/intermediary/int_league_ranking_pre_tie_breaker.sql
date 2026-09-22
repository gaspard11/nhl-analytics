{{ config(materialized='view', schema='intermediary') }}



{%- set season_query -%}
    SELECT MAX(season) FROM {{ ref('stg_games') }}
    WHERE game_date = (SELECT MAX(game_date) FROM {{ ref('stg_games') }})
{%- endset -%}

{%- set season_selected = run_query(season_query).columns[0].values()[0] -%}

{%- set count_query -%}
    SELECT COUNT(*) AS cnt
    FROM {{ source('nhl_marts', 'LEAGUE_RANKINGS') }}
    WHERE season = {{ season_selected }}
{%- endset -%}

{%- set rankings_count = run_query(count_query).columns[0].values()[0] if execute else 0 -%}


WITH STG_GAMES AS
(
    SELECT * FROM {{ref('stg_games')}} 
    WHERE game_date = (SELECT MAX(GAME_DATE) FROM {{ref('stg_games')}})
),

CURRENT_RANKINGS AS
(

    {% if rankings_count == 0 %}
        SELECT 
            DATEADD(day, -1, (SELECT MAX(GAME_DATE) FROM {{ ref('stg_games') }})) as ranking_date,
            (SELECT MAX(season) FROM {{ref('stg_games')}}) as season,
            32 as ranking,
            team_id,
            0 as points,
            0 as goals_for,
            0 as goals_against,
            0 as goal_diff,
            0 as games_played,
            0 as regulation_wins,
            0 as regulation_ot_wins,
            0 as total_wins
        FROM {{ref('NHL_TEAMS')}}
    {% else %}
        SELECT *
        FROM {{ source('nhl_marts', 'LEAGUE_RANKINGS') }}
        WHERE RANKING_DATE = (
            SELECT MAX(RANKING_DATE) FROM {{ rankings_source }}
        )
    {% endif %}
),

CTE_NEW_POINTS AS
(
SELECT
    GAME_DATE,
    CASE WHEN HOME_TEAM_SCORE > AWAY_TEAM_SCORE THEN HOME_TEAM_ID ELSE AWAY_TEAM_ID END as TEAM_ID,
    2 as points
FROM STG_GAMES
WHERE HOME_TEAM_SCORE IS NOT NULL
UNION
SELECT
    GAME_DATE,
    CASE WHEN HOME_TEAM_SCORE < AWAY_TEAM_SCORE THEN HOME_TEAM_ID ELSE AWAY_TEAM_ID END as TEAM_ID,
    CASE WHEN lastperiodtype in ('OT','SO') THEN 1 ELSE 0 END as points,
FROM STG_GAMES
WHERE HOME_TEAM_SCORE IS NOT NULL
),

CTE_NEW_GOALS AS
(
SELECT 
    GAME_DATE,
    HOME_TEAM_ID as team_id,
    HOME_TEAM_SCORE as goals_for,
    AWAY_TEAM_SCORE as goals_against
FROM STG_GAMES
WHERE HOME_TEAM_SCORE IS NOT NULL
UNION
SELECT 
    GAME_DATE,
    AWAY_TEAM_ID as team_id,
    AWAY_TEAM_SCORE as goals_for,
    HOME_TEAM_SCORE as goals_against
FROM STG_GAMES
WHERE HOME_TEAM_SCORE IS NOT NULL
),

CTE_NEW_WINS AS
(
SELECT
    GAME_DATE,
    CASE WHEN HOME_TEAM_SCORE > AWAY_TEAM_SCORE THEN HOME_TEAM_ID ELSE AWAY_TEAM_ID END as TEAM_ID,
    CASE WHEN lastperiodtype = 'REG' THEN 1 ELSE 0 END as regulation_win,
    CASE WHEN lastperiodtype in ('OT','REG') THEN 1 ELSE 0 END as regulation_ot_win,
    1 as win
FROM STG_GAMES
WHERE HOME_TEAM_SCORE IS NOT NULL
),

CTE_NEW_GAMES AS
(
SELECT
    GAME_DATE,
    HOME_TEAM_ID as TEAM_ID,
    1 as game_played
FROM STG_GAMES
WHERE HOME_TEAM_SCORE IS NOT NULL
UNION ALL
SELECT
    GAME_DATE,
    AWAY_TEAM_ID as TEAM_ID,
    1 as game_played
FROM STG_GAMES
WHERE HOME_TEAM_SCORE IS NOT NULL
),

CTE_PRIOR_POINTS as (
SELECT
    team_id,
    points,
    FROM CURRENT_RANKINGS
),

CTE_PRIOR_DIFF as (
SELECT
    team_id,
    GOAL_DIFF,
    goals_for,
    goals_against
    FROM CURRENT_RANKINGS
),

CTE_PRIOR_WINS as (
SELECT
    team_id,
    regulation_wins,
    regulation_ot_wins,
    total_wins
    FROM CURRENT_RANKINGS
),

CTE_PRIOR_GAMES as (
SELECT
    ranking_date,
    team_id,
    games_played
    FROM CURRENT_RANKINGS
),

CUMUL_POINTS as (
    select
        PP.team_id,
        PP.points + COALESCE(NP.points,0) as cumul_points,
        (SELECT MAX(game_date) FROM CTE_NEW_GOALS) as game_date
    from CTE_PRIOR_POINTS PP
    LEFT JOIN CTE_NEW_POINTS NP on PP.team_id = NP.team_id
),

CUMUL_DIFF as (
    select
        PG.team_id,
        PG.goals_for + COALESCE(NG.goals_for,0) as goals_for,
        PG.goals_against + COALESCE(NG.goals_against,0) as goals_against,
        PG.GOAL_DIFF + COALESCE(NG.goals_for,0) - COALESCE(NG.goals_against,0) as cumul_diff,
        (SELECT MAX(game_date) FROM CTE_NEW_GOALS) as game_date
    from CTE_PRIOR_DIFF PG
    LEFT JOIN CTE_NEW_GOALS NG on PG.team_id = NG.team_id
),

CUMUL_WINS AS
(
select
    PW.team_id,
    PW.regulation_wins + COALESCE(NW.regulation_win,0) as regulation_wins,
    PW.regulation_ot_wins + COALESCE(NW.regulation_ot_win,0) as regulation_ot_wins,
    PW.total_wins + COALESCE(NW.win,0) as total_wins,
    (SELECT MAX(game_date) FROM CTE_NEW_WINS) as game_date
from CTE_PRIOR_WINS PW
LEFT JOIN CTE_NEW_WINS NW on PW.team_id = NW.team_id
),

CUMUL_GAMES AS
(
select
    PG.team_id,
    PG.games_played + COALESCE(NG.game_played,0) as games_played
from CTE_PRIOR_GAMES PG
LEFT JOIN CTE_NEW_GAMES NG on PG.team_id = NG.team_id
),

CTE_RANKINGS AS
(

SELECT 
    CPT.GAME_DATE as game_date,
    (SELECT MAX(season) FROM STG_GAMES) as season,
    rank() over (partition by CPT.GAME_DATE order by [CPT.cumul_points, -CG.games_played, CW.regulation_wins, CW.regulation_ot_wins, CW.total_wins] desc) as pre_tie_break_rank,
    CPT.TEAM_ID,
    CPT.cumul_points,
    CD.goals_for,
    CD.goals_against,
    CD.cumul_diff as diff,
    CG.games_played,
    CW.regulation_wins,
    CW.regulation_ot_wins,
    CW.total_wins
FROM CUMUL_POINTS CPT
JOIN CUMUL_DIFF CD ON CPT.TEAM_ID = CD.TEAM_ID
JOIN CUMUL_WINS CW on CPT.TEAM_ID = CW.TEAM_ID
JOIN CUMUL_GAMES CG on CPT.TEAM_ID = CG.TEAM_ID
)

SELECT
    game_date,
    season,
    pre_tie_break_rank,
    team_id,
    cumul_points,
    goals_for,
    goals_against,
    diff,
    games_played,
    regulation_wins,
    regulation_ot_wins,
    total_wins,
    {{ nhl_tie_group_id() }} as tie_group_id
FROM CTE_RANKINGS
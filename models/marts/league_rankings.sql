{{ config(materialized='incremental', schema='marts', unique_key= ['team_id', 'ranking_date']) }}

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


WITH INIT_OR_APPEND AS
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
    UNION
    SELECT
        game_date as ranking_date,
        season,
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
    FROM {{ref('int_league_ranking_pre_tie_breaker')}} RPT
    LEFT JOIN {{ref('int_tied_teams_rate')}} TTR on RPT.team_id = TTR.team_id and RPT.TIE_GROUP_ID = TTR.TIE_GROUP_ID
{% else %}
    SELECT
        game_date as ranking_date,
        season,
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
    FROM {{ref('int_league_ranking_pre_tie_breaker')}} RPT
    LEFT JOIN {{ref('int_tied_teams_rate')}} TTR on RPT.team_id = TTR.team_id and RPT.TIE_GROUP_ID = TTR.TIE_GROUP_ID
{% endif %}
)

SELECT 
    *
FROM INIT_OR_APPEND





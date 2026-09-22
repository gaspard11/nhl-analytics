{{ config(materialized='view', schema= 'staging') }}

select
    g.value:id::int                            as game_id,
    g.value:season::int                         as season,
    g.value:gameDate::string                    as game_date,
    g.value:gameStateId::int                   as game_state,
    g.value:homeTeamId::int                    as home_team_id,
    g.value:homeScore::int                  as home_team_score,
    g.value:visitingTeamId::int                   as away_team_id,
    g.value:visitingScore::int                  as away_team_score,
    CASE 
        WHEN g.value:period::int = 3 THEN 'REG' 
        WHEN g.value:period::int = 4 THEN 'OT' 
        ELSE 'SO' END                       as lastPeriodType,
    fetched_at
from {{ source('nhl_raw', 'GAMES_RAW') }},
     lateral flatten(input => raw_payload:data) g
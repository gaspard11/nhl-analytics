{{ config(materialized='table', schema='staging') }}

select
    g.value:id::int                            as game_id,
    g.value:gameDate::string                    as game_date,
    g.value:gameState::string                   as game_state,
    g.value:gameType::int                       as game_type,
    g.value:homeTeam.id::int                    as home_team_id,
    g.value:homeTeam.score::int                  as home_team_score,
    g.value:awayTeam.id::int                    as away_team_id,
    g.value:awayTeam.score::int                  as away_team_score,
    g.value:gameOutcome:lastPeriodType::string   as lastPeriodType,
    loaded_at
from {{ source('nhl_raw', 'GAMES_RAW') }},
     lateral flatten(input => raw_payload:games) g
{{ config(materialized='view', schema='staging') }}

SELECT
    raw_payload:id::INT as game_id,
    p.value:eventId::INT as event_id,
    p.value:details:eventOwnerTeamId::INT as team_id,
    p.value:situationCode::INT as situation_code,
    p.value:details:homeScore::INT as home_score,
    p.value:details:awayScore::INT as away_score,
    p.value:details:scoringPlayerId::INT       AS scoring_player_id,
    p.value:details:assist1PlayerId::INT       AS assist1_player_id,
    p.value:details:assist2PlayerId::INT       AS assist2_player_id,
    p.value:periodDescriptor:number::INT        AS period_number,
    p.value:timeInPeriod::STRING                 AS time_in_period,
    p.value:timeRemaining::STRING                AS time_remaining_in_period,
    
FROM {{ source('nhl_raw', 'GAME_PBP_RAW') }},
LATERAL FLATTEN(input => raw_payload:plays) p
WHERE p.value:typeDescKey = 'goal' and p.value:periodDescriptor:periodType <> 'SO'
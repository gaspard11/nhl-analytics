{{ config(materialized='table', schema='staging') }}

SELECT
    raw_payload:playerId::INT as player_id,
    raw_payload:firstName.default::STRING as firstName,
    raw_payload:lastName.default::STRING as lastName,
    raw_payload:position::STRING as position,
    raw_payload:headshot::STRING as headshot_url
FROM {{ source('nhl_raw', 'PLAYERS_INFO_RAW') }}
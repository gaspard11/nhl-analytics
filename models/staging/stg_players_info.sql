SELECT
    raw_payload:playerId::INT as player_id,
    raw_payload:firstName.default::STRING as firstName,
    raw_payload:lastName.default::STRING as lastName,
    raw_payload:position::STRING as position,
    raw_payload:currentTeamId::STRING as team_id,
    raw_payload:headshot::STRING as headshot_url,
    fetched_at
FROM {{ source('nhl_raw', 'PLAYERS_INFO_RAW') }}
qualify row_number() over (partition by raw_payload:playerId::int order by fetched_at desc) = 1
-- One row per player, from the latest load of that player in PLAYERS_INFO_RAW.

select
    raw_payload:playerId::int                   as player_id,
    raw_payload:firstName.default::string       as first_name,
    raw_payload:lastName.default::string        as last_name,
    raw_payload:position::string                as position,
    -- Team when the player was loaded. Players are only loaded once, so it can be stale:
    -- dim_players takes the current team from the play-by-play instead.
    raw_payload:currentTeamId::int              as current_team_id,
    raw_payload:headshot::string                as headshot_url,
    fetched_at
from {{ source('nhl_raw', 'PLAYERS_INFO_RAW') }}
qualify row_number() over (partition by raw_payload:playerId::int order by fetched_at desc) = 1

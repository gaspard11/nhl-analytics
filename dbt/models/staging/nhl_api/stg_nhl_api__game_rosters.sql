with latest_payload as (

    select
        raw_payload,
        fetched_at
    from {{ source('nhl_raw', 'GAMES_PBP_RAW') }}
    qualify row_number() over (partition by raw_payload:id::int order by fetched_at desc) = 1

)

select
    latest_payload.raw_payload:id::int          as game_id,
    p.value:playerId::int                       as player_id,
    p.value:teamId::int                         as team_id,
    p.value:firstName:default::string           as first_name,
    p.value:lastName:default::string            as last_name,
    p.value:positionCode::string                as position,
    p.value:sweaterNumber::int                  as sweater_number,
    p.value:headshot::string                    as headshot_url,
    latest_payload.fetched_at
from latest_payload,
    lateral flatten(input => latest_payload.raw_payload:rosterSpots) p

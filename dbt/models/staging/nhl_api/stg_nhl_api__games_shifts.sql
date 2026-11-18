with source as (

    select
        raw_payload,
        fetched_at
    from {{ source('nhl_raw', 'GAMES_SHIFTS_RAW') }}

)


select
    g.value:gameId::int as game_id,
    g.value:teamId::int as team_id,
    g.value:playerId::int as player_id,
    g.value:shiftNumber::int as shift_number,
    g.value:period::int as period,
    g.value:id as shift_id,
    g.value:startTime::string as start_time,
    g.value:endTime::string as end_time,
    g.value:duration::string as duration,
    fetched_at
from source,
    lateral flatten(input => source.raw_payload:data) g
where g.value:typeCode::int = 517
with source as (

    select
        raw_payload,
        fetched_at
    from {{ source('nhl_raw', 'GAMES_SHIFTS_RAW') }}
    -- Latest load of each game. A shift payload has no game id at the top level ({"data": [...],
    -- "total": n}): it's taken from the first shift. The DAG never loads an empty payload
    qualify row_number() over (partition by raw_payload:data[0]:gameId::int order by fetched_at desc) = 1
)


select
    g.value:gameId::int as game_id,
    g.value:teamId::int as team_id,
    g.value:playerId::int as player_id,
    g.value:shiftNumber::int as shift_number,
    g.value:period::int as period,
    g.value:startTime::string as start_time,
    g.value:endTime::string as end_time,
    g.value:duration::string as duration,
    fetched_at
from source,
    lateral flatten(input => source.raw_payload:data) g
where g.value:typeCode::int = 517
qualify row_number() over (partition by game_id, player_id, period, start_time, end_time order by shift_number) = 1
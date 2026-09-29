-- One row per non-shootout goal, from the latest play-by-play load of each game.
-- The latest payload is picked before flattening, so every goal of that game is kept.

with latest_payload as (

    select
        raw_payload,
        fetched_at
    from {{ source('nhl_raw', 'GAMES_PBP_RAW') }}
    qualify row_number() over (partition by raw_payload:id::int order by fetched_at desc) = 1

)

select
    latest_payload.raw_payload:id::int          as game_id,
    p.value:eventId::int                        as event_id,
    p.value:details:eventOwnerTeamId::int       as team_id,
    -- String, not int: codes like '0651' start with a meaningful 0 (goalie pulled)
    p.value:situationCode::string               as situation_code,
    p.value:details:homeScore::int              as home_score,
    p.value:details:awayScore::int              as away_score,
    p.value:details:scoringPlayerId::int        as scoring_player_id,
    p.value:details:assist1PlayerId::int        as assist1_player_id,
    p.value:details:assist2PlayerId::int        as assist2_player_id,
    p.value:periodDescriptor:number::int        as period_number,
    p.value:timeInPeriod::string                as time_in_period,
    p.value:timeRemaining::string               as time_remaining_in_period,
    latest_payload.fetched_at
from latest_payload,
    lateral flatten(input => latest_payload.raw_payload:plays) p
where p.value:typeDescKey::string = 'goal'
  and p.value:periodDescriptor:periodType::string <> 'SO'

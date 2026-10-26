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
    p.value:situationCode::string               as situation_code,
    p.value:typeDescKey::string                 as event_type,
    p.value:details:homeScore::int              as home_score,
    p.value:details:awayScore::int              as away_score,
    p.value:periodDescriptor:number::int        as period_number,
    p.value:periodDescriptor:periodType::string as period_descriptor,
    p.value:timeInPeriod::string                as time_in_period,
    p.value:timeRemaining::string               as time_remaining_in_period,
    p.value:details:zoneCode::string               as zone_code,
    p.value:details:xCoord::int                    as x_coord,
    p.value:details:yCoord::int                    as y_coord,
    case event_type
        when 'goal'                then 'scoring_player_id'
        when 'shot-on-goal'        then 'shooting_player_id'
        when 'missed-shot'         then 'shooting_player_id'
        when 'failed-shot-attempt' then 'shooting_player_id'
        when 'blocked-shot'        then 'shooting_player_id'
        when 'faceoff'             then 'winning_player_id'
        when 'hit'                 then 'hitting_player_id'
        when 'giveaway'            then 'player_id'
        when 'takeaway'            then 'player_id'
        when 'penalty'             then 'received_by_player_id'
        else null
    end::string                                    as player_1_desc,
    case event_type
        when 'goal'                then p.value:details:scoringPlayerId
        when 'shot-on-goal'        then p.value:details:shootingPlayerId
        when 'missed-shot'         then p.value:details:shootingPlayerId
        when 'failed-shot-attempt' then p.value:details:shootingPlayerId
        when 'blocked-shot'        then p.value:details:blockingPlayerId
        when 'faceoff'             then p.value:details:winningPlayerId
        when 'hit'                 then p.value:details:hittingPlayerId
        when 'giveaway'            then p.value:details:playerId
        when 'takeaway'            then p.value:details:playerId
        when 'penalty'             then p.value:details:committedByPlayerId
        else null
    end::int                                    as player_1_id,
    case event_type
        when 'goal'                then 'assist1_player_id'
        when 'blocked-shot'        then 'shooting_player_id'
        when 'faceoff'             then 'loosing_player_id'
        when 'hit'                 then 'hittee_player_id'
        when 'penalty'             then 'drawn_by_player_id'
    end::string                                    as player_2_desc,
    case event_type
        when 'goal'                then p.value:details:assist1PlayerId
        when 'blocked-shot'        then p.value:details:shootingPlayerId
        when 'faceoff'             then p.value:details:losingPlayerId
        when 'hit'                 then p.value:details:hitteePlayerId
        when 'penalty'             then p.value:details:drawnByPlayerId
    end::int                                    as player_2_id,
    case event_type
        when 'goal'                then 'assist2_player_id'
        when 'penalty'             then 'served_by_player_id'
    end::string                                   as player_3_desc,
    case event_type
        when 'goal'                then p.value:details:assist2PlayerId
        when 'penalty'             then p.value:details:servedByPlayerId
    end::int                                    as player_3_id,
    p.value:details:goalieInNetId::int             as goalie_in_net_id,
    p.value:details                                as details,
    latest_payload.fetched_at
from latest_payload,
    lateral flatten(input => latest_payload.raw_payload:plays) p
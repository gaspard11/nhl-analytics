-- One row per finished regular-season game, from the latest load of that game in GAMES_RAW.
-- GAMES_RAW keeps every load, so a game loaded several times appears several times in raw.

with source as (

    select
        raw_payload,
        fetched_at
    from {{ source('nhl_raw', 'GAMES_RAW') }}

)

select
    g.value:id::int                 as game_id,
    g.value:season::int             as season,
    g.value:gameDate::date          as game_date,
    g.value:gameStateId::int        as game_state,
    g.value:homeTeamId::int         as home_team_id,
    g.value:homeScore::int          as home_team_score,
    g.value:visitingTeamId::int     as away_team_id,
    g.value:visitingScore::int      as away_team_score,
    -- Regular season only: one OT period (4), then shootout
    case
        when g.value:period::int = 3 then 'REG'
        when g.value:period::int = 4 then 'OT'
        else 'SO'
    end                             as last_period_type,
    source.fetched_at
from source,
    lateral flatten(input => source.raw_payload:data) g
-- gameStateId 7 = final
where g.value:gameStateId::int = 7
qualify row_number() over (partition by g.value:id::int order by source.fetched_at desc) = 1

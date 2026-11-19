-- On the latest ranking date of each season, the season-to-date totals in fct_goalie_stats must equal
-- a sum from scratch over int_player_game_stats and int_goalie_game_stats. Catches drift from
-- incremental runs on the goalie side.
-- Returns the goalies whose stored totals differ from the recomputed ones.

with latest as (

    select
        season,
        max(ranking_date) as ranking_date
    from {{ ref('fct_goalie_stats') }}
    group by season

),

stored as (

    select
        c.season,
        c.player_id,
        c.games_played,
        c.toi_seconds,
        c.goals_against,
        c.saves,
        c.shutouts
    from {{ ref('fct_goalie_stats') }} c
    join latest l
        on l.season = c.season
       and l.ranking_date = c.ranking_date

),

game_stats as (

    select game_id, player_id, stat_name, stat_value from {{ ref('int_player_game_stats') }}
    union all
    select game_id, player_id, stat_name, stat_value from {{ ref('int_goalie_game_stats') }}

),

recomputed as (

    select
        g.season,
        s.player_id,
        sum(iff(s.stat_name = 'toi_seconds', 1, 0))              as games_played,
        sum(iff(s.stat_name = 'toi_seconds', s.stat_value, 0))   as toi_seconds,
        sum(iff(s.stat_name = 'goals_against', s.stat_value, 0)) as goals_against,
        sum(iff(s.stat_name = 'saves', s.stat_value, 0))         as saves,
        sum(iff(s.stat_name = 'shutout', s.stat_value, 0))       as shutouts
    from game_stats s
    join {{ ref('stg_nhl_api__games') }} g
        on g.game_id = s.game_id
    join {{ ref('dim_players') }} p
        on p.player_id = s.player_id
       and p.position = 'G'
    join latest l
        on l.season = g.season
       and g.game_date <= l.ranking_date
    group by g.season, s.player_id
    -- Same rule as the mart: a goalie appears from their first game
    having sum(iff(s.stat_name = 'toi_seconds', 1, 0)) > 0

)

select
    coalesce(s.season, r.season)       as season,
    coalesce(s.player_id, r.player_id) as player_id,
    s.games_played                     as stored_games_played,
    r.games_played                     as recomputed_games_played,
    s.toi_seconds                      as stored_toi_seconds,
    r.toi_seconds                      as recomputed_toi_seconds,
    s.goals_against                    as stored_goals_against,
    r.goals_against                    as recomputed_goals_against,
    s.saves                            as stored_saves,
    r.saves                            as recomputed_saves,
    s.shutouts                         as stored_shutouts,
    r.shutouts                         as recomputed_shutouts
from stored s
full outer join recomputed r
    on r.season = s.season
   and r.player_id = s.player_id
where s.player_id is null
   or r.player_id is null
   or s.games_played  <> r.games_played
   or s.toi_seconds   <> r.toi_seconds
   or s.goals_against <> r.goals_against
   or s.saves         <> r.saves
   or s.shutouts      <> r.shutouts

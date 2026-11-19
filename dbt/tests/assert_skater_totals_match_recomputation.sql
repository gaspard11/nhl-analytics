-- On the latest ranking date of each season, the season-to-date totals in fct_skater_stats must equal
-- a sum from scratch over int_player_game_stats. Catches drift from incremental runs on the skater side.
-- Returns the skaters whose stored totals differ from the recomputed ones.

with latest as (

    select
        season,
        max(ranking_date) as ranking_date
    from {{ ref('fct_skater_stats') }}
    group by season

),

stored as (

    select
        c.season,
        c.player_id,
        c.games_played,
        c.toi_seconds,
        c.goals,
        c.assists
    from {{ ref('fct_skater_stats') }} c
    join latest l
        on l.season = c.season
       and l.ranking_date = c.ranking_date

),

recomputed as (

    select
        g.season,
        s.player_id,
        sum(iff(s.stat_name = 'toi_seconds', 1, 0))            as games_played,
        sum(iff(s.stat_name = 'toi_seconds', s.stat_value, 0)) as toi_seconds,
        sum(iff(s.stat_name = 'goals', s.stat_value, 0))       as goals,
        sum(iff(s.stat_name = 'assists', s.stat_value, 0))     as assists
    from {{ ref('int_player_game_stats') }} s
    join {{ ref('stg_nhl_api__games') }} g
        on g.game_id = s.game_id
    join {{ ref('dim_players') }} p
        on p.player_id = s.player_id
       and p.position <> 'G'
    join latest l
        on l.season = g.season
       and g.game_date <= l.ranking_date
    group by g.season, s.player_id
    -- Same rule as the mart: a skater appears from their first game
    having sum(iff(s.stat_name = 'toi_seconds', 1, 0)) > 0

)

select
    coalesce(s.season, r.season)       as season,
    coalesce(s.player_id, r.player_id) as player_id,
    s.games_played                     as stored_games_played,
    r.games_played                     as recomputed_games_played,
    s.toi_seconds                      as stored_toi_seconds,
    r.toi_seconds                      as recomputed_toi_seconds,
    s.goals                            as stored_goals,
    r.goals                            as recomputed_goals,
    s.assists                          as stored_assists,
    r.assists                          as recomputed_assists
from stored s
full outer join recomputed r
    on r.season = s.season
   and r.player_id = s.player_id
where s.player_id is null
   or r.player_id is null
   or s.games_played <> r.games_played
   or s.toi_seconds  <> r.toi_seconds
   or s.goals        <> r.goals
   or s.assists      <> r.assists

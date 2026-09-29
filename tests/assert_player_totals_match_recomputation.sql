-- On the latest ranking date of each season, the cumulative goals and assists in
-- int_player_scoring_cumulative must equal a recomputation from scratch over the play-by-play.
-- Catches drift from incremental runs on the player side.
-- Returns the players whose stored totals differ from the recomputed ones.

with latest as (

    select
        season,
        max(ranking_date) as ranking_date
    from {{ ref('int_player_scoring_cumulative') }}
    group by season

),

stored as (

    select
        c.season,
        c.player_id,
        c.number_of_goals,
        c.number_of_assists
    from {{ ref('int_player_scoring_cumulative') }} c
    join latest l
        on l.season = c.season
       and l.ranking_date = c.ranking_date

),

goals as (

    select
        g.season,
        g.game_date,
        p.scoring_player_id,
        p.assist1_player_id,
        p.assist2_player_id
    from {{ ref('stg_nhl_api__goals') }} p
    join {{ ref('stg_nhl_api__games') }} g
        on g.game_id = p.game_id

),

player_events as (

    select season, game_date, scoring_player_id as player_id, 1 as goals, 0 as assists
    from goals
    where scoring_player_id is not null

    union all

    select season, game_date, assist1_player_id as player_id, 0 as goals, 1 as assists
    from goals
    where assist1_player_id is not null

    union all

    select season, game_date, assist2_player_id as player_id, 0 as goals, 1 as assists
    from goals
    where assist2_player_id is not null

),

recomputed as (

    select
        e.season,
        e.player_id,
        sum(e.goals)   as number_of_goals,
        sum(e.assists) as number_of_assists
    from player_events e
    join latest l
        on l.season = e.season
       and e.game_date <= l.ranking_date
    group by e.season, e.player_id

)

select
    coalesce(s.season, r.season)       as season,
    coalesce(s.player_id, r.player_id) as player_id,
    s.number_of_goals                  as stored_goals,
    r.number_of_goals                  as recomputed_goals,
    s.number_of_assists                as stored_assists,
    r.number_of_assists                as recomputed_assists
from stored s
full outer join recomputed r
    on r.season = s.season
   and r.player_id = s.player_id
where coalesce(s.number_of_goals, -1)   <> coalesce(r.number_of_goals, 0)
   or coalesce(s.number_of_assists, -1) <> coalesce(r.number_of_assists, 0)

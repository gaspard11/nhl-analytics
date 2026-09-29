-- For every finished game, the number of goals in the play-by-play must match the final score.
-- The final score counts the shootout winner as one goal, but stg_nhl_api__goals excludes shootout goals,
-- so one goal is subtracted for games decided in a shootout.
-- Catches a play-by-play payload loaded before the game ended (incomplete goals), or never loaded.
-- Returns the games whose play-by-play doesn't match the score.

with pbp_goals as (

    select
        game_id,
        count(*) as pbp_goals
    from {{ ref('stg_nhl_api__goals') }}
    group by game_id

)

select
    g.game_id,
    g.season,
    g.game_date,
    g.home_team_score,
    g.away_team_score,
    g.last_period_type,
    g.home_team_score + g.away_team_score - iff(g.last_period_type = 'SO', 1, 0) as expected_goals,
    coalesce(p.pbp_goals, 0)                                                     as pbp_goals
from {{ ref('stg_nhl_api__games') }} g
left join pbp_goals p
    on p.game_id = g.game_id
where g.home_team_score + g.away_team_score - iff(g.last_period_type = 'SO', 1, 0)
      <> coalesce(p.pbp_goals, 0)

-- Every ranking date must have every team, and ranks must start at 1
-- (except on day 0, where nobody has played and every team is ranked last).
-- Catches a partially written day or a team missing from the nhl_teams seed.
-- Returns the incomplete ranking dates.

select
    season,
    ranking_date,
    count(*)          as teams,
    min(ranking)      as best_ranking,
    max(games_played) as max_games_played
from {{ ref('fct_league_rankings') }}
group by season, ranking_date
having count(*) <> (select count(*) from {{ ref('nhl_teams') }})
    or (max(games_played) > 0 and min(ranking) <> 1)

-- Across the whole league, on every ranking date:
--   - every game has exactly one winner: total wins = team games played / 2
--   - every goal scored is a goal conceded: goals for = goals against
-- Catches a game counted for only one of its two teams, or home and away inverted,
-- which checking each team alone can't detect.
-- Returns the ranking dates where the league totals don't balance.

select
    season,
    ranking_date,
    sum(total_wins)    as league_wins,
    sum(games_played)  as league_team_games,
    sum(goals_for)     as league_goals_for,
    sum(goals_against) as league_goals_against
from {{ ref('league_rankings') }}
group by season, ranking_date
having sum(total_wins) * 2 <> sum(games_played)
    or sum(goals_for) <> sum(goals_against)

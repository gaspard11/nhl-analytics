-- Rules that hold for every team on every ranking date:
--   - wins can't exceed games played
--   - regulation wins <= regulation + OT wins <= total wins
--   - every win is worth 2 points, and each loss at most 1 (OT/SO loss)
--   - goal differential = goals for - goals against
-- Catches a result flag computed wrong in int_team_game_results, or swapped columns.
-- Returns the rows that break a rule.

select *
from {{ ref('fct_league_rankings') }}
where total_wins > games_played
   or regulation_wins > regulation_ot_wins
   or regulation_ot_wins > total_wins
   or points < 2 * total_wins
   or points - 2 * total_wins > games_played - total_wins
   or goal_diff <> goals_for - goals_against

-- In every game, the faceoffs won by all the players add up to the faceoffs lost: each faceoff has
-- one winner and one loser. Catches a faceoff event with a missing player id, which would count for
-- one side only.
-- Returns the games where the two totals differ.

select
    game_id,
    sum(iff(stat_name = 'faceoffs_won', stat_value, 0))  as faceoffs_won,
    sum(iff(stat_name = 'faceoffs_lost', stat_value, 0)) as faceoffs_lost
from {{ ref('int_skater_game_stats') }}
where stat_name in ('faceoffs_won', 'faceoffs_lost')
group by game_id
having sum(iff(stat_name = 'faceoffs_won', stat_value, 0))
    <> sum(iff(stat_name = 'faceoffs_lost', stat_value, 0))

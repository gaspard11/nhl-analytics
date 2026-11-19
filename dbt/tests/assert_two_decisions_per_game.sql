-- Every finished game gives exactly two goalie decisions: one win, and one loss or OT loss.
-- Catches a game where no goalie of record was found (missing shifts) or two goalies of the same
-- team got the decision.
-- Returns the games with a different set of decisions.

with decisions as (

    select
        game_id,
        count_if(stat_name = 'awarded_wins')                                  as wins,
        count_if(stat_name in ('awarded_losses', 'awarded_ot_losses'))       as losses
    from {{ ref('int_goalie_game_stats') }}
    where stat_name in ('awarded_wins', 'awarded_losses', 'awarded_ot_losses')
    group by game_id

)

select
    g.game_id,
    coalesce(d.wins, 0)   as wins,
    coalesce(d.losses, 0) as losses
from {{ ref('stg_nhl_api__games') }} g
left join decisions d
    on d.game_id = g.game_id
where coalesce(d.wins, 0) <> 1
   or coalesce(d.losses, 0) <> 1

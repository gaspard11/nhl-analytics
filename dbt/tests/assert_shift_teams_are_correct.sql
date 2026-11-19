-- Every shift belongs to one of the two teams of its game. Catches a shift chart holding the shifts
-- of another game (game 2025020565: Vegas and San Jose shifts in Buffalo at New Jersey).
-- Returns each game with a team that didn't play in it, once.

with games as (
    select * from {{ ref('stg_nhl_api__games') }}
),

shifts as (
    select * from {{ ref('stg_nhl_api__games_shifts') }}
)

select distinct
    s.game_id,
    s.team_id
from shifts s
join games g
    on s.game_id = g.game_id
where s.team_id <> g.home_team_id
  and s.team_id <> g.away_team_id

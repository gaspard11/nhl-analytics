with games as (
    select * from {{ ref('stg_nhl_api__games') }}

),

shifts as (
    select * from {{ ref('stg_nhl_api__games_shifts') }}
)


select
    s.game_id,
    s.team_id
from shifts s join games g on s.game_id = g.game_id
where s.team_id <> g.home_team_id and s.team_id <> g.away_team_id

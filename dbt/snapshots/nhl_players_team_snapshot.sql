{% snapshot nhl_players_team_snapshot %}

{{
    config(
      schema='snapshots',
      unique_key='player_id',
      strategy='timestamp',
      updated_at='team_since',
    )
}} 


with player_games as (
    select 
        rosters.player_id,
        rosters.team_id,
        games.game_date
    from {{ ref('fct_game_rosters') }} rosters
    join {{ ref('fct_games') }} games on rosters.game_id = games.game_id
    where games.game_date <= '{{ var("as_of", run_started_at.strftime("%Y-%m-%d")) }}'
),


current_team as(
    select
        player_id,
        team_id
    from player_games
    qualify row_number() over (partition by player_id order by game_date desc) = 1
),

last_other_team as (
    select
        ct.player_id,
        max(pg.game_date) as last_other_team_date
    from  current_team ct 
    join player_games pg on ct.player_id = pg.player_id
    where ct.team_id <> pg.team_id
    group by ct.player_id
),

player_team_since as (
    select
        ct.player_id,
        ct.team_id,
        min(pg.game_date::timestamp) as team_since
    from  current_team ct 
    join player_games pg on ct.player_id = pg.player_id and ct.team_id = pg.team_id
    left join last_other_team lot on lot.player_id = ct.player_id
    where   pg.game_date > coalesce(lot.last_other_team_date, '1900-01-01')
    group by ct.player_id, ct.team_id
)

select
    player_id,
    team_id,
    team_since
from player_team_since


{% endsnapshot %}
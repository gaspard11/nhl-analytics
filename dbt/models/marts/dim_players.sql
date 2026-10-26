{{ config(materialized='incremental', unique_key='player_id', incremental_strategy='merge') }}

-- One row per player who has dressed for at least one game, with the team, sweater number and
-- details of their most recent game (from the play-by-play rosters).

with new_games_rosters as (
    select
        rosters.game_id,
        player_id,
        team_id,
        first_name,
        last_name,
        position,
        sweater_number,
        headshot_url,
        rosters.fetched_at
    from {{ ref('stg_nhl_api__game_rosters') }} rosters
    join {{ ref('stg_nhl_api__games') }} games
        on games.game_id = rosters.game_id
    {% if is_incremental() %}
    where rosters.fetched_at > (select max(fetched_at) from {{ this }})
    {% endif %}
    qualify row_number() over (partition by rosters.player_id order by games.game_date desc) = 1


)

select
    player_id,
    first_name,
    last_name,
    position,
    team_id,
    sweater_number,
    headshot_url,
    fetched_at
from new_games_rosters

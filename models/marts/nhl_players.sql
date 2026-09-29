{{ config(materialized='incremental', unique_key='player_id', incremental_strategy='merge') }}

WITH STG_GAMES_PBP AS
(
    SELECT
        p.scoring_player_id,
        p.assist1_player_id,
        p.assist2_player_id,
        p.team_id,
        g.game_date,
        greatest(p.fetched_at, g.fetched_at) as fetched_at
    FROM {{ref('stg_games_pbp')}} p
    JOIN {{ref('stg_games')}} g on p.game_id = g.game_id
    {% if is_incremental() %}
    where greatest(p.fetched_at, g.fetched_at) > (select max(fetched_at) from {{ this }})
    {% endif %}
),

CTE_PLAYER_CURRENT_TEAM AS
(
    SELECT * FROM
    (
    SELECT scoring_player_id as player_id, team_id, game_date, fetched_at
    FROM STG_GAMES_PBP
    where scoring_player_id is not null
    UNION ALL
    SELECT assist1_player_id as player_id, team_id, game_date, fetched_at
    FROM STG_GAMES_PBP
    where assist1_player_id is not null
    UNION ALL
    SELECT assist2_player_id as player_id, team_id, game_date, fetched_at
    FROM STG_GAMES_PBP
    where assist2_player_id is not null
    )
    qualify row_number() over (partition by player_id order by game_date desc) = 1
)

select
    a.player_id,
    a.firstName,
    a.lastName,
    a.position,
    b.team_id,
    a.headshot_url,
    b.fetched_at
from {{ref('stg_players_info')}} a
join CTE_PLAYER_CURRENT_TEAM b on a.player_id = b.player_id
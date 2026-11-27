{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}


select
    s.*,
    r.team_id
from {{ ref('int_skater_game_stats') }} s 
join {{ ref('stg_nhl_api__game_rosters') }} r on s.player_id = r.player_id
union all

select
    s.*,
    r.team_id
from {{ ref('int_player_game_stats') }} s 
join {{ ref('stg_nhl_api__game_rosters') }} r on s.player_id = r.player_id
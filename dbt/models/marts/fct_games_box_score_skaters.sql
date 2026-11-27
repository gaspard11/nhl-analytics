{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='game_id') }}


select
    s.*,
    r.team_id
from {{ ref('int_skater_game_stats') }} s 
join {{ ref('stg_nhl_api__game_rosters') }} r
on r.game_id = s.game_id
and r.player_id = s.player_id
union all

select
    s.*,
    r.team_id
from {{ ref('int_player_game_stats') }} s 
join {{ ref('stg_nhl_api__game_rosters') }} r
on r.game_id = s.game_id
and r.player_id = s.player_id
where r.position <> 'G'

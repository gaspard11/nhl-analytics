{{ config(materialized='incremental', schema='marts', unique_key= 'player_id') }}

select
    player_id,
    firstName,
    lastName,
    position,
    team_id,
    headshot_url
from {{ref('stg_players')}}
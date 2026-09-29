{% snapshot nhl_players_team_snapshot %}

{{
    config(
      schema='snapshots',
      unique_key='player_id',
      strategy='check',
      check_cols=['team_id'],
    )
}}

select
    player_id,
    team_id
from {{ ref('dim_players') }}

{% endsnapshot %}
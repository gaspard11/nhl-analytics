-- The 32 NHL teams, from the nhl_teams seed.

select
    team_id,
    conference_name,
    division_name,
    logo_url,
    name
from {{ ref('nhl_teams') }}

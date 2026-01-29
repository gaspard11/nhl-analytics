select
  home.team_name as home_team,
  away.team_name as away_team,
  home_team_score,
  away_team_score,
  game_date
from {{ source('nhl_raw', 'nhl_scores') }} scores
join {{ source('nhl_raw', 'nhl_teams_definition') }} home on scores.home_team_id = home.team_id
join {{ source('nhl_raw', 'nhl_teams_definition') }} away on scores.away_team_id = away.team_id
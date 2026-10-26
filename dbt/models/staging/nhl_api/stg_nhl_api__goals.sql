-- One row per non-shootout goal, from the latest play-by-play load of each game.
-- The latest payload is picked before flattening, so every goal of that game is kept.

select
    game_id,
    event_id,
    team_id,
    situation_code,
    home_score,
    away_score,
    player_1_id        as scoring_player_id,
    player_2_id        as assist1_player_id,
    player_3_id        as assist2_player_id,
    period_number,
    time_in_period,
    time_remaining_in_period,
    fetched_at
from {{ ref('stg_nhl_api__pbp') }},
where event_type = 'goal'
  and period_descriptor <> 'SO'

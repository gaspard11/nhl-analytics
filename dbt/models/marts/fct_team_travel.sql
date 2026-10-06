-- One row per team per game: the arena of the game and the arena of the team's previous game,
-- with the distance between the two. Feeds the travel map of the app.

with team_games as (

    select
        game_id,
        season,
        game_date,
        home_team_id as team_id,
        home_team_id as venue_team_id,
        true as is_home
    from {{ ref('fct_games') }}

    union all

    select
        game_id,
        season,
        game_date,
        away_team_id as team_id,
        home_team_id as venue_team_id,
        false as is_home
    from {{ ref('fct_games') }}

),

located as (

    select
        team_games.game_id,
        team_games.season,
        team_games.game_date,
        team_games.team_id,
        team_games.is_home,
        venues.arena_name,
        venues.arena_latitude,
        venues.arena_longitude
    from team_games
    inner join {{ ref('dim_teams') }} as venues
        on team_games.venue_team_id = venues.team_id

),

with_previous as (

    select
        *,
        lag(arena_name) over (partition by team_id, season order by game_date, game_id) as previous_arena_name,
        lag(arena_latitude) over (partition by team_id, season order by game_date, game_id) as previous_arena_latitude,
        lag(arena_longitude) over (partition by team_id, season order by game_date, game_id) as previous_arena_longitude
    from located

)

select
    game_id,
    season,
    game_date,
    team_id,
    is_home,
    previous_arena_name,
    previous_arena_latitude,
    previous_arena_longitude,
    arena_name,
    arena_latitude,
    arena_longitude,
    -- null for the team's first game of the season; 0 during a home stand or a stay in the same city
    haversine(previous_arena_latitude, previous_arena_longitude, arena_latitude, arena_longitude) as distance_km
from with_previous

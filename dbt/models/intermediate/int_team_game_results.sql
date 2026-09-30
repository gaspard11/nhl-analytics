-- One row per team per finished game: the home and away sides of each game, unioned,
-- with the result from that team's point of view.

with games as (

    select * from {{ ref('stg_nhl_api__games') }}

),

home as (

    select
        game_id,
        game_date,
        season,
        home_team_id        as team_id,
        away_team_id        as opponent_team_id,
        true                as is_home,
        home_team_score     as goals_for,
        away_team_score     as goals_against,
        last_period_type,
        fetched_at
    from games

),

away as (

    select
        game_id,
        game_date,
        season,
        away_team_id        as team_id,
        home_team_id        as opponent_team_id,
        false               as is_home,
        away_team_score     as goals_for,
        home_team_score     as goals_against,
        last_period_type,
        fetched_at
    from games

),

team_games as (

    select * from home
    union all
    select * from away

)

select
    game_id,
    game_date,
    season,
    team_id,
    opponent_team_id,
    is_home,
    goals_for,
    goals_against,
    last_period_type,
    fetched_at,
    iff(goals_for > goals_against, 1, 0)                                as win,
    iff(goals_for > goals_against and last_period_type = 'REG', 1, 0)   as regulation_win,
    iff(goals_for > goals_against and last_period_type <> 'SO', 1, 0)   as regulation_ot_win,
    case
        when goals_for > goals_against then 2
        when last_period_type <> 'REG' then 1   -- overtime or shootout loss
        else 0
    end                                                                 as points
from team_games

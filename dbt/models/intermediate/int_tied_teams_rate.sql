-- Head-to-head tie-breaker: for each tie group on each ranking date, the points % of each
-- tied team in games played so far this season against the other teams of its tie group.
-- When two teams played an odd number of games, the oldest game hosted by the team with
-- the extra home game is excluded (NHL rule).

with games as (

    select * from {{ ref('stg_nhl_api__games') }}

),

standings as (

    select * from {{ ref('int_league_ranking_pre_tie_breaker') }}

),

-- Games played up to the ranking date between two teams of the same tie group
tied_team_games as (

    select
        home_team.season,
        home_team.ranking_date,
        home_team.tie_group_id,
        games.game_date,
        games.game_id,
        games.home_team_id,
        games.away_team_id,
        games.home_team_score,
        games.away_team_score,
        games.last_period_type,
        {{ nhl_matchups_ids() }} as matchup_id
    from games
    join standings home_team
        on  home_team.team_id = games.home_team_id
        and home_team.season = games.season
        and games.game_date <= home_team.ranking_date
    join standings away_team
        on  away_team.team_id = games.away_team_id
        and away_team.season = home_team.season
        and away_team.ranking_date = home_team.ranking_date
        and away_team.tie_group_id = home_team.tie_group_id
    where home_team.tie_group_id is not null

),

matchup_games as (

    select
        season,
        ranking_date,
        tie_group_id,
        matchup_id,
        game_id,
        game_date,
        home_team_id,
        away_team_id,
        home_team_score,
        away_team_score,
        last_period_type,
        count(*) over (partition by season, ranking_date, tie_group_id, matchup_id) as matchup_game_count
    from tied_team_games

),

-- Number of home games of each team, per matchup
home_game_counts as (

    select
        season,
        ranking_date,
        tie_group_id,
        matchup_id,
        home_team_id,
        count(*) as home_game_count
    from matchup_games
    group by season, ranking_date, tie_group_id, matchup_id, home_team_id

),

-- Team with the most home games in each matchup
top_home_teams as (

    select
        season,
        ranking_date,
        tie_group_id,
        matchup_id,
        home_team_id as top_home_team_id
    from home_game_counts
    qualify row_number() over (
        partition by season, ranking_date, tie_group_id, matchup_id
        order by home_game_count desc, home_team_id
    ) = 1

),

-- Oldest game hosted by that team
oldest_top_home_games as (

    select
        matchup_games.season,
        matchup_games.ranking_date,
        matchup_games.tie_group_id,
        matchup_games.matchup_id,
        matchup_games.game_id
    from matchup_games
    join top_home_teams
        on  matchup_games.season = top_home_teams.season
        and matchup_games.ranking_date = top_home_teams.ranking_date
        and matchup_games.tie_group_id = top_home_teams.tie_group_id
        and matchup_games.matchup_id = top_home_teams.matchup_id
        and matchup_games.home_team_id = top_home_teams.top_home_team_id
    qualify row_number() over (
        partition by matchup_games.season, matchup_games.ranking_date,
                     matchup_games.tie_group_id, matchup_games.matchup_id
        order by matchup_games.game_date, matchup_games.game_id
    ) = 1

),

-- Odd number of games: the oldest game at the top home team doesn't count
counted_games as (

    select matchup_games.*
    from matchup_games
    left join oldest_top_home_games
        on  matchup_games.season = oldest_top_home_games.season
        and matchup_games.ranking_date = oldest_top_home_games.ranking_date
        and matchup_games.tie_group_id = oldest_top_home_games.tie_group_id
        and matchup_games.matchup_id = oldest_top_home_games.matchup_id
        and matchup_games.game_id = oldest_top_home_games.game_id
    where matchup_games.matchup_game_count % 2 = 0
       or oldest_top_home_games.game_id is null

),

-- One row per team per counted game
team_games as (

    select
        season,
        ranking_date,
        tie_group_id,
        game_id,
        home_team_id        as team_id,
        home_team_score     as team_score,
        away_team_score     as opponent_score,
        last_period_type
    from counted_games

    union all

    select
        season,
        ranking_date,
        tie_group_id,
        game_id,
        away_team_id        as team_id,
        away_team_score     as team_score,
        home_team_score     as opponent_score,
        last_period_type
    from counted_games

),

team_stats as (

    select
        season,
        ranking_date,
        tie_group_id,
        team_id,
        count(distinct game_id) as games_played,
        sum(
            case
                when team_score > opponent_score then 2                             -- win
                when last_period_type in ('OT', 'SO') then 1                        -- OT or SO loss
                else 0                                                              -- regulation loss
            end
        )                       as points_earned
    from team_games
    group by season, ranking_date, tie_group_id, team_id

)

select
    season,
    ranking_date,
    tie_group_id,
    team_id,
    points_earned,
    games_played,
    points_earned / (games_played * 2) as tie_rate
from team_stats

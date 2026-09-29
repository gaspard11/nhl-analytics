WITH CTE_DEDUP_GAMES_TIED_TEAMS AS
(
SELECT DISTINCT
    GH.GAME_DATE,
    GH.GAME_ID,
    GH.HOME_TEAM_ID,
    GH.AWAY_TEAM_ID,
    GH.HOME_TEAM_SCORE,
    GH.AWAY_TEAM_SCORE,
    RP_HOME.TIE_GROUP_ID,
    GH.last_period_type,
    {{nhl_matchups_ids()}} as matchup_id
FROM {{ ref('games_history') }} GH
JOIN {{ ref('int_league_ranking_pre_tie_breaker') }} RP_HOME
    ON RP_HOME.TEAM_ID = GH.HOME_TEAM_ID
JOIN {{ ref('int_league_ranking_pre_tie_breaker') }} RP_AWAY
    ON RP_AWAY.TEAM_ID = GH.AWAY_TEAM_ID
   AND RP_AWAY.TIE_GROUP_ID = RP_HOME.TIE_GROUP_ID
WHERE RP_HOME.TIE_GROUP_ID IS NOT NULL
),

CTE_BASE as (
    select
        game_id,
        game_date,
        home_team_id,
        away_team_id,
        matchup_id,
        home_team_score,
        away_team_score,
        last_period_type,
        tie_group_id,
        count(*) over (partition by tie_group_id, matchup_id) as matchup_game_count
    from CTE_DEDUP_GAMES_TIED_TEAMS

),

CTE_HOME_COUNTS as (
    select
        matchup_id,
        home_team_id,
        count(*) as home_count
    from CTE_BASE
    group by matchup_id, home_team_id

),

CTE_TOP_HOME as (
    select
        matchup_id,
        home_team_id as top_home_team_id,
        row_number() over (
            partition by matchup_id
            order by home_count desc, home_team_id
        ) as rn
    from CTE_HOME_COUNTS

),

CTE_TOP_HOME_FINAL as (
    select matchup_id, top_home_team_id
    from CTE_TOP_HOME
    where rn = 1
),

CTE_OLDEST_GAME as (
    select
        b.matchup_id,
        b.game_id,
        row_number() over (
            partition by b.matchup_id
            order by b.game_date asc, b.game_id
        ) as rn_oldest
    from CTE_BASE b
    inner join CTE_TOP_HOME_FINAL t
        on b.matchup_id = t.matchup_id
        and b.home_team_id = t.top_home_team_id

),

CTE_LABELED_GAMES AS (
    select
    b.*,
    case
        when b.matchup_game_count % 2 = 0 then 1
        when og.rn_oldest = 1 then 0
        else 1
    end as flag
from CTE_BASE b
left join CTE_OLDEST_GAME og
    on b.matchup_id = og.matchup_id
    and b.game_id = og.game_id
    and og.rn_oldest = 1
),


CTE_TEAM_GAMES AS (
    SELECT
        GAME_ID,
        TIE_GROUP_ID,
        HOME_TEAM_ID AS TEAM_ID,
        HOME_TEAM_SCORE AS TEAM_SCORE,
        AWAY_TEAM_SCORE AS OPPONENT_SCORE,
        LAST_PERIOD_TYPE
    FROM CTE_LABELED_GAMES
    WHERE FLAG = 1

    UNION ALL

    SELECT
        GAME_ID,
        TIE_GROUP_ID,
        AWAY_TEAM_ID AS TEAM_ID,
        AWAY_TEAM_SCORE AS TEAM_SCORE,
        HOME_TEAM_SCORE AS OPPONENT_SCORE,
        LAST_PERIOD_TYPE
    FROM CTE_LABELED_GAMES
    WHERE FLAG = 1

),

CTE_TEAM_STATS AS (
    SELECT
        TIE_GROUP_ID,
        TEAM_ID,

        COUNT(DISTINCT GAME_ID) AS GAMES_PLAYED,

        SUM(
            CASE
                -- Win
                WHEN TEAM_SCORE > OPPONENT_SCORE THEN 2

                -- Loss in OT or SO
                WHEN TEAM_SCORE < OPPONENT_SCORE
                     AND LAST_PERIOD_TYPE IN ('OT', 'SO') THEN 1

                -- Regulation loss
                ELSE 0
            END
        ) AS POINTS_EARNED

    FROM CTE_TEAM_GAMES
    GROUP BY
        TIE_GROUP_ID,
        TEAM_ID
)

SELECT 
    TIE_GROUP_ID,
    TEAM_ID,
    POINTS_EARNED,
    GAMES_PLAYED,
    POINTS_EARNED / (GAMES_PLAYED*2) as tie_rate
FROM CTE_TEAM_STATS
ORDER BY
    TIE_GROUP_ID,
    TEAM_ID
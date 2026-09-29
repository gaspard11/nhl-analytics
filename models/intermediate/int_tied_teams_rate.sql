WITH CTE_DEDUP_GAMES_TIED_TEAMS AS
(
SELECT
    RP_HOME.SEASON,                                          
    RP_HOME.RANKING_DATE,                                   
    RP_HOME.TIE_GROUP_ID,
    GH.GAME_DATE,
    GH.GAME_ID,
    GH.HOME_TEAM_ID,
    GH.AWAY_TEAM_ID,
    GH.HOME_TEAM_SCORE,
    GH.AWAY_TEAM_SCORE,
    GH.LAST_PERIOD_TYPE,                   
    {{ nhl_matchups_ids() }} AS MATCHUP_ID
FROM {{ ref('stg_games') }} GH                               
JOIN {{ ref('int_league_ranking_pre_tie_breaker') }} RP_HOME
    ON  RP_HOME.TEAM_ID = GH.HOME_TEAM_ID
    AND RP_HOME.SEASON = GH.SEASON                           
    AND GH.GAME_DATE <= RP_HOME.RANKING_DATE                  
JOIN {{ ref('int_league_ranking_pre_tie_breaker') }} RP_AWAY
    ON  RP_AWAY.TEAM_ID = GH.AWAY_TEAM_ID
    AND RP_AWAY.SEASON = RP_HOME.SEASON                      
    AND RP_AWAY.RANKING_DATE = RP_HOME.RANKING_DATE        
    AND RP_AWAY.TIE_GROUP_ID = RP_HOME.TIE_GROUP_ID
WHERE RP_HOME.TIE_GROUP_ID IS NOT NULL
),

CTE_BASE as (
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
    from CTE_DEDUP_GAMES_TIED_TEAMS
),

CTE_HOME_COUNTS as (
    select
        season,
        ranking_date,
        tie_group_id,
        matchup_id,
        home_team_id,
        count(*) as home_count
    from CTE_BASE
    group by season, ranking_date, tie_group_id, matchup_id, home_team_id
),

CTE_TOP_HOME as (
    select
        season,
        ranking_date,
        tie_group_id,
        matchup_id,
        home_team_id as top_home_team_id,
        row_number() over (
            partition by season, ranking_date, tie_group_id, matchup_id
            order by home_count desc, home_team_id
        ) as rn
    from CTE_HOME_COUNTS
),

CTE_TOP_HOME_FINAL as (
    select season, ranking_date, tie_group_id, matchup_id, top_home_team_id
    from CTE_TOP_HOME
    where rn = 1
),

CTE_OLDEST_GAME AS (
    SELECT
        B.SEASON,
        B.RANKING_DATE,
        B.TIE_GROUP_ID,
        B.MATCHUP_ID,
        B.GAME_ID,
        ROW_NUMBER() OVER (
            PARTITION BY B.SEASON, B.RANKING_DATE, B.TIE_GROUP_ID, B.MATCHUP_ID 
            ORDER BY B.GAME_DATE ASC, B.GAME_ID
        ) AS RN_OLDEST
    FROM CTE_BASE B
    INNER JOIN CTE_TOP_HOME_FINAL T
        ON  B.SEASON = T.SEASON                              
        AND B.RANKING_DATE = T.RANKING_DATE                  
        AND B.TIE_GROUP_ID = T.TIE_GROUP_ID                  
        AND B.MATCHUP_ID = T.MATCHUP_ID
        AND B.HOME_TEAM_ID = T.TOP_HOME_TEAM_ID
),

CTE_LABELED_GAMES AS (
    SELECT
        B.*,
        CASE
            WHEN B.MATCHUP_GAME_COUNT % 2 = 0 THEN 1
            WHEN OG.RN_OLDEST = 1 THEN 0
            ELSE 1
        END AS FLAG
    FROM CTE_BASE B
    LEFT JOIN CTE_OLDEST_GAME OG
        ON  B.SEASON = OG.SEASON                          
        AND B.RANKING_DATE = OG.RANKING_DATE                  
        AND B.TIE_GROUP_ID = OG.TIE_GROUP_ID                 
        AND B.MATCHUP_ID = OG.MATCHUP_ID
        AND B.GAME_ID = OG.GAME_ID
        AND OG.RN_OLDEST = 1
),

CTE_TEAM_GAMES AS (
    SELECT
        SEASON,
        RANKING_DATE,
        TIE_GROUP_ID,
        GAME_ID,
        HOME_TEAM_ID    AS TEAM_ID,
        HOME_TEAM_SCORE AS TEAM_SCORE,
        AWAY_TEAM_SCORE AS OPPONENT_SCORE,
        LAST_PERIOD_TYPE
    FROM CTE_LABELED_GAMES
    WHERE FLAG = 1

    UNION ALL

    SELECT
        SEASON,
        RANKING_DATE,
        TIE_GROUP_ID,
        GAME_ID,
        AWAY_TEAM_ID    AS TEAM_ID,
        AWAY_TEAM_SCORE AS TEAM_SCORE,
        HOME_TEAM_SCORE AS OPPONENT_SCORE,
        LAST_PERIOD_TYPE
    FROM CTE_LABELED_GAMES
    WHERE FLAG = 1
),

CTE_TEAM_STATS AS (
    SELECT
        SEASON,
        RANKING_DATE,
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
    GROUP BY SEASON, RANKING_DATE, TIE_GROUP_ID, TEAM_ID
)

SELECT
    SEASON,
    RANKING_DATE,
    TIE_GROUP_ID,
    TEAM_ID,
    POINTS_EARNED,
    GAMES_PLAYED,
    POINTS_EARNED / (GAMES_PLAYED * 2) AS TIE_RATE
FROM CTE_TEAM_STATS
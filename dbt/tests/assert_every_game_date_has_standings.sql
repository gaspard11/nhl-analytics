-- Every date with a finished game must have standings in fct_league_rankings.
-- Catches a day that was loaded into raw but never processed by the cumulative models.
-- Returns the game dates missing from fct_league_rankings.

with ranking_dates as (

    select distinct
        season,
        ranking_date
    from {{ ref('fct_league_rankings') }}

)

select distinct
    g.season,
    g.game_date
from {{ ref('stg_nhl_api__games') }} g
left join ranking_dates r
    on r.season = g.season
   and r.ranking_date = g.game_date
where r.ranking_date is null

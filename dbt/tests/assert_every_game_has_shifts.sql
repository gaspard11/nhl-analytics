-- Every finished game should have its shifts. Without them, its goalies get no time on ice, so
-- their games played, time on ice, GAA and shutouts are wrong.
-- A warning, not an error: the NHL can publish a shift chart after the game is final, and the next
-- daily run picks it up. If a game stays here for days, the shift API never got it: reload it from
-- the HTML reports with the DAG backfill_shifts_from_html.
-- Returns the finished games without any shift.

{{ config(severity='warn') }}

select
    g.game_id,
    g.game_date
from {{ ref('stg_nhl_api__games') }} g
where not exists (
    select 1
    from {{ ref('stg_nhl_api__games_shifts') }} s
    where s.game_id = g.game_id
)

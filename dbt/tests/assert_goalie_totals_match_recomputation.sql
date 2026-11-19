-- On the latest ranking date of each season, every season-to-date total in fct_goalie_stats must
-- equal a sum from scratch over the per-game models. Catches drift from incremental runs, and a stat
-- forgotten in prior_rows / prior_state, which a full refresh doesn't show.
-- Returns the goalies with at least one total that differs.

-- Every stat accumulated by fct_goalie_stats, as (column in the mart, per-game stat it is summed
-- from); games_played is counted from the toi_seconds rows
{% set stats = [
    ('toi_seconds', 'toi_seconds'), ('goals', 'goals'), ('assists', 'assists'),
    ('saves', 'saves'), ('goals_against', 'goals_against'), ('shutouts', 'shutout'),
    ('penalty_minutes', 'penalty_minutes'), ('games_started', 'games_started'),
    ('awarded_wins', 'awarded_wins'), ('awarded_losses', 'awarded_losses'),
    ('awarded_ot_losses', 'awarded_ot_losses')
] %}

with latest as (

    select
        season,
        max(ranking_date) as ranking_date
    from {{ ref('fct_goalie_stats') }}
    group by season

),

stored as (

    select c.*
    from {{ ref('fct_goalie_stats') }} c
    join latest l
        on l.season = c.season
       and l.ranking_date = c.ranking_date

),

game_stats as (

    select game_id, player_id, stat_name, stat_value from {{ ref('int_player_game_stats') }}
    union all
    select game_id, player_id, stat_name, stat_value from {{ ref('int_goalie_game_stats') }}

),

recomputed as (

    select
        g.season,
        s.player_id,
        sum(iff(s.stat_name = 'toi_seconds', 1, 0)) as games_played,
        {% for column, stat in stats %}
        sum(iff(s.stat_name = '{{ stat }}', s.stat_value, 0)) as {{ column }}{{ "," if not loop.last }}
        {% endfor %}
    from game_stats s
    join {{ ref('stg_nhl_api__games') }} g
        on g.game_id = s.game_id
    join {{ ref('dim_players') }} p
        on p.player_id = s.player_id
       and p.position = 'G'
    join latest l
        on l.season = g.season
       and g.game_date <= l.ranking_date
    group by g.season, s.player_id
    -- Same rule as the mart: a goalie appears from their first game
    having sum(iff(s.stat_name = 'toi_seconds', 1, 0)) > 0

)

select
    coalesce(s.season, r.season)       as season,
    coalesce(s.player_id, r.player_id) as player_id
from stored s
full outer join recomputed r
    on r.season = s.season
   and r.player_id = s.player_id
where s.player_id is null
   or r.player_id is null
   or s.games_played <> r.games_played
   {% for column, stat in stats %}
   or s.{{ column }} <> r.{{ column }}
   {% endfor %}

-- On the latest ranking date of each season, the cumulative totals in fct_league_rankings must equal
-- a recomputation from scratch over the game history (int_team_game_results is stateless).
-- Catches drift from incremental runs: a day counted twice, a day skipped, a bad re-run.
-- Returns the teams whose stored totals differ from the recomputed ones.

{%- set metrics = {
    'games_played':       'count(*)',
    'points':             'sum(g.points)',
    'total_wins':         'sum(g.win)',
    'regulation_wins':    'sum(g.regulation_win)',
    'regulation_ot_wins': 'sum(g.regulation_ot_win)',
    'goals_for':          'sum(g.goals_for)',
    'goals_against':      'sum(g.goals_against)'
} %}

with latest as (

    select
        season,
        max(ranking_date) as ranking_date
    from {{ ref('fct_league_rankings') }}
    group by season

),

stored as (

    select
        r.season,
        r.team_id,
        {%- for metric in metrics %}
        r.{{ metric }}{% if not loop.last %},{% endif %}
        {%- endfor %}
    from {{ ref('fct_league_rankings') }} r
    join latest l
        on l.season = r.season
       and l.ranking_date = r.ranking_date

),

recomputed as (

    select
        g.season,
        g.team_id,
        {%- for metric, expression in metrics.items() %}
        {{ expression }} as {{ metric }}{% if not loop.last %},{% endif %}
        {%- endfor %}
    from {{ ref('int_team_game_results') }} g
    join latest l
        on l.season = g.season
       and g.game_date <= l.ranking_date
    group by g.season, g.team_id

)

select
    coalesce(s.season, r.season)   as season,
    coalesce(s.team_id, r.team_id) as team_id,
    {%- for metric in metrics %}
    s.{{ metric }} as stored_{{ metric }},
    r.{{ metric }} as recomputed_{{ metric }}{% if not loop.last %},{% endif %}
    {%- endfor %}
from stored s
full outer join recomputed r
    on r.season = s.season
   and r.team_id = s.team_id
-- A team with no game yet is in stored (with 0) but not in recomputed: coalesce to 0.
-- A team missing from stored is flagged by coalescing it to -1.
where
    {%- for metric in metrics %}
    coalesce(s.{{ metric }}, -1) <> coalesce(r.{{ metric }}, 0){% if not loop.last %} or{% endif %}
    {%- endfor %}

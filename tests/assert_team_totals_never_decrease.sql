-- Within a season, a team's season-to-date totals can never go down from one ranking date to the next.
-- Catches a day replaced with older data, or a stale row left behind by a backfill.
-- Returns the rows where a total is lower than on the previous ranking date.

{%- set metrics = [
    'games_played',
    'points',
    'total_wins',
    'regulation_wins',
    'regulation_ot_wins',
    'goals_for',
    'goals_against'
] %}

with ordered as (

    select
        season,
        ranking_date,
        team_id,
        {%- for metric in metrics %}
        {{ metric }},
        lag({{ metric }}) over (partition by season, team_id order by ranking_date) as previous_{{ metric }}{% if not loop.last %},{% endif %}
        {%- endfor %}
    from {{ ref('league_rankings') }}

)

select *
from ordered
where
    {%- for metric in metrics %}
    {{ metric }} < previous_{{ metric }}{% if not loop.last %} or{% endif %}
    {%- endfor %}

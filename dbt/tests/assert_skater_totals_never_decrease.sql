-- Within a season, a skater's season-to-date totals can never go down from one ranking date to the next.
-- Catches a day replaced with older data on the skater side.
-- plus_minus isn't checked: it goes down on every goal against.
-- Returns the rows where a total is lower than on the previous ranking date.

{% set stats = [
    'games_played', 'toi_seconds', 'goals', 'assists', 'penalty_minutes', 'shots',
    'ev_goals', 'ev_assists', 'pp_goals', 'pp_assists', 'sh_goals', 'sh_assists', 'ps_goals'
] %}

with ordered as (

    select
        season,
        ranking_date,
        player_id,
        {% for stat in stats %}
        {{ stat }},
        lag({{ stat }}) over (partition by season, player_id order by ranking_date) as previous_{{ stat }}{{ "," if not loop.last }}
        {% endfor %}
    from {{ ref('fct_skater_stats') }}

)

select *
from ordered
where false
   {% for stat in stats %}
   or {{ stat }} < previous_{{ stat }}
   {% endfor %}

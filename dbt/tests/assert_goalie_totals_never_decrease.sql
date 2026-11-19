-- Within a season, a goalie's season-to-date totals can never go down from one ranking date to the next.
-- Catches a day replaced with older data on the goalie side.
-- Returns the rows where a total is lower than on the previous ranking date.

{% set stats = [
    'games_played', 'toi_seconds', 'goals', 'assists', 'saves', 'goals_against', 'shutouts',
    'penalty_minutes', 'games_started', 'awarded_wins', 'awarded_losses', 'awarded_ot_losses'
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
    from {{ ref('fct_goalie_stats') }}

)

select *
from ordered
where false
   {% for stat in stats %}
   or {{ stat }} < previous_{{ stat }}
   {% endfor %}

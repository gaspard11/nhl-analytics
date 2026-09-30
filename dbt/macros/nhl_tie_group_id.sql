{% macro nhl_tie_group_id(
    ranking_date = 'game_date',
    points='cumul_points',
    games_played='games_played',
    regulation_wins='regulation_wins',
    regulation_ot_wins='regulation_ot_wins',
    total_wins='total_wins'
) %}
    case
        when count(*) over (
            partition by {{ranking_date}}, {{ points }}, {{ games_played }}, {{ regulation_wins }},
                         {{ regulation_ot_wins }}, {{ total_wins }}
        ) > 1
        then {{ dbt_utils.generate_surrogate_key([
                points, games_played, regulation_wins, regulation_ot_wins, total_wins
             ]) }}
        else null
    end
{% endmacro %}